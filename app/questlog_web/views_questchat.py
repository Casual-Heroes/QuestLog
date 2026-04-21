import json
import logging
import re
import time

import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django_ratelimit.decorators import ratelimit

from app.db import get_db_session
from app.questlog_web.models import WebUser, WebFluxerGuildSettings
from sqlalchemy import text

logger = logging.getLogger(__name__)

# JWT token lifetime - 7 days in seconds
_TOKEN_TTL = 60 * 60 * 24 * 7

# Only alphanumeric + hyphens/underscores allowed in guild IDs and icon hashes
_SAFE_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]+$')


def _safe_cdn_part(value: str) -> str:
    """Return value only if it looks safe to embed in a CDN URL, else empty string."""
    if value and _SAFE_ID_RE.match(str(value)):
        return str(value)
    return ''


def _make_token(user_id: int) -> str:
    """Issue a signed JWT for a QuestLog user."""
    payload = {
        'sub': user_id,
        'iat': int(time.time()),
        'exp': int(time.time()) + _TOKEN_TTL,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def _verify_token(request) -> int | None:
    """
    Read Bearer token from Authorization header, verify signature,
    return user_id or None if invalid/expired.
    """
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        return int(payload['sub'])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def _user_dict(user: WebUser) -> dict:
    """Serialize a WebUser into the QuestChat profile shape. Never expose platform IDs."""
    legacy_labels = {1: 'Recruit', 2: 'Veteran', 3: 'Warden', 4: 'Guardian', 5: 'Legend'}
    return {
        'id': user.id,
        'username': user.username,
        'display_name': user.display_name or user.username,
        'avatar_url': user.avatar_url or '',
        'banner_url': getattr(user, 'banner_url', None) or '',
        'web_xp': user.web_xp or 0,
        'web_level': user.web_level or 1,
        'hero_points': user.hero_points or 0,
        'legacy_tier': user.legacy_tier or 1,
        'legacy_label': legacy_labels.get(user.legacy_tier or 1, 'Recruit'),
        'is_hero': bool(user.is_hero),
        'flair_emoji': user.flair_emoji,
        'flair_name': user.flair_name,
        # discord_id and fluxer_id intentionally omitted - internal linking keys only
    }


def _check_user(user: WebUser | None) -> bool:
    """Return True if user exists and is not banned or disabled."""
    return bool(user and not user.is_banned and not user.is_disabled)


# ---------------------------------------------------------------------------
# POST /ql/qc/auth/token/
# Body: { "username": "...", "password": "..." }
# Returns: { "token": "...", "user": {...} }
# Rate limited: 10 attempts per hour per IP
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
@ratelimit(key='ip', rate='10/h', method='POST', block=True)
def qc_auth_token(request):
    try:
        data = json.loads(request.body)
    except (ValueError, KeyError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or not password:
        return JsonResponse({'error': 'Username and password required'}, status=400)

    # Django auth: timing-safe, hashed password check
    django_user = authenticate(request, username=username, password=password)
    if not django_user:
        logger.warning('qc_auth failed: bad credentials for username=%s ip=%s',
                       username[:64], request.META.get('REMOTE_ADDR', ''))
        return JsonResponse({'error': 'Invalid credentials'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(username=django_user.username).first()
        if not _check_user(user):
            logger.warning('qc_auth denied: account suspended user_id=%s', getattr(user, 'id', '?'))
            return JsonResponse({'error': 'Account suspended'}, status=403)
        if not user.email_verified:
            logger.warning('qc_auth denied: email not verified user_id=%s', user.id)
            return JsonResponse({'error': 'Email not verified'}, status=403)

        logger.info('qc_auth token issued user_id=%s', user.id)
        token = _make_token(user.id)
        return JsonResponse({'token': token, 'user': _user_dict(user)})


# ---------------------------------------------------------------------------
# GET /ql/qc/me/
# Header: Authorization: Bearer <token>
# Returns: { "user": {...} }
# ---------------------------------------------------------------------------
@require_http_methods(['GET'])
def qc_me(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        return JsonResponse({'user': _user_dict(user)})


# ---------------------------------------------------------------------------
# GET /ql/qc/guilds/
# Header: Authorization: Bearer <token>
# Returns: { "guilds": [...] }
# Each guild: { id, name, icon_url, platform, is_owner, member_count }
# ---------------------------------------------------------------------------
@require_http_methods(['GET'])
def qc_guilds(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        guilds = []
        seen_ids: set[str] = set()

        # Fluxer guilds the user owns
        if user.fluxer_id:
            fluxer_owned = db.query(WebFluxerGuildSettings).filter_by(
                owner_id=str(user.fluxer_id), bot_present=1
            ).all()
            for g in fluxer_owned:
                gid = _safe_cdn_part(g.guild_id)
                if not gid or gid in seen_ids:
                    continue
                icon_url = ''
                safe_hash = _safe_cdn_part(g.guild_icon_hash)
                if safe_hash:
                    icon_url = f'https://cdn.fluxer.app/icons/{gid}/{safe_hash}.png'
                guilds.append({
                    'id': gid,
                    'name': g.guild_name or 'Unknown Guild',
                    'icon_url': icon_url,
                    'platform': 'fluxer',
                    'is_owner': True,
                    'member_count': g.member_count or 0,
                })
                seen_ids.add(gid)

        # Fluxer guilds the user is a member of (not owner)
        if user.fluxer_id:
            rows = db.execute(text(
                "SELECT gs.guild_id, gs.guild_name, gs.guild_icon_hash, gs.member_count "
                "FROM web_fluxer_guild_settings gs "
                "JOIN fluxer_member_xp mx ON mx.guild_id = gs.guild_id "
                "WHERE mx.user_id = :uid AND gs.owner_id != :oid AND gs.bot_present = 1"
            ), {'uid': str(user.fluxer_id), 'oid': str(user.fluxer_id)}).fetchall()
            for r in rows:
                gid = _safe_cdn_part(r.guild_id)
                if not gid or gid in seen_ids:
                    continue
                icon_url = ''
                safe_hash = _safe_cdn_part(r.guild_icon_hash)
                if safe_hash:
                    icon_url = f'https://cdn.fluxer.app/icons/{gid}/{safe_hash}.png'
                guilds.append({
                    'id': gid,
                    'name': r.guild_name or 'Unknown Guild',
                    'icon_url': icon_url,
                    'platform': 'fluxer',
                    'is_owner': False,
                    'member_count': r.member_count or 0,
                })
                seen_ids.add(gid)

        # Discord guilds the user owns
        if user.discord_id:
            discord_rows = db.execute(text(
                "SELECT guild_id, guild_name, icon_hash, member_count "
                "FROM guilds WHERE owner_id = :uid"
            ), {'uid': str(user.discord_id)}).fetchall()
            for r in discord_rows:
                gid = _safe_cdn_part(str(r.guild_id))
                if not gid or gid in seen_ids:
                    continue
                icon_url = ''
                safe_hash = _safe_cdn_part(r.icon_hash)
                if safe_hash:
                    icon_url = f'https://cdn.discordapp.com/icons/{gid}/{safe_hash}.png'
                guilds.append({
                    'id': gid,
                    'name': r.guild_name or 'Unknown Guild',
                    'icon_url': icon_url,
                    'platform': 'discord',
                    'is_owner': True,
                    'member_count': r.member_count or 0,
                })
                seen_ids.add(gid)

        return JsonResponse({'guilds': guilds})
