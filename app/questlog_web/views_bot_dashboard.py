# views_bot_dashboard.py - Fluxer Bot Dashboard (admin-only)
#
# Multi-page per-guild Fluxer bot configuration dashboard.
# Mirrors the Discord guild dashboard: each feature has its own URL and template.
#
# URL structure:
#   /ql/dashboard/fluxer/                            - guild list landing page
#   /ql/dashboard/fluxer/<guild_id>/                 - per-guild overview
#   /ql/dashboard/fluxer/<guild_id>/xp/              - XP & Leveling
#   /ql/dashboard/fluxer/<guild_id>/welcome/         - Welcome Messages
#   /ql/dashboard/fluxer/<guild_id>/moderation/      - Moderation
#   /ql/dashboard/fluxer/<guild_id>/lfg/             - LFG System
#   /ql/dashboard/fluxer/<guild_id>/bridge/          - Chat Bridge
#   /ql/dashboard/fluxer/<guild_id>/settings/        - Server Settings
#   /ql/dashboard/fluxer/<guild_id>/<soon>/          - Coming Soon pages
#   /ql/api/dashboard/fluxer/<guild_id>/settings/    - GET/POST guild settings (partial update)
#   /ql/api/dashboard/bot-configs/                   - community network sub configs (kept)
#   /ql/api/dashboard/bot-configs/<id>/              - detail (kept)

import asyncio
import re as _re
import json
import time
import random
import logging

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from app.db import get_db_session
from sqlalchemy import text
from .models import (
    WebCommunityBotConfig, WebCommunity,
    WebFluxerGuildChannel, WebFluxerGuildRole, WebFluxerGuildSettings,
    WebBridgeConfig,
    WebFluxerLfgGame, WebFluxerLfgGroup, WebFluxerLfgMember,
    WebFluxerLfgAttendance, WebFluxerLfgMemberStats, WebFluxerLfgConfig,
    WebFluxerWelcomeConfig, WebFluxerReactionRole,
    WebFluxerRaffle, WebFluxerRaffleEntry,
    WebFluxerModWarning, WebFluxerVerificationConfig,
    WebFluxerRssFeed, WebFluxerRssArticle, WebFluxerGuildFlair, WebFluxerLevelRole, WebFluxerXpBoostEvent,
    WebFlair, WebFluxerGuildAction,
    WebFluxerStreamerSub, WebCreatorProfile,
    WebFluxerGameSearchConfig, WebFluxerFoundGame,
    FluxerChannelStatTracker,
)
from django_ratelimit.decorators import ratelimit
from .helpers import web_admin_required, web_login_required, fluxer_guild_required, fluxer_login_required, discord_guild_required, discord_login_required, add_web_user_context, safe_int, sanitize_text

logger = logging.getLogger(__name__)

# Custom emoji format: <:name:id> or <a:name:id> (animated)
_CUSTOM_EMOJI_RE = _re.compile(r'^<a?:[A-Za-z0-9_]{1,32}:\d{15,22}>$')

# Guild icon hash: only alphanumeric, underscore, hyphen allowed to prevent URL injection
_ICON_HASH_RE = _re.compile(r'^[A-Za-z0-9_\-]+$')


def _sanitize_emoji(value: str) -> str:
    """Allow Unicode emoji or Fluxer/Discord custom emoji syntax <:name:id>. Strips everything else."""
    v = (value or '').strip()[:100]
    if not v:
        return ''
    # Allow custom emoji format
    if _CUSTOM_EMOJI_RE.match(v):
        return v
    # Strip any HTML-like tags and return the rest (handles plain Unicode emoji)
    return _re.sub(r'<[^>]+>', '', v).strip()[:100]


SOON_FEATURES = {
    'fluxer_guild_soon_verification': {
        'name': 'Verification', 'icon': 'fas fa-user-check', 'color': 'purple',
        'desc': 'CAPTCHA, account age checks, and role-gated access controls.',
    },
    'fluxer_guild_soon_reaction_roles': {
        'name': 'Reaction Roles', 'icon': 'fas fa-smile', 'color': 'yellow',
        'desc': 'Let members self-assign roles by reacting to pinned messages.',
    },
    'fluxer_guild_soon_trackers': {
        'name': 'Trackers', 'icon': 'fas fa-chart-bar', 'color': 'orange',
        'desc': 'Live channel stats showing member counts and game activity.',
    },
    'fluxer_guild_soon_audit': {
        'name': 'Audit Log', 'icon': 'fas fa-history', 'color': 'cyan',
        'desc': 'Track and search all server events - bans, role changes, joins.',
    },
    'fluxer_guild_soon_templates': {
        'name': 'Templates', 'icon': 'fas fa-copy', 'color': 'pink',
        'desc': 'Save server configurations as templates and apply them across guilds.',
    },
    'fluxer_guild_soon_discovery': {
        'name': 'Discovery', 'icon': 'fas fa-bullhorn', 'color': 'orange',
        'desc': 'Feature creators and games to help your community grow.',
    },
    'fluxer_guild_soon_raffles': {
        'name': 'Raffles', 'icon': 'fas fa-ticket-alt', 'color': 'yellow',
        'desc': 'Community giveaways with weighted entries and automated winner selection.',
    },
    'fluxer_guild_soon_roles': {
        'name': 'Role Management', 'icon': 'fas fa-user-tag', 'color': 'indigo',
        'desc': 'Manage, assign, and automate roles across your community.',
    },
    'fluxer_guild_soon_messages': {
        'name': 'Message Tools', 'icon': 'fas fa-comment-dots', 'color': 'blue',
        'desc': 'Scheduled messages, embeds, and automated announcements.',
    },
}

EVENT_LABELS = {
    'lfg_announce': {
        'label': 'LFG Announcements',
        'description': 'Receive LFG posts from the QuestLog Network in this channel.',
        'icon': 'fas fa-users',
        'color': 'yellow',
        'available': True,
    },
    'featured_creators': {
        'label': 'Featured Creators',
        'description': 'Get notified when QuestLog features a new creator.',
        'icon': 'fas fa-star',
        'color': 'purple',
        'available': False,
    },
    'new_games': {
        'label': 'New Games',
        'description': 'Updates when new games are added to QuestLog.',
        'icon': 'fas fa-gamepad',
        'color': 'blue',
        'available': False,
    },
    'gaming_news': {
        'label': 'Gaming News',
        'description': 'QuestLog curated gaming news and announcements.',
        'icon': 'fas fa-newspaper',
        'color': 'green',
        'available': False,
    },
}


def _config_dict(cfg: WebCommunityBotConfig) -> dict:
    return {
        'id': cfg.id,
        'community_id': cfg.community_id,
        'platform': cfg.platform,
        'guild_id': cfg.guild_id,
        'guild_name': cfg.guild_name or '',
        'channel_id': cfg.channel_id or '',
        'channel_name': cfg.channel_name or '',
        'webhook_url': cfg.webhook_url or '',
        'event_type': cfg.event_type,
        'is_enabled': cfg.is_enabled,
        'updated_at': cfg.updated_at,
    }


def _settings_dict(s: WebFluxerGuildSettings) -> dict:
    def _safe(attr, default=None):
        v = getattr(s, attr, None)
        return v if v is not None else default

    return {
        'guild_id': s.guild_id,
        'guild_name': s.guild_name or '',
        # XP
        'xp_enabled': bool(s.xp_enabled),
        'xp_per_message': _safe('xp_per_message', 2),
        'xp_per_reaction': _safe('xp_per_reaction', 1),
        'xp_per_voice_minute': _safe('xp_per_voice_minute', 1),
        'xp_per_media': _safe('xp_per_media', 3),
        'xp_per_gaming_hour': _safe('xp_per_gaming_hour', 10),
        'xp_cooldown_secs': _safe('xp_cooldown_secs', 60),
        'xp_media_cooldown_secs': _safe('xp_media_cooldown_secs', 60),
        'xp_reaction_cooldown_secs': _safe('xp_reaction_cooldown_secs', 60),
        'xp_ignored_channels': json.loads(s.xp_ignored_channels) if s.xp_ignored_channels else [],
        'track_messages': bool(_safe('track_messages', 1)),
        'track_media': bool(_safe('track_media', 1)),
        'track_reactions': bool(_safe('track_reactions', 1)),
        'track_voice': bool(_safe('track_voice', 1)),
        'track_gaming': bool(_safe('track_gaming', 0)),
        # Moderation
        'mod_log_channel_id': _safe('mod_log_channel_id', ''),
        'warn_threshold': _safe('warn_threshold', 3),
        'auto_ban_after_warns': bool(_safe('auto_ban_after_warns', 0)),
        # LFG
        'lfg_channel_id': _safe('lfg_channel_id', ''),
        # Welcome (legacy fields - now handled by WebFluxerWelcomeConfig)
        'welcome_channel_id': _safe('welcome_channel_id', ''),
        'welcome_message': _safe('welcome_message', ''),
        'goodbye_channel_id': _safe('goodbye_channel_id', ''),
        'goodbye_message': _safe('goodbye_message', ''),
        # General
        'bot_prefix': _safe('bot_prefix', '!'),
        'language': _safe('language', 'en'),
        'timezone': _safe('timezone', 'UTC'),
        'token_name': _safe('token_name', 'Hero Tokens'),
        'token_emoji': _safe('token_emoji', ':coin:'),
        # Member management
        'role_persistence_enabled': bool(_safe('role_persistence_enabled', 0)),
        'admin_roles': json.loads(s.admin_roles) if getattr(s, 'admin_roles', None) else [],
        'channel_notify_channel_id': _safe('channel_notify_channel_id', ''),
        'temp_voice_category_ids': json.loads(s.temp_voice_category_ids) if getattr(s, 'temp_voice_category_ids', None) else [],
        'discovery_enabled': bool(_safe('discovery_enabled', 0)),
        'flair_sync_enabled': bool(_safe('flair_sync_enabled', 0)),
        # Audit logging
        'audit_log_enabled': bool(_safe('audit_logging_enabled', 0)),
        'audit_log_channel_id': _safe('audit_log_channel_id', '') or '',
        # Creator Discovery (stored as JSON blob)
        **_parse_creator_discovery(getattr(s, 'creator_discovery_json', None)),
        'updated_at': s.updated_at,
        'owner_id': _safe('owner_id', ''),
    }


_CREATOR_DISCOVERY_DEFAULTS = {
    'creator_enabled': False,
    'creator_spotlight_channel_id': '',
    'creator_selfpromo_channel_id': '',
    'creator_feature_channel_id': '',
    'creator_response_channel_id': '',
    'creator_feature_interval_hours': 3,
    'creator_cooldown_hours': 72,
    'creator_announcement_template': '',
    'creator_cotw_enabled': False,
    'creator_cotw_channel_id': '',
    'creator_cotw_auto_rotate': False,
    'creator_cotw_rotation_day': 1,
    'creator_cotm_enabled': False,
    'creator_cotm_channel_id': '',
    'creator_cotm_auto_rotate': False,
    'creator_cotm_rotation_day': 1,
    'creator_channel_discovery_enabled': False,
    'game_announcements_enabled': False,
    'game_announcements_channel_id': '',
    'game_check_interval_hours': 24,
    'game_max_announcements': 5,
    'creator_spotlight_enabled': False,
    'creator_spotlight_message': '',
    'creator_feature_interval_hours': 3,
    'creator_feature_cooldown_hours': 72,
}


def _parse_creator_discovery(raw_json: str | None) -> dict:
    """Parse the creator_discovery_json column into a flat dict with defaults."""
    defaults = dict(_CREATOR_DISCOVERY_DEFAULTS)
    if not raw_json:
        return defaults
    try:
        stored = json.loads(raw_json)
        if isinstance(stored, dict):
            defaults.update({k: v for k, v in stored.items() if k in defaults})
    except (json.JSONDecodeError, TypeError):
        pass
    return defaults


def _clean_name(val) -> str:
    """Return a usable guild name, rejecting empty strings and the literal 'None'."""
    if not val:
        return ''
    s = str(val).strip()
    return '' if s in ('None', 'null', 'undefined') else s


def _default_settings(guild_id: str, guild_name: str = '') -> dict:
    return {
        'guild_id': guild_id,
        'guild_name': guild_name,
        # XP
        'xp_enabled': True,
        'xp_per_message': 2,
        'xp_per_reaction': 1,
        'xp_per_voice_minute': 1,
        'xp_per_media': 3,
        'xp_per_gaming_hour': 10,
        'xp_cooldown_secs': 60,
        'xp_media_cooldown_secs': 60,
        'xp_reaction_cooldown_secs': 60,
        'xp_ignored_channels': [],
        'track_messages': True,
        'track_media': True,
        'track_reactions': True,
        'track_voice': True,
        'track_gaming': False,
        # Moderation
        'mod_log_channel_id': '',
        'warn_threshold': 3,
        'auto_ban_after_warns': False,
        # LFG
        'lfg_channel_id': '',
        # Welcome (legacy)
        'welcome_channel_id': '',
        'welcome_message': '',
        'goodbye_channel_id': '',
        'goodbye_message': '',
        # General
        'bot_prefix': '!',
        'language': 'en',
        'timezone': 'UTC',
        'token_name': 'Hero Tokens',
        'token_emoji': ':coin:',
        # Member management
        'role_persistence_enabled': False,
        'admin_roles': [],
        'channel_notify_channel_id': '',
        'temp_voice_category_ids': [],
        'updated_at': 0,
    }


# ---------------------------------------------------------------------------
# Helper: common context for all per-guild pages
# ---------------------------------------------------------------------------

def _get_fluxer_guild_context(db, guild_id: str) -> dict:
    """Returns channels, settings, guild_name, and all_guilds for any Fluxer guild view."""
    channels = db.query(WebFluxerGuildChannel).filter_by(guild_id=guild_id).order_by(
        WebFluxerGuildChannel.channel_name
    ).all()
    channels_data = [
        {'id': c.channel_id, 'value': c.channel_id, 'label': c.channel_name or c.channel_id}
        for c in channels
    ]

    settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
    ch_name = _clean_name(channels[0].guild_name) if channels else ''
    settings_name = _clean_name(settings.guild_name) if settings else ''
    guild_name = settings_name or ch_name or _fetch_fluxer_guild_name(guild_id, db) or guild_id
    settings_data = _settings_dict(settings) if settings else _default_settings(guild_id, guild_name)

    all_guilds = [
        {'guild_id': r[0], 'guild_name': _clean_name(r[1])}
        for r in db.execute(text(
            "SELECT c.guild_id, "
            "  COALESCE(NULLIF(s.guild_name, ''), NULLIF(MAX(c.guild_name), '')) as guild_name "
            "FROM web_fluxer_guild_channels c "
            "LEFT JOIN web_fluxer_guild_settings s ON s.guild_id = c.guild_id "
            "GROUP BY c.guild_id, s.guild_name "
            "HAVING guild_name IS NOT NULL AND guild_name != '' "
            "ORDER BY guild_name"
        )).fetchall()
        if _clean_name(r[1])
    ]

    network_row = db.execute(
        text("SELECT id FROM web_communities WHERE platform='fluxer' AND platform_id=:g AND network_status='approved' LIMIT 1"),
        {'g': guild_id}
    ).fetchone()

    _icon_hash = getattr(settings, 'guild_icon_hash', None) or '' if settings else ''
    if _icon_hash and not _ICON_HASH_RE.match(_icon_hash):
        _icon_hash = ''
    guild_icon_url = (
        f'https://fluxerusercontent.com/icons/{guild_id}/{_icon_hash}.png'
        if _icon_hash else None
    )

    return {
        'guild_id': guild_id,
        'guild_name': guild_name,
        'settings': settings_data,
        'channels_json': json.dumps(channels_data),
        'settings_json': json.dumps(settings_data),
        'all_guilds': all_guilds,
        'is_network_approved': network_row is not None,
        'guild_icon_url': guild_icon_url,
    }


# ---------------------------------------------------------------------------
# Landing page: list all Fluxer guilds the bot is in
# ---------------------------------------------------------------------------

def _fetch_fluxer_guild_name(guild_id: str, db) -> str:
    """
    Try to get a guild name from the Fluxer API and cache it in the DB.
    Returns the name or empty string on failure.
    """
    try:
        import requests as _req
        from django.conf import settings as _dj
        bot_token = getattr(_dj, 'FLUXER_BOT_TOKEN', '')
        api_base  = getattr(_dj, 'FLUXER_API_BASE', 'https://api.fluxer.app')
        api_ver   = getattr(_dj, 'FLUXER_API_VERSION', '1')
        if not bot_token:
            return ''
        resp = _req.get(
            f'{api_base}/v{api_ver}/guilds/{guild_id}',
            headers={'Authorization': f'Bot {bot_token}'},
            timeout=5,
        )
        if resp.status_code == 200:
            name = _clean_name(resp.json().get('name', ''))
            if name:
                db.execute(text(
                    "UPDATE web_fluxer_guild_channels SET guild_name = :n WHERE guild_id = :g"
                ), {'n': name, 'g': guild_id})
                db.execute(text(
                    "UPDATE web_fluxer_guild_settings SET guild_name = :n WHERE guild_id = :g"
                ), {'n': name, 'g': guild_id})
                db.commit()
            return name
    except Exception:
        pass
    return ''


@web_login_required
@add_web_user_context
def unified_dashboard(request):
    """
    Unified server dashboard landing page.
    Shows all servers the logged-in user owns/admins across Discord, Fluxer, and Matrix.
    Accepts full QL session or lite Discord OAuth session.
    Each platform section links to the appropriate per-guild dashboard.
    """
    wu = request.web_user
    discord_id = str(getattr(wu, 'discord_id', None) or '')

    # --- Fluxer guilds (from QL account if linked) ---
    fluxer_owned = getattr(wu, 'owned_fluxer_guilds', []) if wu else []

    # --- Discord guilds: from QL account ---
    discord_owned = getattr(wu, 'owned_discord_guilds', []) if wu else []
    if not discord_owned and discord_id:
        with get_db_session() as db:
            rows = db.execute(text(
                "SELECT guild_id, guild_name FROM guilds WHERE owner_id = :uid ORDER BY guild_name"
            ), {'uid': int(discord_id)}).fetchall()
            discord_owned = [{'guild_id': str(r[0]), 'guild_name': r[1] or str(r[0])} for r in rows]

    # --- Linked platform status ---
    has_discord = bool(getattr(wu, 'discord_id', None))
    has_fluxer = bool(getattr(wu, 'fluxer_id', None))
    user_matrix_id = getattr(wu, 'matrix_id', None) or ''
    has_matrix = bool(user_matrix_id)

    # --- Matrix spaces this user owns or admins ---
    matrix_spaces = []
    if has_matrix:
        from .models import WebMatrixSpaceSettings
        with get_db_session() as db:
            rows = db.query(WebMatrixSpaceSettings).filter_by(bot_present=1).order_by(
                WebMatrixSpaceSettings.space_name
            ).all()
            for r in rows:
                is_owner = r.owner_matrix_id == user_matrix_id
                admin_ids = []
                if r.admin_matrix_ids:
                    try:
                        admin_ids = json.loads(r.admin_matrix_ids)
                    except Exception:
                        pass
                if is_owner or user_matrix_id in admin_ids or request.user.is_superuser:
                    matrix_spaces.append({
                        'id': r.space_id,
                        'name': r.space_name or r.space_id,
                        'member_count': r.member_count,
                        'room_count': r.room_count,
                    })

    return render(request, 'questlog_web/unified_dashboard.html', {
        'web_user': wu,
        'active_page': 'dashboard',
        'fluxer_guilds': fluxer_owned,
        'discord_guilds': discord_owned,
        'matrix_spaces': matrix_spaces,
        'has_discord': has_discord,
        'has_fluxer': has_fluxer,
        'has_matrix': has_matrix,
    })


@discord_guild_required
@add_web_user_context
def discord_guild_dashboard(request, guild_id):
    """
    Per-guild Discord dashboard - delegates to the existing WardenBot guild_dashboard view.
    The URL /ql/dashboard/discord/<guild_id>/ is also aliased directly in app/urls.py
    so this view is only hit from the questlog_web URL conf (the /ql/ prefix).
    """
    from app.views import guild_dashboard as _guild_dashboard
    return _guild_dashboard(request, guild_id=guild_id)


@fluxer_login_required
@add_web_user_context
def fluxer_dashboard(request):
    """List Fluxer guilds the current user owns. Works with lite session or full QL account."""
    fluxer_id = request.fluxer_id
    is_superuser = request.user.is_authenticated and request.user.is_superuser

    with get_db_session() as db:
        if is_superuser:
            # Superusers see all guilds
            rows = db.execute(text(
                "SELECT c.guild_id, "
                "  COALESCE(NULLIF(s.guild_name, ''), NULLIF(MAX(c.guild_name), ''), '') as guild_name "
                "FROM web_fluxer_guild_channels c "
                "LEFT JOIN web_fluxer_guild_settings s ON s.guild_id = c.guild_id "
                "GROUP BY c.guild_id, s.guild_name"
            )).fetchall()
        else:
            # Only guilds this Fluxer user owns or has admin roles in
            rows = db.execute(text(
                "SELECT c.guild_id, "
                "  COALESCE(NULLIF(s.guild_name, ''), NULLIF(MAX(c.guild_name), ''), '') as guild_name "
                "FROM web_fluxer_guild_channels c "
                "LEFT JOIN web_fluxer_guild_settings s ON s.guild_id = c.guild_id "
                "WHERE s.owner_id = :uid "
                "GROUP BY c.guild_id, s.guild_name"
            ), {'uid': fluxer_id}).fetchall()

        guilds = []
        for row in rows:
            gid = row[0]
            gname = _clean_name(row[1])
            if not gname:
                gname = _fetch_fluxer_guild_name(gid, db)
            gname = gname or gid

            settings_row = db.execute(text(
                "SELECT guild_icon_hash, owner_id FROM web_fluxer_guild_settings WHERE guild_id = :g LIMIT 1"
            ), {'g': gid}).fetchone()
            icon_hash = settings_row[0] if settings_row else None
            if icon_hash and not _ICON_HASH_RE.match(icon_hash):
                icon_hash = None
            owner_id = str(settings_row[1] or '') if settings_row else ''

            channel_count = db.execute(text(
                "SELECT COUNT(*) FROM web_fluxer_guild_channels WHERE guild_id = :g"
            ), {'g': gid}).scalar() or 0

            member_count = db.execute(text(
                "SELECT COUNT(DISTINCT user_id) FROM fluxer_member_xp WHERE guild_id = :g"
            ), {'g': gid}).scalar() or 0

            is_owner = (owner_id == str(fluxer_id)) if fluxer_id else is_superuser
            icon_url = f'https://fluxerusercontent.com/icons/{gid}/{icon_hash}.png' if icon_hash else None

            guilds.append({
                'guild_id': gid,
                'guild_name': gname,
                'channel_count': channel_count,
                'member_count': member_count,
                'icon_url': icon_url,
                'is_owner': is_owner,
            })

    return render(request, 'questlog_web/bot_dashboard.html', {
        'web_user': request.web_user,
        'active_page': 'bot_dashboard',
        'guilds': guilds,
        'guild_count': len(guilds),
    })


# ---------------------------------------------------------------------------
# Sidebar guild list helper - called by all admin views that skip add_web_user_context
# ---------------------------------------------------------------------------

def _ensure_sidebar_guilds(request):
    """Populate owned_fluxer_guilds / member_fluxer_guilds on request.web_user if not already set."""
    if not request.web_user or hasattr(request.web_user, 'owned_fluxer_guilds'):
        return
    _fid = str(getattr(request.web_user, 'fluxer_id', '') or '')
    _uid = getattr(request.web_user, 'id', None)
    if _fid and _uid:
        try:
            with get_db_session() as _db:
                _owned = _db.execute(
                    text("SELECT guild_id, COALESCE(NULLIF(guild_name,''), guild_id) as name, guild_icon_hash "
                         "FROM web_fluxer_guild_settings WHERE owner_id = :fid LIMIT 10"),
                    {'fid': _fid}
                ).fetchall()
                _admin = _db.execute(
                    text("SELECT c.platform_id, COALESCE(NULLIF(s.guild_name,''), c.platform_id) as name, s.guild_icon_hash "
                         "FROM web_community_members cm "
                         "JOIN web_communities c ON c.id = cm.community_id "
                         "LEFT JOIN web_fluxer_guild_settings s ON s.guild_id = c.platform_id "
                         "WHERE cm.user_id = :uid AND cm.role IN ('admin','moderator','owner') "
                         "AND c.platform = 'fluxer' AND c.is_active = 1 LIMIT 10"),
                    {'uid': _uid}
                ).fetchall()
                _member = _db.execute(
                    text("SELECT x.guild_id, COALESCE(NULLIF(s.guild_name,''), x.guild_id) as name, s.guild_icon_hash "
                         "FROM (SELECT DISTINCT guild_id FROM fluxer_member_xp WHERE user_id = :fid) x "
                         "LEFT JOIN web_fluxer_guild_settings s ON s.guild_id = x.guild_id LIMIT 15"),
                    {'fid': _fid}
                ).fetchall()
            _owned_map = {str(r[0]): {'id': str(r[0]), 'name': r[1], 'icon_hash': r[2] or ''} for r in _owned}
            _admin_map = {str(r[0]): {'id': str(r[0]), 'name': r[1], 'icon_hash': r[2] or ''} for r in _admin}
            _admin_map.update(_owned_map)
            _member_map = {str(r[0]): {'id': str(r[0]), 'name': r[1], 'icon_hash': r[2] or ''} for r in _member}
            request.web_user.owned_fluxer_guilds = list(_admin_map.values())
            request.web_user.member_fluxer_guilds = [g for gid, g in _member_map.items() if gid not in _admin_map]
        except Exception:
            request.web_user.owned_fluxer_guilds = []
            request.web_user.member_fluxer_guilds = []
    else:
        request.web_user.owned_fluxer_guilds = []
        request.web_user.member_fluxer_guilds = []


# ---------------------------------------------------------------------------
# Per-guild dashboard
# ---------------------------------------------------------------------------

@fluxer_guild_required
def fluxer_guild_dashboard(request, guild_id):
    """Admin-only: per-guild Fluxer bot overview page."""
    guild_id = guild_id.strip()

    with get_db_session() as db:
        ctx = _get_fluxer_guild_context(db, guild_id)

        member_count = db.execute(text(
            "SELECT COUNT(DISTINCT user_id) FROM fluxer_member_xp WHERE guild_id = :g"
        ), {'g': guild_id}).scalar() or 0

        channel_count = db.execute(text(
            "SELECT COUNT(*) FROM web_fluxer_guild_channels WHERE guild_id = :g"
        ), {'g': guild_id}).scalar() or 0

        top_row = db.execute(text(
            "SELECT username FROM fluxer_member_xp WHERE guild_id = :g ORDER BY xp DESC LIMIT 1"
        ), {'g': guild_id}).fetchone()
        top_xp_earner = top_row[0] if top_row else None

        bridge_count = db.query(WebBridgeConfig).filter_by(
            fluxer_guild_id=guild_id, enabled=True
        ).count()

    _ensure_sidebar_guilds(request)
    ctx.update({
        'web_user': request.web_user,
        'active_page': 'bot_dashboard',
        'active_section': 'overview',
        'is_owner': True,  # passed fluxer_guild_required, so always owner/admin
        'stats': {
            'member_count': member_count,
            'channel_count': channel_count,
            'top_xp_earner': top_xp_earner,
            'bridge_count': bridge_count,
        },
    })
    return render(request, 'questlog_web/fluxer_guild_dashboard.html', ctx)


# ---------------------------------------------------------------------------
# Per-guild feature pages
# ---------------------------------------------------------------------------

# Welcome/goodbye message variables - ported from WardenBot cogs/welcome.py
_WELCOME_VARS = [
    ('{user}',             'User mention (@username)'),
    ('{username}',         'Plain display name'),
    ('{server}',           'Server name'),
    ('{member_count}',     'Current member count'),
    ('{member_count_ord}', 'Member count with ordinal (1st, 2nd...)'),
    ('{join_number}',      "This member's join number"),
    ('{join_number_ord}',  'Join number with ordinal'),
    ('{user_id}',          "User's ID"),
    ('{created_at}',       'When the account was created'),
    ('{avatar_url}',       "User's avatar URL"),
]


def _guild_view(request, guild_id, template, active_section, extra=None):
    """Shared helper: fetch context and render a per-guild template."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        ctx = _get_fluxer_guild_context(db, guild_id)
        if extra:
            ctx.update(extra(db, guild_id))

    # Anyone who reached here passed fluxer_guild_required (owner OR admin-role member).
    _ensure_sidebar_guilds(request)
    ctx.update({
        'web_user': request.web_user,
        'active_page': active_section,
        'active_section': active_section,
        'is_owner': True,
    })
    return render(request, template, ctx)


@fluxer_guild_required
def fluxer_guild_xp(request, guild_id):
    def _extra(db, gid):
        level_roles = db.query(WebFluxerLevelRole).filter_by(guild_id=gid).order_by(
            WebFluxerLevelRole.level_required
        ).all()
        roles = db.query(WebFluxerGuildRole).filter_by(guild_id=gid).order_by(
            WebFluxerGuildRole.role_name
        ).all()
        boosts = db.query(WebFluxerXpBoostEvent).filter_by(guild_id=gid).order_by(
            WebFluxerXpBoostEvent.created_at.desc()
        ).all()
        s = db.query(WebFluxerGuildSettings).filter_by(guild_id=gid).first()
        levelup_config = {
            'level_up_enabled': bool(s.level_up_enabled) if s else False,
            'level_up_destination': (s.level_up_destination or 'current') if s else 'current',
            'level_up_channel_id': (s.level_up_channel_id or '') if s else '',
            'level_up_message': (s.level_up_message or '') if s else '',
        }
        channels = db.query(WebFluxerGuildChannel).filter_by(guild_id=gid).order_by(
            WebFluxerGuildChannel.channel_name
        ).all()
        return {
            'level_roles': [_level_role_dict(r) for r in level_roles],
            'roles_json': json.dumps([{'id': r.role_id, 'name': r.role_name or r.role_id} for r in roles]),
            'boosts_json': json.dumps([_boost_dict(b) for b in boosts]),
            'levelup_config_json': json.dumps(levelup_config),
            'channels_list': [{'id': c.channel_id, 'name': c.channel_name or c.channel_id} for c in channels],
        }
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_xp.html', 'xp', extra=_extra)


def _welcome_config_dict(c: WebFluxerWelcomeConfig) -> dict:
    return {
        'enabled': bool(c.enabled),
        'welcome_channel_id': c.welcome_channel_id or '',
        'welcome_message': c.welcome_message or '',
        'welcome_embed_enabled': bool(c.welcome_embed_enabled),
        'welcome_embed_title': c.welcome_embed_title or '',
        'welcome_embed_color': c.welcome_embed_color or '#5865F2',
        'welcome_embed_footer': c.welcome_embed_footer or '',
        'welcome_embed_thumbnail': bool(c.welcome_embed_thumbnail),
        'dm_enabled': bool(c.dm_enabled),
        'dm_message': c.dm_message or '',
        'goodbye_enabled': bool(c.goodbye_enabled),
        'goodbye_channel_id': c.goodbye_channel_id or '',
        'goodbye_message': c.goodbye_message or '',
        'auto_role_id': c.auto_role_id or '',
    }


def _default_welcome_config() -> dict:
    return {
        'enabled': False,
        'welcome_channel_id': '',
        'welcome_message': 'Welcome to the server, {user}! You are member #{member_count}.',
        'welcome_embed_enabled': False,
        'welcome_embed_title': 'Welcome!',
        'welcome_embed_color': '#5865F2',
        'welcome_embed_footer': '',
        'welcome_embed_thumbnail': False,
        'dm_enabled': False,
        'dm_message': '',
        'goodbye_enabled': False,
        'goodbye_channel_id': '',
        'goodbye_message': 'Goodbye, {username}. We will miss you!',
        'auto_role_id': '',
    }


@fluxer_guild_required
def fluxer_guild_welcome(request, guild_id):
    def _extra(db, gid):
        cfg = db.query(WebFluxerWelcomeConfig).filter_by(guild_id=gid).first()
        welcome_cfg = _welcome_config_dict(cfg) if cfg else _default_welcome_config()
        return {
            'welcome_vars': _WELCOME_VARS,
            'welcome_config': welcome_cfg,
            'welcome_config_json': json.dumps(welcome_cfg),
        }
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_welcome.html', 'welcome', extra=_extra)


@fluxer_guild_required
def fluxer_guild_moderation(request, guild_id):
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_moderation.html', 'moderation')


@fluxer_guild_required
def fluxer_guild_lfg(request, guild_id):
    def _extra(db, gid):
        net_configs = db.query(WebCommunityBotConfig).filter_by(
            platform='fluxer', guild_id=gid
        ).all()
        lfg_cfg = db.query(WebFluxerLfgConfig).filter_by(guild_id=gid).first()
        return {
            'net_configs': [_config_dict(c) for c in net_configs],
            'publish_to_network': bool(lfg_cfg.publish_to_network) if lfg_cfg else False,
        }
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_lfg.html', 'lfg', extra=_extra)


@fluxer_guild_required
def fluxer_guild_settings_page(request, guild_id):
    def _extra(db, gid):
        roles = db.query(WebFluxerGuildRole).filter_by(guild_id=gid).order_by(
            WebFluxerGuildRole.role_name
        ).all()
        roles_data = [{'value': r.role_id, 'label': r.role_name or r.role_id} for r in roles]
        return {'roles_json': json.dumps(roles_data)}
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_settings.html', 'settings', extra=_extra)


@fluxer_guild_required
def fluxer_guild_bridge(request, guild_id):
    def _extra(db, gid):
        # Current guild's channels for the Fluxer channel picker
        channels = db.query(WebFluxerGuildChannel).filter_by(guild_id=gid).order_by(
            WebFluxerGuildChannel.channel_name
        ).all()
        channels_data = [{'value': c.channel_id, 'label': c.channel_name or c.channel_id} for c in channels]

        # Matrix spaces for the optional Matrix bridge leg
        from .models import WebMatrixSpaceSettings, WebMatrixRoom
        space_rows = db.query(WebMatrixSpaceSettings).filter_by(bot_present=1).order_by(
            WebMatrixSpaceSettings.space_name
        ).all()
        matrix_spaces = []
        for s in space_rows:
            room_rows = db.query(WebMatrixRoom).filter_by(space_id=s.space_id, is_space=0).order_by(
                WebMatrixRoom.room_name
            ).all()
            rooms = [{'value': r.room_id, 'label': r.room_name} for r in room_rows if r.room_name and r.room_name != r.room_id]
            matrix_spaces.append({'id': s.space_id, 'name': s.space_name or s.space_id, 'channels': rooms})

        # Discord guilds: all guilds this user's discord_id is a member of (bot present)
        discord_guilds = []
        discord_id = getattr(request.web_user, 'discord_id', None)
        if discord_id:
            try:
                guild_rows = db.execute(
                    text(
                        "SELECT g.guild_id, COALESCE(NULLIF(g.guild_name,''), CAST(g.guild_id AS CHAR)) as name, "
                        "g.cached_channels FROM guild_members gm "
                        "JOIN guilds g ON g.guild_id = gm.guild_id "
                        "WHERE gm.user_id = :uid AND gm.left_at IS NULL AND g.bot_present = 1 "
                        "ORDER BY name LIMIT 50"
                    ),
                    {'uid': int(discord_id)}
                ).fetchall()
                for gr in guild_rows:
                    channels = []
                    if gr[2]:
                        try:
                            raw = json.loads(gr[2])
                            channels = [
                                {'value': str(c['id']), 'label': c['name']}
                                for c in raw if c.get('type') == 0
                            ]
                        except Exception:
                            pass
                    discord_guilds.append({'id': str(gr[0]), 'name': gr[1], 'channels': channels})
            except Exception:
                pass

        return {
            'channels_json': json.dumps(channels_data),
            'matrix_spaces_json': json.dumps(matrix_spaces),
            'discord_guilds_json': json.dumps(discord_guilds),
        }

    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_bridge.html', 'bridge', extra=_extra)


@fluxer_guild_required
def fluxer_guild_verification(request, guild_id):
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_verification.html', 'verification')


@fluxer_guild_required
def fluxer_guild_reaction_roles(request, guild_id):
    def _extra(db, gid):
        roles = db.query(WebFluxerGuildRole).filter_by(guild_id=gid).order_by(WebFluxerGuildRole.role_name).all()
        return {
            'roles_json': json.dumps([
                {'value': r.role_id, 'label': r.role_name or r.role_id}
                for r in roles
            ])
        }
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_reaction_roles.html', 'reaction_roles', extra=_extra)


@fluxer_guild_required
def fluxer_guild_live_alerts(request, guild_id):
    def _extra(db, gid):
        from .models import WebUser
        rows = (
            db.query(WebCreatorProfile, WebUser.username)
            .join(WebUser, WebUser.id == WebCreatorProfile.user_id)
            .filter(
                WebCreatorProfile.allow_discovery == True,
                WebUser.is_banned == False,
                (WebCreatorProfile.twitch_user_id != None) | (WebCreatorProfile.youtube_channel_id != None),
            )
            .order_by(WebCreatorProfile.follower_count.desc())
            .limit(50)
            .all()
        )
        featured = []
        for c, username in rows:
            if c.twitch_user_id:
                featured.append({
                    'display_name': c.twitch_display_name or c.display_name,
                    'platform': 'twitch',
                    'handle': c.twitch_user_id,
                    'avatar_url': c.avatar_url or '',
                    'profile_url': f'/ql/profile/{username}/',
                    'follower_count': c.twitch_follower_count or 0,
                })
            if c.youtube_channel_id:
                featured.append({
                    'display_name': c.youtube_channel_name or c.display_name,
                    'platform': 'youtube',
                    'handle': c.youtube_channel_id,
                    'avatar_url': c.avatar_url or '',
                    'profile_url': f'/ql/profile/{username}/',
                    'follower_count': c.youtube_subscriber_count or 0,
                })
        return {'featured_creators_json': json.dumps(featured)}
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_live_alerts.html', 'live_alerts', extra=_extra)


@fluxer_guild_required
def fluxer_guild_trackers(request, guild_id):
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_trackers.html', 'trackers')


@fluxer_guild_required
def fluxer_guild_audit(request, guild_id):
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_audit.html', 'audit')


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_audit_logs(request, guild_id):
    """GET paginated audit log entries for a guild."""
    guild_id = guild_id.strip()
    page = safe_int(request.GET.get('page', 1), 1, 1, 1000)
    days = safe_int(request.GET.get('days', 7), 7, 1, 90)
    action_filter = (request.GET.get('action', '') or '').strip()[:64]
    actor_filter = (request.GET.get('actor_id', '') or '').strip()[:64]
    target_filter = (request.GET.get('target_id', '') or '').strip()[:64]
    per_page = 50

    cutoff = int(time.time()) - (days * 86400)
    with get_db_session() as db:
        base_sql = (
            "SELECT action, action_category, actor_id, actor_name, target_id, target_name, "
            "target_type, reason, details, created_at "
            "FROM web_fluxer_audit_log WHERE guild_id = :gid AND created_at >= :cutoff"
        )
        params = {'gid': guild_id, 'cutoff': cutoff}
        if action_filter:
            base_sql += " AND action = :action"
            params['action'] = action_filter
        if actor_filter:
            base_sql += " AND actor_id = :actor_id"
            params['actor_id'] = actor_filter
        if target_filter:
            base_sql += " AND target_id = :target_id"
            params['target_id'] = target_filter

        count_row = db.execute(text("SELECT COUNT(*) FROM (" + base_sql + ") AS sub"), params).fetchone()
        total = count_row[0] if count_row else 0
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        rows = db.execute(
            text(base_sql + " ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
            {**params, 'lim': per_page, 'off': offset}
        ).fetchall()

    logs = []
    for r in rows:
        logs.append({
            'action': r.action,
            'action_category': r.action_category,
            'actor_id': r.actor_id or '',
            'actor_name': r.actor_name or '',
            'target_id': r.target_id or '',
            'target_name': r.target_name or '',
            'target_type': r.target_type or '',
            'reason': r.reason or '',
            'details': r.details or '',
            'created_at': r.created_at,
        })
    return JsonResponse({'logs': logs, 'total': total, 'page': page, 'total_pages': total_pages})


@fluxer_guild_required
def fluxer_guild_roles(request, guild_id):
    return _guild_view(
        request, guild_id,
        'questlog_web/fluxer_guild_soon.html', 'roles',
        extra=lambda db, gid: {'feature': {
            'name': 'Role Management',
            'desc': 'Assign and manage Fluxer server roles directly from the dashboard. Bulk assign, create, and import roles.',
            'icon': 'fas fa-user-tag',
            'color': 'indigo',
        }},
    )


@fluxer_guild_required
def fluxer_guild_messages(request, guild_id):
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_messages.html', 'messages')


@fluxer_guild_required
def fluxer_guild_templates_page(request, guild_id):
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_templates.html', 'templates')


@fluxer_guild_required
def fluxer_guild_raffles(request, guild_id):
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_raffles.html', 'guild_raffles')


@fluxer_guild_required
def fluxer_guild_soon(request, guild_id):
    url_name = request.resolver_match.url_name
    feature = SOON_FEATURES.get(url_name, {
        'name': 'Coming Soon', 'icon': 'fas fa-clock', 'color': 'gray',
        'desc': 'This feature is under development.',
    })
    return _guild_view(
        request, guild_id, 'questlog_web/fluxer_guild_soon.html', 'soon',
        extra=lambda db, gid: {'feature': feature},
    )


# ---------------------------------------------------------------------------
# Settings API
# ---------------------------------------------------------------------------

@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_settings(request, guild_id):
    """GET/POST per-guild Fluxer bot settings."""
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            s = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
            if s:
                return JsonResponse({'settings': _settings_dict(s)})
            # Fetch guild name from channel cache for defaults
            row = db.execute(text(
                "SELECT guild_name FROM web_fluxer_guild_channels WHERE guild_id = :g LIMIT 1"
            ), {'g': guild_id}).fetchone()
            gname = _clean_name(row[0]) or guild_id if row else guild_id
            return JsonResponse({'settings': _default_settings(guild_id, gname)})

    # POST
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Validate channel IDs against known channels
    with get_db_session() as db:
        known_channels = {
            r[0] for r in db.execute(text(
                "SELECT channel_id FROM web_fluxer_guild_channels WHERE guild_id = :g"
            ), {'g': guild_id}).fetchall()
        }

        def _valid_channel(cid):
            return not cid or cid in known_channels

        mod_log = data.get('mod_log_channel_id', '').strip()
        lfg_ch = data.get('lfg_channel_id', '').strip()
        welcome_ch = data.get('welcome_channel_id', '').strip()
        goodbye_ch = data.get('goodbye_channel_id', '').strip()

        for ch_val, ch_name in [
            (mod_log, 'mod_log_channel_id'),
            (lfg_ch, 'lfg_channel_id'),
            (welcome_ch, 'welcome_channel_id'),
            (goodbye_ch, 'goodbye_channel_id'),
        ]:
            if ch_val and ch_val not in known_channels:
                return JsonResponse({'error': f'Unknown channel for {ch_name}'}, status=400)

        # Validate multi-select ignored channels
        ignored_raw = data.get('xp_ignored_channels', [])
        if not isinstance(ignored_raw, list):
            ignored_raw = []
        ignored_channels = [str(c) for c in ignored_raw if str(c) in known_channels]

        now = int(time.time())
        s = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()

        # guild_name is owned by the bot sync (api_internal_guild_names / _sync_guild_channels).
        # On first settings save, pull current value from channels table; never overwrite with form data.
        if s is None:
            row = db.execute(text(
                "SELECT guild_name FROM web_fluxer_guild_channels WHERE guild_id = :g LIMIT 1"
            ), {'g': guild_id}).fetchone()
            bot_name = (row[0] or '').strip() if row else ''
            s = WebFluxerGuildSettings(
                guild_id=guild_id,
                guild_name=bot_name or guild_id,
                created_at=now,
                updated_at=now,
            )
            db.add(s)
        # Partial update: only update fields present in the request body.
        # This allows each feature page to save only its own fields.
        if 'xp_enabled' in data:
            s.xp_enabled = 1 if data['xp_enabled'] else 0
        if 'xp_per_message' in data:
            s.xp_per_message = safe_int(data['xp_per_message'], 2, 1, 50)
        if 'xp_per_reaction' in data:
            s.xp_per_reaction = safe_int(data['xp_per_reaction'], 1, 0, 20)
        if 'xp_per_voice_minute' in data:
            s.xp_per_voice_minute = safe_int(data['xp_per_voice_minute'], 1, 0, 20)
        if 'xp_cooldown_secs' in data:
            s.xp_cooldown_secs = safe_int(data['xp_cooldown_secs'], 60, 10, 3600)
        if 'xp_media_cooldown_secs' in data:
            s.xp_media_cooldown_secs = safe_int(data['xp_media_cooldown_secs'], 60, 10, 3600)
        if 'xp_reaction_cooldown_secs' in data:
            s.xp_reaction_cooldown_secs = safe_int(data['xp_reaction_cooldown_secs'], 60, 10, 3600)
        if 'xp_ignored_channels' in data:
            s.xp_ignored_channels = json.dumps(ignored_channels)
        if 'mod_log_channel_id' in data:
            s.mod_log_channel_id = mod_log or None
        if 'warn_threshold' in data:
            s.warn_threshold = safe_int(data['warn_threshold'], 3, 1, 20)
        if 'auto_ban_after_warns' in data:
            s.auto_ban_after_warns = 1 if data['auto_ban_after_warns'] else 0
        if 'lfg_channel_id' in data:
            s.lfg_channel_id = lfg_ch or None
        if 'welcome_channel_id' in data:
            s.welcome_channel_id = welcome_ch or None
        if 'welcome_message' in data:
            s.welcome_message = sanitize_text(data.get('welcome_message', '') or '')[:1000] or None
        if 'goodbye_channel_id' in data:
            s.goodbye_channel_id = goodbye_ch or None
        if 'goodbye_message' in data:
            s.goodbye_message = sanitize_text(data.get('goodbye_message', '') or '')[:1000] or None
        if 'bot_prefix' in data:
            s.bot_prefix = (data['bot_prefix'] or '!')[:10]
        if 'language' in data:
            s.language = (data['language'] or 'en')[:10]
        if 'timezone' in data:
            s.timezone = (data['timezone'] or 'UTC')[:50]
        # XP source toggles + gaming/media XP
        if 'track_messages' in data:
            s.track_messages = 1 if data['track_messages'] else 0
        if 'track_media' in data:
            s.track_media = 1 if data['track_media'] else 0
        if 'track_reactions' in data:
            s.track_reactions = 1 if data['track_reactions'] else 0
        if 'track_voice' in data:
            s.track_voice = 1 if data['track_voice'] else 0
        if 'track_gaming' in data:
            s.track_gaming = 1 if data['track_gaming'] else 0
        if 'xp_per_media' in data:
            s.xp_per_media = safe_int(data['xp_per_media'], 3, 0, 50)
        if 'xp_per_gaming_hour' in data:
            s.xp_per_gaming_hour = safe_int(data['xp_per_gaming_hour'], 10, 0, 100)
        # Token customization
        if 'token_name' in data:
            s.token_name = sanitize_text(data.get('token_name', '') or 'Hero Tokens')[:50] or 'Hero Tokens'
        if 'token_emoji' in data:
            s.token_emoji = (data.get('token_emoji', '') or ':coin:')[:20] or ':coin:'
        # Member management
        if 'role_persistence_enabled' in data:
            s.role_persistence_enabled = 1 if data['role_persistence_enabled'] else 0
        if 'admin_roles' in data:
            raw_ar = data.get('admin_roles', [])
            if not isinstance(raw_ar, list):
                raw_ar = []
            s.admin_roles = json.dumps([str(r)[:32] for r in raw_ar][:50])
        if 'channel_notify_channel_id' in data:
            cncid = (data.get('channel_notify_channel_id', '') or '').strip()
            if cncid and cncid not in known_channels:
                return JsonResponse({'error': 'Unknown channel for channel_notify_channel_id'}, status=400)
            s.channel_notify_channel_id = cncid or None
        if 'temp_voice_category_ids' in data:
            raw_tvc = data.get('temp_voice_category_ids', [])
            if not isinstance(raw_tvc, list):
                raw_tvc = []
            s.temp_voice_category_ids = json.dumps([str(c)[:32] for c in raw_tvc][:20])
        if 'discovery_enabled' in data:
            s.discovery_enabled = 1 if data['discovery_enabled'] else 0
        if 'flair_sync_enabled' in data:
            s.flair_sync_enabled = 1 if data['flair_sync_enabled'] else 0
        if 'audit_log_enabled' in data:
            s.audit_logging_enabled = 1 if data['audit_log_enabled'] else 0
        if 'audit_log_channel_id' in data:
            audit_ch = (data.get('audit_log_channel_id', '') or '').strip()
            s.audit_log_channel_id = audit_ch[:32] if audit_ch and audit_ch in known_channels else None
        # Creator Discovery JSON blob - update any provided keys
        _CD_KEYS = set(_CREATOR_DISCOVERY_DEFAULTS.keys())
        cd_keys_in_data = _CD_KEYS & set(data.keys())
        if cd_keys_in_data:
            existing_cd = _parse_creator_discovery(getattr(s, 'creator_discovery_json', None))
            for k in cd_keys_in_data:
                v = data[k]
                if k.endswith('_channel_id'):
                    v = str(v).strip()[:32] if v else ''
                elif k.endswith('_hours') or k.endswith('_day') or k.endswith('_max_announcements') or k == 'game_max_announcements':
                    v = safe_int(v, existing_cd.get(k, 0), 0, 8760)
                elif isinstance(existing_cd.get(k), bool):
                    v = bool(v)
                else:
                    v = sanitize_text(str(v))[:1000] if v else ''
                existing_cd[k] = v
            s.creator_discovery_json = json.dumps(existing_cd)
        s.updated_at = now

        db.commit()
        db.refresh(s)

        # Upsert WebFluxerWelcomeConfig if any welcome/goodbye extended fields are present
        _WELCOME_CONFIG_FIELDS = {
            'welcome_enabled', 'welcome_embed_enabled', 'welcome_embed_title',
            'welcome_embed_color', 'welcome_embed_footer', 'welcome_embed_thumbnail',
            'dm_enabled', 'dm_message', 'goodbye_enabled', 'auto_role_id',
        }
        if _WELCOME_CONFIG_FIELDS & set(data.keys()):
            wc = db.query(WebFluxerWelcomeConfig).filter_by(guild_id=guild_id).first()
            if wc is None:
                wc = WebFluxerWelcomeConfig(guild_id=guild_id, updated_at=now)
                db.add(wc)
            if 'welcome_enabled' in data:
                wc.enabled = 1 if data['welcome_enabled'] else 0
            if 'welcome_channel_id' in data:
                wc.welcome_channel_id = welcome_ch or None
            if 'welcome_message' in data:
                wc.welcome_message = sanitize_text(data.get('welcome_message', '') or '')[:2000] or None
            if 'welcome_embed_enabled' in data:
                wc.welcome_embed_enabled = 1 if data['welcome_embed_enabled'] else 0
            if 'welcome_embed_title' in data:
                wc.welcome_embed_title = sanitize_text(data.get('welcome_embed_title', '') or '')[:200] or None
            if 'welcome_embed_color' in data:
                wc.welcome_embed_color = (data.get('welcome_embed_color', '') or '')[:10] or None
            if 'welcome_embed_footer' in data:
                wc.welcome_embed_footer = sanitize_text(data.get('welcome_embed_footer', '') or '')[:300] or None
            if 'welcome_embed_thumbnail' in data:
                wc.welcome_embed_thumbnail = 1 if data['welcome_embed_thumbnail'] else 0
            if 'dm_enabled' in data:
                wc.dm_enabled = 1 if data['dm_enabled'] else 0
            if 'dm_message' in data:
                wc.dm_message = sanitize_text(data.get('dm_message', '') or '')[:2000] or None
            if 'goodbye_enabled' in data:
                wc.goodbye_enabled = 1 if data['goodbye_enabled'] else 0
            if 'goodbye_channel_id' in data:
                wc.goodbye_channel_id = goodbye_ch or None
            if 'goodbye_message' in data:
                wc.goodbye_message = sanitize_text(data.get('goodbye_message', '') or '')[:2000] or None
            if 'auto_role_id' in data:
                wc.auto_role_id = (data.get('auto_role_id', '') or '').strip() or None
            wc.updated_at = now
            db.commit()

        # Upsert WebFluxerVerificationConfig if any verification fields are present
        _VERIF_CONFIG_FIELDS = {
            'verification_type', 'verification_channel_id', 'verified_role_id',
            'account_age_days', 'verified_message', 'failed_message',
        }
        if _VERIF_CONFIG_FIELDS & set(data.keys()):
            vc = db.query(WebFluxerVerificationConfig).filter_by(guild_id=guild_id).first()
            if vc is None:
                vc = WebFluxerVerificationConfig(guild_id=guild_id, updated_at=now)
                db.add(vc)
            if 'verification_type' in data:
                vtype = (data.get('verification_type', '') or '').strip()
                if vtype in ('none', 'button', 'age'):
                    vc.verification_type = vtype
            if 'verification_channel_id' in data:
                verif_ch = (data.get('verification_channel_id', '') or '').strip()
                if verif_ch and verif_ch not in known_channels:
                    return JsonResponse({'error': 'Unknown verification_channel_id'}, status=400)
                vc.verification_channel_id = verif_ch or None
            if 'verified_role_id' in data:
                vc.verified_role_id = (data.get('verified_role_id', '') or '').strip() or None
            if 'account_age_days' in data:
                vc.account_age_days = safe_int(data['account_age_days'], 7, 0, 365)
            if 'verified_message' in data:
                vc.verified_message = sanitize_text(data.get('verified_message', '') or '')[:1000] or None
            if 'failed_message' in data:
                vc.failed_message = sanitize_text(data.get('failed_message', '') or '')[:1000] or None
            vc.updated_at = now
            db.commit()

        return JsonResponse({'success': True, 'settings': _settings_dict(s)})


# ---------------------------------------------------------------------------
# LFG Games API (ADMIN - per Fluxer guild)
# ---------------------------------------------------------------------------

def _lfg_game_dict(g: WebFluxerLfgGame) -> dict:
    return {
        'id': g.id,
        'guild_id': g.guild_id,
        'name': g.name,
        'igdb_id': g.igdb_id or '',
        'game_short': g.game_short or '',
        'platforms': g.platforms or '',
        'emoji': g.emoji or '',
        'cover_url': g.cover_url or '',
        'channel_id': g.channel_id or '',
        'notify_role_id': g.notify_role_id or '',
        'max_group_size': g.max_group_size,
        'auto_archive_hours': g.auto_archive_hours if g.auto_archive_hours is not None else 24,
        'has_roles': bool(g.has_roles),
        'tank_slots': g.tank_slots,
        'healer_slots': g.healer_slots,
        'dps_slots': g.dps_slots,
        'support_slots': g.support_slots,
        'require_rank': bool(g.require_rank) if g.require_rank is not None else False,
        'rank_label': g.rank_label or '',
        'rank_min': g.rank_min,
        'rank_max': g.rank_max,
        'is_custom_game': bool(g.is_custom_game) if g.is_custom_game is not None else False,
        'enabled': bool(g.enabled) if g.enabled is not None else True,
        'custom_options': json.loads(g.options_json) if g.options_json else [],
        'options': json.loads(g.options_json) if g.options_json else [],
        'is_active': bool(g.is_active),
        'created_at': g.created_at,
        'receive_network_lfg': bool(g.receive_network_lfg),
    }


# ---------------------------------------------------------------------------
# Level Roles API
# ---------------------------------------------------------------------------

def _level_role_dict(lr: WebFluxerLevelRole) -> dict:
    return {
        'id': lr.id,
        'guild_id': lr.guild_id,
        'level_required': lr.level_required,
        'role_id': lr.role_id,
        'role_name': lr.role_name or '',
        'remove_previous': bool(lr.remove_previous),
        'created_at': lr.created_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_level_roles(request, guild_id):
    """
    GET  - list level roles for a guild
    POST - create or update a level role (upsert by level_required)
    """
    guild_id = guild_id.strip()
    with get_db_session() as db:
        if request.method == 'GET':
            rows = db.query(WebFluxerLevelRole).filter_by(guild_id=guild_id).order_by(
                WebFluxerLevelRole.level_required
            ).all()
            return JsonResponse({'level_roles': [_level_role_dict(r) for r in rows]})

        # POST
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        level_required = safe_int(data.get('level_required'), None, 1, 9999)
        if level_required is None:
            return JsonResponse({'error': 'level_required must be 1-9999'}, status=400)

        role_id = (data.get('role_id', '') or '').strip()[:32]
        if not role_id:
            return JsonResponse({'error': 'role_id required'}, status=400)

        role_name = sanitize_text(data.get('role_name', '') or '')[:200]
        remove_previous = bool(data.get('remove_previous', False))
        now = int(time.time())

        existing = db.query(WebFluxerLevelRole).filter_by(
            guild_id=guild_id, level_required=level_required
        ).first()
        if existing:
            existing.role_id = role_id
            existing.role_name = role_name
            existing.remove_previous = 1 if remove_previous else 0
        else:
            existing = WebFluxerLevelRole(
                guild_id=guild_id,
                level_required=level_required,
                role_id=role_id,
                role_name=role_name,
                remove_previous=1 if remove_previous else 0,
                created_at=now,
            )
            db.add(existing)
        db.commit()
        db.refresh(existing)
        return JsonResponse({'success': True, 'level_role': _level_role_dict(existing)})


@fluxer_guild_required
@require_http_methods(['DELETE'])
def api_fluxer_guild_level_role_detail(request, guild_id, lr_id):
    """DELETE a level role."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        lr = db.query(WebFluxerLevelRole).filter_by(id=lr_id, guild_id=guild_id).first()
        if not lr:
            return JsonResponse({'error': 'Not found'}, status=404)
        db.delete(lr)
        db.commit()
        return JsonResponse({'success': True})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_level_roles_bulk(request, guild_id):
    """Bulk-add level roles from a list."""
    guild_id = guild_id.strip()
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    entries = data.get('level_roles', [])
    if not isinstance(entries, list):
        return JsonResponse({'error': 'level_roles must be a list'}, status=400)

    now = int(time.time())
    saved = []
    with get_db_session() as db:
        for entry in entries[:100]:
            level_required = safe_int(entry.get('level_required'), None, 1, 9999)
            role_id = (entry.get('role_id', '') or '').strip()[:32]
            if not level_required or not role_id:
                continue
            role_name = sanitize_text(entry.get('role_name', '') or '')[:200]
            remove_previous = bool(entry.get('remove_previous', False))
            existing = db.query(WebFluxerLevelRole).filter_by(
                guild_id=guild_id, level_required=level_required
            ).first()
            if existing:
                existing.role_id = role_id
                existing.role_name = role_name
                existing.remove_previous = 1 if remove_previous else 0
                saved.append(_level_role_dict(existing))
            else:
                new_lr = WebFluxerLevelRole(
                    guild_id=guild_id,
                    level_required=level_required,
                    role_id=role_id,
                    role_name=role_name,
                    remove_previous=1 if remove_previous else 0,
                    created_at=now,
                )
                db.add(new_lr)
                db.flush()
                saved.append(_level_role_dict(new_lr))
        db.commit()
    return JsonResponse({'success': True, 'saved': len(saved), 'level_roles': saved})


# ---------------------------------------------------------------------------
# Member XP API (ADMIN - per Fluxer guild)
# ---------------------------------------------------------------------------

@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_member_xp(request, guild_id):
    """
    GET  - list leaderboard (top 200 by XP) from fluxer_member_xp, joined with web_users for HP
    POST - bulk update XP and/or hero_points
           body: { "updates": [{ "user_id": "...", "xp": N, "hp": N }, ...] }  (max 100)
           xp is written to fluxer_member_xp; hp is written to web_users via fluxer_id link
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            # Check if this guild's community has unified XP enabled
            community = db.execute(text(
                "SELECT site_xp_to_guild FROM web_communities "
                "WHERE platform='fluxer' AND platform_id=:g AND network_status='approved' AND is_active=1 LIMIT 1"
            ), {'g': guild_id}).fetchone()
            is_unified = bool(community and community[0])

            _HIDDEN_FLUXER_IDS = ['1473922619936604188']
            _HIDDEN_USER_IDS = [1]

            if is_unified:
                # Unified mode: prefer web_unified_leaderboard for linked users,
                # but include ALL fluxer_member_xp rows so unlinked members still appear.
                rows = db.execute(text("""
                    SELECT
                        COALESCE(wu.id, 0) AS user_id,
                        COALESCE(wu.username, fx.username) AS username,
                        COALESCE(ul.xp_total, fx.xp) AS xp,
                        COALESCE(wu.web_level, fx.level) AS level,
                        COALESCE(ul.messages, fx.message_count) AS message_count,
                        COALESCE(wu.hero_points, 0) AS hero_points
                    FROM fluxer_member_xp fx
                    LEFT JOIN web_users wu
                        ON wu.fluxer_id COLLATE utf8mb4_general_ci = fx.user_id COLLATE utf8mb4_general_ci
                    LEFT JOIN web_unified_leaderboard ul
                        ON ul.user_id = wu.id AND ul.guild_id = :g AND ul.platform = 'fluxer'
                    WHERE fx.guild_id = :gi
                    AND fx.user_id NOT IN :hidden_fid
                    AND (wu.id IS NULL OR wu.id NOT IN :hidden_uid)
                    ORDER BY xp DESC LIMIT 200
                """), {'g': guild_id, 'gi': int(guild_id),
                       'hidden_fid': tuple(_HIDDEN_FLUXER_IDS + ['']),
                       'hidden_uid': tuple(_HIDDEN_USER_IDS + [0])}).fetchall()
                members = [
                    {
                        'user_id': str(r[0]),
                        'username': r[1] or str(r[0]),
                        'xp': int(r[2] or 0),
                        'level': int(r[3] or 1),
                        'message_count': int(r[4] or 0),
                        'hero_points': int(r[5] or 0),
                        'unified': True,
                    }
                    for r in rows
                ]
            else:
                rows = db.execute(text(
                    "SELECT m.user_id, m.username, m.xp, m.level, m.message_count, "
                    "       COALESCE(wu.hero_points, 0) AS hero_points "
                    "FROM fluxer_member_xp m "
                    "LEFT JOIN web_users wu ON wu.fluxer_id COLLATE utf8mb4_general_ci = m.user_id COLLATE utf8mb4_general_ci "
                    "WHERE m.guild_id = :g "
                    "AND m.user_id NOT IN :hidden_fid "
                    "ORDER BY m.xp DESC LIMIT 200"
                ), {'g': guild_id, 'hidden_fid': tuple(_HIDDEN_FLUXER_IDS + [''])}).fetchall()
                members = [
                    {
                        'user_id': str(r[0]),
                        'username': r[1] or str(r[0]),
                        'xp': int(r[2]),
                        'level': int(r[3]),
                        'message_count': int(r[4]),
                        'hero_points': int(r[5]),
                        'unified': False,
                    }
                    for r in rows
                ]
        return JsonResponse({'success': True, 'members': members, 'unified': is_unified})

    # POST - bulk update
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    updates = data.get('updates', [])
    if not isinstance(updates, list) or len(updates) > 100:
        return JsonResponse({'success': False, 'error': 'Provide 1-100 updates'}, status=400)

    applied = 0
    with get_db_session() as db:
        for item in updates:
            try:
                uid = int(item.get('user_id', 0))
                if not uid:
                    continue
                uid_str = str(uid)
                changed = False

                if 'xp' in item:
                    new_xp = max(0, int(item['xp']))
                    db.execute(text(
                        "UPDATE fluxer_member_xp SET xp = :xp WHERE guild_id = :g AND user_id = :u"
                    ), {'xp': new_xp, 'g': guild_id, 'u': uid})
                    changed = True

                if 'hp' in item:
                    new_hp = max(0, int(item['hp']))
                    db.execute(text(
                        "UPDATE web_users SET hero_points = :hp WHERE fluxer_id = :fid"
                    ), {'hp': new_hp, 'fid': uid_str})
                    changed = True

                if changed:
                    applied += 1
            except (TypeError, ValueError):
                continue
        db.commit()

    return JsonResponse({'success': True, 'updated': applied})


# ---------------------------------------------------------------------------
# Level-Up Message Config API
# ---------------------------------------------------------------------------

@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_levelup_config(request, guild_id):
    """
    GET  - return level-up message config for this guild
    POST - save level-up message config
    """
    guild_id = guild_id.strip()
    VALID_DEST = {'current', 'channel', 'dm', 'none'}

    if request.method == 'GET':
        with get_db_session() as db:
            s = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
        if not s:
            return JsonResponse({'success': True, 'config': {
                'level_up_enabled': False, 'level_up_destination': 'current',
                'level_up_channel_id': '', 'level_up_message': '',
            }})
        return JsonResponse({'success': True, 'config': {
            'level_up_enabled': bool(s.level_up_enabled),
            'level_up_destination': s.level_up_destination or 'current',
            'level_up_channel_id': s.level_up_channel_id or '',
            'level_up_message': s.level_up_message or '',
        }})

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    dest = data.get('level_up_destination', 'current')
    if dest not in VALID_DEST:
        dest = 'current'

    with get_db_session() as db:
        s = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
        if not s:
            return JsonResponse({'success': False, 'error': 'Guild not found'}, status=404)
        s.level_up_enabled = 1 if data.get('level_up_enabled') else 0
        s.level_up_destination = dest
        s.level_up_channel_id = sanitize_text(str(data.get('level_up_channel_id') or ''))[:25] or None
        msg = data.get('level_up_message', '') or ''
        s.level_up_message = sanitize_text(msg)[:1000] or None
        s.updated_at = int(time.time())
        db.commit()

    return JsonResponse({'success': True})


# ---------------------------------------------------------------------------
# XP Boost Events API
# ---------------------------------------------------------------------------

def _boost_dict(b: WebFluxerXpBoostEvent) -> dict:
    return {
        'id': b.id,
        'guild_id': b.guild_id,
        'name': b.name,
        'multiplier': b.multiplier,
        'is_active': bool(b.is_active),
        'start_time': b.start_time,
        'end_time': b.end_time,
        'created_at': b.created_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_xp_boosts(request, guild_id):
    """
    GET  - list all boost events for this guild
    POST - create a new boost event
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            boosts = db.query(WebFluxerXpBoostEvent).filter_by(guild_id=guild_id).order_by(
                WebFluxerXpBoostEvent.created_at.desc()
            ).all()
        return JsonResponse({'success': True, 'boosts': [_boost_dict(b) for b in boosts]})

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    name = sanitize_text(str(data.get('name', '') or '').strip())[:100]
    if not name:
        return JsonResponse({'success': False, 'error': 'Name required'}, status=400)
    multiplier = max(2, min(10, safe_int(data.get('multiplier'), 2, 2, 10)))
    is_active = 1 if data.get('is_active') else 0
    start_time = safe_int(data.get('start_time'), None) if data.get('start_time') else None
    end_time = safe_int(data.get('end_time'), None) if data.get('end_time') else None

    with get_db_session() as db:
        boost = WebFluxerXpBoostEvent(
            guild_id=guild_id,
            name=name,
            multiplier=multiplier,
            is_active=is_active,
            start_time=start_time,
            end_time=end_time,
            created_at=int(time.time()),
            created_by=request.web_user.id if request.web_user else None,
        )
        db.add(boost)
        db.flush()
        result = _boost_dict(boost)
        db.commit()

    return JsonResponse({'success': True, 'boost': result}, status=201)


@fluxer_guild_required
@require_http_methods(['PATCH', 'DELETE'])
def api_fluxer_guild_xp_boost_detail(request, guild_id, boost_id):
    """
    PATCH  - update boost (name, multiplier, is_active, start_time, end_time)
    DELETE - remove boost
    """
    guild_id = guild_id.strip()

    with get_db_session() as db:
        boost = db.query(WebFluxerXpBoostEvent).filter_by(id=boost_id, guild_id=guild_id).first()
        if not boost:
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.delete(boost)
            db.commit()
            return JsonResponse({'success': True})

        # PATCH
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        if 'name' in data:
            boost.name = sanitize_text(str(data['name'] or '').strip())[:100] or boost.name
        if 'multiplier' in data:
            boost.multiplier = max(2, min(10, safe_int(data['multiplier'], 2, 2, 10)))
        if 'is_active' in data:
            boost.is_active = 1 if data['is_active'] else 0
        if 'start_time' in data:
            boost.start_time = safe_int(data['start_time'], None) if data['start_time'] else None
        if 'end_time' in data:
            boost.end_time = safe_int(data['end_time'], None) if data['end_time'] else None

        result = _boost_dict(boost)
        db.commit()

    return JsonResponse({'success': True, 'boost': result})


# ---------------------------------------------------------------------------
# LFG Games API (ADMIN - per Fluxer guild)
# ---------------------------------------------------------------------------

@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_live_info(request, guild_id):
    """
    GET - return guild stats (member_count) from web_fluxer_guild_settings,
    which is kept up-to-date by the bot's member join/leave events.
    """
    guild_id = guild_id.strip()
    with get_db_session() as db:
        member_count = db.execute(
            text("SELECT COUNT(DISTINCT user_id) FROM fluxer_member_xp WHERE guild_id = :g"),
            {'g': guild_id}
        ).scalar() or 0
    return JsonResponse({'success': True, 'member_count': member_count})


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_lfg_games(request, guild_id):
    """
    GET  - list LFG games configured for a Fluxer guild
    POST - add a new LFG game
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            games = db.query(WebFluxerLfgGame).filter_by(guild_id=guild_id, is_active=1).order_by(
                WebFluxerLfgGame.name
            ).all()
            return JsonResponse({'success': True, 'games': [_lfg_game_dict(g) for g in games]})

    # POST
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = sanitize_text(data.get('name', '') or '').strip()[:100]
    if not name:
        return JsonResponse({'error': 'name is required'}, status=400)

    igdb_id = (data.get('igdb_id', '') or '').strip()[:20]
    game_short = (data.get('game_short', '') or '').strip().upper()[:20]
    platforms = (data.get('platforms', '') or '').strip()[:500]
    emoji = (data.get('emoji', '') or '').strip()[:100]
    cover_url = (data.get('cover_url', '') or '').strip()[:500]
    if cover_url and not cover_url.startswith('https://'):
        cover_url = ''
    channel_id = (data.get('channel_id', '') or '').strip()[:32]
    notify_role_id = (data.get('notify_role_id', '') or '').strip()[:32]
    max_group_size = safe_int(data.get('max_group_size', 5), default=5, min_val=2, max_val=100)
    auto_archive_hours = safe_int(data.get('auto_archive_hours', 24), default=24, min_val=1, max_val=168)
    has_roles = bool(data.get('has_roles', False))
    tank_slots = safe_int(data.get('tank_slots', 0), default=0, min_val=0, max_val=20)
    healer_slots = safe_int(data.get('healer_slots', 0), default=0, min_val=0, max_val=20)
    dps_slots = safe_int(data.get('dps_slots', 0), default=0, min_val=0, max_val=20)
    support_slots = safe_int(data.get('support_slots', 0), default=0, min_val=0, max_val=20)
    require_rank = bool(data.get('require_rank', False))
    rank_label = (data.get('rank_label', '') or '').strip()[:50]
    rank_min = safe_int(data.get('rank_min', None), default=None) if data.get('rank_min') is not None else None
    rank_max = safe_int(data.get('rank_max', None), default=None) if data.get('rank_max') is not None else None
    is_custom_game = bool(data.get('is_custom_game', False))
    enabled = bool(data.get('enabled', True))
    receive_network_lfg = bool(data.get('receive_network_lfg', False))
    custom_options = data.get('custom_options', data.get('options', []))
    if not isinstance(custom_options, list):
        custom_options = []

    now = int(time.time())
    with get_db_session() as db:
        game = WebFluxerLfgGame(
            guild_id=guild_id,
            name=name,
            igdb_id=igdb_id or None,
            game_short=game_short or None,
            platforms=platforms or None,
            emoji=emoji or None,
            cover_url=cover_url or None,
            channel_id=channel_id or None,
            notify_role_id=notify_role_id or None,
            max_group_size=max_group_size,
            auto_archive_hours=auto_archive_hours,
            has_roles=1 if has_roles else 0,
            tank_slots=tank_slots,
            healer_slots=healer_slots,
            dps_slots=dps_slots,
            support_slots=support_slots,
            require_rank=1 if require_rank else 0,
            rank_label=rank_label or None,
            rank_min=rank_min,
            rank_max=rank_max,
            is_custom_game=1 if is_custom_game else 0,
            enabled=1 if enabled else 0,
            receive_network_lfg=1 if receive_network_lfg else 0,
            options_json=json.dumps(custom_options) if custom_options else None,
            is_active=1,
            created_at=now,
        )
        db.add(game)
        db.commit()
        db.refresh(game)
        return JsonResponse({'success': True, 'game': _lfg_game_dict(game)}, status=201)


@fluxer_guild_required
@require_http_methods(['GET', 'PUT', 'DELETE'])
def api_fluxer_guild_lfg_game_detail(request, guild_id, game_id):
    """
    GET    - fetch a single LFG game
    PUT    - update a configured LFG game
    DELETE - remove (soft-delete) a configured LFG game
    """
    guild_id = guild_id.strip()
    game_id = safe_int(game_id, default=0)
    if not game_id:
        return JsonResponse({'error': 'Invalid game_id'}, status=400)

    with get_db_session() as db:
        game = db.query(WebFluxerLfgGame).filter_by(id=game_id, guild_id=guild_id).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            game.is_active = 0
            db.commit()
            return JsonResponse({'success': True})

        if request.method == 'GET':
            return JsonResponse({'success': True, 'game': _lfg_game_dict(game)})

        # PUT
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'name' in data:
            v = sanitize_text(data['name'] or '').strip()[:100]
            if v:
                game.name = v
        if 'igdb_id' in data:
            game.igdb_id = (data['igdb_id'] or '').strip()[:20] or None
        if 'game_short' in data:
            game.game_short = (data['game_short'] or '').strip().upper()[:20] or None
        if 'platforms' in data:
            game.platforms = (data['platforms'] or '').strip()[:500] or None
        if 'emoji' in data:
            game.emoji = (data['emoji'] or '').strip()[:100] or None
        if 'cover_url' in data:
            v = (data['cover_url'] or '').strip()[:500]
            game.cover_url = v if v.startswith('https://') else None
        if 'channel_id' in data:
            game.channel_id = (data['channel_id'] or '').strip()[:32] or None
        if 'notify_role_id' in data:
            game.notify_role_id = (data['notify_role_id'] or '').strip()[:32] or None
        if 'max_group_size' in data:
            game.max_group_size = safe_int(data['max_group_size'], default=5, min_val=2, max_val=100)
        if 'auto_archive_hours' in data:
            game.auto_archive_hours = safe_int(data['auto_archive_hours'], default=24, min_val=1, max_val=168)
        if 'has_roles' in data:
            game.has_roles = 1 if data['has_roles'] else 0
        if 'tank_slots' in data:
            game.tank_slots = safe_int(data['tank_slots'], default=0, min_val=0, max_val=20)
        if 'healer_slots' in data:
            game.healer_slots = safe_int(data['healer_slots'], default=0, min_val=0, max_val=20)
        if 'dps_slots' in data:
            game.dps_slots = safe_int(data['dps_slots'], default=0, min_val=0, max_val=20)
        if 'support_slots' in data:
            game.support_slots = safe_int(data['support_slots'], default=0, min_val=0, max_val=20)
        if 'require_rank' in data:
            game.require_rank = 1 if data['require_rank'] else 0
        if 'rank_label' in data:
            game.rank_label = (data['rank_label'] or '').strip()[:50] or None
        if 'rank_min' in data:
            game.rank_min = safe_int(data['rank_min'], default=None) if data['rank_min'] is not None else None
        if 'rank_max' in data:
            game.rank_max = safe_int(data['rank_max'], default=None) if data['rank_max'] is not None else None
        if 'is_custom_game' in data:
            game.is_custom_game = 1 if data['is_custom_game'] else 0
        if 'enabled' in data:
            game.enabled = 1 if data['enabled'] else 0
        if 'receive_network_lfg' in data:
            game.receive_network_lfg = 1 if data['receive_network_lfg'] else 0
        for key in ('custom_options', 'options'):
            if key in data:
                v = data[key]
                if isinstance(v, list):
                    game.options_json = json.dumps(v) if v else None
                break

        db.commit()
        db.refresh(game)
        return JsonResponse({'success': True, 'game': _lfg_game_dict(game)})


# ---------------------------------------------------------------------------
# IGDB Search Proxy (ADMIN - Fluxer LFG)
# ---------------------------------------------------------------------------

@fluxer_guild_required
@require_http_methods(['GET'])
@ratelimit(key='user', rate='20/h', method='GET', block=True)
def api_fluxer_igdb_search(request):
    """GET /ql/api/dashboard/fluxer/igdb-search/?q=query - Search IGDB for games.
    Delegates to the same search_games utility used by api_igdb_search in views_discovery.py.
    """
    from app.utils.igdb import search_games

    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'error': 'Query too short', 'games': []})

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # 8-second timeout prevents hung threads if IGDB API is slow
            games = loop.run_until_complete(
                asyncio.wait_for(search_games(query, limit=10), timeout=8.0)
            )
        finally:
            loop.close()

        games_data = [{
            'id': g.id,
            'name': g.name,
            'cover_url': g.cover_url,
            'platforms': ', '.join(g.platforms[:3]) if g.platforms else '',
            'release_year': g.release_year,
            'steam_id': g.steam_id,
        } for g in games]

        return JsonResponse({'success': True, 'games': games_data})
    except asyncio.TimeoutError:
        return JsonResponse({'error': 'IGDB search timed out', 'games': []}, status=504)
    except Exception as e:
        logger.error(f"IGDB search error: {e}", exc_info=True)
        return JsonResponse({'error': 'IGDB search failed', 'games': []})


# ---------------------------------------------------------------------------
# LFG Attendance Config / Stats / Blacklist (ADMIN)
# ---------------------------------------------------------------------------

def _lfg_config_dict(c: WebFluxerLfgConfig) -> dict:
    return {
        'attendance_enabled': bool(c.attendance_enabled),
        'require_confirmation': bool(c.require_confirmation),
        'auto_noshow_hours': c.auto_noshow_hours,
        'warn_at_reliability': c.warn_at_reliability,
        'min_required_score': c.min_required_score,
        'auto_blacklist_noshow': c.auto_blacklist_noshow,
        'publish_to_network': bool(getattr(c, 'publish_to_network', 0)),
    }


def _member_stats_dict(s: WebFluxerLfgMemberStats) -> dict:
    return {
        'id': s.id,
        'fluxer_user_id': s.fluxer_user_id,
        'display_name': s.display_name or '',
        'total_signups': s.total_signups,
        'showed_count': s.showed_count,
        'no_show_count': s.no_show_count,
        'late_count': s.late_count,
        'cancelled_count': s.cancelled_count,
        'pardoned_count': s.pardoned_count,
        'reliability_score': s.reliability_score,
        'is_blacklisted': bool(s.is_blacklisted),
        'blacklist_reason': s.blacklist_reason or '',
        'blacklisted_at': s.blacklisted_at,
        'updated_at': s.updated_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_lfg_config(request, guild_id):
    """GET/POST attendance tracking configuration for a Fluxer guild."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        if request.method == 'GET':
            cfg = db.query(WebFluxerLfgConfig).filter_by(guild_id=guild_id).first()
            if not cfg:
                return JsonResponse({'success': True, 'config': {
                    'attendance_enabled': False,
                    'require_confirmation': False,
                    'auto_noshow_hours': 1,
                    'warn_at_reliability': 50,
                    'min_required_score': 0,
                    'auto_blacklist_noshow': 0,
                    'publish_to_network': False,
                }})
            return JsonResponse({'success': True, 'config': _lfg_config_dict(cfg)})

        # POST
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        cfg = db.query(WebFluxerLfgConfig).filter_by(guild_id=guild_id).first()
        if not cfg:
            cfg = WebFluxerLfgConfig(guild_id=guild_id)
            db.add(cfg)

        if 'attendance_enabled' in data:
            cfg.attendance_enabled = 1 if data['attendance_enabled'] else 0
        if 'require_confirmation' in data:
            cfg.require_confirmation = 1 if data['require_confirmation'] else 0
        if 'auto_noshow_hours' in data:
            cfg.auto_noshow_hours = safe_int(data['auto_noshow_hours'], default=1, min_val=0, max_val=24)
        if 'warn_at_reliability' in data:
            cfg.warn_at_reliability = safe_int(data['warn_at_reliability'], default=50, min_val=0, max_val=100)
        if 'min_required_score' in data:
            cfg.min_required_score = safe_int(data['min_required_score'], default=0, min_val=0, max_val=100)
        if 'auto_blacklist_noshow' in data:
            cfg.auto_blacklist_noshow = safe_int(data['auto_blacklist_noshow'], default=0, min_val=0, max_val=20)
        if 'publish_to_network' in data:
            cfg.publish_to_network = 1 if data['publish_to_network'] else 0
        cfg.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'success': True, 'config': _lfg_config_dict(cfg)})


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_network_lfg(request, guild_id):
    """GET/POST the QuestLog Network LFG broadcast subscription for this Fluxer guild."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        if request.method == 'GET':
            row = db.execute(
                text("SELECT channel_id, channel_name, is_enabled FROM web_community_bot_configs "
                     "WHERE platform='fluxer' AND guild_id=:g AND event_type='lfg_announce' LIMIT 1"),
                {'g': guild_id},
            ).fetchone()
            if not row:
                return JsonResponse({'is_enabled': False, 'channel_id': '', 'channel_name': ''})
            return JsonResponse({
                'is_enabled': bool(row[2]),
                'channel_id': row[0] or '',
                'channel_name': row[1] or '',
            })

        # POST
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        is_enabled = bool(data.get('is_enabled', False))
        channel_id = str(data.get('channel_id', '') or '').strip()
        if is_enabled and not channel_id:
            return JsonResponse({'error': 'Channel required when enabling'}, status=400)

        # Resolve channel name from cached channels
        settings = db.execute(
            text("SELECT cached_channels, guild_name FROM web_fluxer_guild_settings WHERE guild_id=:g LIMIT 1"),
            {'g': guild_id},
        ).fetchone()
        guild_name = settings[1] if settings else guild_id
        channel_name = channel_id
        if settings and settings[0]:
            try:
                channels = json.loads(settings[0])
                for ch in channels:
                    if str(ch.get('id', '')) == channel_id:
                        channel_name = ch.get('name', channel_id)
                        break
            except Exception:
                pass

        now_ts = int(time.time())
        existing = db.execute(
            text("SELECT id FROM web_community_bot_configs "
                 "WHERE platform='fluxer' AND guild_id=:g AND event_type='lfg_announce' LIMIT 1"),
            {'g': guild_id},
        ).fetchone()

        if existing:
            db.execute(
                text("UPDATE web_community_bot_configs "
                     "SET channel_id=:ch, channel_name=:cname, guild_name=:gname, "
                     "    is_enabled=:en, updated_at=:now "
                     "WHERE platform='fluxer' AND guild_id=:g AND event_type='lfg_announce'"),
                {'ch': channel_id if is_enabled else None,
                 'cname': channel_name if is_enabled else None,
                 'gname': guild_name, 'en': 1 if is_enabled else 0,
                 'now': now_ts, 'g': guild_id},
            )
        else:
            db.execute(
                text("INSERT INTO web_community_bot_configs "
                     "(platform, guild_id, guild_name, channel_id, channel_name, "
                     " event_type, is_enabled, created_at, updated_at) "
                     "VALUES ('fluxer', :g, :gname, :ch, :cname, 'lfg_announce', :en, :now, :now)"),
                {'g': guild_id, 'gname': guild_name,
                 'ch': channel_id if is_enabled else None,
                 'cname': channel_name if is_enabled else None,
                 'en': 1 if is_enabled else 0, 'now': now_ts},
            )
        db.commit()
        return JsonResponse({'success': True, 'is_enabled': is_enabled, 'channel_name': channel_name})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_lfg_stats(request, guild_id):
    """GET member reliability stats for a Fluxer guild. ?sort=reliability|active|flaky"""
    guild_id = guild_id.strip()
    sort = request.GET.get('sort', 'reliability')
    with get_db_session() as db:
        q = db.query(WebFluxerLfgMemberStats).filter_by(guild_id=guild_id)
        if sort == 'active':
            q = q.order_by(WebFluxerLfgMemberStats.total_signups.desc())
        elif sort == 'flaky':
            q = q.order_by(WebFluxerLfgMemberStats.reliability_score.asc())
        else:
            q = q.order_by(WebFluxerLfgMemberStats.reliability_score.desc())
        members = q.limit(100).all()
        return JsonResponse({'success': True, 'members': [_member_stats_dict(m) for m in members]})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_lfg_blacklist(request, guild_id):
    """GET blacklisted members for a Fluxer guild."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        members = db.query(WebFluxerLfgMemberStats).filter_by(
            guild_id=guild_id, is_blacklisted=1
        ).order_by(WebFluxerLfgMemberStats.blacklisted_at.desc()).all()
        return JsonResponse({'success': True, 'members': [_member_stats_dict(m) for m in members]})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_lfg_blacklist_action(request, guild_id, user_id):
    """POST blacklist or unblacklist a member. Body: {action: 'blacklist'|'unblacklist', reason: '...'}"""
    guild_id = guild_id.strip()
    user_id = user_id.strip()
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = (data.get('action', '') or '').strip()
    if action not in ('blacklist', 'unblacklist', 'pardon'):
        return JsonResponse({'error': 'action must be blacklist, unblacklist, or pardon'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        member = db.query(WebFluxerLfgMemberStats).filter_by(
            guild_id=guild_id, fluxer_user_id=user_id
        ).first()
        if not member:
            return JsonResponse({'error': 'Member stats not found'}, status=404)

        if action == 'blacklist':
            reason = sanitize_text(data.get('reason', '') or '').strip()[:500]
            member.is_blacklisted = 1
            member.blacklist_reason = reason or None
            member.blacklisted_at = now
        elif action in ('unblacklist', 'pardon'):
            member.is_blacklisted = 0
            member.blacklist_reason = None
            member.blacklisted_at = None
            if action == 'pardon':
                member.reliability_score = 100
                member.no_show_count = 0
                member.late_count = 0
                member.pardoned_count += 1
                member.global_pardon_at = now
        member.updated_at = now
        db.commit()
        return JsonResponse({'success': True, 'member': _member_stats_dict(member)})


# ---------------------------------------------------------------------------
# Moderation Warnings API (ADMIN)
# ---------------------------------------------------------------------------

def _warning_dict(w: WebFluxerModWarning) -> dict:
    return {
        'id': w.id,
        'guild_id': w.guild_id,
        'target_user_id': w.target_user_id,
        'target_username': w.target_username or '',
        'moderator_user_id': w.moderator_user_id or '',
        'moderator_username': w.moderator_username or '',
        'reason': w.reason or '',
        'severity': w.severity,
        'is_active': bool(w.is_active),
        'pardoned_at': w.pardoned_at,
        'created_at': w.created_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_warnings(request, guild_id):
    """
    GET  - list warnings for a Fluxer guild. Supports ?user_id= and ?active_only=1
    POST - add a warning manually
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            q = db.query(WebFluxerModWarning).filter_by(guild_id=guild_id)
            user_id_filter = request.GET.get('user_id', '').strip()
            if user_id_filter:
                q = q.filter(WebFluxerModWarning.target_user_id == user_id_filter)
            if request.GET.get('active_only') == '1':
                q = q.filter_by(is_active=1)
            warnings = q.order_by(WebFluxerModWarning.created_at.desc()).limit(200).all()
            return JsonResponse({'success': True, 'warnings': [_warning_dict(w) for w in warnings]})

    # POST
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    target_user_id = (data.get('target_user_id', '') or '').strip()
    if not target_user_id:
        return JsonResponse({'error': 'target_user_id is required'}, status=400)

    target_username = sanitize_text(data.get('target_username', '') or '').strip()[:100]
    moderator_user_id = (data.get('moderator_user_id', '') or '').strip()
    moderator_username = sanitize_text(data.get('moderator_username', '') or '').strip()[:100]
    reason = sanitize_text(data.get('reason', '') or '').strip()[:2000]
    severity = safe_int(data.get('severity', 1), default=1, min_val=1, max_val=3)

    now = int(time.time())
    with get_db_session() as db:
        warning = WebFluxerModWarning(
            guild_id=guild_id,
            target_user_id=target_user_id,
            target_username=target_username or None,
            moderator_user_id=moderator_user_id or None,
            moderator_username=moderator_username or None,
            reason=reason or None,
            severity=severity,
            is_active=1,
            created_at=now,
        )
        db.add(warning)
        db.commit()
        db.refresh(warning)
        return JsonResponse({'success': True, 'warning': _warning_dict(warning)}, status=201)


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_warning_pardon(request, guild_id, warning_id):
    """
    POST - pardon (deactivate) a warning
    """
    guild_id = guild_id.strip()
    warning_id = safe_int(warning_id, default=0)
    if not warning_id:
        return JsonResponse({'error': 'Invalid warning_id'}, status=400)

    with get_db_session() as db:
        warning = db.query(WebFluxerModWarning).filter_by(id=warning_id, guild_id=guild_id).first()
        if not warning:
            return JsonResponse({'error': 'Not found'}, status=404)
        if not warning.is_active:
            return JsonResponse({'error': 'Warning already pardoned'}, status=400)
        warning.is_active = 0
        warning.pardoned_at = int(time.time())
        db.commit()
        return JsonResponse({'success': True, 'warning': _warning_dict(warning)})


# ---------------------------------------------------------------------------
# Welcome Config API (ADMIN)
# ---------------------------------------------------------------------------

@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_welcome_config(request, guild_id):
    """GET/POST welcome/goodbye configuration for a Fluxer guild."""
    guild_id = guild_id.strip()

    with get_db_session() as db:
        if request.method == 'GET':
            cfg = db.query(WebFluxerWelcomeConfig).filter_by(guild_id=guild_id).first()
            result = _welcome_config_dict(cfg) if cfg else _default_welcome_config()
            return JsonResponse({'success': True, 'config': result})

        # POST
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        cfg = db.query(WebFluxerWelcomeConfig).filter_by(guild_id=guild_id).first()
        if not cfg:
            cfg = WebFluxerWelcomeConfig(guild_id=guild_id)
            db.add(cfg)

        bool_fields = {
            'enabled': 'enabled',
            'welcome_embed_enabled': 'welcome_embed_enabled',
            'welcome_embed_thumbnail': 'welcome_embed_thumbnail',
            'dm_enabled': 'dm_enabled',
            'goodbye_enabled': 'goodbye_enabled',
        }
        str_fields = {
            'welcome_channel_id': ('welcome_channel_id', 32),
            'welcome_message': ('welcome_message', 2000),
            'welcome_embed_title': ('welcome_embed_title', 200),
            'welcome_embed_color': ('welcome_embed_color', 10),
            'welcome_embed_footer': ('welcome_embed_footer', 300),
            'dm_message': ('dm_message', 2000),
            'goodbye_channel_id': ('goodbye_channel_id', 32),
            'goodbye_message': ('goodbye_message', 2000),
            'auto_role_id': ('auto_role_id', 32),
        }
        for k, attr in bool_fields.items():
            if k in data:
                setattr(cfg, attr, 1 if data[k] else 0)
        for k, (attr, maxlen) in str_fields.items():
            if k in data:
                v = (data[k] or '').strip()[:maxlen]
                setattr(cfg, attr, v or None)

        cfg.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'success': True, 'config': _welcome_config_dict(cfg)})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_welcome_test(request, guild_id):
    """
    POST - queue a test welcome or goodbye message via fluxer_pending_broadcasts.
    Body: {type: 'welcome'|'goodbye', channel_id: '...'}
    The bot's broadcast poll loop picks it up within 5 seconds.
    """
    guild_id = guild_id.strip()
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    msg_type = (data.get('type', '') or '').strip()
    if msg_type not in ('welcome', 'goodbye'):
        return JsonResponse({'error': 'type must be welcome or goodbye'}, status=400)

    channel_id = (data.get('channel_id', '') or '').strip()[:32]
    if not channel_id:
        return JsonResponse({'error': 'channel_id is required'}, status=400)

    with get_db_session() as db:
        cfg = db.query(WebFluxerWelcomeConfig).filter_by(guild_id=guild_id).first()
        if not cfg:
            return JsonResponse({'error': 'Welcome config not saved yet. Save settings first.'}, status=400)

        # Use the admin's username as stand-in for {username}/{user} in test messages
        test_name = getattr(request.web_user, 'username', 'TestUser') or 'TestUser'

        if msg_type == 'welcome':
            template = cfg.welcome_message or 'Welcome, {username}!'
            color = 0x5865F2
            try:
                raw = cfg.welcome_embed_color or ''
                color = int(raw.lstrip('#'), 16) if raw else 0x5865F2
            except (ValueError, AttributeError):
                pass
            description = (
                template
                .replace('{user}', f'**{test_name}**')
                .replace('{username}', test_name)
                .replace('{server}', 'Your Server')
                .replace('{member_count}', '100')
                .replace('{member_count_ord}', '100th')
            )
            embed_data = {
                'title': (cfg.welcome_embed_title or '').replace('{username}', test_name) if cfg.welcome_embed_enabled else None,
                'description': f'**[TEST]** {description}',
                'color': color,
                'footer': cfg.welcome_embed_footer or 'Welcome Test',
            }
        else:  # goodbye
            template = cfg.goodbye_message or 'Goodbye, {username}!'
            description = (
                template
                .replace('{user}', f'**{test_name}**')
                .replace('{username}', test_name)
                .replace('{server}', 'Your Server')
                .replace('{member_count}', '99')
                .replace('{member_count_ord}', '99th')
            )
            embed_data = {
                'description': f'**[TEST]** {description}',
                'color': 0x747F8D,
            }

        # Insert into fluxer_pending_broadcasts - the bot's poll loop delivers it
        now = int(time.time())
        db.execute(
            text(
                "INSERT INTO fluxer_pending_broadcasts "
                "(guild_id, channel_id, payload, created_at) "
                "VALUES (:gid, :cid, :payload, :now)"
            ),
            {
                'gid': guild_id,
                'cid': channel_id,
                'payload': json.dumps(embed_data),
                'now': now,
            },
        )
        db.commit()

    return JsonResponse({
        'success': True,
        'message': f'Test {msg_type} message queued. The bot will send it within 5 seconds.',
    })


# ---------------------------------------------------------------------------
# Community network bot configs (kept for QuestLog Network tab in guild dashboard)
# ---------------------------------------------------------------------------

@web_login_required
@require_http_methods(['GET', 'POST'])
def api_bot_dashboard_configs(request):
    """
    GET  - list bot configs for current user's communities
    POST - create or update a config
    """
    user_id = request.web_user.id

    if request.method == 'GET':
        with get_db_session() as db:
            communities = db.query(WebCommunity).filter_by(owner_id=user_id, is_active=True).all()
            community_ids = [c.id for c in communities]
            configs = db.query(WebCommunityBotConfig).filter(
                WebCommunityBotConfig.community_id.in_(community_ids)
            ).all() if community_ids else []
            return JsonResponse({'configs': [_config_dict(c) for c in configs]})

    # POST - create/update
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    community_id = safe_int(data.get('community_id'), default=0)
    platform = data.get('platform', '').strip()
    guild_id = data.get('guild_id', '').strip()
    event_type = data.get('event_type', '').strip()
    webhook_url = data.get('webhook_url', '').strip()
    channel_name = data.get('channel_name', '').strip()
    guild_name = data.get('guild_name', '').strip()
    is_enabled = bool(data.get('is_enabled', True))

    if platform not in ('discord', 'fluxer'):
        return JsonResponse({'error': 'Invalid platform'}, status=400)
    if event_type not in EVENT_LABELS or not EVENT_LABELS[event_type]['available']:
        return JsonResponse({'error': 'Invalid or unavailable event_type'}, status=400)
    if webhook_url and not webhook_url.startswith('https://'):
        return JsonResponse({'error': 'Webhook URL must start with https://'}, status=400)

    with get_db_session() as db:
        if community_id:
            community = db.query(WebCommunity).filter_by(id=community_id, owner_id=user_id).first()
            if not community:
                return JsonResponse({'error': 'Community not found or not owned by you'}, status=403)

        now = int(time.time())
        cfg = None
        if guild_id:
            cfg = db.query(WebCommunityBotConfig).filter_by(
                platform=platform, guild_id=guild_id, event_type=event_type
            ).first()

        if cfg:
            cfg.community_id = community_id or cfg.community_id
            cfg.guild_name = guild_name or cfg.guild_name
            cfg.channel_name = channel_name or cfg.channel_name
            cfg.webhook_url = webhook_url or cfg.webhook_url
            cfg.is_enabled = is_enabled
            cfg.updated_at = now
        else:
            cfg = WebCommunityBotConfig(
                community_id=community_id or None,
                platform=platform,
                guild_id=guild_id or f"manual_{user_id}_{now}",
                guild_name=guild_name,
                channel_name=channel_name,
                webhook_url=webhook_url or None,
                event_type=event_type,
                is_enabled=is_enabled and bool(webhook_url),
                created_at=now,
                updated_at=now,
            )
            db.add(cfg)
        db.commit()
        db.refresh(cfg)
        return JsonResponse({'success': True, 'config': _config_dict(cfg)}, status=201)


@web_login_required
@require_http_methods(['DELETE', 'PUT'])
def api_bot_dashboard_config_detail(request, config_id):
    """PUT to update, DELETE to remove a bot config."""
    user_id = request.web_user.id

    with get_db_session() as db:
        cfg = db.query(WebCommunityBotConfig).filter_by(id=config_id).first()
        if not cfg:
            return JsonResponse({'error': 'Not found'}, status=404)

        if cfg.community_id:
            community = db.query(WebCommunity).filter_by(id=cfg.community_id, owner_id=user_id).first()
            if not community:
                return JsonResponse({'error': 'Forbidden'}, status=403)

        if request.method == 'DELETE':
            db.delete(cfg)
            db.commit()
            return JsonResponse({'success': True})

        # PUT - update
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        webhook_url = data.get('webhook_url', '').strip()
        if webhook_url and not webhook_url.startswith('https://'):
            return JsonResponse({'error': 'Webhook URL must start with https://'}, status=400)

        cfg.webhook_url = webhook_url or cfg.webhook_url
        cfg.channel_name = data.get('channel_name', cfg.channel_name)
        cfg.guild_name = data.get('guild_name', cfg.guild_name)
        cfg.is_enabled = bool(data.get('is_enabled', cfg.is_enabled)) and bool(cfg.webhook_url)
        cfg.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'success': True, 'config': _config_dict(cfg)})


# ---------------------------------------------------------------------------
# Reaction Roles API
# ---------------------------------------------------------------------------

def _reaction_role_dict(rr: WebFluxerReactionRole) -> dict:
    roles = json.loads(rr.mappings_json) if rr.mappings_json else []
    return {
        'id': rr.id,
        'guild_id': rr.guild_id,
        'channel_id': rr.channel_id,
        'message_id': rr.message_id or '',
        'title': rr.title or '',
        'description': rr.description or '',
        'roles': roles,       # template expects 'roles'
        'mappings': roles,    # backward-compat alias
        'is_exclusive': bool(rr.is_exclusive),
        'created_at': rr.created_at,
        'updated_at': rr.updated_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_reaction_roles(request, guild_id):
    """
    GET  - list reaction role menus for a Fluxer guild
    POST - create a new reaction role menu
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            menus = db.query(WebFluxerReactionRole).filter_by(guild_id=guild_id).order_by(
                WebFluxerReactionRole.created_at.desc()
            ).all()
            return JsonResponse({'success': True, 'menus': [_reaction_role_dict(m) for m in menus]})

    # POST
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    title = sanitize_text(data.get('title', '') or '').strip()[:200]
    if not title:
        return JsonResponse({'error': 'title is required'}, status=400)

    channel_id = (data.get('channel_id', '') or '').strip()
    if not channel_id:
        return JsonResponse({'error': 'channel_id is required'}, status=400)

    with get_db_session() as db:
        known_channels = {
            r[0] for r in db.execute(text(
                "SELECT channel_id FROM web_fluxer_guild_channels WHERE guild_id = :g"
            ), {'g': guild_id}).fetchall()
        }
        if channel_id not in known_channels:
            return JsonResponse({'error': 'Unknown channel_id'}, status=400)

        description = sanitize_text(data.get('description', '') or '')[:500]
        # Accept 'roles', 'mappings', or 'mappings_json' - template sends 'roles'
        mappings = data.get('roles', data.get('mappings_json', data.get('mappings', [])))
        if not isinstance(mappings, list):
            mappings = []
        is_exclusive = bool(data.get('is_exclusive', False))

        now = int(time.time())
        rr = WebFluxerReactionRole(
            guild_id=guild_id,
            channel_id=channel_id,
            title=title,
            description=description or None,
            mappings_json=json.dumps(mappings),
            is_exclusive=1 if is_exclusive else 0,
            created_at=now,
            updated_at=now,
        )
        db.add(rr)
        db.commit()
        db.refresh(rr)
        return JsonResponse({'success': True, 'menu': _reaction_role_dict(rr)}, status=201)


@fluxer_guild_required
@require_http_methods(['PUT', 'DELETE'])
def api_fluxer_reaction_role_detail(request, guild_id, message_id):
    """
    PUT    - update a reaction role menu by DB id
    DELETE - remove a reaction role menu by DB id
    (message_id param is actually the DB id or the Discord message_id)
    """
    guild_id = guild_id.strip()
    # Try numeric DB id first, fall back to Discord message_id lookup
    record_id = safe_int(message_id, default=0)

    with get_db_session() as db:
        if record_id:
            rr = db.query(WebFluxerReactionRole).filter_by(id=record_id, guild_id=guild_id).first()
        else:
            rr = db.query(WebFluxerReactionRole).filter_by(
                message_id=message_id.strip(), guild_id=guild_id
            ).first()

        if not rr:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.delete(rr)
            db.commit()
            return JsonResponse({'success': True})

        # PUT - update
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'title' in data:
            rr.title = sanitize_text(data['title'] or '')[:200] or rr.title
        if 'description' in data:
            rr.description = sanitize_text(data['description'] or '')[:500] or None
        if 'channel_id' in data:
            ch = (data['channel_id'] or '').strip()
            if ch:
                known = {r[0] for r in db.execute(text(
                    "SELECT channel_id FROM web_fluxer_guild_channels WHERE guild_id = :g"
                ), {'g': guild_id}).fetchall()}
                if ch not in known:
                    return JsonResponse({'error': 'Unknown channel_id'}, status=400)
                rr.channel_id = ch
        mappings = data.get('roles', data.get('mappings', data.get('mappings_json')))
        if mappings is not None:
            if not isinstance(mappings, list):
                mappings = []
            rr.mappings_json = json.dumps(mappings)
        if 'is_exclusive' in data:
            rr.is_exclusive = 1 if data['is_exclusive'] else 0
        rr.updated_at = int(time.time())
        db.commit()
        db.refresh(rr)
        return JsonResponse({'success': True, 'menu': _reaction_role_dict(rr)})


# ---------------------------------------------------------------------------
# Raffles API
# ---------------------------------------------------------------------------

def _raffle_dict(r: WebFluxerRaffle) -> dict:
    winners = json.loads(r.winners_json) if r.winners_json else []
    return {
        'id': r.id,
        'guild_id': r.guild_id,
        'title': r.title,
        'description': r.description or '',
        'prize': r.prize or '',
        # channel_id stored as announce_channel_id in template
        'channel_id': r.channel_id or '',
        'announce_channel_id': r.channel_id or '',
        'message_id': r.message_id or '',
        'max_winners': r.max_winners,
        # cost_tokens is the template field name; ticket_cost_hp is the DB column
        'cost_tokens': r.ticket_cost_hp,
        'ticket_cost_hp': r.ticket_cost_hp,
        'max_entries_per_user': r.max_entries_per_user,
        'winners': winners,
        'winners_json': winners,
        'status': r.status,
        'active': r.status in ('pending', 'active'),
        # Template uses start_at/end_at; DB stores starts_at/ends_at
        'start_at': r.starts_at,
        'end_at': r.ends_at,
        'starts_at': r.starts_at,
        'ends_at': r.ends_at,
        # Extra fields not yet in DB - return safe defaults
        'announce_role_id': '',
        'announce_message': '',
        'winner_message': '',
        'entry_emoji': '',
        'reminder_channel_id': '',
        'auto_pick': False,
        'entry_count': 0,
        'created_at': r.created_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_raffles(request, guild_id):
    """
    GET  - list raffles for a Fluxer guild (split by status)
    POST - create a raffle
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            all_raffles = db.query(WebFluxerRaffle).filter_by(guild_id=guild_id).order_by(
                WebFluxerRaffle.created_at.desc()
            ).all()
            active = [_raffle_dict(r) for r in all_raffles if r.status in ('pending', 'active')]
            ended = [_raffle_dict(r) for r in all_raffles if r.status == 'ended']
            return JsonResponse({'success': True, 'active': active, 'ended': ended})

    # POST
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    title = sanitize_text(data.get('title', '') or '').strip()[:200]
    if not title:
        return JsonResponse({'error': 'title is required'}, status=400)

    channel_id = (data.get('channel_id', '') or '').strip()

    # Validate channel if provided
    if channel_id:
        with get_db_session() as db:
            known_channels = {
                r[0] for r in db.execute(text(
                    "SELECT channel_id FROM web_fluxer_guild_channels WHERE guild_id = :g"
                ), {'g': guild_id}).fetchall()
            }
            if channel_id not in known_channels:
                return JsonResponse({'error': 'Unknown channel_id'}, status=400)

    max_winners = safe_int(data.get('max_winners', 1), default=1, min_val=1, max_val=100)
    # Accept cost_tokens (template field) or ticket_cost_hp (DB column name)
    ticket_cost_hp = safe_int(
        data.get('cost_tokens', data.get('ticket_cost_hp', 0)),
        default=0, min_val=0, max_val=10000
    )
    max_entries = safe_int(data.get('max_entries_per_user', 1), default=1, min_val=1, max_val=100)
    # Accept start_at/end_at (template) or starts_at/ends_at (legacy)
    raw_start = data.get('start_at', data.get('starts_at'))
    raw_end = data.get('end_at', data.get('ends_at'))

    now = int(time.time())
    with get_db_session() as db:
        raffle = WebFluxerRaffle(
            guild_id=guild_id,
            title=title,
            description=sanitize_text(data.get('description', '') or '')[:1000] or None,
            prize=sanitize_text(data.get('prize', '') or '')[:300] or None,
            channel_id=channel_id or None,
            max_winners=max_winners,
            ticket_cost_hp=ticket_cost_hp,
            max_entries_per_user=max_entries,
            status='pending',
            starts_at=int(raw_start) if raw_start else None,
            ends_at=int(raw_end) if raw_end else None,
            created_by=request.web_user.id,
            created_at=now,
        )
        db.add(raffle)
        db.commit()
        db.refresh(raffle)
        return JsonResponse({'success': True, 'raffle': _raffle_dict(raffle)}, status=201)


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_raffle_pick(request, guild_id, raffle_id):
    """
    POST - pick raffle winner(s) using weighted random selection by ticket_count.
    Sets status to 'ended' and stores winner IDs in winners_json.
    """
    guild_id = guild_id.strip()
    raffle_id = safe_int(raffle_id, default=0)
    if not raffle_id:
        return JsonResponse({'error': 'Invalid raffle_id'}, status=400)

    with get_db_session() as db:
        raffle = db.query(WebFluxerRaffle).filter_by(id=raffle_id, guild_id=guild_id).first()
        if not raffle:
            return JsonResponse({'error': 'Raffle not found'}, status=404)
        if raffle.status == 'ended':
            return JsonResponse({'error': 'Raffle already ended'}, status=400)

        entries = db.query(WebFluxerRaffleEntry).filter_by(raffle_id=raffle_id).all()
        if not entries:
            return JsonResponse({
                'success': True,
                'message': 'No entries to draw from.',
                'winners': [],
            })

        # Build weighted pool: each entry repeated by ticket_count
        pool = []
        for entry in entries:
            pool.extend([entry] * max(1, entry.ticket_count))

        num_winners = min(raffle.max_winners, len(entries))
        # Pick without replacement by sampling unique entries
        seen_users = set()
        winners = []
        shuffled = pool[:]
        random.shuffle(shuffled)
        for entry in shuffled:
            uid = entry.web_user_id or entry.fluxer_user_id
            if uid not in seen_users:
                seen_users.add(uid)
                winners.append(entry)
            if len(winners) >= num_winners:
                break

        winner_ids = [
            {'web_user_id': w.web_user_id, 'fluxer_user_id': w.fluxer_user_id, 'username': w.username}
            for w in winners
        ]
        raffle.winners_json = json.dumps(winner_ids)
        raffle.status = 'ended'
        db.commit()

        return JsonResponse({
            'success': True,
            'message': f'Picked {len(winners)} winner(s).',
            'winners': winner_ids,
        })


@fluxer_guild_required
@require_http_methods(['GET', 'PUT', 'DELETE'])
def api_fluxer_guild_raffle_detail(request, guild_id, raffle_id):
    """GET / PUT / DELETE a single raffle."""
    guild_id = guild_id.strip()
    raffle_id = safe_int(raffle_id, default=0)
    if not raffle_id:
        return JsonResponse({'error': 'Invalid raffle_id'}, status=400)

    with get_db_session() as db:
        raffle = db.query(WebFluxerRaffle).filter_by(id=raffle_id, guild_id=guild_id).first()
        if not raffle:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'GET':
            return JsonResponse({'success': True, 'raffle': _raffle_dict(raffle)})

        if request.method == 'DELETE':
            db.delete(raffle)
            db.commit()
            return JsonResponse({'success': True})

        # PUT - update
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'title' in data:
            title = sanitize_text(data['title'] or '').strip()[:200]
            if title:
                raffle.title = title
        if 'description' in data:
            raffle.description = sanitize_text(data['description'] or '')[:1000] or None
        if 'prize' in data:
            raffle.prize = sanitize_text(data['prize'] or '')[:300] or None
        # Accept announce_channel_id (template) or channel_id (DB)
        ch = (data.get('announce_channel_id', data.get('channel_id', '')) or '').strip()
        if ch:
            raffle.channel_id = ch
        if 'max_winners' in data:
            raffle.max_winners = safe_int(data['max_winners'], default=1, min_val=1, max_val=100)
        if 'cost_tokens' in data or 'ticket_cost_hp' in data:
            raffle.ticket_cost_hp = safe_int(
                data.get('cost_tokens', data.get('ticket_cost_hp', raffle.ticket_cost_hp)),
                default=0, min_val=0, max_val=10000
            )
        if 'max_entries_per_user' in data:
            val = data['max_entries_per_user']
            raffle.max_entries_per_user = safe_int(val, default=1, min_val=1, max_val=100) if val else 1
        raw_start = data.get('start_at', data.get('starts_at'))
        if raw_start is not None:
            raffle.starts_at = int(raw_start) if raw_start else None
        raw_end = data.get('end_at', data.get('ends_at'))
        if raw_end is not None:
            raffle.ends_at = int(raw_end) if raw_end else None
        db.commit()
        db.refresh(raffle)
        return JsonResponse({'success': True, 'raffle': _raffle_dict(raffle)})


# ---------------------------------------------------------------------------
# Discovery RSS feeds API
# ---------------------------------------------------------------------------

def _rss_feed_dict(f: WebFluxerRssFeed) -> dict:
    embed_cfg = {}
    if f.embed_config:
        try:
            embed_cfg = json.loads(f.embed_config)
        except Exception:
            pass
    cat_filters = []
    if f.category_filters:
        try:
            cat_filters = json.loads(f.category_filters)
        except Exception:
            pass
    return {
        'id': f.id,
        'guild_id': f.guild_id,
        'url': f.url,
        'label': f.label or '',
        'channel_id': f.channel_id,
        'channel_name': f.channel_name or '',
        'ping_role_id': f.ping_role_id or '',
        'poll_interval_minutes': f.poll_interval_minutes or 15,
        'max_age_days': f.max_age_days,
        'category_filter_mode': f.category_filter_mode or 'none',
        'category_filters': cat_filters,
        'embed_config': embed_cfg,
        'last_checked_at': f.last_checked_at,
        'consecutive_failures': f.consecutive_failures or 0,
        'last_error': f.last_error or '',
        'enabled': bool(f.enabled) if f.enabled is not None else True,
        'is_active': bool(f.is_active),
        'created_at': f.created_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_discovery_rss(request, guild_id):
    """
    GET  - list RSS feeds configured for a Fluxer guild
    POST - add an RSS feed to a Fluxer guild
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            feeds = db.query(WebFluxerRssFeed).filter_by(guild_id=guild_id, is_active=1).order_by(
                WebFluxerRssFeed.created_at.desc()
            ).all()
            return JsonResponse({'success': True, 'feeds': [_rss_feed_dict(f) for f in feeds], 'feed_count': len(feeds)})

    # POST
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    label = sanitize_text(data.get('label', data.get('name', '')) or '').strip()[:200]
    feed_url = (data.get('url', data.get('feed_url', '')) or '').strip()[:500]
    channel_id = (data.get('channel_id', '') or '').strip()
    ping_role_id = (data.get('ping_role_id', '') or '').strip() or None
    poll_interval = safe_int(data.get('poll_interval_minutes', 15), default=15, min_val=5, max_val=10080)
    max_age_days = safe_int(data.get('max_age_days', 0), default=0, min_val=0, max_val=365) or None
    cat_filter_mode = (data.get('category_filter_mode', 'none') or 'none').strip()
    if cat_filter_mode not in ('none', 'include', 'exclude'):
        cat_filter_mode = 'none'
    cat_filters_raw = data.get('category_filters', [])
    cat_filters = json.dumps([sanitize_text(str(c))[:100] for c in cat_filters_raw if c][:20]) if cat_filters_raw else None

    # embed_config fields
    ec = data.get('embed_config', {}) or {}
    embed_cfg = {
        'color': (str(ec.get('color', '#ea580c') or '#ea580c'))[:10],
        'custom_emoji_prefix': sanitize_text(str(ec.get('custom_emoji_prefix', '') or ''))[:10],
        'title_prefix': sanitize_text(str(ec.get('title_prefix', '') or ''))[:100],
        'title_suffix': sanitize_text(str(ec.get('title_suffix', '') or ''))[:100],
        'custom_description': sanitize_text(str(ec.get('custom_description', '') or ''))[:500],
        'footer_text': sanitize_text(str(ec.get('footer_text', '') or ''))[:200],
        'thumbnail_mode': (str(ec.get('thumbnail_mode', 'rss') or 'rss'))[:20],
        'custom_thumbnail_url': (str(ec.get('custom_thumbnail_url', '') or ''))[:500],
        'show_author': bool(ec.get('show_author', True)),
        'show_categories': bool(ec.get('show_categories', False)),
        'show_publish_date': bool(ec.get('show_publish_date', True)),
        'show_full_content': bool(ec.get('show_full_content', False)),
        'max_individual_posts': safe_int(ec.get('max_individual_posts', 5), default=5, min_val=0, max_val=20),
        'always_use_summary': bool(ec.get('always_use_summary', False)),
    }

    if not feed_url:
        return JsonResponse({'error': 'url is required'}, status=400)
    if not feed_url.startswith('https://') and not feed_url.startswith('http://'):
        return JsonResponse({'error': 'url must be a valid http/https URL'}, status=400)
    if not channel_id:
        return JsonResponse({'error': 'channel_id is required'}, status=400)

    with get_db_session() as db:
        known_channels = {
            r[0]: r[1] for r in db.execute(text(
                "SELECT channel_id, channel_name FROM web_fluxer_guild_channels WHERE guild_id = :g"
            ), {'g': guild_id}).fetchall()
        }
        if channel_id not in known_channels:
            return JsonResponse({'error': 'Unknown channel_id'}, status=400)

        channel_name = known_channels[channel_id] or ''
        now = int(time.time())
        feed = WebFluxerRssFeed(
            guild_id=guild_id,
            url=feed_url,
            label=label or None,
            channel_id=channel_id,
            channel_name=channel_name,
            ping_role_id=ping_role_id,
            poll_interval_minutes=poll_interval,
            max_age_days=max_age_days,
            category_filter_mode=cat_filter_mode,
            category_filters=cat_filters,
            embed_config=json.dumps(embed_cfg),
            enabled=1 if data.get('enabled', True) else 0,
            is_active=1,
            created_at=now,
        )
        db.add(feed)
        db.commit()
        db.refresh(feed)
        return JsonResponse({'success': True, 'feed': _rss_feed_dict(feed)}, status=201)


@fluxer_guild_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def api_fluxer_discovery_rss_detail(request, guild_id, feed_id):
    """
    GET    - fetch a single feed
    PATCH  - update feed settings
    DELETE - soft-delete the feed
    """
    guild_id = guild_id.strip()
    feed_id = safe_int(feed_id, default=0)
    if not feed_id:
        return JsonResponse({'error': 'Invalid feed_id'}, status=400)

    with get_db_session() as db:
        feed = db.query(WebFluxerRssFeed).filter_by(id=feed_id, guild_id=guild_id).first()
        if not feed:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'GET':
            return JsonResponse({'success': True, 'feed': _rss_feed_dict(feed)})

        if request.method == 'DELETE':
            feed.is_active = 0
            db.commit()
            return JsonResponse({'success': True})

        # PATCH - update fields
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Reuse same validation as POST
        if 'url' in data:
            new_url = (data['url'] or '').strip()[:500]
            if not new_url.startswith('http://') and not new_url.startswith('https://'):
                return JsonResponse({'error': 'url must be a valid http/https URL'}, status=400)
            feed.url = new_url
        if 'label' in data:
            feed.label = sanitize_text(data['label'] or '').strip()[:200] or None
        if 'channel_id' in data:
            channel_id = (data.get('channel_id', '') or '').strip()
            known = {r[0]: r[1] for r in db.execute(text(
                "SELECT channel_id, channel_name FROM web_fluxer_guild_channels WHERE guild_id = :g"
            ), {'g': guild_id}).fetchall()}
            if channel_id and channel_id not in known:
                return JsonResponse({'error': 'Unknown channel_id'}, status=400)
            feed.channel_id = channel_id
            feed.channel_name = known.get(channel_id, '')
        if 'ping_role_id' in data:
            feed.ping_role_id = (data['ping_role_id'] or '').strip() or None
        if 'poll_interval_minutes' in data:
            feed.poll_interval_minutes = safe_int(data['poll_interval_minutes'], default=15, min_val=5, max_val=10080)
        if 'max_age_days' in data:
            feed.max_age_days = safe_int(data['max_age_days'], default=0, min_val=0, max_val=365) or None
        if 'category_filter_mode' in data:
            m = (data['category_filter_mode'] or 'none').strip()
            feed.category_filter_mode = m if m in ('none', 'include', 'exclude') else 'none'
        if 'category_filters' in data:
            raw = data['category_filters'] or []
            feed.category_filters = json.dumps([sanitize_text(str(c))[:100] for c in raw if c][:20]) if raw else None
        if 'enabled' in data:
            feed.enabled = 1 if data['enabled'] else 0
        if 'embed_config' in data:
            ec = data['embed_config'] or {}
            feed.embed_config = json.dumps({
                'color': str(ec.get('color', '#ea580c') or '#ea580c')[:10],
                'custom_emoji_prefix': sanitize_text(str(ec.get('custom_emoji_prefix', '') or ''))[:10],
                'title_prefix': sanitize_text(str(ec.get('title_prefix', '') or ''))[:100],
                'title_suffix': sanitize_text(str(ec.get('title_suffix', '') or ''))[:100],
                'custom_description': sanitize_text(str(ec.get('custom_description', '') or ''))[:500],
                'footer_text': sanitize_text(str(ec.get('footer_text', '') or ''))[:200],
                'thumbnail_mode': str(ec.get('thumbnail_mode', 'rss') or 'rss')[:20],
                'custom_thumbnail_url': str(ec.get('custom_thumbnail_url', '') or '')[:500],
                'show_author': bool(ec.get('show_author', True)),
                'show_categories': bool(ec.get('show_categories', False)),
                'show_publish_date': bool(ec.get('show_publish_date', True)),
                'show_full_content': bool(ec.get('show_full_content', False)),
                'max_individual_posts': safe_int(ec.get('max_individual_posts', 5), default=5, min_val=0, max_val=20),
                'always_use_summary': bool(ec.get('always_use_summary', False)),
            })
        db.commit()
        db.refresh(feed)
        return JsonResponse({'success': True, 'feed': _rss_feed_dict(feed)})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_discovery_rss_force_send(request, guild_id, feed_id):
    """
    POST - queue a force-send action so the bot fetches the feed now and posts the latest article.
    """
    guild_id = guild_id.strip()
    feed_id = safe_int(feed_id, default=0)
    if not feed_id:
        return JsonResponse({'error': 'Invalid feed_id'}, status=400)

    with get_db_session() as db:
        feed = db.query(WebFluxerRssFeed).filter_by(id=feed_id, guild_id=guild_id, is_active=1).first()
        if not feed:
            return JsonResponse({'error': 'Feed not found'}, status=404)
        action = WebFluxerGuildAction(
            guild_id=guild_id,
            action_type='rss_force_send',
            payload_json=json.dumps({'feed_id': feed_id}),
            status='pending',
            created_at=int(time.time()),
        )
        db.add(action)
        db.commit()
        return JsonResponse({'success': True, 'message': 'Force send queued - bot will deliver within 15 seconds.'})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_messages_send_embed(request, guild_id):
    """
    POST - queue a send_embed action so the bot posts a custom embed to a channel.
    """
    guild_id = guild_id.strip()
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    channel_id = (data.get('channel_id', '') or '').strip()
    title = sanitize_text(data.get('title', '') or '').strip()[:256]
    description = sanitize_text(data.get('description', '') or '').strip()[:4096]
    footer = sanitize_text(data.get('footer', '') or '').strip()[:256]
    color = (data.get('color', '#ea580c') or '#ea580c').strip()[:10]

    if not channel_id:
        return JsonResponse({'error': 'channel_id is required'}, status=400)
    if not title and not description:
        return JsonResponse({'error': 'Title or description is required'}, status=400)

    with get_db_session() as db:
        known = {r[0] for r in db.execute(
            text("SELECT channel_id FROM web_fluxer_guild_channels WHERE guild_id = :g"),
            {'g': guild_id}
        ).fetchall()}
        if channel_id not in known:
            return JsonResponse({'error': 'Unknown channel_id'}, status=400)

        action = WebFluxerGuildAction(
            guild_id=guild_id,
            action_type='send_embed',
            payload_json=json.dumps({
                'channel_id': channel_id,
                'title': title,
                'description': description,
                'footer': footer,
                'color': color,
            }),
            status='pending',
            created_at=int(time.time()),
        )
        db.add(action)
        db.commit()
        return JsonResponse({'success': True, 'message': 'Embed queued - bot will send within 15 seconds.'})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_discovery_rss_preview(request, guild_id, feed_id):
    """
    GET - fetch the RSS feed URL and return a preview of the latest entry embed.
    """
    guild_id = guild_id.strip()
    feed_id = safe_int(feed_id, default=0)
    if not feed_id:
        return JsonResponse({'error': 'Invalid feed_id'}, status=400)

    with get_db_session() as db:
        feed = db.query(WebFluxerRssFeed).filter_by(id=feed_id, guild_id=guild_id, is_active=1).first()
        if not feed:
            return JsonResponse({'error': 'Feed not found'}, status=404)
        feed_url = feed.url
        label = feed.label or feed.url
        embed_cfg = {}
        if feed.embed_config:
            try:
                embed_cfg = json.loads(feed.embed_config)
            except Exception:
                pass

    # Fetch the RSS feed - secure_fetch_rss is synchronous, call it directly
    try:
        from app.rss_utils import secure_fetch_rss
        parsed, fetch_error = secure_fetch_rss(feed_url)
    except Exception as e:
        return JsonResponse({'error': f'Failed to fetch feed: {e}'}, status=502)

    if fetch_error:
        return JsonResponse({'error': fetch_error}, status=502)

    if not parsed or not getattr(parsed, 'entries', None):
        return JsonResponse({'error': 'Feed has no entries'}, status=404)

    entry = parsed.entries[0]

    # Build preview embed dict mirroring what the bot would send
    color_hex = embed_cfg.get('color', '#ea580c')
    emoji = embed_cfg.get('custom_emoji_prefix', '')
    title_prefix = embed_cfg.get('title_prefix', '')
    title_suffix = embed_cfg.get('title_suffix', '')

    title = entry.get('title', 'No Title')
    if title_prefix:
        title = f"{title_prefix} {title}"
    if title_suffix:
        title = f"{title} {title_suffix}"
    if emoji:
        title = f"{emoji} {title}"

    import re as _re, html as _html
    def _strip_html(t):
        t = _re.sub(r'<[^>]+>', '', t or '')
        return _html.unescape(t).strip()

    description = _strip_html(entry.get('summary', entry.get('description', '')))
    if len(description) > 500:
        description = description[:497] + '...'

    custom_desc = embed_cfg.get('custom_description', '')
    if custom_desc:
        description = f"{custom_desc}\n\n{description}"

    footer = embed_cfg.get('footer_text', 'Powered By - QuestLog Network')

    author = None
    if embed_cfg.get('show_author', True):
        author = entry.get('author') or (entry.get('author_detail') or {}).get('name')

    published = None
    if embed_cfg.get('show_publish_date', True):
        published = entry.get('published', entry.get('updated'))

    return JsonResponse({
        'success': True,
        'feed_label': label,
        'embed': {
            'title': title[:256],
            'description': description[:500],
            'url': entry.get('link', ''),
            'color': color_hex,
            'footer': footer,
            'author': author,
            'published': published,
        }
    })


# ---------------------------------------------------------------------------
# Roles API (stubs - no Fluxer guild role management model yet)
# ---------------------------------------------------------------------------

@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_roles_list(request, guild_id):
    """GET - list roles for a Fluxer guild (from DB cache synced by the bot)."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        roles = db.query(WebFluxerGuildRole).filter_by(guild_id=guild_id).order_by(
            WebFluxerGuildRole.position.desc()
        ).all()
        roles_data = [
            {
                'id': r.role_id,
                'value': r.role_id,
                'label': r.role_name,
                'color': r.role_color,
                'position': r.position,
                'is_managed': bool(r.is_managed),
            }
            for r in roles
        ]
    return JsonResponse({'success': True, 'roles': roles_data})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_roles_actions(request, guild_id):
    """
    GET - list pending role actions for a Fluxer guild (stub)
    """
    return JsonResponse({'success': True, 'actions': []})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_role_action(request, guild_id):
    """
    POST - queue a role add/remove action for a Fluxer guild member (stub)
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action', '').strip()
    if action not in ('add', 'remove'):
        return JsonResponse({'error': 'action must be "add" or "remove"'}, status=400)

    user_id = data.get('user_id')
    role_id = data.get('role_id')
    if not user_id or not role_id:
        return JsonResponse({'error': 'user_id and role_id are required'}, status=400)

    return JsonResponse({'success': True, 'action_id': 0, 'message': f'Role {action} queued'})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_role_create(request, guild_id):
    """
    POST - queue a role creation action for the Fluxer bot to execute.
    Bot polls /api/internal/guild-actions/ and calls guild.create_role().
    """
    guild_id = guild_id.strip()
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = sanitize_text(str(data.get('name', '') or '').strip())[:100]
    if not name:
        return JsonResponse({'error': 'Role name is required'}, status=400)

    # permissions is sent as a string from JS BigInt
    try:
        permissions = int(str(data.get('permissions', 0) or 0))
    except (ValueError, TypeError):
        permissions = 0

    color = safe_int(data.get('color', 0), 0, 0, 0xFFFFFF)
    hoist = bool(data.get('hoist', False))
    mentionable = bool(data.get('mentionable', False))

    payload = {
        'name': name,
        'permissions': permissions,
        'color': color,
        'hoist': hoist,
        'mentionable': mentionable,
    }

    now = int(time.time())
    with get_db_session() as db:
        action = WebFluxerGuildAction(
            guild_id=guild_id,
            action_type='create_role',
            payload_json=json.dumps(payload),
            status='pending',
            created_at=now,
        )
        db.add(action)
        db.commit()
        db.refresh(action)
        return JsonResponse({
            'success': True,
            'action_id': action.id,
            'message': f'Role "{name}" creation queued. It will appear in the list shortly.',
        })


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_role_bulk_create(request, guild_id):
    """POST - bulk create roles by queuing one create_role action per role."""
    guild_id = guild_id.strip()
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    roles = data.get('roles', [])
    if not isinstance(roles, list) or len(roles) == 0:
        return JsonResponse({'error': 'No roles provided'}, status=400)
    if len(roles) > 50:
        return JsonResponse({'error': 'Maximum 50 roles per bulk create'}, status=400)

    now = int(time.time())
    queued = 0
    with get_db_session() as db:
        for item in roles:
            name = sanitize_text(str(item.get('name', '') or '').strip())[:100]
            if not name:
                continue
            try:
                permissions = int(str(item.get('permissions', 0) or 0))
            except (ValueError, TypeError):
                permissions = 0
            color = safe_int(item.get('color', 0), 0, 0, 0xFFFFFF)
            hoist = bool(item.get('hoist', False))
            mentionable = bool(item.get('mentionable', False))
            payload = {
                'name': name,
                'permissions': permissions,
                'color': color,
                'hoist': hoist,
                'mentionable': mentionable,
            }
            action = WebFluxerGuildAction(
                guild_id=guild_id,
                action_type='create_role',
                payload_json=json.dumps(payload),
                status='pending',
                created_at=now,
            )
            db.add(action)
            queued += 1
        db.commit()

    return JsonResponse({
        'success': True,
        'queued': queued,
        'message': f'Queued {queued} role(s) for creation. They will appear in the list shortly.',
    })


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_role_import(request, guild_id):
    """
    POST - import roles via file upload (stub)
    """
    return JsonResponse({'success': True, 'imported': 0})


# ---------------------------------------------------------------------------
# Templates API (stubs - no Fluxer guild template model yet)
# ---------------------------------------------------------------------------

@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_templates_list(request, guild_id):
    """
    GET - list channel and role templates for a Fluxer guild (stub)
    """
    return JsonResponse({
        'success': True,
        'channel_templates': [],
        'role_templates': [],
    })


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_template_create(request, guild_id, template_type):
    """
    POST - create a new template for a Fluxer guild (stub)
    Called as POST /templates/channels/ or POST /templates/roles/
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = sanitize_text(data.get('name', '') or '').strip()
    if not name:
        return JsonResponse({'error': 'name is required'}, status=400)

    return JsonResponse({'success': True, 'id': 0}, status=201)


@fluxer_guild_required
@require_http_methods(['GET', 'PUT', 'DELETE'])
def api_fluxer_guild_template_detail(request, guild_id, template_type, template_id):
    """
    GET    - get template details (stub)
    PUT    - update an existing template (stub)
    DELETE - delete a template (stub)
    """
    if request.method == 'GET':
        return JsonResponse({'error': 'Template not found'}, status=404)

    if request.method == 'DELETE':
        return JsonResponse({'success': True})

    # PUT - update
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = sanitize_text(data.get('name', '') or '').strip()
    if not name:
        return JsonResponse({'error': 'name is required'}, status=400)

    return JsonResponse({'success': True})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_template_apply(request, guild_id, template_type, template_id):
    """
    POST - apply a template to the Fluxer guild (stub)
    """
    return JsonResponse({'success': True, 'action_id': 0})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_members(request, guild_id):
    """
    GET - list guild members.
    Priority: 1) web_fluxer_members (rich profile data from MemberSyncCog)
              2) cached_members JSON from bot guild-sync (legacy)
              3) fluxer_member_xp (organic XP fallback, username only)
    Returns [{id, username, display_name, avatar, roles}] sorted by display_name.
    """
    with get_db_session() as db:
        members = []

        # 1. web_fluxer_members - dedicated member sync table (richest data)
        try:
            rows = db.execute(text(
                "SELECT user_id, username, global_name, avatar_hash, roles "
                "FROM web_fluxer_members "
                "WHERE guild_id = :g AND left_at IS NULL "
                "ORDER BY COALESCE(global_name, username) ASC LIMIT 1000"
            ), {'g': guild_id}).fetchall()
            if rows:
                members = [{
                    'id': str(r[0]),
                    'username': r[1] or '',
                    'display_name': r[2] or r[1] or '',
                    'avatar': r[3] or '',
                    'roles': json.loads(r[4]) if r[4] else [],
                } for r in rows if r[0]]
        except Exception:
            pass  # Table may not exist yet

        # 2. Fallback: cached_members JSON from guild-sync
        if not members:
            try:
                settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
                if settings and settings.cached_members:
                    cached = json.loads(settings.cached_members)
                    if isinstance(cached, list) and cached:
                        members = cached
            except (json.JSONDecodeError, TypeError):
                pass

        # 3. Fallback: fluxer_member_xp (anyone who has ever sent a message)
        if not members:
            rows = db.execute(text(
                "SELECT user_id, username FROM fluxer_member_xp "
                "WHERE guild_id = :g ORDER BY username ASC LIMIT 500"
            ), {'g': guild_id}).fetchall()
            members = [
                {'id': str(r[0]), 'username': r[1] or '', 'display_name': r[1] or '', 'avatar': '', 'roles': []}
                for r in rows if r[0]
            ]

        members.sort(key=lambda m: (m.get('display_name') or m.get('username') or '').lower())
    return JsonResponse({'members': members, 'cached': bool(members)})




# ---------------------------------------------------------------------------
# Fluxer Guild Flair Management (ADMIN)
# ---------------------------------------------------------------------------

def _guild_flair_dict(f: WebFluxerGuildFlair) -> dict:
    return {
        'id': f.id,
        'guild_id': f.guild_id,
        'flair_id': f.flair_id,
        'flair_name': f.flair_name,
        'flair_type': f.flair_type,
        'emoji': f.emoji or '',
        'enabled': bool(f.enabled),
        'admin_only': bool(getattr(f, 'admin_only', 0)),
        'hp_cost': f.hp_cost,
        'display_order': f.display_order,
    }


def _seed_guild_flairs(db, guild_id: str) -> None:
    """Auto-populate guild flair settings from global web_flairs on first load."""
    global_flairs = db.query(WebFlair).order_by(WebFlair.display_order).all()
    now = int(time.time())
    for gf in global_flairs:
        flair_type = gf.flair_type if gf.flair_type in ('normal', 'seasonal') else 'normal'
        entry = WebFluxerGuildFlair(
            guild_id=guild_id,
            flair_id=gf.id,
            flair_name=gf.name,
            flair_type=flair_type,
            emoji=gf.emoji or '',
            enabled=1,
            hp_cost=gf.hp_cost,
            display_order=gf.display_order,
            created_at=now,
        )
        db.add(entry)
    db.commit()


@fluxer_guild_required
def fluxer_guild_flair(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/flairs/ - Flair management page."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        ctx = _get_fluxer_guild_context(db, guild_id)
    _ensure_sidebar_guilds(request)
    return render(request, 'questlog_web/fluxer_guild_flair.html', {
        'web_user': request.web_user,
        'guild_id': guild_id,
        'guild_name': ctx['guild_name'],
        'guild_icon_url': ctx.get('guild_icon_url'),
        'all_guilds': ctx['all_guilds'],
        'is_owner': True,
        'is_network_approved': ctx.get('is_network_approved', False),
        'active_section': 'flair',
        'active_page': 'flair',
    })


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_flairs(request, guild_id):
    """
    GET  /ql/api/dashboard/fluxer/<guild_id>/flairs/ - list guild flairs (auto-seed if empty)
    POST /ql/api/dashboard/fluxer/<guild_id>/flairs/ - bulk update flair settings
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            rows = db.query(WebFluxerGuildFlair).filter_by(guild_id=guild_id).order_by(
                WebFluxerGuildFlair.display_order, WebFluxerGuildFlair.id
            ).all()
            if not rows:
                _seed_guild_flairs(db, guild_id)
                rows = db.query(WebFluxerGuildFlair).filter_by(guild_id=guild_id).order_by(
                    WebFluxerGuildFlair.display_order, WebFluxerGuildFlair.id
                ).all()
            return JsonResponse({'success': True, 'flairs': [_guild_flair_dict(f) for f in rows]})

    # POST - bulk update
    try:
        data = json.loads(request.body)
        flairs = data.get('flairs', [])
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if not isinstance(flairs, list):
        return JsonResponse({'error': 'flairs must be a list'}, status=400)

    updated = 0
    with get_db_session() as db:
        for item in flairs:
            flair_id = safe_int(item.get('id'), default=0)
            if not flair_id:
                continue
            row = db.query(WebFluxerGuildFlair).filter_by(id=flair_id, guild_id=guild_id).first()
            if not row:
                continue
            if 'enabled' in item:
                row.enabled = 1 if item['enabled'] else 0
            if 'admin_only' in item:
                row.admin_only = 1 if item['admin_only'] else 0
            if 'flair_name' in item:
                name = sanitize_text(str(item['flair_name']))[:100].strip()
                if name:
                    row.flair_name = name
            if 'hp_cost' in item:
                row.hp_cost = safe_int(item['hp_cost'], default=0, min_val=0, max_val=100000)
            if 'display_order' in item:
                row.display_order = safe_int(item['display_order'], default=0, min_val=0, max_val=9999)
            updated += 1
        db.commit()

    return JsonResponse({'success': True, 'updated': updated})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_flair_create(request, guild_id):
    """POST /ql/api/dashboard/fluxer/<guild_id>/flairs/create/ - create custom flair."""
    guild_id = guild_id.strip()
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    flair_name = sanitize_text(str(data.get('flair_name', ''))).strip()[:100]
    if not flair_name:
        return JsonResponse({'error': 'flair_name is required'}, status=400)

    hp_cost = safe_int(data.get('cost', 0), default=0, min_val=0, max_val=100000)
    display_order = safe_int(data.get('display_order', 0), default=0, min_val=0, max_val=9999)

    with get_db_session() as db:
        entry = WebFluxerGuildFlair(
            guild_id=guild_id,
            flair_id=None,
            flair_name=flair_name,
            flair_type='custom',
            emoji='',
            enabled=1,
            hp_cost=hp_cost,
            display_order=display_order,
            created_at=int(time.time()),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return JsonResponse({'success': True, 'flair': _guild_flair_dict(entry)})


@fluxer_guild_required
@require_http_methods(['DELETE'])
def api_fluxer_guild_flair_detail(request, guild_id, flair_id):
    """DELETE /ql/api/dashboard/fluxer/<guild_id>/flairs/<flair_id>/ - delete custom flair."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        row = db.query(WebFluxerGuildFlair).filter_by(id=flair_id, guild_id=guild_id).first()
        if not row:
            return JsonResponse({'error': 'Not found'}, status=404)
        if row.flair_type != 'custom':
            return JsonResponse({'error': 'Only custom flairs can be deleted'}, status=400)
        db.delete(row)
        db.commit()
    return JsonResponse({'success': True})


# =============================================================================
# LFG Attendance + Calendar
# =============================================================================

@fluxer_guild_required
def fluxer_guild_lfg_attendance(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/lfg/attendance/ - Attendance tracking page."""
    guild_id = guild_id.strip()

    def _extra(db, gid):
        cfg = db.query(WebFluxerLfgConfig).filter_by(guild_id=gid).first()
        games = db.query(WebFluxerLfgGame).filter_by(guild_id=gid, is_active=1).order_by(WebFluxerLfgGame.name).all()
        return {
            'lfg_config': cfg,
            'lfg_config_json': json.dumps({
                'auto_noshow_hours': cfg.auto_noshow_hours if cfg else 1,
                'warn_at_reliability': cfg.warn_at_reliability if cfg else 50,
                'min_required_score': cfg.min_required_score if cfg else 0,
                'auto_blacklist_noshow': cfg.auto_blacklist_noshow if cfg else 0,
            }),
            'games_json': json.dumps([{'id': g.id, 'name': g.name} for g in games]),
        }

    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_lfg_attendance.html', 'lfg_attendance', extra=_extra)


@fluxer_guild_required
def fluxer_guild_lfg_calendar(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/lfg/calendar/ - LFG Calendar page."""
    guild_id = guild_id.strip()
    now_ts = int(time.time())
    cutoff = now_ts - 86400  # include events that ended up to 1 day ago
    current_user_id = getattr(request.web_user, 'id', None) if request.web_user else None

    def _extra(db, gid):
        groups = (
            db.query(WebFluxerLfgGroup)
            .filter(
                WebFluxerLfgGroup.guild_id == gid,
                WebFluxerLfgGroup.scheduled_time != None,  # noqa: E711
                WebFluxerLfgGroup.scheduled_time >= cutoff,
            )
            .order_by(WebFluxerLfgGroup.scheduled_time)
            .limit(365)
            .all()
        )
        events = [
            {
                'id': g.id,
                'title': g.title or g.game_name,
                'game_name': g.game_name,
                'ts': g.scheduled_time,
                'status': g.status,
                'current_size': g.current_size,
                'max_size': g.max_size,
                'recurrence': g.recurrence or 'none',
                'description': g.description or '',
            }
            for g in groups
        ]
        # Query current user's active memberships in this guild's groups
        my_group_ids = []
        my_creator_ids = []
        if current_user_id and groups:
            group_ids = [g.id for g in groups]
            my_members = db.query(WebFluxerLfgMember).filter(
                WebFluxerLfgMember.group_id.in_(group_ids),
                WebFluxerLfgMember.web_user_id == current_user_id,
                WebFluxerLfgMember.left_at.is_(None),
            ).all()
            for m in my_members:
                my_group_ids.append(m.group_id)
                if m.is_creator:
                    my_creator_ids.append(m.group_id)
        return {
            'events_json': json.dumps(events),
            'my_group_ids_json': json.dumps(my_group_ids),
            'my_creator_ids_json': json.dumps(my_creator_ids),
        }

    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_lfg_calendar.html', 'lfg_calendar', extra=_extra)


@fluxer_guild_required
def fluxer_guild_discovery(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/discovery/ - Discovery & Member Features hub."""
    guild_id = guild_id.strip()

    def _extra(db, gid):
        # LFG stats
        total_groups = db.query(WebFluxerLfgGroup).filter_by(guild_id=gid).count()
        open_groups = db.query(WebFluxerLfgGroup).filter_by(guild_id=gid, status='open').count()

        # Active LFG members (currently in a group)
        active_members = db.execute(text(
            "SELECT COUNT(DISTINCT m.web_user_id) FROM web_fluxer_lfg_members m "
            "JOIN web_fluxer_lfg_groups g ON g.id = m.group_id "
            "WHERE g.guild_id = :gid AND g.status = 'open' AND m.left_at IS NULL AND m.web_user_id IS NOT NULL"
        ), {'gid': gid}).scalar() or 0

        # Discovery setting
        settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=gid).first()
        discovery_enabled = bool(settings.discovery_enabled) if settings else False

        # LFG config for publish_to_network
        lfg_cfg = db.query(WebFluxerLfgConfig).filter_by(guild_id=gid).first()
        publish_to_network = bool(lfg_cfg.publish_to_network) if lfg_cfg else False

        # Game discovery - search configs
        search_configs_raw = db.query(WebFluxerGameSearchConfig).filter_by(guild_id=gid).order_by(
            WebFluxerGameSearchConfig.name
        ).all()
        search_configs = []
        for c in search_configs_raw:
            d = _game_search_config_dict(c)
            d['genres_list'] = d['genres']
            d['themes_list'] = d['themes']
            d['keywords_list'] = d['keywords']
            d['modes_list'] = d['game_modes']
            d['platforms_list'] = d['platforms']
            search_configs.append(d)

        # Recent found games (for stats sidebar)
        import json as _json
        from datetime import datetime
        recent_raw = db.query(WebFluxerFoundGame).filter_by(guild_id=gid).order_by(
            WebFluxerFoundGame.found_at.desc()
        ).limit(10).all()
        recent_found_games = []
        for g in recent_raw:
            rd = g.release_date
            if rd:
                try:
                    fmt = datetime.utcfromtimestamp(rd).strftime('%b %d, %Y')
                except Exception:
                    fmt = 'TBD'
            else:
                fmt = 'TBD'
            recent_found_games.append({
                'game_name': g.game_name,
                'cover_url': g.cover_url or '',
                'igdb_url': g.igdb_url or '',
                'steam_url': g.steam_url or '',
                'genres_list': _json.loads(g.genres) if g.genres else [],
                'formatted_date': fmt,
            })
        found_games_count = db.query(WebFluxerFoundGame).filter_by(guild_id=gid).count()

        return {
            'total_groups': total_groups,
            'open_groups': open_groups,
            'active_members': active_members,
            'discovery_enabled': discovery_enabled,
            'publish_to_network': publish_to_network,
            'search_configs': search_configs,
            'total_search_configs': len(search_configs),
            'recent_found_games': recent_found_games,
            'found_games_count': found_games_count,
            'available_genres': _AVAILABLE_GENRES,
            'available_themes': _AVAILABLE_THEMES,
            'available_modes': _AVAILABLE_MODES,
            'available_platforms': _AVAILABLE_PLATFORMS,
            # Game discovery global settings
            'game_discovery_enabled': bool(settings.game_discovery_enabled) if settings else False,
            'game_discovery_channel_id': settings.game_discovery_channel_id or '' if settings else '',
            'game_discovery_ping_role_id': settings.game_discovery_ping_role_id or '' if settings else '',
            'game_check_interval_hours': settings.game_check_interval_hours or 24 if settings else 24,
        }

    valid_tabs = {'creator', 'games', 'rss', 'network', 'twitch', 'youtube'}
    active_tab = request.GET.get('tab', 'creator')
    if active_tab not in valid_tabs:
        active_tab = 'creator'
    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_discovery.html', 'discovery',
                       extra=lambda db, gid: {**_extra(db, gid), 'active_tab': active_tab})


@fluxer_guild_required
def fluxer_guild_lfg_browse_admin(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/lfg/browse/ - Find Groups within the Fluxer dashboard."""
    guild_id = guild_id.strip()

    def _extra(db, gid):
        groups = (
            db.query(WebFluxerLfgGroup)
            .filter_by(guild_id=gid, status='open')
            .order_by(WebFluxerLfgGroup.created_at.desc())
            .limit(100)
            .all()
        )
        games = (
            db.query(WebFluxerLfgGame)
            .filter_by(guild_id=gid, is_active=1)
            .order_by(WebFluxerLfgGame.name)
            .all()
        )
        group_ids = [g.id for g in groups]
        members_raw = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id.in_(group_ids),
            WebFluxerLfgMember.left_at.is_(None),
        ).all() if group_ids else []
        members_by_group: dict = {}
        for m in members_raw:
            members_by_group.setdefault(m.group_id, []).append({
                'id': m.id,
                'username': m.username or 'Unknown',
                'role': m.role or 'member',
                'is_creator': bool(m.is_creator),
                'is_co_leader': (m.role or '') == 'co_leader',
                'web_user_id': m.web_user_id,
                'selections': json.loads(m.selections_json) if m.selections_json else {},
                'joined_at': m.joined_at,
            })

        groups_data = [
            {
                'id': g.id,
                'game_id': g.game_id,
                'game_name': g.game_name,
                'title': g.title or '',
                'description': g.description or '',
                'max_size': g.max_size,
                'current_size': g.current_size,
                'creator_name': g.creator_name or 'Unknown',
                'creator_web_user_id': g.creator_web_user_id,
                'scheduled_time': g.scheduled_time,
                'created_at': g.created_at,
                'status': g.status,
                'members': members_by_group.get(g.id, []),
                'tanks_needed': getattr(g, 'tanks_needed', 0) or 0,
                'healers_needed': getattr(g, 'healers_needed', 0) or 0,
                'dps_needed': getattr(g, 'dps_needed', 0) or 0,
                'support_needed': getattr(g, 'support_needed', 0) or 0,
                'role_schema': json.loads(g.role_schema) if getattr(g, 'role_schema', None) else None,
            }
            for g in groups
        ]
        games_data = [
            {'id': gm.id, 'name': gm.name, 'emoji': gm.emoji or ''}
            for gm in games
        ]
        # Full game config for create modal
        games_full = [_lfg_game_dict(gm) for gm in games]
        cfg = db.query(WebFluxerLfgConfig).filter_by(guild_id=gid).first()
        publish_default = bool(getattr(cfg, 'publish_to_network', 0)) if cfg else False
        return {
            'groups_data': groups_data,
            'games_data': games_data,
            'games_full_data': games_full,
            'group_count': len(groups_data),
            'lfg_publish_default': publish_default,
        }

    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_lfg_browse.html', 'lfg_browse', extra=_extra)


@web_login_required
@add_web_user_context
def fluxer_guild_found_games(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/found-games/ - Found Games within the Fluxer dashboard."""
    import json as _json
    from datetime import datetime
    guild_id = guild_id.strip()

    sort_by = request.GET.get('sort', 'release')
    game_name_filter = request.GET.get('game_name', '').strip()
    min_hype_param = request.GET.get('min_hype', '')
    min_hype = int(min_hype_param) if min_hype_param and min_hype_param.isdigit() else None
    search_id = request.GET.get('search_id', '')

    def _extra(db, gid):
        query = db.query(WebFluxerFoundGame).filter_by(guild_id=gid)
        if search_id:
            query = query.filter(WebFluxerFoundGame.search_config_id == int(search_id))
        raw = query.order_by(WebFluxerFoundGame.found_at.desc()).limit(300).all()
        total_found = db.query(WebFluxerFoundGame).filter_by(guild_id=gid).count()
        cfg_rows = db.query(WebFluxerGameSearchConfig).filter_by(
            guild_id=gid, enabled=1, show_on_website=1
        ).order_by(WebFluxerGameSearchConfig.name).all()
        search_configs = [{'id': c.id, 'name': c.name} for c in cfg_rows]

        games = []
        for g in raw:
            modes = _json.loads(g.game_modes) if g.game_modes else []
            kws = _json.loads(g.keywords) if g.keywords else []
            if game_name_filter and game_name_filter.lower() not in g.game_name.lower():
                continue
            if min_hype is not None and (g.hypes is None or g.hypes < min_hype):
                continue
            rd = g.release_date
            try:
                fmt_date = datetime.utcfromtimestamp(rd).strftime('%b %d, %Y') if rd else 'TBD'
            except Exception:
                fmt_date = 'TBD'
            games.append({
                'id': g.id,
                'game_name': g.game_name,
                'cover_url': g.cover_url or '',
                'igdb_url': g.igdb_url or '',
                'steam_url': g.steam_url or '',
                'release_date': rd,
                'release_date_fmt': fmt_date,
                'genres': _json.loads(g.genres) if g.genres else [],
                'keywords': kws,
                'hypes': g.hypes,
                'rating': g.rating,
                'summary': g.summary or '',
            })

        if sort_by == 'release':
            games.sort(key=lambda x: (0, x['release_date']) if x['release_date'] else (1, 0))
        elif sort_by == 'hype':
            games.sort(key=lambda x: -(x['hypes'] or 0))
        elif sort_by == 'name':
            games.sort(key=lambda x: x['game_name'].lower())

        return {
            'games': games,
            'total_found': total_found,
            'search_configs': search_configs,
            'sort_by': sort_by,
            'game_name_filter': game_name_filter,
            'min_hype_param': min_hype_param,
        }

    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_found_games.html', 'found_games', extra=_extra)


@fluxer_guild_required
def fluxer_guild_rss_articles(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/rss-articles/ - RSS Articles within the Fluxer dashboard."""
    import json as _json
    from datetime import datetime
    guild_id = guild_id.strip()
    feed_filter = safe_int(request.GET.get('feed_id', ''), default=0)

    def _extra(db, gid):
        feed_rows = db.query(WebFluxerRssFeed).filter_by(
            guild_id=gid, is_active=1
        ).order_by(WebFluxerRssFeed.created_at.asc()).all()
        feeds = [{'id': f.id, 'label': f.label or f.url} for f in feed_rows]

        query = db.query(WebFluxerRssArticle).filter_by(guild_id=gid)
        if feed_filter:
            query = query.filter(WebFluxerRssArticle.feed_id == feed_filter)
        total_articles = query.count()
        article_rows = query.order_by(WebFluxerRssArticle.published_at.desc()).limit(100).all()

        articles = []
        for a in article_rows:
            cats = _json.loads(a.entry_categories) if a.entry_categories else []
            pub = ''
            if a.published_at:
                try:
                    pub = datetime.utcfromtimestamp(a.published_at).strftime('%b %d, %Y')
                except Exception:
                    pass
            posted = ''
            if a.posted_at:
                try:
                    posted = datetime.utcfromtimestamp(a.posted_at).strftime('%b %d')
                except Exception:
                    pass
            articles.append({
                'title': a.entry_title or '',
                'link': a.entry_link or '',
                'summary': a.entry_summary or '',
                'author': a.entry_author or '',
                'thumbnail': a.entry_thumbnail or '',
                'feed_label': a.feed_label or '',
                'categories': cats,
                'published_at': pub,
                'posted_at': posted,
            })

        return {
            'feeds': feeds,
            'feeds_json': _json.dumps(feeds),
            'articles': articles,
            'total_articles': total_articles,
            'selected_feed_id': str(feed_filter) if feed_filter else '',
        }

    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_rss_articles.html', 'rss_articles', extra=_extra)


@web_login_required
@add_web_user_context
def fluxer_guild_leaderboards(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/leaderboards/ - Guild XP leaderboard."""
    from .views_pages import _fluxer_guild_base_context
    _settings, ctx = _fluxer_guild_base_context(request, guild_id)
    guild_id = guild_id.strip()

    try:
        with get_db_session() as db:
            from sqlalchemy import text as sa_text

            is_unified = bool(db.execute(sa_text(
                "SELECT 1 FROM web_communities "
                "WHERE platform='fluxer' AND platform_id=:g AND site_xp_to_guild=1 "
                "AND network_status='approved' AND is_active=1 LIMIT 1"
            ), {'g': guild_id}).fetchone())

            _HIDDEN_USER_IDS = [1]      # site owners hidden from leaderboards
            _HIDDEN_FLUXER_IDS = ['1473922619936604188']

            if is_unified:
                xp_rows = db.execute(sa_text(
                    "SELECT wu.username, ul.xp_total "
                    "FROM web_unified_leaderboard ul "
                    "JOIN web_users wu ON wu.id = ul.user_id "
                    "WHERE ul.guild_id=:g AND ul.platform='fluxer' AND ul.xp_total > 0 "
                    "AND wu.id NOT IN :hidden "
                    "ORDER BY ul.xp_total DESC LIMIT 10"
                ), {'g': guild_id, 'hidden': tuple(_HIDDEN_USER_IDS + [0])}).fetchall()
                xp_leaders = [{'username': r[0], 'xp': r[1]} for r in xp_rows]
                xp_label = 'QuestLog XP'
            else:
                xp_rows = db.execute(sa_text(
                    "SELECT username, xp FROM fluxer_member_xp WHERE guild_id=:g AND xp > 0 "
                    "AND user_id NOT IN :hidden "
                    "ORDER BY xp DESC LIMIT 10"
                ), {'g': guild_id, 'hidden': tuple(_HIDDEN_FLUXER_IDS + [''])}).fetchall()
                xp_leaders = [{'username': r[0], 'xp': r[1]} for r in xp_rows]
                xp_label = 'Server XP'

            msg_rows = db.execute(sa_text(
                "SELECT username, message_count FROM fluxer_member_xp WHERE guild_id=:g AND message_count > 0 "
                "AND user_id NOT IN :hidden "
                "ORDER BY message_count DESC LIMIT 10"
            ), {'g': guild_id, 'hidden': tuple(_HIDDEN_FLUXER_IDS + [''])}).fetchall()
            voice_rows = db.execute(sa_text(
                "SELECT username, voice_minutes FROM fluxer_member_xp WHERE guild_id=:g AND voice_minutes > 0 "
                "AND user_id NOT IN :hidden "
                "ORDER BY voice_minutes DESC LIMIT 10"
            ), {'g': guild_id, 'hidden': tuple(_HIDDEN_FLUXER_IDS + [''])}).fetchall()
    except Exception:
        xp_leaders, xp_label, is_unified, msg_rows, voice_rows = [], 'Server XP', False, [], []

    ctx.update({
        'active_page': 'leaderboards',
        'xp_leaders': xp_leaders,
        'xp_label': xp_label,
        'is_unified': is_unified,
        'msg_leaders': [{'username': r[0], 'message_count': r[1]} for r in msg_rows],
        'voice_leaders': [{'username': r[0], 'voice_minutes': r[1]} for r in voice_rows],
    })
    return render(request, 'questlog_web/fluxer_guild_leaderboards.html', ctx)


@fluxer_guild_required
def fluxer_guild_member_profile_page(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/profile/ - Member's own profile in this guild."""
    guild_id = guild_id.strip()

    def _extra(db, gid):
        from sqlalchemy import text as sa_text
        fluxer_id = str(getattr(request, 'fluxer_id', '') or '')
        web_user = getattr(request, 'web_user', None)
        stats = None

        # Check if this guild has unified XP enabled
        is_unified = bool(db.execute(sa_text(
            "SELECT 1 FROM web_communities "
            "WHERE platform='fluxer' AND platform_id=:g AND site_xp_to_guild=1 "
            "AND network_status='approved' AND is_active=1 LIMIT 1"
        ), {'g': gid}).fetchone())

        if fluxer_id:
            row = db.execute(sa_text(
                "SELECT username, xp, message_count, voice_minutes, reaction_count "
                "FROM fluxer_member_xp WHERE guild_id=:g AND user_id=:u LIMIT 1"
            ), {'g': gid, 'u': fluxer_id}).fetchone()
            if row:
                # Unified: use web_xp/web_level if user has a linked QL account
                if is_unified and web_user and getattr(web_user, 'web_xp', None) is not None:
                    xp = int(web_user.web_xp or 0)
                    level = int(web_user.web_level or 1)
                    xp_label = 'QuestLog XP'
                else:
                    xp = int(row[1] or 0)
                    level = 1
                    while level < 99 and xp >= int(7 * ((level + 1) ** 1.5)):
                        level += 1
                    xp_label = 'Server XP'
                stats = {
                    'username': row[0] or 'Unknown',
                    'xp': xp,
                    'xp_label': xp_label,
                    'level': level,
                    'message_count': int(row[2] or 0),
                    'voice_minutes': int(row[3] or 0),
                    'reaction_count': int(row[4] or 0),
                    'is_unified': is_unified,
                }
        # Equipped flair from WebFluxerMemberFlair
        equipped_flair = None
        web_user = getattr(request, 'web_user', None)
        web_user_id = getattr(web_user, 'id', None) if web_user else None
        if web_user_id:
            from .models import WebFluxerMemberFlair, WebFluxerGuildFlair
            mf = db.query(WebFluxerMemberFlair).filter_by(
                guild_id=gid, web_user_id=web_user_id, equipped=1
            ).first()
            if mf:
                gf = db.query(WebFluxerGuildFlair).filter_by(id=mf.guild_flair_id).first()
                if gf:
                    equipped_flair = {'emoji': gf.emoji or '', 'name': gf.flair_name or ''}
        return {'member_stats': stats, 'equipped_flair': equipped_flair}

    return _guild_view(request, guild_id, 'questlog_web/fluxer_guild_member_profile_page.html', 'profile', extra=_extra)


@web_login_required
@add_web_user_context
def fluxer_guild_featured_creators(request, guild_id):
    """GET /ql/dashboard/fluxer/<guild_id>/featured-creators/ - QuestLog creators featured in this guild."""
    from .views_pages import _fluxer_guild_base_context
    _settings, ctx = _fluxer_guild_base_context(request, guild_id)
    ctx.update({
        'active_page': 'featured_creators',
        'is_network': ctx.get('is_network_approved', False),
    })
    return render(request, 'questlog_web/fluxer_guild_featured_creators.html', ctx)


def _group_dict(g: WebFluxerLfgGroup, members: list) -> dict:
    return {
        'id': g.id,
        'game_id': g.game_id,
        'game_name': g.game_name,
        'title': g.title or '',
        'description': g.description or '',
        'max_size': g.max_size,
        'current_size': g.current_size,
        'creator_name': g.creator_name or 'Unknown',
        'creator_web_user_id': g.creator_web_user_id,
        'scheduled_time': g.scheduled_time,
        'created_at': g.created_at,
        'status': g.status,
        'members': members,
        'tanks_needed': getattr(g, 'tanks_needed', 0) or 0,
        'healers_needed': getattr(g, 'healers_needed', 0) or 0,
        'dps_needed': getattr(g, 'dps_needed', 0) or 0,
        'support_needed': getattr(g, 'support_needed', 0) or 0,
        'role_schema': json.loads(g.role_schema) if getattr(g, 'role_schema', None) else None,
        'recurrence': getattr(g, 'recurrence', 'none') or 'none',
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_lfg_groups(request, guild_id):
    """GET list / POST create LFG groups for a Fluxer guild."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        if request.method == 'GET':
            groups = db.query(WebFluxerLfgGroup).filter(
                WebFluxerLfgGroup.guild_id == guild_id,
                WebFluxerLfgGroup.status.in_(['open', 'full']),
            ).order_by(WebFluxerLfgGroup.created_at.desc()).limit(100).all()

            group_ids = [g.id for g in groups]
            members_raw = db.query(WebFluxerLfgMember).filter(
                WebFluxerLfgMember.group_id.in_(group_ids),
                WebFluxerLfgMember.left_at.is_(None),
            ).all() if group_ids else []
            members_by_group: dict = {}
            for m in members_raw:
                members_by_group.setdefault(m.group_id, []).append({
                    'id': m.id, 'username': m.username or 'Unknown',
                    'role': m.role or 'member', 'is_creator': bool(m.is_creator),
                    'is_co_leader': (m.role or '') == 'co_leader',
                    'web_user_id': m.web_user_id,
                    'selections': json.loads(m.selections_json) if m.selections_json else {},
                    'joined_at': m.joined_at,
                })
            return JsonResponse({'success': True, 'groups': [
                _group_dict(g, members_by_group.get(g.id, [])) for g in groups
            ]})

        # POST - create
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        game_id = safe_int(data.get('game_id'), default=0, min_val=1, max_val=9999999)
        if not game_id:
            return JsonResponse({'error': 'Game is required'}, status=400)
        game = db.query(WebFluxerLfgGame).filter_by(id=game_id, guild_id=guild_id, is_active=1).first()
        if not game:
            return JsonResponse({'error': 'Game not found'}, status=404)

        title = (data.get('title') or '').strip()[:200]
        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)

        now = int(time.time())
        max_size = safe_int(data.get('max_size'), default=game.max_group_size or 5, min_val=2, max_val=100)
        st_raw = data.get('scheduled_time')
        scheduled_time = safe_int(st_raw, default=0, min_val=1, max_val=9999999999) if st_raw else None
        description = (data.get('description') or '')[:2000] or None
        creator_name = (request.web_user.display_name or request.web_user.username) if request.web_user else 'Admin'

        rec_raw = (data.get('recurrence') or 'none').strip()
        recurrence = rec_raw if rec_raw in ('none', 'daily', 'weekly', 'monthly') else 'none'
        post_to_network = bool(data.get('post_to_network', False))
        game_cover_url = (data.get('game_cover_url') or game.cover_url or '')[:500] or None
        _sil_raw = (data.get('server_invite_link') or '').strip()
        server_invite_link = _sil_raw[:500] if _sil_raw.startswith('https://') else None

        # Role composition
        use_roles = bool(data.get('use_roles', False))
        tanks_needed = safe_int(data.get('tanks_needed'), default=0, min_val=0, max_val=50) if use_roles else 0
        healers_needed = safe_int(data.get('healers_needed'), default=0, min_val=0, max_val=50) if use_roles else 0
        dps_needed = safe_int(data.get('dps_needed'), default=0, min_val=0, max_val=200) if use_roles else 0
        support_needed = safe_int(data.get('support_needed'), default=0, min_val=0, max_val=50) if use_roles else 0
        enforce_role_limits = bool(data.get('enforce_role_limits', True))
        role_schema_raw = data.get('role_schema')
        # Survival games: no slot counts - role_schema stores opt-in flag for card display
        if use_roles and not role_schema_raw and not (tanks_needed or healers_needed or dps_needed or support_needed):
            role_schema = '{"survival":true}'
        else:
            role_schema = json.dumps(role_schema_raw) if role_schema_raw and isinstance(role_schema_raw, list) else None
        if use_roles:
            max_size = (tanks_needed + healers_needed + dps_needed + support_needed) or max_size

        # Resolve guild name for origin tracking
        guild_settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
        guild_display_name = (guild_settings.guild_name if guild_settings and guild_settings.guild_name else None)

        group = WebFluxerLfgGroup(
            guild_id=guild_id, game_id=game_id, game_name=game.name,
            title=title, description=description, max_size=max_size, current_size=1,
            creator_web_user_id=request.web_user.id if request.web_user else None,
            creator_name=creator_name,
            scheduled_time=scheduled_time, status='open', created_at=now,
            recurrence=recurrence,
            tanks_needed=tanks_needed, healers_needed=healers_needed,
            dps_needed=dps_needed, support_needed=support_needed,
            enforce_role_limits=1 if enforce_role_limits else 0,
            role_schema=role_schema,
            server_invite_link=server_invite_link,
        )
        db.add(group)
        db.flush()

        selections = data.get('selections') or {}
        # Detect creator's role from their selections (WoW spec mapping, ESO role field, etc.)
        from .views_pages import _detect_lfg_role
        creator_role = _detect_lfg_role(selections, game.options_json if game else None)
        db.add(WebFluxerLfgMember(
            group_id=group.id,
            web_user_id=request.web_user.id if request.web_user else None,
            username=creator_name, role=creator_role,
            selections_json=json.dumps(selections) if selections else None,
            is_creator=1, joined_at=now,
        ))

        # Optional co-leader from guild members
        co_leader_id = (data.get('co_leader_id') or '')[:32] or None
        co_leader_name = (data.get('co_leader_name') or '')[:100] or None
        if co_leader_id:
            db.add(WebFluxerLfgMember(
                group_id=group.id,
                fluxer_user_id=co_leader_id,
                username=co_leader_name or co_leader_id,
                role='co_leader', is_creator=0, joined_at=now,
            ))
            group.current_size = 2

        db.commit()

        # Post to QuestLog Network if requested - fire and forget
        network_group_id = None
        if post_to_network:
            try:
                from .models import WebLFGGroup, WebLFGMember, WebCommunityBotConfig
                from sqlalchemy import text as _text
                import json as _json, time as _time
                from .views_discovery import _parse_role_schema as _prs
                from .fluxer_webhooks import build_lfg_embed_data as _blfg

                web_role_schema = _prs(role_schema) if role_schema else []

                # Site post only if linked QuestLog account exists
                web_group = None
                group_url = ''
                if request.web_user:
                    web_group = WebLFGGroup(
                        creator_id=request.web_user.id,
                        title=title,
                        description=description,
                        game_name=game.name,
                        game_image_url=game_cover_url,
                        group_size=max_size,
                        current_size=1,
                        scheduled_time=scheduled_time,
                        status='open',
                        use_roles=1 if use_roles else 0,
                        tanks_needed=tanks_needed,
                        healers_needed=healers_needed,
                        dps_needed=dps_needed,
                        support_needed=support_needed,
                        role_schema=role_schema,
                        created_at=now,
                        updated_at=now,
                        origin_platform='fluxer',
                        origin_group_id=group.id,
                        origin_guild_id=str(guild_id),
                        origin_guild_name=guild_display_name,
                    )
                    db.add(web_group)
                    db.flush()
                    db.add(WebLFGMember(
                        group_id=web_group.id,
                        user_id=request.web_user.id,
                        role=creator_role,
                        selections=json.dumps(selections) if selections else None,
                        is_creator=True,
                        status='joined',
                        joined_at=now,
                    ))
                    db.commit()
                    group_url = f"https://casual-heroes.com/ql/lfg/{web_group.id}/"

                # Always broadcast to opted-in guilds - no linked account required
                embed_data = _blfg(
                    creator=creator_name,
                    game_name=game.name,
                    title=title,
                    description=description or '',
                    group_size=max_size,
                    current_size=1,
                    scheduled_time=scheduled_time,
                    lfg_url=group_url,
                    game_image_url=game_cover_url,
                    use_roles=use_roles,
                    role_schema=web_role_schema,
                    tanks_needed=tanks_needed,
                    healers_needed=healers_needed,
                    dps_needed=dps_needed,
                    support_needed=support_needed,
                    creator_selections=selections,
                    group_id=web_group.id if web_group else None,
                    group_platform='web',
                    server_invite_link=server_invite_link,
                )
                embed_data["color"] = 0xFEE75C
                embed_data["footer"] = "QuestLog Network - casual-heroes.com/ql/lfg/"
                embed_data["fields"].append({"name": "Posted via", "value": "Fluxer", "inline": True})
                embed_data["thread_name"] = f"{title} - {game.name} - {creator_name}"

                payload_json = _json.dumps(embed_data)
                broadcast_now = int(_time.time())
                _broadcast_game = game.name.lower() if game.name else ''
                configs = db.query(WebCommunityBotConfig).filter_by(
                    event_type='lfg_announce'
                ).all()

                for cfg in configs:
                    # Check if this receiving guild has opted in for this specific game
                    if cfg.platform == 'discord':
                        _game_row = db.execute(_text(
                            "SELECT lfg_channel_id FROM lfg_games WHERE guild_id=:g AND LOWER(game_name)=:gn "
                            "AND receive_network_lfg=1 AND enabled=1 LIMIT 1"
                        ), {"g": int(cfg.guild_id), "gn": _broadcast_game}).fetchone()
                    else:
                        _game_row = db.execute(_text(
                            "SELECT channel_id FROM web_fluxer_lfg_games WHERE guild_id=:g AND LOWER(name)=:gn "
                            "AND receive_network_lfg=1 AND enabled=1 AND is_active=1 LIMIT 1"
                        ), {"g": cfg.guild_id, "gn": _broadcast_game}).fetchone()

                    if not _game_row:
                        continue

                    # Use per-game channel if set, otherwise fall back to master bot config channel
                    _dest_channel = str(_game_row[0]).strip() if _game_row[0] else cfg.channel_id

                    if cfg.platform == 'discord':
                        db.execute(_text(
                            "INSERT INTO discord_pending_broadcasts (guild_id, channel_id, payload, created_at) "
                            "VALUES (:gid, :cid, :payload, :now)"
                        ), {"gid": int(cfg.guild_id), "cid": int(_dest_channel), "payload": payload_json, "now": broadcast_now})
                    else:
                        db.execute(_text(
                            "INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at) "
                            "VALUES (:gid, :cid, :payload, :now)"
                        ), {"gid": cfg.guild_id, "cid": _dest_channel, "payload": payload_json, "now": broadcast_now})

                db.commit()
                network_group_id = web_group.id
            except Exception as _e:
                import logging as _logging
                _logging.getLogger(__name__).warning(f"[LFG] Fluxer network post failed for group {group.id}: {_e}")

        members = [{'id': 1, 'username': creator_name, 'role': creator_role,
                    'is_creator': True, 'selections': selections, 'joined_at': now}]
        return JsonResponse({'success': True, 'group': _group_dict(group, members), 'network_group_id': network_group_id})


@fluxer_guild_required
@require_http_methods(['PUT', 'DELETE'])
def api_fluxer_guild_lfg_group_detail(request, guild_id, group_id):
    """PUT edit / DELETE close a Fluxer LFG group."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id, guild_id=guild_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        if request.method == 'DELETE':
            group.status = 'closed'
            group.closed_at = int(time.time())
            db.commit()
            return JsonResponse({'success': True})

        # PUT
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'title' in data:
            group.title = (data['title'] or '').strip()[:200]
        if 'description' in data:
            group.description = (data.get('description') or '')[:2000] or None
        if 'max_size' in data:
            group.max_size = safe_int(data['max_size'], default=group.max_size, min_val=2, max_val=100)
        if 'scheduled_time' in data:
            st = data.get('scheduled_time')
            group.scheduled_time = safe_int(st, default=0, min_val=1, max_val=9999999999) if st else None
        if 'recurrence' in data:
            rec = (data.get('recurrence') or 'none').strip()
            group.recurrence = rec if rec in ('none', 'daily', 'weekly', 'monthly') else 'none'
        if 'status' in data:
            requested = (data.get('status') or '').strip()
            if requested in ('open', 'closed'):
                group.status = requested
                if requested == 'closed':
                    group.closed_at = int(time.time())

        # Role composition slots
        if 'tanks_needed' in data:
            group.tanks_needed = safe_int(data['tanks_needed'], default=0, min_val=0, max_val=50)
        if 'healers_needed' in data:
            group.healers_needed = safe_int(data['healers_needed'], default=0, min_val=0, max_val=50)
        if 'dps_needed' in data:
            group.dps_needed = safe_int(data['dps_needed'], default=0, min_val=0, max_val=50)
        if 'support_needed' in data:
            group.support_needed = safe_int(data['support_needed'], default=0, min_val=0, max_val=50)
        if 'enforce_role_limits' in data:
            group.enforce_role_limits = 1 if data['enforce_role_limits'] else 0

        # Sync max_size to total role slots if role composition enabled
        total_slots = (group.tanks_needed or 0) + (group.healers_needed or 0) + (group.dps_needed or 0) + (group.support_needed or 0)
        if total_slots > 0 and 'tanks_needed' in data:
            group.max_size = total_slots

        # Co-leader updates
        if 'co_leaders' in data and isinstance(data['co_leaders'], list):
            for entry in data['co_leaders']:
                mid = safe_int(entry.get('member_id'), default=0, min_val=1, max_val=9999999)
                if not mid:
                    continue
                m = db.query(WebFluxerLfgMember).filter_by(id=mid, group_id=group.id).first()
                if not m or m.is_creator or m.left_at is not None:
                    continue
                if entry.get('is_co_leader'):
                    m.role = 'co_leader'
                else:
                    # Demote - re-detect their actual role
                    from .views_pages import _detect_lfg_role
                    game = db.query(WebFluxerLfgGame).filter_by(id=group.game_id).first()
                    sels = json.loads(m.selections_json) if m.selections_json else {}
                    m.role = _detect_lfg_role(sels, game.options_json if game else None)

        # Auto-set full/open based on capacity (only if not being manually closed)
        if group.status != 'closed':
            group.status = 'full' if group.current_size >= group.max_size else 'open'
        db.commit()
        return JsonResponse({'success': True})


@fluxer_guild_required
@require_http_methods(['POST'])
def api_fluxer_guild_lfg_group_kick(request, guild_id, group_id, member_id):
    """POST kick a member from a Fluxer LFG group."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id, guild_id=guild_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        member = db.query(WebFluxerLfgMember).filter_by(id=member_id, group_id=group_id).first()
        if not member:
            return JsonResponse({'error': 'Member not found'}, status=404)
        if member.is_creator:
            return JsonResponse({'error': 'Cannot remove the group creator'}, status=400)

        member.left_at = int(time.time())
        group.current_size = max(1, group.current_size - 1)
        if group.status == 'full' and group.current_size < group.max_size:
            group.status = 'open'
        db.commit()
        return JsonResponse({'success': True})


@fluxer_guild_required
@require_http_methods(['PUT'])
def api_fluxer_guild_lfg_member_update(request, guild_id, group_id, member_id):
    """PUT update a member's selections/role in a Fluxer LFG group (admin dashboard)."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id, guild_id=guild_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        member = db.query(WebFluxerLfgMember).filter_by(id=member_id, group_id=group_id).first()
        if not member or member.left_at is not None:
            return JsonResponse({'error': 'Member not found'}, status=404)
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        selections = data.get('selections') or {}
        if selections and isinstance(selections, dict):
            member.selections_json = json.dumps(selections)
        elif not selections:
            member.selections_json = None
        # Re-detect role from updated selections
        from .views_pages import _detect_lfg_role
        game = db.query(WebFluxerLfgGame).filter_by(id=group.game_id).first()
        detected = _detect_lfg_role(selections, game.options_json if game else None)
        # Preserve creator/co_leader role designations; only update regular members
        if member.role not in ('co_leader',) and not member.is_creator:
            member.role = detected
        elif member.is_creator:
            member.role = detected  # Creator can also have their class updated
        db.commit()
        return JsonResponse({'success': True})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_lfg_attendance(request, guild_id):
    """GET /ql/api/dashboard/fluxer/<guild_id>/lfg/attendance/
    Params: game_id, user (search), days (0=all), status
    Returns grouped attendance data.
    """
    guild_id = guild_id.strip()
    game_id = safe_int(request.GET.get('game_id', 0), default=0, min_val=0)
    user_q = (request.GET.get('user', '') or '').strip()[:100]
    days = safe_int(request.GET.get('days', 30), default=30, min_val=0, max_val=365)
    status_filter = (request.GET.get('status', '') or '').strip()
    VALID_STATUSES = {'pending', 'confirmed', 'showed', 'no_show', 'late', 'cancelled', 'pardoned'}

    now_ts = int(time.time())
    cutoff_ts = (now_ts - days * 86400) if days > 0 else 0

    with get_db_session() as db:
        # Query attendance rows
        q = db.query(WebFluxerLfgAttendance).filter(WebFluxerLfgAttendance.guild_id == guild_id)
        if cutoff_ts:
            q = q.filter(WebFluxerLfgAttendance.created_at >= cutoff_ts)
        if status_filter and status_filter in VALID_STATUSES:
            q = q.filter(WebFluxerLfgAttendance.status == status_filter)
        if user_q:
            q = q.filter(WebFluxerLfgAttendance.display_name.ilike(f'%{user_q}%'))
        rows = q.order_by(WebFluxerLfgAttendance.group_id, WebFluxerLfgAttendance.created_at).all()

        # Gather all group IDs
        group_ids = list({r.group_id for r in rows})
        if not group_ids:
            return JsonResponse({'groups': []})

        # Query groups
        groups_q = db.query(WebFluxerLfgGroup).filter(WebFluxerLfgGroup.id.in_(group_ids))
        if game_id:
            groups_q = groups_q.filter(WebFluxerLfgGroup.game_id == game_id)
        groups_map = {g.id: g for g in groups_q.all()}

        # Build response
        from collections import defaultdict
        by_group = defaultdict(list)
        for r in rows:
            if r.group_id in groups_map:
                by_group[r.group_id].append(r)

        result = []
        for gid, members in by_group.items():
            g = groups_map[gid]
            result.append({
                'id': g.id,
                'game_name': g.game_name,
                'title': g.title or g.game_name,
                'scheduled_time': g.scheduled_time,
                'status': g.status,
                'members': [
                    {
                        'display_name': m.display_name or m.fluxer_user_id or '',
                        'status': m.status,
                    }
                    for m in members
                ],
            })

        # Sort by scheduled_time desc (most recent first)
        result.sort(key=lambda x: x['scheduled_time'] or 0, reverse=True)

    return JsonResponse({'groups': result})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_attendance_export(request, guild_id):
    """GET /ql/api/dashboard/fluxer/<guild_id>/lfg/attendance/export/
    Returns CSV of attendance data with current filters.
    """
    import csv
    from django.http import HttpResponse

    guild_id = guild_id.strip()
    game_id = safe_int(request.GET.get('game_id', 0), default=0, min_val=0)
    user_q = (request.GET.get('user', '') or '').strip()[:100]
    days = safe_int(request.GET.get('days', 30), default=30, min_val=0, max_val=365)
    status_filter = (request.GET.get('status', '') or '').strip()
    VALID_STATUSES = {'pending', 'confirmed', 'showed', 'no_show', 'late', 'cancelled', 'pardoned'}

    now_ts = int(time.time())
    cutoff_ts = (now_ts - days * 86400) if days > 0 else 0

    with get_db_session() as db:
        q = db.query(WebFluxerLfgAttendance).filter(WebFluxerLfgAttendance.guild_id == guild_id)
        if cutoff_ts:
            q = q.filter(WebFluxerLfgAttendance.created_at >= cutoff_ts)
        if status_filter and status_filter in VALID_STATUSES:
            q = q.filter(WebFluxerLfgAttendance.status == status_filter)
        if user_q:
            q = q.filter(WebFluxerLfgAttendance.display_name.ilike(f'%{user_q}%'))
        rows = q.order_by(WebFluxerLfgAttendance.group_id, WebFluxerLfgAttendance.created_at).all()

        group_ids = list({r.group_id for r in rows})
        groups_map = {}
        if group_ids:
            groups_q = db.query(WebFluxerLfgGroup).filter(WebFluxerLfgGroup.id.in_(group_ids))
            if game_id:
                groups_q = groups_q.filter(WebFluxerLfgGroup.game_id == game_id)
            groups_map = {g.id: g for g in groups_q.all()}

        response = HttpResponse(content_type='text/csv')
        import datetime
        date_str = datetime.date.today().isoformat()
        response['Content-Disposition'] = f'attachment; filename=attendance_{guild_id}_{date_str}.csv'

        writer = csv.writer(response)
        writer.writerow(['Group ID', 'Game', 'Title', 'Scheduled Date', 'Member', 'Status'])
        for r in rows:
            g = groups_map.get(r.group_id)
            if not g:
                continue
            if g.scheduled_time:
                sched = datetime.datetime.utcfromtimestamp(g.scheduled_time).strftime('%Y-%m-%d %H:%M UTC')
            else:
                sched = ''
            writer.writerow([
                g.id,
                g.game_name,
                g.title or g.game_name,
                sched,
                r.display_name or r.fluxer_user_id or '',
                r.status,
            ])

    return response


# ---------------------------------------------------------------------------
# Live Alerts - Streamer Subscriptions API
# ---------------------------------------------------------------------------

def _streamer_sub_dict(s: WebFluxerStreamerSub) -> dict:
    return {
        'id': s.id,
        'guild_id': s.guild_id,
        'streamer_platform': s.streamer_platform,
        'streamer_handle': s.streamer_handle,
        'streamer_display_name': s.streamer_display_name or s.streamer_handle,
        'notify_channel_id': s.notify_channel_id,
        'custom_message': s.custom_message or '',
        'is_active': bool(s.is_active),
        'is_currently_live': bool(s.is_currently_live),
        'last_notified_at': s.last_notified_at,
        'created_at': s.created_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_streamer_subs(request, guild_id):
    """
    GET  - list streamer subscriptions for a Fluxer guild
    POST - add a new streamer subscription
    """
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            subs = db.query(WebFluxerStreamerSub).filter_by(guild_id=guild_id).order_by(
                WebFluxerStreamerSub.created_at.desc()
            ).all()
            return JsonResponse({'success': True, 'subs': [_streamer_sub_dict(s) for s in subs]})

    # POST - add subscription
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    platform = (data.get('streamer_platform', '') or '').strip().lower()
    if platform not in ('twitch', 'youtube'):
        return JsonResponse({'error': 'streamer_platform must be twitch or youtube'}, status=400)

    handle = sanitize_text(data.get('streamer_handle', '') or '').strip()
    if not handle:
        return JsonResponse({'error': 'streamer_handle is required'}, status=400)
    if len(handle) > 100:
        return JsonResponse({'error': 'streamer_handle too long'}, status=400)

    display_name = sanitize_text(data.get('streamer_display_name', '') or '').strip()[:100] or None
    notify_channel_id = (data.get('notify_channel_id', '') or '').strip()
    if not notify_channel_id:
        return JsonResponse({'error': 'notify_channel_id is required'}, status=400)

    custom_message = sanitize_text(data.get('custom_message', '') or '').strip()[:500] or None

    now = int(time.time())
    with get_db_session() as db:
        # Check duplicate
        existing = db.query(WebFluxerStreamerSub).filter_by(
            guild_id=guild_id, streamer_platform=platform, streamer_handle=handle
        ).first()
        if existing:
            return JsonResponse({'error': 'Already subscribed to this streamer'}, status=409)

        # Cap at 25 subs per guild
        count = db.query(WebFluxerStreamerSub).filter_by(guild_id=guild_id, is_active=1).count()
        if count >= 25:
            return JsonResponse({'error': 'Maximum 25 active streamer alerts per server'}, status=400)

        sub = WebFluxerStreamerSub(
            guild_id=guild_id,
            streamer_platform=platform,
            streamer_handle=handle,
            streamer_display_name=display_name,
            notify_channel_id=notify_channel_id,
            custom_message=custom_message,
            is_active=1,
            is_currently_live=0,
            created_at=now,
            updated_at=now,
        )
        db.add(sub)
        db.commit()
        db.refresh(sub)
        return JsonResponse({'success': True, 'sub': _streamer_sub_dict(sub)}, status=201)


@fluxer_guild_required
@require_http_methods(['PATCH', 'DELETE'])
def api_fluxer_guild_streamer_sub_detail(request, guild_id, sub_id):
    """
    PATCH  - update channel/message/active state for a streamer sub
    DELETE - remove a streamer subscription
    """
    guild_id = guild_id.strip()
    with get_db_session() as db:
        sub = db.query(WebFluxerStreamerSub).filter_by(id=sub_id, guild_id=guild_id).first()
        if not sub:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.delete(sub)
            db.commit()
            return JsonResponse({'success': True})

        # PATCH
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        now = int(time.time())
        if 'notify_channel_id' in data:
            ch = (data['notify_channel_id'] or '').strip()
            if ch:
                sub.notify_channel_id = ch
        if 'custom_message' in data:
            sub.custom_message = sanitize_text(data['custom_message'] or '').strip()[:500] or None
        if 'streamer_display_name' in data:
            sub.streamer_display_name = sanitize_text(data['streamer_display_name'] or '').strip()[:100] or None
        if 'is_active' in data:
            sub.is_active = 1 if data['is_active'] else 0
        sub.updated_at = now
        db.commit()
        return JsonResponse({'success': True, 'sub': _streamer_sub_dict(sub)})


# =============================================================================
# Fluxer Guild - Game Discovery (IGDB-based, mirrors Discord GameSearchConfig)
# =============================================================================

_AVAILABLE_GENRES = [
    "Adventure", "Arcade", "Fighting", "Hack and slash/Beat 'em up",
    "Indie", "Music", "Pinball", "Platform", "Point-and-click",
    "Puzzle", "Racing", "Real Time Strategy (RTS)", "Role-playing (RPG)",
    "Shooter", "Simulator", "Sport", "Strategy", "Tactical",
    "Turn-based strategy (TBS)", "Visual Novel",
]

_AVAILABLE_THEMES = [
    "Action", "Comedy", "Drama", "Educational", "Erotic", "Fantasy",
    "Historical", "Horror", "Kids", "Mystery", "Non-fiction", "Open world",
    "Romance", "Sandbox", "Science fiction", "Stealth", "Survival",
    "Thriller", "Warfare",
]

_AVAILABLE_MODES = [
    "Auditory",
    "Battle Royale",
    "Bird view / Isometric",
    "Co-operative",
    "First Person",
    "Massively Multiplayer Online (MMO)",
    "Multiplayer",
    "Single player",
    "Split screen",
    "Side View",
    "Text",
    "Third Person",
    "Virtual Reality",
]

_AVAILABLE_PLATFORMS = [
    "Linux", "Mac", "PC (Microsoft Windows)", "Nintendo Switch",
    "PlayStation 4", "PlayStation 5", "Xbox One", "Xbox Series X|S",
    "Android", "iOS",
]


def _game_search_config_dict(c: 'WebFluxerGameSearchConfig') -> dict:
    import json as _json
    def _parse(val):
        if not val:
            return []
        try:
            return _json.loads(val)
        except Exception:
            return []
    return {
        'id': c.id,
        'guild_id': c.guild_id,
        'name': c.name,
        'enabled': bool(c.enabled),
        'genres': _parse(c.genres),
        'themes': _parse(c.themes),
        'keywords': _parse(c.keywords),
        'game_modes': _parse(c.game_modes),
        'platforms': _parse(c.platforms),
        'min_hype': c.min_hype,
        'min_rating': c.min_rating,
        'days_ahead': c.days_ahead if c.days_ahead is not None else 30,
        'show_on_website': bool(c.show_on_website),
        'created_at': c.created_at,
        'updated_at': c.updated_at,
    }


def _found_game_dict(g: 'WebFluxerFoundGame') -> dict:
    import json as _json
    def _parse(val):
        if not val:
            return []
        try:
            return _json.loads(val)
        except Exception:
            return []
    return {
        'id': g.id,
        'guild_id': g.guild_id,
        'igdb_id': g.igdb_id,
        'igdb_slug': g.igdb_slug or '',
        'game_name': g.game_name,
        'release_date': g.release_date,
        'summary': g.summary or '',
        'genres': _parse(g.genres),
        'themes': _parse(g.themes),
        'keywords': _parse(g.keywords),
        'game_modes': _parse(g.game_modes),
        'platforms': _parse(g.platforms_json),
        'cover_url': g.cover_url or '',
        'igdb_url': g.igdb_url or '',
        'steam_url': g.steam_url or '',
        'hypes': g.hypes,
        'rating': g.rating,
        'search_config_id': g.search_config_id,
        'search_config_name': g.search_config_name or '',
        'found_at': g.found_at,
        'check_id': g.check_id or '',
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_game_search_configs(request, guild_id):
    """GET list / POST create game search configs for a Fluxer guild."""
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            configs = db.query(WebFluxerGameSearchConfig).filter_by(guild_id=guild_id).order_by(
                WebFluxerGameSearchConfig.name
            ).all()
            return JsonResponse({'success': True, 'searches': [_game_search_config_dict(c) for c in configs]})

    # POST - create
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = sanitize_text(data.get('name', '') or '').strip()[:100]
    if not name:
        return JsonResponse({'error': 'name is required'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        cfg = WebFluxerGameSearchConfig(
            guild_id=guild_id,
            name=name,
            enabled=1,
            genres=json.dumps(data['genres']) if data.get('genres') else None,
            themes=json.dumps(data['themes']) if data.get('themes') else None,
            keywords=json.dumps(data['keywords']) if data.get('keywords') else None,
            game_modes=json.dumps(data['game_modes']) if data.get('game_modes') else None,
            platforms=json.dumps(data['platforms']) if data.get('platforms') else None,
            min_hype=safe_int(data.get('min_hype'), default=None) if data.get('min_hype') is not None else None,
            min_rating=float(data['min_rating']) if data.get('min_rating') is not None and data['min_rating'] != '' else None,
            days_ahead=safe_int(data.get('days_ahead', 30), default=30, min_val=7, max_val=365),
            show_on_website=1 if data.get('show_on_website', True) else 0,
            created_at=now,
            updated_at=now,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        return JsonResponse({'success': True, 'search': _game_search_config_dict(cfg)}, status=201)


@fluxer_guild_required
@require_http_methods(['PUT', 'DELETE'])
def api_fluxer_guild_game_search_config_detail(request, guild_id, config_id):
    """PUT update / DELETE remove a game search config."""
    guild_id = guild_id.strip()

    with get_db_session() as db:
        cfg = db.query(WebFluxerGameSearchConfig).filter_by(id=config_id, guild_id=guild_id).first()
        if not cfg:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.delete(cfg)
            db.commit()
            return JsonResponse({'success': True})

        # PUT
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        now = int(time.time())
        if 'name' in data:
            cfg.name = sanitize_text(data['name'] or '').strip()[:100]
        if 'enabled' in data:
            cfg.enabled = 1 if data['enabled'] else 0
        if 'genres' in data:
            cfg.genres = json.dumps(data['genres']) if data['genres'] else None
        if 'themes' in data:
            cfg.themes = json.dumps(data['themes']) if data['themes'] else None
        if 'keywords' in data:
            cfg.keywords = json.dumps(data['keywords']) if data['keywords'] else None
        if 'game_modes' in data:
            cfg.game_modes = json.dumps(data['game_modes']) if data['game_modes'] else None
        if 'platforms' in data:
            cfg.platforms = json.dumps(data['platforms']) if data['platforms'] else None
        if 'min_hype' in data:
            cfg.min_hype = safe_int(data['min_hype'], default=None) if data['min_hype'] is not None and data['min_hype'] != '' else None
        if 'min_rating' in data:
            cfg.min_rating = float(data['min_rating']) if data['min_rating'] is not None and data['min_rating'] != '' else None
        if 'days_ahead' in data:
            cfg.days_ahead = safe_int(data['days_ahead'], default=30, min_val=7, max_val=365)
        if 'show_on_website' in data:
            cfg.show_on_website = 1 if data['show_on_website'] else 0
        cfg.updated_at = now
        db.commit()
        return JsonResponse({'success': True, 'search': _game_search_config_dict(cfg)})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_found_games(request, guild_id):
    """GET list of found games for a Fluxer guild, with optional filters."""
    guild_id = guild_id.strip()
    import json as _json
    from datetime import datetime

    search_id = request.GET.get('search_id')
    mode_filters = request.GET.getlist('mode')
    keyword_filters = request.GET.getlist('keyword')
    min_hype_param = request.GET.get('min_hype')
    min_hype = int(min_hype_param) if min_hype_param and min_hype_param.isdigit() else None
    game_name_filter = request.GET.get('game_name', '').strip()
    sort_by = request.GET.get('sort', 'release')

    with get_db_session() as db:
        query = db.query(WebFluxerFoundGame).filter_by(guild_id=guild_id)
        if search_id:
            query = query.filter(WebFluxerFoundGame.search_config_id == int(search_id))
        raw = query.order_by(WebFluxerFoundGame.found_at.desc()).limit(300).all()

        filtered = []
        now_ts = int(time.time())
        for g in raw:
            modes = _json.loads(g.game_modes) if g.game_modes else []
            kws = _json.loads(g.keywords) if g.keywords else []
            if game_name_filter and game_name_filter.lower() not in g.game_name.lower():
                continue
            if mode_filters and not any(m in modes for m in mode_filters):
                continue
            if keyword_filters:
                kws_lower = [k.lower() for k in kws]
                if not any(kw.lower() in kws_lower for kw in keyword_filters):
                    continue
            if min_hype is not None and (g.hypes is None or g.hypes < min_hype):
                continue
            filtered.append(g)

        # Sort
        def release_key(g):
            if g.release_date and g.release_date > 0:
                return (0, g.release_date)
            return (1, 0)

        if sort_by == 'release':
            filtered.sort(key=release_key)
        elif sort_by == 'hype':
            filtered.sort(key=lambda g: -(g.hypes or 0))
        elif sort_by == 'name':
            filtered.sort(key=lambda g: g.game_name.lower())
        # else found_at desc (already sorted)

        return JsonResponse({'success': True, 'games': [_found_game_dict(g) for g in filtered]})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_igdb_keywords(request, guild_id):
    """GET /ql/api/dashboard/fluxer/<guild_id>/igdb-keywords/?q=souls - keyword autocomplete."""
    query = request.GET.get('q', '').strip().lower()
    limit = min(safe_int(request.GET.get('limit', 20), default=20), 50)

    if not query or len(query) < 2:
        return JsonResponse({'keywords': []})

    with get_db_session() as db:
        results = db.execute(
            text("SELECT id, name FROM igdb_keywords WHERE LOWER(name) LIKE :q ORDER BY name LIMIT :lim"),
            {'q': f'%{query}%', 'lim': limit}
        ).fetchall()
        return JsonResponse({'keywords': [{'id': r[0], 'name': r[1]} for r in results]})


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_game_discovery_settings(request, guild_id):
    """GET/POST game discovery global settings (channel, enable, interval, ping role)."""
    guild_id = guild_id.strip()

    with get_db_session() as db:
        settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
        if not settings:
            return JsonResponse({'error': 'Guild not found'}, status=404)

        if request.method == 'GET':
            return JsonResponse({
                'game_discovery_enabled': bool(settings.game_discovery_enabled),
                'game_discovery_channel_id': settings.game_discovery_channel_id or '',
                'game_discovery_ping_role_id': settings.game_discovery_ping_role_id or '',
                'game_check_interval_hours': settings.game_check_interval_hours or 24,
            })

        # POST - save settings
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        settings.game_discovery_enabled = 1 if data.get('game_discovery_enabled') else 0
        channel_id = str(data.get('game_discovery_channel_id') or '').strip()
        settings.game_discovery_channel_id = channel_id if channel_id else None
        ping_role_id = str(data.get('game_discovery_ping_role_id') or '').strip()
        settings.game_discovery_ping_role_id = ping_role_id if ping_role_id else None
        interval = safe_int(data.get('game_check_interval_hours', 24), default=24, min_val=1, max_val=168)
        settings.game_check_interval_hours = interval
        settings.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'success': True})


@web_login_required
@fluxer_guild_required
@add_web_user_context
@require_http_methods(['POST'])
def api_fluxer_guild_force_check_games(request, guild_id):
    """Queue a check_games action so the bot runs discovery immediately for this guild."""
    guild_id = guild_id.strip()

    with get_db_session() as db:
        settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
        if not settings:
            return JsonResponse({'error': 'Guild not found'}, status=404)

        if not settings.game_discovery_enabled:
            return JsonResponse({'error': 'Game discovery is not enabled'}, status=400)

        if not settings.game_discovery_channel_id:
            return JsonResponse({'error': 'No announcement channel configured'}, status=400)

        # Cancel any pending check_games actions to avoid stacking
        db.query(WebFluxerGuildAction).filter(
            WebFluxerGuildAction.guild_id == guild_id,
            WebFluxerGuildAction.action_type == 'check_games',
            WebFluxerGuildAction.status == 'pending',
        ).update({'status': 'cancelled'}, synchronize_session=False)

        action = WebFluxerGuildAction(
            guild_id=guild_id,
            action_type='check_games',
            payload_json='{}',
            status='pending',
            created_at=int(time.time()),
        )
        db.add(action)
        db.commit()

    return JsonResponse({'success': True, 'message': 'Discovery queued - bot will run within 15 seconds'})


# ---------------------------------------------------------------------------
# Fluxer Dashboard: Bridge CRUD
# ---------------------------------------------------------------------------

def _bridge_dict(b: WebBridgeConfig) -> dict:
    return {
        'id': b.id,
        'name': b.name or '',
        'discord_guild_id': b.discord_guild_id or '',
        'discord_channel_id': b.discord_channel_id or '',
        'fluxer_channel_id': b.fluxer_channel_id or '',
        'matrix_space_id': b.matrix_space_id or '',
        'matrix_room_id': b.matrix_room_id or '',
        'relay_discord_to_fluxer': bool(b.relay_discord_to_fluxer),
        'relay_fluxer_to_discord': bool(b.relay_fluxer_to_discord),
        'relay_matrix_outbound': bool(getattr(b, 'relay_matrix_outbound', 1)),
        'relay_matrix_inbound': bool(getattr(b, 'relay_matrix_inbound', 1)),
        'max_msg_len': b.max_msg_len,
        'enabled': bool(b.enabled),
        'created_at': b.created_at,
    }


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_bridges(request, guild_id):
    """GET list / POST create bridge config for this Fluxer guild."""
    guild_id = guild_id.strip()

    if request.method == 'GET':
        with get_db_session() as db:
            bridges = db.query(WebBridgeConfig).filter_by(
                fluxer_guild_id=guild_id
            ).order_by(WebBridgeConfig.id).all()
            return JsonResponse({'success': True, 'bridges': [_bridge_dict(b) for b in bridges]})

    # POST - create
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = sanitize_text(data.get('name', '') or '').strip()[:100] or None
    discord_guild_id = str(data.get('discord_guild_id', '') or '').strip()[:20]
    discord_channel_id = str(data.get('discord_channel_id', '') or '').strip()[:20]
    fluxer_channel_id = str(data.get('fluxer_channel_id', '') or '').strip()[:20]
    matrix_space_id = str(data.get('matrix_space_id', '') or '').strip()[:512]
    matrix_room_id = str(data.get('matrix_room_id', '') or '').strip()[:512]

    if not discord_channel_id and not matrix_room_id:
        return JsonResponse({'error': 'discord_channel_id or matrix_room_id is required'}, status=400)

    # Validate that the fluxer_channel_id belongs to this guild (if provided)
    with get_db_session() as db:
        if fluxer_channel_id:
            known_channels = {
                r[0] for r in db.execute(text(
                    "SELECT channel_id FROM web_fluxer_guild_channels WHERE guild_id = :g"
                ), {'g': guild_id}).fetchall()
            }
            if fluxer_channel_id not in known_channels:
                return JsonResponse({'error': 'Unknown Fluxer channel'}, status=400)

        # If matrix_room_id is set, resolve the correct space_id from web_matrix_rooms
        if matrix_room_id and not matrix_space_id:
            from .models import WebMatrixRoom
            room_row = db.query(WebMatrixRoom).filter_by(room_id=matrix_room_id).first()
            if room_row:
                matrix_space_id = room_row.space_id

        now = int(time.time())
        bridge = WebBridgeConfig(
            name=name,
            discord_guild_id=discord_guild_id or None,
            discord_channel_id=discord_channel_id or None,
            fluxer_guild_id=guild_id,
            fluxer_channel_id=fluxer_channel_id or None,
            matrix_space_id=matrix_space_id or None,
            matrix_room_id=matrix_room_id or None,
            relay_discord_to_fluxer=1 if data.get('relay_discord_to_fluxer', True) else 0,
            relay_fluxer_to_discord=1 if data.get('relay_fluxer_to_discord', True) else 0,
            relay_matrix_outbound=1 if data.get('relay_matrix_outbound', True) else 0,
            relay_matrix_inbound=1 if data.get('relay_matrix_inbound', True) else 0,
            max_msg_len=safe_int(data.get('max_msg_len', 1000), default=1000, min_val=50, max_val=2000),
            enabled=1,
            created_at=now,
        )
        db.add(bridge)
        db.commit()
        db.refresh(bridge)
        return JsonResponse({'success': True, 'bridge': _bridge_dict(bridge)}, status=201)


@fluxer_guild_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def api_fluxer_guild_bridge_detail(request, guild_id, bridge_id):
    """GET / PATCH update / DELETE remove a single bridge config."""
    guild_id = guild_id.strip()
    bridge_id = safe_int(bridge_id, default=0)
    if not bridge_id:
        return JsonResponse({'error': 'Invalid bridge_id'}, status=400)

    with get_db_session() as db:
        bridge = db.query(WebBridgeConfig).filter_by(id=bridge_id, fluxer_guild_id=guild_id).first()
        if not bridge:
            return JsonResponse({'error': 'Bridge not found'}, status=404)

        if request.method == 'GET':
            return JsonResponse({'success': True, 'bridge': _bridge_dict(bridge)})

        if request.method == 'DELETE':
            from .models import WebBridgeRelayQueue
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
        if 'relay_discord_to_fluxer' in data:
            bridge.relay_discord_to_fluxer = 1 if data['relay_discord_to_fluxer'] else 0
        if 'relay_fluxer_to_discord' in data:
            bridge.relay_fluxer_to_discord = 1 if data['relay_fluxer_to_discord'] else 0
        if 'max_msg_len' in data:
            bridge.max_msg_len = safe_int(data['max_msg_len'], default=1000, min_val=50, max_val=2000)
        if 'discord_channel_id' in data:
            bridge.discord_channel_id = str(data['discord_channel_id'] or '')[:20] or None
        if 'discord_guild_id' in data:
            bridge.discord_guild_id = str(data['discord_guild_id'] or '')[:20] or None
        if 'fluxer_channel_id' in data:
            ch = str(data['fluxer_channel_id'] or '').strip()[:20]
            if ch:
                # Validate channel belongs to this guild
                known = {
                    r[0] for r in db.execute(text(
                        "SELECT channel_id FROM web_fluxer_guild_channels WHERE guild_id = :g"
                    ), {'g': guild_id}).fetchall()
                }
                if ch not in known:
                    return JsonResponse({'error': 'Unknown Fluxer channel'}, status=400)
            bridge.fluxer_channel_id = ch or None
        if 'matrix_space_id' in data:
            bridge.matrix_space_id = str(data['matrix_space_id'] or '')[:255] or None
        if 'matrix_room_id' in data:
            bridge.matrix_room_id = str(data['matrix_room_id'] or '')[:255] or None
        if 'relay_matrix_outbound' in data:
            bridge.relay_matrix_outbound = 1 if data['relay_matrix_outbound'] else 0
        if 'relay_matrix_inbound' in data:
            bridge.relay_matrix_inbound = 1 if data['relay_matrix_inbound'] else 0
        db.commit()
        db.refresh(bridge)
        return JsonResponse({'success': True, 'bridge': _bridge_dict(bridge)})


# =============================================================================
# CHANNEL STAT TRACKERS
# =============================================================================

def _tracker_dict(t):
    return {
        'id': t.id,
        'guild_id': t.guild_id,
        'channel_id': t.channel_id,
        'role_id': t.role_id,
        'label': t.label,
        'emoji': t.emoji or '',
        'game_name': t.game_name or '',
        'show_playing_count': bool(t.show_playing_count),
        'enabled': bool(t.enabled),
        'last_updated': t.last_updated,
        'last_topic': t.last_topic or '',
        'created_at': t.created_at,
    }


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_channels(request, guild_id):
    """GET cached Fluxer text channels for a guild."""
    from sqlalchemy import text as sa_text
    with get_db_session() as db:
        rows = db.execute(
            sa_text(
                "SELECT channel_id, channel_name FROM web_fluxer_guild_channels "
                "WHERE guild_id = :gid ORDER BY channel_name ASC"
            ),
            {"gid": str(guild_id)},
        ).fetchall()
    channels = [{'channel_id': r.channel_id, 'channel_name': r.channel_name} for r in rows]
    return JsonResponse({'channels': channels})


@fluxer_guild_required
@require_http_methods(['GET'])
def api_fluxer_guild_roles(request, guild_id):
    """GET cached Fluxer roles for a guild."""
    guild_id = guild_id.strip()
    with get_db_session() as db:
        roles = db.query(WebFluxerGuildRole).filter_by(guild_id=guild_id).order_by(
            WebFluxerGuildRole.position.desc()
        ).all()
        roles_data = [
            {'role_id': r.role_id, 'role_name': r.role_name}
            for r in roles
        ]
    return JsonResponse({'roles': roles_data})


@fluxer_guild_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_guild_trackers(request, guild_id):
    if request.method == 'GET':
        with get_db_session() as db:
            trackers = db.query(FluxerChannelStatTracker).filter_by(guild_id=guild_id).order_by(FluxerChannelStatTracker.id).all()
            return JsonResponse({'trackers': [_tracker_dict(t) for t in trackers]})

    # POST - create
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    channel_id = str(data.get('channel_id', '') or '').strip()[:64]
    role_id = str(data.get('role_id', '') or '').strip()[:64]
    label = sanitize_text(str(data.get('label', '') or '').strip())[:100]
    if not channel_id or not role_id or not label:
        return JsonResponse({'error': 'channel_id, role_id, and label are required'}, status=400)

    with get_db_session() as db:
        existing = db.query(FluxerChannelStatTracker).filter_by(guild_id=guild_id, channel_id=channel_id).first()
        if existing:
            return JsonResponse({'error': 'A tracker for that channel already exists'}, status=400)

        game_name = sanitize_text(str(data.get('game_name', '') or '').strip())[:100] or None
        tracker = FluxerChannelStatTracker(
            guild_id=guild_id,
            channel_id=channel_id,
            role_id=role_id,
            label=label,
            emoji=_sanitize_emoji(str(data.get('emoji', '') or '')) or None,
            game_name=game_name,
            show_playing_count=bool(game_name),
            enabled=True,
            created_at=int(time.time()),
            created_by=str(request.session.get('web_user_id', '')) or None,
        )
        db.add(tracker)
        db.commit()
        db.refresh(tracker)
        return JsonResponse({'success': True, 'tracker': _tracker_dict(tracker)}, status=201)


@fluxer_guild_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def api_fluxer_guild_tracker_detail(request, guild_id, tracker_id):
    with get_db_session() as db:
        tracker = db.query(FluxerChannelStatTracker).filter_by(id=tracker_id, guild_id=guild_id).first()
        if not tracker:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'GET':
            return JsonResponse({'tracker': _tracker_dict(tracker)})

        if request.method == 'DELETE':
            db.delete(tracker)
            db.commit()
            return JsonResponse({'success': True})

        # PATCH
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'label' in data:
            tracker.label = sanitize_text(str(data['label']).strip())[:100]
        if 'emoji' in data:
            tracker.emoji = _sanitize_emoji(str(data['emoji'])) or None
        if 'role_id' in data:
            tracker.role_id = str(data['role_id']).strip()[:64]
        if 'game_name' in data:
            gn = sanitize_text(str(data['game_name']).strip())[:100] or None
            tracker.game_name = gn
            tracker.show_playing_count = bool(gn)
        if 'enabled' in data:
            tracker.enabled = bool(data['enabled'])
        # Reset last_topic so bot re-evaluates on next cycle
        tracker.last_topic = None
        db.commit()
        db.refresh(tracker)
        return JsonResponse({'success': True, 'tracker': _tracker_dict(tracker)})
