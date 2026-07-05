import csv
import hashlib
import io
import json
import logging
import secrets
import time
import urllib.request

import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django_ratelimit.decorators import ratelimit
from sqlalchemy import text

from app.db import get_db_session
from app.questlog_web.models import WebUser

_GATEWAY_URL = 'http://127.0.0.1:9500'

def _gateway_push(event: str, user_ids: list, data: dict):
    """Push a real-time event to connected users via the gateway internal endpoint."""
    import os
    secret = os.environ.get('QC_INTERNAL_SECRET', '')
    if not secret:
        return
    try:
        body = json.dumps({'event': event, 'user_ids': user_ids, 'data': data}).encode()
        req = urllib.request.Request(
            f'{_GATEWAY_URL}/internal/notify',
            data=body,
            headers={'Content-Type': 'application/json', 'X-Internal-Secret': secret},
            method='POST',
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception as e:
        logger.warning('gateway_push failed event=%s: %s', event, e)

# DM rep score below this = DMs permanently locked
_DM_REP_LOCK_THRESHOLD = 0
# How many unique reports before auto-lock
_DM_AUTO_LOCK_REPORTS = 3
# Platform default account age in days before DMs unlock
_DM_DEFAULT_ACCOUNT_AGE_DAYS = 7

logger = logging.getLogger(__name__)

_TOKEN_TTL = 60 * 60 * 24 * 7
_MAX_SERVER_NAME = 100
_MAX_CHANNEL_NAME = 100
_MAX_SERVERS_PER_USER = 10
_DEFAULT_CHANNELS = [
    ('general',     'text',  0),
    ('gaming-news', 'text',  1),
    ('lfg',         'text',  2),
    ('off-topic',   'text',  3),
    ('Voice Room 1','voice', 4),
]


def _make_token(user_id: int) -> str:
    payload = {
        'sub': user_id,
        'iat': int(time.time()),
        'exp': int(time.time()) + _TOKEN_TTL,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def _verify_token(request) -> int | None:
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    token = auth[7:]
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        return int(payload['sub'])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def _verify_token_verified(request):
    """Like _verify_token but also checks email_verified. Returns user_id or None."""
    user_id = _verify_token(request)
    if not user_id:
        return None, JsonResponse({'error': 'Unauthorized'}, status=401)
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user:
            return None, JsonResponse({'error': 'Unauthorized'}, status=401)
        if not user.email_verified:
            return None, JsonResponse({
                'error': 'verify_email',
                'message': 'Please verify your email before using this feature.'
            }, status=403)
    return user_id, None


def _user_dict(user: WebUser) -> dict:
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
    }


def _check_user(user: WebUser | None) -> bool:
    return bool(user and not user.is_banned and not user.is_disabled)


def _server_dict(row) -> dict:
    return {
        'id': row.id,
        'name': row.name,
        'icon_url': row.icon_url or '',
        'owner_id': row.owner_id,
        'invite_code': row.invite_code,
        'member_count': row.member_count,
    }


def _channel_dict(row) -> dict:
    return {
        'id': row.id,
        'server_id': row.server_id,
        'name': row.name,
        'type': row.type,
        'position': row.position,
    }


def _gen_invite_code() -> str:
    # 10 chars from a 32-char alphabet = ~51 bits entropy, URL-safe, no ambiguous chars
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no I/O/0/1 to avoid confusion
    return ''.join(secrets.choice(alphabet) for _ in range(10))


# ---------------------------------------------------------------------------
# POST /ql/qc/auth/token/
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
# GET  /ql/qc/servers/       - list servers the user belongs to
# POST /ql/qc/servers/       - create a new server
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def qc_servers(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        if request.method == 'GET':
            rows = db.execute(text("""
                SELECT s.id, s.name, s.icon_url, s.owner_id, s.invite_code,
                       COUNT(m2.user_id) AS member_count
                FROM qc_servers s
                JOIN qc_server_members m ON m.server_id = s.id AND m.user_id = :uid
                JOIN qc_server_members m2 ON m2.server_id = s.id
                GROUP BY s.id
                ORDER BY s.name
            """), {'uid': user_id}).fetchall()
            return JsonResponse({'servers': [_server_dict(r) for r in rows]})

        # POST - create server
        try:
            data = json.loads(request.body)
        except ValueError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        name = (data.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Server name required'}, status=400)
        if len(name) > _MAX_SERVER_NAME:
            return JsonResponse({'error': f'Name too long (max {_MAX_SERVER_NAME})'}, status=400)

        # Limit servers per user
        count = db.execute(text(
            "SELECT COUNT(*) FROM qc_server_members WHERE user_id = :uid AND role = 'owner'"
        ), {'uid': user_id}).scalar()
        if count >= _MAX_SERVERS_PER_USER:
            return JsonResponse({'error': f'Max {_MAX_SERVERS_PER_USER} servers per user'}, status=400)

        now = int(time.time())
        invite_code = _gen_invite_code()

        result = db.execute(text("""
            INSERT INTO qc_servers (name, icon_url, owner_id, invite_code, created_at)
            VALUES (:name, NULL, :owner, :code, :now)
        """), {'name': name, 'owner': user_id, 'code': invite_code, 'now': now})
        server_id = result.lastrowid

        # Add owner as member
        db.execute(text("""
            INSERT INTO qc_server_members (server_id, user_id, role, joined_at)
            VALUES (:sid, :uid, 'owner', :now)
        """), {'sid': server_id, 'uid': user_id, 'now': now})

        # Create default channels
        for ch_name, ch_type, position in _DEFAULT_CHANNELS:
            db.execute(text("""
                INSERT INTO qc_channels (server_id, name, type, position, created_at)
                VALUES (:sid, :name, :type, :pos, :now)
            """), {'sid': server_id, 'name': ch_name, 'type': ch_type, 'pos': position, 'now': now})

        db.commit()
        logger.info('qc_server created id=%s name=%s owner=%s', server_id, name, user_id)

        server = db.execute(text("""
            SELECT s.id, s.name, s.icon_url, s.owner_id, s.invite_code, 1 AS member_count
            FROM qc_servers s WHERE s.id = :sid
        """), {'sid': server_id}).fetchone()

        return JsonResponse({'server': _server_dict(server)}, status=201)


# ---------------------------------------------------------------------------
# POST /ql/qc/servers/join/   - join a server by invite code
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_servers_join(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    invite_code = (data.get('invite_code') or '').strip().upper()
    if not invite_code:
        return JsonResponse({'error': 'Invite code required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        server = db.execute(text(
            "SELECT id, name, icon_url, owner_id, invite_code FROM qc_servers WHERE invite_code = :code"
        ), {'code': invite_code}).fetchone()
        if not server:
            return JsonResponse({'error': 'Invalid invite code'}, status=404)

        # Already a member?
        existing = db.execute(text(
            "SELECT id FROM qc_server_members WHERE server_id = :sid AND user_id = :uid"
        ), {'sid': server.id, 'uid': user_id}).fetchone()
        if existing:
            return JsonResponse({'error': 'Already a member'}, status=400)

        now = int(time.time())
        db.execute(text("""
            INSERT INTO qc_server_members (server_id, user_id, role, joined_at)
            VALUES (:sid, :uid, 'member', :now)
        """), {'sid': server.id, 'uid': user_id, 'now': now})
        db.commit()

        member_count = db.execute(text(
            "SELECT COUNT(*) FROM qc_server_members WHERE server_id = :sid"
        ), {'sid': server.id}).scalar()

        return JsonResponse({'server': {
            'id': server.id,
            'name': server.name,
            'icon_url': server.icon_url or '',
            'owner_id': server.owner_id,
            'invite_code': server.invite_code,
            'member_count': member_count,
        }})


# ---------------------------------------------------------------------------
# POST /ql/qc/servers/<id>/channels/create/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_server_create_channel(request, server_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = (data.get('name') or '').strip().lower().replace(' ', '-')
    if not name:
        return JsonResponse({'error': 'Channel name required'}, status=400)
    if len(name) > _MAX_CHANNEL_NAME:
        return JsonResponse({'error': f'Name too long (max {_MAX_CHANNEL_NAME})'}, status=400)

    ch_type = data.get('type', 'text')
    if ch_type not in ('text', 'voice'):
        return JsonResponse({'error': 'Invalid channel type'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        # Must be owner or admin
        role_row = db.execute(text(
            "SELECT role FROM qc_server_members WHERE server_id = :sid AND user_id = :uid"
        ), {'sid': server_id, 'uid': user_id}).fetchone()
        if not role_row or role_row.role not in ('owner', 'admin'):
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Position = max existing + 1
        max_pos = db.execute(text(
            "SELECT COALESCE(MAX(position), -1) FROM qc_channels WHERE server_id = :sid"
        ), {'sid': server_id}).scalar()

        now = int(time.time())
        result = db.execute(text("""
            INSERT INTO qc_channels (server_id, name, type, position, created_at)
            VALUES (:sid, :name, :type, :pos, :now)
        """), {'sid': server_id, 'name': name, 'type': ch_type, 'pos': max_pos + 1, 'now': now})
        channel_id = result.lastrowid
        db.commit()

        logger.info('qc_channel created id=%s name=%s server=%s', channel_id, name, server_id)
        return JsonResponse({'channel': {
            'id': channel_id,
            'server_id': server_id,
            'name': name,
            'type': ch_type,
            'position': max_pos + 1,
        }}, status=201)


# ---------------------------------------------------------------------------
# GET /ql/qc/servers/<id>/channels/
# ---------------------------------------------------------------------------
@require_http_methods(['GET'])
def qc_server_channels(request, server_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        # Must be a member
        member = db.execute(text(
            "SELECT id FROM qc_server_members WHERE server_id = :sid AND user_id = :uid"
        ), {'sid': server_id, 'uid': user_id}).fetchone()
        if not member:
            return JsonResponse({'error': 'Not a member'}, status=403)

        channels = db.execute(text("""
            SELECT id, server_id, name, type, position
            FROM qc_channels WHERE server_id = :sid
            ORDER BY position
        """), {'sid': server_id}).fetchall()

        return JsonResponse({'channels': [_channel_dict(r) for r in channels]})


# ---------------------------------------------------------------------------
# GET  /ql/qc/dms/        - list open DMs
# ---------------------------------------------------------------------------
@require_http_methods(['GET'])
def qc_dms(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        rows = db.execute(text("""
            SELECT d.id, d.user_a_id, d.user_b_id,
                   ua.username AS a_username, COALESCE(ua.display_name, ua.username) AS a_display_name, COALESCE(ua.avatar_url, '') AS a_avatar_url,
                   ub.username AS b_username, COALESCE(ub.display_name, ub.username) AS b_display_name, COALESCE(ub.avatar_url, '') AS b_avatar_url
            FROM qc_dms d
            JOIN web_users ua ON ua.id = d.user_a_id
            JOIN web_users ub ON ub.id = d.user_b_id
            WHERE d.user_a_id = :uid OR d.user_b_id = :uid
            ORDER BY d.id DESC
        """), {'uid': user_id}).fetchall()

        dms = []
        for r in rows:
            other_id = r.user_b_id if r.user_a_id == user_id else r.user_a_id
            other_username = r.b_username if r.user_a_id == user_id else r.a_username
            other_display = r.b_display_name if r.user_a_id == user_id else r.a_display_name
            other_avatar = r.b_avatar_url if r.user_a_id == user_id else r.a_avatar_url
            dms.append({
                'id': r.id,
                'channel_id': f'dm_{r.id}',
                'other_user_id': other_id,
                'other_username': other_username,
                'other_display_name': other_display,
                'other_avatar_url': other_avatar,
            })

        return JsonResponse({'dms': dms})


# ---------------------------------------------------------------------------
# Internal: DM gate check
# Returns None if allowed, or a string reason if blocked.
# ---------------------------------------------------------------------------
def _check_dm_gate(db, sender_id: int, recipient_id: int) -> str | None:
    now = int(time.time())

    # --- Gate 0: Platform bad actor registry ---
    sender_user = db.query(WebUser).filter_by(id=sender_id).first()
    bad_actor = db.execute(text(
        "SELECT severity FROM qc_bad_actors WHERE user_id = :uid AND severity IN ('ban','ip_ban') LIMIT 1"
    ), {'uid': sender_id}).fetchone()
    if bad_actor:
        return 'Your account has been flagged by the platform. DMs are disabled.'

    # --- Gate 1: DM reputation score ---
    rep = db.execute(text(
        "SELECT score, locked FROM qc_dm_reputation WHERE user_id = :uid"
    ), {'uid': sender_id}).fetchone()
    if rep and (rep.locked or rep.score <= _DM_REP_LOCK_THRESHOLD):
        return 'Your DM reputation score is too low to send messages. Contact support to appeal.'

    # --- Gate 2: Account age ---
    # Use web_users.created_at (Unix epoch)
    if sender_user and sender_user.created_at:
        age_days = (now - sender_user.created_at) / 86400
        if age_days < _DM_DEFAULT_ACCOUNT_AGE_DAYS:
            days_left = int(_DM_DEFAULT_ACCOUNT_AGE_DAYS - age_days) + 1
            return f'Your account must be at least {_DM_DEFAULT_ACCOUNT_AGE_DAYS} days old to send DMs. {days_left} day(s) remaining.'

    # --- Gate 3: Shared server membership ---
    shared = db.execute(text("""
        SELECT s.id, s.name
        FROM qc_servers s
        JOIN qc_server_members ma ON ma.server_id = s.id AND ma.user_id = :sender
        JOIN qc_server_members mb ON mb.server_id = s.id AND mb.user_id = :recipient
        LIMIT 1
    """), {'sender': sender_id, 'recipient': recipient_id}).fetchone()
    if not shared:
        return 'You must share a server with this user before you can DM them.'

    # Get server settings for that shared server
    settings_row = db.execute(text(
        "SELECT dm_min_messages, dm_min_days, dm_require_friends, dm_min_account_age FROM qc_server_settings WHERE server_id = :sid"
    ), {'sid': shared.id}).fetchone()
    min_messages = settings_row.dm_min_messages if settings_row else 10
    min_days = settings_row.dm_min_days if settings_row else 3
    require_friends = bool(settings_row.dm_require_friends) if settings_row else True
    min_account_age = settings_row.dm_min_account_age if settings_row else _DM_DEFAULT_ACCOUNT_AGE_DAYS

    # Server-specific account age override
    if sender_user and sender_user.created_at:
        age_days = (now - sender_user.created_at) / 86400
        if age_days < min_account_age:
            days_left = int(min_account_age - age_days) + 1
            return f'Your account must be {min_account_age} days old to DM members of {shared.name}. {days_left} day(s) remaining.'

    # --- Gate 4: Server activity threshold ---
    cutoff = now - (min_days * 86400)
    msg_count = db.execute(text("""
        SELECT COUNT(*) FROM qc_messages
        WHERE guild_id = :gid AND user_id = :uid AND created_at >= :cutoff AND deleted_at IS NULL
    """), {'gid': str(shared.id), 'uid': sender_id, 'cutoff': cutoff}).scalar() or 0
    if msg_count < min_messages:
        return f'You need at least {min_messages} messages in a shared server within the last {min_days} day(s) to send DMs. You have {msg_count}.'

    # --- Gate 5: Friends (if required by server) ---
    if require_friends:
        friendship = db.execute(text("""
            SELECT id FROM qc_friends
            WHERE status = 'accepted'
              AND ((requester_id = :a AND addressee_id = :b) OR (requester_id = :b AND addressee_id = :a))
        """), {'a': sender_id, 'b': recipient_id}).fetchone()
        if not friendship:
            return 'You must be friends with this user to send them a DM. Send a friend request first.'

    return None


# ---------------------------------------------------------------------------
# POST /ql/qc/dms/open/   - open or find DM with another user (gated)
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
@ratelimit(key='ip', rate='30/h', method='POST', block=True)
def qc_dms_open(request):
    user_id, gate = _verify_token_verified(request)
    if gate: return gate

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    other_id = data.get('user_id')
    if not other_id or not isinstance(other_id, int):
        return JsonResponse({'error': 'user_id required'}, status=400)
    if other_id == user_id:
        return JsonResponse({'error': 'Cannot DM yourself'}, status=400)

    a_id = min(user_id, other_id)
    b_id = max(user_id, other_id)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        other = db.query(WebUser).filter_by(id=other_id).first()
        if not _check_user(other):
            return JsonResponse({'error': 'User not found'}, status=404)

        # Check if DM already exists - existing DMs bypass gate (conversation already established)
        existing = db.execute(text(
            "SELECT id FROM qc_dms WHERE user_a_id = :a AND user_b_id = :b"
        ), {'a': a_id, 'b': b_id}).fetchone()

        if not existing:
            # Run full gate check for new DMs only
            block_reason = _check_dm_gate(db, user_id, other_id)
            if block_reason:
                return JsonResponse({'error': block_reason, 'blocked': True}, status=403)

            now = int(time.time())
            result = db.execute(text(
                "INSERT INTO qc_dms (user_a_id, user_b_id, created_at) VALUES (:a, :b, :now)"
            ), {'a': a_id, 'b': b_id, 'now': now})
            db.commit()
            dm_id = result.lastrowid
        else:
            dm_id = existing.id

        logger.info('qc_dm opened id=%s sender=%s recipient=%s', dm_id, user_id, other_id)
        return JsonResponse({
            'dm': {
                'id': dm_id,
                'channel_id': f'dm_{dm_id}',
                'other_user_id': other_id,
                'other_username': other.username,
                'other_display_name': other.display_name or other.username,
                'other_avatar_url': other.avatar_url or '',
            }
        })


# ---------------------------------------------------------------------------
# POST /ql/qc/dms/<id>/report/  - report a DM as spam/abuse
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
@ratelimit(key='ip', rate='10/h', method='POST', block=True)
def qc_dm_report(request, dm_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    valid_reasons = ('spam', 'harassment', 'csam', 'hate_speech', 'threats', 'other')
    reason = data.get('reason', 'spam')
    if reason not in valid_reasons:
        return JsonResponse({'error': 'Invalid reason'}, status=400)
    details = (data.get('details') or '')[:500]

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        # Must be a participant in the DM
        dm = db.execute(text(
            "SELECT id, user_a_id, user_b_id FROM qc_dms WHERE id = :did"
        ), {'did': dm_id}).fetchone()
        if not dm or user_id not in (dm.user_a_id, dm.user_b_id):
            return JsonResponse({'error': 'Not found'}, status=404)

        reported_id = dm.user_b_id if dm.user_a_id == user_id else dm.user_a_id

        # Deduplicated - one report per dm per reporter
        existing = db.execute(text(
            "SELECT id FROM qc_dm_reports WHERE dm_id = :did AND reporter_id = :uid"
        ), {'did': dm_id, 'uid': user_id}).fetchone()
        if existing:
            return JsonResponse({'error': 'Already reported'}, status=400)

        now = int(time.time())
        db.execute(text("""
            INSERT INTO qc_dm_reports (dm_id, reporter_id, reported_id, reason, details, created_at)
            VALUES (:did, :rptr, :rptd, :reason, :details, :now)
        """), {'did': dm_id, 'rptr': user_id, 'rptd': reported_id, 'reason': reason, 'details': details, 'now': now})

        # Update or create reputation row
        rep = db.execute(text(
            "SELECT score, reports_count FROM qc_dm_reputation WHERE user_id = :uid"
        ), {'uid': reported_id}).fetchone()

        if rep:
            new_score = rep.score - 35
            new_count = rep.reports_count + 1
            auto_lock = new_count >= _DM_AUTO_LOCK_REPORTS or new_score <= _DM_REP_LOCK_THRESHOLD
            db.execute(text("""
                UPDATE qc_dm_reputation
                SET score = :score, reports_count = :cnt, locked = :locked,
                    locked_reason = IF(:locked, 'Auto-locked: too many reports', locked_reason),
                    updated_at = :now
                WHERE user_id = :uid
            """), {'score': new_score, 'cnt': new_count, 'locked': int(auto_lock), 'now': now, 'uid': reported_id})
        else:
            new_score = 65  # 100 - 35 for first report
            new_count = 1
            auto_lock = new_count >= _DM_AUTO_LOCK_REPORTS
            db.execute(text("""
                INSERT INTO qc_dm_reputation (user_id, score, reports_count, locked, locked_reason, updated_at)
                VALUES (:uid, :score, :cnt, :locked, IF(:locked, 'Auto-locked: too many reports', NULL), :now)
            """), {'uid': reported_id, 'score': new_score, 'cnt': new_count, 'locked': int(auto_lock), 'now': now})

        db.commit()
        logger.warning('qc_dm_report dm=%s reporter=%s reported=%s reason=%s score_now=%s',
                       dm_id, user_id, reported_id, reason, new_score)

        return JsonResponse({'ok': True, 'message': 'Report submitted. Thank you for keeping QuestChat safe.'})


# ---------------------------------------------------------------------------
# Friend system
# POST /ql/qc/friends/request/   - send friend request
# POST /ql/qc/friends/respond/   - accept or decline
# GET  /ql/qc/friends/           - list friends + pending requests
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
@ratelimit(key='ip', rate='20/h', method='POST', block=True)
def qc_friend_request(request):
    user_id, gate = _verify_token_verified(request)
    if gate: return gate

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Accept either user_id (int) or username (str)
    other_id = data.get('user_id')
    username_lookup = (data.get('username') or '').strip()

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        if username_lookup:
            other = db.query(WebUser).filter_by(username=username_lookup).first()
        elif other_id and isinstance(other_id, int):
            other = db.query(WebUser).filter_by(id=other_id).first()
        else:
            return JsonResponse({'error': 'user_id or username required'}, status=400)

        if not _check_user(other):
            return JsonResponse({'error': 'User not found'}, status=404)
        other_id = other.id
        if other_id == user_id:
            return JsonResponse({'error': 'Cannot add yourself'}, status=400)

        # Check no existing relationship
        existing = db.execute(text("""
            SELECT id, status FROM qc_friends
            WHERE (requester_id = :a AND addressee_id = :b) OR (requester_id = :b AND addressee_id = :a)
        """), {'a': user_id, 'b': other_id}).fetchone()

        if existing:
            if existing.status == 'accepted':
                return JsonResponse({'error': 'Already friends'}, status=400)
            if existing.status == 'pending':
                return JsonResponse({'error': 'Friend request already sent'}, status=400)
            if existing.status == 'blocked':
                return JsonResponse({'error': 'Unable to send request'}, status=403)

        now = int(time.time())
        db.execute(text("""
            INSERT INTO qc_friends (requester_id, addressee_id, status, created_at, updated_at)
            VALUES (:req, :adr, 'pending', :now, :now)
        """), {'req': user_id, 'adr': other_id, 'now': now})
        db.commit()

        logger.info('qc_friend_request from=%s to=%s', user_id, other_id)
        return JsonResponse({'ok': True, 'message': f'Friend request sent to {other.display_name or other.username}.'})


@csrf_exempt
@require_http_methods(['POST'])
def qc_friend_respond(request):
    user_id, gate = _verify_token_verified(request)
    if gate: return gate

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    request_id = data.get('request_id')
    action = data.get('action')  # 'accept' or 'decline'
    if not request_id or action not in ('accept', 'decline'):
        return JsonResponse({'error': 'request_id and action (accept/decline) required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        row = db.execute(text(
            "SELECT id, requester_id, addressee_id, status FROM qc_friends WHERE id = :rid AND addressee_id = :uid"
        ), {'rid': request_id, 'uid': user_id}).fetchone()
        if not row:
            return JsonResponse({'error': 'Request not found'}, status=404)
        if row.status != 'pending':
            return JsonResponse({'error': 'Request already handled'}, status=400)

        now = int(time.time())
        new_status = 'accepted' if action == 'accept' else 'blocked'
        db.execute(text(
            "UPDATE qc_friends SET status = :status, updated_at = :now WHERE id = :rid"
        ), {'status': new_status, 'now': now, 'rid': request_id})
        db.commit()

        # Push real-time update to both users
        if new_status == 'accepted':
            # Get both users' display info for the push payload
            requester = db.query(WebUser).filter_by(id=row.requester_id).first()
            addressee = db.query(WebUser).filter_by(id=row.addressee_id).first()
            if requester and addressee:
                _gateway_push('friend_update', [row.requester_id, row.addressee_id], {
                    'status': 'accepted',
                    'request_id': request_id,
                    'users': {
                        str(row.requester_id): {
                            'user_id': row.requester_id,
                            'username': requester.username,
                            'display_name': requester.display_name or requester.username,
                            'avatar_url': requester.avatar_url or '',
                        },
                        str(row.addressee_id): {
                            'user_id': row.addressee_id,
                            'username': addressee.username,
                            'display_name': addressee.display_name or addressee.username,
                            'avatar_url': addressee.avatar_url or '',
                        },
                    }
                })
        elif new_status == 'blocked':
            _gateway_push('friend_update', [row.requester_id, row.addressee_id], {
                'status': 'declined',
                'request_id': request_id,
            })

        return JsonResponse({'ok': True, 'status': new_status})


@require_http_methods(['GET'])
def qc_friends(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        rows = db.execute(text("""
            SELECT f.id, f.requester_id, f.addressee_id, f.status,
                   ur.username AS req_username, COALESCE(ur.display_name, ur.username) AS req_display, COALESCE(ur.avatar_url,'') AS req_avatar,
                   ua.username AS adr_username, COALESCE(ua.display_name, ua.username) AS adr_display, COALESCE(ua.avatar_url,'') AS adr_avatar
            FROM qc_friends f
            JOIN web_users ur ON ur.id = f.requester_id
            JOIN web_users ua ON ua.id = f.addressee_id
            WHERE (f.requester_id = :uid OR f.addressee_id = :uid)
              AND f.status IN ('accepted','pending')
            ORDER BY f.updated_at DESC
        """), {'uid': user_id}).fetchall()

        friends = []
        pending_in = []
        pending_out = []
        for r in rows:
            is_requester = r.requester_id == user_id
            other_id = r.addressee_id if is_requester else r.requester_id
            other_username = r.adr_username if is_requester else r.req_username
            other_display = r.adr_display if is_requester else r.req_display
            other_avatar = r.adr_avatar if is_requester else r.req_avatar
            entry = {
                'request_id': r.id,
                'user_id': other_id,
                'username': other_username,
                'display_name': other_display,
                'avatar_url': other_avatar,
            }
            if r.status == 'accepted':
                friends.append(entry)
            elif r.status == 'pending':
                if is_requester:
                    pending_out.append(entry)
                else:
                    pending_in.append(entry)

        return JsonResponse({'friends': friends, 'pending_in': pending_in, 'pending_out': pending_out})


# ---------------------------------------------------------------------------
# Unfriend
# POST /ql/qc/friends/remove/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_friend_remove(request):
    user_id, gate = _verify_token_verified(request)
    if gate: return gate
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    other_id = data.get('user_id')
    if not other_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        result = db.execute(text("""
            DELETE FROM qc_friends
            WHERE ((requester_id = :a AND addressee_id = :b) OR (requester_id = :b AND addressee_id = :a))
              AND status = 'accepted'
        """), {'a': user_id, 'b': other_id})
        db.commit()

        if result.rowcount == 0:
            return JsonResponse({'error': 'Not friends'}, status=404)

        _gateway_push('friend_update', [user_id, other_id], {'status': 'removed', 'by': user_id})
        return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Cancel outgoing friend request
# POST /ql/qc/friends/cancel/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_friend_cancel(request):
    user_id, gate = _verify_token_verified(request)
    if gate: return gate
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    other_id = data.get('user_id')
    if not other_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        result = db.execute(text("""
            DELETE FROM qc_friends
            WHERE requester_id = :uid AND addressee_id = :other AND status = 'pending'
        """), {'uid': user_id, 'other': other_id})
        db.commit()

        if result.rowcount == 0:
            return JsonResponse({'error': 'No pending request found'}, status=404)

        _gateway_push('friend_update', [user_id, other_id], {'status': 'cancelled', 'by': user_id})
        return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Block / Unblock
# POST /ql/qc/block/         { user_id }
# POST /ql/qc/unblock/       { user_id }
# GET  /ql/qc/blocks/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_block(request):
    user_id, gate = _verify_token_verified(request)
    if gate: return gate
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    other_id = data.get('user_id')
    if not other_id or other_id == user_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        now = int(time.time())
        # Remove any friend relationship first
        db.execute(text("""
            DELETE FROM qc_friends
            WHERE (requester_id = :a AND addressee_id = :b) OR (requester_id = :b AND addressee_id = :a)
        """), {'a': user_id, 'b': other_id})

        # Upsert block
        db.execute(text("""
            INSERT INTO qc_blocks (blocker_id, blocked_id, created_at)
            VALUES (:blocker, :blocked, :now)
            ON DUPLICATE KEY UPDATE created_at = :now
        """), {'blocker': user_id, 'blocked': other_id, 'now': now})
        db.commit()

        _gateway_push('friend_update', [user_id, other_id], {'status': 'blocked', 'by': user_id})
        return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def qc_unblock(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    other_id = data.get('user_id')
    if not other_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        db.execute(text("""
            DELETE FROM qc_blocks WHERE blocker_id = :blocker AND blocked_id = :blocked
        """), {'blocker': user_id, 'blocked': other_id})
        db.commit()

        _gateway_push('friend_update', [user_id, other_id], {'status': 'unblocked', 'by': user_id})
        return JsonResponse({'ok': True})


@require_http_methods(['GET'])
def qc_blocks(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        rows = db.execute(text("""
            SELECT b.blocked_id, COALESCE(u.display_name, u.username) AS display_name,
                   u.username, COALESCE(u.avatar_url, '') AS avatar_url, b.created_at
            FROM qc_blocks b
            JOIN web_users u ON u.id = b.blocked_id
            WHERE b.blocker_id = :uid
            ORDER BY b.created_at DESC
        """), {'uid': user_id}).fetchall()

        return JsonResponse({'blocks': [
            {'user_id': r.blocked_id, 'display_name': r.display_name,
             'username': r.username, 'avatar_url': r.avatar_url}
            for r in rows
        ]})


# ---------------------------------------------------------------------------
# Ignore / Unignore  (mute without blocking - they can still message you)
# POST /ql/qc/ignore/        { user_id }
# POST /ql/qc/unignore/      { user_id }
# GET  /ql/qc/ignores/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_ignore(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    other_id = data.get('user_id')
    if not other_id or other_id == user_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        now = int(time.time())
        db.execute(text("""
            INSERT INTO qc_ignores (ignorer_id, ignored_id, created_at)
            VALUES (:ignorer, :ignored, :now)
            ON DUPLICATE KEY UPDATE created_at = :now
        """), {'ignorer': user_id, 'ignored': other_id, 'now': now})
        db.commit()

        return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def qc_unignore(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    other_id = data.get('user_id')
    if not other_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        db.execute(text("""
            DELETE FROM qc_ignores WHERE ignorer_id = :ignorer AND ignored_id = :ignored
        """), {'ignorer': user_id, 'ignored': other_id})
        db.commit()

        return JsonResponse({'ok': True})


@require_http_methods(['GET'])
def qc_ignores(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        rows = db.execute(text("""
            SELECT i.ignored_id, COALESCE(u.display_name, u.username) AS display_name,
                   u.username, COALESCE(u.avatar_url, '') AS avatar_url
            FROM qc_ignores i
            JOIN web_users u ON u.id = i.ignored_id
            WHERE i.ignorer_id = :uid
            ORDER BY i.created_at DESC
        """), {'uid': user_id}).fetchall()

        return JsonResponse({'ignores': [
            {'user_id': r.ignored_id, 'display_name': r.display_name,
             'username': r.username, 'avatar_url': r.avatar_url}
            for r in rows
        ]})


# ---------------------------------------------------------------------------
# Message edit / delete / react
# POST /ql/qc/messages/<id>/edit/
# POST /ql/qc/messages/<id>/delete/
# POST /ql/qc/messages/<id>/react/
# ---------------------------------------------------------------------------

# These are REST fallbacks - the primary path is WS (edit/delete/react go via WS).
# These endpoints exist for clients that can't use WS for a specific action.

@csrf_exempt
@require_http_methods(['POST'])
@ratelimit(key='ip', rate='60/m', method='POST', block=True)
def qc_message_edit(request, msg_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    content = (data.get('content') or '').strip()
    if not content or len(content) > 2000:
        return JsonResponse({'error': 'Content required (max 2000)'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        row = db.execute(text(
            "SELECT id, guild_id, channel_id, user_id FROM qc_messages WHERE id = :mid AND deleted_at IS NULL"
        ), {'mid': msg_id}).fetchone()
        if not row:
            return JsonResponse({'error': 'Not found'}, status=404)
        if row.user_id != user_id:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        now = int(time.time())
        db.execute(text(
            "UPDATE qc_messages SET content = :c, edited_at = :now WHERE id = :mid"
        ), {'c': content, 'now': now, 'mid': msg_id})
        db.commit()
        _gateway_push('message_edit', [], {
            'message_id': msg_id, 'guild_id': row.guild_id,
            'channel_id': row.channel_id, 'content': content, 'edited_at': now,
        })
        return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
@ratelimit(key='ip', rate='60/m', method='POST', block=True)
def qc_message_delete(request, msg_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        row = db.execute(text(
            "SELECT id, guild_id, channel_id, user_id FROM qc_messages WHERE id = :mid AND deleted_at IS NULL"
        ), {'mid': msg_id}).fetchone()
        if not row:
            return JsonResponse({'error': 'Not found'}, status=404)
        # Owner of message OR guild admin/owner may delete
        is_admin = db.execute(text(
            "SELECT id FROM qc_server_members WHERE server_id = :sid AND user_id = :uid AND role IN ('owner','admin')"
        ), {'sid': row.guild_id, 'uid': user_id}).fetchone()
        if row.user_id != user_id and not is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        now = int(time.time())
        db.execute(text("UPDATE qc_messages SET deleted_at = :now WHERE id = :mid"), {'now': now, 'mid': msg_id})
        db.commit()
        _gateway_push('message_delete', [], {
            'message_id': msg_id, 'guild_id': row.guild_id, 'channel_id': row.channel_id,
        })
        return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
@ratelimit(key='ip', rate='120/m', method='POST', block=True)
def qc_message_react(request, msg_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    emoji = (data.get('emoji') or '').strip()
    if not emoji or len(emoji) > 64:
        return JsonResponse({'error': 'Emoji required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        row = db.execute(text(
            "SELECT id, guild_id, channel_id FROM qc_messages WHERE id = :mid AND deleted_at IS NULL"
        ), {'mid': msg_id}).fetchone()
        if not row:
            return JsonResponse({'error': 'Not found'}, status=404)
        now = int(time.time())
        # Toggle: try insert, if dup then delete
        existing = db.execute(text(
            "SELECT id FROM qc_reactions WHERE message_id = :mid AND user_id = :uid AND emoji = :e"
        ), {'mid': msg_id, 'uid': user_id, 'e': emoji}).fetchone()
        if existing:
            db.execute(text("DELETE FROM qc_reactions WHERE message_id = :mid AND user_id = :uid AND emoji = :e"),
                       {'mid': msg_id, 'uid': user_id, 'e': emoji})
            added = False
        else:
            db.execute(text("INSERT INTO qc_reactions (message_id, user_id, emoji, created_at) VALUES (:mid,:uid,:e,:now)"),
                       {'mid': msg_id, 'uid': user_id, 'e': emoji, 'now': now})
            added = True
        db.commit()
        reactions = db.execute(text(
            "SELECT emoji, COUNT(*) as cnt, GROUP_CONCAT(user_id) as uids FROM qc_reactions WHERE message_id = :mid GROUP BY emoji"
        ), {'mid': msg_id}).fetchall()
        reactions_out = [{'emoji': r.emoji, 'count': r.cnt, 'user_ids': r.uids} for r in reactions]
        return JsonResponse({'ok': True, 'added': added, 'reactions': reactions_out})


# ---------------------------------------------------------------------------
# Moderation: kick, ban, unban, bans list
# POST /ql/qc/servers/<id>/kick/
# POST /ql/qc/servers/<id>/ban/
# POST /ql/qc/servers/<id>/unban/
# GET  /ql/qc/servers/<id>/bans/
# ---------------------------------------------------------------------------

@csrf_exempt
@require_http_methods(['POST'])
def qc_guild_kick(request, server_id):
    from app.questlog_web.helpers import safe_int
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    target_id = safe_int(data.get('user_id'), 0, min_val=1)
    if not target_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        role_row = db.execute(text(
            "SELECT role FROM qc_server_members WHERE server_id = :sid AND user_id = :uid"
        ), {'sid': server_id, 'uid': user_id}).fetchone()
        if not role_row or role_row.role not in ('owner', 'admin'):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        # Can't kick owner
        target_role = db.execute(text(
            "SELECT role FROM qc_server_members WHERE server_id = :sid AND user_id = :tid"
        ), {'sid': server_id, 'tid': target_id}).fetchone()
        if not target_role:
            return JsonResponse({'error': 'User not in server'}, status=404)
        if target_role.role == 'owner':
            return JsonResponse({'error': 'Cannot kick the owner'}, status=403)
        db.execute(text(
            "DELETE FROM qc_server_members WHERE server_id = :sid AND user_id = :tid"
        ), {'sid': server_id, 'tid': target_id})
        db.commit()
        _gateway_push('guild_kick', [target_id], {'server_id': server_id, 'kicked_by': user_id})
        logger.info('qc_guild_kick server=%s target=%s by=%s', server_id, target_id, user_id)
        return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def qc_guild_ban(request, server_id):
    from app.questlog_web.helpers import safe_int
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    target_id = safe_int(data.get('user_id'), 0, min_val=1)
    reason = (data.get('reason') or '')[:500]
    if not target_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        role_row = db.execute(text(
            "SELECT role FROM qc_server_members WHERE server_id = :sid AND user_id = :uid"
        ), {'sid': server_id, 'uid': user_id}).fetchone()
        if not role_row or role_row.role not in ('owner', 'admin'):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        target_role = db.execute(text(
            "SELECT role FROM qc_server_members WHERE server_id = :sid AND user_id = :tid"
        ), {'sid': server_id, 'tid': target_id}).fetchone()
        if target_role and target_role.role == 'owner':
            return JsonResponse({'error': 'Cannot ban the owner'}, status=403)
        now = int(time.time())
        # Remove from server
        db.execute(text(
            "DELETE FROM qc_server_members WHERE server_id = :sid AND user_id = :tid"
        ), {'sid': server_id, 'tid': target_id})
        # Add ban record
        db.execute(text("""
            INSERT INTO qc_guild_bans (server_id, user_id, banned_by, reason, created_at)
            VALUES (:sid, :tid, :by, :reason, :now)
            ON DUPLICATE KEY UPDATE banned_by = :by, reason = :reason, created_at = :now
        """), {'sid': server_id, 'tid': target_id, 'by': user_id, 'reason': reason, 'now': now})
        db.commit()
        _gateway_push('guild_ban', [target_id], {'server_id': server_id, 'banned_by': user_id})
        logger.info('qc_guild_ban server=%s target=%s by=%s reason=%s', server_id, target_id, user_id, reason)
        return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
def qc_guild_unban(request, server_id):
    from app.questlog_web.helpers import safe_int
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    target_id = safe_int(data.get('user_id'), 0, min_val=1)
    if not target_id:
        return JsonResponse({'error': 'user_id required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        role_row = db.execute(text(
            "SELECT role FROM qc_server_members WHERE server_id = :sid AND user_id = :uid"
        ), {'sid': server_id, 'uid': user_id}).fetchone()
        if not role_row or role_row.role not in ('owner', 'admin'):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        db.execute(text(
            "DELETE FROM qc_guild_bans WHERE server_id = :sid AND user_id = :tid"
        ), {'sid': server_id, 'tid': target_id})
        db.commit()
        return JsonResponse({'ok': True})


@require_http_methods(['GET'])
def qc_guild_bans(request, server_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        role_row = db.execute(text(
            "SELECT role FROM qc_server_members WHERE server_id = :sid AND user_id = :uid"
        ), {'sid': server_id, 'uid': user_id}).fetchone()
        if not role_row or role_row.role not in ('owner', 'admin'):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        rows = db.execute(text("""
            SELECT b.user_id, COALESCE(u.display_name, u.username) AS display_name,
                   u.username, b.reason, b.created_at
            FROM qc_guild_bans b
            JOIN web_users u ON u.id = b.user_id
            WHERE b.server_id = :sid
            ORDER BY b.created_at DESC
        """), {'sid': server_id}).fetchall()
        return JsonResponse({'bans': [
            {'user_id': r.user_id, 'display_name': r.display_name,
             'username': r.username, 'reason': r.reason}
            for r in rows
        ]})


# ---------------------------------------------------------------------------
# Welcome message: GET/POST /ql/qc/servers/<id>/welcome/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['GET', 'POST'])
def qc_guild_welcome(request, server_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)

        if request.method == 'GET':
            row = db.execute(text(
                "SELECT welcome_message FROM qc_servers WHERE id = :sid"
            ), {'sid': server_id}).fetchone()
            return JsonResponse({'welcome_message': row.welcome_message or '' if row else ''})

        # POST - only owner/admin
        role_row = db.execute(text(
            "SELECT role FROM qc_server_members WHERE server_id = :sid AND user_id = :uid"
        ), {'sid': server_id, 'uid': user_id}).fetchone()
        if not role_row or role_row.role not in ('owner', 'admin'):
            return JsonResponse({'error': 'Forbidden'}, status=403)
        try:
            data = json.loads(request.body)
        except ValueError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        msg = (data.get('welcome_message') or '')[:500]
        db.execute(text(
            "UPDATE qc_servers SET welcome_message = :msg WHERE id = :sid"
        ), {'msg': msg or None, 'sid': server_id})
        db.commit()
        return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Unread: mark channel as read
# POST /ql/qc/channels/<guild_id>/<channel_id>/read/
# GET  /ql/qc/unread/   - returns unread counts per channel
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_mark_read(request, guild_id, channel_id):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        now = int(time.time())
        db.execute(text("""
            INSERT INTO qc_channel_reads (user_id, guild_id, channel_id, last_read)
            VALUES (:uid, :gid, :cid, :now)
            ON DUPLICATE KEY UPDATE last_read = :now
        """), {'uid': user_id, 'gid': guild_id, 'cid': channel_id, 'now': now})
        db.commit()
        return JsonResponse({'ok': True})


@require_http_methods(['GET'])
def qc_unread(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not _check_user(user):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        rows = db.execute(text("""
            SELECT m.guild_id, m.channel_id, COUNT(*) as unread
            FROM qc_messages m
            LEFT JOIN qc_channel_reads r
                ON r.user_id = :uid AND r.guild_id = m.guild_id AND r.channel_id = m.channel_id
            JOIN qc_server_members sm ON sm.server_id = m.guild_id AND sm.user_id = :uid
            WHERE m.deleted_at IS NULL
              AND m.user_id != :uid
              AND (r.last_read IS NULL OR m.created_at > r.last_read)
            GROUP BY m.guild_id, m.channel_id
        """), {'uid': user_id}).fetchall()
        return JsonResponse({'unread': {
            f"{r.guild_id}:{r.channel_id}": r.unread for r in rows
        }})


# ---------------------------------------------------------------------------
# XP for chatting - unified with QuestLog award_xp()
# Called internally after message save, not a public endpoint
# Cooldown: 1 XP award per 60 seconds per user (enforced via qc_chat_xp_at on web_users)
# ---------------------------------------------------------------------------
_QC_CHAT_XP_COOLDOWN = 60  # seconds

def _award_chat_xp(user_id: int):
    """Award chat XP using the unified QuestLog XP system. Cooldown: 60s."""
    try:
        from app.questlog_web.helpers import award_xp
        now = int(time.time())
        with get_db_session() as db:
            row = db.execute(text(
                "SELECT qc_chat_xp_at FROM web_users WHERE id = :uid"
            ), {'uid': user_id}).fetchone()
            last = row.qc_chat_xp_at if row and row.qc_chat_xp_at else 0
            if now - last < _QC_CHAT_XP_COOLDOWN:
                return
            db.execute(text(
                "UPDATE web_users SET qc_chat_xp_at = :now WHERE id = :uid"
            ), {'now': now, 'uid': user_id})
            db.commit()
        award_xp(user_id, 'qc_chat')
    except Exception as e:
        logger.warning('_award_chat_xp failed user=%s: %s', user_id, e)


# ---------------------------------------------------------------------------
# Internal XP endpoint - called by the Go gateway after message save
# POST /ql/qc/internal/xp/
# Secured by QC_INTERNAL_SECRET header, not a user JWT
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_internal_award_xp(request):
    import os
    from app.questlog_web.helpers import safe_int
    # Defense-in-depth: only accept from loopback even before secret check
    remote = request.META.get('REMOTE_ADDR', '')
    if remote not in ('127.0.0.1', '::1'):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    secret = os.environ.get('QC_INTERNAL_SECRET', '')
    if not secret or request.headers.get('X-Internal-Secret') != secret:
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    user_id = safe_int(data.get('user_id'), 0, min_val=1)
    if not user_id:
        return JsonResponse({'error': 'user_id required'}, status=400)
    _award_chat_xp(user_id)
    return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Admin: Platform bad actor registry
# POST /ql/qc/admin/bad-actors/add/
# POST /ql/qc/admin/bad-actors/import-csv/
# GET  /ql/qc/admin/bad-actors/
# ---------------------------------------------------------------------------
@csrf_exempt
@require_http_methods(['POST'])
def qc_admin_bad_actor_add(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        admin = db.query(WebUser).filter_by(id=user_id).first()
        if not admin or not admin.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        try:
            data = json.loads(request.body)
        except ValueError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        username = (data.get('username') or '').strip()
        if not username:
            return JsonResponse({'error': 'username required'}, status=400)

        valid_reasons = ('spam', 'csam', 'harassment', 'hate_speech', 'threats', 'policy_violation', 'other')
        reason = data.get('reason', 'other')
        if reason not in valid_reasons:
            return JsonResponse({'error': 'Invalid reason'}, status=400)

        valid_severities = ('flag', 'ban', 'ip_ban')
        severity = data.get('severity', 'ban')
        if severity not in valid_severities:
            return JsonResponse({'error': 'Invalid severity'}, status=400)

        notes = (data.get('notes') or '')[:2000]

        # Resolve user_id if account exists
        target = db.query(WebUser).filter_by(username=username).first()
        target_id = target.id if target else None
        # Hash IP if provided
        raw_ip = (data.get('ip') or '').strip()
        ip_hash = hashlib.sha256(raw_ip.encode()).hexdigest() if raw_ip else None

        now = int(time.time())
        db.execute(text("""
            INSERT INTO qc_bad_actors (user_id, username, email, ip_hash, reason, severity, notes, added_by, created_at)
            VALUES (:uid, :uname, :email, :ip_hash, :reason, :severity, :notes, :added_by, :now)
        """), {
            'uid': target_id, 'uname': username, 'email': data.get('email'),
            'ip_hash': ip_hash, 'reason': reason, 'severity': severity,
            'notes': notes, 'added_by': user_id, 'now': now,
        })

        # If ban/ip_ban: set DM rep to -50, lock DMs
        if severity in ('ban', 'ip_ban') and target_id:
            existing_rep = db.execute(text(
                "SELECT user_id FROM qc_dm_reputation WHERE user_id = :uid"
            ), {'uid': target_id}).fetchone()
            if existing_rep:
                db.execute(text("""
                    UPDATE qc_dm_reputation SET score = -50, locked = 1,
                    locked_reason = 'Platform ban', updated_at = :now WHERE user_id = :uid
                """), {'now': now, 'uid': target_id})
            else:
                db.execute(text("""
                    INSERT INTO qc_dm_reputation (user_id, score, reports_count, locked, locked_reason, updated_at)
                    VALUES (:uid, -50, 0, 1, 'Platform ban', :now)
                """), {'uid': target_id, 'now': now})

            # Ban the account itself
            if target:
                db.execute(text(
                    "UPDATE web_users SET is_banned = 1 WHERE id = :uid"
                ), {'uid': target_id})

        db.commit()
        logger.warning('qc_bad_actor added username=%s severity=%s by_admin=%s', username, severity, user_id)
        return JsonResponse({'ok': True, 'message': f'{username} added to bad actor registry with severity={severity}.'})


@csrf_exempt
@require_http_methods(['POST'])
def qc_admin_bad_actor_import_csv(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        admin = db.query(WebUser).filter_by(id=user_id).first()
        if not admin or not admin.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        try:
            data = json.loads(request.body)
        except ValueError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        csv_text = data.get('csv', '')
        if not csv_text:
            return JsonResponse({'error': 'csv field required'}, status=400)

        reader = csv.DictReader(io.StringIO(csv_text))
        now = int(time.time())
        added = 0
        skipped = 0
        errors = []

        for i, row in enumerate(reader):
            username = (row.get('username') or '').strip()
            if not username:
                errors.append(f'Row {i+2}: missing username')
                continue

            reason = (row.get('reason') or 'other').strip()
            severity = (row.get('severity') or 'ban').strip()
            notes = (row.get('notes') or '')[:2000]

            valid_reasons = ('spam', 'csam', 'harassment', 'hate_speech', 'threats', 'policy_violation', 'other')
            valid_severities = ('flag', 'ban', 'ip_ban')
            if reason not in valid_reasons:
                reason = 'other'
            if severity not in valid_severities:
                severity = 'ban'

            target = db.query(WebUser).filter_by(username=username).first()
            target_id = target.id if target else None

            try:
                db.execute(text("""
                    INSERT IGNORE INTO qc_bad_actors (user_id, username, reason, severity, notes, added_by, created_at)
                    VALUES (:uid, :uname, :reason, :severity, :notes, :added_by, :now)
                """), {'uid': target_id, 'uname': username, 'reason': reason,
                       'severity': severity, 'notes': notes, 'added_by': user_id, 'now': now})

                if severity in ('ban', 'ip_ban') and target_id:
                    db.execute(text("""
                        INSERT INTO qc_dm_reputation (user_id, score, reports_count, locked, locked_reason, updated_at)
                        VALUES (:uid, -50, 0, 1, 'Platform ban (CSV import)', :now)
                        ON DUPLICATE KEY UPDATE score = -50, locked = 1,
                        locked_reason = 'Platform ban (CSV import)', updated_at = :now
                    """), {'uid': target_id, 'now': now})
                    if target:
                        db.execute(text("UPDATE web_users SET is_banned = 1 WHERE id = :uid"), {'uid': target_id})

                added += 1
            except Exception as e:
                errors.append(f'Row {i+2} ({username}): {str(e)[:100]}')
                skipped += 1

        db.commit()
        logger.warning('qc_bad_actor csv_import added=%s skipped=%s by_admin=%s', added, skipped, user_id)
        return JsonResponse({'ok': True, 'added': added, 'skipped': skipped, 'errors': errors})


@require_http_methods(['GET'])
def qc_admin_bad_actors(request):
    user_id = _verify_token(request)
    if not user_id:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    with get_db_session() as db:
        admin = db.query(WebUser).filter_by(id=user_id).first()
        if not admin or not admin.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        rows = db.execute(text("""
            SELECT ba.id, ba.user_id, ba.username, ba.reason, ba.severity,
                   ba.notes, ba.created_at,
                   COALESCE(adm.display_name, adm.username) AS added_by_name
            FROM qc_bad_actors ba
            JOIN web_users adm ON adm.id = ba.added_by
            ORDER BY ba.created_at DESC
            LIMIT 500
        """)).fetchall()

        return JsonResponse({'bad_actors': [{
            'id': r.id, 'user_id': r.user_id, 'username': r.username,
            'reason': r.reason, 'severity': r.severity, 'notes': r.notes,
            'created_at': r.created_at, 'added_by': r.added_by_name,
        } for r in rows]})
