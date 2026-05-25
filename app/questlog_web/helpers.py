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
    WebXpEvent, WebFlair, WebUserFlair, WebRankTitle, WebCommunity,
    WebLegacyEvent,
)
from app.db import get_db_session

logger = logging.getLogger(__name__)

STEAM_API_KEY = os.getenv('STEAM_API_KEY', '')

# User IDs excluded from all public listings (leaderboards, suggestions, search, gamers directory)
# Add internal/test accounts here. ID 4 = RyvenTest (test account)
EXCLUDED_USER_IDS = {4}

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


_PUBLIC_ID_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

def generate_post_public_id():
    """Generate a random 8-char alphanumeric public ID for posts."""
    return ''.join(secrets.choice(_PUBLIC_ID_CHARS) for _ in range(8))


def safe_int(value, default=1, min_val=None, max_val=None):
    """Parse an integer from a request param safely, returning default on ValueError."""
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if result is not None and min_val is not None:
        result = max(min_val, result)
    if result is not None and max_val is not None:
        result = min(max_val, result)
    return result


def safe_redirect_url(next_url, default='/'):
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
    # Prefer CF-Connecting-IP (set by Cloudflare, not spoofable when behind CF)
    cf_ip = request.META.get('HTTP_CF_CONNECTING_IP', '').strip()
    if cf_ip:
        return cf_ip
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def _hash_ip(ip_address):
    # Store a full 64-char SHA-256 hex digest — correlatable within a session, not reversible
    return hashlib.sha256(
        (ip_address + AUDIT_LOG_SALT).encode('utf-8')
    ).hexdigest()


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
            login_url = reverse('questlog_web_login')
            return redirect(f'{login_url}?next={quote(request.get_full_path())}')
        request.web_user = web_user
        return view_func(request, *args, **kwargs)
    return wrapper


def api_login_required(view_func):
    """Like web_login_required but returns JSON 401 instead of redirecting. Use on API endpoints."""
    from django.http import JsonResponse as _JsonResponse
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        web_user = get_web_user(request)
        if not web_user:
            return _JsonResponse({'ok': False, 'error': 'Login required.'}, status=401)
        request.web_user = web_user
        return view_func(request, *args, **kwargs)
    return wrapper


def web_verified_required(view_func):
    """Requires login AND email_verified=True. Returns 403 JSON for API calls, redirect for pages."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from django.http import JsonResponse as _JsonResponse
        web_user = get_web_user(request)
        if not web_user:
            login_url = reverse('questlog_web_login')
            if 'application/json' in request.headers.get('Accept', ''):
                return _JsonResponse({'error': 'Login required.'}, status=401)
            return redirect(f'{login_url}?next={quote(request.get_full_path())}')
        if not web_user.email_verified:
            if 'application/json' in request.headers.get('Accept', ''):
                return _JsonResponse({'error': 'Please verify your email before using this feature.'}, status=403)
            from django.contrib import messages as _msg
            _msg.warning(request, "Please verify your email to use this feature.")
            return redirect('/')
        request.web_user = web_user
        return view_func(request, *args, **kwargs)
    return wrapper


def web_admin_required(view_func):
    """Requires Django superuser + active WebUser with is_admin=True (re-verified from DB each request)."""
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

        # Re-verify is_admin from DB on every request (not just session flag)
        # Prevents a revoked admin from retaining access for up to 7 days via session
        if not web_user.is_admin:
            logger.warning(
                f"ADMIN ACCESS DENIED: User {web_user.username} (id={web_user.id}) "
                f"- is_admin=False in DB. IP: {get_client_ip(request)}"
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


def web_mod_required(view_func):
    """Allows site admins (is_admin=True) OR site mods (is_mod=True). Re-verified from DB each request."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        web_user = get_web_user(request)

        if not web_user:
            if request.headers.get('Accept', '').find('application/json') >= 0:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            messages.error(request, "Please log in first.")
            return redirect('questlog_web_login')

        if not (web_user.is_admin or web_user.is_mod):
            logger.warning(
                f"MOD ACCESS DENIED: User {web_user.username} (id={web_user.id}) "
                f"- not admin or mod. IP: {get_client_ip(request)}"
            )
            if request.headers.get('Accept', '').find('application/json') >= 0:
                return JsonResponse({'error': 'Access denied'}, status=403)
            messages.error(request, "Access denied.")
            return redirect('questlog_web_home')

        if web_user.is_banned:
            if request.headers.get('Accept', '').find('application/json') >= 0:
                return JsonResponse({'error': 'Account suspended'}, status=403)
            messages.error(request, "Your account has been suspended.")
            return redirect('questlog_web_home')

        request.web_user = web_user
        return view_func(request, *args, **kwargs)
    return wrapper


def fluxer_login_required(view_func):
    """
    Lightweight Fluxer identity check for list/landing pages (no guild_id needed).
    Accepts a full QL web_user with fluxer_id OR a lite Fluxer OAuth session.
    Sets request.fluxer_id and request.web_user.
    Redirects to fluxer_dashboard_login if neither is present.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        web_user = get_web_user(request)
        user_fluxer_id = None

        if web_user:
            if web_user.is_banned:
                messages.error(request, "Your account has been suspended.")
                return redirect('questlog_web_home')
            user_fluxer_id = str(getattr(web_user, 'fluxer_id', None) or '')

        if not user_fluxer_id:
            lite_id = request.session.get('fluxer_session_id', '')
            lite_ts = request.session.get('fluxer_session_ts', 0)
            if lite_id and (int(time.time()) - lite_ts) < 604800:
                user_fluxer_id = str(lite_id)

        if not user_fluxer_id and not (request.user.is_authenticated and request.user.is_superuser):
            login_url = reverse('questlog_web_fluxer_dashboard_login')
            return redirect(f'{login_url}?next={quote(request.get_full_path())}')

        request.web_user = web_user
        request.fluxer_id = user_fluxer_id or ''
        return view_func(request, *args, **kwargs)
    return wrapper


def discord_login_required(view_func):
    """
    Lightweight Discord identity check for list/landing pages (no guild_id needed).
    Accepts a full QL web_user with discord_id OR a lite Discord OAuth session.
    Sets request.discord_id and request.web_user.
    Redirects to discord_dashboard_login if neither is present.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        web_user = get_web_user(request)
        user_discord_id = None

        if web_user:
            if web_user.is_banned:
                messages.error(request, "Your account has been suspended.")
                return redirect('questlog_web_home')
            user_discord_id = str(getattr(web_user, 'discord_id', None) or '')

        if not user_discord_id:
            lite_id = request.session.get('discord_session_id', '')
            lite_ts = request.session.get('discord_session_ts', 0)
            if lite_id and (int(time.time()) - lite_ts) < 604800:
                user_discord_id = str(lite_id)

        if not user_discord_id and not (request.user.is_authenticated and request.user.is_superuser):
            login_url = reverse('questlog_web_discord_dashboard_login')
            return redirect(f'{login_url}?next={quote(request.get_full_path())}')

        request.web_user = web_user
        request.discord_id = user_discord_id or ''
        return view_func(request, *args, **kwargs)
    return wrapper


def fluxer_or_web_admin_required(view_func):
    """
    Allows access if the user is a Django superuser OR has an active Fluxer session.
    Used for quest-control API endpoints that are reached from both the Discord
    dashboard (web_admin_required) and the Fluxer dashboard (Fluxer OAuth session).
    Returns JSON errors for all failures (these are always API endpoints).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        web_user = get_web_user(request)

        if web_user:
            if web_user.is_banned:
                return JsonResponse({'error': 'Account suspended'}, status=403)
            # QuestLog admin - always allow
            if web_user.is_admin:
                return view_func(request, *args, **kwargs)
            # Fluxer-linked user - allow if they have a fluxer_id (guild admin check is on the page itself)
            user_fluxer_id = str(getattr(web_user, 'fluxer_id', None) or '')
            if user_fluxer_id:
                return view_func(request, *args, **kwargs)

        # Lite Fluxer session (OAuth without QL account)
        lite_id = request.session.get('fluxer_session_id', '')
        lite_ts = request.session.get('fluxer_session_ts', 0)
        if lite_id and (int(time.time()) - lite_ts) < 604800:
            return view_func(request, *args, **kwargs)

        return JsonResponse({'error': 'Authentication required'}, status=401)
    return wrapper


def fluxer_guild_required(view_func):
    """
    Fluxer bot dashboard access guard. Accepts either:
    - A full QL web_user session with fluxer_id linked, OR
    - A lite Fluxer OAuth session (fluxer_session_id) - no QL account needed.
    Also allows Django superuser always.
    Checks: owner_id match OR admin role membership in cached_members.
    Returns JSON 403 for API requests (Accept: application/json).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from .models import WebFluxerGuildSettings

        is_json = 'application/json' in request.headers.get('Accept', '')

        # Resolve Fluxer identity - full QL account OR lite session
        web_user = get_web_user(request)
        user_fluxer_id = None

        if web_user:
            if web_user.is_banned:
                if is_json:
                    return JsonResponse({'error': 'Account suspended'}, status=403)
                messages.error(request, "Your account has been suspended.")
                return redirect('questlog_web_home')
            user_fluxer_id = str(getattr(web_user, 'fluxer_id', None) or '')

        # Lite session fallback - Fluxer OAuth without a QL account
        if not user_fluxer_id:
            lite_id = request.session.get('fluxer_session_id', '')
            lite_ts = request.session.get('fluxer_session_ts', 0)
            # Lite sessions expire after 7 days
            if lite_id and (int(time.time()) - lite_ts) < 604800:
                user_fluxer_id = str(lite_id)

        if not user_fluxer_id and not (request.user.is_authenticated and request.user.is_superuser):
            logger.warning(f"[fluxer_guild_required] No fluxer_id resolved, web_user={web_user}, path={request.path}")
            if is_json:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            login_url = reverse('questlog_web_fluxer_dashboard_login')
            return redirect(f'{login_url}?next={quote(request.get_full_path())}')

        if not request.user.is_superuser:
            guild_id = kwargs.get('guild_id', '').strip() if kwargs.get('guild_id') else ''
            if not guild_id:
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "Access denied.")
                return redirect('questlog_web_home')

            with get_db_session() as db:
                s = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()

            if not s:
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "You don't have access to this guild's dashboard.")
                return redirect('questlog_web_home')

            # Check 1: owner
            if str(s.owner_id or '') == user_fluxer_id:
                request.web_user = web_user
                request.fluxer_id = user_fluxer_id
                return view_func(request, *args, **kwargs)

            # Check 2: user holds one of the configured admin roles
            # Cache must be fresh (< 5 minutes) - stale cache could grant access after role removal
            CACHE_MAX_AGE = 300  # 5 minutes
            cache_age = int(time.time()) - int(s.updated_at or 0)
            granted = False
            try:
                admin_role_ids = json.loads(s.admin_roles) if s.admin_roles else []
                if admin_role_ids and s.cached_members and cache_age <= CACHE_MAX_AGE:
                    members = json.loads(s.cached_members)
                    user_data = next((m for m in members if str(m.get('id')) == user_fluxer_id), None)
                    if user_data:
                        user_roles = user_data.get('roles', [])
                        granted = any(str(r) in [str(ar) for ar in admin_role_ids] for r in user_roles)
                elif admin_role_ids and cache_age > CACHE_MAX_AGE:
                    logger.warning(
                        f"FLUXER GUILD CACHE STALE: guild={guild_id} age={cache_age}s - denying admin-role access"
                    )
            except (json.JSONDecodeError, TypeError, AttributeError):
                granted = False

            if not granted:
                logger.warning(
                    f"FLUXER GUILD ACCESS DENIED: fluxer_id={user_fluxer_id} guild={guild_id} owner={s.owner_id}"
                )
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "You don't have access to this guild's dashboard.")
                return redirect('questlog_web_home')

        request.web_user = web_user
        request.fluxer_id = user_fluxer_id
        return view_func(request, *args, **kwargs)
    return wrapper


def discord_guild_required(view_func):
    """
    Discord bot dashboard access guard. Accepts either:
    - A full QL web_user session with discord_id linked, OR
    - A lite Discord OAuth session (discord_session_id) - no QL account needed.
    Also allows Django superuser always.
    Verifies guild ownership via the guilds table (owner_id) or admin_roles JSON.
    Returns JSON 403 for API requests (Accept: application/json).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        is_json = 'application/json' in request.headers.get('Accept', '')

        web_user = get_web_user(request)
        user_discord_id = None

        if web_user:
            if web_user.is_banned:
                if is_json:
                    return JsonResponse({'error': 'Account suspended'}, status=403)
                messages.error(request, "Your account has been suspended.")
                return redirect('questlog_web_home')
            user_discord_id = str(getattr(web_user, 'discord_id', None) or '')

        # Lite session fallback - Discord OAuth without a QL account
        if not user_discord_id:
            lite_id = request.session.get('discord_session_id', '')
            lite_ts = request.session.get('discord_session_ts', 0)
            if lite_id and (int(time.time()) - lite_ts) < 604800:
                user_discord_id = str(lite_id)

        if not user_discord_id and not (request.user.is_authenticated and request.user.is_superuser):
            if is_json:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            login_url = reverse('questlog_web_discord_dashboard_login')
            return redirect(f'{login_url}?next={quote(request.get_full_path())}')

        if not request.user.is_superuser:
            guild_id = kwargs.get('guild_id', '').strip() if kwargs.get('guild_id') else ''
            if not guild_id:
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "Access denied.")
                return redirect('questlog_web_home')

            with get_db_session() as db:
                row = db.execute(
                    text("SELECT owner_id, admin_roles FROM guilds WHERE guild_id = :g LIMIT 1"),
                    {'g': int(guild_id)}
                ).fetchone()

            if not row:
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "You don't have access to this guild's dashboard.")
                return redirect('questlog_web_home')

            # Check 1: owner
            if str(row[0] or '') == user_discord_id:
                request.web_user = web_user
                request.discord_id = user_discord_id
                return view_func(request, *args, **kwargs)

            # Check 2: admin roles
            granted = False
            try:
                admin_role_ids = json.loads(row[1]) if row[1] else []
                if admin_role_ids:
                    with get_db_session() as db:
                        member = db.execute(
                            text("SELECT roles FROM guild_members WHERE guild_id=:g AND user_id=:u LIMIT 1"),
                            {'g': int(guild_id), 'u': int(user_discord_id)}
                        ).fetchone()
                    if member and member[0]:
                        user_roles = json.loads(member[0])
                        granted = any(str(r) in [str(ar) for ar in admin_role_ids] for r in user_roles)
            except (json.JSONDecodeError, TypeError, AttributeError, ValueError):
                granted = False

            if not granted:
                logger.warning(
                    f"DISCORD GUILD ACCESS DENIED: discord_id={user_discord_id} guild={guild_id} owner={row[0]}"
                )
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "You don't have access to this guild's dashboard.")
                return redirect('questlog_web_home')

        request.web_user = web_user
        request.discord_id = user_discord_id
        return view_func(request, *args, **kwargs)
    return wrapper


def matrix_space_required(view_func):
    """
    Matrix bot dashboard access guard. Requires login plus one of:
    - Django superuser (site admins always allowed), OR
    - The user's matrix_id matches the space's owner_matrix_id in WebMatrixSpaceSettings, OR
    - The user's matrix_id appears in the space's admin_matrix_ids JSON list.
    If no space_id kwarg, falls back to superuser-only (for the space list page).
    Returns JSON 403 for API requests (Accept: application/json).
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        from .models import WebMatrixSpaceSettings
        import urllib.parse as _urlparse

        # URL-decode space_id so DB lookups work regardless of whether the URL
        # arrived encoded (%21room%3Aserver) or plain (!room:server).
        if 'space_id' in kwargs:
            kwargs['space_id'] = _urlparse.unquote(kwargs['space_id'])

        web_user = get_web_user(request)
        is_json = 'application/json' in request.headers.get('Accept', '')

        if not web_user:
            if is_json:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            login_url = reverse('questlog_web_login')
            return redirect(f'{login_url}?next={quote(request.get_full_path())}')

        if web_user.is_banned:
            if is_json:
                return JsonResponse({'error': 'Account suspended'}, status=403)
            messages.error(request, "Your account has been suspended.")
            return redirect('questlog_web_home')

        if not request.user.is_superuser:
            space_id = kwargs.get('space_id', '').strip() if kwargs.get('space_id') else ''
            if not space_id:
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "Access denied.")
                return redirect('questlog_web_home')

            user_matrix_id = str(getattr(web_user, 'matrix_id', None) or '')
            if not user_matrix_id:
                if is_json:
                    return JsonResponse({'error': 'No Matrix account linked'}, status=403)
                messages.error(request, "Link your Matrix account to access the bot dashboard.")
                return redirect('questlog_web_matrix_link')

            with get_db_session() as db:
                s = db.query(WebMatrixSpaceSettings).filter_by(space_id=space_id).first()

            if not s:
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "You don't have access to this space's dashboard.")
                return redirect('questlog_web_home')

            # Check 1: space owner
            if str(s.owner_matrix_id or '') == user_matrix_id:
                request.web_user = web_user
                return view_func(request, *args, **kwargs)

            # Check 2: in admin_matrix_ids list
            granted = False
            try:
                admin_ids = json.loads(s.admin_matrix_ids) if s.admin_matrix_ids else []
                granted = user_matrix_id in [str(a) for a in admin_ids]
            except (json.JSONDecodeError, TypeError, AttributeError):
                granted = False

            if not granted:
                logger.warning(
                    f"MATRIX SPACE ACCESS DENIED: user={web_user.username} "
                    f"matrix={user_matrix_id} space={space_id} owner={s.owner_matrix_id}"
                )
                if is_json:
                    return JsonResponse({'error': 'Access denied'}, status=403)
                messages.error(request, "You don't have access to this space's dashboard.")
                return redirect('questlog_web_home')

        request.web_user = web_user
        return view_func(request, *args, **kwargs)
    return wrapper


def add_web_user_context(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Reuse web_user if already set by web_login_required to avoid a double DB fetch
        if not hasattr(request, 'web_user') or request.web_user is None:
            request.web_user = get_web_user(request)
        # Award daily visit HP once per calendar day (tracked via session to avoid per-request DB hits)
        if request.web_user:
            today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            if not request.session.get('hp_visit_last') == today_str:
                award_hero_points(request.web_user.id, 'daily_visit', ref_id=today_str)
                request.session['hp_visit_last'] = today_str
            # Community owner check for sidebar Community Admin section
            try:
                from sqlalchemy import text as sa_text
                with get_db_session() as _db:
                    count = _db.execute(
                        sa_text("SELECT COUNT(*) FROM web_communities WHERE owner_id=:id AND is_active=1"),
                        {'id': request.web_user.id}
                    ).scalar()
                request.web_user.has_community = bool(count)
            except Exception:
                request.web_user.has_community = False

            # Resolve primary community name + icon for sidebar display.
            # If primary_community_id is not set, auto-detect: if the user belongs to
            # exactly 1 approved community, auto-set it (and persist). If multiple, leave
            # NULL so they choose from the picker in profile edit.
            try:
                from sqlalchemy import text as sa_text
                _pc_id = getattr(request.web_user, 'primary_community_id', None)
                if not _pc_id:
                    with get_db_session() as _db:
                        # Check communities the user is a member of
                        _auto = _db.execute(
                            sa_text(
                                "SELECT c.id FROM web_communities c "
                                "JOIN web_community_members m ON m.community_id = c.id "
                                "WHERE m.user_id = :uid AND c.is_active = 1 "
                                "AND c.network_status = 'approved' LIMIT 2"
                            ),
                            {'uid': request.web_user.id}
                        ).fetchall()
                        if not _auto:
                            # Fall back to owned communities (owner is implicitly a member)
                            _auto = _db.execute(
                                sa_text(
                                    "SELECT id FROM web_communities "
                                    "WHERE owner_id = :uid AND is_active = 1 "
                                    "AND network_status = 'approved' LIMIT 2"
                                ),
                                {'uid': request.web_user.id}
                            ).fetchall()
                        if not _auto:
                            # Fall back to Fluxer bot activity
                            _fluxer_id = getattr(request.web_user, 'fluxer_id', None)
                            if _fluxer_id:
                                _auto = _db.execute(
                                    sa_text(
                                        "SELECT c.id FROM web_communities c "
                                        "JOIN fluxer_member_xp x ON x.guild_id = c.platform_id "
                                        "WHERE x.user_id = :uid AND c.platform = 'fluxer' "
                                        "AND c.is_active = 1 AND c.network_status = 'approved' LIMIT 2"
                                    ),
                                    {'uid': _fluxer_id}
                                ).fetchall()
                        if not _auto:
                            # Fall back to Discord bot activity
                            _discord_id_auto = getattr(request.web_user, 'discord_id', None)
                            if _discord_id_auto:
                                _auto = _db.execute(
                                    sa_text(
                                        "SELECT c.id FROM web_communities c "
                                        "JOIN guild_members gm ON gm.guild_id = c.platform_id "
                                        "WHERE gm.user_id = :uid AND c.platform = 'discord' "
                                        "AND c.is_active = 1 AND c.network_status = 'approved' LIMIT 2"
                                    ),
                                    {'uid': _discord_id_auto}
                                ).fetchall()
                    # Auto-set only when user belongs to exactly 1 approved community.
                    # Community owners with multiple communities must pick from the profile edit page.
                    if len(_auto) == 1:
                        _pc_id = _auto[0][0]
                        # Persist so we don't re-query every request
                        try:
                            with get_db_session() as _db:
                                _db.execute(
                                    sa_text("UPDATE web_users SET primary_community_id = :cid WHERE id = :uid"),
                                    {'cid': _pc_id, 'uid': request.web_user.id}
                                )
                                _db.commit()
                            request.web_user.primary_community_id = _pc_id
                        except Exception:
                            pass
                if _pc_id:
                    with get_db_session() as _db:
                        _pc_row = _db.execute(
                            sa_text(
                                "SELECT name, icon_url, platform FROM web_communities "
                                "WHERE id=:id AND is_active=1 LIMIT 1"
                            ),
                            {'id': _pc_id}
                        ).fetchone()
                    if _pc_row:
                        _plat_raw = _pc_row[2]
                        request.web_user.primary_community_name = _pc_row[0]
                        request.web_user.primary_community_icon = _pc_row[1]
                        request.web_user.primary_community_platform = _plat_raw.value if hasattr(_plat_raw, 'value') else str(_plat_raw)
                    else:
                        request.web_user.primary_community_name = None
                        request.web_user.primary_community_icon = None
                        request.web_user.primary_community_platform = None
                else:
                    request.web_user.primary_community_name = None
                    request.web_user.primary_community_icon = None
                    request.web_user.primary_community_platform = None
            except Exception:
                request.web_user.primary_community_name = None
                request.web_user.primary_community_icon = None
                request.web_user.primary_community_platform = None

            from sqlalchemy import text as sa_text
            _discord_id = getattr(request.web_user, 'discord_id', None)
            _fluxer_id  = getattr(request.web_user, 'fluxer_id',  None)
            _web_uid    = request.web_user.id

            # --- FLUXER (uses fluxer_id ONLY - completely separate platform from Discord) ---
            try:
                if _fluxer_id:
                    _fid_str = str(_fluxer_id)
                    with get_db_session() as _db:
                        # Owned: web_fluxer_guild_settings.owner_id is a Fluxer user ID
                        owned_rows = _db.execute(
                            sa_text(
                                "SELECT guild_id, COALESCE(NULLIF(guild_name,''), guild_id) as name, guild_icon_hash "
                                "FROM web_fluxer_guild_settings WHERE owner_id = :fid LIMIT 10"
                            ),
                            {'fid': _fid_str}
                        ).fetchall()
                        # Web-panel admin/mod via web_community_members (platform='fluxer')
                        admin_rows = _db.execute(
                            sa_text(
                                "SELECT c.platform_id, COALESCE(NULLIF(s.guild_name,''), c.platform_id) as name, s.guild_icon_hash "
                                "FROM web_community_members cm "
                                "JOIN web_communities c ON c.id = cm.community_id "
                                "LEFT JOIN web_fluxer_guild_settings s ON s.guild_id = c.platform_id "
                                "WHERE cm.user_id = :uid AND cm.role IN ('admin','moderator','owner') "
                                "AND c.platform = 'fluxer' AND c.is_active = 1 LIMIT 50"
                            ),
                            {'uid': _web_uid}
                        ).fetchall()
                        # Member: use web_fluxer_members for all servers the bot sees this user in
                        member_rows = _db.execute(
                            sa_text(
                                "SELECT m.guild_id, COALESCE(NULLIF(s.guild_name,''), CAST(m.guild_id AS CHAR)) as name, s.guild_icon_hash "
                                "FROM web_fluxer_members m "
                                "LEFT JOIN web_fluxer_guild_settings s ON s.guild_id = m.guild_id "
                                "WHERE m.user_id = :fid AND m.left_at IS NULL "
                                "LIMIT 50"
                            ),
                            {'fid': _fid_str}
                        ).fetchall()

                    # Normalize all keys to str to avoid int/str type mismatch in set lookup
                    _owned_f = {str(r[0]): {'id': str(r[0]), 'name': r[1], 'icon_hash': r[2] or ''} for r in owned_rows}
                    _admin_f = {str(r[0]): {'id': str(r[0]), 'name': r[1], 'icon_hash': r[2] or ''} for r in admin_rows}
                    _admin_f.update(_owned_f)
                    _member_f = {str(r[0]): {'id': str(r[0]), 'name': r[1], 'icon_hash': r[2] or ''} for r in member_rows}

                    request.web_user.owned_fluxer_guilds = list(_admin_f.values())
                    request.web_user.member_fluxer_guilds = [
                        g for gid, g in _member_f.items() if gid not in _admin_f
                    ]
                else:
                    request.web_user.owned_fluxer_guilds = []
                    request.web_user.member_fluxer_guilds = []
            except Exception:
                request.web_user.owned_fluxer_guilds = []
                request.web_user.member_fluxer_guilds = []

            # --- DISCORD (uses discord_id ONLY - WardenBot tables) ---
            try:
                import json as _json
                if _discord_id:
                    _did_int = int(_discord_id)
                    with get_db_session() as _db:
                        # Fetch guilds where bot is present; use owner_id to classify admin vs member
                        all_guild_rows = _db.execute(
                            sa_text(
                                "SELECT g.guild_id, COALESCE(NULLIF(g.guild_name,''), CAST(g.guild_id AS CHAR)) as name, "
                                "g.guild_icon_hash, g.owner_id "
                                "FROM guild_members gm JOIN guilds g ON g.guild_id = gm.guild_id "
                                "WHERE gm.user_id = :uid AND gm.left_at IS NULL AND g.bot_present = 1 LIMIT 50"
                            ),
                            {'uid': _did_int}
                        ).fetchall()
                        # Also fetch Discord guilds where user has web-panel admin/mod role
                        web_admin_discord_rows = _db.execute(
                            sa_text(
                                "SELECT c.platform_id FROM web_community_members cm "
                                "JOIN web_communities c ON c.id = cm.community_id "
                                "WHERE cm.user_id = :uid AND cm.role IN ('admin','moderator','owner') "
                                "AND c.platform = 'discord' AND c.is_active = 1 LIMIT 50"
                            ),
                            {'uid': _web_uid}
                        ).fetchall()
                        _web_admin_discord_ids = {str(r[0]) for r in web_admin_discord_rows}

                    _admin_d = {}
                    _member_d = {}
                    for row in all_guild_rows:
                        gid, gname, icon_hash, owner_id = row
                        gid_str = str(gid)
                        entry = {'id': gid_str, 'name': gname, 'icon_hash': icon_hash or ''}

                        if str(owner_id) == _discord_id or gid_str in _web_admin_discord_ids:
                            _admin_d[gid_str] = entry
                        else:
                            _member_d[gid_str] = entry

                    request.web_user.owned_discord_guilds = list(_admin_d.values())
                    request.web_user.member_discord_guilds = list(_member_d.values())
                else:
                    request.web_user.owned_discord_guilds = []
                    request.web_user.member_discord_guilds = []
            except Exception:
                request.web_user.owned_discord_guilds = []
                request.web_user.member_discord_guilds = []

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
    'steam_achievement': {'xp': 1,  'daily_max': 50},
    'steam_hours':       {'xp': 1,  'daily_max': None},
    'steam_game_launch': {'xp': 2,  'daily_max': None},  # cooldown enforced in update_steam_now_playing (30 min)
    'invite':            {'xp': 50, 'daily_max': None},
    'champion_sub':      {'xp': 100, 'daily_max': 1},  # one-time bonus on first Champion sub
    # QuestChat native activity - cooldown enforced by _award_chat_xp (60s), no daily cap
    'qc_chat':           {'xp': 2,  'daily_max': None},
    # Fluxer bot activity - cooldowns enforced by bot, no daily caps
    'fluxer_message':    {'xp': 2,  'daily_max': None},
    'fluxer_reaction':   {'xp': 1,  'daily_max': None},
    'fluxer_voice':      {'xp': 3,  'daily_max': None},
    'fluxer_migration':  {'xp': 1,  'daily_max': None},  # one-time historical XP import
    # Discord (WardenBot) activity - cooldowns enforced by bot, no daily caps
    'discord_message':   {'xp': 2,  'daily_max': None},
    'discord_media':     {'xp': 2,  'daily_max': None},
    'discord_reaction':  {'xp': 1,  'daily_max': None},
    'discord_voice':     {'xp': 3,  'daily_max': None},
    'discord_gaming':    {'xp': 2,  'daily_max': None},
    # 7DTD in-game events - awarded via Fluxer bot, unified XP
    '7dtd_boss_kill':    {'xp': 75, 'daily_max': None},  # stalker/miniboss kill
    '7dtd_boss_assist':  {'xp': 25, 'daily_max': None},  # nearby player during boss kill
    # 7DTD organic events - awarded via C# mod -> Django endpoint
    # Group kill > solo kill on Legacy to encourage cooperative play
    'ingame_boss_kill':       {'xp': 75, 'daily_max': None},   # group kill (killer) - 75 XP, 50 Legacy
    'ingame_boss_solo_kill':  {'xp': 75, 'daily_max': None},   # solo kill - 75 XP, 25 Legacy (less Legacy than group)
    'ingame_boss_assist':     {'xp': 25, 'daily_max': None},   # group assist - 25 XP, 15 Legacy
    'ingame_normal_kill':     {'xp': 1,  'daily_max': 50},     # normal mob kill - tiny XP drip, cap 50/day
    'ingame_revive':          {'xp': 20, 'daily_max': 5},
    'ingame_bloodmoon':       {'xp': 50, 'daily_max': 1},
    'ingame_quest_complete':  {'xp': 10, 'daily_max': 10},
    'ingame_trade':           {'xp': 10, 'daily_max': 5},
    # --- FFXIV Lodestone character link ---
    'ffxiv_char_linked':      {'xp': 25,  'daily_max': 1},   # one-time per character link
    # --- FFXIV in-game achievements (synced from Lodestone) ---
    # Progression milestones
    'ffxiv_msq_complete':     {'xp': 50,  'daily_max': None},  # completed an expansion MSQ
    'ffxiv_job_level_cap':    {'xp': 10,  'daily_max': None},  # per job/profession at level cap
    'ffxiv_all_jobs_cap':     {'xp': 200, 'daily_max': None},  # ALL jobs at level cap
    # Endgame content
    'ffxiv_extreme_clear':    {'xp': 30,  'daily_max': None},  # any extreme trial clear
    'ffxiv_savage_clear':     {'xp': 75,  'daily_max': None},  # any savage raid clear
    'ffxiv_ultimate_clear':   {'xp': 250, 'daily_max': None},  # any ultimate raid clear
    'ffxiv_criterion_savage': {'xp': 100, 'daily_max': None},  # criterion savage clear
    # Collector milestones
    'ffxiv_mount_50':         {'xp': 25,  'daily_max': None},  # 50 mounts collected
    'ffxiv_mount_100':        {'xp': 50,  'daily_max': None},
    'ffxiv_mount_200':        {'xp': 100, 'daily_max': None},
    'ffxiv_mount_300':        {'xp': 150, 'daily_max': None},
    'ffxiv_mount_all':        {'xp': 500, 'daily_max': None},  # ALL mounts - legendary
    'ffxiv_minion_50':        {'xp': 15,  'daily_max': None},
    'ffxiv_minion_100':       {'xp': 30,  'daily_max': None},
    'ffxiv_minion_all':       {'xp': 300, 'daily_max': None},
    # Community/mentor
    'ffxiv_mentor':           {'xp': 300, 'daily_max': None},  # earned Mentor crown (PvE or PvP)
    'ffxiv_commendations_50': {'xp': 25,  'daily_max': None},  # 50 player commendations
    'ffxiv_commendations_500':{'xp': 150, 'daily_max': None},
    # Crafting/Gathering mastery
    'ffxiv_crafter_cap':      {'xp': 10,  'daily_max': None},  # any crafter to level cap
    'ffxiv_gatherer_cap':     {'xp': 10,  'daily_max': None},  # any gatherer to level cap
    'ffxiv_all_crafters_cap': {'xp': 200, 'daily_max': None},  # all crafters at cap
    # Fishing
    'ffxiv_ocean_fishing_ach':{'xp': 30,  'daily_max': None},  # ocean fishing achievement
    'ffxiv_big_fish':         {'xp': 50,  'daily_max': None},  # big fish achievement
    # Other prestige
    'ffxiv_triple_triad_all': {'xp': 200, 'daily_max': None},  # all triple triad cards
    'ffxiv_blue_mage_all':    {'xp': 150, 'daily_max': None},  # all blue mage spells
    'ffxiv_deep_dungeon_200': {'xp': 200, 'daily_max': None},  # floor 200 in any deep dungeon
    'ffxiv_eureka_complete':  {'xp': 100, 'daily_max': None},  # Eureka Orthos complete
    # --- Blog / Articles ---
    'article_published':      {'xp': 10,  'daily_max': 2},     # contributor publishes an article
    'article_comment':        {'xp': 3,   'daily_max': 10},    # leaving a comment on an article
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
            # If a ref_id is provided, XP for this action can only be earned once
            # per unique ref (prevents like/unlike/like exploit on the same post/user)
            if ref_id is not None:
                already = db.query(WebXpEvent).filter(
                    WebXpEvent.user_id == user_id,
                    WebXpEvent.action_type == action_type,
                    WebXpEvent.ref_id == str(ref_id),
                ).first()
                if already:
                    return 0

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

            # Hero +25% XP multiplier for active subscribers
            if (
                getattr(user, 'is_hero', 0)
                and getattr(user, 'hero_expires_at', None)
                and user.hero_expires_at > now
            ):
                xp_amount = max(1, int(xp_amount * 1.25))

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

            # Back-write to primary guild leaderboard if user has one and guild opts in
            _backwrite_xp_to_guild(db, user, xp_amount)

            return xp_amount
    except Exception as e:
        logger.error(f"award_xp failed for user {user_id} action {action_type}: {e}")
        return 0


def _backwrite_xp_to_guild(db, user, xp_amount):
    """
    If the user has a primary community with site_xp_to_guild enabled (admin-approved),
    write the site XP into that guild's local leaderboard.
    Silently no-ops if anything is missing - never blocks the main XP award.
    """
    try:
        if not user.primary_community_id:
            return

        community = db.query(WebCommunity).filter_by(
            id=user.primary_community_id,
            is_active=True,
            network_status='approved',
            site_xp_to_guild=True,
        ).first()
        if not community:
            return

        from sqlalchemy import text
        platform = community.platform.value if hasattr(community.platform, 'value') else community.platform
        guild_id = community.platform_id
        if not guild_id:
            return

        if platform == 'fluxer' and user.fluxer_id:
            now_ts = int(time.time())
            db.execute(
                text(
                    "INSERT INTO fluxer_member_xp "
                    "(guild_id, user_id, username, xp, level, message_count, last_message_ts, first_seen, last_active) "
                    "VALUES (:gid, :uid, :uname, :xp, 1, 0, :now, :now, :now) "
                    "ON DUPLICATE KEY UPDATE xp = xp + :xp, last_active = :now"
                ),
                {"gid": guild_id, "uid": str(user.fluxer_id),
                 "uname": user.username, "xp": xp_amount, "now": now_ts}
            )
            db.commit()

        elif platform == 'discord' and user.discord_id:
            db.execute(
                text("UPDATE guild_members SET xp = xp + :xp WHERE guild_id = :gid AND user_id = :uid"),
                {"xp": xp_amount, "gid": int(guild_id), "uid": int(user.discord_id)}
            )
            db.commit()

    except Exception as e:
        logger.warning(f"_backwrite_xp_to_guild failed for user {user.id}: {e}")


def award_hero_points(user_id, action_type, source='web', ref_id=None):
    """
    Legacy alias: delegates to award_xp().
    Kept so existing call sites don't break during transition.
    """
    return award_xp(user_id, action_type, source=source, ref_id=ref_id)


# =============================================================================
# LEGACY SYSTEM
# =============================================================================

# Legacy points per action. source can be: web, fluxer, discord, 7dtd, dayz, minecraft, palworld, soulmask, hytale
LEGACY_ACTIONS = {
    # --- Platform actions ---
    'post_liked':              {'points': 2,  'daily_max': None},
    'post_shared':             {'points': 5,  'daily_max': None},
    'gained_follower':         {'points': 3,  'daily_max': 10},
    'community_member_joined': {'points': 5,  'daily_max': 5},
    'lfg_group_filled':        {'points': 10, 'daily_max': 3},
    'comment_received':        {'points': 1,  'daily_max': None},
    'post_pinned':             {'points': 15, 'daily_max': 1},
    'referral_active':         {'points': 15, 'daily_max': 2},
    'clean_record_30d':        {'points': 10, 'daily_max': 1},
    'clean_record_60d':        {'points': 15, 'daily_max': 1},
    'clean_record_90d':        {'points': 20, 'daily_max': 1},
    'lfg_completed':           {'points': 15, 'daily_max': 3},
    'comment_helpful':         {'points': 5,  'daily_max': 5},
    'community_milestone':     {'points': 25, 'daily_max': 1},
    'event_hosted':            {'points': 20, 'daily_max': 1},
    'most_helpful_vote':       {'points': 15, 'daily_max': 1},  # monthly community award - ref_id = YYYY-MM:category
    # --- In-game actions ---
    'ingame_revive':           {'points': 10, 'daily_max': 5},
    'ingame_trade':            {'points': 8,  'daily_max': 5},
    'ingame_quest_complete':   {'points': 5,  'daily_max': 10},
    'ingame_bloodmoon':        {'points': 15, 'daily_max': 1},
    'ingame_hours_milestone':  {'points': 20, 'daily_max': 1},
    'ingame_clean_record_30d': {'points': 25, 'daily_max': 1},
    'ingame_report_confirmed': {'points': 20, 'daily_max': 2},
    'ingame_survive_milestone':{'points': 15, 'daily_max': 1},
    'ingame_helped_newbie':    {'points': 10, 'daily_max': 3},
    'ingame_community_build':  {'points': 15, 'daily_max': 2},
    # --- 7DTD boss events ---
    'ingame_boss_kill':        {'points': 50, 'daily_max': None},  # group kill (killer) - cooperative play rewarded
    'ingame_boss_assist':      {'points': 15, 'daily_max': None},  # group assist
    'ingame_boss_solo_kill':   {'points': 25, 'daily_max': None},  # solo kill - less than group to encourage coop
    'ingame_normal_kill':      {'points': 0,  'daily_max': None},  # normal kills give no Legacy - only XP drip
    # --- FFXIV prestige achievements (these are the "WOW you did THAT?!" ones) ---
    # Mentor status - took hundreds of hours of helping new players
    'ffxiv_mentor':            {'points': 500, 'daily_max': None},
    'ffxiv_commendations_500': {'points': 200, 'daily_max': None},
    # Ultimate raids - hardest content in the game, long prog commitment
    'ffxiv_ultimate_clear':    {'points': 300, 'daily_max': None},
    # Complete collection milestones - deep time investment
    'ffxiv_mount_all':         {'points': 500, 'daily_max': None},
    'ffxiv_minion_all':        {'points': 300, 'daily_max': None},
    'ffxiv_triple_triad_all':  {'points': 250, 'daily_max': None},
    'ffxiv_blue_mage_all':     {'points': 150, 'daily_max': None},
    'ffxiv_deep_dungeon_200':  {'points': 200, 'daily_max': None},
    # All jobs/crafters at cap - commitment to mastering the game
    'ffxiv_all_jobs_cap':      {'points': 200, 'daily_max': None},
    'ffxiv_all_crafters_cap':  {'points': 150, 'daily_max': None},
    # Savage raiding - dedicated progression content
    'ffxiv_savage_clear':      {'points': 75, 'daily_max': None},
    'ffxiv_criterion_savage':  {'points': 100, 'daily_max': None},
    # Collector milestones
    'ffxiv_mount_300':         {'points': 100, 'daily_max': None},
    'ffxiv_mount_200':         {'points': 50, 'daily_max': None},
    'ffxiv_mount_100':         {'points': 25, 'daily_max': None},
    # Extreme clears - meaningful but not as prestige as savage/ultimate
    'ffxiv_extreme_clear':     {'points': 25, 'daily_max': None},
    # Character link - small bonus for connecting account
    'ffxiv_char_linked':       {'points': 10, 'daily_max': None},
    # --- Negative legacy ---
    'report_upheld':           {'points': -20, 'daily_max': None},
    'temp_ban':                {'points': -50, 'daily_max': None},
}

# Tier thresholds - score >= value = that tier
LEGACY_TIERS = [
    (25000, 5),  # Ascendant
    (7500,  4),  # Champion
    (2000,  3),  # Warden
    (500,   2),  # Ranger
    (0,     1),  # Wanderer
]

LEGACY_TIER_NAMES = {
    1: 'Wanderer',
    2: 'Ranger',
    3: 'Warden',
    4: 'Champion',
    5: 'Ascendant',
}


def _calculate_legacy_tier(score: int) -> int:
    """Return tier (1-5) based on legacy score."""
    for threshold, tier in LEGACY_TIERS:
        if score >= threshold:
            return tier
    return 1


# Award flair definitions - auto-created per month when nominations close
_AWARD_FLAIR_DEFS = {
    'community': {'emoji': '🌟', 'color': 'gold'},
    'lfg_host':  {'emoji': '🎯', 'color': 'cyan'},
    'build':     {'emoji': '🏗️', 'color': 'lime'},
    '7dtd':      {'emoji': '☣️', 'color': 'orange'},
    'valheim':   {'emoji': '❄️', 'color': 'blue'},
    'minecraft': {'emoji': '🧱', 'color': 'green'},
    'dayz':      {'emoji': '🧟', 'color': 'red'},
    'palworld':  {'emoji': '🐉', 'color': 'emerald'},
}

_AWARD_FLAIR_LABELS = {
    'community': 'Most Helpful',
    'lfg_host':  'LFG Host',
    'build':     'Master Builder',
    '7dtd':      'SYNAPSE MVP',
    'valheim':   'Valheim Wanderer',
    'minecraft': 'Minecraft Builder',
    'dayz':      'DayZ Survivor',
    'palworld':  'Palworld Tamer',
}


def grant_flair_award(user_id: int, category: str, month_year: str) -> int | None:
    """Auto-create the monthly award flair if needed, then grant it to user_id.
    Returns the flair id on success, None on failure.
    Flair is exclusive + non-equippable (trophy only).
    """
    import time as _time
    from app.db import get_db_session
    from .models import WebFlair, WebUserFlair

    label = _AWARD_FLAIR_LABELS.get(category)
    defn = _AWARD_FLAIR_DEFS.get(category)
    if not label or not defn:
        logger.warning(f"grant_flair_award: unknown category '{category}'")
        return None

    flair_name = f"{label} - {month_year}"
    now = int(_time.time())

    try:
        with get_db_session() as db:
            # Get or create the flair
            flair = db.query(WebFlair).filter_by(name=flair_name).first()
            if not flair:
                flair = WebFlair(
                    name=flair_name,
                    emoji=defn['emoji'],
                    description=f"Awarded for {label} in {month_year}.",
                    flair_type='exclusive',
                    hp_cost=0,
                    equippable=0,
                    enabled=True,
                    display_order=999,
                    created_at=now,
                    updated_at=now,
                )
                db.add(flair)
                db.flush()

            # Grant to user if not already owned
            existing = db.query(WebUserFlair).filter_by(
                user_id=user_id, flair_id=flair.id
            ).first()
            if not existing:
                db.add(WebUserFlair(
                    user_id=user_id,
                    flair_id=flair.id,
                    is_equipped=False,
                    purchased_at=now,
                ))
            db.commit()
            return flair.id
    except Exception as e:
        logger.error(f"grant_flair_award: failed for user {user_id} cat {category}: {e}")
        return None


def award_legacy(user_id, action_type, source='web', ref_id=None):
    """
    Award Legacy points to a user for the given action.
    Mirrors award_xp() pattern exactly.
    Always pass ref_id to prevent duplicate awards.
    Returns points awarded (0 if capped, unknown action, or duplicate).
    """
    from sqlalchemy import text
    from app.questlog_web.models import WebLegacyEvent, WebUser
    from app.db import get_db_session

    config = LEGACY_ACTIONS.get(action_type)
    if not config:
        logger.warning(f"award_legacy: unknown action_type '{action_type}'")
        return 0

    points = config['points']
    daily_max = config['daily_max']

    try:
        with get_db_session() as db:
            now = int(time.time())

            # Duplicate check via ref_id
            if ref_id is not None:
                existing = db.execute(text(
                    "SELECT id FROM web_legacy_events "
                    "WHERE user_id=:uid AND action_type=:act AND ref_id=:ref LIMIT 1"
                ), {'uid': user_id, 'act': action_type, 'ref': str(ref_id)}).fetchone()
                if existing:
                    return 0

            # Daily cap check (skip for negative actions)
            if daily_max is not None and points > 0:
                today_start = now - (now % 86400)
                count = db.execute(text(
                    "SELECT COUNT(*) FROM web_legacy_events "
                    "WHERE user_id=:uid AND action_type=:act AND created_at>=:ts"
                ), {'uid': user_id, 'act': action_type, 'ts': today_start}).scalar()
                if count >= daily_max:
                    return 0

            # Insert event
            db.execute(text(
                "INSERT INTO web_legacy_events (user_id, action_type, points, source, ref_id, created_at) "
                "VALUES (:uid, :act, :pts, :src, :ref, :ts)"
            ), {'uid': user_id, 'act': action_type, 'pts': points,
                'src': source, 'ref': str(ref_id) if ref_id else None, 'ts': now})

            # Update legacy_score and recalculate tier on web_users
            db.execute(text(
                "UPDATE web_users SET legacy_score = GREATEST(0, legacy_score + :pts) WHERE id = :uid"
            ), {'pts': points, 'uid': user_id})

            # Fetch new score and update tier
            new_score = db.execute(text(
                "SELECT legacy_score FROM web_users WHERE id = :uid"
            ), {'uid': user_id}).scalar() or 0
            new_tier = _calculate_legacy_tier(new_score)
            db.execute(text(
                "UPDATE web_users SET legacy_tier = :tier WHERE id = :uid"
            ), {'tier': new_tier, 'uid': user_id})

            db.commit()
            return points

    except Exception as e:
        logger.error(f"award_legacy failed for user {user_id} action {action_type}: {e}")
        return 0


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
        # Block internal/loopback/private addresses.
        # On DNS failure, reject - we cannot verify the URL is safe.
        try:
            for _, _, _, _, sockaddr in _socket.getaddrinfo(hostname, None):
                ip = ipaddress.ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return None
        except Exception:
            return None  # DNS failure - reject rather than allow through unverified
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


import ipaddress as _ipaddress

_BLOCKED_NETWORKS = [
    _ipaddress.ip_network(cidr) for cidr in (
        # IPv4
        '0.0.0.0/8',         # this network (includes 0.x.x.x)
        '127.0.0.0/8',       # loopback
        '10.0.0.0/8',        # private
        '172.16.0.0/12',     # private
        '192.168.0.0/16',    # private
        '100.64.0.0/10',     # shared address (CGNAT)
        '192.0.0.0/24',      # IETF protocol
        '169.254.0.0/16',    # link-local
        '192.88.99.0/24',    # 6to4 relay
        '198.18.0.0/15',     # benchmarking
        '192.0.2.0/24',      # TEST-NET-1
        '198.51.100.0/24',   # TEST-NET-2
        '203.0.113.0/24',    # TEST-NET-3
        '224.0.0.0/4',       # multicast
        '240.0.0.0/4',       # reserved
        '255.255.255.255/32', # broadcast
        # IPv6
        '::/128',            # unspecified
        '::1/128',           # loopback
        'fe80::/10',         # link-local
        'fc00::/7',          # unique local
        '2001:db8::/32',     # documentation
        'ff00::/8',          # multicast
        'fec0::/10',         # deprecated site-local
        '64:ff9b::/96',      # IPv4-mapped (NAT64)
    )
]


def _is_blocked_ip(addr_str):
    """Return True if the resolved IP falls in any blocked network range."""
    try:
        ip = _ipaddress.ip_address(addr_str)
        return any(ip in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        return True  # unparseable = block it


def fetch_link_preview(url):
    """Fetch Open Graph metadata for a URL. Returns a dict or None.
    Security hardening:
    - HTTPS only, no HTTP
    - No redirects followed (prevents SSRF via redirect chaining)
    - DNS resolved before connect; all RFC-reserved ranges blocked
    - 3s timeout, 500KB cap
    - OG values stripped of HTML tags and length-capped
    """
    import socket
    import html as _html
    from urllib.request import urlopen, Request, HTTPRedirectHandler, build_opener
    from urllib.error import HTTPError

    # Subclass that blocks ALL redirects
    class _NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None  # never follow

    try:
        if not url or not isinstance(url, str):
            return None
        url = url.strip()
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            return None
        host = parsed.hostname  # properly handles IPv6 brackets, ports
        if not host:
            return None

        # Resolve DNS and block all RFC-reserved ranges (pre-connect SSRF guard)
        # getaddrinfo returns all records; check every resolved address to prevent SSRF via multi-homed hosts
        try:
            records = socket.getaddrinfo(host, None)
            if not records or any(_is_blocked_ip(r[4][0]) for r in records):
                return None
        except Exception:
            return None

        req = Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; QuestLogBot/1.0)',
            'Accept': 'text/html',
        })
        opener = build_opener(_NoRedirect())
        try:
            resp = opener.open(req, timeout=3)
        except HTTPError as e:
            # 3xx responses raise HTTPError when redirects are blocked - that's fine
            if e.code in (301, 302, 303, 307, 308):
                return None
            raise
        with resp:
            content_type = resp.headers.get('Content-Type', '').lower()
            if 'html' not in content_type:
                return None
            raw = resp.read(524288).decode('utf-8', errors='replace')

        def _clean_og(val, max_len=300):
            """Strip tags, decode HTML entities, cap length."""
            if not val:
                return ''
            # Strip any HTML tags
            val = re.sub(r'<[^>]+>', '', val)
            # Decode HTML entities (&amp; &lt; etc.)
            val = _html.unescape(val)
            return val.strip()[:max_len]

        og = {}
        for prop in ('title', 'description', 'image', 'url', 'site_name'):
            m = re.search(
                r'<meta[^>]+(?:property=["\']og:' + prop + r'["\']|name=["\']og:' + prop + r'["\'])[^>]+content=["\']([^"\']{1,500})["\']',
                raw, re.IGNORECASE
            )
            if m:
                cleaned = _clean_og(m.group(1))
                if cleaned:
                    og[prop] = cleaned

        # Fallback to <title> if no og:title
        if 'title' not in og:
            m = re.search(r'<title[^>]*>([^<]{1,200})</title>', raw, re.IGNORECASE)
            if m:
                og['title'] = _clean_og(m.group(1), max_len=200)

        if not og.get('title') and not og.get('description'):
            return None

        # Validate og:image - HTTPS only, no private IPs, not embedded data URIs
        img = og.get('image', '')
        if img:
            try:
                img_parsed = urlparse(img)
                if img_parsed.scheme != 'https' or not img_parsed.hostname:
                    og.pop('image', None)
                else:
                    img_records = socket.getaddrinfo(img_parsed.hostname, None)
                    if not img_records or any(_is_blocked_ip(r[4][0]) for r in img_records):
                        og.pop('image', None)
            except Exception:
                og.pop('image', None)

        og['source_url'] = url
        return og

    except Exception as e:
        logger.debug("fetch_link_preview failed for %r: %s", url, e)
        return None


def sanitize_text(text_input, max_length=2000):
    """Sanitize user text input: escape HTML entities, normalize whitespace, limit length."""
    import html as _html
    if not text_input:
        return ''
    # Use html.unescape first to normalize any existing entities, then re-escape
    # This prevents double-encoding while ensuring all tags are neutralized
    clean = _html.escape(str(text_input), quote=False)
    clean = re.sub(r'\n{3,}', '\n\n', clean)
    clean = clean[:max_length].strip()
    return clean


# HTML tags and attributes allowed in rendered article bodies.
# This is the ONLY set that survives after markdown -> HTML conversion.
# Everything else is stripped before the HTML ever reaches a template.
_ARTICLE_ALLOWED_TAGS = frozenset({
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'p', 'br', 'hr',
    'strong', 'b', 'em', 'i', 'u', 's', 'del', 'ins', 'mark', 'small', 'sub', 'sup',
    'ul', 'ol', 'li',
    'blockquote', 'pre', 'code',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'a', 'img',
    'div', 'span',
    'details', 'summary',
})

_ARTICLE_ALLOWED_ATTRS = {
    'a':   {'href', 'title', 'rel', 'target'},
    'img': {'src', 'alt', 'title', 'width', 'height'},
    'th':  {'scope', 'colspan', 'rowspan'},
    'td':  {'colspan', 'rowspan'},
    'code': {'class'},   # for syntax-highlight class names (e.g. language-python)
    'pre':  {'class'},
    'div':  {'class'},
    'span': {'class'},
}

# Schemes allowed in href/src attributes
_SAFE_URL_SCHEMES = frozenset({'http', 'https', 'mailto'})


def _sanitize_url(url):
    """Return url only if its scheme is in _SAFE_URL_SCHEMES, else '#'."""
    from urllib.parse import urlparse
    if not url:
        return '#'
    try:
        scheme = urlparse(url.strip()).scheme.lower()
    except Exception:
        return '#'
    if scheme not in _SAFE_URL_SCHEMES:
        return '#'
    return url.strip()


def _strip_html_to_allowlist(html_source):
    """
    Walk the parsed HTML tree and rebuild it keeping only allowed tags/attrs.
    Uses stdlib html.parser - no third-party sanitizer needed.
    Enforces _SAFE_URL_SCHEMES on href and src to block javascript: and data: URIs.
    """
    import html as _html
    from html.parser import HTMLParser

    VOID_ELEMENTS = frozenset({
        'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
        'link', 'meta', 'param', 'source', 'track', 'wbr',
    })

    class _Sanitizer(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self._out = []

        def handle_starttag(self, tag, attrs):
            tag = tag.lower()
            if tag not in _ARTICLE_ALLOWED_TAGS:
                return
            allowed_attr_names = _ARTICLE_ALLOWED_ATTRS.get(tag, set())
            safe_attrs = []
            for name, value in attrs:
                name = name.lower()
                if name not in allowed_attr_names:
                    continue
                if value is None:
                    value = ''
                if name in ('href', 'src'):
                    value = _sanitize_url(value)
                # Strip event handlers defensively (shouldn't reach here but belt+braces)
                if name.startswith('on'):
                    continue
                safe_attrs.append(f'{_html.escape(name)}="{_html.escape(value)}"')
            # Force rel="noopener noreferrer" on external links
            if tag == 'a' and 'href' in {n for n, _ in attrs}:
                has_rel = any(n.lower() == 'rel' for n, _ in attrs)
                if not has_rel:
                    safe_attrs.append('rel="noopener noreferrer"')
                # Force target=_blank only when we have a full URL (not anchor)
                href_val = next((v for n, v in attrs if n.lower() == 'href'), '')
                if href_val and href_val.startswith('http'):
                    safe_attrs.append('target="_blank"')
            attr_str = (' ' + ' '.join(safe_attrs)) if safe_attrs else ''
            if tag in VOID_ELEMENTS:
                self._out.append(f'<{tag}{attr_str}>')
            else:
                self._out.append(f'<{tag}{attr_str}>')

        def handle_endtag(self, tag):
            tag = tag.lower()
            if tag not in _ARTICLE_ALLOWED_TAGS:
                return
            VOID_ELEMENTS = frozenset({
                'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                'link', 'meta', 'param', 'source', 'track', 'wbr',
            })
            if tag not in VOID_ELEMENTS:
                self._out.append(f'</{tag}>')

        def handle_data(self, data):
            self._out.append(_html.escape(data, quote=False))

        def handle_entityref(self, name):
            self._out.append(f'&{_html.escape(name)};')

        def handle_charref(self, name):
            self._out.append(f'&#{_html.escape(name)};')

        def get_output(self):
            return ''.join(self._out)

    sanitizer = _Sanitizer()
    sanitizer.feed(html_source)
    return sanitizer.get_output()


def sanitize_article_html(markdown_source, max_chars=100_000):
    """
    Convert Markdown source to sanitized HTML safe for direct template rendering.

    Pipeline:
      1. Hard-limit raw markdown size to prevent DoS via huge inputs.
      2. Convert markdown -> HTML using python-markdown with safe extensions.
      3. Strip all tags/attrs not on the allowlist (_ARTICLE_ALLOWED_TAGS).
      4. Enforce URL scheme allowlist on every href/src.
      5. Return the resulting HTML string.

    The returned string is marked safe for Django's |safe filter ONLY because
    we fully control what tags and attributes survive. Never call this on
    arbitrary HTML that skipped step 2.
    """
    import re as _re
    import markdown as _md

    if not markdown_source:
        return ''

    # Hard cap on input size - prevents ReDoS / CPU exhaustion on pathological markdown
    source = str(markdown_source)[:max_chars]

    # Pre-process: wrap bare URLs that are NOT already inside markdown link syntax
    # [text](url) or <url> - so they survive as clickable links after markdown render.
    # We only match http/https to stay safe.
    _bare_url_re = _re.compile(
        r'(?<!\()'                    # not preceded by ( - already a markdown link target
        r'(?<!\[)'                    # not preceded by [ - markdown link label
        r'(?<!href=")'                # not inside an href already
        r'(https?://[^\s\)\]<>"]+)',  # the URL itself
    )
    def _wrap_url(m):
        url = m.group(1)
        return f'[{url}]({url})'
    source = _bare_url_re.sub(_wrap_url, source)

    # Convert markdown to raw HTML.
    # Extensions used:
    #   - tables:   GitHub-style tables
    #   - fenced_code: ``` code blocks
    #   - nl2br:    newlines become <br> inside paragraphs
    #   - toc:      auto-generates id attrs on headings for anchor links
    #   - sane_lists: fixes mixed list edge cases
    raw_html = _md.markdown(
        source,
        extensions=['tables', 'fenced_code', 'nl2br', 'toc', 'sane_lists'],
        output_format='html',
    )

    # Walk the HTML tree and enforce the allowlist
    return _strip_html_to_allowlist(raw_html)


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
# Types NOT listed here (e.g. giveaway_win, level_up system) are always delivered.
_NOTIF_PREF_FIELD = {
    # Social
    'follow':         'notify_follows',
    'like':           'notify_likes',
    'comment':        'notify_comments',
    'comment_like':   'notify_comment_likes',
    'share':          'notify_shares',
    'mention':        'notify_mentions',
    # Gaming
    'lfg_join':       'notify_lfg_join',
    'lfg_leave':      'notify_lfg_leave',
    'lfg_full':       'notify_lfg_full',
    'now_playing':    'notify_now_playing',
    # Platform
    'giveaway':       'notify_giveaways',
    'community_join': 'notify_community_join',
    # level_up is NOT listed - always delivered (system notification)
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
        # Re-encode through Pillow to strip embedded scripts/metadata rather than writing raw bytes
        try:
            frames = []
            durations = []
            for frame_idx in range(getattr(img, 'n_frames', 1)):
                img.seek(frame_idx)
                frames.append(img.copy().convert('RGBA'))
                durations.append(img.info.get('duration', 100))
            frames[0].save(
                save_path, format='GIF', save_all=True, append_images=frames[1:],
                loop=0, duration=durations, optimize=False,
            )
        except Exception:
            # Fallback: write raw bytes if Pillow multi-frame save fails
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
    # Second flair slot (Champions only)
    flair2_emoji, flair2_name = '', ''
    if getattr(user, 'active_flair2_id', None) and getattr(user, 'is_hero', 0):
        flair2_emoji, flair2_name = _get_flair_from_cache(user.active_flair2_id)
    return {
        'id': user.id,
        'username': user.username,
        'display_name': user.display_name or user.username,
        'avatar_url': user.avatar_url or user.steam_avatar,
        'is_banned': user.is_banned,
        'is_vip': bool(user.is_vip),
        'is_ffxiv_member': bool(getattr(user, 'is_ffxiv_member', False)),
        'is_contributor': bool(getattr(user, 'is_contributor', False)),
        'web_level': user.web_level or 1,
        'rank_title': rank_title,
        'flair_emoji': flair_emoji,
        'flair_name': flair_name,
        'flair2_emoji': flair2_emoji,
        'flair2_name': flair2_name,
        'current_game': user.current_game if getattr(user, 'show_playing_status', False) else None,
        'current_game_appid': (getattr(user, 'current_game_appid', None) if getattr(user, 'show_playing_status', False) else None),
        'is_live': bool(getattr(user, 'is_live', 0)),
        'live_platform': getattr(user, 'live_platform', None) or '',
        'live_url': getattr(user, 'live_url', None) or '',
        'is_hero': bool(getattr(user, 'is_hero', 0)),
    }


def serialize_user_admin(user):
    """Serialize a WebUser with admin-level detail. Only use in admin views."""
    data = serialize_user_brief(user)
    data.update({
        'steam_id': user.steam_id,
        'discord_id': user.discord_id,
        'email': user.email,
        'is_admin': user.is_admin,
        'is_mod': user.is_mod,
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
    if author_data and post.author:
        if following_ids is not None:
            author_data['_following'] = post.author.id in following_ids
        elif current_user_id and db and current_user_id != post.author.id:
            from app.questlog_web.models import WebFollow
            author_data['_following'] = db.query(WebFollow).filter_by(
                follower_id=current_user_id, following_id=post.author.id
            ).first() is not None
        else:
            author_data['_following'] = False

    data = {
        'id': post.id,
        'public_id': post.public_id,
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
        'game_tag_cover_url': (
            f'https://cdn.cloudflare.steamstatic.com/steam/apps/{post.game_tag_steam_id}/library_600x900.jpg'
            if post.game_tag_steam_id else None
        ),
        'is_pinned': post.is_pinned,
        'edited_at': post.edited_at,
        'edit_count': post.edit_count or 0,
        'link_preview': json.loads(post.link_preview) if post.link_preview else None,
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


def get_steam_cover_url(aid):
    """Return a working cover image URL for a Steam appid.
    Tries the standard CDN first. Falls back to the Store API header_image
    for new titles not yet on the standard CDN. Result cached 24h."""
    try:
        from django.core.cache import cache
        import requests
        cache_key = f'steam_cover_{aid}'
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        standard = f'https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/capsule_sm_120.jpg'
        try:
            r = requests.head(standard, timeout=3, allow_redirects=True)
            if r.status_code == 200:
                cache.set(cache_key, standard, 86400)
                return standard
        except Exception:
            pass
        try:
            r = requests.get(
                f'https://store.steampowered.com/api/appdetails?appids={aid}&filters=basic',
                timeout=4,
            )
            img = r.json().get(str(aid), {}).get('data', {}).get('header_image', '')
            if img:
                cache.set(cache_key, img, 86400)
                return img
        except Exception:
            pass
        cache.set(cache_key, standard, 3600)
        return standard
    except Exception:
        return f'https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/capsule_sm_120.jpg'
