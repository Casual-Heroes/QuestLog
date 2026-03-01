# QuestLog Web — shared utilities (all other view modules import from here)

import os
import re
import uuid
import time
import json
import logging
import hashlib
import secrets
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse, quote

from django.shortcuts import redirect
from django.urls import reverse
from django.http import JsonResponse
from django.contrib import messages
from django.conf import settings as django_settings
from sqlalchemy import or_, and_

from .models import (
    WebUser, WebUserBlock, WebNotification, WebLike, WebPost,
    AdminAuditLog, WebHeroPointEvent, WebRSSFeed, WebRSSArticle,
    WebXpEvent, WebFlair, WebUserFlair, WebRankTitle,
)
from app.db import get_db_session

logger = logging.getLogger(__name__)

STEAM_API_KEY = os.getenv('STEAM_API_KEY', '')

# IP addresses in audit logs are SHA-256 hashed with this salt (never stored raw)
AUDIT_LOG_SALT = os.getenv('AUDIT_LOG_SALT', '')
if not AUDIT_LOG_SALT:
    if not django_settings.DEBUG:
        from django.core.exceptions import ImproperlyConfigured
        raise ImproperlyConfigured(
            "AUDIT_LOG_SALT must be set in production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\" "
            "and add it to /etc/casual-heroes/secrets.env"
        )
    # Dev/test only: use a transient salt (IP hashes reset on restart, acceptable for local dev)
    logger.warning("AUDIT_LOG_SALT not set - using transient salt (dev mode). Set it in production.")
    AUDIT_LOG_SALT = secrets.token_hex(32)


def safe_int(value, default=1, min_val=None, max_val=None):
    """Parse an integer from a request param safely, returning default on ValueError."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if min_val is not None:
        result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)
    return result


def safe_redirect_url(next_url, default='/ql/'):
    """
    Validate a ?next= redirect parameter to prevent open redirect attacks.
    Only allows relative paths on the same host — rejects:
      - Absolute URLs (http://, https://)
      - Protocol-relative URLs (//)
      - Backslash bypasses (/\attacker.com)
      - Null-byte injections
    """
    if not next_url or not isinstance(next_url, str):
        return default
    from urllib.parse import urlparse
    try:
        parsed = urlparse(next_url)
        # Reject anything with a scheme or netloc (absolute/protocol-relative URLs)
        if parsed.scheme or parsed.netloc:
            return default
        # Must start with a single /
        if not next_url.startswith('/') or next_url.startswith('//'):
            return default
        # Reject backslash (browser-specific bypass: /\attacker.com)
        if '\\' in next_url:
            return default
        # Reject null bytes
        if '\x00' in next_url:
            return default
        return next_url
    except Exception as e:
        logger.debug("safe_redirect_url: rejected url %r: %s", next_url, e)
        return default


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _hash_ip(ip_address):
    # Store a 16-char truncated hash — enough to correlate entries without storing the raw IP
    return hashlib.sha256(
        (ip_address + AUDIT_LOG_SALT).encode('utf-8')
    ).hexdigest()[:16]


def _truncate_user_agent(ua_string):
    # We only want "Chrome 121", not the full 200-char UA string
    if not ua_string:
        return 'Unknown'
    ua = ua_string.lower()
    for browser, pattern in [
        ('Edge', r'edg[e/](\d+)'),
        ('Chrome', r'chrome/(\d+)'),
        ('Firefox', r'firefox/(\d+)'),
        ('Safari', r'version/(\d+).*safari'),
        ('Opera', r'opr/(\d+)'),
    ]:
        match = re.search(pattern, ua)
        if match:
            return f'{browser} {match.group(1)}'
    return 'Other'


def log_admin_action(request, action, target_type=None, target_id=None, details=None):
    """Write one row to the admin audit log. IPs are hashed, UA truncated."""
    web_user = getattr(request, 'web_user', None)
    if not web_user:
        return
    with get_db_session() as db:
        log_entry = AdminAuditLog(
            admin_user_id=web_user.id,
            admin_username=web_user.username,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=json.dumps(details) if details else None,
            ip_address=_hash_ip(get_client_ip(request)),
            user_agent=_truncate_user_agent(request.META.get('HTTP_USER_AGENT', '')),
            created_at=int(time.time()),
        )
        db.add(log_entry)
        db.commit()


# =============================================================================
# DECORATORS
# =============================================================================

def get_web_user(request):
    user_id = request.session.get('web_user_id')
    if not user_id:
        return None

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user:
            return None
        # OWASP A01: immediately invalidate sessions for banned/disabled accounts
        if user.is_banned or user.is_disabled:
            request.session.flush()
            return None
        db.expunge(user)  # Must expunge before the context manager closes
        return user


def web_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        web_user = get_web_user(request)
        if not web_user:
            messages.warning(request, "Please log in to access this page.")
            login_url = reverse('questlog_web_login')
            return redirect(f'{login_url}?next={quote(request.get_full_path())}')
        request.web_user = web_user
        return view_func(request, *args, **kwargs)
    return wrapper


def web_admin_required(view_func):
    """Requires Django superuser + active WebUser. Logs all denied attempts."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        web_user = get_web_user(request)

        if not web_user:
            if request.headers.get('Accept', '').find('application/json') >= 0:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            messages.error(request, "Please log in first.")
            return redirect('questlog_web_login')

        if not request.user.is_authenticated or not request.user.is_superuser:
            logger.warning(
                f"ADMIN ACCESS DENIED: User {web_user.username} (id={web_user.id}) "
                f"- not a superuser. IP: {get_client_ip(request)}"
            )
            if request.headers.get('Accept', '').find('application/json') >= 0:
                return JsonResponse({'error': 'Access denied'}, status=403)
            messages.error(request, "Access denied.")
            return redirect('questlog_web_home')

        if web_user.is_banned:
            logger.warning(
                f"BANNED ADMIN ATTEMPT: User {web_user.username} (id={web_user.id}) "
                f"is banned but is a superuser. IP: {get_client_ip(request)}"
            )
            if request.headers.get('Accept', '').find('application/json') >= 0:
                return JsonResponse({'error': 'Account suspended'}, status=403)
            messages.error(request, "Your account has been suspended.")
            return redirect('questlog_web_home')

        request.web_user = web_user
        return view_func(request, *args, **kwargs)
    return wrapper


def add_web_user_context(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        request.web_user = get_web_user(request)
        # Award daily visit HP once per calendar day (tracked via session to avoid per-request DB hits)
        if request.web_user:
            today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            session_key = f'hp_visit_{today_str}'
            if not request.session.get(session_key):
                award_hero_points(request.web_user.id, 'daily_visit')
                request.session[session_key] = True
        return view_func(request, *args, **kwargs)
    return wrapper


# =============================================================================
# XP + HERO POINTS
# =============================================================================

# XP per action and max events allowed per UTC day (None = uncapped)
XP_ACTIONS = {
    'daily_visit':       {'xp': 2,  'daily_max': 1},
    'like':              {'xp': 1,  'daily_max': 5},
    'follow':            {'xp': 3,  'daily_max': 5},
    'share':             {'xp': 3,  'daily_max': 3},
    'post':              {'xp': 5,  'daily_max': 5},
    'steam_achievement': {'xp': 5,  'daily_max': None},
    'steam_hours':       {'xp': 1,  'daily_max': None},
    'invite':            {'xp': 50, 'daily_max': None},
}

# HP conversion: every XP_TO_HP_THRESHOLD XP earns HP_PER_THRESHOLD HP
XP_TO_HP_THRESHOLD = 50
HP_PER_THRESHOLD = 10
HP_PER_LEVEL = 5  # HP bonus per level gained on level-up


def _get_rank_title(level, db):
    """Return the rank title string for a given level (highest milestone reached)."""
    title_row = (
        db.query(WebRankTitle)
        .filter(WebRankTitle.level <= level)
        .order_by(WebRankTitle.level.desc())
        .first()
    )
    return title_row.title if title_row else 'Hollow Wanderer'


def _get_level_for_xp(xp, db):
    """
    Return the level corresponding to total XP, based on web_rank_titles milestones.
    Falls back to level_requirements table if available.
    """
    from sqlalchemy import text
    try:
        rows = db.execute(
            text("SELECT level, xp_required FROM level_requirements ORDER BY level")
        ).fetchall()
        if rows:
            current_level = 1
            for row in rows:
                if xp >= row[1]:
                    current_level = row[0]
                else:
                    break
            return current_level
    except Exception as e:
        logger.warning("_get_level_for_xp: DB lookup failed, using formula fallback: %s", e)
    # Fallback: simple formula matching Discord bot default (7 * level^1.5)
    level = 1
    while True:
        xp_needed = int(7 * ((level + 1) ** 1.5))
        if xp < xp_needed:
            break
        level += 1
        if level >= 99:
            break
    return level


def award_xp(user_id, action_type, source='web', ref_id=None):
    """
    Award XP to a user for the given action.
    - Respects daily caps
    - Converts XP → HP at every 50 XP threshold crossed
    - Awards HP bonus on level-up (5 HP per level gained)
    Returns XP awarded (0 if capped or unknown action).
    """
    config = XP_ACTIONS.get(action_type)
    if not config:
        logger.warning(f"award_xp: unknown action_type '{action_type}'")
        return 0

    xp_amount = config['xp']
    daily_max = config['daily_max']
    now = int(time.time())
    today_midnight = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    try:
        with get_db_session() as db:
            # Enforce daily cap
            if daily_max is not None:
                count_today = db.query(WebXpEvent).filter(
                    WebXpEvent.user_id == user_id,
                    WebXpEvent.action_type == action_type,
                    WebXpEvent.created_at >= today_midnight,
                ).count()
                if count_today >= daily_max:
                    return 0

            # Log XP event
            db.add(WebXpEvent(
                user_id=user_id,
                action_type=action_type,
                xp=xp_amount,
                source=source,
                ref_id=str(ref_id) if ref_id is not None else None,
                created_at=now,
            ))

            user = db.query(WebUser).filter_by(id=user_id).first()
            if not user:
                db.commit()
                return xp_amount

            old_xp = user.web_xp or 0
            new_xp = old_xp + xp_amount
            user.web_xp = new_xp

            # XP → HP conversion (every 50 XP threshold crossed)
            old_thresholds = old_xp // XP_TO_HP_THRESHOLD
            new_thresholds = new_xp // XP_TO_HP_THRESHOLD
            thresholds_crossed = new_thresholds - old_thresholds
            if thresholds_crossed > 0:
                hp_from_xp = thresholds_crossed * HP_PER_THRESHOLD
                user.hero_points = (user.hero_points or 0) + hp_from_xp
                db.add(WebHeroPointEvent(
                    user_id=user_id,
                    action_type='xp_conversion',
                    points=hp_from_xp,
                    source=source,
                    ref_id=f'xp_{new_xp}',
                    created_at=now,
                ))

            # Level-up check
            old_level = user.web_level or 1
            new_level = _get_level_for_xp(new_xp, db)
            if new_level > old_level:
                user.web_level = new_level
                levels_gained = new_level - old_level
                hp_from_levelup = levels_gained * HP_PER_LEVEL
                user.hero_points = (user.hero_points or 0) + hp_from_levelup
                db.add(WebHeroPointEvent(
                    user_id=user_id,
                    action_type='level_up',
                    points=hp_from_levelup,
                    source=source,
                    ref_id=f'level_{new_level}',
                    created_at=now,
                ))

            db.commit()
            return xp_amount
    except Exception as e:
        logger.error(f"award_xp failed for user {user_id} action {action_type}: {e}")
        return 0


def award_hero_points(user_id, action_type, source='web', ref_id=None):
    """
    Legacy alias: delegates to award_xp().
    Kept so existing call sites don't break during transition.
    """
    return award_xp(user_id, action_type, source=source, ref_id=ref_id)


# =============================================================================
# SOCIAL LAYER HELPERS
# =============================================================================

# Video embed domain whitelist and regex patterns
EMBED_PATTERNS = {
    'youtube': [
        re.compile(r'(?:youtube\.com/(?:watch\?v=|embed/|live/|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})'),
    ],
    'twitch': [
        re.compile(r'twitch\.tv/videos/(\d+)'),
        re.compile(r'clips\.twitch\.tv/([a-zA-Z0-9_-]+)'),
        re.compile(r'twitch\.tv/[^/]+/clip/([a-zA-Z0-9_-]+)'),
    ],
    'tiktok': [
        re.compile(r'tiktok\.com/@[^/]+/video/(\d+)'),
    ],
    'instagram': [
        re.compile(r'instagram\.com/(?:p|reel)/([a-zA-Z0-9_-]+)'),
    ],
    'kick': [
        re.compile(r'kick\.com/[^/]+\?clip=([a-zA-Z0-9_-]+)'),
        re.compile(r'kick\.com/[^/]+/clips/([a-zA-Z0-9_-]+)'),
    ],
    'twitter': [
        re.compile(r'(?:twitter\.com|x\.com)/[^/]+/status/(\d+)'),
    ],
}


def parse_embed_url(url):
    """Parse a video embed URL. Returns (platform, video_id) or (None, None)."""
    if not url or not isinstance(url, str):
        return None, None
    url = url.strip()
    for platform, patterns in EMBED_PATTERNS.items():
        for pattern in patterns:
            match = pattern.search(url)
            if match:
                return platform, match.group(1)
    return None, None


def reconstruct_embed_url(platform, vid_id):
    """Return a canonical, safe URL from a validated platform + video ID.

    Always call this instead of storing the raw user-supplied URL, so we never
    persist a javascript: URI or other dangerous scheme in media_url.
    """
    if not platform or not vid_id:
        return None
    builders = {
        'youtube':   lambda v: f'https://www.youtube.com/watch?v={v}',
        'twitch':    lambda v: f'https://www.twitch.tv/videos/{v}' if v.isdigit() else f'https://clips.twitch.tv/{v}',
        'tiktok':    lambda v: f'https://www.tiktok.com/@/video/{v}',
        'instagram': lambda v: f'https://www.instagram.com/p/{v}/',
        'kick':      lambda v: f'https://kick.com/clip/{v}',
        'twitter':   lambda v: f'https://x.com/i/status/{v}',
    }
    builder = builders.get(platform)
    return builder(vid_id) if builder else None


_GIPHY_CDN_HOSTS = frozenset({
    'media.giphy.com',
    'media0.giphy.com',
    'media1.giphy.com',
    'media2.giphy.com',
    'media3.giphy.com',
    'media4.giphy.com',
    'i.giphy.com',
})


def validate_admin_image_url(url):
    """
    Validate an image URL submitted by an admin (giveaways, polls, raffles).
    Requires HTTPS and blocks private/loopback IPs to prevent SSRF.
    Returns the sanitized URL on success, or None if invalid.
    """
    if not url or not isinstance(url, str):
        return None
    url = url.strip()[:500]
    if not url:
        return None
    try:
        import ipaddress, socket as _socket
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            return None
        hostname = parsed.hostname
        if not hostname or not parsed.netloc:
            return None
        # Block internal/loopback/private addresses
        try:
            for _, _, _, _, sockaddr in _socket.getaddrinfo(hostname, None):
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return None
        except Exception:
            pass  # DNS failure or unresolvable - allow through (not a local address)
        return url
    except Exception:
        return None


def _is_valid_giphy_url(url):
    """Reject anything that didn't actually come from GIPHY's CDN."""
    if not url or not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme == 'https' and parsed.netloc in _GIPHY_CDN_HOSTS
    except Exception as e:
        logger.debug("_is_valid_giphy_url: url parse error for %r: %s", url, e)
        return False


def sanitize_text(text_input, max_length=2000):
    """Sanitize user text input: strip HTML, normalize whitespace, limit length."""
    if not text_input:
        return ''
    clean = re.sub(r'<[^>]+>', '', str(text_input))
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    clean = clean[:max_length].strip()
    return clean


def is_blocked(db, user_id_a, user_id_b):
    """Check if either user has blocked the other."""
    if not user_id_a or not user_id_b:
        return False
    block = db.query(WebUserBlock).filter(
        or_(
            and_(WebUserBlock.blocker_id == user_id_a, WebUserBlock.blocked_id == user_id_b),
            and_(WebUserBlock.blocker_id == user_id_b, WebUserBlock.blocked_id == user_id_a),
        )
    ).first()
    return block is not None


def check_banned(request):
    """Return JsonResponse if user is banned or disabled, else None."""
    if request.web_user.is_banned:
        return JsonResponse({'error': 'Your account has been suspended'}, status=403)
    if request.web_user.is_disabled:
        return JsonResponse({'error': 'Your account has been disabled'}, status=403)
    return None


def check_posting_timeout(request):
    """Return JsonResponse if user is on a posting timeout, else None."""
    timeout_until = request.web_user.posting_timeout_until
    if timeout_until and int(time.time()) < timeout_until:
        from datetime import datetime
        until_str = datetime.utcfromtimestamp(timeout_until).strftime('%Y-%m-%d %H:%M UTC')
        return JsonResponse({'error': f'You are on a posting timeout until {until_str}'}, status=403)
    return None


# Maps notification_type -> WebUser preference column name.
# Types NOT listed here (e.g. giveaway_win) are always delivered.
_NOTIF_PREF_FIELD = {
    'follow':        'notify_follows',
    'like':          'notify_likes',
    'comment':       'notify_comments',
    'comment_like':  'notify_comment_likes',
    'giveaway':      'notify_giveaways',
    'lfg_join':      'notify_lfg_join',
    'lfg_leave':     'notify_lfg_leave',
    'lfg_full':      'notify_lfg_full',
    'community_join': 'notify_community_join',
}


def create_notification(db, user_id, actor_id, notification_type,
                        target_type=None, target_id=None, message=None,
                        skip_self=True):
    """Create a notification. Skips if actor == recipient (unless skip_self=False),
    if blocked, or if the recipient has muted this notification type."""
    if skip_self and user_id == actor_id:
        return
    if is_blocked(db, user_id, actor_id):
        return
    # Check recipient's notification preference
    pref_field = _NOTIF_PREF_FIELD.get(notification_type)
    if pref_field:
        from app.questlog_web.models import WebUser as _WU
        recipient = db.query(_WU).filter_by(id=user_id).first()
        if recipient and not getattr(recipient, pref_field, True):
            return
    notif = WebNotification(
        user_id=user_id,
        actor_id=actor_id,
        notification_type=notification_type,
        target_type=target_type,
        target_id=target_id,
        message=message[:500] if message else None,
        is_read=False,
        created_at=int(time.time()),
    )
    db.add(notif)


def process_uploaded_image(uploaded_file, dest_subdir='posts',
                           max_size_bytes=40 * 1024 * 1024,
                           max_gif_size=15 * 1024 * 1024,
                           max_dimension=4096):
    """
    Validate, strip EXIF, convert to WebP, generate a 400px thumbnail, and save.
    Animated GIFs are kept as-is. Returns {image_url, thumbnail_url, width, height, file_size}.
    Raises ValueError on validation failure.

    Security layers:
      1. Content-type allowlist (JPEG/PNG/GIF/WebP only)
      2. File size cap before decoding
      3. Pillow .verify() — rejects malformed/polyglot files
      4. Max pixel dimension — prevents decompression bomb attacks
      5. EXIF stripping — fresh Image object, never copies metadata
    """
    from PIL import Image

    # 1. Content-type allowlist
    ALLOWED_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}
    content_type = uploaded_file.content_type
    if content_type not in ALLOWED_TYPES:
        raise ValueError('Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed.')

    # 2. File size cap (checked before any decoding)
    file_size = uploaded_file.size
    is_gif = content_type == 'image/gif'
    size_limit = max_gif_size if is_gif else max_size_bytes
    if file_size > size_limit:
        limit_mb = size_limit / (1024 * 1024)
        raise ValueError(f'File too large. Maximum size is {limit_mb:.0f}MB.')

    # 3. Pillow verify — confirms this is a real image, catches polyglot/malformed files
    try:
        img = Image.open(uploaded_file)
        img.verify()
        uploaded_file.seek(0)
        img = Image.open(uploaded_file)
    except Exception:
        raise ValueError('Invalid image file.')

    # 4. Dimension cap — prevents decompression bomb attacks (e.g. 1px PNG expanding to 4GB)
    width, height = img.size
    if width > max_dimension or height > max_dimension:
        raise ValueError(f'Image too large. Maximum dimensions are {max_dimension}x{max_dimension} pixels.')

    now = datetime.now(timezone.utc)
    file_uuid = uuid.uuid4().hex
    year_month = now.strftime('%Y/%m')
    base_dir = os.path.join(django_settings.MEDIA_ROOT, 'uploads', dest_subdir, year_month)
    os.makedirs(base_dir, exist_ok=True)

    if is_gif and getattr(img, 'is_animated', False):
        ext = '.gif'
        save_path = os.path.join(base_dir, f'{file_uuid}{ext}')
        uploaded_file.seek(0)
        with open(save_path, 'wb') as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)
        saved_size = os.path.getsize(save_path)
    else:
        ext = '.webp'
        save_path = os.path.join(base_dir, f'{file_uuid}{ext}')
        # Strip EXIF by creating clean image
        if img.mode in ('RGBA', 'LA', 'P'):
            clean_img = img.copy()
        else:
            clean_img = img.convert('RGB')
        clean_img.save(save_path, 'WEBP', quality=85, method=4)
        saved_size = os.path.getsize(save_path)

    thumb_path = os.path.join(base_dir, f'{file_uuid}_thumb.webp')
    thumb_img = img.copy()
    thumb_width = 400
    if width > thumb_width:
        thumb_height = int(height * (thumb_width / width))
        thumb_img.thumbnail((thumb_width, thumb_height), Image.LANCZOS)
    if thumb_img.mode not in ('RGB', 'RGBA'):
        thumb_img = thumb_img.convert('RGB')
    thumb_img.save(thumb_path, 'WEBP', quality=80)

    rel_path = f'uploads/{dest_subdir}/{year_month}/{file_uuid}'
    image_url = f'{django_settings.MEDIA_URL}{rel_path}{ext}'
    thumbnail_url = f'{django_settings.MEDIA_URL}{rel_path}_thumb.webp'

    return {
        'image_url': image_url,
        'thumbnail_url': thumbnail_url,
        'width': width,
        'height': height,
        'file_size': saved_size,
    }


# Simple TTL caches (refresh every 5 minutes) to avoid per-post DB round-trips.
# IMPORTANT: These caches use direct engine connections (NOT get_db_session / scoped_session)
# to avoid closing the thread-local scoped session while other code is still using it.
_rank_title_cache = {'ts': 0, 'data': []}   # [(level, title), ...] sorted desc
_flair_cache      = {'ts': 0, 'data': {}}   # {flair_id: (emoji, name)}
_CACHE_TTL = 300  # seconds


def _get_rank_title_cache():
    now = time.time()
    if now - _rank_title_cache['ts'] > _CACHE_TTL:
        try:
            from app.db import get_engine
            from sqlalchemy import text as sa_text
            with get_engine().connect() as conn:
                rows = conn.execute(
                    sa_text("SELECT level, title FROM web_rank_titles ORDER BY level DESC")
                ).fetchall()
                _rank_title_cache['data'] = [(r[0], r[1]) for r in rows]
                _rank_title_cache['ts'] = now
        except Exception as e:
            logger.warning("_get_rank_title_cache: DB refresh failed, using stale cache: %s", e)
    return _rank_title_cache['data']


def _get_flair_from_cache(flair_id):
    now = time.time()
    if now - _flair_cache['ts'] > _CACHE_TTL:
        try:
            from app.db import get_engine
            from sqlalchemy import text as sa_text
            with get_engine().connect() as conn:
                rows = conn.execute(
                    sa_text("SELECT id, emoji, name FROM web_flairs WHERE enabled = 1")
                ).fetchall()
                _flair_cache['data'] = {r[0]: (r[1] or '', r[2] or '') for r in rows}
                _flair_cache['ts'] = now
        except Exception as e:
            logger.warning("_get_flair_from_cache: DB refresh failed, using stale cache: %s", e)
    return _flair_cache['data'].get(flair_id, ('', ''))


def get_user_flair_and_title(user):
    """
    Return (flair_emoji, flair_name, rank_title) for a user.
    Uses TTL-cached lookups to avoid per-post DB round-trips.
    """
    # Rank title
    rank_title = 'Hollow Wanderer'
    level = user.web_level or 1
    for milestone_level, title in _get_rank_title_cache():
        if level >= milestone_level:
            rank_title = title
            break

    # Active flair
    flair_emoji, flair_name = '', ''
    if user.active_flair_id:
        flair_emoji, flair_name = _get_flair_from_cache(user.active_flair_id)

    return flair_emoji, flair_name, rank_title


def serialize_user_brief(user):
    """Serialize a WebUser to a brief dict for public API responses.
    Does NOT include steam_id or other sensitive identifiers."""
    flair_emoji, flair_name, rank_title = get_user_flair_and_title(user)
    return {
        'id': user.id,
        'username': user.username,
        'display_name': user.display_name or user.username,
        'avatar_url': user.avatar_url or user.steam_avatar,
        'is_banned': user.is_banned,
        'is_vip': bool(user.is_vip),
        'web_level': user.web_level or 1,
        'rank_title': rank_title,
        'flair_emoji': flair_emoji,
        'flair_name': flair_name,
        'current_game': user.current_game if getattr(user, 'show_playing_status', False) else None,
    }


def serialize_user_admin(user):
    """Serialize a WebUser with admin-level detail. Only use in admin views."""
    data = serialize_user_brief(user)
    data.update({
        'steam_id': user.steam_id,
        'discord_id': user.discord_id,
        'email': user.email,
        'is_admin': user.is_admin,
        'created_at': user.created_at,
        'last_login_at': user.last_login_at,
    })
    return data


def _strip_html(text):
    """Strip HTML tags and unescape entities, returning plain text."""
    import html as _html
    from html.parser import HTMLParser

    class _Stripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self._parts = []
        def handle_data(self, d):
            self._parts.append(d)
        def get_text(self):
            return ' '.join(self._parts)

    s = _Stripper()
    try:
        s.feed(text)
        result = _html.unescape(s.get_text())
    except Exception as e:
        logger.debug("_strip_html: HTML parser error, returning raw text: %s", e)
        result = text
    # Collapse whitespace
    return ' '.join(result.split())


def fetch_rss_feed(feed, db):
    """
    Fetch and store new articles for a WebRSSFeed.
    Uses the SSRF-protected secure_fetch_rss() from app.rss_utils.

    Returns:
        (new_count: int, error: str|None)
    """
    import calendar
    from app.rss_utils import secure_fetch_rss

    parsed, error = secure_fetch_rss(feed.url)
    now = int(time.time())

    if error:
        feed.last_error = error
        feed.last_fetched_at = now
        db.commit()
        return 0, error

    MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds
    cutoff = now - MAX_AGE

    new_count = 0
    for entry in parsed.entries:
        # --- guid ---
        guid = (entry.get('id') or entry.get('link') or entry.get('title', ''))[:500]
        if not guid:
            continue

        # --- published_at (resolve early so we can age-filter before DB lookup) ---
        published_at = None
        ts = entry.get('published_parsed') or entry.get('updated_parsed')
        if ts:
            try:
                published_at = int(calendar.timegm(ts))
            except Exception:
                pass

        # Skip articles older than 7 days (if publish date is known)
        if published_at and published_at < cutoff:
            continue

        # Skip if already stored
        exists = db.query(WebRSSArticle).filter_by(feed_id=feed.id, guid=guid).first()
        if exists:
            continue

        # --- title / url ---
        title = (entry.get('title') or 'Untitled')[:500]
        url = (entry.get('link') or feed.url)[:500]

        # --- summary: strip HTML, discard if it's just the title ---
        summary = None
        raw_summary = None
        if entry.get('summary'):
            raw_summary = entry.summary
        elif entry.get('content'):
            raw_summary = entry.content[0].get('value', '')
        if raw_summary:
            clean = _strip_html(raw_summary)
            # Discard if empty or if it's just the title text (Google News pattern)
            if clean and clean.lower() != title.lower() and not clean.lower().startswith(title.lower()[:40]):
                summary = clean[:2000]

        # --- author ---
        author = (entry.get('author') or '')[:200] or None

        # --- image ---
        image_url = None
        media = entry.get('media_content') or entry.get('media_thumbnail')
        if media and isinstance(media, list) and media[0].get('url'):
            image_url = media[0]['url'][:500]
        elif entry.get('enclosures'):
            for enc in entry.enclosures:
                if enc.get('type', '').startswith('image/') and enc.get('href'):
                    image_url = enc.href[:500]
                    break

        article = WebRSSArticle(
            feed_id=feed.id,
            title=title,
            url=url,
            summary=summary,
            author=author,
            image_url=image_url,
            guid=guid,
            published_at=published_at,
            fetched_at=now,
        )
        db.add(article)
        new_count += 1

    feed.last_fetched_at = now
    feed.last_error = None
    db.commit()
    return new_count, None


def serialize_post(post, current_user_id=None, db=None, following_ids=None):
    """Serialize a WebPost to a dict for API responses.
    following_ids: set/frozenset of user IDs that the current user follows,
    used to populate author._following so the follow button renders correctly."""
    author_data = serialize_user_brief(post.author) if post.author else None
    if author_data and following_ids is not None:
        author_data['_following'] = post.author.id in following_ids

    data = {
        'id': post.id,
        'author': author_data,
        'content': post.content,
        'post_type': post.post_type,
        'media_url': post.media_url,
        'thumbnail_url': post.thumbnail_url,
        'embed_platform': post.embed_platform,
        'embed_id': post.embed_id,
        'game_tag_id': post.game_tag_id,
        'game_tag_name': post.game_tag_name,
        'game_tag_steam_id': post.game_tag_steam_id,
        'is_pinned': post.is_pinned,
        'like_count': post.like_count,
        'comment_count': post.comment_count,
        'repost_count': post.repost_count,
        'created_at': post.created_at,
        'updated_at': post.updated_at,
        'images': [],
        'liked_by_me': False,
    }

    if post.images:
        data['images'] = [{
            'id': img.id,
            'image_url': img.image_url,
            'thumbnail_url': img.thumbnail_url,
            'sort_order': img.sort_order,
            'width': img.width,
            'height': img.height,
        } for img in post.images]

    if current_user_id and db:
        like = db.query(WebLike).filter_by(
            user_id=current_user_id, post_id=post.id
        ).first()
        data['liked_by_me'] = like is not None

    return data
