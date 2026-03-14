# views_matrix_dashboard.py - QuestLogMatrix Bot Dashboard
#
# Per-space Matrix bot configuration dashboard.
# Mirrors views_bot_dashboard.py patterns exactly.
#
# URL structure:
#   /ql/dashboard/matrix/                              - space list landing
#   /ql/dashboard/matrix/<space_id>/                   - per-space overview
#   /ql/dashboard/matrix/<space_id>/rooms/             - room management
#   /ql/dashboard/matrix/<space_id>/members/           - member management
#   /ql/dashboard/matrix/<space_id>/xp/                - XP & Leveling
#   /ql/dashboard/matrix/<space_id>/moderation/        - Moderation settings
#   /ql/dashboard/matrix/<space_id>/welcome/           - Welcome messages
#   /ql/dashboard/matrix/<space_id>/ban-lists/         - Ban lists (Draupnir-style)
#   /ql/dashboard/matrix/<space_id>/rss/               - RSS feeds
#   /ql/dashboard/matrix/<space_id>/messages/          - Send message to room
#   /ql/dashboard/matrix/<space_id>/settings/          - Space settings
#   /ql/api/dashboard/matrix/<space_id>/...            - REST API endpoints

import json
import time
import re
import logging
import urllib.parse
import os
import urllib.request

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from app.db import get_db_session
from sqlalchemy import text as sa_text
from .models import (
    WebMatrixSpaceSettings, WebMatrixRoom, WebMatrixMember,
    WebMatrixModWarning, WebMatrixWelcomeConfig,
    WebMatrixRssFeed, WebMatrixRssArticle,
    WebMatrixGuildAction, WebMatrixXpEvent,
    WebMatrixBanList, WebMatrixBanListEntry,
    WebMatrixLevelRole, WebMatrixXpBoost,
    WebBridgeConfig, WebBridgeRelayQueue,
)
from django_ratelimit.decorators import ratelimit
from .helpers import (
    web_login_required, matrix_space_required, add_web_user_context,
    safe_int, sanitize_text,
)

logger = logging.getLogger(__name__)

_MATRIX_ID_RE = re.compile(r'^@[\w._\-=]+:[A-Za-z0-9.\-]+$')

# ---- Matrix live API helper ----
_MATRIX_HOMESERVER = os.getenv('MATRIX_HOMESERVER', 'https://matrix.casual-heroes.com')
_MATRIX_ACCESS_TOKEN = os.getenv('MATRIX_ACCESS_TOKEN', '')

# Simple in-process cache: room_id -> (timestamp, members_list)
_room_members_cache: dict = {}
_ROOM_MEMBERS_CACHE_TTL = 60  # seconds


def _fetch_room_members_live(room_id: str) -> list[dict] | None:
    """Call Matrix /_matrix/client/v3/rooms/{roomId}/joined_members.
    Returns list of {matrix_id, display_name, avatar_url} or None on error.
    Results cached for 60 seconds.
    """
    now = time.time()
    cached = _room_members_cache.get(room_id)
    if cached and now - cached[0] < _ROOM_MEMBERS_CACHE_TTL:
        return cached[1]

    token = _MATRIX_ACCESS_TOKEN
    if not token:
        return None

    encoded_room = urllib.parse.quote(room_id, safe='')
    url = f"{_MATRIX_HOMESERVER}/_matrix/client/v3/rooms/{encoded_room}/joined_members"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        members = []
        for mid, info in data.get('joined', {}).items():
            members.append({
                'matrix_id': mid,
                'display_name': (info.get('display_name') or '').strip() or mid,
                'avatar_url': info.get('avatar_url') or '',
            })
        members.sort(key=lambda m: m['display_name'].lower())
        _room_members_cache[room_id] = (now, members)
        return members
    except Exception as e:
        logger.warning(f"Matrix live members fetch failed for {room_id}: {e}")
        return None


def _valid_matrix_id(value: str) -> bool:
    return bool(_MATRIX_ID_RE.match(str(value or '')))


def _valid_room_id(value: str) -> bool:
    return str(value or '').startswith('!')


def _url_encode_space(space_id: str) -> str:
    """URL-encode a Matrix space ID for use in href attributes."""
    return urllib.parse.quote(space_id, safe='')


# ---------------------------------------------------------------------------
# Common context helper
# ---------------------------------------------------------------------------

def _get_space_context(db, space_id: str, request=None) -> dict:
    """Load common context for all Matrix dashboard pages."""
    settings = db.query(WebMatrixSpaceSettings).filter_by(space_id=space_id).first()

    # Walk two levels: direct children of the space, then children of any sub-spaces.
    # This surfaces the actual chat rooms rather than the sub-space containers.
    direct = db.query(WebMatrixRoom).filter(
        WebMatrixRoom.space_id == space_id,
    ).all()
    direct_room_ids = [r.room_id for r in direct]

    sub_space_children = []
    sub_space_ids = []
    if direct_room_ids:
        sub_space_children = db.query(WebMatrixRoom).filter(
            WebMatrixRoom.space_id.in_(direct_room_ids),
        ).all()
        sub_space_ids = list({r.space_id for r in sub_space_children})

    if sub_space_children:
        all_room_rows = sub_space_children[:]
        for r in direct:
            if r.room_id not in sub_space_ids:
                all_room_rows.append(r)
    else:
        all_room_rows = direct[:]

    # Skip rooms where name hasn't been synced yet (room_id stored as name placeholder)
    named_rooms = [r for r in all_room_rows if r.room_name and r.room_name != r.room_id]
    seen = set()
    rooms = []
    for r in sorted(named_rooms, key=lambda r: r.room_name or ''):
        if r.room_id not in seen:
            seen.add(r.room_id)
            rooms.append(r)

    rooms_json = [
        {'value': r.room_id, 'label': r.room_name or r.room_id, 'alias': r.room_alias or ''}
        for r in rooms
    ]

    # All spaces for sidebar switcher - scoped to current user if possible
    all_spaces_rows = db.query(WebMatrixSpaceSettings).filter_by(bot_present=1).order_by(
        WebMatrixSpaceSettings.space_name).all()
    all_spaces = [
        {
            'space_id': s.space_id,
            'space_id_url': _url_encode_space(s.space_id),
            'space_name': s.space_name or s.space_id,
        }
        for s in all_spaces_rows
    ]

    # Extract all settings fields into a plain dict while the DB session is still open.
    # Passing the raw SQLAlchemy object to the template breaks once the session closes.
    settings_dict = {
        'bot_prefix': '!',
        'language': 'en',
        'timezone': 'UTC',
        'mod_log_room_id': '',
        'owner_matrix_id': '',
        'admin_matrix_ids': [],
        'warn_threshold': 3,
        'xp_enabled': True,
        'xp_per_message': 2,
        'xp_cooldown_secs': 60,
        'xp_ignored_rooms': [],
        'level_up_enabled': False,
        'level_up_room_id': '',
        'level_up_message': '',
        'auto_ban_after_warns': False,
        'admin_power_level': 50,
        'space_name': space_id,
        'space_avatar_url': '',
        # Audit fields (may not exist in DB yet)
        'audit_log_room_id': '',
        'audit_log_enabled': False,
        'audit_event_config': {},
        # Verification fields (may not exist in DB yet)
        'verification_type': 'none',
        'verification_room_id': '',
        'verification_account_age_days': 7,
        'verification_verified_message': '',
        'verification_failed_message': '',
    }
    if settings:
        settings_dict.update({
            'bot_prefix': settings.bot_prefix or '!',
            'language': settings.language or 'en',
            'timezone': settings.timezone or 'UTC',
            'mod_log_room_id': settings.mod_log_room_id or '',
            'owner_matrix_id': settings.owner_matrix_id or '',
            'admin_matrix_ids': json.loads(settings.admin_matrix_ids or '[]'),
            'warn_threshold': settings.warn_threshold or 3,
            'xp_enabled': bool(settings.xp_enabled),
            'xp_per_message': settings.xp_per_message or 2,
            'xp_cooldown_secs': settings.xp_cooldown_secs or 60,
            'xp_ignored_rooms': json.loads(settings.xp_ignored_rooms or '[]'),
            'level_up_enabled': bool(settings.level_up_enabled),
            'level_up_room_id': settings.level_up_room_id or '',
            'level_up_message': settings.level_up_message or '',
            'auto_ban_after_warns': bool(settings.auto_ban_after_warns),
            'admin_power_level': settings.admin_power_level or 50,
            'space_name': settings.space_name or space_id,
            'space_avatar_url': settings.space_avatar_url or '',
            # Audit fields (may not exist in DB yet - use getattr)
            'audit_log_room_id': getattr(settings, 'audit_log_room_id', None) or '',
            'audit_log_enabled': bool(getattr(settings, 'audit_log_enabled', False)),
            'audit_event_config': json.loads(getattr(settings, 'audit_event_config', None) or '{}'),
            # Verification fields (may not exist in DB yet)
            'verification_type': getattr(settings, 'verification_type', None) or 'none',
            'verification_room_id': getattr(settings, 'verification_room_id', None) or '',
            'verification_account_age_days': getattr(settings, 'verification_account_age_days', 7) or 7,
            'verification_verified_message': getattr(settings, 'verification_verified_message', None) or '',
            'verification_failed_message': getattr(settings, 'verification_failed_message', None) or '',
            'updated_at': settings.updated_at,
        })

    space_name = settings_dict['space_name']

    return {
        'space_id': space_id,
        'space_id_url': _url_encode_space(space_id),
        'settings': settings_dict,
        'settings_json': json.dumps(settings_dict),
        'rooms': rooms,
        'rooms_json': json.dumps(rooms_json),
        'space_name': space_name,
        'all_spaces': all_spaces,
        '_settings_obj': settings,  # raw ORM object for views that need to modify it
    }


def _queue_action(space_id: str, action_type: str, payload: dict, db) -> int:
    """Queue a bot action. Returns the action ID."""
    now = int(time.time())
    action = WebMatrixGuildAction(
        space_id=space_id,
        action_type=action_type,
        payload_json=json.dumps(payload),
        status='pending',
        created_at=now,
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action.id


# ---------------------------------------------------------------------------
# Dashboard Landing - Space List
# ---------------------------------------------------------------------------

@web_login_required
@add_web_user_context
def matrix_dashboard(request):
    """List all Matrix spaces the user has admin access to."""
    web_user = getattr(request, 'web_user', None)
    if not web_user:
        return redirect('questlog_web_login')

    user_matrix_id = str(getattr(web_user, 'matrix_id', '') or '')
    spaces = []

    with get_db_session() as db:
        if request.user.is_superuser:
            rows = db.query(WebMatrixSpaceSettings).filter_by(bot_present=1).order_by(
                WebMatrixSpaceSettings.space_name).all()
        elif user_matrix_id:
            rows = db.query(WebMatrixSpaceSettings).filter(
                sa_text(
                    "bot_present=1 AND (owner_matrix_id=:mid OR JSON_CONTAINS(IFNULL(admin_matrix_ids,'[]'), JSON_QUOTE(:mid)))"
                ).bindparams(mid=user_matrix_id)
            ).all()
        else:
            rows = []

        for s in rows:
            spaces.append({
                'space_id': s.space_id,
                'space_id_url': _url_encode_space(s.space_id),
                'space_name': s.space_name or s.space_id,
                'space_avatar_url': s.space_avatar_url or '',
                'room_count': s.room_count,
                'member_count': s.member_count,
                'bot_present': bool(s.bot_present),
            })

    return render(request, 'questlog_web/matrix_guild_list.html', {
        'spaces': spaces,
        'has_matrix': bool(user_matrix_id),
        'active_section': 'dashboard_list',
    })


# ---------------------------------------------------------------------------
# Per-Space Overview
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_dashboard(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
        member_count = db.query(WebMatrixMember).filter_by(space_id=space_id).filter(
            WebMatrixMember.left_at == None  # noqa: E711
        ).count()
        warn_count = db.query(WebMatrixModWarning).filter_by(
            space_id=space_id, is_active=1).count()
        xp_count = db.query(WebMatrixXpEvent).filter_by(space_id=space_id).count()
        rss_count = db.query(WebMatrixRssFeed).filter_by(space_id=space_id, enabled=1).count()

    ctx.update({
        'active_section': 'overview',
        'member_count': member_count,
        'warn_count': warn_count,
        'xp_count': xp_count,
        'rss_count': rss_count,
    })
    return render(request, 'questlog_web/matrix_guild_dashboard.html', ctx)


# ---------------------------------------------------------------------------
# Room Management
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_rooms(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
    ctx['active_section'] = 'rooms'
    return render(request, 'questlog_web/matrix_guild_rooms.html', ctx)


# ---------------------------------------------------------------------------
# Member Management
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_members(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
    ctx['active_section'] = 'members'
    return render(request, 'questlog_web/matrix_guild_members.html', ctx)


# ---------------------------------------------------------------------------
# XP & Leveling
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_xp(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
        level_roles = db.query(WebMatrixLevelRole).filter_by(space_id=space_id).order_by(
            WebMatrixLevelRole.level).all()
        boosts = db.query(WebMatrixXpBoost).filter_by(space_id=space_id).order_by(
            WebMatrixXpBoost.ends_at.desc()).limit(20).all()

    now = int(time.time())
    ctx.update({
        'active_section': 'xp',
        'level_roles': level_roles,
        'boosts': boosts,
        'now': now,
    })
    return render(request, 'questlog_web/matrix_guild_xp.html', ctx)


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_moderation(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
        warnings = db.query(WebMatrixModWarning).filter_by(
            space_id=space_id, is_active=1).order_by(
            WebMatrixModWarning.created_at.desc()).limit(50).all()

    ctx.update({
        'active_section': 'moderation',
        'warnings': warnings,
    })
    return render(request, 'questlog_web/matrix_guild_moderation.html', ctx)


# ---------------------------------------------------------------------------
# Welcome Messages
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_welcome(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
        welcome = db.query(WebMatrixWelcomeConfig).filter_by(space_id=space_id).first()

    welcome_config_json = {}
    if welcome:
        welcome_config_json = {
            'enabled': bool(welcome.enabled),
            'welcome_room_id': welcome.welcome_room_id or '',
            'welcome_message': welcome.welcome_message or '',
            'dm_enabled': bool(welcome.dm_enabled),
            'dm_message': welcome.dm_message or '',
            'auto_invite_room_ids': json.loads(welcome.auto_invite_room_ids or '[]'),
            'goodbye_enabled': bool(welcome.goodbye_enabled),
            'goodbye_room_id': welcome.goodbye_room_id or '',
            'goodbye_message': welcome.goodbye_message or '',
        }
    wu = getattr(request, 'web_user', None)
    viewer_matrix_id = str(getattr(wu, 'matrix_id', '') or '') if wu else ''
    ctx.update({
        'active_section': 'welcome',
        'welcome_config': welcome,
        'welcome_config_json': json.dumps(welcome_config_json),
        'viewer_matrix_id': viewer_matrix_id,
    })
    return render(request, 'questlog_web/matrix_guild_welcome.html', ctx)


# ---------------------------------------------------------------------------
# Ban Lists
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_ban_lists(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
        raw_lists = db.query(WebMatrixBanList).filter_by(space_id=space_id).order_by(
            WebMatrixBanList.created_at.desc()).all()
        ban_lists = []
        for bl in raw_lists:
            entries = db.query(WebMatrixBanListEntry).filter_by(list_id=bl.id).order_by(
                WebMatrixBanListEntry.created_at.desc()).all()
            entry_dicts = []
            for e in entries:
                mid = e.target_matrix_id or ''
                server = (mid.split(':')[-1] if ':' in mid else 'unknown')[:60]
                entry_dicts.append({
                    'id': e.id,
                    'target_matrix_id': mid,
                    'target_matrix_id_server': server,
                    'reason': e.reason or '',
                    'added_by': e.added_by or '',
                    'created_at': e.created_at,
                })
            ban_lists.append({
                'id': bl.id,
                'list_name': bl.name,
                'description': bl.description or '',
                'is_subscribed': bool(bl.is_subscribed),
                'sync_paused': bool(bl.sync_paused),
                'source_room_id': bl.source_room_id or '',
                'last_synced_at': bl.last_synced_at,
                'entries': entry_dicts,
            })

    ctx.update({
        'active_section': 'ban_lists',
        'ban_lists': ban_lists,
    })
    return render(request, 'questlog_web/matrix_guild_ban_lists.html', ctx)


# ---------------------------------------------------------------------------
# RSS Feeds
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_rss(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
        feeds = db.query(WebMatrixRssFeed).filter_by(space_id=space_id).order_by(
            WebMatrixRssFeed.label).all()

    ctx.update({
        'active_section': 'rss',
        'rss_feeds': feeds,
    })
    return render(request, 'questlog_web/matrix_guild_rss.html', ctx)


# ---------------------------------------------------------------------------
# Message Tools
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_messages(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
    ctx['active_section'] = 'messages'
    return render(request, 'questlog_web/matrix_guild_messages.html', ctx)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_settings(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
    ctx['active_section'] = 'settings'
    ctx['admin_matrix_ids_list'] = ctx['settings'].get('admin_matrix_ids', [])
    return render(request, 'questlog_web/matrix_guild_settings.html', ctx)


@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_audit(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
    ctx['active_section'] = 'audit'
    # settings_json already includes audit fields from _get_space_context
    return render(request, 'questlog_web/matrix_guild_audit.html', ctx)


@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_verification(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)
    ctx['active_section'] = 'verification'
    # settings_json already includes verification fields from _get_space_context
    return render(request, 'questlog_web/matrix_guild_verification.html', ctx)


# ===========================================================================
# REST API ENDPOINTS
# ===========================================================================

# ---------------------------------------------------------------------------
# Settings API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_space_settings(request, space_id):
    with get_db_session() as db:
        s = db.query(WebMatrixSpaceSettings).filter_by(space_id=space_id).first()
        if not s:
            return JsonResponse({'error': 'Space not found'}, status=404)

        if request.method == 'GET':
            return JsonResponse({
                'settings': {
                    'xp_enabled': bool(s.xp_enabled),
                    'xp_per_message': s.xp_per_message,
                    'xp_cooldown_secs': s.xp_cooldown_secs,
                    'xp_ignored_rooms': json.loads(s.xp_ignored_rooms or '[]'),
                    'level_up_enabled': bool(s.level_up_enabled),
                    'level_up_room_id': s.level_up_room_id or '',
                    'level_up_message': s.level_up_message or '',
                    'mod_log_room_id': s.mod_log_room_id or '',
                    'warn_threshold': s.warn_threshold,
                    'auto_ban_after_warns': bool(s.auto_ban_after_warns),
                    'admin_power_level': s.admin_power_level,
                    'admin_matrix_ids': json.loads(s.admin_matrix_ids or '[]'),
                    'bot_prefix': s.bot_prefix or '!',
                    'language': s.language or 'en',
                    'timezone': s.timezone or 'UTC',
                }
            })

        # POST - partial update
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        now = int(time.time())
        bool_fields = ['xp_enabled', 'level_up_enabled', 'auto_ban_after_warns',
                       'audit_log_enabled']
        int_fields = {'xp_per_message': (1, 100), 'xp_cooldown_secs': (0, 3600),
                      'warn_threshold': (1, 20), 'admin_power_level': (1, 100),
                      'verification_account_age_days': (1, 365)}
        str_fields = {'level_up_room_id': 255, 'level_up_message': 500,
                      'mod_log_room_id': 255, 'bot_prefix': 10,
                      'language': 10, 'timezone': 50,
                      'space_name': 200, 'space_avatar_url': 500,
                      'owner_matrix_id': 100,
                      'audit_log_room_id': 255,
                      'verification_type': 20,
                      'verification_room_id': 255,
                      'verification_verified_message': 500,
                      'verification_failed_message': 500}

        for f in bool_fields:
            if f in data and hasattr(s, f):
                setattr(s, f, 1 if data[f] else 0)
        for f, (mn, mx) in int_fields.items():
            if f in data and hasattr(s, f):
                setattr(s, f, max(mn, min(mx, int(data[f] or mn))))
        for f, maxlen in str_fields.items():
            if f in data and hasattr(s, f):
                setattr(s, f, str(data[f] or '')[:maxlen] or None)
        if 'xp_ignored_rooms' in data:
            rooms_list = [r for r in (data['xp_ignored_rooms'] or []) if _valid_room_id(str(r))]
            s.xp_ignored_rooms = json.dumps(rooms_list)
        if 'admin_matrix_ids' in data:
            ids = [str(i) for i in (data['admin_matrix_ids'] or []) if _valid_matrix_id(str(i))]
            s.admin_matrix_ids = json.dumps(ids)
        if 'audit_event_config' in data and hasattr(s, 'audit_event_config'):
            cfg = data['audit_event_config']
            if isinstance(cfg, dict):
                s.audit_event_config = json.dumps({str(k): bool(v) for k, v in cfg.items()})

        s.updated_at = now
        db.commit()
        return JsonResponse({'ok': True})


@matrix_space_required
@require_http_methods(['POST'])
def api_matrix_propagate_audit(request, space_id):
    """Copy audit settings from this space to all other spaces the user owns/admins."""
    web_user = getattr(request, 'web_user', None)
    user_matrix_id = str(getattr(web_user, 'matrix_id', None) or '') if web_user else ''

    with get_db_session() as db:
        source = db.query(WebMatrixSpaceSettings).filter_by(space_id=space_id).first()
        if not source:
            return JsonResponse({'error': 'Space not found'}, status=404)

        # Find all other spaces this user has access to
        if request.user.is_superuser:
            targets = db.query(WebMatrixSpaceSettings).filter(
                WebMatrixSpaceSettings.space_id != space_id,
                WebMatrixSpaceSettings.bot_present == 1
            ).all()
        elif user_matrix_id:
            targets = db.query(WebMatrixSpaceSettings).filter(
                WebMatrixSpaceSettings.space_id != space_id,
                WebMatrixSpaceSettings.bot_present == 1,
                sa_text(
                    "owner_matrix_id=:mid OR JSON_CONTAINS(IFNULL(admin_matrix_ids,'[]'), JSON_QUOTE(:mid))"
                ).bindparams(mid=user_matrix_id)
            ).all()
        else:
            targets = []

        now = int(time.time())
        count = 0
        for t in targets:
            t.audit_log_enabled = source.audit_log_enabled
            t.audit_event_config = source.audit_event_config
            t.audit_log_room_id = source.audit_log_room_id
            t.updated_at = now
            count += 1
        db.commit()

    return JsonResponse({'ok': True, 'updated': count})


# ---------------------------------------------------------------------------
# Rooms API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET'])
def api_matrix_rooms(request, space_id):
    with get_db_session() as db:
        rooms = db.query(WebMatrixRoom).filter_by(space_id=space_id).order_by(WebMatrixRoom.room_name).all()
        return JsonResponse({
            'rooms': [
                {
                    'room_id': r.room_id,
                    'room_name': r.room_name or r.room_id,
                    'room_alias': r.room_alias or '',
                    'topic': r.topic or '',
                    'is_encrypted': bool(r.is_encrypted),
                    'member_count': r.member_count,
                    'last_synced_at': r.last_synced_at,
                }
                for r in rooms
            ]
        })


@matrix_space_required
@require_http_methods(['POST'])
def api_matrix_room_create(request, space_id):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = sanitize_text(str(data.get('name', '') or '').strip())[:100]
    if not name:
        return JsonResponse({'error': 'Room name required'}, status=400)

    with get_db_session() as db:
        action_id = _queue_action(space_id, 'create_room', {
            'name': name,
            'topic': sanitize_text(str(data.get('topic', '') or '').strip())[:500],
            'encrypted': bool(data.get('encrypted', False)),
        }, db)

    return JsonResponse({'ok': True, 'action_id': action_id,
                         'message': 'Room creation queued. It will appear shortly.'})


@matrix_space_required
@require_http_methods(['PATCH', 'DELETE'])
def api_matrix_room_detail(request, space_id, room_id):
    room_id = urllib.parse.unquote(room_id)

    with get_db_session() as db:
        room = db.query(WebMatrixRoom).filter_by(space_id=space_id, room_id=room_id).first()
        if not room:
            return JsonResponse({'error': 'Room not found'}, status=404)

        if request.method == 'DELETE':
            action_id = _queue_action(space_id, 'delete_room', {'room_id': room_id}, db)
            return JsonResponse({'ok': True, 'action_id': action_id})

        # PATCH
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        action_id = None
        if 'topic' in data:
            action_id = _queue_action(space_id, 'set_room_topic', {
                'room_id': room_id,
                'topic': sanitize_text(str(data['topic'] or '').strip())[:1000],
            }, db)
        if 'name' in data:
            action_id = _queue_action(space_id, 'set_room_name', {
                'room_id': room_id,
                'name': sanitize_text(str(data['name'] or '').strip())[:100],
            }, db)

        return JsonResponse({'ok': True, 'action_id': action_id})


# ---------------------------------------------------------------------------
# Members API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET'])
def api_matrix_members(request, space_id):
    page = safe_int(request.GET.get('page', 1), 1, 1, 9999)
    # Support both ?search= and ?q= for compatibility
    search_raw = request.GET.get('search', '') or request.GET.get('q', '') or ''
    search = sanitize_text(str(search_raw).strip())[:100]
    per_page = safe_int(request.GET.get('per_page', 50), 50, 1, 500)
    room_id_raw = request.GET.get('room_id', '').strip()
    room_id = room_id_raw if room_id_raw.startswith('!') else None
    live_all = request.GET.get('live', '') == '1'

    # live=1: fetch all rooms across this space AND all sub-spaces from DB,
    # call Matrix live for each, deduplicate members and return a single distinct list.
    if live_all:
        with get_db_session() as db:
            # Collect all space IDs: the requested space + any sub-spaces whose space_id
            # appears as a child room_id of this space (spaces-within-spaces).
            child_space_ids = db.execute(
                sa_text(
                    "SELECT r.room_id FROM web_matrix_rooms r "
                    "INNER JOIN web_matrix_space_settings s ON s.space_id = r.room_id "
                    "WHERE r.space_id=:s"
                ),
                {'s': space_id}
            ).fetchall()
            all_space_ids = [space_id] + [r[0] for r in child_space_ids]

            placeholders = ','.join(f':s{i}' for i in range(len(all_space_ids)))
            params = {f's{i}': sid for i, sid in enumerate(all_space_ids)}
            room_rows = db.execute(
                sa_text(f"SELECT room_id, room_name, power_levels_json, space_id FROM web_matrix_rooms WHERE space_id IN ({placeholders})"),
                params
            ).fetchall()

        # Filter out:
        # - rows where room_id is itself a space (sub-space entries, not chat rooms)
        # - rows where room_name is null/empty or equals room_id (bot was never in the room, will 403)
        space_id_set = set(all_space_ids)
        room_rows = [
            r for r in room_rows
            if r[0] not in space_id_set
            and r[1]  # has a name
            and r[1] != r[0]  # name is not the same as room_id (unsynced/inaccessible rooms)
        ]

        seen: dict[str, dict] = {}  # matrix_id -> member dict
        for rrow in room_rows:
            r_id, r_name, r_pl_json = rrow[0], rrow[1], rrow[2]
            # Skip if room_id is a known space (avoid calling joined_members on a space)
            if r_id in space_id_set:
                continue
            live = _fetch_room_members_live(r_id)
            if not live:
                continue
            # Parse power levels for this room
            power_levels: dict[str, int] = {}
            default_pl = 0
            if r_pl_json:
                try:
                    pl_data = json.loads(r_pl_json)
                    default_pl = int(pl_data.get('users_default', 0))
                    for uid, pl in pl_data.get('users', {}).items():
                        power_levels[uid] = int(pl)
                except Exception:
                    pass
            for m in live:
                mid = m['matrix_id']
                if mid not in seen:
                    seen[mid] = {
                        'matrix_id': mid,
                        'display_name': m['display_name'],
                        'avatar_url': m['avatar_url'],
                        'power_level': power_levels.get(mid, default_pl),
                        'joined_at': None,
                        'web_user_id': None,
                        'rooms': [r_name or r_id],
                    }
                else:
                    seen[mid]['rooms'].append(r_name or r_id)
                    # Take highest power level across rooms
                    seen[mid]['power_level'] = max(seen[mid]['power_level'], power_levels.get(mid, default_pl))

        all_members = sorted(seen.values(), key=lambda m: m['display_name'].lower())
        if search:
            sq = search.lower()
            all_members = [m for m in all_members if sq in m['matrix_id'].lower() or sq in m['display_name'].lower()]

        total = len(all_members)
        offset = (page - 1) * per_page
        return JsonResponse({
            'members': all_members[offset:offset + per_page],
            'total': total,
            'page': page,
            'pages': max(1, (total + per_page - 1) // per_page),
        })

    if room_id:
        # Fetch live from Matrix API - always accurate, 60s cache
        live = _fetch_room_members_live(room_id)
        if live is None:
            return JsonResponse({'error': 'Could not reach Matrix server'}, status=502)

        # Enrich with power levels from DB (stored in web_matrix_rooms.power_levels_json)
        power_levels: dict[str, int] = {}
        default_pl = 0
        with get_db_session() as db:
            room_row = db.execute(
                sa_text("SELECT power_levels_json FROM web_matrix_rooms WHERE room_id=:r"),
                {'r': room_id}
            ).fetchone()
            if room_row and room_row[0]:
                try:
                    pl_data = json.loads(room_row[0])
                    default_pl = int(pl_data.get('users_default', 0))
                    for uid, pl in pl_data.get('users', {}).items():
                        power_levels[uid] = int(pl)
                except Exception:
                    pass

        if search:
            sq = search.lower()
            live = [m for m in live if sq in m['matrix_id'].lower() or sq in m['display_name'].lower()]

        total = len(live)
        offset = (page - 1) * per_page
        page_members = live[offset:offset + per_page]
        members = [
            {
                'matrix_id': m['matrix_id'],
                'display_name': m['display_name'],
                'avatar_url': m['avatar_url'],
                'power_level': power_levels.get(m['matrix_id'], default_pl),
                'joined_at': None,
                'web_user_id': None,
            }
            for m in page_members
        ]
    else:
        with get_db_session() as db:
            q = db.query(WebMatrixMember).filter_by(space_id=space_id).filter(
                WebMatrixMember.left_at == None  # noqa: E711
            )
            if search:
                q = q.filter(
                    sa_text("(matrix_id LIKE :s OR display_name LIKE :s)").bindparams(s=f'%{search}%')
                )
            total = q.count()
            rows_orm = q.order_by(WebMatrixMember.display_name).offset((page - 1) * per_page).limit(per_page).all()
            members = [
                {
                    'matrix_id': m.matrix_id,
                    'display_name': m.display_name or m.matrix_id,
                    'avatar_url': m.avatar_url or '',
                    'power_level': m.power_level,
                    'joined_at': m.joined_at,
                    'web_user_id': m.web_user_id,
                }
                for m in rows_orm
            ]

    return JsonResponse({
        'members': members,
        'total': total,
        'page': page,
        'pages': max(1, (total + per_page - 1) // per_page),
    })


@matrix_space_required
@require_http_methods(['POST'])
def api_matrix_member_kick(request, space_id):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Accept both 'user_id' and 'matrix_id' field names
    user_id = str(data.get('user_id', '') or data.get('matrix_id', '') or '').strip()
    if not _valid_matrix_id(user_id):
        return JsonResponse({'error': 'Invalid Matrix user ID'}, status=400)

    room_id = str(data.get('room_id', '') or '').strip()
    all_rooms = bool(data.get('all_rooms', False))
    reason = sanitize_text(str(data.get('reason', '') or '').strip())[:500]

    with get_db_session() as db:
        if all_rooms or not room_id:
            action_id = _queue_action(space_id, 'kick_all_rooms', {
                'space_id': space_id, 'user_id': user_id, 'reason': reason
            }, db)
        else:
            action_id = _queue_action(space_id, 'kick_user', {
                'room_id': room_id, 'user_id': user_id, 'reason': reason
            }, db)

    # Invalidate live member cache so next panel load reflects the change
    _room_members_cache.pop(room_id, None)
    return JsonResponse({'ok': True, 'action_id': action_id})


@matrix_space_required
@require_http_methods(['POST'])
def api_matrix_member_ban(request, space_id):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Accept both 'user_id' and 'matrix_id' field names
    user_id = str(data.get('user_id', '') or data.get('matrix_id', '') or '').strip()
    if not _valid_matrix_id(user_id):
        return JsonResponse({'error': 'Invalid Matrix user ID'}, status=400)

    room_id = str(data.get('room_id', '') or '').strip()
    all_rooms = bool(data.get('all_rooms', False))
    reason = sanitize_text(str(data.get('reason', '') or '').strip())[:500]
    unban = bool(data.get('unban', False))

    with get_db_session() as db:
        if unban:
            if not room_id:
                return JsonResponse({'error': 'room_id required for unban'}, status=400)
            action_id = _queue_action(space_id, 'unban_user', {
                'room_id': room_id, 'user_id': user_id
            }, db)
        elif all_rooms or not room_id:
            action_id = _queue_action(space_id, 'ban_all_rooms', {
                'space_id': space_id, 'user_id': user_id, 'reason': reason
            }, db)
        else:
            action_id = _queue_action(space_id, 'ban_user', {
                'room_id': room_id, 'user_id': user_id, 'reason': reason
            }, db)

    # Invalidate live member cache so next panel load reflects the change
    _room_members_cache.pop(room_id, None)
    return JsonResponse({'ok': True, 'action_id': action_id})


@matrix_space_required
@require_http_methods(['POST'])
def api_matrix_member_invite(request, space_id):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = str(data.get('user_id', '') or '').strip()
    room_id = str(data.get('room_id', '') or '').strip()
    if not _valid_matrix_id(user_id):
        return JsonResponse({'error': 'Invalid Matrix user ID'}, status=400)
    if not _valid_room_id(room_id):
        return JsonResponse({'error': 'Invalid room ID'}, status=400)

    with get_db_session() as db:
        action_id = _queue_action(space_id, 'invite_user', {
            'room_id': room_id, 'user_id': user_id,
        }, db)

    _room_members_cache.pop(room_id, None)
    return JsonResponse({'ok': True, 'action_id': action_id})


@matrix_space_required
@require_http_methods(['POST'])
def api_matrix_member_powerlevel(request, space_id):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = str(data.get('user_id', '') or '').strip()
    room_id = str(data.get('room_id', '') or '').strip()
    if not _valid_matrix_id(user_id) or not _valid_room_id(room_id):
        return JsonResponse({'error': 'Invalid user_id or room_id'}, status=400)
    level = safe_int(data.get('level', 0), 0, -1, 100)

    with get_db_session() as db:
        action_id = _queue_action(space_id, 'set_power_level', {
            'room_id': room_id, 'user_id': user_id, 'level': level
        }, db)

    return JsonResponse({'ok': True, 'action_id': action_id})


# ---------------------------------------------------------------------------
# Moderation Warnings API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_warnings(request, space_id):
    with get_db_session() as db:
        if request.method == 'GET':
            target = sanitize_text(request.GET.get('user_id', '') or '')[:100]
            q = db.query(WebMatrixModWarning).filter_by(space_id=space_id)
            if target:
                q = q.filter_by(target_matrix_id=target)
            warnings = q.order_by(WebMatrixModWarning.created_at.desc()).limit(100).all()
            return JsonResponse({
                'warnings': [
                    {
                        'id': w.id,
                        'target_matrix_id': w.target_matrix_id,
                        'moderator_matrix_id': w.moderator_matrix_id,
                        'reason': w.reason,
                        'room_id': w.room_id or '',
                        'is_active': bool(w.is_active),
                        'created_at': w.created_at,
                    }
                    for w in warnings
                ]
            })

        # POST - issue warning via action queue
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        target = str(data.get('target_matrix_id', '') or '').strip()
        reason = sanitize_text(str(data.get('reason', '') or '').strip())[:500]
        room_id = str(data.get('room_id', '') or '').strip()

        if not _valid_matrix_id(target):
            return JsonResponse({'error': 'Invalid target Matrix ID'}, status=400)
        if not reason:
            return JsonResponse({'error': 'Reason required'}, status=400)

        web_user = getattr(request, 'web_user', None)
        moderator = str(getattr(web_user, 'matrix_id', '') or 'web-dashboard')

        now = int(time.time())
        w = WebMatrixModWarning(
            space_id=space_id,
            target_matrix_id=target,
            moderator_matrix_id=moderator,
            reason=reason,
            room_id=room_id or None,
            is_active=1,
            created_at=now,
        )
        db.add(w)
        db.commit()
        db.refresh(w)
        return JsonResponse({'ok': True, 'warning_id': w.id})


@matrix_space_required
@require_http_methods(['POST'])
def api_matrix_warning_pardon(request, space_id, warning_id):
    web_user = getattr(request, 'web_user', None)
    moderator = str(getattr(web_user, 'matrix_id', '') or 'web-dashboard')
    now = int(time.time())

    with get_db_session() as db:
        w = db.query(WebMatrixModWarning).filter_by(id=warning_id, space_id=space_id).first()
        if not w:
            return JsonResponse({'error': 'Not found'}, status=404)
        w.is_active = 0
        w.pardoned_by = moderator
        w.pardoned_at = now
        db.commit()

    return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Welcome Config API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_welcome_config(request, space_id):
    with get_db_session() as db:
        cfg = db.query(WebMatrixWelcomeConfig).filter_by(space_id=space_id).first()

        if request.method == 'GET':
            if not cfg:
                return JsonResponse({'config': None})
            return JsonResponse({
                'config': {
                    'enabled': bool(cfg.enabled),
                    'welcome_room_id': cfg.welcome_room_id or '',
                    'welcome_message': cfg.welcome_message or '',
                    'welcome_embed_enabled': bool(cfg.welcome_embed_enabled),
                    'welcome_embed_title': cfg.welcome_embed_title or '',
                    'welcome_embed_color': cfg.welcome_embed_color or '',
                    'dm_enabled': bool(cfg.dm_enabled),
                    'dm_message': cfg.dm_message or '',
                    'goodbye_enabled': bool(cfg.goodbye_enabled),
                    'goodbye_room_id': cfg.goodbye_room_id or '',
                    'goodbye_message': cfg.goodbye_message or '',
                    'auto_invite_room_ids': json.loads(cfg.auto_invite_room_ids or '[]'),
                }
            })

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if not cfg:
            cfg = WebMatrixWelcomeConfig(space_id=space_id, updated_at=int(time.time()))
            db.add(cfg)

        str_fields = {
            'welcome_room_id': 255, 'welcome_message': 2000,
            'welcome_embed_title': 200, 'welcome_embed_color': 10,
            'dm_message': 2000, 'goodbye_room_id': 255, 'goodbye_message': 2000,
        }
        bool_fields = ['enabled', 'welcome_embed_enabled', 'dm_enabled', 'goodbye_enabled']

        for f in bool_fields:
            if f in data:
                setattr(cfg, f, 1 if data[f] else 0)
        for f, maxlen in str_fields.items():
            if f in data:
                setattr(cfg, f, sanitize_text(str(data[f] or ''))[:maxlen] or None)
        if 'auto_invite_room_ids' in data:
            valid_rooms = [str(r) for r in (data['auto_invite_room_ids'] or []) if _valid_room_id(str(r))]
            cfg.auto_invite_room_ids = json.dumps(valid_rooms)

        cfg.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# XP Settings API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_xp_settings(request, space_id):
    """Alias to api_matrix_space_settings but only XP fields."""
    return api_matrix_space_settings(request, space_id)


@matrix_space_required
@require_http_methods(['GET'])
def api_matrix_xp_leaderboard(request, space_id):
    page = safe_int(request.GET.get('page', 1), 1, 1, 9999)
    per_page = 25
    with get_db_session() as db:
        total = db.query(WebMatrixXpEvent).filter_by(space_id=space_id).count()
        rows = db.query(WebMatrixXpEvent).filter_by(space_id=space_id).order_by(
            WebMatrixXpEvent.xp.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return JsonResponse({
        'leaderboard': [
            {'matrix_id': r.matrix_id, 'xp': r.xp, 'level': r.level, 'rank': (page - 1) * per_page + i + 1}
            for i, r in enumerate(rows)
        ],
        'total': total,
        'page': page,
    })


@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_xp_boosts(request, space_id):
    with get_db_session() as db:
        if request.method == 'GET':
            boosts = db.query(WebMatrixXpBoost).filter_by(space_id=space_id).order_by(
                WebMatrixXpBoost.ends_at.desc()).all()
            return JsonResponse({
                'boosts': [
                    {'id': b.id, 'label': b.label, 'multiplier': b.multiplier,
                     'starts_at': b.starts_at, 'ends_at': b.ends_at}
                    for b in boosts
                ]
            })
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        label = sanitize_text(str(data.get('label', '') or '').strip())[:100]
        multiplier = max(1.1, min(10.0, float(data.get('multiplier', 2.0) or 2.0)))
        now = int(time.time())
        starts_at = safe_int(data.get('starts_at', now), now)
        # Support 'hours' shorthand from templates
        hours = safe_int(data.get('hours', 0), 0, 0, 8760)
        if hours:
            ends_at = starts_at + hours * 3600
        else:
            ends_at = safe_int(data.get('ends_at', starts_at + 3600), starts_at + 3600)
        if ends_at <= starts_at:
            return JsonResponse({'error': 'ends_at must be after starts_at'}, status=400)

        boost = WebMatrixXpBoost(
            space_id=space_id, label=label, multiplier=multiplier,
            starts_at=starts_at, ends_at=ends_at, created_at=int(time.time())
        )
        db.add(boost)
        db.commit()
        db.refresh(boost)
        return JsonResponse({'ok': True, 'boost_id': boost.id})


@matrix_space_required
@require_http_methods(['DELETE'])
def api_matrix_xp_boost_detail(request, space_id, boost_id):
    with get_db_session() as db:
        b = db.query(WebMatrixXpBoost).filter_by(id=boost_id, space_id=space_id).first()
        if not b:
            return JsonResponse({'error': 'Not found'}, status=404)
        db.delete(b)
        db.commit()
    return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# RSS Feeds API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_rss(request, space_id):
    with get_db_session() as db:
        if request.method == 'GET':
            feeds = db.query(WebMatrixRssFeed).filter_by(space_id=space_id).order_by(
                WebMatrixRssFeed.label).all()
            return JsonResponse({
                'feeds': [
                    {
                        'id': f.id,
                        'url': f.url,
                        'label': f.label or '',
                        'room_id': f.room_id,
                        'room_name': f.room_name or '',
                        'ping_matrix_id': f.ping_matrix_id or '',
                        'poll_interval_minutes': f.poll_interval_minutes,
                        'enabled': bool(f.enabled),
                        'last_checked_at': f.last_checked_at,
                        'consecutive_failures': f.consecutive_failures,
                        'last_error': f.last_error or '',
                    }
                    for f in feeds
                ]
            })

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        url = str(data.get('url', '') or '').strip()[:500]
        room_id = str(data.get('room_id', '') or '').strip()
        if not url or not url.startswith('http'):
            return JsonResponse({'error': 'Valid URL required'}, status=400)
        if not _valid_room_id(room_id):
            return JsonResponse({'error': 'Valid room_id required'}, status=400)

        existing = db.query(WebMatrixRssFeed).filter_by(space_id=space_id, url=url).first()
        if existing:
            return JsonResponse({'error': 'Feed already exists for this URL'}, status=400)

        ping_id = str(data.get('ping_matrix_id', '') or '').strip()[:100]
        if ping_id and not _valid_matrix_id(ping_id):
            ping_id = ''

        # Accept both 'name' (templates) and 'label' (API)
        label = sanitize_text(str(data.get('name', '') or data.get('label', '') or '').strip())[:200] or None
        # Accept 'interval' (minutes, templates) or 'poll_interval_minutes' (API)
        interval = safe_int(data.get('interval', data.get('poll_interval_minutes', 60)), 60, 5, 1440)
        # Accept 'max_age_hours' (templates) or 'max_age_days' (API)
        max_age_hours = safe_int(data.get('max_age_hours', 0), 0, 0, 8760)
        max_age_days = safe_int(data.get('max_age_days', 0), 0, 0, 365)
        if max_age_hours and not max_age_days:
            max_age_days = max(1, max_age_hours // 24) if max_age_hours else None
        elif not max_age_days:
            max_age_days = None

        feed = WebMatrixRssFeed(
            space_id=space_id,
            url=url,
            label=label,
            room_id=room_id,
            room_name=sanitize_text(str(data.get('room_name', '') or '').strip())[:100] or None,
            ping_matrix_id=ping_id or None,
            poll_interval_minutes=interval,
            max_age_days=max_age_days,
            enabled=1,
            created_at=int(time.time()),
        )
        db.add(feed)
        db.commit()
        db.refresh(feed)
        return JsonResponse({'ok': True, 'feed_id': feed.id}, status=201)


@matrix_space_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def api_matrix_rss_detail(request, space_id, feed_id):
    with get_db_session() as db:
        feed = db.query(WebMatrixRssFeed).filter_by(id=feed_id, space_id=space_id).first()
        if not feed:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.delete(feed)
            db.commit()
            return JsonResponse({'ok': True})

        if request.method == 'GET':
            return JsonResponse({'feed': {
                'id': feed.id, 'url': feed.url, 'label': feed.label or '',
                'room_id': feed.room_id, 'room_name': feed.room_name or '',
                'ping_matrix_id': feed.ping_matrix_id or '',
                'poll_interval_minutes': feed.poll_interval_minutes,
                'max_age_days': feed.max_age_days,
                'enabled': bool(feed.enabled),
            }})

        # PATCH
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Accept 'name' (templates) or 'label' (API)
        if 'name' in data or 'label' in data:
            feed.label = sanitize_text(str(data.get('name', '') or data.get('label', '') or '').strip())[:200] or None
        if 'url' in data:
            new_url = str(data['url'] or '').strip()[:500]
            if new_url and new_url.startswith('http'):
                feed.url = new_url
        if 'room_id' in data and _valid_room_id(str(data['room_id'])):
            feed.room_id = str(data['room_id'])[:255]
        if 'ping_matrix_id' in data:
            pid = str(data['ping_matrix_id'] or '').strip()
            feed.ping_matrix_id = pid[:100] if (pid and _valid_matrix_id(pid)) else None
        # Accept 'interval' (templates) or 'poll_interval_minutes' (API)
        if 'interval' in data or 'poll_interval_minutes' in data:
            feed.poll_interval_minutes = safe_int(
                data.get('interval', data.get('poll_interval_minutes', 60)), 60, 5, 1440)
        if 'enabled' in data:
            feed.enabled = 1 if data['enabled'] else 0
        db.commit()
        return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Ban Lists API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_ban_lists(request, space_id):
    with get_db_session() as db:
        if request.method == 'GET':
            lists = db.query(WebMatrixBanList).filter_by(space_id=space_id).all()
            result = []
            for bl in lists:
                entries = db.query(WebMatrixBanListEntry).filter_by(list_id=bl.id).count()
                result.append({
                    'id': bl.id, 'name': bl.name, 'description': bl.description or '',
                    'is_subscribed': bool(bl.is_subscribed),
                    'source_room_id': bl.source_room_id or '',
                    'entry_count': entries,
                    'last_synced_at': bl.last_synced_at,
                })
            return JsonResponse({'ban_lists': result})

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        name = sanitize_text(str(data.get('name', '') or '').strip())[:200]
        if not name:
            return JsonResponse({'error': 'Name required'}, status=400)

        source_room_id = str(data.get('source_room_id', '') or '').strip()[:255] or None
        is_subscribed = 1 if (data.get('is_subscribed') and source_room_id) else 0
        bl = WebMatrixBanList(
            space_id=space_id,
            name=name,
            description=sanitize_text(str(data.get('description', '') or '').strip())[:1000] or None,
            is_subscribed=is_subscribed,
            source_room_id=source_room_id,
            created_at=int(time.time()),
        )
        db.add(bl)
        db.commit()
        db.refresh(bl)
        return JsonResponse({'ok': True, 'list_id': bl.id}, status=201)


@matrix_space_required
@require_http_methods(['GET', 'POST', 'DELETE'])
def api_matrix_ban_list_entries(request, space_id, list_id):
    with get_db_session() as db:
        bl = db.query(WebMatrixBanList).filter_by(id=list_id, space_id=space_id).first()
        if not bl:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'GET':
            entries = db.query(WebMatrixBanListEntry).filter_by(list_id=list_id).order_by(
                WebMatrixBanListEntry.created_at.desc()).all()
            return JsonResponse({
                'entries': [
                    {'id': e.id, 'target_matrix_id': e.target_matrix_id,
                     'reason': e.reason or '', 'added_by': e.added_by or '',
                     'created_at': e.created_at}
                    for e in entries
                ]
            })

        if request.method == 'DELETE':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, AttributeError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            target = str(data.get('target_matrix_id', '') or '').strip()
            db.query(WebMatrixBanListEntry).filter_by(list_id=list_id, target_matrix_id=target).delete()
            db.commit()
            return JsonResponse({'ok': True})

        # POST - add entry
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Accept 'matrix_id' (templates) or 'target_matrix_id' (API)
        target = str(data.get('matrix_id', '') or data.get('target_matrix_id', '') or '').strip()
        if not _valid_matrix_id(target):
            return JsonResponse({'error': 'Invalid Matrix user ID'}, status=400)

        web_user = getattr(request, 'web_user', None)
        added_by = str(getattr(web_user, 'matrix_id', '') or 'web-dashboard')

        entry = WebMatrixBanListEntry(
            list_id=list_id,
            target_matrix_id=target,
            reason=sanitize_text(str(data.get('reason', '') or '').strip())[:500] or None,
            added_by=added_by,
            created_at=int(time.time()),
        )
        db.add(entry)
        db.commit()

        # Queue ban_all_rooms action only if ban_now=True
        if data.get('ban_now', False):
            _queue_action(space_id, 'ban_all_rooms', {
                'space_id': space_id,
                'user_id': target,
                'reason': f"Ban list: {bl.name}",
            }, db)

        return JsonResponse({'ok': True}, status=201)


# ---------------------------------------------------------------------------
# Message Send API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['POST'])
def api_matrix_send_message(request, space_id):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    room_id = str(data.get('room_id', '') or '').strip()
    matrix_id = str(data.get('matrix_id', '') or '').strip()
    # Accept 'content' (templates) or legacy 'body'
    body = sanitize_text(str(data.get('content', '') or data.get('body', '') or '').strip())[:4000]
    is_dm = bool(data.get('is_dm', False))
    broadcast_all = bool(data.get('broadcast_all', False))
    as_html = bool(data.get('as_html', False) or data.get('html', False))

    if not body:
        return JsonResponse({'error': 'Message required'}, status=400)

    with get_db_session() as db:
        if is_dm:
            if not _valid_matrix_id(matrix_id):
                return JsonResponse({'error': 'Valid Matrix ID required for DM'}, status=400)
            action_id = _queue_action(space_id, 'send_dm', {
                'target_matrix_id': matrix_id, 'body': body,
            }, db)
        elif broadcast_all:
            # Queue send_message for each room
            rooms = db.query(WebMatrixRoom).filter_by(space_id=space_id).all()
            for r in rooms:
                _queue_action(space_id, 'send_message', {
                    'room_id': r.room_id, 'body': body, 'html': body if as_html else '',
                }, db)
            action_id = len(rooms)
        else:
            if not _valid_room_id(room_id):
                return JsonResponse({'error': 'Valid room_id required'}, status=400)
            action_id = _queue_action(space_id, 'send_message', {
                'room_id': room_id, 'body': body, 'html': body if as_html else '',
            }, db)

    return JsonResponse({'ok': True, 'action_id': action_id})


# ---------------------------------------------------------------------------
# Sync Status API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_sync_status(request, space_id):
    with get_db_session() as db:
        s = db.query(WebMatrixSpaceSettings).filter_by(space_id=space_id).first()
        room_count = db.query(WebMatrixRoom).filter_by(space_id=space_id).count()
        member_count = db.query(WebMatrixMember).filter_by(space_id=space_id).filter(
            WebMatrixMember.left_at == None  # noqa: E711
        ).count()
        pending_actions = db.query(WebMatrixGuildAction).filter_by(
            space_id=space_id, status='pending').count()

    if request.method == 'POST':
        # Queue a sync action
        with get_db_session() as db:
            _queue_action(space_id, 'sync_space', {}, db)
        return JsonResponse({'ok': True, 'queued': True})

    return JsonResponse({
        'bot_present': bool(s.bot_present) if s else False,
        'room_count': room_count,
        'member_count': member_count,
        'pending_actions': pending_actions,
        'space_name': s.space_name if s else '',
    })


# ---------------------------------------------------------------------------
# Missing stub views needed by urls.py
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_level_roles(request, space_id):
    with get_db_session() as db:
        if request.method == 'GET':
            roles = db.query(WebMatrixLevelRole).filter_by(space_id=space_id).order_by(
                WebMatrixLevelRole.level).all()
            return JsonResponse({
                'level_roles': [
                    {'id': r.id, 'level': r.level, 'power_level': r.power_level,
                     'label': r.label or ''}
                    for r in roles
                ]
            })
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        level = safe_int(data.get('level'), 0, 1, 999)
        power_level = safe_int(data.get('power_level'), 0, 0, 100)
        label = str(data.get('label', '') or '').strip()[:100] or None
        if not level:
            return JsonResponse({'error': 'level required'}, status=400)
        lr = WebMatrixLevelRole(
            space_id=space_id, level=level, power_level=power_level,
            label=label, created_at=int(time.time())
        )
        db.add(lr)
        db.commit()
        db.refresh(lr)
        return JsonResponse({'ok': True, 'id': lr.id}, status=201)


@matrix_space_required
@require_http_methods(['DELETE'])
def api_matrix_level_role_detail(request, space_id, role_id):
    with get_db_session() as db:
        lr = db.query(WebMatrixLevelRole).filter_by(id=role_id, space_id=space_id).first()
        if not lr:
            return JsonResponse({'error': 'Not found'}, status=404)
        db.delete(lr)
        db.commit()
    return JsonResponse({'ok': True})


@matrix_space_required
@require_http_methods(['PATCH', 'DELETE'])
def api_matrix_ban_list_detail(request, space_id, list_id):
    with get_db_session() as db:
        bl = db.query(WebMatrixBanList).filter_by(id=list_id, space_id=space_id).first()
        if not bl:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.query(WebMatrixBanListEntry).filter_by(list_id=list_id).delete()
            db.delete(bl)
            db.commit()
            return JsonResponse({'ok': True})

        # PATCH - update subscription settings
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'source_room_id' in data:
            source = str(data['source_room_id'] or '').strip()[:255]
            bl.source_room_id = source or None
            bl.is_subscribed = 1 if source else 0
            bl.last_synced_at = None
        if 'name' in data:
            bl.name = sanitize_text(str(data['name'] or '').strip())[:200] or bl.name
        if 'description' in data:
            bl.description = sanitize_text(str(data['description'] or '').strip())[:1000] or None
        if 'sync_paused' in data:
            bl.sync_paused = 1 if data['sync_paused'] else 0

        db.commit()
        return JsonResponse({'ok': True, 'sync_paused': bool(bl.sync_paused)})


@matrix_space_required
@require_http_methods(['DELETE'])
def api_matrix_ban_list_entry_detail(request, space_id, entry_id):
    with get_db_session() as db:
        entry = db.query(WebMatrixBanListEntry).filter_by(id=entry_id).first()
        if not entry:
            return JsonResponse({'error': 'Not found'}, status=404)
        # Verify entry belongs to this space via the ban list
        bl = db.query(WebMatrixBanList).filter_by(id=entry.list_id, space_id=space_id).first()
        if not bl:
            return JsonResponse({'error': 'Not found'}, status=404)
        db.delete(entry)
        db.commit()
    return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Action History API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET'])
def api_matrix_action_history(request, space_id):
    """Return recent actions for this space so the dashboard can show kick/ban results."""
    limit = safe_int(request.GET.get('limit', 50), 50, 1, 200)
    with get_db_session() as db:
        rows = db.execute(
            sa_text(
                "SELECT a.id, a.action_type, a.payload_json, a.status, a.result_json, a.created_at, a.processed_at, "
                "r.room_name "
                "FROM web_matrix_guild_actions a "
                "LEFT JOIN web_matrix_rooms r ON r.room_id = JSON_UNQUOTE(JSON_EXTRACT(a.payload_json, '$.room_id')) "
                "WHERE a.space_id=:s ORDER BY a.created_at DESC LIMIT :lim"
            ),
            {'s': space_id, 'lim': limit}
        ).fetchall()

    actions = []
    for row in rows:
        try:
            payload = json.loads(row[2] or '{}')
        except Exception:
            payload = {}
        try:
            result = json.loads(row[4] or '{}')
        except Exception:
            result = {}
        room_id = payload.get('room_id', '')
        room_name = row[7] or room_id  # fall back to ID if name not in DB
        actions.append({
            'id': row[0],
            'action_type': row[1],
            'user_id': payload.get('user_id', ''),
            'room_id': room_id,
            'room_name': room_name,
            'status': row[3],
            'result': result,
            'created_at': row[5],
            'processed_at': row[6],
        })

    return JsonResponse({'actions': actions})


# ---------------------------------------------------------------------------
# Audit Log API
# ---------------------------------------------------------------------------

@matrix_space_required
@require_http_methods(['GET'])
def api_matrix_audit_log(request, space_id):
    """Return paginated audit log entries with optional filters."""
    limit = min(safe_int(request.GET.get('limit', 50), 50, 1, 200), 200)
    offset = safe_int(request.GET.get('offset', 0), 0, 0)
    category = request.GET.get('category', '').strip()[:20]
    action_filter = request.GET.get('action', '').strip()[:50]
    actor_filter = request.GET.get('actor', '').strip()[:255]
    target_filter = request.GET.get('target', '').strip()[:255]

    conditions = ['space_id = :sid']
    params = {'sid': space_id, 'lim': limit, 'off': offset}

    if category:
        conditions.append('category = :cat')
        params['cat'] = category
    if action_filter:
        conditions.append('action = :act')
        params['act'] = action_filter
    if actor_filter:
        conditions.append('actor_matrix_id LIKE :actor')
        params['actor'] = f'%{actor_filter}%'
    if target_filter:
        conditions.append('target_matrix_id LIKE :target')
        params['target'] = f'%{target_filter}%'

    where = ' AND '.join(conditions)

    with get_db_session() as db:
        rows = db.execute(
            sa_text(
                f"SELECT id, action, category, actor_matrix_id, actor_display_name, "
                f"target_matrix_id, target_display_name, target_type, "
                f"room_id, room_name, reason, details, created_at "
                f"FROM web_matrix_audit_log WHERE {where} "
                f"ORDER BY created_at DESC LIMIT :lim OFFSET :off"
            ),
            params
        ).fetchall()
        total_row = db.execute(
            sa_text(f"SELECT COUNT(*) FROM web_matrix_audit_log WHERE {where}"),
            {k: v for k, v in params.items() if k not in ('lim', 'off')}
        ).fetchone()

    total = int(total_row[0]) if total_row else 0
    entries = []
    for r in rows:
        entries.append({
            'id': r[0],
            'action': r[1],
            'category': r[2] or '',
            'actor_matrix_id': r[3] or '',
            'actor_display_name': r[4] or r[3] or '',
            'target_matrix_id': r[5] or '',
            'target_display_name': r[6] or r[5] or '',
            'target_type': r[7] or '',
            'room_id': r[8] or '',
            'room_name': r[9] or r[8] or '',
            'reason': r[10] or '',
            'details': r[11] or '',
            'created_at': r[12],
        })

    return JsonResponse({'entries': entries, 'total': total, 'offset': offset, 'limit': limit})


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

@web_login_required
@matrix_space_required
@add_web_user_context
def matrix_guild_bridge(request, space_id):
    with get_db_session() as db:
        ctx = _get_space_context(db, space_id)

    wu = request.web_user

    # Build Discord guilds + channels from guilds.cached_channels JSON column
    discord_guilds = []
    owned_discord = getattr(wu, 'owned_discord_guilds', []) or []
    if owned_discord:
        import json as _json
        with get_db_session() as db:
            for g in owned_discord:
                gid = str(g.get('id', ''))
                if not gid:
                    continue
                try:
                    gid_int = int(gid)
                except ValueError:
                    continue
                row = db.execute(
                    sa_text("SELECT cached_channels FROM guilds WHERE guild_id = :gid LIMIT 1"),
                    {'gid': gid_int}
                ).fetchone()
                channels = []
                if row and row[0]:
                    try:
                        raw = _json.loads(row[0])
                        channels = [
                            {'value': str(c['id']), 'label': c['name']}
                            for c in raw
                            if c.get('type') == 0  # text channels only
                        ]
                    except Exception:
                        pass
                discord_guilds.append({'id': gid, 'name': g.get('name', gid), 'channels': channels})

    # Build Fluxer guilds + channels for cascading pickers
    fluxer_guilds = []
    owned_fluxer = getattr(wu, 'owned_fluxer_guilds', []) or []
    if owned_fluxer:
        with get_db_session() as db:
            for g in owned_fluxer:
                gid = str(g.get('id', ''))
                if not gid:
                    continue
                rows = db.execute(
                    sa_text(
                        "SELECT channel_id, channel_name FROM web_fluxer_guild_channels "
                        "WHERE guild_id = :gid ORDER BY channel_name"
                    ),
                    {'gid': gid}
                ).fetchall()
                channels = [{'value': str(r[0]), 'label': r[1] or str(r[0])} for r in rows]
                fluxer_guilds.append({
                    'id': gid,
                    'name': g.get('name', gid),
                    'channels': channels,
                })

    ctx['active_section'] = 'bridge'
    ctx['discord_guilds_json'] = json.dumps(discord_guilds)
    ctx['fluxer_guilds_json'] = json.dumps(fluxer_guilds)
    return render(request, 'questlog_web/matrix_guild_bridge.html', ctx)


def _bridge_dict(b: WebBridgeConfig) -> dict:
    return {
        'id': b.id,
        'name': b.name or '',
        'matrix_space_id': b.matrix_space_id or '',
        'matrix_room_id': b.matrix_room_id or '',
        'discord_guild_id': b.discord_guild_id or '',
        'discord_channel_id': b.discord_channel_id or '',
        'fluxer_guild_id': b.fluxer_guild_id or '',
        'fluxer_channel_id': b.fluxer_channel_id or '',
        'relay_matrix_outbound': bool(getattr(b, 'relay_matrix_outbound', 1)),
        'relay_matrix_inbound': bool(getattr(b, 'relay_matrix_inbound', 1)),
        'max_msg_len': b.max_msg_len,
        'enabled': bool(b.enabled),
        'created_at': b.created_at,
    }


@matrix_space_required
@require_http_methods(['GET', 'POST'])
def api_matrix_bridges(request, space_id):
    """GET list / POST create bridge config for this Matrix space."""
    if request.method == 'GET':
        with get_db_session() as db:
            # Match by space_id OR by any room_id that belongs to this space
            room_ids = [
                r.room_id for r in db.query(WebMatrixRoom).filter_by(
                    space_id=space_id, is_space=0
                ).all()
            ]
            from sqlalchemy import or_
            clauses = [WebBridgeConfig.matrix_space_id == space_id]
            if room_ids:
                clauses.append(WebBridgeConfig.matrix_room_id.in_(room_ids))
            bridges = db.query(WebBridgeConfig).filter(
                or_(*clauses)
            ).order_by(WebBridgeConfig.id).all()
            return JsonResponse({'success': True, 'bridges': [_bridge_dict(b) for b in bridges]})

    # POST - create
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    matrix_room_id = str(data.get('matrix_room_id', '') or '').strip()[:255]
    if not matrix_room_id:
        return JsonResponse({'error': 'matrix_room_id is required'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        bridge = WebBridgeConfig(
            name=sanitize_text(str(data.get('name', '') or '')).strip()[:100] or None,
            matrix_space_id=space_id,
            matrix_room_id=matrix_room_id,
            discord_guild_id=str(data.get('discord_guild_id', '') or '').strip()[:20] or None,
            discord_channel_id=str(data.get('discord_channel_id', '') or '').strip()[:20] or None,
            fluxer_guild_id=str(data.get('fluxer_guild_id', '') or '').strip()[:20] or None,
            fluxer_channel_id=str(data.get('fluxer_channel_id', '') or '').strip()[:20] or None,
            relay_matrix_outbound=1 if data.get('relay_matrix_outbound', True) else 0,
            relay_matrix_inbound=1 if data.get('relay_matrix_inbound', True) else 0,
            relay_discord_to_fluxer=1 if data.get('relay_discord_to_fluxer', True) else 0,
            relay_fluxer_to_discord=1 if data.get('relay_fluxer_to_discord', True) else 0,
            max_msg_len=safe_int(data.get('max_msg_len', 1000), 1000, 50, 2000),
            enabled=1,
            created_at=now,
        )
        db.add(bridge)
        db.commit()
        db.refresh(bridge)
        return JsonResponse({'success': True, 'bridge': _bridge_dict(bridge)}, status=201)


@matrix_space_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def api_matrix_bridge_detail(request, space_id, bridge_id):
    """GET / PATCH / DELETE a single bridge config."""
    bridge_id = safe_int(bridge_id, default=0)
    if not bridge_id:
        return JsonResponse({'error': 'Invalid bridge_id'}, status=400)

    with get_db_session() as db:
        bridge = db.query(WebBridgeConfig).filter_by(id=bridge_id, matrix_space_id=space_id).first()
        if not bridge:
            return JsonResponse({'error': 'Bridge not found'}, status=404)

        if request.method == 'GET':
            return JsonResponse({'success': True, 'bridge': _bridge_dict(bridge)})

        if request.method == 'DELETE':
            db.query(WebBridgeRelayQueue).filter_by(bridge_id=bridge_id).delete()
            db.delete(bridge)
            db.commit()
            return JsonResponse({'success': True})

        # PATCH
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'name' in data:
            bridge.name = sanitize_text(str(data['name'] or '')).strip()[:100] or None
        if 'enabled' in data:
            bridge.enabled = 1 if data['enabled'] else 0
        if 'relay_matrix_outbound' in data:
            bridge.relay_matrix_outbound = 1 if data['relay_matrix_outbound'] else 0
        if 'relay_matrix_inbound' in data:
            bridge.relay_matrix_inbound = 1 if data['relay_matrix_inbound'] else 0
        if 'relay_discord_to_fluxer' in data:
            bridge.relay_discord_to_fluxer = 1 if data['relay_discord_to_fluxer'] else 0
        if 'relay_fluxer_to_discord' in data:
            bridge.relay_fluxer_to_discord = 1 if data['relay_fluxer_to_discord'] else 0
        if 'max_msg_len' in data:
            bridge.max_msg_len = safe_int(data['max_msg_len'], 1000, 50, 2000)
        if 'matrix_room_id' in data:
            bridge.matrix_room_id = str(data['matrix_room_id'] or '').strip()[:255] or None
        if 'discord_guild_id' in data:
            bridge.discord_guild_id = str(data['discord_guild_id'] or '').strip()[:20] or None
        if 'discord_channel_id' in data:
            bridge.discord_channel_id = str(data['discord_channel_id'] or '').strip()[:20] or None
        if 'fluxer_guild_id' in data:
            bridge.fluxer_guild_id = str(data['fluxer_guild_id'] or '').strip()[:20] or None
        if 'fluxer_channel_id' in data:
            bridge.fluxer_channel_id = str(data['fluxer_channel_id'] or '').strip()[:20] or None

        db.commit()
        db.refresh(bridge)
        return JsonResponse({'success': True, 'bridge': _bridge_dict(bridge)})
