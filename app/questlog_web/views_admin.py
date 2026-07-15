# QuestLog Web - admin views & APIs

import json
import re
import time
import logging
import os
from functools import wraps
import requests as _requests

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from sqlalchemy import or_, text as sa_text

from django.contrib.auth.models import User as DjangoUser

from .models import (
    WebUser, WebCommunity, WebCommunityMember,
    WebLFGGroup, WebLFGGameConfig, WebCreatorProfile,
    WebRSSFeed, WebRSSArticle,
    WebSteamSearchConfig, WebFoundGame,
    WebRaffle, WebRaffleEntry,
    AdminAuditLog,
    WebPost, WebComment, WebCommentLike,
    WebFollow, WebLike, WebNotification, WebUserBlock,
    WebLFGMember, WebSiteConfig,
    WebFlair, WebUserFlair, WebRankTitle,
    WebServerPoll, WebServerPollOption, WebServerPollVote,
    WebUserTOTP,
    WebGiveaway, WebGiveawayEntry,
    WebFluxerWebhookConfig,
    WebCommunityBotConfig,
    WebEarlyAccessCode,
    WebSubscriptionEvent,
    WebBridgeConfig, WebBridgeRelayQueue,
    WebFluxerGuildChannel,
    WebCustomEmoji,
    WebFluxerGuildSettings, WebFluxerLfgGroup, WebFluxerRssFeed,
    WebFluxerReactionRole, WebFluxerWelcomeConfig, WebFluxerXpBoostEvent,
    WebFluxerRaffle, WebFluxerStreamerSub,
    WebMatrixSpaceSettings, WebMatrixRoom, WebMatrixMember, WebMatrixXpEvent, WebMatrixRssFeed,
    WebBroadcastUser,
    WebTestimonial,
)
from django_ratelimit.decorators import ratelimit
from app.security_middleware import MAINTENANCE_FLAG
from app.db import get_db_session
from .fluxer_webhooks import notify_giveaway_start as _fluxer_giveaway_start, notify_giveaway_winner as _fluxer_giveaway_winner
from app.models import SiteActivityGame, SiteActivityGuildRole, SiteActivityFluxerRole
from .helpers import (
    web_login_required, web_admin_required, web_mod_required, add_web_user_context, log_admin_action,
    serialize_post, fetch_rss_feed, create_notification,
    serialize_user_brief, safe_int, validate_admin_image_url,
    process_uploaded_image, fluxer_or_web_admin_required, get_web_user,
)

logger = logging.getLogger(__name__)


@web_login_required
def admin_verify_pin(request):
    """Legacy endpoint - PIN auth replaced by Django superuser check."""
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect('questlog_web_admin')
    messages.error(request, "Access denied.")
    return redirect('questlog_web_home')


@web_mod_required
@add_web_user_context
def admin_panel(request):
    """Admin panel - admins and mods."""
    wu = request.web_user
    context = {
        'web_user': wu,
        'active_page': 'admin',
        'is_mod_only': wu.is_mod and not wu.is_admin,
    }
    return render(request, 'questlog_web/admin.html', context)


# --- Quest Control: single unified table, keyed by instance_name ---
# All per-game tables (vquest_configs, sdtd_configs, etc.) replaced by gamebot_configs.
# Single AMP account (AMP_USER/AMP_PASSWORD) - no per-instance credentials needed.

_INSTANCE_NAME_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')

def _validate_instance_name(name: str) -> bool:
    """Return True only if instance_name is a safe alphanumeric slug."""
    return bool(name and _INSTANCE_NAME_RE.match(name))


def _get_gamebot_config(engine, instance_name: str) -> dict | None:
    """Load a single row from gamebot_configs by instance_name."""
    from sqlalchemy import text as sa_text2
    try:
        with engine.connect() as conn:
            row = conn.execute(sa_text2(
                "SELECT * FROM gamebot_configs WHERE instance_name = :n LIMIT 1"
            ), {'n': instance_name}).fetchone()
            return dict(row._mapping) if row else None
    except Exception as e:
        logger.error('_get_gamebot_config(%s): %s', instance_name, e)
        return None


# Discord's guilds.cached_members is refreshed by WardenBot's guild_sync_cog every
# 30 minutes (cogs/guild_sync_cog.py), NOT continuously - a 5-minute window (the
# value fluxer_guild_required uses for a different, more-frequently-synced cache)
# denied legitimate managers most of the time here. 35 min gives a few minutes of
# slack past the sync interval; a role change takes up to ~30 min to take effect
# either direction (grant or revoke) - same lag as the underlying sync itself.
_MANAGER_ROLE_CACHE_MAX_AGE = 35 * 60


def _web_user_manages_instance(web_user, instance_name: str) -> bool:
    """True if web_user can access this specific Quest Control instance: full site
    admins always can; mods only if their linked Discord/Fluxer account CURRENTLY
    holds that instance's configured Manager role in its linked guild (live-checked
    against cached member data on every call, not a one-time grant, so a role
    removed in Discord/Fluxer immediately revokes access here too)."""
    if not web_user or web_user.is_banned:
        return False
    if web_user.is_admin:
        return True
    if not web_user.is_mod:
        return False
    if not _validate_instance_name(instance_name):
        return False

    from app.db import get_engine
    engine = get_engine()
    cfg = _get_gamebot_config(engine, instance_name)
    if not cfg:
        return False

    # Discord side - role membership lives in guilds.cached_members (a JSON array of
    # {id, username, roles}, synced by WardenBot's Gateway cache), NOT a per-member
    # roles column on guild_members - that column doesn't exist on this table.
    discord_role_id = cfg.get('discord_manager_role_id')
    discord_guild_id = cfg.get('discord_guild_id')
    user_discord_id = str(getattr(web_user, 'discord_id', None) or '')
    if discord_role_id and discord_guild_id and user_discord_id:
        try:
            with get_db_session() as db:
                row = db.execute(
                    sa_text("SELECT cached_members, updated_at FROM guilds WHERE guild_id=:g LIMIT 1"),
                    {'g': int(discord_guild_id)}
                ).fetchone()
            if row and row[0]:
                cache_age = int(time.time()) - int(row[1] or 0)
                if cache_age <= _MANAGER_ROLE_CACHE_MAX_AGE:
                    members = json.loads(row[0])
                    user_data = next((m for m in members if str(m.get('id')) == user_discord_id), None)
                    if user_data:
                        user_roles = {str(r) for r in user_data.get('roles', [])}
                        allowed = {r.strip() for r in str(discord_role_id).split(',') if r.strip()}
                        if allowed & user_roles:
                            return True
                else:
                    logger.warning(
                        'MANAGER ROLE CACHE STALE: guild=%s age=%ss - denying role-based access',
                        discord_guild_id, cache_age,
                    )
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning('_web_user_manages_instance discord check %s: %s', instance_name, e)

    # Fluxer side
    fluxer_role_id = cfg.get('fluxer_manager_role_id')
    fluxer_guild_id = cfg.get('fluxer_guild_id')
    user_fluxer_id = str(getattr(web_user, 'fluxer_id', None) or '')
    if fluxer_role_id and fluxer_guild_id and user_fluxer_id:
        try:
            with get_db_session() as db:
                s = db.query(WebFluxerGuildSettings).filter_by(guild_id=fluxer_guild_id).first()
            if s and s.cached_members:
                cache_age = int(time.time()) - int(s.updated_at or 0)
                if cache_age <= _MANAGER_ROLE_CACHE_MAX_AGE:
                    members = json.loads(s.cached_members)
                    user_data = next((m for m in members if str(m.get('id')) == user_fluxer_id), None)
                    if user_data:
                        user_roles = {str(r) for r in user_data.get('roles', [])}
                        allowed = {r.strip() for r in str(fluxer_role_id).split(',') if r.strip()}
                        if allowed & user_roles:
                            return True
                else:
                    logger.warning(
                        'MANAGER ROLE CACHE STALE: guild=%s age=%ss - denying role-based access',
                        fluxer_guild_id, cache_age,
                    )
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning('_web_user_manages_instance fluxer check %s: %s', instance_name, e)

    return False


def web_admin_or_instance_manager_required(view_func):
    """Allows full site admins through unconditionally. Mods (is_mod=True) are only
    allowed through if the request identifies a specific instance (?bot=... query
    param on GET, or a JSON body {"bot": "..."} on POST) AND they currently hold
    that instance's configured Manager role - checked fresh on every request via
    _web_user_manages_instance, never cached as a standing grant. Requires its own
    valid web_user session (checks auth itself, does not rely on another decorator).
    Replaces the old fluxer_or_web_admin_required on Quest Control's API endpoints,
    which let through ANY Fluxer-linked user regardless of admin/mod status."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        web_user = get_web_user(request)
        if not web_user or web_user.is_banned:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        if web_user.is_admin:
            request.web_user = web_user
            return view_func(request, *args, **kwargs)

        instance_name = request.GET.get('bot', '')
        if not instance_name and request.method == 'POST':
            try:
                instance_name = json.loads(request.body).get('bot', '')
            except (json.JSONDecodeError, TypeError, AttributeError):
                instance_name = ''

        if not instance_name or not _web_user_manages_instance(web_user, instance_name):
            logger.warning(
                'QUEST CONTROL ACCESS DENIED: user=%s instance=%r - not admin, not manager of this instance',
                getattr(web_user, 'username', '?'), instance_name,
            )
            return JsonResponse({'error': 'Access denied'}, status=403)

        request.web_user = web_user
        return view_func(request, *args, **kwargs)
    return wrapper

def _load_preset_from_file(preset_path):
    """Import DAY_EVENT_PRESETS from a bot preset .py file. Returns dict or None."""
    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location('_preset_module', preset_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, 'DAY_EVENT_PRESETS', None)
    except Exception as e:
        logger.warning('_load_preset_from_file(%s): %s', preset_path, e)
        return None

def _flatten_preset_day(day_data):
    """Flatten a nested preset day dict to a flat key->value dict for UI rendering."""
    flat = {}
    def _walk(d, prefix=''):
        for k, v in d.items():
            key = f'{prefix}{k}' if not prefix else f'{prefix}.{k}'
            if isinstance(v, dict):
                _walk(v, key)
            else:
                flat[key] = v
    _walk(day_data)
    return flat

def _unflatten_preset_day(flat):
    """Reverse of _flatten_preset_day - reconstruct nested dict."""
    result = {}
    for dotkey, v in flat.items():
        parts = dotkey.split('.')
        d = result
        for part in parts[:-1]:
            d = d.setdefault(part, {})
        d[parts[-1]] = v
    return result

def _build_schedule_schema():
    """Return a list of field groups for the V Rising schedule UI.

    Each group has: label, icon (FA class), fields list.
    Each field has: key (dot-notation), label, type, and type-specific attrs.
    Types: select, number, time_pair.
    """
    DAMAGE_MODES = [
        {'value': 'Never', 'label': 'Never'},
        {'value': 'Always', 'label': 'Always'},
        {'value': 'TimeRestricted', 'label': 'Time Restricted'},
    ]
    return [
        {
            'label': 'Game Mode',
            'icon': 'fa-gamepad',
            'fields': [
                {'key': 'GameDifficulty', 'label': 'Game Difficulty', 'type': 'number', 'step': 1, 'min': 1, 'max': 5},
                {'key': 'GameModeType', 'label': 'Game Mode', 'type': 'select',
                 'options': [{'value': 'PvE', 'label': 'PvE'}, {'value': 'PvP', 'label': 'PvP'}]},
                {'key': 'PlayerDamageMode', 'label': 'Player Damage Mode', 'type': 'select', 'options': DAMAGE_MODES},
                {'key': 'CastleDamageMode', 'label': 'Castle Damage Mode', 'type': 'select', 'options': DAMAGE_MODES},
            ],
        },
        {
            'label': 'Rates and Crafting',
            'icon': 'fa-hammer',
            'fields': [
                {'key': 'SunDamageModifier',              'label': 'Sun Damage',          'type': 'number', 'step': 0.01},
                {'key': 'DropTableModifier_General',      'label': 'Drop Rate (General)', 'type': 'number', 'step': 0.01},
                {'key': 'RepairCostModifier',             'label': 'Repair Cost',         'type': 'number', 'step': 0.01},
                {'key': 'RefinementRateModifier',         'label': 'Refinement Rate',     'type': 'number', 'step': 0.01},
                {'key': 'CraftRateModifier',              'label': 'Craft Rate',          'type': 'number', 'step': 0.01},
                {'key': 'BuildCostModifier',              'label': 'Build Cost',          'type': 'number', 'step': 0.01},
                {'key': 'MaterialYieldModifier_Global',   'label': 'Material Yield',      'type': 'number', 'step': 0.01},
                {'key': 'ServantConvertRateModifier',     'label': 'Servant Convert Rate','type': 'number', 'step': 0.01},
                {'key': 'BloodEssenceYieldModifier',      'label': 'Blood Essence Yield', 'type': 'number', 'step': 0.01},
                {'key': 'DropTableModifier_Missions',     'label': 'Drop Rate (Missions)','type': 'number', 'step': 0.01},
                {'key': 'DropTableModifier_StygianShards','label': 'Drop Rate (Shards)',  'type': 'number', 'step': 0.01},
            ],
        },
        {
            'label': 'Day and Night',
            'icon': 'fa-sun',
            'fields': [
                {'key': 'GameTimeModifiers.DayDurationInSeconds', 'label': 'Day Duration (seconds)', 'type': 'number', 'step': 1, 'min': 60},
                {'type': 'time_pair', 'label': 'Day Start',
                 'hour_key': 'GameTimeModifiers.DayStartHour', 'minute_key': 'GameTimeModifiers.DayStartMinute'},
                {'type': 'time_pair', 'label': 'Day End',
                 'hour_key': 'GameTimeModifiers.DayEndHour', 'minute_key': 'GameTimeModifiers.DayEndMinute'},
            ],
        },
        {
            'label': 'Blood Moon',
            'icon': 'fa-moon',
            'fields': [
                {'key': 'GameTimeModifiers.BloodMoonFrequency_Min', 'label': 'Blood Moon Frequency Min', 'type': 'number', 'step': 1, 'min': 1},
                {'key': 'GameTimeModifiers.BloodMoonFrequency_Max', 'label': 'Blood Moon Frequency Max', 'type': 'number', 'step': 1, 'min': 1},
                {'key': 'GameTimeModifiers.BloodMoonBuff',          'label': 'Blood Moon Buff',          'type': 'number', 'step': 0.01},
            ],
        },
        {
            'label': 'Enemy Difficulty',
            'icon': 'fa-skull',
            'fields': [
                {'key': 'UnitStatModifiers_Global.MaxHealthModifier', 'label': 'Global Max Health',  'type': 'number', 'step': 0.01},
                {'key': 'UnitStatModifiers_Global.PowerModifier',     'label': 'Global Power',       'type': 'number', 'step': 0.01},
                {'key': 'UnitStatModifiers_Global.LevelIncrease',     'label': 'Global Level Bonus', 'type': 'number', 'step': 1},
                {'key': 'UnitStatModifiers_VBlood.MaxHealthModifier', 'label': 'VBlood Max Health',  'type': 'number', 'step': 0.01},
                {'key': 'UnitStatModifiers_VBlood.PowerModifier',     'label': 'VBlood Power',       'type': 'number', 'step': 0.01},
                {'key': 'UnitStatModifiers_VBlood.LevelIncrease',     'label': 'VBlood Level Bonus', 'type': 'number', 'step': 1},
            ],
        },
        {
            'label': 'War Events',
            'icon': 'fa-flag',
            'fields': [
                {'key': 'WarEventGameSettings.Interval',      'label': 'Interval',        'type': 'number', 'step': 1, 'min': 1},
                {'key': 'WarEventGameSettings.MajorDuration', 'label': 'Major Duration',  'type': 'number', 'step': 1, 'min': 1},
                {'key': 'WarEventGameSettings.MinorDuration', 'label': 'Minor Duration',  'type': 'number', 'step': 1, 'min': 1},
                {'type': 'time_pair', 'label': 'Weekday Start',
                 'hour_key': 'WarEventGameSettings.WeekdayTime.StartHour',
                 'minute_key': 'WarEventGameSettings.WeekdayTime.StartMinute'},
                {'type': 'time_pair', 'label': 'Weekday End',
                 'hour_key': 'WarEventGameSettings.WeekdayTime.EndHour',
                 'minute_key': 'WarEventGameSettings.WeekdayTime.EndMinute'},
                {'type': 'time_pair', 'label': 'Weekend Start',
                 'hour_key': 'WarEventGameSettings.WeekendTime.StartHour',
                 'minute_key': 'WarEventGameSettings.WeekendTime.StartMinute'},
                {'type': 'time_pair', 'label': 'Weekend End',
                 'hour_key': 'WarEventGameSettings.WeekendTime.EndHour',
                 'minute_key': 'WarEventGameSettings.WeekendTime.EndMinute'},
                {'key': 'WarEventGameSettings.ScalingPlayers1.PointsModifier', 'label': '1-Player Points Mod', 'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.ScalingPlayers1.DropModifier',   'label': '1-Player Drop Mod',   'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.ScalingPlayers2.PointsModifier', 'label': '2-Player Points Mod', 'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.ScalingPlayers2.DropModifier',   'label': '2-Player Drop Mod',   'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.ScalingPlayers3.PointsModifier', 'label': '3-Player Points Mod', 'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.ScalingPlayers3.DropModifier',   'label': '3-Player Drop Mod',   'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.ScalingPlayers4.PointsModifier', 'label': '4-Player Points Mod', 'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.ScalingPlayers4.DropModifier',   'label': '4-Player Drop Mod',   'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.VampireStatModifiers.SpellPowerModifier',    'label': 'Vampire Spell Power',    'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.VampireStatModifiers.PhysicalPowerModifier', 'label': 'Vampire Physical Power', 'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.VampireStatModifiers.ResourcePowerModifier', 'label': 'Vampire Resource Power', 'type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.VampireStatModifiers.DamageReceivedModifier','label': 'Vampire Damage Received','type': 'number', 'step': 0.01},
                {'key': 'WarEventGameSettings.VampireStatModifiers.MaxHealthModifier',     'label': 'Vampire Max Health',     'type': 'number', 'step': 0.01},
            ],
        },
    ]



@web_admin_required
@require_http_methods(['GET'])
def api_quest_control_discord_lookup(request):
    """Fetch channels and roles for a guild_id from the Fluxer bot's synced DB tables.
    Admin-only (not instance-scoped): takes a bare guild_id, not a bot/instance_name,
    so there's no single instance to check Manager access against. No live caller in
    the current admin_quest_control.html - only referenced by the old, unrouted
    quest_control.html template."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()

    guild_id = request.GET.get('guild_id', '').strip()
    if not guild_id:
        return JsonResponse({'ok': False, 'error': 'guild_id required'})

    try:
        with engine.connect() as conn:
            ch_rows = conn.execute(sa_text2(
                "SELECT channel_id, channel_name FROM web_fluxer_guild_channels "
                "WHERE guild_id = :g ORDER BY channel_name"
            ), {'g': guild_id}).fetchall()
            role_rows = conn.execute(sa_text2(
                "SELECT role_id, role_name FROM web_fluxer_guild_roles "
                "WHERE guild_id = :g ORDER BY role_name"
            ), {'g': guild_id}).fetchall()
        channels = [{'value': str(r.channel_id), 'label': r.channel_name or str(r.channel_id)} for r in ch_rows]
        roles    = [{'value': str(r.role_id),    'label': r.role_name    or str(r.role_id)}    for r in role_rows]
        return JsonResponse({'ok': True, 'channels': channels, 'roles': roles})
    except Exception as e:
        logger.error('api_quest_control_discord_lookup: %s', e)
        return JsonResponse({'ok': False, 'error': 'Lookup failed'})


@web_admin_or_instance_manager_required
@require_http_methods(['GET', 'POST'])
def api_quest_control_schedule(request):
    """GET: Load schedule presets for an instance. POST: Save schedule overrides to DB."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()

    if request.method == 'GET':
        instance_name = request.GET.get('bot', '')  # 'bot' param = instance_name slug from template
        if not _validate_instance_name(instance_name):
            return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})
        cfg = _get_gamebot_config(engine, instance_name)
        if not cfg:
            return JsonResponse({'ok': False, 'error': 'Instance not found'})

        db_hour    = cfg.get('scheduler_hour', 3) or 3
        db_minute  = cfg.get('scheduler_minute', 27) or 27
        db_backup_hour   = cfg.get('backup_hour', 23) if cfg.get('backup_hour') is not None else 23
        db_backup_minute = cfg.get('backup_minute', 30) if cfg.get('backup_minute') is not None else 30
        db_backup_days = None
        if cfg.get('backup_days'):
            try:
                db_backup_days = json.loads(cfg['backup_days'])
            except Exception:
                pass
        db_overrides = None
        if cfg.get('schedule_overrides'):
            try:
                db_overrides = json.loads(cfg['schedule_overrides']) or None
            except Exception:
                pass

        db_schedule_enabled = cfg.get('schedule_enabled', 1)
        if db_schedule_enabled is None:
            db_schedule_enabled = 1

        common = {
            'scheduler_hour': db_hour, 'scheduler_minute': db_minute,
            'backup_hour': db_backup_hour, 'backup_minute': db_backup_minute,
            'backup_days': db_backup_days,
            'schedule_enabled': bool(db_schedule_enabled),
        }
        if db_overrides:
            return JsonResponse({'ok': True, 'presets': db_overrides, 'source': 'db',
                                 'schema': _build_schedule_schema(), **common})

        return JsonResponse({'ok': False, 'error': 'No schedule configured yet.', **common})

    else:  # POST
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

        instance_name    = body.get('bot', '')
        reset            = body.get('reset', False)
        scheduler_hour   = body.get('scheduler_hour')
        scheduler_minute = body.get('scheduler_minute')
        backup_hour      = body.get('backup_hour')
        backup_minute    = body.get('backup_minute')
        backup_days      = body.get('backup_days')  # list of day names or 'all'
        schedule_enabled = body.get('schedule_enabled')

        if not _validate_instance_name(instance_name):
            return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

        set_parts = []
        params = {'n': instance_name}

        if 'presets' in body or reset:
            presets = body.get('presets', {})
            save_val = None if reset else json.dumps(presets) if presets else None
            set_parts.append('schedule_overrides = :val')
            params['val'] = save_val

        if not set_parts and schedule_enabled is None and scheduler_hour is None and scheduler_minute is None and backup_hour is None and backup_minute is None and backup_days is None:
            return JsonResponse({'ok': False, 'error': 'Nothing to save'})

        if scheduler_hour is not None:
            try:
                h = int(scheduler_hour)
                if 0 <= h <= 23:
                    set_parts.append('scheduler_hour = :sh')
                    params['sh'] = h
            except (ValueError, TypeError):
                pass
        if scheduler_minute is not None:
            try:
                m = int(scheduler_minute)
                if 0 <= m <= 59:
                    set_parts.append('scheduler_minute = :sm')
                    params['sm'] = m
            except (ValueError, TypeError):
                pass
        if backup_hour is not None:
            try:
                h = int(backup_hour)
                if 0 <= h <= 23:
                    set_parts.append('backup_hour = :bh')
                    params['bh'] = h
            except (ValueError, TypeError):
                pass
        if backup_minute is not None:
            try:
                m = int(backup_minute)
                if 0 <= m <= 59:
                    set_parts.append('backup_minute = :bm')
                    params['bm'] = m
            except (ValueError, TypeError):
                pass
        if backup_days is not None:
            valid_days = {'Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'}
            if isinstance(backup_days, list):
                clean = [d for d in backup_days if d in valid_days]
                set_parts.append('backup_days = :bd')
                params['bd'] = json.dumps(clean) if clean else None
            elif backup_days == 'all':
                set_parts.append('backup_days = :bd')
                params['bd'] = None
        if schedule_enabled is not None:
            set_parts.append('schedule_enabled = :se')
            params['se'] = 1 if schedule_enabled else 0

        if not set_parts:
            return JsonResponse({'ok': False, 'error': 'Nothing valid to save'})

        try:
            with engine.connect() as conn:
                conn.execute(sa_text2(
                    f"UPDATE gamebot_configs SET {', '.join(set_parts)} WHERE instance_name = :n"
                ).bindparams(**params))
                conn.commit()
        except Exception as e:
            logger.error('api_quest_control_schedule save: %s', e)
            return JsonResponse({'ok': False, 'error': 'Save failed'})

        return JsonResponse({'ok': True})


@web_admin_or_instance_manager_required
@require_http_methods(['POST'])
def api_quest_control_backup_timing(request):
    """Save the warned-backup-cycle timing for a game server instance - warning lead
    times and wait durations. Everything here is admin-editable, never hardcoded in
    the bot itself; this endpoint is the only place these values are ever written."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = body.get('bot', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    updates = {}
    if 'backup_warning_minutes' in body:
        raw = body['backup_warning_minutes']
        if isinstance(raw, list):
            try:
                minutes = sorted({int(v) for v in raw if int(v) > 0}, reverse=True)
            except (TypeError, ValueError):
                return JsonResponse({'ok': False, 'error': 'backup_warning_minutes must be a list of positive integers'})
            updates['backup_warning_minutes'] = json.dumps(minutes) if minutes else None
        else:
            return JsonResponse({'ok': False, 'error': 'backup_warning_minutes must be a list'})

    for field, cap in (
        ('backup_wait_after_stop_sec', 3600),
        ('backup_wait_after_backup_sec', 3600),
        ('backup_wait_after_start_sec', 3600),
    ):
        if field not in body:
            continue
        try:
            val = int(body[field])
        except (TypeError, ValueError):
            return JsonResponse({'ok': False, 'error': f'{field} must be an integer'})
        updates[field] = max(0, min(val, cap))

    if not updates:
        return JsonResponse({'ok': False, 'error': 'No fields to update'})

    set_clause = ', '.join(f'{f} = :{f}' for f in updates)
    updates['n'] = instance_name
    try:
        with engine.connect() as conn:
            conn.execute(sa_text2(
                f"UPDATE gamebot_configs SET {set_clause} WHERE instance_name = :n"
            ).bindparams(**updates))
            conn.commit()
    except Exception as e:
        logger.error('api_quest_control_backup_timing save: %s', e)
        return JsonResponse({'ok': False, 'error': 'Save failed'})

    return JsonResponse({'ok': True})


@web_admin_or_instance_manager_required
@require_http_methods(['POST'])
def api_quest_control_backup_messages(request):
    """Save the 3 admin-authored embeds (warn/down/online) used by the warned backup
    cycle. Blank fields fall back to the bot's stock wording - nothing here forces the
    admin to fill in all 9 fields, only the ones they want to customize."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = body.get('bot', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    updates = {}
    for kind in ('warn', 'down', 'online'):
        title_field = f'backup_{kind}_embed_title'
        desc_field = f'backup_{kind}_embed_description'
        color_field = f'backup_{kind}_embed_color'
        if title_field in body:
            updates[title_field] = str(body[title_field] or '').strip()[:256] or None
        if desc_field in body:
            updates[desc_field] = str(body[desc_field] or '').strip()[:4096] or None
        if color_field in body:
            color = str(body[color_field] or '').strip()
            if color and not (color.startswith('#') and len(color) == 7):
                return JsonResponse({'ok': False, 'error': f'{color_field} must be #RRGGBB format'})
            updates[color_field] = color or None

    if not updates:
        return JsonResponse({'ok': False, 'error': 'No fields to update'})

    set_clause = ', '.join(f'{f} = :{f}' for f in updates)
    updates['n'] = instance_name
    try:
        with engine.connect() as conn:
            conn.execute(sa_text2(
                f"UPDATE gamebot_configs SET {set_clause} WHERE instance_name = :n"
            ).bindparams(**updates))
            conn.commit()
    except Exception as e:
        logger.error('api_quest_control_backup_messages save: %s', e)
        return JsonResponse({'ok': False, 'error': 'Save failed'})

    return JsonResponse({'ok': True})


@web_admin_or_instance_manager_required
@require_http_methods(['POST'])
def api_quest_control_backup_run_now(request):
    """Queue an immediate warned backup cycle for one instance, bypassing the daily
    scheduler entirely - for testing, and for catching a missed trigger window without
    waiting until tomorrow. Consumed by QuestLogFluxer's scheduler loop within ~60s."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = body.get('bot', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    try:
        with engine.connect() as conn:
            row = conn.execute(sa_text2(
                "SELECT backups_enabled FROM gamebot_configs WHERE instance_name = :n LIMIT 1"
            ), {'n': instance_name}).fetchone()
            if not row:
                return JsonResponse({'ok': False, 'error': 'Instance not found'})
            if not row.backups_enabled:
                return JsonResponse({'ok': False, 'error': 'Nightly Backups is not enabled for this instance'})
            conn.execute(sa_text2(
                "INSERT INTO gamebot_backup_run_requests (instance_name, requested_at) VALUES (:n, :t)"
            ), {'n': instance_name, 't': int(time.time())})
            conn.commit()
    except Exception as e:
        logger.error('api_quest_control_backup_run_now: %s', e)
        return JsonResponse({'ok': False, 'error': 'Request failed'})

    return JsonResponse({'ok': True})


@web_admin_or_instance_manager_required
@require_http_methods(['POST'])
def api_quest_control_channels(request):
    """Save channel/role IDs for a game server instance."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = body.get('bot', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    allowed_fields = ['notif_channel_id', 'stats_channel_id',
                      'discord_stats_channel_id', 'admin_role_id',
                      'discord_manager_role_id', 'fluxer_manager_role_id',
                      'live_log_discord_channel_id', 'live_log_fluxer_channel_id',
                      'server_update_discord_channel_id', 'server_update_fluxer_channel_id',
                      'backup_notice_discord_channel_id', 'backup_notice_fluxer_channel_id',
                      'rcon_broadcast_message']
    # Manager-role fields control WHO counts as an instance manager - only a site
    # admin may change them, or a manager could re-point the role at themselves
    # and entrench access after their real Discord/Fluxer role is revoked.
    if not request.web_user.is_admin:
        allowed_fields = [f for f in allowed_fields
                           if f not in ('discord_manager_role_id', 'fluxer_manager_role_id')]
    updates = {}
    for f in allowed_fields:
        if f not in body:
            continue
        if f == 'discord_stats_channel_id':
            # Multi-select field - stored as a JSON array of channel IDs, not a bare string.
            raw = body[f]
            if isinstance(raw, list):
                channel_ids = [str(c).strip() for c in raw if str(c).strip()]
            elif raw:
                channel_ids = [str(raw).strip()]
            else:
                channel_ids = []
            updates[f] = json.dumps(channel_ids) if channel_ids else None
        elif f == 'rcon_broadcast_message':
            # Free text (admin-authored in-game broadcast command/message), not a
            # Discord/Fluxer channel or role snowflake id - longer cap, no strip-to-id.
            updates[f] = str(body[f])[:2000].strip() or None
        else:
            updates[f] = str(body[f]).strip() or None

    if not updates:
        return JsonResponse({'ok': False, 'error': 'No fields to update'})

    set_clause = ', '.join(f'{f} = :{f}' for f in updates)
    updates['n'] = instance_name
    try:
        with engine.connect() as conn:
            conn.execute(sa_text2(
                f"UPDATE gamebot_configs SET {set_clause} WHERE instance_name = :n"
            ).bindparams(**updates))
            conn.commit()
    except Exception as e:
        logger.error('api_quest_control_channels save: %s', e)
        return JsonResponse({'ok': False, 'error': 'Save failed'})

    return JsonResponse({'ok': True})


@web_admin_or_instance_manager_required
@require_http_methods(['POST'])
def api_quest_control_toggles(request):
    """Save display/alert toggles for a game server instance."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = body.get('bot', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    toggle_fields = ['alert_join_leave', 'alert_live_logs', 'show_player_count',
                     'show_ip_port', 'show_password', 'show_top_5_players',
                     'backups_enabled', 'rcon_broadcast_enabled']
    updates = {f: 1 if body.get(f) else 0 for f in toggle_fields if f in body}
    if not updates:
        return JsonResponse({'ok': False, 'error': 'No fields to update'})

    try:
        with engine.connect() as conn:
            set_clause = ', '.join(f'{f} = :{f}' for f in updates)
            updates['n'] = instance_name
            conn.execute(sa_text2(
                f"UPDATE gamebot_configs SET {set_clause} WHERE instance_name = :n"
            ), updates)
            conn.commit()
    except Exception as e:
        logger.error('api_quest_control_toggles save: %s', e)
        return JsonResponse({'ok': False, 'error': 'Save failed'})

    return JsonResponse({'ok': True})


def _get_amp_instance(instance_name, user_env='AMP_USER', pass_env='AMP_PASSWORD'):
    """Synchronous helper: connects to AMP and returns the named instance object, or None."""
    import asyncio
    from ampapi.dataclass import APIParams
    from ampapi.bridge import Bridge
    from ampapi.controller import AMPControllerInstance as _AMPController

    async def _fetch():
        _params = APIParams(
            url=os.getenv('AMP_URL'),
            user=os.getenv(user_env),
            password=os.getenv(pass_env),
        )
        Bridge(api_params=_params)
        ctrl = _AMPController()
        await ctrl.get_instances()
        return next((i for i in ctrl.instances if i.instance_name == instance_name), None)

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_fetch())
    finally:
        loop.close()


@web_admin_or_instance_manager_required
@require_http_methods(['POST'])
def api_quest_control_server_settings(request):
    """Save server-level settings (public_ip override) for a game server instance."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    import re
    engine = get_engine()
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = body.get('bot', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    public_ip = (body.get('public_ip') or '').strip() or None
    if public_ip and not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', public_ip):
        return JsonResponse({'ok': False, 'error': 'Invalid IP address format'})

    try:
        with engine.connect() as conn:
            conn.execute(sa_text2(
                "UPDATE gamebot_configs SET public_ip = :ip WHERE instance_name = :n"
            ).bindparams(ip=public_ip, n=instance_name))
            conn.commit()
    except Exception as e:
        logger.error('api_quest_control_server_ip save: %s', e)
        return JsonResponse({'ok': False, 'error': 'Save failed'})

    return JsonResponse({'ok': True})


@web_admin_or_instance_manager_required
@ratelimit(key='ip', rate='10000/h', method='GET', block=True)
@require_http_methods(['GET'])
def api_quest_control_server_status(request):
    """GET: Fetch AMP server status for a game server instance."""
    instance_name = request.GET.get('bot', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    try:
        import asyncio
        from ampapi.dataclass import APIParams
        from ampapi.bridge import Bridge
        from ampapi.controller import AMPControllerInstance as _AMPCtrl

        async def _fetch_status():
            _params = APIParams(url=os.getenv('AMP_URL'), user=os.getenv('AMP_USER'), password=os.getenv('AMP_PASSWORD'))
            Bridge(api_params=_params)
            ctrl = _AMPCtrl()
            await ctrl.get_instances()
            instance = next((i for i in ctrl.instances if i.instance_name == instance_name), None)
            if not instance:
                return None, None
            # Only fetch get_status() metrics when the instance is actually running
            from ampapi.dataclass import AMPInstanceState
            if instance.app_state == AMPInstanceState.ready:
                status = await instance.get_status(format_data=False)
            else:
                status = None
            return instance, status

        loop = asyncio.new_event_loop()
        try:
            instance, status = loop.run_until_complete(_fetch_status())
        finally:
            loop.close()

        if instance is None:
            return JsonResponse({'ok': False, 'error': f'Instance "{instance_name}" not found in AMP'})

        # Use controller-level app_state (1:1 with AMP panel) - NOT get_status() state
        # AMPInstanceState enum: stopped=0, pre_start=5, configuring=7, starting=10,
        # ready=20, restarting=30, stopping=40, sleeping=50, failed=100, suspended=200
        _APP_STATE_LABEL = {
            'undefined': 'Unknown', 'stopped': 'Stopped', 'pre_start': 'Pre-Start',
            'configuring': 'Configuring', 'starting': 'Starting', 'ready': 'Running',
            'restarting': 'Restarting', 'stopping': 'Stopping',
            'preparing_for_sleep': 'Preparing for Sleep', 'sleeping': 'Sleeping',
            'waiting': 'Waiting', 'installing': 'Installing', 'updating': 'Updating',
            'awaiting_user_input': 'Awaiting Input', 'failed': 'Failed',
            'suspended': 'Suspended', 'maintenance': 'Maintenance', 'indeterminate': 'Unknown',
        }
        _STATE_COLOR = {
            'Running': 'green', 'Starting': 'amber', 'Configuring': 'amber',
            'Restarting': 'amber', 'Stopping': 'amber', 'Pre-Start': 'amber',
            'Stopped': 'neutral', 'Failed': 'red', 'Sleeping': 'neutral',
            'Waiting': 'neutral', 'Installing': 'amber', 'Updating': 'amber',
            'Suspended': 'neutral', 'Maintenance': 'amber', 'Unknown': 'neutral',
        }

        app_state_name = instance.app_state.name if hasattr(instance.app_state, 'name') else str(instance.app_state)
        state_label = _APP_STATE_LABEL.get(app_state_name, app_state_name.replace('_', ' ').title())

        s = status if isinstance(status, dict) else {}
        uptime = s.get('uptime') or s.get('Uptime') or ''

        # Parse metrics dict (snake_case keys from ampapi) - only present when running
        metrics = s.get('metrics') or s.get('Metrics') or {}

        def _metric(m, *keys):
            for k in keys:
                if k in m:
                    return m[k]
            return {}

        cpu    = _metric(metrics, 'cpu_usage',    'CPU Usage',    'CPUUsage')
        mem    = _metric(metrics, 'memory_usage', 'Memory Usage', 'MemoryUsage')
        users  = _metric(metrics, 'active_users', 'Active Users', 'ActiveUsers')

        def _val(d, *keys):
            for k in keys:
                v = d.get(k)
                if v is not None:
                    return v
            return 0

        return JsonResponse({
            'ok': True,
            'instance': instance_name,
            'state': state_label,
            'state_color': _STATE_COLOR.get(state_label, 'neutral'),
            'uptime': uptime,
            'cpu_pct':      _val(cpu,   'percent', 'Percent'),
            'cpu_raw':      _val(cpu,   'raw_value', 'RawValue'),
            'mem_used_mb':  _val(mem,   'raw_value', 'RawValue'),
            'mem_total_mb': _val(mem,   'max_value', 'MaxValue'),
            'mem_pct':      _val(mem,   'percent',   'Percent'),
            'players':      _val(users, 'raw_value', 'RawValue'),
            'players_max':  _val(users, 'max_value', 'MaxValue'),
        })

    except Exception as e:
        logger.error('api_quest_control_server_status: %s', e)
        return JsonResponse({'ok': False, 'error': 'Failed to fetch server status'})


@web_admin_or_instance_manager_required
@ratelimit(key='ip', rate='20/h', method='POST', block=True)
@require_http_methods(['POST'])
def api_quest_control_server_action(request):
    """POST: Start, stop, or restart a game server via AMP."""
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = body.get('bot', '')
    action        = body.get('action', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})
    if action not in ('start', 'stop', 'restart'):
        return JsonResponse({'ok': False, 'error': 'Invalid action'})

    try:
        import asyncio
        from ampapi.dataclass import APIParams
        from ampapi.bridge import Bridge
        from ampapi.controller import AMPControllerInstance as _AMPCtrl

        async def _do_action():
            _params = APIParams(url=os.getenv('AMP_URL'), user=os.getenv('AMP_USER'), password=os.getenv('AMP_PASSWORD'))
            Bridge(api_params=_params)
            ctrl = _AMPCtrl()
            await ctrl.get_instances()
            instance = next((i for i in ctrl.instances if i.instance_name == instance_name), None)
            if not instance:
                raise ValueError(f'Instance "{instance_name}" not found in AMP')
            if action == 'start':
                await instance.start_application()
            elif action == 'stop':
                await instance.stop_application()
            elif action == 'restart':
                await instance.restart_application()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_do_action())
        finally:
            loop.close()

        return JsonResponse({'ok': True, 'action': action, 'instance': instance_name})

    except Exception as e:
        logger.error('api_quest_control_server_action: %s', e)
        return JsonResponse({'ok': False, 'error': 'Server action failed'})


@web_admin_or_instance_manager_required
@ratelimit(key='ip', rate='20/h', method='POST', block=True)
@require_http_methods(['POST'])
def api_quest_control_god_action(request):
    """POST: Execute a God Mode action on a game server via AMP console commands."""
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = str(body.get('bot', '')).strip()
    action        = str(body.get('action', '')).strip()

    VALID_ACTIONS = ('broadcast', 'spawn', 'kick', 'ban', 'teleport', 'give_item',
                     'trigger_horde', 'blood_moon', 'set_time')
    if not _validate_instance_name(instance_name) or action not in VALID_ACTIONS:
        return JsonResponse({'ok': False, 'error': 'Invalid action or missing bot'})

    # Verify the instance exists and is configured
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()

    try:
        with engine.connect() as conn:
            row = conn.execute(sa_text2(
                "SELECT instance_name FROM gamebot_configs "
                "WHERE LOWER(instance_name) = LOWER(:name) AND configured = 1 LIMIT 1"
            ), {'name': instance_name}).fetchone()
            if not row:
                return JsonResponse({'ok': False, 'error': f'Instance not found or not configured: {instance_name}'})
            instance_name = row[0]  # Use canonical casing from DB
    except Exception as e:
        logger.error('api_quest_control_god_action: config lookup: %s', e)
        return JsonResponse({'ok': False, 'error': 'Config lookup failed'})

    # Build the AMP console command(s) for this action
    commands = []
    try:
        if action == 'broadcast':
            message = str(body.get('message', '')).strip()
            if not message:
                return JsonResponse({'ok': False, 'error': 'Message is required'})
            if not re.match(r'^[^\n\r;|&`]{1,500}$', message):
                return JsonResponse({'ok': False, 'error': 'Message contains invalid characters'})
            commands = [f'say {message}']

        elif action == 'spawn':
            import random as _random
            import json as _json
            from pathlib import Path as _Path
            entity   = str(body.get('entity', '')).strip()
            quantity = max(1, min(int(body.get('quantity', 1)), 50))
            _FACTIONS = {
                'feral_strike':    ['zombieSpiderFeral', 'zombieJanitorFeral', 'zombieMarlene',
                                    'zombieBikerFeral', 'zombieNurseFeral', 'zombieScreamerFeral'],
                'radiated_wave':   ['zombieYoRadiated', 'zombieNurseRadiated', 'zombieSkateboarderFeral',
                                    'zombieBurntRadiated', 'zombieSoldierRadiated', 'zombieMutatedRadiated'],
                'hazmat_response': ['zombieMaleHazmatFeral', 'zombieSoldierFeral', 'zombieLabFeral',
                                    'zombieBurntFeral', 'zombieDemolition'],
                'infernal_wave':   ['zombieBikerInfernal', 'zombieBurntInfernal', 'zombieLumberjackInfernal',
                                    'zombieFatCopInfernal', 'zombieMutatedInfernal', 'zombieWightInfernal'],
                'animal_horde':    ['animalZombieDog', 'animalZombieBear', 'animalZombieVulture',
                                    'animalDireWolf', 'animalMountainLion', 'animalZombieBoar'],
            }
            if entity in _FACTIONS:
                pool = _FACTIONS[entity]
                entity_list = [_random.choice(pool) for _ in range(quantity)]
            elif not entity or not re.match(r'^[A-Za-z0-9_]+$', entity):
                return JsonResponse({'ok': False, 'error': 'Invalid entity type'})
            else:
                entity_list = [entity] * quantity

            # Read player positions to spawn at actual player location
            # Flat list: [{name, x, y, z, timestamp}, ...] - last entry per player = most recent
            _SPAWN_RADIUS = 15
            _pos_file = _Path('/mnt/gamestoreage2/DiscordBots/7questbot/player_positions.json')
            spawn_pos = None
            try:
                if _pos_file.exists():
                    raw = _json.loads(_pos_file.read_text())
                    # Build map of name -> most recent entry (list is chronological)
                    _pos_map = {}
                    for entry in raw:
                        name = entry.get('name') or entry.get('id')
                        if name:
                            _pos_map[name] = entry
                    if _pos_map:
                        chosen = _random.choice(list(_pos_map.values()))
                        spawn_pos = (int(chosen['x']), int(chosen.get('y', 0)), int(chosen['z']))
            except Exception as _pe:
                logger.warning('god_action spawn: could not read positions: %s', _pe)

            if spawn_pos:
                px, py, pz = spawn_pos
                commands = []
                for ent in entity_list:
                    ox = _random.randint(-_SPAWN_RADIUS, _SPAWN_RADIUS)
                    oz = _random.randint(-_SPAWN_RADIUS, _SPAWN_RADIUS)
                    commands.append(f'spawnentityat {ent} {px + ox} {py} {pz + oz}')
            else:
                # No position data - fall back to se command which spawns near a random player
                commands = [f'se {ent}' for ent in entity_list]

        elif action == 'kick':
            player = str(body.get('player', '')).strip()
            if not player:
                return JsonResponse({'ok': False, 'error': 'Player name required'})
            if not re.match(r'^[A-Za-z0-9_ \-]{1,64}$', player):
                return JsonResponse({'ok': False, 'error': 'Invalid player name'})
            commands = [f'kick {player}']

        elif action == 'ban':
            player = str(body.get('player', '')).strip()
            if not player:
                return JsonResponse({'ok': False, 'error': 'Player name required'})
            if not re.match(r'^[A-Za-z0-9_ \-]{1,64}$', player):
                return JsonResponse({'ok': False, 'error': 'Invalid player name'})
            commands = [f'ban add {player} 36500 "Banned via God Mode"']

        elif action == 'teleport':
            player = str(body.get('player', '')).strip()
            if not player:
                return JsonResponse({'ok': False, 'error': 'Player name required'})
            if not re.match(r'^[A-Za-z0-9_ \-]{1,64}$', player):
                return JsonResponse({'ok': False, 'error': 'Invalid player name'})
            commands = [f'teleportplayer {player} 0 0 0']

        elif action == 'give_item':
            player = str(body.get('player', '')).strip()
            item   = str(body.get('item', '')).strip()
            if not player or not item:
                return JsonResponse({'ok': False, 'error': 'Player and item required'})
            if not re.match(r'^[A-Za-z0-9_ \-]{1,64}$', player):
                return JsonResponse({'ok': False, 'error': 'Invalid player name'})
            if not re.match(r'^[A-Za-z0-9_ ]+$', item):
                return JsonResponse({'ok': False, 'error': 'Invalid item name'})
            commands = [f'give {player} {item} 1']

        elif action == 'trigger_horde':
            commands = ['spawnscouting']

        elif action == 'blood_moon':
            commands = ['bloodmoon']

        elif action == 'set_time':
            hour = max(0, min(int(body.get('hour', 6)), 23))
            commands = [f'settime {hour} 0']

    except (ValueError, TypeError) as e:
        return JsonResponse({'ok': False, 'error': f'Bad parameter: {e}'})

    # Execute commands via AMP console
    try:
        import asyncio
        from ampapi.dataclass import APIParams
        from ampapi.bridge import Bridge
        from ampapi.controller import AMPControllerInstance as _AMPCtrl

        async def _run_commands():
            _params = APIParams(
                url=os.getenv('AMP_URL'),
                user=os.getenv('AMP_USER'),
                password=os.getenv('AMP_PASSWORD'),
            )
            Bridge(api_params=_params)
            ctrl = _AMPCtrl()
            await ctrl.get_instances()
            inst = next((i for i in ctrl.instances if i.instance_name == instance_name), None)
            if not inst:
                raise ValueError(f'Instance "{instance_name}" not found in AMP')
            # Flush any buffered updates before sending so get_updates only returns new lines
            try:
                await inst.get_updates()
            except Exception:
                pass
            for cmd in commands:
                await inst.send_console_message(cmd)
            # Brief pause then collect console output as confirmation
            await asyncio.sleep(1.5)
            console_lines = []
            try:
                updates = await inst.get_updates()
                entries = getattr(updates, 'console_entries', None) or []
                for entry in entries[-10:]:
                    contents = getattr(entry, 'contents', None) or ''
                    if contents:
                        console_lines.append(contents)
            except Exception:
                pass
            return console_lines

        loop = asyncio.new_event_loop()
        try:
            console_lines = loop.run_until_complete(_run_commands())
        finally:
            loop.close()

        log_admin_action(request, 'god_action', instance_name, 0,
                         f'action={action} instance={instance_name} params={json.dumps({k: body.get(k) for k in ("player","message","entity","item","hour") if body.get(k)})}')
        result_msg = f'{action} sent ({len(commands)} command(s))'
        return JsonResponse({
            'ok': True,
            'result': result_msg,
            'console': console_lines,
        })

    except Exception as e:
        logger.error('api_quest_control_god_action: %s', e)
        return JsonResponse({'ok': False, 'error': f'Command failed: {e}'})


@web_admin_or_instance_manager_required
@require_http_methods(['POST'])
def api_quest_control_send_embed(request):
    """POST: Send a custom embed to a game bot channel via fluxer_pending_broadcasts."""
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = body.get('bot', '')
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    # Each platform gets its own optional channel_id now that an instance can be linked
    # to a Discord guild, a Fluxer guild, both, or neither - the client sends whichever
    # of these it collected from the user, and we queue a broadcast per channel provided.
    discord_channel_id = str(body.get('discord_channel_id', '')).strip()
    fluxer_channel_id   = str(body.get('fluxer_channel_id', '')).strip()
    # Back-compat: a bare 'channel_id' with no platform-specific field is treated as
    # whichever single platform this instance is actually linked to (existing callers).
    legacy_channel_id = str(body.get('channel_id', '')).strip()

    if not discord_channel_id and not fluxer_channel_id and not legacy_channel_id:
        return JsonResponse({'ok': False, 'error': 'No destination channel provided'})
    for cid in (discord_channel_id, fluxer_channel_id, legacy_channel_id):
        if cid and not cid.isdigit():
            return JsonResponse({'ok': False, 'error': 'Invalid channel_id'})

    title = str(body.get('title', '')).strip()[:256]
    description = str(body.get('description', '')).strip()[:4096]
    color_hex = str(body.get('color', '#5865F2')).strip()
    fields = body.get('fields', [])  # [{name, value, inline}]
    footer = str(body.get('footer', '')).strip()[:256]

    if not title and not description:
        return JsonResponse({'ok': False, 'error': 'Embed must have a title or description'})

    # Parse color
    try:
        color_int = int(color_hex.lstrip('#'), 16)
    except (ValueError, AttributeError):
        color_int = 0x5865F2

    # Build embed payload matching fluxer_pending_broadcasts format
    embed_data = {}
    if title:
        embed_data['title'] = title
    if description:
        embed_data['description'] = description
    embed_data['color'] = color_int

    # Sanitize and add fields (max 10)
    clean_fields = []
    for f in (fields or [])[:10]:
        fname = str(f.get('name', '')).strip()[:256]
        fval  = str(f.get('value', '')).strip()[:1024]
        if fname and fval:
            clean_fields.append({'name': fname, 'value': fval, 'inline': bool(f.get('inline', True))})
    if clean_fields:
        embed_data['fields'] = clean_fields

    if footer:
        embed_data['footer'] = footer

    # Look up this instance's independent Discord/Fluxer guild links
    try:
        with engine.connect() as conn:
            row = conn.execute(sa_text2(
                "SELECT discord_guild_id, fluxer_guild_id FROM gamebot_configs WHERE instance_name = :n LIMIT 1"
            ), {'n': instance_name}).fetchone()
            if not row:
                return JsonResponse({'ok': False, 'error': 'Instance not found'})
            discord_guild_id = row.discord_guild_id
            fluxer_guild_id  = row.fluxer_guild_id
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'DB error: {e}'})

    # Legacy bare channel_id (no platform specified): send it to whichever single
    # platform this instance is actually linked to, preferring Fluxer to match the
    # old default when both existed only in theory (never in practice, pre-split).
    if legacy_channel_id and not discord_channel_id and not fluxer_channel_id:
        if fluxer_guild_id:
            fluxer_channel_id = legacy_channel_id
        elif discord_guild_id:
            discord_channel_id = legacy_channel_id
        else:
            return JsonResponse({'ok': False, 'error': 'Instance is not linked to any guild'})

    payload_json = json.dumps({'embed': embed_data})
    now_ts = int(time.time())
    sent_to = []

    try:
        with engine.connect() as conn:
            if fluxer_channel_id:
                if not fluxer_guild_id:
                    return JsonResponse({'ok': False, 'error': 'Instance is not linked to a Fluxer guild'})
                conn.execute(sa_text2(
                    "INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at) VALUES (:g, :c, :p, :t)"
                ), {'g': int(fluxer_guild_id), 'c': int(fluxer_channel_id), 'p': payload_json, 't': now_ts})
                sent_to.append('fluxer')
            if discord_channel_id:
                if not discord_guild_id:
                    return JsonResponse({'ok': False, 'error': 'Instance is not linked to a Discord guild'})
                conn.execute(sa_text2(
                    "INSERT INTO discord_pending_broadcasts (guild_id, channel_id, payload, created_at) VALUES (:g, :c, :p, :t)"
                ), {'g': int(discord_guild_id), 'c': int(discord_channel_id), 'p': payload_json, 't': now_ts})
                sent_to.append('discord')
            conn.commit()
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'Queue insert failed: {e}'})

    log_admin_action(request, 'quest_control_send_embed', instance_name, 0,
                     details={'sent_to': sent_to, 'title': title, 'instance': instance_name})
    return JsonResponse({'ok': True, 'sent_to': sent_to})


@web_admin_required
@require_http_methods(['POST'])
def api_quest_control_claim(request):
    """
    POST: Activate a discovered-but-unconfigured AMP instance into QuestLog.
    Every game server instance is owned by QuestLog itself (site admin), not by any
    Discord or Fluxer guild - Discord/Fluxer linkage is a separate, independent,
    per-instance notification setting (see api_quest_control_link_guild below), not
    an ownership/authorization mechanism. No guild is involved in activation at all.
    """
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = str(body.get('instance_name', '')).strip()
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    try:
        with engine.connect() as conn:
            result = conn.execute(sa_text2(
                "UPDATE gamebot_configs SET configured = 1 WHERE instance_name = :n AND configured = 0"
            ), {'n': instance_name})
            conn.commit()
            if result.rowcount == 0:
                return JsonResponse({'ok': False, 'error': 'Instance already active or not found'})
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'Activation failed: {e}'})

    return JsonResponse({'ok': True})


@web_admin_required
@require_http_methods(['POST'])
def api_quest_control_link_guild(request):
    """
    POST: Set or clear which Discord and/or Fluxer guild a QuestLog-owned instance
    should notify. Independent per platform - an instance can be linked to a Discord
    guild, a Fluxer guild, both, or neither, at any time, regardless of the other.
    Site-admin only (this whole page is admin-gated) - no separate guild-ownership
    proof is required, since only trusted admins can reach this endpoint at all.
    """
    from app.db import get_engine
    from sqlalchemy import text as sa_text2
    engine = get_engine()

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Invalid JSON'})

    instance_name = str(body.get('instance_name', '')).strip()
    if not _validate_instance_name(instance_name):
        return JsonResponse({'ok': False, 'error': 'Missing or invalid instance_name'})

    updates = {}
    if 'discord_guild_id' in body:
        updates['discord_guild_id'] = str(body['discord_guild_id']).strip() or None
    if 'fluxer_guild_id' in body:
        updates['fluxer_guild_id'] = str(body['fluxer_guild_id']).strip() or None
    if not updates:
        return JsonResponse({'ok': False, 'error': 'No guild fields to update'})

    set_clause = ', '.join(f'{f} = :{f}' for f in updates)
    updates['n'] = instance_name
    try:
        with engine.connect() as conn:
            conn.execute(sa_text2(
                f"UPDATE gamebot_configs SET {set_clause} WHERE instance_name = :n"
            ), updates)
            conn.commit()
    except Exception as e:
        return JsonResponse({'ok': False, 'error': f'Link update failed: {e}'})

    return JsonResponse({'ok': True})


@web_mod_required
def api_admin_stats(request):
    """API: Get admin dashboard stats."""
    with get_db_session() as db:
        stats = {
            'users': db.query(WebUser).count(),
            'communities': db.query(WebCommunity).count(),
            'pending_communities': db.query(WebCommunity).filter_by(network_status='pending').count(),
            'banned_communities': db.query(WebCommunity).filter_by(is_banned=True).count(),
            'lfg_groups': db.query(WebLFGGroup).filter(WebLFGGroup.status.in_(['open', 'full'])).count(),
            'lfg_game_configs': db.query(WebLFGGameConfig).count(),
            'creators': db.query(WebCreatorProfile).count(),
            'verified_creators': db.query(WebCreatorProfile).filter_by(is_verified=True).count(),
            'steam_searches': db.query(WebSteamSearchConfig).count(),
            'found_games': db.query(WebFoundGame).filter_by(is_hidden=False).count(),
            'raffles': db.query(WebRaffle).filter_by(is_active=True).count(),
            'rss_feeds': db.query(WebRSSFeed).count(),
            'active_rss_feeds': db.query(WebRSSFeed).filter_by(is_active=True).count(),
        }
    return JsonResponse(stats)


@web_admin_required
def api_admin_bot_stats(request):
    """API: Bot usage stats for admin panel."""
    now = int(time.time())
    thirty_days_ago = now - (30 * 24 * 3600)

    with get_db_session() as db:
        # ── Fluxer ──────────────────────────────────────────────
        f_total   = db.query(WebFluxerGuildSettings).count()
        f_active  = db.query(WebFluxerGuildSettings).filter_by(bot_present=1).count()
        f_members = db.execute(sa_text(
            "SELECT COALESCE(SUM(member_count),0) FROM web_fluxer_guild_settings"
        )).scalar() or 0
        f_xp_30d  = db.execute(sa_text(
            "SELECT COUNT(*) FROM fluxer_member_xp WHERE last_active >= :ts"
        ), {'ts': thirty_days_ago}).scalar() or 0
        f_lfg_total  = db.query(WebFluxerLfgGroup).count()
        f_lfg_active = db.query(WebFluxerLfgGroup).filter_by(status='open').count()
        f_xp_enabled = db.query(WebFluxerGuildSettings).filter_by(xp_enabled=1).count()
        f_lfg_cfg    = db.execute(sa_text(
            "SELECT COUNT(DISTINCT guild_id) FROM web_fluxer_lfg_config"
        )).scalar() or 0
        f_live_alerts = db.query(WebFluxerStreamerSub).count()
        f_rss        = db.query(WebFluxerRssFeed).count()
        f_rr         = db.query(WebFluxerReactionRole).count()
        f_welcome    = db.query(WebFluxerWelcomeConfig).filter_by(enabled=1).count()
        f_xp_boosts  = db.query(WebFluxerXpBoostEvent).filter_by(is_active=1).count()
        f_raffles    = db.query(WebFluxerRaffle).count()
        f_top_guilds = db.execute(sa_text(
            "SELECT guild_id, guild_name, member_count, bot_present "
            "FROM web_fluxer_guild_settings ORDER BY member_count DESC LIMIT 10"
        )).fetchall()

        # ── Discord (WardenBot tables) ───────────────────────────
        disc_total   = db.execute(sa_text("SELECT COUNT(*) FROM guilds WHERE bot_present=1 AND left_at IS NULL")).scalar() or 0
        disc_active  = disc_total
        disc_members = db.execute(sa_text("SELECT COALESCE(SUM(member_count),0) FROM guilds")).scalar() or 0
        disc_xp_30d  = db.execute(sa_text(
            "SELECT COUNT(*) FROM guild_members WHERE last_active >= :ts"
        ), {'ts': thirty_days_ago}).scalar() or 0
        disc_lfg_total  = db.execute(sa_text("SELECT COUNT(*) FROM lfg_groups")).scalar() or 0
        disc_lfg_active = db.execute(sa_text("SELECT COUNT(*) FROM lfg_groups WHERE is_active=1")).scalar() or 0
        disc_rss        = db.execute(sa_text("SELECT COUNT(*) FROM rss_feeds")).scalar() or 0
        disc_lfg_cfg    = db.execute(sa_text("SELECT COUNT(DISTINCT guild_id) FROM lfg_configs")).scalar() or 0
        disc_raffles    = db.execute(sa_text("SELECT COUNT(*) FROM raffles")).scalar() or 0

        # ── Matrix ───────────────────────────────────────────────
        m_total   = db.query(WebMatrixSpaceSettings).count()
        m_active  = db.query(WebMatrixSpaceSettings).filter_by(bot_present=1).count()
        m_members = db.execute(sa_text(
            "SELECT COALESCE(SUM(member_count),0) FROM web_matrix_space_settings"
        )).scalar() or 0
        m_xp_30d  = db.query(WebMatrixXpEvent).filter(
            WebMatrixXpEvent.last_message_at >= thirty_days_ago
        ).count()
        m_rooms   = db.query(WebMatrixRoom).count()
        m_rss     = db.query(WebMatrixRssFeed).count()
        m_xp_enabled = db.query(WebMatrixSpaceSettings).filter_by(xp_enabled=1).count()
        m_welcome = db.query(WebMatrixSpaceSettings).filter(
            WebMatrixSpaceSettings.welcome_room_id.isnot(None)
        ).count()

        # ── Bridge ───────────────────────────────────────────────
        bridge_active = db.query(WebBridgeConfig).filter_by(enabled=1).count()
        bridge_msgs   = db.execute(sa_text(
            "SELECT COUNT(*) FROM web_bridge_relay_queue WHERE created_at >= :ts"
        ), {'ts': thirty_days_ago}).scalar() or 0

    return JsonResponse({
        'fluxer': {
            'total_guilds':    f_total,
            'active_guilds':   f_active,
            'total_members':   int(f_members),
            'xp_events_30d':   int(f_xp_30d),
            'lfg_groups_total':  f_lfg_total,
            'lfg_groups_active': f_lfg_active,
            'xp_enabled':      f_xp_enabled,
            'lfg_configured':  int(f_lfg_cfg),
            'live_alerts':     f_live_alerts,
            'rss_feeds':       f_rss,
            'reaction_roles':  f_rr,
            'welcome_enabled': f_welcome,
            'xp_boosts_active': f_xp_boosts,
            'raffles_total':   f_raffles,
            'top_guilds': [
                {'guild_id': r[0], 'guild_name': r[1], 'member_count': r[2] or 0, 'bot_present': bool(r[3])}
                for r in f_top_guilds
            ],
        },
        'discord': {
            'total_guilds':    int(disc_total),
            'active_guilds':   int(disc_active),
            'total_members':   int(disc_members),
            'xp_events_30d':   int(disc_xp_30d),
            'lfg_groups_total':  int(disc_lfg_total),
            'lfg_groups_active': int(disc_lfg_active),
            'rss_feeds':       int(disc_rss),
            'lfg_configured':  int(disc_lfg_cfg),
            'raffles_total':   int(disc_raffles),
        },
        'matrix': {
            'total_spaces':  m_total,
            'active_spaces': m_active,
            'total_members': int(m_members),
            'xp_events_30d': m_xp_30d,
            'rss_feeds':     m_rss,
            'xp_enabled':    m_xp_enabled,
            'welcome_set':   m_welcome,
        },
        'bridge': {
            'active_bridges': bridge_active,
            'messages_30d':   int(bridge_msgs),
        },
    })


# --- LFG Game Config Admin ---

@web_admin_required
@require_http_methods(["GET", "POST"])
def api_admin_lfg_games(request):
    """API: CRUD for LFG game configs."""
    if request.method == 'GET':
        with get_db_session() as db:
            configs = db.query(WebLFGGameConfig).order_by(WebLFGGameConfig.sort_order, WebLFGGameConfig.game_name).all()
            data = [{
                'id': c.id,
                'game_name': c.game_name,
                'game_short': c.game_short,
                'steam_app_id': c.steam_app_id,
                'cover_url': c.cover_url,
                'default_group_size': c.default_group_size,
                'max_group_size': c.max_group_size,
                'role_mode': c.role_mode,
                'custom_roles': json.loads(c.custom_roles) if c.custom_roles else [],
                'enabled': c.enabled,
                'sort_order': c.sort_order,
            } for c in configs]
        return JsonResponse({'games': data})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        with get_db_session() as db:
            config = WebLFGGameConfig(
                game_name=body['game_name'],
                game_short=body.get('game_short'),
                steam_app_id=body.get('steam_app_id'),
                cover_url=body.get('cover_url'),
                default_group_size=body.get('default_group_size', 4),
                max_group_size=body.get('max_group_size', 25),
                role_mode=body.get('role_mode', 'none'),
                custom_roles=json.dumps(body.get('custom_roles', [])),
                enabled=body.get('enabled', True),
                sort_order=body.get('sort_order', 0),
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )
            db.add(config)
            db.commit()
            db.refresh(config)
            log_admin_action(request, 'create_lfg_game', 'lfg_game', config.id, {'game_name': body['game_name']})
            return JsonResponse({'success': True, 'id': config.id})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@web_admin_required
@require_http_methods(["PUT", "DELETE"])
def api_admin_lfg_game_detail(request, game_id):
    """API: Update/delete a single LFG game config."""
    with get_db_session() as db:
        config = db.query(WebLFGGameConfig).filter_by(id=game_id).first()
        if not config:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            game_name = config.game_name
            db.delete(config)
            db.commit()
            log_admin_action(request, 'delete_lfg_game', 'lfg_game', game_id, {'game_name': game_name})
            return JsonResponse({'success': True})

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        _lfg_game_field_types = {
            'game_name': str, 'game_short': str, 'steam_app_id': str, 'cover_url': str,
            'default_group_size': int, 'max_group_size': int,
            'role_mode': str, 'enabled': bool, 'sort_order': int,
        }
        for field, coerce in _lfg_game_field_types.items():
            if field in body:
                try:
                    setattr(config, field, coerce(body[field]) if body[field] is not None else None)
                except (ValueError, TypeError):
                    pass
        if 'custom_roles' in body:
            config.custom_roles = json.dumps(body['custom_roles'])
        config.updated_at = int(time.time())
        db.commit()
        _safe_log = {k: body[k] for k in ('game_name', 'game_short', 'role_mode', 'enabled', 'sort_order') if k in body}
        log_admin_action(request, 'update_lfg_game', 'lfg_game', game_id, _safe_log)
        return JsonResponse({'success': True})


# --- Community Admin ---

@web_mod_required
def api_admin_communities(request):
    """API: List all communities for admin."""
    with get_db_session() as db:
        communities = db.query(WebCommunity).order_by(WebCommunity.name).all()
        data = [{
            'id': c.id,
            'name': c.name,
            'platform': c.platform.value,
            'owner_id': c.owner_id,
            'short_description': c.short_description,
            'description': c.description,
            'tags': json.loads(c.tags or '[]'),
            'icon_url': c.icon_url,
            'banner_url': c.banner_url,
            'invite_url': c.invite_url,
            'website_url': c.website_url,
            'twitch_url': c.twitch_url,
            'youtube_url': c.youtube_url,
            'twitter_url': c.twitter_url,
            'member_count': c.member_count,
            'allow_discovery': c.allow_discovery,
            'allow_joins': c.allow_joins,
            'network_status': c.network_status,
            'site_xp_to_guild': bool(c.site_xp_to_guild),
            'is_active': c.is_active,
            'is_banned': c.is_banned,
            'ban_reason': c.ban_reason,
            'created_at': c.created_at,
        } for c in communities]
    return JsonResponse({'communities': data})


@web_mod_required
@require_http_methods(["POST"])
def api_admin_community_action(request, community_id):
    """API: Admin actions on a community (approve, ban, unban, purge)."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = body.get('action')
    if action not in ('approve', 'deny', 'ban', 'unban', 'purge', 'toggle_discovery', 'remove_from_network', 'toggle_unified_xp'):
        return JsonResponse({'error': 'Invalid action'}, status=400)

    # Purge is irreversible (deletes the community and all its members) - only
    # a full admin may do this, unlike the other softer/reversible actions
    # this endpoint allows any mod to perform.
    if action == 'purge' and not request.web_user.is_admin:
        return JsonResponse({'error': 'Access denied - admin only action'}, status=403)

    with get_db_session() as db:
        community = db.query(WebCommunity).filter_by(id=community_id).first()
        if not community:
            return JsonResponse({'error': 'Not found'}, status=404)

        if action == 'approve':
            community.network_status = 'approved'
            community.network_member = True
            community.network_approved_at = int(time.time())
        elif action == 'deny':
            community.network_status = 'denied'
            community.network_member = False
        elif action == 'ban':
            community.is_banned = True
            community.ban_reason = body.get('reason', '')
            community.network_status = 'banned'
            community.network_member = False
        elif action == 'unban':
            community.is_banned = False
            community.ban_reason = None
            community.network_status = 'none'
        elif action == 'toggle_discovery':
            community.allow_discovery = not community.allow_discovery
        elif action == 'toggle_unified_xp':
            was_enabled = bool(community.site_xp_to_guild)
            community.site_xp_to_guild = not was_enabled
            # When enabling: backfill all members who have linked QL accounts
            # Take MAX(platform_xp, web_xp) - never inflate by summing
            if not was_enabled:
                platform = community.platform.value if hasattr(community.platform, 'value') else str(community.platform)
                guild_id_str = str(community.platform_id)
                now_ts = int(time.time())
                try:
                    if platform == 'discord':
                        rows = db.execute(sa_text(
                            "SELECT wu.id, wu.web_xp, wu.hero_points, gm.xp, gm.hero_tokens, "
                            "       gm.message_count, gm.voice_minutes, gm.reaction_count, gm.media_count "
                            "FROM web_users wu "
                            "JOIN guild_members gm ON gm.user_id = CAST(wu.discord_id AS UNSIGNED) "
                            "WHERE gm.guild_id = :gid AND gm.xp > 0 AND wu.discord_id IS NOT NULL "
                            "AND wu.primary_community_id = :cid"
                        ), {'gid': int(guild_id_str), 'cid': community_id}).fetchall()
                        for r in rows:
                            wu_id, web_xp, web_hp, gm_xp, gm_hp = int(r[0]), float(r[1] or 0), int(r[2] or 0), float(r[3] or 0), int(r[4] or 0)
                            new_xp = max(web_xp, gm_xp)
                            new_hp = web_hp + gm_hp if gm_xp > web_xp else web_hp
                            new_lvl = db.execute(sa_text(
                                "SELECT COALESCE(MAX(level),0) FROM level_requirements WHERE xp_required <= :xp"
                            ), {'xp': new_xp}).scalar() or 0
                            db.execute(sa_text(
                                "UPDATE web_users SET web_xp=:xp, web_level=:lvl, hero_points=:hp WHERE id=:uid"
                            ), {'xp': new_xp, 'lvl': new_lvl, 'hp': new_hp, 'uid': wu_id})
                            # Upsert into unified leaderboard
                            db.execute(sa_text("""
                                INSERT INTO web_unified_leaderboard
                                    (user_id, guild_id, platform, messages, voice_mins, reactions,
                                     media_count, xp_total, last_active, updated_at)
                                VALUES (:uid, :gid, 'discord', :msg, :voice, :react, :media, :xp, :la, :now)
                                ON DUPLICATE KEY UPDATE
                                    messages=:msg, voice_mins=:voice, reactions=:react,
                                    media_count=:media, xp_total=:xp, updated_at=:now
                            """), {
                                'uid': wu_id, 'gid': guild_id_str,
                                'msg': int(r[5] or 0), 'voice': int(r[6] or 0),
                                'react': int(r[7] or 0), 'media': int(r[8] or 0),
                                'xp': new_xp, 'la': now_ts, 'now': now_ts,
                            })
                    elif platform == 'fluxer':
                        rows = db.execute(sa_text(
                            "SELECT wu.id, wu.web_xp, wu.hero_points, fx.xp, fx.message_count "
                            "FROM web_users wu "
                            "JOIN fluxer_member_xp fx ON fx.user_id = wu.fluxer_id "
                            "WHERE fx.guild_id = :gid AND fx.xp > 0 AND wu.fluxer_id IS NOT NULL "
                            "AND wu.primary_community_id = :cid"
                        ), {'gid': guild_id_str, 'cid': community_id}).fetchall()
                        for r in rows:
                            wu_id, web_xp, web_hp, fx_xp = int(r[0]), float(r[1] or 0), int(r[2] or 0), float(r[3] or 0)
                            new_xp = max(web_xp, fx_xp)
                            new_hp = web_hp  # Fluxer HP not tracked separately
                            new_lvl = db.execute(sa_text(
                                "SELECT COALESCE(MAX(level),0) FROM level_requirements WHERE xp_required <= :xp"
                            ), {'xp': new_xp}).scalar() or 0
                            db.execute(sa_text(
                                "UPDATE web_users SET web_xp=:xp, web_level=:lvl, hero_points=:hp WHERE id=:uid"
                            ), {'xp': new_xp, 'lvl': new_lvl, 'hp': new_hp, 'uid': wu_id})
                            db.execute(sa_text("""
                                INSERT INTO web_unified_leaderboard
                                    (user_id, guild_id, platform, messages, voice_mins, reactions,
                                     media_count, xp_total, last_active, updated_at)
                                VALUES (:uid, :gid, 'fluxer', :msg, 0, 0, 0, :xp, :la, :now)
                                ON DUPLICATE KEY UPDATE
                                    messages=:msg, xp_total=:xp, updated_at=:now
                            """), {
                                'uid': wu_id, 'gid': guild_id_str,
                                'msg': int(r[4] or 0), 'xp': new_xp,
                                'la': now_ts, 'now': now_ts,
                            })
                    db.commit()
                except Exception as e:
                    logger.warning(f"toggle_unified_xp backfill failed for community {community_id}: {e}")
        elif action == 'remove_from_network':
            community.network_status = 'none'
            community.network_member = False
        elif action == 'purge':
            community_name = community.name
            db.query(WebCommunityMember).filter_by(community_id=community_id).delete()
            db.delete(community)
            db.commit()
            log_admin_action(request, 'purge_community', 'community', community_id, {'name': community_name})
            return JsonResponse({'success': True, 'purged': True})

        community.updated_at = int(time.time())
        db.commit()
    log_admin_action(request, f'{action}_community', 'community', community_id, {'action': action})
    return JsonResponse({'success': True})


# --- Creator Admin ---

@web_mod_required
def api_admin_creators(request):
    """API: List all creators for admin."""
    with get_db_session() as db:
        creators = db.query(WebCreatorProfile).order_by(WebCreatorProfile.display_name).all()
        data = [{
            'id': c.id,
            'user_id': c.user_id,
            'display_name': c.display_name,
            'avatar_url': c.avatar_url,
            'is_verified': c.is_verified,
            'allow_discovery': c.allow_discovery,
            'follower_count': c.follower_count,
            'times_featured': c.times_featured,
            'featured_at': c.featured_at,
            'is_current_cotw': c.is_current_cotw,
            'is_current_cotm': c.is_current_cotm,
            'cotw_last_featured': c.cotw_last_featured,
            'cotm_last_featured': c.cotm_last_featured,
            'twitch_url': c.twitch_url,
            'youtube_url': c.youtube_url,
            'created_at': c.created_at,
        } for c in creators]
    return JsonResponse({'creators': data})


@web_mod_required
@require_http_methods(["POST"])
def api_admin_creator_action(request, creator_id):
    """API: Admin actions on a creator (verify, unverify, feature, delete)."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = body.get('action')
    valid_actions = ('verify', 'unverify', 'feature', 'delete', 'set_cotw', 'unset_cotw', 'set_cotm', 'unset_cotm', 'hide', 'unhide', 'reset_featured')
    if action not in valid_actions:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        creator = db.query(WebCreatorProfile).filter_by(id=creator_id).first()
        if not creator:
            return JsonResponse({'error': 'Not found'}, status=404)

        if action == 'verify':
            creator.is_verified = True
            web_user = db.query(WebUser).filter_by(id=creator.user_id).first()
            if web_user and not web_user.is_contributor:
                web_user.is_contributor = True
        elif action == 'unverify':
            creator.is_verified = False
        elif action == 'feature':
            creator.featured_at = now
            creator.times_featured = (creator.times_featured or 0) + 1
        elif action == 'delete':
            creator_name = creator.display_name
            db.delete(creator)
            db.commit()
            log_admin_action(request, 'delete_creator', 'creator', creator_id, {'name': creator_name})
            return JsonResponse({'success': True, 'deleted': True})
        elif action == 'set_cotw':
            # Clear all existing COTW holders
            db.query(WebCreatorProfile).filter(WebCreatorProfile.is_current_cotw == True).update({'is_current_cotw': False})
            # Anti-double-dip: strip COTM from this person if they hold it
            if creator.is_current_cotm:
                creator.is_current_cotm = False
            creator.is_current_cotw = True
            creator.cotw_last_featured = now
            creator.times_featured = (creator.times_featured or 0) + 1
            creator.featured_at = now
        elif action == 'unset_cotw':
            creator.is_current_cotw = False
        elif action == 'set_cotm':
            # Clear all existing COTM holders
            db.query(WebCreatorProfile).filter(WebCreatorProfile.is_current_cotm == True).update({'is_current_cotm': False})
            # Anti-double-dip: strip COTW from this person if they hold it
            if creator.is_current_cotw:
                creator.is_current_cotw = False
            creator.is_current_cotm = True
            creator.cotm_last_featured = now
            creator.times_featured = (creator.times_featured or 0) + 1
            creator.featured_at = now
        elif action == 'unset_cotm':
            creator.is_current_cotm = False
        elif action == 'hide':
            creator.allow_discovery = False
        elif action == 'unhide':
            creator.allow_discovery = True
        elif action == 'reset_featured':
            creator.times_featured = 0

        creator.updated_at = now
        db.commit()
    log_admin_action(request, f'{action}_creator', 'creator', creator_id, {'action': action})
    return JsonResponse({'success': True})


def _do_rotate_cotw(db):
    """Pick a random COTW. Requires allow_discovery, 14-day cooldown, and not already COTM."""
    import secrets
    now = int(time.time())
    cooldown_ts = now - (14 * 24 * 60 * 60)

    db.query(WebCreatorProfile).filter(WebCreatorProfile.is_current_cotw == True).update({'is_current_cotw': False})

    eligible = db.query(WebCreatorProfile).filter(
        WebCreatorProfile.allow_discovery == True,
        WebCreatorProfile.is_current_cotm == False,
        (WebCreatorProfile.cotw_last_featured == None) |
        (WebCreatorProfile.cotw_last_featured < cooldown_ts),
    ).all()

    if not eligible:
        return None

    winner = secrets.choice(eligible)
    winner.is_current_cotw = True
    winner.cotw_last_featured = now
    winner.times_featured = (winner.times_featured or 0) + 1
    winner.featured_at = now
    winner.updated_at = now
    return winner


def _do_rotate_cotm(db):
    """Pick a random COTM. Requires allow_discovery, 60-day cooldown, and not already COTW."""
    import secrets
    now = int(time.time())
    cooldown_ts = now - (60 * 24 * 60 * 60)

    db.query(WebCreatorProfile).filter(WebCreatorProfile.is_current_cotm == True).update({'is_current_cotm': False})

    eligible = db.query(WebCreatorProfile).filter(
        WebCreatorProfile.allow_discovery == True,
        WebCreatorProfile.is_current_cotw == False,
        (WebCreatorProfile.cotm_last_featured == None) |
        (WebCreatorProfile.cotm_last_featured < cooldown_ts),
    ).all()

    if not eligible:
        return None

    winner = secrets.choice(eligible)
    winner.is_current_cotm = True
    winner.cotm_last_featured = now
    winner.times_featured = (winner.times_featured or 0) + 1
    winner.featured_at = now
    winner.updated_at = now
    return winner


@web_mod_required
@require_http_methods(["POST"])
def api_admin_rotate_cotw(request):
    """API: Admin triggers COTW rotation."""
    with get_db_session() as db:
        winner = _do_rotate_cotw(db)
        db.commit()
        if winner:
            log_admin_action(request, 'rotate_cotw', 'creator', winner.id, {'new_cotw': winner.display_name})
            return JsonResponse({'success': True, 'new_cotw': winner.display_name, 'id': winner.id})
        else:
            return JsonResponse({'success': True, 'new_cotw': None, 'message': 'No eligible creators for COTW.'})


@web_mod_required
@require_http_methods(["POST"])
def api_admin_rotate_cotm(request):
    """API: Admin triggers COTM rotation."""
    with get_db_session() as db:
        winner = _do_rotate_cotm(db)
        db.commit()
        if winner:
            log_admin_action(request, 'rotate_cotm', 'creator', winner.id, {'new_cotm': winner.display_name})
            return JsonResponse({'success': True, 'new_cotm': winner.display_name, 'id': winner.id})
        else:
            return JsonResponse({'success': True, 'new_cotm': None, 'message': 'No eligible creators for COTM.'})


# --- Steam Search Config Admin ---

@web_admin_required
def api_admin_steam_searches(request):
    """API: CRUD for Steam search configs."""
    if request.method == 'GET':
        with get_db_session() as db:
            configs = db.query(WebSteamSearchConfig).order_by(WebSteamSearchConfig.created_at.desc()).all()
            data = [{
                'id': c.id,
                'name': c.name,
                'enabled': c.enabled,
                'steam_tags': json.loads(c.steam_tags) if c.steam_tags else [],
                'exclude_tags': json.loads(c.exclude_tags) if c.exclude_tags else [],
                'coming_soon_only': c.coming_soon_only,
                'min_reviews': c.min_reviews or 0,
                'max_results': c.max_results or 50,
                'show_on_site': c.show_on_site,
                'fetch_interval': c.fetch_interval or 1440,
                'include_consoles': bool(c.include_consoles),
                'last_run_at': c.last_run_at,
                'last_result_count': c.last_result_count or 0,
                'last_error': c.last_error,
                'created_at': c.created_at,
            } for c in configs]
        return JsonResponse({'searches': data})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        with get_db_session() as db:
            config = WebSteamSearchConfig(
                name=body['name'],
                enabled=body.get('enabled', True),
                steam_tags=json.dumps(body.get('steam_tags', [])),
                exclude_tags=json.dumps(body.get('exclude_tags', [])),
                coming_soon_only=body.get('coming_soon_only', True),
                min_reviews=body.get('min_reviews', 0),
                max_results=body.get('max_results', 50),
                show_on_site=body.get('show_on_site', True),
                fetch_interval=body.get('fetch_interval', 1440),
                include_consoles=body.get('include_consoles', False),
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )
            db.add(config)
            db.commit()
            db.refresh(config)
            log_admin_action(request, 'create_steam_search', 'steam_search', config.id, {'name': body['name']})
            return JsonResponse({'success': True, 'id': config.id})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@web_admin_required
@require_http_methods(["PUT", "DELETE"])
def api_admin_steam_search_detail(request, search_id):
    """API: Update/delete a single Steam search config."""
    with get_db_session() as db:
        config = db.query(WebSteamSearchConfig).filter_by(id=search_id).first()
        if not config:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            search_name = config.name
            db.delete(config)
            db.commit()
            log_admin_action(request, 'delete_steam_search', 'steam_search', search_id, {'name': search_name})
            return JsonResponse({'success': True})

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        _steam_search_field_types = {
            'name': str,
            'enabled': bool, 'coming_soon_only': bool, 'show_on_site': bool, 'include_consoles': bool,
            'min_reviews': int, 'max_results': int, 'fetch_interval': int,
        }
        for field, coerce in _steam_search_field_types.items():
            if field in body:
                try:
                    setattr(config, field, coerce(body[field]) if body[field] is not None else None)
                except (ValueError, TypeError):
                    pass
        if 'steam_tags' in body:
            config.steam_tags = json.dumps(body['steam_tags'])
        if 'exclude_tags' in body:
            config.exclude_tags = json.dumps(body['exclude_tags'])
        config.updated_at = int(time.time())
        db.commit()
        _safe_log = {k: body[k] for k in ('name', 'enabled', 'min_reviews', 'max_results', 'fetch_interval') if k in body}
        log_admin_action(request, 'update_steam_search', 'steam_search', search_id, _safe_log)
        return JsonResponse({'success': True})


@web_admin_required
@require_http_methods(["POST"])
def api_admin_run_steam_search(request, search_id):
    """API: Immediately run a Steam search config.
    ?clear=1  - delete all WebFoundGame rows for this config first, then re-run.
    """
    from .steam_search import run_steam_search_config
    clear = request.GET.get('clear') == '1'
    with get_db_session() as db:
        config = db.query(WebSteamSearchConfig).filter_by(id=search_id).first()
        if not config:
            return JsonResponse({'error': 'Not found'}, status=404)
        if clear:
            db.query(WebFoundGame).filter_by(search_config_id=search_id).delete()
            db.commit()
        new_count, updated_count, error = run_steam_search_config(config, db)
    if error:
        return JsonResponse({'success': False, 'error': error})
    return JsonResponse({'success': True, 'new_count': new_count, 'updated_count': updated_count})


# --- Found Games Admin ---

@web_admin_required
def api_admin_found_games(request):
    """API: List/manage found games. Paginated - previously hard-capped at 100 rows
    with no way to see the rest; now returns a page at a time plus the total count.
    Supports optional genre and NSFW filters via query params."""
    page = safe_int(request.GET.get('page'), 1, 1, 100000)
    page_size = 50
    genre_filter = (request.GET.get('genre') or '').strip()
    hide_nsfw = request.GET.get('hide_nsfw') == '1'

    with get_db_session() as db:
        query = db.query(WebFoundGame)

        if genre_filter:
            # genres is a JSON array stored as text - a plain LIKE on the quoted
            # value avoids needing a JSON-aware column type for this simple filter.
            query = query.filter(WebFoundGame.genres.like(f'%"{genre_filter}"%'))

        if hide_nsfw:
            # Real Steam flag first; keyword fallback covers rows fetched before
            # is_nsfw existed (Steam's own content_descriptors weren't captured yet).
            nsfw_keywords = ['hentai', 'nudity', 'sexual content', 'adult only', 'erotic', 'nsfw']
            keyword_clause = or_(*[
                or_(
                    WebFoundGame.name.ilike(f'%{kw}%'),
                    WebFoundGame.summary.ilike(f'%{kw}%'),
                    WebFoundGame.genres.ilike(f'%{kw}%'),
                )
                for kw in nsfw_keywords
            ])
            query = query.filter(WebFoundGame.is_nsfw == False, ~keyword_clause)

        total = query.count()
        games = (
            query.order_by(WebFoundGame.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        # Genre list for the filter dropdown - drawn from ALL games, not just this
        # page, so the option list doesn't shrink/shift as the admin paginates.
        all_genre_rows = db.query(WebFoundGame.genres).all()
        all_genres = set()
        for (raw,) in all_genre_rows:
            try:
                all_genres.update(json.loads(raw or '[]'))
            except (TypeError, ValueError):
                pass

        data = [{
            'id': g.id,
            'steam_app_id': g.steam_app_id,
            'name': g.name,
            'steam_url': g.steam_url,
            'igdb_url': g.igdb_url,
            'cover_url': g.cover_url,
            'header_url': g.header_url,
            'summary': g.summary,
            'release_date': g.release_date,
            'developer': g.developer,
            'publisher': g.publisher,
            'price': g.price,
            'review_score': g.review_score,
            'review_count': g.review_count,
            'genres': json.loads(g.genres or '[]'),
            'platforms': json.loads(g.platforms or '[]'),
            'console_platforms': json.loads(g.console_platforms or '[]'),
            'is_featured': g.is_featured,
            'is_hidden': g.is_hidden,
            'is_nsfw': g.is_nsfw,
            'found_at': g.found_at,
        } for g in games]

    return JsonResponse({
        'games': data,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total + page_size - 1) // page_size),
        'genres': sorted(all_genres),
    })


@web_admin_required
@require_http_methods(["POST"])
def api_admin_found_game_action(request, game_id):
    """API: Admin actions on found games (feature, hide, unhide, delete)."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = body.get('action')
    if action not in ('feature', 'unfeature', 'hide', 'unhide', 'delete'):
        return JsonResponse({'error': 'Invalid action'}, status=400)

    with get_db_session() as db:
        game = db.query(WebFoundGame).filter_by(id=game_id).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)

        if action == 'feature':
            game.is_featured = True
        elif action == 'unfeature':
            game.is_featured = False
        elif action == 'hide':
            game.is_hidden = True
        elif action == 'unhide':
            game.is_hidden = False
        elif action == 'delete':
            game_name = game.name
            db.delete(game)
            db.commit()
            log_admin_action(request, 'delete_found_game', 'found_game', game_id, {'name': game_name})
            return JsonResponse({'success': True, 'deleted': True})

        game.updated_at = int(time.time())
        db.commit()
    log_admin_action(request, f'{action}_found_game', 'found_game', game_id, {'action': action})
    return JsonResponse({'success': True})


# --- Raffle Admin ---

@web_admin_required
def api_admin_raffles(request):
    """API: CRUD for raffles."""
    if request.method == 'GET':
        with get_db_session() as db:
            raffles = db.query(WebRaffle).order_by(WebRaffle.created_at.desc()).all()
            data = [{
                'id': r.id,
                'title': r.title,
                'description': r.description,
                'prize_description': r.prize_description,
                'cost_hero_points': r.cost_hero_points,
                'max_entries_per_user': r.max_entries_per_user,
                'max_winners': r.max_winners,
                'start_at': r.start_at,
                'end_at': r.end_at,
                'auto_pick': r.auto_pick,
                'is_active': r.is_active,
                'is_ended': r.is_ended,
                'winners': json.loads(r.winners) if r.winners else [],
                'entry_count': db.query(WebRaffleEntry).filter_by(raffle_id=r.id).count(),
                'created_at': r.created_at,
            } for r in raffles]
        return JsonResponse({'raffles': data})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        with get_db_session() as db:
            raffle = WebRaffle(
                title=body['title'],
                description=body.get('description'),
                prize_description=body.get('prize_description'),
                image_url=validate_admin_image_url(body.get('image_url')),
                cost_hero_points=body.get('cost_hero_points', 0),
                max_entries_per_user=body.get('max_entries_per_user', 1),
                max_winners=body.get('max_winners', 1),
                start_at=body.get('start_at'),
                end_at=body.get('end_at'),
                auto_pick=body.get('auto_pick', False),
                is_active=body.get('is_active', True),
                created_by_id=request.web_user.id,
                created_at=int(time.time()),
                updated_at=int(time.time()),
            )
            db.add(raffle)
            db.commit()
            db.refresh(raffle)
            log_admin_action(request, 'create_raffle', 'raffle', raffle.id, {'title': body['title']})
            return JsonResponse({'success': True, 'id': raffle.id})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@web_admin_required
@require_http_methods(["PUT", "DELETE"])
def api_admin_raffle_detail(request, raffle_id):
    """API: Update/delete a raffle."""
    with get_db_session() as db:
        raffle = db.query(WebRaffle).filter_by(id=raffle_id).first()
        if not raffle:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            raffle_title = raffle.title
            db.query(WebRaffleEntry).filter_by(raffle_id=raffle_id).delete()
            db.delete(raffle)
            db.commit()
            log_admin_action(request, 'delete_raffle', 'raffle', raffle_id, {'title': raffle_title})
            return JsonResponse({'success': True})

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        _raffle_field_types = {
            'title': str, 'description': str, 'prize_description': str,
            'cost_hero_points': int, 'max_entries_per_user': int, 'max_winners': int,
            'start_at': int, 'end_at': int, 'auto_pick': bool, 'is_active': bool,
        }
        for field, coerce in _raffle_field_types.items():
            if field in body:
                try:
                    setattr(raffle, field, coerce(body[field]) if body[field] is not None else None)
                except (ValueError, TypeError):
                    pass
        if 'image_url' in body:
            raffle.image_url = validate_admin_image_url(body['image_url'])
        raffle.updated_at = int(time.time())
        db.commit()
        log_admin_action(request, 'update_raffle', 'raffle', raffle_id, body)
        return JsonResponse({'success': True})


@web_admin_required
@require_http_methods(["POST"])
def api_admin_raffle_pick_winners(request, raffle_id):
    """API: Pick winners for a raffle."""
    import secrets
    with get_db_session() as db:
        raffle = db.query(WebRaffle).filter_by(id=raffle_id).first()
        if not raffle:
            return JsonResponse({'error': 'Not found'}, status=404)

        entries = db.query(WebRaffleEntry).filter_by(raffle_id=raffle_id).all()
        if not entries:
            return JsonResponse({'error': 'No entries'}, status=400)

        # Build weighted pool
        pool = []
        for entry in entries:
            pool.extend([entry.user_id] * entry.tickets)

        # Pick unique winners
        winners = []
        pool_copy = list(pool)
        for _ in range(min(raffle.max_winners, len(set(e.user_id for e in entries)))):
            if not pool_copy:
                break
            winner = secrets.choice(pool_copy)
            winners.append(winner)
            pool_copy = [uid for uid in pool_copy if uid != winner]

        raffle.winners = json.dumps(winners)
        raffle.is_ended = True
        raffle.is_active = False
        raffle.updated_at = int(time.time())
        db.commit()

        # Get winner usernames
        winner_names = []
        for wid in winners:
            user = db.query(WebUser).filter_by(id=wid).first()
            if user:
                winner_names.append({'id': user.id, 'username': user.username})

    log_admin_action(request, 'pick_raffle_winners', 'raffle', raffle_id, {'winners': winner_names})
    return JsonResponse({'success': True, 'winners': winner_names})


# --- RSS Feed Admin ---

# Maps field name → coercion function for admin setattr() to prevent type confusion
_RSS_EDITABLE_FIELDS = {
    'name': str,
    'url': str,
    'description': str,
    'icon_url': str,
    'is_active': bool,
    'fetch_interval': int,
}

def _serialize_rss_feed(f, article_count):
    return {
        'id': f.id,
        'name': f.name,
        'url': f.url,
        'description': f.description,
        'icon_url': f.icon_url,
        'is_active': f.is_active,
        'fetch_interval': f.fetch_interval or 15,
        'last_fetched_at': f.last_fetched_at,
        'last_error': f.last_error,
        'article_count': article_count,
        'created_at': f.created_at,
    }


@web_admin_required
def api_admin_rss_feeds(request):
    """API: CRUD for RSS feeds."""
    if request.method == 'GET':
        with get_db_session() as db:
            feeds = db.query(WebRSSFeed).order_by(WebRSSFeed.name).all()
            data = [_serialize_rss_feed(f, db.query(WebRSSArticle).filter_by(feed_id=f.id).count()) for f in feeds]
        return JsonResponse({'feeds': data})

    elif request.method == 'POST':
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if not body.get('name') or not body.get('url'):
            return JsonResponse({'error': 'Name and URL are required'}, status=400)

        now = int(time.time())
        feed = WebRSSFeed(created_at=now, updated_at=now)
        for field, coerce in _RSS_EDITABLE_FIELDS.items():
            if field in body:
                try:
                    setattr(feed, field, coerce(body[field]) if body[field] is not None else None)
                except (ValueError, TypeError):
                    pass

        with get_db_session() as db:
            db.add(feed)
            db.commit()
            db.refresh(feed)
            log_admin_action(request, 'create_rss_feed', 'rss_feed', feed.id, {'name': body['name'], 'url': body['url']})
            return JsonResponse({'success': True, 'id': feed.id})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@web_admin_required
@require_http_methods(["PUT", "DELETE"])
def api_admin_rss_feed_detail(request, feed_id):
    """API: Update/delete an RSS feed."""
    with get_db_session() as db:
        feed = db.query(WebRSSFeed).filter_by(id=feed_id).first()
        if not feed:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            feed_name = feed.name
            db.query(WebRSSArticle).filter_by(feed_id=feed_id).delete()
            db.delete(feed)
            db.commit()
            log_admin_action(request, 'delete_rss_feed', 'rss_feed', feed_id, {'name': feed_name})
            return JsonResponse({'success': True})

        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        for field, coerce in _RSS_EDITABLE_FIELDS.items():
            if field in body:
                try:
                    setattr(feed, field, coerce(body[field]) if body[field] is not None else None)
                except (ValueError, TypeError):
                    pass
        feed.updated_at = int(time.time())
        db.commit()
        log_admin_action(request, 'update_rss_feed', 'rss_feed', feed_id, body)
        return JsonResponse({'success': True})


@web_admin_required
@require_http_methods(["POST"])
def api_admin_validate_rss(request):
    """POST: Validate that a URL is a reachable RSS/Atom feed."""
    from app.rss_utils import secure_fetch_rss
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'valid': False, 'error': 'Invalid JSON'}, status=400)

    url = body.get('url', '').strip()
    if not url:
        return JsonResponse({'valid': False, 'error': 'No URL provided'})

    feed, error = secure_fetch_rss(url)
    if error:
        return JsonResponse({'valid': False, 'error': error})
    return JsonResponse({
        'valid': True,
        'title': feed.feed.get('title', ''),
        'entry_count': len(feed.entries),
    })


@web_admin_required
@require_http_methods(["POST"])
def api_admin_rss_feed_fetch_now(request, feed_id):
    """API: Immediately fetch new articles for a single RSS feed."""
    clear = request.GET.get('clear') == '1'
    with get_db_session() as db:
        feed = db.query(WebRSSFeed).filter_by(id=feed_id).first()
        if not feed:
            return JsonResponse({'error': 'Not found'}, status=404)
        if clear:
            db.query(WebRSSArticle).filter_by(feed_id=feed_id).delete()
            db.commit()
        new_count, error = fetch_rss_feed(feed, db)

    if error:
        return JsonResponse({'success': False, 'error': error})
    return JsonResponse({'success': True, 'new_articles': new_count})


# --- User Admin ---

@web_admin_required
@require_http_methods(['GET'])
def api_admin_tracker_stats(request):
    """Admin: Full site analytics + Mortality Tracker download stats."""
    import time as _time
    from sqlalchemy import text as _t
    now = int(_time.time())
    period_days = int(request.GET.get('days', 30))
    since = now - (period_days * 86400)

    SECTION_LABELS = {
        'soulslike_tracker': 'Mortality Tracker',
        'soulslike_r2':      'Remnant 2',
        'soulslike':         'SoulsLike Hub',
        'survival':          'Survival Hub',
        'palworld':          'Palworld',
        'ffxiv_tools':       'FFXIV Tools',
        'ffxiv':             'FFXIV',
        'eso':               'ESO',
        'indie_heroes':      'Indie Heroes',
        'lfg':               'LFG',
        'games_we_play':     'Games We Play',
        'game_servers':      'Game Servers',
        'communities':       'Communities',
        'discover':          'Discover',
        'blog':              'Blog',
        'creators':          'Creators',
        'steamquest':        'SteamQuest',
        'leaderboard':       'Leaderboard',
        'profile':           'Profiles',
        'register':          'Register',
        'getting_started':   'Getting Started',
    }

    try:
        with get_db_session() as db:
            # Site-wide totals
            total_views = db.execute(_t(
                "SELECT COUNT(*) FROM web_page_views WHERE created_at >= :s"
            ), {'s': since}).scalar() or 0

            unique_visitors = db.execute(_t(
                "SELECT COUNT(DISTINCT ip_hash) FROM web_page_views WHERE created_at >= :s"
            ), {'s': since}).scalar() or 0

            # Views + unique visitors per section
            section_rows = db.execute(_t(
                "SELECT section, COUNT(*) as views, COUNT(DISTINCT ip_hash) as uniques "
                "FROM web_page_views "
                "WHERE created_at >= :s GROUP BY section ORDER BY views DESC"
            ), {'s': since}).fetchall()
            sections = [
                {
                    'section': r[0],
                    'label': SECTION_LABELS.get(r[0], r[0].replace('_', ' ').title()),
                    'views': r[1],
                    'uniques': r[2],
                }
                for r in section_rows
            ]

            # New vs returning
            new_visitors = db.execute(_t(
                "SELECT COUNT(DISTINCT ip_hash) FROM web_page_views "
                "WHERE created_at >= :s AND is_new_visitor = 1"
            ), {'s': since}).scalar() or 0
            returning_visitors = db.execute(_t(
                "SELECT COUNT(DISTINCT ip_hash) FROM web_page_views "
                "WHERE created_at >= :s AND is_new_visitor = 0"
            ), {'s': since}).scalar() or 0

            # Traffic sources (utm_source)
            source_rows = db.execute(_t(
                "SELECT utm_source, COUNT(*) as views, COUNT(DISTINCT ip_hash) as uniques "
                "FROM web_page_views WHERE created_at >= :s AND utm_source IS NOT NULL "
                "GROUP BY utm_source ORDER BY views DESC LIMIT 15"
            ), {'s': since}).fetchall()

            # Top external referrers only (exclude own domain)
            referrer_rows = db.execute(_t(
                "SELECT referrer, COUNT(*) as cnt FROM web_page_views "
                "WHERE created_at >= :s AND referrer IS NOT NULL AND referrer != '' "
                "AND referrer NOT LIKE '%questlog.casual-heroes.com%' "
                "AND referrer NOT LIKE '%casual-heroes.com%' "
                "AND utm_source != 'internal' "
                "GROUP BY referrer ORDER BY cnt DESC LIMIT 10"
            ), {'s': since}).fetchall()

            # Internal navigation - top pages people click FROM within the site
            internal_nav_rows = db.execute(_t(
                "SELECT referrer, COUNT(*) as cnt FROM web_page_views "
                "WHERE created_at >= :s AND referrer IS NOT NULL "
                "AND referrer LIKE '%questlog.casual-heroes.com%' "
                "GROUP BY referrer ORDER BY cnt DESC LIMIT 10"
            ), {'s': since}).fetchall()

            # Daily trend (last 14 days)
            daily = db.execute(_t(
                "SELECT DATE(FROM_UNIXTIME(created_at)) as day, COUNT(*) as cnt "
                "FROM web_page_views WHERE created_at >= :s "
                "GROUP BY day ORDER BY day DESC LIMIT 14"
            ), {'s': now - 14 * 86400}).fetchall()

            # Tracker downloads
            total_dl = db.execute(_t("SELECT COUNT(*) FROM web_tracker_download_stats")).scalar() or 0
            dl_by_platform = {}
            for r in db.execute(_t(
                "SELECT platform, COUNT(*) FROM web_tracker_download_stats GROUP BY platform"
            )).fetchall():
                dl_by_platform[r[0] or 'unknown'] = r[1]

            recent_dl = db.execute(_t(
                "SELECT platform, created_at FROM web_tracker_download_stats ORDER BY created_at DESC LIMIT 20"
            )).fetchall()

        return JsonResponse({
            'period_days': period_days,
            'total_views': total_views,
            'unique_visitors': unique_visitors,
            'new_visitors': new_visitors,
            'returning_visitors': returning_visitors,
            'sections': sections,
            'traffic_sources': [
                {'source': r[0], 'views': r[1], 'uniques': r[2]}
                for r in source_rows
            ],
            'top_referrers': [
                {'referrer': r[0], 'count': r[1]}
                for r in referrer_rows
            ],
            'internal_nav': [
                {'referrer': r[0], 'count': r[1]}
                for r in internal_nav_rows
            ],
            'daily_trend': [{'day': str(r[0]), 'views': r[1]} for r in daily],
            'tracker': {
                'total_downloads': total_dl,
                'by_platform': dl_by_platform,
                'recent': [{'platform': r[0] or 'unknown', 'created_at': r[1]} for r in recent_dl],
            },
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@web_mod_required
def api_admin_users(request):
    """API: List users for admin."""
    q = request.GET.get('q', '').strip()
    with get_db_session() as db:
        query = db.query(WebUser).order_by(WebUser.username)
        if q:
            query = query.filter(
                or_(WebUser.username.ilike(f'%{q}%'), WebUser.display_name.ilike(f'%{q}%'))
            )
        users = query.limit(200).all()
        # Fetch all admin-only flairs once for grant/revoke UI
        admin_flairs = db.query(WebFlair).filter(
            WebFlair.admin_only == 1, WebFlair.enabled == True
        ).order_by(WebFlair.display_order, WebFlair.id).all()
        admin_flair_list = [{'id': f.id, 'name': f.name, 'emoji': f.emoji or ''} for f in admin_flairs]
        # Build per-user owned-admin-flair set
        user_ids = [u.id for u in users]
        admin_flair_ids = {f.id for f in admin_flairs}
        owned_rows = db.query(WebUserFlair).filter(
            WebUserFlair.user_id.in_(user_ids),
            WebUserFlair.flair_id.in_(admin_flair_ids),
        ).all() if admin_flair_ids else []
        owned_map: dict = {}
        for row in owned_rows:
            owned_map.setdefault(row.user_id, set()).add(row.flair_id)

        data = [{
            'id': u.id,
            'username': u.username,
            'display_name': u.display_name,
            'email_domain': u.email.split('@')[-1] if u.email and '@' in u.email else '',
            'avatar_url': u.avatar_url,
            'is_admin': u.is_admin,
            'is_mod': bool(u.is_mod),
            'is_vip': bool(u.is_vip),
            'is_founder': bool(u.is_founder),
            'is_ffxiv_member': bool(u.is_ffxiv_member),
            'is_eso_member': bool(u.is_eso_member),
            'is_contributor': bool(u.is_contributor),
            'is_indie_dev': bool(u.is_indie_dev),
            'indie_dev_pending': bool(u.indie_dev_pending),
            'is_banned': u.is_banned,
            'ban_reason': u.ban_reason,
            'is_disabled': u.is_disabled,
            'is_hidden': bool(u.is_hidden),
            'posting_timeout_until': u.posting_timeout_until,
            'post_count': u.post_count,
            'web_xp': u.web_xp,
            'web_level': u.web_level,
            'hero_points': u.hero_points,
            'created_at': u.created_at,
            'last_login_at': u.last_login_at,
            'email_verified': bool(u.email_verified),
            'owned_admin_flair_ids': list(owned_map.get(u.id, set())),
        } for u in users]
    return JsonResponse({'users': data, 'admin_flairs': admin_flair_list})


@web_mod_required
@require_http_methods(["POST"])
def api_admin_user_action(request, user_id):
    """API: Admin actions on user (ban, unban, toggle admin/mod)."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = body.get('action')
    is_mod_only = request.web_user.is_mod and not request.web_user.is_admin

    all_actions = ('ban', 'unban', 'disable', 'enable', 'timeout', 'clear_timeout',
                   'make_admin', 'remove_admin', 'grant_mod', 'revoke_mod',
                   'set_hero_points', 'delete_posts',
                   'purge_user', 'grant_vip', 'revoke_vip', 'award_most_helpful',
                   'grant_ffxiv', 'revoke_ffxiv',
                   'grant_eso', 'revoke_eso',
                   'grant_contributor', 'revoke_contributor',
                   'grant_founder', 'revoke_founder',
                   'verify_email',
                   'grant_flair', 'revoke_flair',
                   'hide_user', 'unhide_user',
                   'approve_dev', 'reject_dev')
    # Actions mods are allowed to perform
    mod_allowed_actions = ('timeout', 'clear_timeout', 'disable', 'enable', 'delete_posts')

    if action not in all_actions:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    if is_mod_only and action not in mod_allowed_actions:
        return JsonResponse({'error': 'Access denied - admin only action'}, status=403)

    now = int(time.time())
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user:
            return JsonResponse({'error': 'Not found'}, status=404)

        # Prevent self-action on destructive operations
        if user_id == request.web_user.id and action in ('ban', 'disable', 'remove_admin', 'revoke_mod'):
            return JsonResponse({'error': 'Cannot perform this action on your own account'}, status=400)

        # A mod (not a full admin) may only act on regular users - otherwise a
        # mod could disable/timeout/mass-delete-posts on another mod's or an
        # admin's account, which is a privilege-escalation path since
        # mod_allowed_actions has no target-role check of its own.
        if is_mod_only and (user.is_admin or user.is_mod):
            return JsonResponse({'error': 'Access denied - cannot act on a mod or admin account'}, status=403)

        if action == 'ban':
            user.is_banned = True
            user.ban_reason = body.get('reason', '')
        elif action == 'unban':
            user.is_banned = False
            user.ban_reason = None
        elif action == 'disable':
            user.is_disabled = True
        elif action == 'enable':
            user.is_disabled = False
        elif action == 'timeout':
            try:
                hours = int(body.get('hours', 24))
            except (TypeError, ValueError):
                return JsonResponse({'error': 'Invalid hours value'}, status=400)
            hours = max(1, min(hours, 720))  # 1h to 30 days
            user.posting_timeout_until = now + (hours * 3600)
        elif action == 'clear_timeout':
            user.posting_timeout_until = None
        elif action == 'make_admin':
            user.is_admin = True
            # Sync Django is_superuser so web_admin_required decorator passes
            try:
                DjangoUser.objects.filter(username__iexact=user.username).update(is_superuser=True, is_staff=True)
            except Exception:
                pass
        elif action == 'remove_admin':
            user.is_admin = False
            # Sync Django is_superuser
            try:
                DjangoUser.objects.filter(username__iexact=user.username).update(is_superuser=False, is_staff=False)
            except Exception:
                pass
        elif action == 'grant_mod':
            user.is_mod = True
        elif action == 'revoke_mod':
            user.is_mod = False
        elif action == 'set_hero_points':
            try:
                hp = int(body.get('hero_points', 0))
            except (TypeError, ValueError):
                return JsonResponse({'error': 'hero_points must be an integer'}, status=400)
            if not (0 <= hp <= 999999):
                return JsonResponse({'error': 'hero_points must be between 0 and 999999'}, status=400)
            user.hero_points = hp
        elif action == 'delete_posts':
            db.query(WebPost).filter_by(author_id=user_id).update({'is_deleted': True})

        elif action == 'grant_vip':
            user.is_vip = True
            # Find the Early Tester flair and auto-grant it
            vip_flair = db.query(WebFlair).filter_by(name='Early Tester').first()
            if vip_flair:
                existing_uf = db.query(WebUserFlair).filter_by(
                    user_id=user_id, flair_id=vip_flair.id
                ).first()
                if not existing_uf:
                    db.add(WebUserFlair(
                        user_id=user_id,
                        flair_id=vip_flair.id,
                        is_equipped=False,
                        purchased_at=now,
                    ))
                # Auto-equip if user has no active flair
                if not user.active_flair_id:
                    user.active_flair_id = vip_flair.id

        elif action == 'revoke_vip':
            user.is_vip = False
            # Leave the flair in their collection - it's a reward they earned

        elif action == 'grant_founder':
            user.is_founder = True
            # Auto-grant the Founding Member flair
            founder_flair = db.query(WebFlair).filter_by(name='Founding Member').first()
            if founder_flair:
                existing_uf = db.query(WebUserFlair).filter_by(
                    user_id=user_id, flair_id=founder_flair.id
                ).first()
                if not existing_uf:
                    db.add(WebUserFlair(
                        user_id=user_id,
                        flair_id=founder_flair.id,
                        is_equipped=False,
                        purchased_at=now,
                    ))
                if not user.active_flair_id:
                    user.active_flair_id = founder_flair.id

        elif action == 'revoke_founder':
            user.is_founder = False
            # Leave the flair - it's earned, not revoked

        elif action == 'grant_ffxiv':
            user.is_ffxiv_member = True

        elif action == 'revoke_ffxiv':
            user.is_ffxiv_member = False

        elif action == 'grant_eso':
            user.is_eso_member = True

        elif action == 'revoke_eso':
            user.is_eso_member = False

        elif action == 'grant_contributor':
            user.is_contributor = True

        elif action == 'revoke_contributor':
            user.is_contributor = False

        elif action == 'grant_indie_dev':
            user.is_indie_dev = True

        elif action == 'revoke_indie_dev':
            user.is_indie_dev = False

        elif action == 'hide_user':
            user.is_hidden = True

        elif action == 'unhide_user':
            user.is_hidden = False

        elif action == 'approve_dev':
            user.is_indie_dev = True
            user.indie_dev_pending = False

        elif action == 'reject_dev':
            user.is_indie_dev = False
            user.indie_dev_pending = False

        elif action == 'verify_email':
            user.email_verified = True

        elif action == 'grant_flair':
            flair_id = safe_int(body.get('flair_id'), 0)
            flair = db.query(WebFlair).filter_by(id=flair_id).first()
            if not flair:
                return JsonResponse({'error': 'Flair not found'}, status=404)
            existing = db.query(WebUserFlair).filter_by(user_id=user_id, flair_id=flair_id).first()
            if not existing:
                db.add(WebUserFlair(user_id=user_id, flair_id=flair_id, is_equipped=False,
                                    purchased_at=now))
            db.commit()
            log_admin_action(request, 'grant_flair', 'user', user_id, {
                'action': 'grant_flair', 'flair_id': flair_id, 'flair_name': flair.name,
                'target_username': user.username,
            })
            return JsonResponse({'success': True})

        elif action == 'revoke_flair':
            flair_id = safe_int(body.get('flair_id'), 0)
            flair = db.query(WebFlair).filter_by(id=flair_id).first()
            if not flair:
                return JsonResponse({'error': 'Flair not found'}, status=404)
            db.query(WebUserFlair).filter_by(user_id=user_id, flair_id=flair_id).delete()
            # If user had this flair equipped, clear it
            if user.active_flair_id == flair_id:
                user.active_flair_id = None
            if getattr(user, 'active_flair2_id', None) == flair_id:
                user.active_flair2_id = None
            db.commit()
            log_admin_action(request, 'revoke_flair', 'user', user_id, {
                'action': 'revoke_flair', 'flair_id': flair_id, 'flair_name': flair.name,
                'target_username': user.username,
            })
            return JsonResponse({'success': True})

        elif action == 'award_most_helpful':
            # Manual fallback: admin awards Most Helpful to a user for a given month+category
            from .helpers import award_legacy
            category = (body.get('category') or 'community').strip()
            month_year = (body.get('month_year') or '').strip()
            if not month_year or len(month_year) != 7:
                import datetime as _dt
                month_year = _dt.datetime.utcnow().strftime('%Y-%m')
            valid_cats = {'community', 'lfg_host', 'build', '7dtd', 'valheim', 'minecraft', 'dayz', 'palworld'}
            if category not in valid_cats:
                return JsonResponse({'error': 'Invalid category'}, status=400)
            db.commit()  # flush before calling award_legacy (opens its own session)
            award_legacy(user_id, 'most_helpful_vote', source='web', ref_id=f"{month_year}:{category}")
            log_admin_action(request, 'award_most_helpful', 'user', user_id, {
                'action': 'award_most_helpful',
                'target_username': user.username,
                'category': category,
                'month_year': month_year,
            })
            return JsonResponse({'success': True})

        elif action == 'purge_user':
            if user_id == request.web_user.id:
                return JsonResponse({'error': 'Cannot purge your own account'}, status=400)
            target_username = user.username

            # Wipe all social data
            db.query(WebLike).filter_by(user_id=user_id).delete()
            db.query(WebCommentLike).filter_by(user_id=user_id).delete()
            db.query(WebComment).filter_by(author_id=user_id).delete()
            db.query(WebPost).filter_by(author_id=user_id).delete()
            db.query(WebFollow).filter(
                (WebFollow.follower_id == user_id) | (WebFollow.following_id == user_id)
            ).delete(synchronize_session=False)
            db.query(WebNotification).filter(
                (WebNotification.user_id == user_id) | (WebNotification.actor_id == user_id)
            ).delete(synchronize_session=False)
            db.query(WebUserBlock).filter(
                (WebUserBlock.blocker_id == user_id) | (WebUserBlock.blocked_id == user_id)
            ).delete(synchronize_session=False)
            db.query(WebLFGMember).filter_by(user_id=user_id).delete()

            db.delete(user)
            db.commit()

            # Delete Django auth_user row (frees the username + email for re-registration)
            DjangoUser.objects.filter(username__iexact=target_username).delete()

            log_admin_action(request, 'purge_user', 'user', user_id, {
                'action': 'purge_user',
                'target_username': target_username,
                'reason': body.get('reason', ''),
            })
            return JsonResponse({'success': True})

        user.updated_at = now
        db.commit()

    # Award negative legacy for ban actions (outside session to avoid DetachedInstanceError)
    if action == 'ban':
        try:
            from .helpers import award_legacy
            import time as _time
            ref_id = f"ban_{user_id}_{int(_time.time())}"
            award_legacy(user_id, 'report_upheld', source='web', ref_id=ref_id)
        except Exception as e:
            logger.warning(f"[Admin] Failed to award negative legacy for ban on user {user_id}: {e}")
    elif action == 'timeout' and body.get('hours', 0):
        try:
            from .helpers import award_legacy
            import time as _time
            hours = body.get('hours', 24)
            # Only apply temp_ban penalty for longer timeouts (24h+) to avoid spam
            if int(hours) >= 24:
                ref_id = f"timeout_{user_id}_{int(_time.time())}"
                award_legacy(user_id, 'temp_ban', source='web', ref_id=ref_id)
        except Exception as e:
            logger.warning(f"[Admin] Failed to award negative legacy for timeout on user {user_id}: {e}")

    log_admin_action(request, f'{action}_user', 'user', user_id, {
        'action': action,
        'target_username': user.username if user else 'unknown',
        'reason': body.get('reason', ''),
    })
    return JsonResponse({'success': True})


# --- Admin Audit Log ---

@web_mod_required
def api_admin_audit_log(request):
    """API: View admin audit log."""
    limit = safe_int(request.GET.get('limit', 100), default=100, min_val=1, max_val=500)
    with get_db_session() as db:
        entries = db.query(AdminAuditLog).order_by(
            AdminAuditLog.created_at.desc()
        ).limit(limit).all()

        admin_ids = set(e.admin_user_id for e in entries)
        admins = {}
        if admin_ids:
            for admin in db.query(WebUser).filter(WebUser.id.in_(admin_ids)).all():
                admins[admin.id] = admin.username

        data = [{
            'id': e.id,
            'admin_username': e.admin_username or admins.get(e.admin_user_id, 'Unknown'),
            'action': e.action,
            'target_type': e.target_type,
            'target_id': e.target_id,
            'details': json.loads(e.details) if e.details else None,
            'ip_address': e.ip_address,
            'created_at': e.created_at,
        } for e in entries]
    return JsonResponse({'entries': data})


# --- Admin Social Moderation ---

@web_mod_required
def api_admin_posts(request):
    """GET: List posts for moderation. Paginated."""
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1)
    per_page = safe_int(request.GET.get('per_page', 50), default=50, min_val=1, max_val=50)
    offset = (page - 1) * per_page
    show_hidden = request.GET.get('hidden', 'false').lower() == 'true'
    show_deleted = request.GET.get('deleted', 'false').lower() == 'true'

    with get_db_session() as db:
        query = db.query(WebPost)
        if not show_deleted:
            query = query.filter(WebPost.is_deleted == False)
        if show_hidden:
            query = query.filter(WebPost.is_hidden == True)

        total = query.count()
        posts = query.order_by(WebPost.created_at.desc()).offset(offset).limit(per_page).all()
        data = [serialize_post(p, None, db) for p in posts]

    return JsonResponse({'posts': data, 'total': total, 'page': page})


@web_mod_required
@require_http_methods(["POST"])
def api_admin_post_action(request, post_id):
    """POST: Admin action on a post (hide/unhide/delete/pin/unpin)."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')
    if action not in ('hide', 'unhide', 'delete', 'pin', 'unpin'):
        return JsonResponse({'error': 'Invalid action'}, status=400)

    with get_db_session() as db:
        post = db.query(WebPost).filter_by(id=post_id).first()
        if not post:
            return JsonResponse({'error': 'Post not found'}, status=404)

        if action == 'hide':
            post.is_hidden = True
        elif action == 'unhide':
            post.is_hidden = False
        elif action == 'delete':
            post.is_deleted = True
            user = db.query(WebUser).filter_by(id=post.author_id).first()
            if user and user.post_count and user.post_count > 0:
                user.post_count -= 1
        elif action == 'pin':
            post.is_pinned = True
        elif action == 'unpin':
            post.is_pinned = False

        post.updated_at = int(time.time())
        log_admin_action(request, f'{action}_post', target_type='post', target_id=post_id, details={
            'action': action,
            'author_id': post.author_id,
            'post_type': post.post_type,
            'content_preview': (post.content or '')[:200],
        })
        db.commit()

    return JsonResponse({'success': True})


@web_mod_required
@require_http_methods(["POST"])
def api_admin_comment_action(request, comment_id):
    """POST: Admin action on a comment (delete/hide)."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')
    if action != 'delete':
        return JsonResponse({'error': 'Invalid action'}, status=400)

    with get_db_session() as db:
        comment = db.query(WebComment).filter_by(id=comment_id).first()
        if not comment:
            return JsonResponse({'error': 'Comment not found'}, status=404)

        comment.is_deleted = True
        post = db.query(WebPost).filter_by(id=comment.post_id).first()
        if post and post.comment_count and post.comment_count > 0:
            post.comment_count -= 1
        log_admin_action(request, f'{action}_comment', target_type='comment', target_id=comment_id, details={
            'action': action,
            'author_id': comment.author_id,
            'post_id': comment.post_id,
            'content_preview': (comment.content or '')[:200],
        })
        db.commit()

    return JsonResponse({'success': True})


# ── Games We Play Tracker ──────────────────────────────────────────────────────

@web_mod_required
@add_web_user_context
def admin_games_tracker(request):
    """Admin page for managing /gamesweplay/ game list."""
    with get_db_session() as db:
        games = db.query(SiteActivityGame).order_by(
            SiteActivityGame.sort_order, SiteActivityGame.display_name
        ).all()

        games_data = []
        for game in games:
            roles = db.query(SiteActivityGuildRole).filter_by(game_id=game.id, is_active=True).all()
            fluxer_roles = db.query(SiteActivityFluxerRole).filter_by(game_id=game.id, is_active=True).all()
            games_data.append({
                'id': game.id,
                'game_key': game.game_key,
                'display_name': game.display_name,
                'description': game.description,
                'activity_keywords': json.loads(game.activity_keywords or '[]'),
                'game_type': game.game_type,
                'display_on': game.display_on or 'gamesweplay',
                'amp_instance_id': game.amp_instance_id,
                'steam_appid': game.steam_appid,
                'steam_link': game.steam_link,
                'discord_invite': game.discord_invite,
                'custom_img': game.custom_img,
                'link_label': game.link_label,
                'is_active': game.is_active,
                'sort_order': game.sort_order,
                'roles': [{
                    'id': r.id,
                    'guild_id': str(r.guild_id),
                    'role_id': str(r.role_id),
                    'guild_name': r.guild_name,
                    'role_name': r.role_name,
                } for r in roles],
                'fluxer_roles': [{
                    'id': r.id,
                    'guild_id': r.guild_id,
                    'role_id': r.role_id,
                    'guild_name': r.guild_name,
                    'role_name': r.role_name,
                } for r in fluxer_roles],
            })

    return render(request, 'questlog_web/admin_games_tracker.html', {
        'games': games_data,
        'web_user': request.web_user,
        'active_page': 'admin',
    })


# ---------------------------------------------------------------------------
# Quest Control (unified) - site-admin page, not guild-scoped-by-URL.
# Replaces the old per-guild pages guild_quest_control (Discord) and
# fluxer_guild_game_servers (Fluxer). Reads/writes the same gamebot_configs
# table and calls the same /api/admin/quest-control/* endpoints - unchanged.
# ---------------------------------------------------------------------------

_QC_GAME_ICONS = {
    'V Rising':          ('fa-droplet',   'red'),
    'Seven Days To Die': ('fa-biohazard', 'orange'),
    'Enshrouded':        ('fa-cloud',     'purple'),
    'Valheim':           ('fa-hammer',    'blue'),
    'Icarus':            ('fa-mountain',  'green'),
    'Palworld':          ('fa-paw',       'yellow'),
}
_QC_DEFAULT_ICON = ('fa-server', 'cyan')


def _qc_load_discord_guilds():
    """All Discord guilds WardenBot is in - site-owner view, not session-scoped."""
    from app.models import Guild as GuildModel
    out = []
    try:
        with get_db_session() as db:
            rows = db.query(GuildModel).order_by(GuildModel.guild_name).all()
            for g in rows:
                out.append({'id': str(g.guild_id), 'name': g.guild_name or str(g.guild_id)})
    except Exception as e:
        logger.warning('_qc_load_discord_guilds: %s', e)
    return out


def _qc_load_fluxer_guilds():
    """All Fluxer guilds the bot currently has joined (bot_present=1)."""
    out = []
    try:
        with get_db_session() as db:
            rows = db.query(WebFluxerGuildSettings).filter_by(bot_present=1).order_by(
                WebFluxerGuildSettings.guild_name
            ).all()
            for g in rows:
                out.append({'id': str(g.guild_id), 'name': g.guild_name or str(g.guild_id)})
    except Exception as e:
        logger.warning('_qc_load_fluxer_guilds: %s', e)
    return out


def _qc_load_channels_roles(platform, guild_id):
    """Load channel/role picker options for a guild, keyed by platform."""
    import json as _json
    channels, roles = [], []
    if not guild_id:
        return channels, roles

    # Every option is tagged with 'platform' so the client can tell a merged
    # Discord+Fluxer channel/role list apart when a channel is actually picked -
    # e.g. sending an embed needs to know whether the chosen channel_id belongs
    # to the Discord broadcast queue or the Fluxer one.
    if platform == 'discord':
        from app.models import Guild as GuildModel
        try:
            with get_db_session() as db:
                g = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
                if g:
                    if g.cached_channels:
                        raw_channels = _json.loads(g.cached_channels)
                        channels = [
                            {'value': str(c['id']), 'label': c['name'], 'platform': 'discord'}
                            for c in raw_channels
                            if c.get('type') == 0 or c.get('type') == 'text'
                        ]
                    if g.cached_roles:
                        raw_roles = _json.loads(g.cached_roles)
                        roles = [
                            {'value': str(r['id']), 'label': r['name'], 'platform': 'discord'}
                            for r in sorted(raw_roles, key=lambda x: -x.get('position', 0))
                        ]
        except Exception as e:
            logger.warning('_qc_load_channels_roles(discord, %s): %s', guild_id, e)
    else:
        from app.db import get_engine
        from sqlalchemy import text as sa_text2
        engine = get_engine()
        try:
            with engine.connect() as conn:
                ch_rows = conn.execute(sa_text2(
                    "SELECT channel_id, channel_name FROM web_fluxer_guild_channels "
                    "WHERE guild_id = :g ORDER BY channel_name"
                ), {'g': str(guild_id)}).fetchall()
                channels = [{'value': str(r.channel_id), 'label': r.channel_name or str(r.channel_id), 'platform': 'fluxer'} for r in ch_rows]
                role_rows = conn.execute(sa_text2(
                    "SELECT role_id, role_name FROM web_fluxer_guild_roles "
                    "WHERE guild_id = :g ORDER BY position DESC"
                ), {'g': str(guild_id)}).fetchall()
                roles = [{'value': str(r.role_id), 'label': r.role_name or str(r.role_id), 'platform': 'fluxer'} for r in role_rows]
        except Exception as e:
            logger.warning('_qc_load_channels_roles(fluxer, %s): %s', guild_id, e)

    return channels, roles


@web_mod_required
@add_web_user_context
def admin_quest_control(request):
    """
    Unified Quest Control page. Site admins see every configured instance
    unconditionally - no guild has to be picked first. Mods (is_mod=True, not
    is_admin) only see instances where their linked Discord/Fluxer account
    currently holds that instance's configured Manager role - checked fresh on
    every page load via _web_user_manages_instance, same check the API endpoints
    enforce, so a mod can never see (or act on) an instance they don't manage.
    Each instance independently and optionally links a Discord guild and/or a Fluxer
    guild purely for notification purposes (which channels get status embeds, etc) -
    that's a per-instance setting managed inline on its own card, not a page-level
    filter/gate. Reference lists of every known Discord/Fluxer guild are still loaded
    up front, to populate the per-instance link-guild pickers.
    """
    from app.db import get_engine
    from sqlalchemy import text as sa_text2

    # Only site admins can link/relink a guild to an instance (see
    # api_quest_control_link_guild), so the full guild directory - names and IDs
    # for every Discord/Fluxer guild QuestLog knows about - is only loaded for
    # them. A mod has no use for it and shouldn't see guilds they don't manage.
    is_site_admin = bool(request.web_user and request.web_user.is_admin)
    discord_guilds = _qc_load_discord_guilds() if is_site_admin else []
    fluxer_guilds = _qc_load_fluxer_guilds() if is_site_admin else []

    engine = get_engine()
    all_rows = []
    try:
        with engine.connect() as conn:
            rows = conn.execute(sa_text2(
                "SELECT * FROM gamebot_configs "
                "ORDER BY configured DESC, COALESCE(NULLIF(server_display_name,''), instance_name) ASC"
            )).fetchall()
            all_rows = [dict(r._mapping) for r in rows]
    except Exception as e:
        logger.warning('admin_quest_control: gamebot_configs query failed: %s', e)

    # Cache channel/role lookups per guild id so an instance's own linked guild(s)
    # aren't refetched if another instance happens to link the same guild.
    _channels_cache = {}
    def _channels_for(platform, guild_id):
        if not guild_id:
            return [], []
        key = (platform, guild_id)
        if key not in _channels_cache:
            _channels_cache[key] = _qc_load_channels_roles(platform, guild_id)
        return _channels_cache[key]

    bots, unconfigured_bots = [], []
    for cfg in all_rows:
        game_type = cfg.get('game_type', 'Unknown')
        icon, color = _QC_GAME_ICONS.get(game_type, _QC_DEFAULT_ICON)

        if cfg.get('configured'):
            discord_channels, discord_roles = _channels_for('discord', cfg.get('discord_guild_id'))
            fluxer_channels, fluxer_roles = _channels_for('fluxer', cfg.get('fluxer_guild_id'))
            bots.append({
                'slug':          cfg['instance_name'],
                'name':          cfg.get('server_display_name') or cfg['instance_name'],
                'game':          game_type,
                'icon':          icon,
                'color':         color,
                'instance_name': cfg['instance_name'],
                'configured':    True,
                'has_password':  bool(cfg.get('server_password')),
                'config':        cfg,
                'discord_guild_id': cfg.get('discord_guild_id') or '',
                'fluxer_guild_id':  cfg.get('fluxer_guild_id') or '',
                'discord_channels': discord_channels,
                'discord_roles':    discord_roles,
                'fluxer_channels':  fluxer_channels,
                'fluxer_roles':     fluxer_roles,
                # Combined list, still used by pickers that don't care which platform
                # a channel/role came from (each option carries its own 'platform' tag).
                'channels': discord_channels + fluxer_channels,
                'roles':    discord_roles + fluxer_roles,
            })
        else:
            unconfigured_bots.append({
                'instance_name': cfg['instance_name'],
                'game':          game_type,
                'icon':          icon,
                'color':         color,
            })

    for bot in bots:
        bot['config_json']   = json.dumps(bot['config'], default=str)
        bot['channels_json'] = json.dumps(bot['channels'])
        bot['roles_json']    = json.dumps(bot['roles'])
        bot['discord_channels_json'] = json.dumps(bot['discord_channels'])
        bot['discord_roles_json']    = json.dumps(bot['discord_roles'])
        bot['fluxer_channels_json']  = json.dumps(bot['fluxer_channels'])
        bot['fluxer_roles_json']     = json.dumps(bot['fluxer_roles'])

    if not is_site_admin:
        # Mod: only show instances they currently hold the configured Manager role
        # for - same live check the API endpoints enforce, so what's visible here
        # always matches what they're actually allowed to act on.
        bots = [b for b in bots if _web_user_manages_instance(request.web_user, b['instance_name'])]
        unconfigured_bots = []  # claiming a new instance is an admin-only action

    context = {
        'web_user':          request.web_user,
        'active_page':       'admin',
        'is_site_admin':     is_site_admin,
        'discord_guilds':    discord_guilds,
        'fluxer_guilds':     fluxer_guilds,
        'discord_guilds_json': json.dumps(discord_guilds),
        'fluxer_guilds_json':  json.dumps(fluxer_guilds),
        'bots':              bots,
        'unconfigured_bots': unconfigured_bots,
        'active_bot':        bots[0]['slug'] if bots else None,
    }
    return render(request, 'questlog_web/admin_quest_control.html', context)


@web_admin_required
@require_http_methods(["GET", "POST", "PUT", "DELETE"])
def api_admin_site_activity_games(request, game_id=None):
    """CRUD for SiteActivityGame entries."""
    with get_db_session() as db:
        if request.method == "GET":
            if game_id:
                game = db.query(SiteActivityGame).filter_by(id=game_id).first()
                if not game:
                    return JsonResponse({'error': 'Game not found'}, status=404)
                roles = db.query(SiteActivityGuildRole).filter_by(game_id=game.id).all()
                fluxer_roles = db.query(SiteActivityFluxerRole).filter_by(game_id=game.id).all()
                return JsonResponse({
                    'id': game.id,
                    'game_key': game.game_key,
                    'display_name': game.display_name,
                    'description': game.description,
                    'game_type': game.game_type,
                    'display_on': game.display_on or 'gamesweplay',
                    'amp_instance_id': game.amp_instance_id,
                    'steam_appid': game.steam_appid,
                    'steam_link': game.steam_link,
                    'discord_invite': game.discord_invite,
                    'custom_img': game.custom_img,
                    'link_label': game.link_label,
                    'activity_keywords': json.loads(game.activity_keywords or '[]'),
                    'is_active': game.is_active,
                    'show_on_discover_strip': game.show_on_discover_strip if game.show_on_discover_strip is not None else True,
                    'sort_order': game.sort_order,
                    'roles': [{
                        'id': r.id,
                        'guild_id': str(r.guild_id),
                        'role_id': str(r.role_id),
                        'guild_name': r.guild_name,
                        'role_name': r.role_name,
                    } for r in roles],
                    'fluxer_roles': [{
                        'id': r.id,
                        'guild_id': r.guild_id,
                        'role_id': r.role_id,
                        'guild_name': r.guild_name,
                        'role_name': r.role_name,
                    } for r in fluxer_roles],
                })
            games = db.query(SiteActivityGame).order_by(SiteActivityGame.sort_order).all()
            return JsonResponse({'games': [
                {'id': g.id, 'game_key': g.game_key, 'display_name': g.display_name, 'is_active': g.is_active}
                for g in games
            ]})

        if request.method == "DELETE":
            if not game_id:
                return JsonResponse({'error': 'game_id required'}, status=400)
            game = db.query(SiteActivityGame).filter_by(id=game_id).first()
            if not game:
                return JsonResponse({'error': 'Game not found'}, status=404)
            db.delete(game)
            db.commit()
            log_admin_action(request, 'delete_site_activity_game', target_type='game', target_id=game_id)
            return JsonResponse({'success': True})

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if request.method == "POST":
            if db.query(SiteActivityGame).filter_by(game_key=data.get('game_key', '')).first():
                return JsonResponse({'error': 'Game key already exists'}, status=400)
            game = SiteActivityGame(
                game_key=data['game_key'],
                display_name=data['display_name'],
                description=data.get('description'),
                game_type=data.get('game_type', 'discord'),
                display_on=data.get('display_on', 'gamesweplay'),
                amp_instance_id=data.get('amp_instance_id'),
                steam_appid=data.get('steam_appid'),
                steam_link=data.get('steam_link'),
                discord_invite=data.get('discord_invite'),
                custom_img=data.get('custom_img'),
                link_label=data.get('link_label', 'View Site'),
                activity_keywords=json.dumps(data.get('activity_keywords', [])),
                is_active=data.get('is_active', True),
                show_on_discover_strip=data.get('show_on_discover_strip', True),
                sort_order=data.get('sort_order', 0),
            )
            db.add(game)
            db.flush()

            for mapping in data.get('role_mappings', []):
                if mapping.get('guild_id') and mapping.get('role_id'):
                    db.add(SiteActivityGuildRole(
                        game_id=game.id,
                        guild_id=int(mapping['guild_id']),
                        role_id=int(mapping['role_id']),
                        guild_name=mapping.get('guild_name', ''),
                        role_name=mapping.get('role_name', ''),
                    ))
            for mapping in data.get('fluxer_role_mappings', []):
                if mapping.get('guild_id') and mapping.get('role_id'):
                    db.add(SiteActivityFluxerRole(
                        game_id=game.id,
                        guild_id=str(mapping['guild_id']),
                        role_id=str(mapping['role_id']),
                        guild_name=mapping.get('guild_name', ''),
                        role_name=mapping.get('role_name', ''),
                    ))
            db.commit()
            log_admin_action(request, 'create_site_activity_game', target_type='game', target_id=game.id)
            return JsonResponse({'success': True, 'id': game.id})

        if request.method == "PUT":
            if not game_id:
                return JsonResponse({'error': 'game_id required'}, status=400)
            game = db.query(SiteActivityGame).filter_by(id=game_id).first()
            if not game:
                return JsonResponse({'error': 'Game not found'}, status=404)

            game.game_key = data.get('game_key', game.game_key)
            game.display_name = data.get('display_name', game.display_name)
            game.description = data.get('description', game.description)
            game.game_type = data.get('game_type', game.game_type)
            game.display_on = data.get('display_on', game.display_on or 'gamesweplay')
            game.amp_instance_id = data.get('amp_instance_id', game.amp_instance_id)
            game.steam_appid = data.get('steam_appid', game.steam_appid)
            game.steam_link = data.get('steam_link', game.steam_link)
            game.discord_invite = data.get('discord_invite', game.discord_invite)
            game.custom_img = data.get('custom_img', game.custom_img)
            game.link_label = data.get('link_label', game.link_label)
            game.activity_keywords = json.dumps(data.get('activity_keywords', json.loads(game.activity_keywords or '[]')))
            game.is_active = data.get('is_active', game.is_active)
            if 'show_on_discover_strip' in data:
                game.show_on_discover_strip = data['show_on_discover_strip']
            game.sort_order = data.get('sort_order', game.sort_order)
            game.updated_at = int(time.time())

            # Replace Discord role mappings if provided
            if 'role_mappings' in data:
                db.query(SiteActivityGuildRole).filter_by(game_id=game.id).delete()
                for mapping in data['role_mappings']:
                    if mapping.get('guild_id') and mapping.get('role_id'):
                        db.add(SiteActivityGuildRole(
                            game_id=game.id,
                            guild_id=int(mapping['guild_id']),
                            role_id=int(mapping['role_id']),
                            guild_name=mapping.get('guild_name', ''),
                            role_name=mapping.get('role_name', ''),
                        ))
            # Replace Fluxer role mappings if provided
            if 'fluxer_role_mappings' in data:
                db.query(SiteActivityFluxerRole).filter_by(game_id=game.id).delete()
                for mapping in data['fluxer_role_mappings']:
                    if mapping.get('guild_id') and mapping.get('role_id'):
                        db.add(SiteActivityFluxerRole(
                            game_id=game.id,
                            guild_id=str(mapping['guild_id']),
                            role_id=str(mapping['role_id']),
                            guild_name=mapping.get('guild_name', ''),
                            role_name=mapping.get('role_name', ''),
                        ))
            db.commit()
            log_admin_action(request, 'update_site_activity_game', target_type='game', target_id=game_id)
            return JsonResponse({'success': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@web_admin_required
@require_http_methods(["POST", "DELETE"])
def api_admin_site_activity_roles(request, role_id=None):
    """Add or remove Discord role mappings for a game."""
    with get_db_session() as db:
        if request.method == "POST":
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

            game = db.query(SiteActivityGame).filter_by(id=data.get('game_id')).first()
            if not game:
                return JsonResponse({'error': 'Game not found'}, status=404)

            role = SiteActivityGuildRole(
                game_id=game.id,
                guild_id=int(data['guild_id']),
                role_id=int(data['role_id']),
                guild_name=data.get('guild_name', ''),
                role_name=data.get('role_name', ''),
            )
            db.add(role)
            db.commit()
            return JsonResponse({'success': True, 'id': role.id})

        if request.method == "DELETE":
            if not role_id:
                return JsonResponse({'error': 'role_id required'}, status=400)
            role = db.query(SiteActivityGuildRole).filter_by(id=role_id).first()
            if not role:
                return JsonResponse({'error': 'Role mapping not found'}, status=404)
            db.delete(role)
            db.commit()
            return JsonResponse({'success': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@web_admin_required
@require_http_methods(["POST", "DELETE"])
def api_admin_site_activity_fluxer_roles(request, role_id=None):
    """Add or remove Fluxer role mappings for a game."""
    with get_db_session() as db:
        if request.method == "POST":
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

            game = db.query(SiteActivityGame).filter_by(id=data.get('game_id')).first()
            if not game:
                return JsonResponse({'error': 'Game not found'}, status=404)

            role = SiteActivityFluxerRole(
                game_id=game.id,
                guild_id=str(data['guild_id']),
                role_id=str(data['role_id']),
                guild_name=data.get('guild_name', ''),
                role_name=data.get('role_name', ''),
            )
            db.add(role)
            db.commit()
            return JsonResponse({'success': True, 'id': role.id})

        if request.method == "DELETE":
            if not role_id:
                return JsonResponse({'error': 'role_id required'}, status=400)
            role = db.query(SiteActivityFluxerRole).filter_by(id=role_id).first()
            if not role:
                return JsonResponse({'error': 'Fluxer role mapping not found'}, status=404)
            db.delete(role)
            db.commit()
            return JsonResponse({'success': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@web_admin_required
@require_http_methods(["POST"])
def api_admin_maintenance(request):
    """
    Toggle site-wide maintenance mode.
    ENABLE:  Creates flag file + disables ALL non-admin, non-banned users (blocks all activity).
             Stores which user IDs were affected so we can restore them exactly.
    DISABLE: Removes flag file + re-enables exactly the users we disabled.
    Admin accounts are NEVER touched.
    """
    currently_on = os.path.exists(MAINTENANCE_FLAG)
    now = int(time.time())

    with get_db_session() as db:
        if currently_on:
            # --- DISABLE MAINTENANCE ---
            try:
                os.remove(MAINTENANCE_FLAG)
            except OSError:
                pass

            # Re-enable only the users we specifically disabled
            cfg = db.query(WebSiteConfig).filter_by(key='maintenance_affected_users').first()
            restored = 0
            if cfg and cfg.value:
                affected_ids = json.loads(cfg.value)
                if affected_ids:
                    db.query(WebUser).filter(
                        WebUser.id.in_(affected_ids)
                    ).update({'is_disabled': False}, synchronize_session=False)
                    restored = len(affected_ids)
                db.delete(cfg)
            db.commit()

            enabled = False
            log_admin_action(request, 'maintenance_mode_off', details={'users_restored': restored})
            return JsonResponse({'success': True, 'enabled': False, 'users_restored': restored})

        else:
            # --- ENABLE MAINTENANCE ---
            try:
                with open(MAINTENANCE_FLAG, 'w') as f:
                    f.write(str(now))
            except OSError as e:
                return JsonResponse({'error': f'Could not create flag file: {e}'}, status=500)

            # Disable every non-admin, non-banned user that isn't already disabled
            rows = db.query(WebUser.id).filter(
                WebUser.is_admin == False,
                WebUser.is_banned == False,
                WebUser.is_disabled == False,
            ).all()
            affected_ids = [r[0] for r in rows]

            if affected_ids:
                db.query(WebUser).filter(
                    WebUser.id.in_(affected_ids)
                ).update({'is_disabled': True}, synchronize_session=False)

            # Persist affected IDs so we can restore them exactly
            cfg = db.query(WebSiteConfig).filter_by(key='maintenance_affected_users').first()
            if cfg:
                cfg.value = json.dumps(affected_ids)
                cfg.updated_at = now
            else:
                db.add(WebSiteConfig(
                    key='maintenance_affected_users',
                    value=json.dumps(affected_ids),
                    updated_at=now,
                ))
            db.commit()

            log_admin_action(request, 'maintenance_mode_on', details={'users_disabled': len(affected_ids)})
            return JsonResponse({'success': True, 'enabled': True, 'users_disabled': len(affected_ids)})


@web_mod_required
@require_http_methods(["GET"])
def api_admin_maintenance_status(request):
    """Return current maintenance mode status."""
    return JsonResponse({'enabled': os.path.exists(MAINTENANCE_FLAG)})


@web_admin_required
@require_http_methods(["POST"])
def api_admin_toggle_logins(request):
    """Enable or disable the /ql/login/ page."""
    now = int(time.time())
    with get_db_session() as db:
        cfg = db.query(WebSiteConfig).filter_by(key='logins_disabled').first()
        currently_disabled = cfg and cfg.value == '1'
        new_value = '0' if currently_disabled else '1'
        if cfg:
            cfg.value = new_value
            cfg.updated_at = now
        else:
            db.add(WebSiteConfig(key='logins_disabled', value=new_value, updated_at=now))
        db.commit()
    return JsonResponse({'logins_disabled': new_value == '1'})


@web_mod_required
@require_http_methods(["GET"])
def api_admin_logins_status(request):
    """Return whether logins are currently disabled."""
    with get_db_session() as db:
        cfg = db.query(WebSiteConfig).filter_by(key='logins_disabled').first()
        disabled = bool(cfg and cfg.value == '1')
    return JsonResponse({'logins_disabled': disabled})


# =============================================================================
# ADMIN: FLAIRS
# =============================================================================

@web_admin_required
@require_http_methods(['GET', 'POST'])
def api_admin_flairs(request):
    with get_db_session() as db:
        if request.method == 'GET':
            flairs = db.query(WebFlair).order_by(WebFlair.display_order, WebFlair.id).all()
            return JsonResponse({'flairs': [{
                'id': f.id,
                'name': f.name,
                'emoji': f.emoji or '',
                'description': f.description or '',
                'flair_type': f.flair_type,
                'hp_cost': f.hp_cost,
                'equippable': bool(getattr(f, 'equippable', 1)),
                'enabled': f.enabled,
                'admin_only': bool(getattr(f, 'admin_only', 0)),
                'display_order': f.display_order,
                'created_at': f.created_at,
                'owner_count': db.query(WebUserFlair).filter_by(flair_id=f.id).count(),
            } for f in flairs]})

        # POST - create
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)

        name = (body.get('name') or '').strip()
        if not name:
            return JsonResponse({'error': 'Name is required.'}, status=400)

        now = int(time.time())
        flair = WebFlair(
            name=name[:100],
            emoji=(body.get('emoji') or '')[:20],
            description=(body.get('description') or '')[:300],
            flair_type=body.get('flair_type', 'normal'),
            hp_cost=safe_int(body.get('hp_cost', 0), default=0, min_val=0),
            equippable=1 if body.get('equippable', True) else 0,
            enabled=bool(body.get('enabled', True)),
            admin_only=1 if body.get('admin_only', False) else 0,
            display_order=safe_int(body.get('display_order', 0), default=0),
            created_at=now,
            updated_at=now,
        )
        db.add(flair)
        db.commit()
        log_admin_action(request, 'create_flair', target_id=flair.id, details=f'name={name}')
        return JsonResponse({'success': True, 'flair_id': flair.id})


@web_admin_required
@require_http_methods(['PUT', 'DELETE'])
def api_admin_flair_detail(request, flair_id):
    with get_db_session() as db:
        flair = db.query(WebFlair).filter_by(id=flair_id).first()
        if not flair:
            return JsonResponse({'error': 'Flair not found.'}, status=404)

        if request.method == 'DELETE':
            db.delete(flair)
            db.commit()
            log_admin_action(request, 'delete_flair', target_id=flair_id, details=f'name={flair.name}')
            return JsonResponse({'success': True})

        # PUT - update
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)

        if 'name' in body:
            flair.name = (body['name'] or '').strip()[:100]
        if 'emoji' in body:
            flair.emoji = (body['emoji'] or '')[:20]
        if 'description' in body:
            flair.description = (body['description'] or '')[:300]
        if 'flair_type' in body:
            flair.flair_type = body['flair_type']
        if 'hp_cost' in body:
            flair.hp_cost = max(0, int(body['hp_cost']))
        if 'equippable' in body:
            flair.equippable = 1 if body['equippable'] else 0
        if 'enabled' in body:
            flair.enabled = bool(body['enabled'])
        if 'admin_only' in body:
            flair.admin_only = 1 if body['admin_only'] else 0
        if 'display_order' in body:
            flair.display_order = int(body['display_order'])
        flair.updated_at = int(time.time())
        db.commit()
        log_admin_action(request, 'update_flair', target_id=flair_id, details=f'name={flair.name}')
        return JsonResponse({'success': True})


# =============================================================================
# ADMIN: RANK TITLES
# =============================================================================

@web_admin_required
@require_http_methods(['GET', 'POST'])
def api_admin_rank_titles(request):
    with get_db_session() as db:
        if request.method == 'GET':
            titles = db.query(WebRankTitle).order_by(WebRankTitle.level).all()
            return JsonResponse({'rank_titles': [{
                'id': t.id,
                'level': t.level,
                'title': t.title,
                'icon': t.icon or '',
            } for t in titles]})

        # POST - create
        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)

        level = safe_int(body.get('level', 0), default=0)
        title = (body.get('title') or '').strip()
        if not level or not title:
            return JsonResponse({'error': 'Level and title are required.'}, status=400)

        now = int(time.time())
        rt = WebRankTitle(
            level=level,
            title=title[:100],
            icon=(body.get('icon') or '')[:50],
            created_at=now,
            updated_at=now,
        )
        try:
            db.add(rt)
            db.commit()
        except Exception:
            return JsonResponse({'error': 'Level already has a rank title.'}, status=400)
        log_admin_action(request, 'create_rank_title', target_id=rt.id, details=f'level={level} title={title}')
        return JsonResponse({'success': True, 'rank_title_id': rt.id})


@web_admin_required
@require_http_methods(['PUT', 'DELETE'])
def api_admin_rank_title_detail(request, title_id):
    with get_db_session() as db:
        rt = db.query(WebRankTitle).filter_by(id=title_id).first()
        if not rt:
            return JsonResponse({'error': 'Rank title not found.'}, status=404)

        if request.method == 'DELETE':
            db.delete(rt)
            db.commit()
            log_admin_action(request, 'delete_rank_title', target_id=title_id, details=f'level={rt.level}')
            return JsonResponse({'success': True})

        try:
            body = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON.'}, status=400)

        if 'title' in body:
            rt.title = (body['title'] or '').strip()[:100]
        if 'icon' in body:
            rt.icon = (body['icon'] or '')[:50]
        if 'level' in body:
            rt.level = int(body['level'])
        rt.updated_at = int(time.time())
        db.commit()
        log_admin_action(request, 'update_rank_title', target_id=title_id, details=f'level={rt.level} title={rt.title}')
        return JsonResponse({'success': True})


# =============================================================================
# ADMIN: XP LEADERBOARD
# =============================================================================

@web_admin_required
@require_http_methods(['GET'])
def api_admin_xp_leaderboard(request):
    """Top 50 users by XP."""
    with get_db_session() as db:
        users = (
            db.query(WebUser)
            .filter(WebUser.is_banned == False)
            .order_by(WebUser.web_xp.desc())
            .limit(50)
            .all()
        )
        return JsonResponse({'leaderboard': [{
            'id': u.id,
            'username': u.username,
            'display_name': u.display_name or u.username,
            'avatar_url': u.avatar_url or u.steam_avatar,
            'web_xp': u.web_xp or 0,
            'web_level': u.web_level or 1,
            'hero_points': u.hero_points or 0,
        } for u in users]})


# =============================================================================
# ADMIN: STEAM GAME SEARCH (proxy - avoids browser CORS)
# =============================================================================

@web_admin_required
@require_http_methods(['GET'])
def api_admin_steam_game_search(request):
    """
    Proxy Steam store search for the poll option autocomplete.
    Returns top 5 results: {appid, name, header_url, tiny_image}.
    """
    query = (request.GET.get('q') or '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'results': []})
    try:
        resp = _requests.get(
            'https://store.steampowered.com/api/storesearch/',
            params={'term': query, 'cc': 'US', 'l': 'english'},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get('items', [])[:5]
        results = []
        for item in items:
            appid = str(item.get('id', ''))
            results.append({
                'appid': appid,
                'name': item.get('name', ''),
                'tiny_image': item.get('tiny_image', ''),
                'header_url': f'https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg' if appid else '',
            })
        return JsonResponse({'results': results})
    except Exception as e:
        logger.warning('api_admin_steam_game_search: %s', e)
        return JsonResponse({'results': []})


# =============================================================================
# ADMIN: SERVER ROTATION POLLS
# =============================================================================

def _serialize_poll(poll, options, total_votes=None):
    if total_votes is None:
        total_votes = sum(o.vote_count for o in options)
    return {
        'id': poll.id,
        'title': poll.title,
        'description': poll.description,
        'is_active': poll.is_active,
        'is_ended': poll.is_ended,
        'show_results_before_end': poll.show_results_before_end,
        'ends_at': poll.ends_at,
        'winner_option_id': poll.winner_option_id,
        'created_at': poll.created_at,
        'total_votes': total_votes,
        'options': [
            {
                'id': o.id,
                'game_name': o.game_name,
                'description': o.description,
                'image_url': o.image_url,
                'steam_appid': o.steam_appid,
                'sort_order': o.sort_order,
                'vote_count': o.vote_count,
            }
            for o in sorted(options, key=lambda x: (x.sort_order, x.id))
        ],
    }


@web_admin_required
@require_http_methods(['GET', 'POST'])
def api_admin_server_polls(request):
    """List all polls (GET) or create a new poll (POST)."""
    with get_db_session() as db:
        if request.method == 'GET':
            polls = (
                db.query(WebServerPoll)
                .order_by(WebServerPoll.created_at.desc())
                .all()
            )
            result = []
            for p in polls:
                opts = db.query(WebServerPollOption).filter_by(poll_id=p.id).all()
                result.append(_serialize_poll(p, opts))
            return JsonResponse({'polls': result})

        # POST - create
        try:
            data = json.loads(request.body)
        except (ValueError, KeyError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        title = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'error': 'title required'}, status=400)

        now = int(time.time())
        poll = WebServerPoll(
            title=title,
            description=(data.get('description') or '').strip() or None,
            is_active=bool(data.get('is_active', False)),
            is_ended=False,
            show_results_before_end=bool(data.get('show_results_before_end', True)),
            ends_at=data.get('ends_at') or None,
            created_by_id=request.web_user.id,
            created_at=now,
            updated_at=now,
        )
        # Only one active poll at a time
        if poll.is_active:
            db.query(WebServerPoll).filter_by(is_active=True).update({'is_active': False})
        db.add(poll)
        db.flush()

        # Seed options from payload
        for i, opt in enumerate(data.get('options', [])):
            game_name = (opt.get('game_name') or '').strip()
            if not game_name:
                continue
            db.add(WebServerPollOption(
                poll_id=poll.id,
                game_name=game_name,
                description=(opt.get('description') or '').strip() or None,
                image_url=validate_admin_image_url(opt.get('image_url')),
                steam_appid=(opt.get('steam_appid') or '').strip() or None,
                sort_order=i,
                vote_count=0,
                created_at=now,
            ))
        db.commit()
        db.refresh(poll)
        opts = db.query(WebServerPollOption).filter_by(poll_id=poll.id).all()
        log_admin_action(request, 'create_server_poll', 'server_poll', poll.id,
                         {'title': title})
        return JsonResponse({'success': True, 'poll': _serialize_poll(poll, opts)}, status=201)


@web_mod_required
@require_http_methods(['GET', 'PUT', 'DELETE'])
def api_admin_server_poll_detail(request, poll_id):
    """Get, update, or delete a specific poll."""
    with get_db_session() as db:
        poll = db.query(WebServerPoll).filter_by(id=poll_id).first()
        if not poll:
            return JsonResponse({'error': 'Not found'}, status=404)
        opts = db.query(WebServerPollOption).filter_by(poll_id=poll_id).all()

        if request.method == 'GET':
            return JsonResponse({'poll': _serialize_poll(poll, opts)})

        if request.method == 'DELETE':
            db.delete(poll)
            db.commit()
            log_admin_action(request, 'delete_server_poll', 'server_poll', poll_id, {})
            return JsonResponse({'success': True})

        # PUT - update
        try:
            data = json.loads(request.body)
        except (ValueError, KeyError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'title' in data:
            poll.title = (data['title'] or '').strip() or poll.title
        if 'description' in data:
            poll.description = (data['description'] or '').strip() or None
        if 'show_results_before_end' in data:
            poll.show_results_before_end = bool(data['show_results_before_end'])
        if 'ends_at' in data:
            poll.ends_at = data['ends_at'] or None
        if 'is_active' in data:
            new_active = bool(data['is_active'])
            if new_active and not poll.is_active:
                # Deactivate all others first
                db.query(WebServerPoll).filter(
                    WebServerPoll.id != poll_id,
                    WebServerPoll.is_active == True,
                ).update({'is_active': False})
            poll.is_active = new_active
        if 'is_ended' in data:
            poll.is_ended = bool(data['is_ended'])
            if poll.is_ended:
                poll.is_active = False
        poll.updated_at = int(time.time())
        db.commit()
        db.refresh(poll)
        opts = db.query(WebServerPollOption).filter_by(poll_id=poll_id).all()
        log_admin_action(request, 'update_server_poll', 'server_poll', poll_id, {'title': poll.title})
        return JsonResponse({'success': True, 'poll': _serialize_poll(poll, opts)})


@web_mod_required
@require_http_methods(['POST'])
def api_admin_server_poll_option(request, poll_id):
    """Add an option to a poll."""
    with get_db_session() as db:
        poll = db.query(WebServerPoll).filter_by(id=poll_id).first()
        if not poll:
            return JsonResponse({'error': 'Poll not found'}, status=404)
        try:
            data = json.loads(request.body)
        except (ValueError, KeyError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        game_name = (data.get('game_name') or '').strip()
        if not game_name:
            return JsonResponse({'error': 'game_name required'}, status=400)
        max_order = db.query(WebServerPollOption).filter_by(poll_id=poll_id).count()
        opt = WebServerPollOption(
            poll_id=poll_id,
            game_name=game_name,
            description=(data.get('description') or '').strip() or None,
            image_url=validate_admin_image_url(data.get('image_url')),
            steam_appid=(data.get('steam_appid') or '').strip() or None,
            sort_order=max_order,
            vote_count=0,
            created_at=int(time.time()),
        )
        db.add(opt)
        poll.updated_at = int(time.time())
        db.commit()
        db.refresh(opt)
        return JsonResponse({'success': True, 'option': {
            'id': opt.id,
            'game_name': opt.game_name,
            'description': opt.description,
            'image_url': opt.image_url,
            'steam_appid': opt.steam_appid,
            'sort_order': opt.sort_order,
            'vote_count': opt.vote_count,
        }})


@web_mod_required
@require_http_methods(['DELETE'])
def api_admin_server_poll_option_detail(request, poll_id, option_id):
    """Remove an option from a poll."""
    with get_db_session() as db:
        opt = db.query(WebServerPollOption).filter_by(id=option_id, poll_id=poll_id).first()
        if not opt:
            return JsonResponse({'error': 'Not found'}, status=404)
        db.delete(opt)
        db.commit()
        return JsonResponse({'success': True})


@web_mod_required
@require_http_methods(['POST'])
def api_admin_server_poll_declare_winner(request, poll_id):
    """Declare a winner and close the poll."""
    with get_db_session() as db:
        poll = db.query(WebServerPoll).filter_by(id=poll_id).first()
        if not poll:
            return JsonResponse({'error': 'Poll not found'}, status=404)
        try:
            data = json.loads(request.body)
            option_id = int(data.get('option_id', 0))
        except (ValueError, KeyError, TypeError):
            return JsonResponse({'error': 'option_id required'}, status=400)
        opt = db.query(WebServerPollOption).filter_by(id=option_id, poll_id=poll_id).first()
        if not opt:
            return JsonResponse({'error': 'Invalid option'}, status=400)
        poll.winner_option_id = option_id
        poll.is_ended = True
        poll.is_active = False
        poll.updated_at = int(time.time())
        db.commit()
        log_admin_action(request, 'declare_poll_winner', 'server_poll', poll_id,
                         {'winner': opt.game_name})
        return JsonResponse({'success': True, 'winner': opt.game_name})


# =============================================================================
# ADMIN GIVEAWAY API
# =============================================================================

def _giveaway_dict(g, db, include_entries=False):
    winner_user = db.query(WebUser).filter_by(id=g.winner_user_id).first() if g.winner_user_id else None
    winner = serialize_user_brief(winner_user) if winner_user else None
    # Parse all winners from winners_json
    winners = []
    if g.winners_json:
        try:
            winner_ids = json.loads(g.winners_json)
            from app.questlog_web.models import WebUser as _WU
            for wid in winner_ids:
                wu = db.query(_WU).filter_by(id=wid).first()
                if wu:
                    winners.append(serialize_user_brief(wu))
        except Exception:
            pass
    data = {
        'id': g.id,
        'title': g.title,
        'description': g.description,
        'prize': g.prize,
        'image_url': g.image_url,
        'status': g.status,
        'ends_at': g.ends_at,
        'entry_count': g.entry_count,
        'max_winners': g.max_winners or 1,
        'max_entries_per_user': g.max_entries_per_user or 1,
        'hp_per_extra_ticket': g.hp_per_extra_ticket or 0,
        'winner': winner,
        'winners': winners,
        'created_at': g.created_at,
        'launched_at': g.launched_at,
        'closed_at': g.closed_at,
    }
    if include_entries:
        entries = db.query(WebGiveawayEntry).filter_by(giveaway_id=g.id).all()
        data['entries'] = [{'id': e.id, 'user': serialize_user_brief(e.user), 'entered_at': e.entered_at, 'ticket_count': e.ticket_count or 1} for e in entries]
    return data


@web_mod_required
@require_http_methods(['GET', 'POST'])
def api_admin_giveaways(request):
    """GET: list all giveaways. POST: create a new draft giveaway."""
    with get_db_session() as db:
        if request.method == 'GET':
            giveaways = db.query(WebGiveaway).order_by(WebGiveaway.created_at.desc()).all()
            return JsonResponse({'giveaways': [_giveaway_dict(g, db) for g in giveaways]})

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        title = (data.get('title') or '').strip()[:200]
        prize = (data.get('prize') or '').strip()[:500]
        if not title or not prize:
            return JsonResponse({'error': 'title and prize are required'}, status=400)

        now = int(time.time())
        g = WebGiveaway(
            title=title,
            description=(data.get('description') or '').strip()[:2000] or None,
            prize=prize,
            image_url=validate_admin_image_url(data.get('image_url')),
            status='draft',
            ends_at=safe_int(data.get('ends_at'), default=None) if data.get('ends_at') else None,
            entry_count=0,
            max_winners=safe_int(data.get('max_winners') or 1, default=1, min_val=1, max_val=100),
            max_entries_per_user=safe_int(data.get('max_entries_per_user') or 1, default=1, min_val=1, max_val=100),
            hp_per_extra_ticket=safe_int(data.get('hp_per_extra_ticket') or 0, default=0, min_val=0),
            created_by_id=request.web_user.id,
            created_at=now,
            updated_at=now,
        )
        db.add(g)
        db.flush()
        db.commit()
        log_admin_action(request, 'create_giveaway', 'giveaway', g.id, {'title': title})
        return JsonResponse({'success': True, 'giveaway': _giveaway_dict(g, db)}, status=201)


@web_mod_required
@require_http_methods(['GET', 'PUT', 'DELETE'])
def api_admin_giveaway_detail(request, giveaway_id):
    """GET: detail with entries. PUT: edit draft. DELETE: remove draft."""
    with get_db_session() as db:
        g = db.query(WebGiveaway).filter_by(id=giveaway_id).first()
        if not g:
            return JsonResponse({'error': 'Giveaway not found'}, status=404)

        if request.method == 'GET':
            return JsonResponse({'giveaway': _giveaway_dict(g, db, include_entries=True)})

        if request.method == 'DELETE':
            if g.status == 'active':
                return JsonResponse({'error': 'Cannot delete an active giveaway. Close it first.'}, status=400)
            db.delete(g)
            db.commit()
            log_admin_action(request, 'delete_giveaway', 'giveaway', giveaway_id, {})
            return JsonResponse({'success': True})

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if g.status not in ('draft',):
            return JsonResponse({'error': 'Only draft giveaways can be edited'}, status=400)
        if 'title' in data:
            g.title = (data['title'] or '').strip()[:200]
        if 'prize' in data:
            g.prize = (data['prize'] or '').strip()[:500]
        if 'description' in data:
            g.description = (data['description'] or '').strip()[:2000] or None
        if 'image_url' in data:
            g.image_url = validate_admin_image_url(data['image_url'])
        if 'ends_at' in data:
            g.ends_at = safe_int(data['ends_at'], default=None) if data['ends_at'] else None
        if 'max_winners' in data:
            g.max_winners = safe_int(data['max_winners'] or 1, default=1, min_val=1, max_val=100)
        if 'max_entries_per_user' in data:
            g.max_entries_per_user = safe_int(data['max_entries_per_user'] or 1, default=1, min_val=1, max_val=100)
        if 'hp_per_extra_ticket' in data:
            g.hp_per_extra_ticket = safe_int(data['hp_per_extra_ticket'] or 0, default=0, min_val=0)
        g.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'success': True, 'giveaway': _giveaway_dict(g, db)})


@web_mod_required
@require_http_methods(['POST'])
def api_admin_giveaway_launch(request, giveaway_id):
    """Launch a giveaway: set active, send global notification to all users."""
    with get_db_session() as db:
        g = db.query(WebGiveaway).filter_by(id=giveaway_id).first()
        if not g:
            return JsonResponse({'error': 'Giveaway not found'}, status=404)
        if g.status != 'draft':
            return JsonResponse({'error': 'Only draft giveaways can be launched'}, status=400)

        now = int(time.time())
        g.status = 'active'
        g.launched_at = now
        g.updated_at = now
        db.flush()

        # Send notification to all active, non-banned users
        users = db.query(WebUser).filter(
            WebUser.is_banned == False,
            WebUser.email_verified == True,
        ).all()
        notif_count = 0
        for u in users:
            try:
                create_notification(
                    db,
                    user_id=u.id,
                    actor_id=request.web_user.id,
                    notification_type='giveaway',
                    target_type='giveaway',
                    target_id=g.id,
                    message=f'New Giveaway: {g.title} - Enter now for a chance to win!',
                    skip_self=False,  # admin who launched it gets notified too
                )
                notif_count += 1
            except Exception:
                pass

        db.commit()
        log_admin_action(request, 'launch_giveaway', 'giveaway', giveaway_id,
                         {'title': g.title, 'notified': notif_count})

        # Notify Fluxer channel
        _fluxer_giveaway_start(
            title=g.title,
            prize=g.prize or '',
            giveaway_url="https://casual-heroes.com/ql/giveaways/",
        )
        return JsonResponse({'success': True, 'notified': notif_count, 'giveaway': _giveaway_dict(g, db)})


@web_mod_required
@require_http_methods(['POST'])
def api_admin_giveaway_close(request, giveaway_id):
    """Close entries for an active giveaway."""
    with get_db_session() as db:
        g = db.query(WebGiveaway).filter_by(id=giveaway_id).first()
        if not g:
            return JsonResponse({'error': 'Giveaway not found'}, status=404)
        if g.status != 'active':
            return JsonResponse({'error': 'Only active giveaways can be closed'}, status=400)
        now = int(time.time())
        g.status = 'closed'
        g.closed_at = now
        g.updated_at = now
        db.commit()
        log_admin_action(request, 'close_giveaway', 'giveaway', giveaway_id, {})
        return JsonResponse({'success': True, 'giveaway': _giveaway_dict(g, db)})


@web_mod_required
@require_http_methods(['POST'])
def api_admin_giveaway_pick_winner(request, giveaway_id):
    """Randomly pick winner(s) from entries, weighted by ticket_count."""
    import secrets
    _srng = secrets.SystemRandom()  # cryptographically secure RNG
    with get_db_session() as db:
        g = db.query(WebGiveaway).filter_by(id=giveaway_id).first()
        if not g:
            return JsonResponse({'error': 'Giveaway not found'}, status=404)
        if g.status not in ('active', 'closed'):
            return JsonResponse({'error': 'Giveaway must be active or closed to pick a winner'}, status=400)

        entries = db.query(WebGiveawayEntry).filter_by(giveaway_id=giveaway_id).all()
        if not entries:
            return JsonResponse({'error': 'No entries to pick from'}, status=400)

        # Weighted selection without replacement
        max_w = max(1, g.max_winners or 1)
        remaining = list(entries)
        weights = [max(1, e.ticket_count or 1) for e in remaining]
        winners = []
        while remaining and len(winners) < max_w:
            chosen = _srng.choices(remaining, weights=weights, k=1)[0]
            idx = remaining.index(chosen)
            winners.append(chosen)
            remaining.pop(idx)
            weights.pop(idx)

        now = int(time.time())
        g.winner_user_id = winners[0].user_id
        g.winners_json = json.dumps([w.user_id for w in winners])
        g.status = 'winner_selected'
        g.closed_at = g.closed_at or now
        g.updated_at = now
        db.flush()

        # Notify all winners
        for w_entry in winners:
            winner_user = db.query(WebUser).filter_by(id=w_entry.user_id).first()
            if winner_user:
                create_notification(
                    db,
                    user_id=winner_user.id,
                    actor_id=request.web_user.id,
                    notification_type='giveaway_win',
                    target_type='giveaway',
                    target_id=g.id,
                    message=f'You won the {g.title} giveaway! Prize: {g.prize}',
                )

        # Collect winner usernames before session closes
        winner_usernames = []
        for w_entry in winners:
            wu = db.query(WebUser).filter_by(id=w_entry.user_id).first()
            if wu:
                winner_usernames.append(wu.username)

        db.commit()
        log_admin_action(request, 'pick_giveaway_winner', 'giveaway', giveaway_id,
                         {'winner_ids': [w.user_id for w in winners]})

        # Notify Fluxer channel
        if winner_usernames:
            _fluxer_giveaway_winner(
                title=g.title,
                winner_names=winner_usernames,
                giveaway_url="https://casual-heroes.com/ql/giveaways/",
            )
        return JsonResponse({'success': True, 'giveaway': _giveaway_dict(g, db, include_entries=False)})


# =============================================================================
# FLUXER WEBHOOK CONFIGURATION
# =============================================================================

def _fluxer_config_dict(cfg: WebFluxerWebhookConfig) -> dict:
    return {
        'id': cfg.id,
        'event_type': cfg.event_type,
        'label': cfg.label,
        'is_enabled': cfg.is_enabled,
        'guild_id': cfg.guild_id or '',
        'channel_id': cfg.channel_id or '',
        'channel_name': cfg.channel_name or '',
        'discord_webhook_url': cfg.discord_webhook_url or '',
        'embed_color': cfg.embed_color or '',
        'message_template': cfg.message_template or '',
        'embed_title': cfg.embed_title or '',
        'embed_footer': cfg.embed_footer or '',
        'mention_role_id': cfg.mention_role_id or '',
        'updated_at': cfg.updated_at,
    }


@web_admin_required
@require_http_methods(['GET'])
def api_admin_fluxer_webhooks(request):
    """List all Fluxer webhook configs."""
    with get_db_session() as db:
        configs = db.query(WebFluxerWebhookConfig).order_by(WebFluxerWebhookConfig.id).all()
        return JsonResponse({'configs': [_fluxer_config_dict(c) for c in configs]})


@web_admin_required
@require_http_methods(['GET'])
def api_admin_fluxer_guilds(request):
    """
    List Fluxer guilds the bot has synced channels for.
    For any guild where guild_name is blank, fetches from the Fluxer API and caches it.
    """
    import requests as _req
    from django.conf import settings as _settings
    from sqlalchemy import text as sa_text

    bot_token  = getattr(_settings, 'FLUXER_BOT_TOKEN', '')
    api_base   = getattr(_settings, 'FLUXER_API_BASE', 'https://api.fluxer.app')
    api_ver    = getattr(_settings, 'FLUXER_API_VERSION', '1')

    with get_db_session() as db:
        rows = db.execute(sa_text("""
            SELECT guild_id,
                   COALESCE(NULLIF(MAX(guild_name), ''), '') AS guild_name
            FROM web_fluxer_guild_channels
            GROUP BY guild_id
        """)).fetchall()

        guilds = []
        needs_cache = []   # guild_ids where name is missing

        for r in rows:
            if r.guild_name:
                guilds.append({'id': r.guild_id, 'name': r.guild_name})
            else:
                needs_cache.append(r.guild_id)

        # Fetch missing names from the Fluxer API and update DB cache
        if needs_cache and bot_token:
            headers = {'Authorization': f'Bot {bot_token}'}
            for guild_id in needs_cache:
                name = guild_id   # fallback to ID
                try:
                    resp = _req.get(
                        f'{api_base}/v{api_ver}/guilds/{guild_id}',
                        headers=headers,
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        name = resp.json().get('name') or guild_id
                        db.execute(sa_text(
                            "UPDATE web_fluxer_guild_channels "
                            "SET guild_name = :name WHERE guild_id = :gid"
                        ), {'name': name, 'gid': guild_id})
                except Exception as _e:
                    logger.warning(f'api_admin_fluxer_guilds: Fluxer API failed for {guild_id}: {_e}')
                guilds.append({'id': guild_id, 'name': name})
            db.commit()
        elif needs_cache:
            # No token - fall back to showing ID
            guilds.extend({'id': gid, 'name': gid} for gid in needs_cache)

    guilds.sort(key=lambda g: g['name'].lower())
    return JsonResponse({'guilds': guilds})


@web_admin_required
@require_http_methods(['PUT'])
def api_admin_fluxer_webhook_detail(request, config_id):
    """Update a Fluxer notification config (channel, color, enabled)."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    guild_id            = data.get('guild_id', '').strip()[:32]
    channel_id          = data.get('channel_id', '').strip()[:32]
    channel_name        = data.get('channel_name', '').strip()[:200]
    discord_webhook_url = (data.get('discord_webhook_url') or '').strip()[:1000]
    embed_color         = data.get('embed_color', '').strip()[:7]
    message_template    = (data.get('message_template') or '').strip()[:4000]
    embed_title         = (data.get('embed_title') or '').strip()[:255]
    embed_footer        = (data.get('embed_footer') or '').strip()[:255]
    mention_role_id     = (data.get('mention_role_id') or '').strip()[:32]
    is_enabled          = bool(data.get('is_enabled', False))

    if embed_color and not (embed_color.startswith('#') and len(embed_color) == 7):
        return JsonResponse({'error': 'embed_color must be #RRGGBB format'}, status=400)
    if discord_webhook_url and not discord_webhook_url.startswith('https://discord.com/api/webhooks/'):
        return JsonResponse({'error': 'discord_webhook_url must be a Discord webhook URL'}, status=400)

    with get_db_session() as db:
        cfg = db.query(WebFluxerWebhookConfig).filter_by(id=config_id).first()
        if not cfg:
            return JsonResponse({'error': 'Config not found'}, status=404)

        cfg.guild_id            = guild_id or cfg.guild_id
        cfg.channel_id          = channel_id or cfg.channel_id
        cfg.channel_name        = channel_name or cfg.channel_name
        cfg.discord_webhook_url = discord_webhook_url or cfg.discord_webhook_url
        cfg.embed_color         = embed_color or cfg.embed_color
        cfg.message_template    = message_template or cfg.message_template
        cfg.embed_title         = embed_title or cfg.embed_title
        cfg.embed_footer        = embed_footer or cfg.embed_footer
        cfg.mention_role_id     = mention_role_id or None
        cfg.is_enabled          = is_enabled and bool(cfg.channel_id)
        cfg.updated_at          = int(time.time())
        db.commit()

        log_admin_action(request, 'update_fluxer_webhook', 'fluxer_webhook', config_id,
                         {'event_type': cfg.event_type, 'is_enabled': cfg.is_enabled})
        return JsonResponse({'success': True, 'config': _fluxer_config_dict(cfg)})


@web_admin_required
@require_http_methods(['POST'])
def api_admin_fluxer_webhook_test(request, config_id):
    """Queue a test embed for the bot to send to the configured channel."""
    with get_db_session() as db:
        cfg = db.query(WebFluxerWebhookConfig).filter_by(id=config_id).first()
        if not cfg:
            return JsonResponse({'error': 'Config not found'}, status=404)
        if not cfg.channel_id:
            return JsonResponse({'error': 'No channel configured'}, status=400)

        from sqlalchemy import text as sa_text
        import json as _json
        from .fluxer_webhooks import _hex_to_int, _format_template

        # Defaults per event type
        _default_colors = {
            'lfg_announce': 0xFF7043,
            'new_post':     0x5865F2,
            'new_member':   0x57F287,
            'giveaway_start':  0xEB459E,
            'giveaway_winner': 0xFEE75C,
            'go_live':         0xF43F5E,
        }
        _default_titles = {
            'lfg_announce':    'New LFG: Test Group',
            'new_post':        'TestUser posted on QuestLog',
            'new_member':      cfg.embed_title or 'New Member Joined QuestLog!',
            'giveaway_start':  'Giveaway Started: Test Prize',
            'giveaway_winner': 'Giveaway Ended: Test Prize',
            'go_live':         '\U0001f534 TestUser is live on Twitch!',
        }
        _default_descriptions = {
            'lfg_announce':    'A new group is looking for players!\n\n*This is a test LFG announcement.*',
            'new_post':        'Check out this awesome post about gaming!\n\n*This is a test post notification.*',
            'new_member':      None,  # built from message_template below
            'giveaway_start':  '**Prize:** Test Game Key\n\n[Enter the Giveaway](https://casual-heroes.com/ql/giveaways/)',
            'giveaway_winner': 'Congratulations to **TestWinner**!\n\n[View Giveaway](https://casual-heroes.com/ql/giveaways/)',
            'go_live':         '**Test Stream Title**\n\n[Watch Stream](https://www.twitch.tv/testuser) | [QuestLog Profile](https://casual-heroes.com/ql/u/testuser/)',
        }
        _default_fields = {
            'lfg_announce': [
                {"name": "Game",       "value": "Test Game",  "inline": True},
                {"name": "Group Size", "value": "1/5",        "inline": True},
                {"name": "Scheduled",  "value": "Tonight 8pm","inline": True},
            ],
        }

        admin_username = request.web_user.username if hasattr(request, 'web_user') else 'Admin'

        # Build description - use configured template for new_member
        if cfg.event_type == 'new_member' and cfg.message_template:
            description = _format_template(
                cfg.message_template,
                username=admin_username,
                profile=f'https://casual-heroes.com/ql/u/{admin_username}/',
            )
        else:
            description = _default_descriptions.get(cfg.event_type, '*Test notification.*')

        embed = {
            "title": _default_titles.get(cfg.event_type, f'Test - {cfg.label}'),
            "description": description,
            "color": _hex_to_int(cfg.embed_color, _default_colors.get(cfg.event_type, 0x5865F2)),
            "footer": cfg.embed_footer or f"QuestLog - https://questlog.casual-heroes.com",
        }
        if cfg.event_type in _default_fields:
            embed["fields"] = _default_fields[cfg.event_type]
        if cfg.event_type == 'lfg_announce':
            embed["url"] = "https://questlog.casual-heroes.com"

        test_payload = _json.dumps(embed)

        db.execute(sa_text("""
            INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at)
            VALUES (:guild_id, :channel_id, :payload, :now)
        """), {
            'guild_id': int(cfg.guild_id) if cfg.guild_id else 0,
            'channel_id': int(cfg.channel_id),
            'payload': test_payload,
            'now': int(time.time()),
        })
        db.commit()

        log_admin_action(request, 'test_fluxer_webhook', 'fluxer_webhook', config_id,
                         {'event_type': cfg.event_type})
        return JsonResponse({'success': True, 'message': 'Test embed queued - bot will post it within 5 seconds.'})


# =============================================================================
# BROADCAST USERS
# =============================================================================

@web_admin_required
@require_http_methods(['GET', 'POST'])
def api_admin_broadcast_users(request):
    """GET list / POST add a user to the broadcast list."""
    if request.method == 'GET':
        with get_db_session() as db:
            rows = db.query(WebBroadcastUser).order_by(WebBroadcastUser.added_at.desc()).all()
            result = []
            for r in rows:
                user = db.query(WebUser).filter_by(id=r.user_id).first()
                result.append({
                    'id': r.id,
                    'user_id': r.user_id,
                    'username': user.username if user else f'#{r.user_id}',
                    'avatar_url': user.avatar_url if user else '',
                    'added_at': r.added_at,
                })
        return JsonResponse({'users': result})

    # POST - add user by username
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    username = (data.get('username') or '').strip()
    if not username:
        return JsonResponse({'error': 'username required'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter(WebUser.username.ilike(username)).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        existing = db.query(WebBroadcastUser).filter_by(user_id=user.id).first()
        if existing:
            return JsonResponse({'error': 'User already in broadcast list'}, status=409)
        bu = WebBroadcastUser(user_id=user.id, added_at=int(time.time()))
        db.add(bu)
        db.commit()
        log_admin_action(request, 'add_broadcast_user', 'broadcast_user', user.id, {'username': user.username})
        return JsonResponse({'success': True, 'user_id': user.id, 'username': user.username})


@web_admin_required
@require_http_methods(['DELETE'])
def api_admin_broadcast_user_detail(request, user_id):
    """DELETE remove a user from the broadcast list."""
    with get_db_session() as db:
        bu = db.query(WebBroadcastUser).filter_by(user_id=user_id).first()
        if not bu:
            return JsonResponse({'error': 'Not found'}, status=404)
        db.delete(bu)
        db.commit()
        log_admin_action(request, 'remove_broadcast_user', 'broadcast_user', user_id, {})
    return JsonResponse({'success': True})


def _subscriber_dict(cfg: WebCommunityBotConfig) -> dict:
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
        'created_at': cfg.created_at,
        'updated_at': cfg.updated_at,
    }


@web_admin_required
@require_http_methods(['GET', 'POST'])
def api_admin_fluxer_subscribers(request):
    """
    GET  - list all community bot configs with aggregate stats
    POST - manually create a new subscriber config
    """
    from sqlalchemy import text as _text, func

    if request.method == 'GET':
        with get_db_session() as db:
            configs = db.query(WebCommunityBotConfig).order_by(
                WebCommunityBotConfig.updated_at.desc()
            ).all()
            configs_data = [_subscriber_dict(c) for c in configs]

            total_guilds = db.query(func.count(func.distinct(WebCommunityBotConfig.guild_id))).scalar() or 0
            active_count = db.query(func.count(WebCommunityBotConfig.id)).filter_by(is_enabled=True).scalar() or 0

            # Stats from bot tables (best-effort)
            try:
                members_tracked = db.execute(_text(
                    "SELECT COUNT(*) FROM fluxer_member_xp"
                )).scalar() or 0
            except Exception:
                members_tracked = 0
            try:
                lfg_total = db.execute(_text(
                    "SELECT COUNT(*) FROM fluxer_lfg_posts"
                )).scalar() or 0
            except Exception:
                lfg_total = 0

        return JsonResponse({
            'configs': configs_data,
            'stats': {
                'total_guilds': total_guilds,
                'active_subscribers': active_count,
                'members_tracked': members_tracked,
                'lfg_posts_total': lfg_total,
            },
        })

    # POST - create manually
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    platform = data.get('platform', 'fluxer').strip()
    guild_id = data.get('guild_id', '').strip()
    guild_name = data.get('guild_name', '').strip()
    channel_name = data.get('channel_name', '').strip()
    webhook_url = data.get('webhook_url', '').strip()
    event_type = data.get('event_type', 'lfg_announce').strip()

    if not guild_id:
        return JsonResponse({'error': 'guild_id is required'}, status=400)
    if platform not in ('discord', 'fluxer'):
        return JsonResponse({'error': 'Invalid platform'}, status=400)
    if event_type not in ('lfg_announce',):
        return JsonResponse({'error': 'Invalid event_type'}, status=400)
    if webhook_url and not webhook_url.startswith('https://'):
        return JsonResponse({'error': 'Webhook URL must start with https://'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        existing = db.query(WebCommunityBotConfig).filter_by(
            platform=platform, guild_id=guild_id, event_type=event_type
        ).first()
        if existing:
            return JsonResponse({'error': 'Config already exists for this guild/event'}, status=409)

        cfg = WebCommunityBotConfig(
            platform=platform,
            guild_id=guild_id,
            guild_name=guild_name or None,
            channel_name=channel_name or None,
            webhook_url=webhook_url or None,
            event_type=event_type,
            is_enabled=bool(webhook_url),
            created_at=now,
            updated_at=now,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        log_admin_action(request, 'create_fluxer_subscriber', 'fluxer_subscriber', cfg.id,
                         {'guild_id': guild_id, 'event_type': event_type})
        return JsonResponse({'success': True, 'config': _subscriber_dict(cfg)}, status=201)


@web_admin_required
@require_http_methods(['PUT', 'DELETE'])
def api_admin_fluxer_subscriber_detail(request, config_id):
    """PUT to update, DELETE to remove a community bot config."""
    with get_db_session() as db:
        cfg = db.query(WebCommunityBotConfig).filter_by(id=config_id).first()
        if not cfg:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.delete(cfg)
            db.commit()
            log_admin_action(request, 'delete_fluxer_subscriber', 'fluxer_subscriber', config_id, {})
            return JsonResponse({'success': True})

        # PUT
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        webhook_url = data.get('webhook_url', cfg.webhook_url or '')
        if isinstance(webhook_url, str):
            webhook_url = webhook_url.strip()
        if webhook_url and not webhook_url.startswith('https://'):
            return JsonResponse({'error': 'Webhook URL must start with https://'}, status=400)

        cfg.webhook_url = webhook_url or None
        cfg.guild_name = data.get('guild_name', cfg.guild_name)
        cfg.channel_name = data.get('channel_name', cfg.channel_name)
        if 'channel_id' in data and data['channel_id']:
            cfg.channel_id = str(data['channel_id']).strip()
        cfg.is_enabled = bool(data.get('is_enabled', cfg.is_enabled))
        cfg.updated_at = int(time.time())
        db.commit()
        log_admin_action(request, 'update_fluxer_subscriber', 'fluxer_subscriber', config_id,
                         {'is_enabled': cfg.is_enabled})
        return JsonResponse({'success': True, 'config': _subscriber_dict(cfg)})


@web_admin_required
@require_http_methods(['GET'])
def api_admin_fluxer_guild_channels(request, guild_id):
    """GET cached Fluxer text channels for a guild - used by channel picker in admin panel."""
    from sqlalchemy import text as sa_text
    with get_db_session() as db:
        rows = db.execute(
            sa_text(
                "SELECT channel_id, channel_name FROM web_fluxer_guild_channels "
                "WHERE guild_id = :gid ORDER BY channel_name ASC"
            ),
            {"gid": str(guild_id)},
        ).fetchall()
    channels = [{'id': r.channel_id, 'name': r.channel_name} for r in rows]
    return JsonResponse({'channels': channels})


@web_admin_required
@require_http_methods(['GET'])
def api_admin_fluxer_guild_roles(request, guild_id):
    """GET cached Fluxer roles for a guild - used by role picker in admin panel."""
    from sqlalchemy import text as sa_text
    with get_db_session() as db:
        rows = db.execute(
            sa_text(
                "SELECT role_id, role_name FROM web_fluxer_guild_roles "
                "WHERE guild_id = :gid ORDER BY role_name ASC"
            ),
            {"gid": str(guild_id)},
        ).fetchall()
    roles = [{'id': r.role_id, 'name': r.role_name} for r in rows]
    return JsonResponse({'roles': roles})


@web_admin_required
@require_http_methods(['GET'])
def api_admin_fluxer_guild_detail(request, config_id):
    """GET guild-level detail: config info + active LFG posts + member count."""
    with get_db_session() as db:
        cfg = db.query(WebCommunityBotConfig).filter_by(id=config_id).first()
        if not cfg:
            return JsonResponse({'error': 'Not found'}, status=404)

        guild_id = cfg.guild_id
        now_ts = int(time.time())

        # Member count from fluxer_member_xp
        try:
            member_row = db.execute(
                text("SELECT COUNT(DISTINCT user_id) FROM fluxer_member_xp WHERE guild_id = :g"),
                {"g": guild_id},
            ).fetchone()
            member_count = member_row[0] if member_row else 0
        except Exception:
            member_count = 0

        # Top XP earner
        try:
            top_row = db.execute(
                text(
                    "SELECT username, xp FROM fluxer_member_xp "
                    "WHERE guild_id = :g ORDER BY xp DESC LIMIT 1"
                ),
                {"g": guild_id},
            ).fetchone()
            top_member = {'username': top_row[0], 'xp': top_row[1]} if top_row else None
        except Exception:
            top_member = None

        # Active LFG posts for this guild
        try:
            lfg_rows = db.execute(
                text(
                    "SELECT id, username, game, description, group_size, "
                    "voice_platform, created_at, expires_at "
                    "FROM fluxer_lfg_posts "
                    "WHERE guild_id = :g AND is_active = 1 AND expires_at > :now "
                    "ORDER BY created_at DESC LIMIT 10"
                ),
                {"g": guild_id, "now": now_ts},
            ).fetchall()
            lfg_posts = [
                {
                    'id': r[0],
                    'username': r[1],
                    'game': r[2],
                    'description': r[3],
                    'group_size': r[4],
                    'voice_platform': r[5],
                    'created_at': r[6],
                    'expires_at': r[7],
                }
                for r in lfg_rows
            ]
        except Exception:
            lfg_posts = []

        # Total LFG posts ever
        try:
            total_row = db.execute(
                text("SELECT COUNT(*) FROM fluxer_lfg_posts WHERE guild_id = :g"),
                {"g": guild_id},
            ).fetchone()
            total_lfg = total_row[0] if total_row else 0
        except Exception:
            total_lfg = 0

    return JsonResponse({
        'config': _subscriber_dict(cfg),
        'guild_id': guild_id,
        'member_count': member_count,
        'top_member': top_member,
        'active_lfg': lfg_posts,
        'total_lfg_posts': total_lfg,
    })


# =============================================================================
# EARLY ACCESS INVITE CODES
# =============================================================================

import secrets as _secrets

_EAC_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no O/0 or I/1 to avoid confusion


def _gen_invite_code() -> str:
    return ''.join(_secrets.choice(_EAC_ALPHABET) for _ in range(10))


def _eac_dict(code: WebEarlyAccessCode) -> dict:
    return {
        'id': code.id,
        'code': code.code,
        'platform': code.platform or '',
        'notes': code.notes or '',
        'created_at': code.created_at,
        'used_at': code.used_at,
        'used_by_username': code.used_by_user.username if code.used_by_user else None,
        'is_revoked': code.is_revoked,
    }


@web_admin_required
@require_http_methods(['GET', 'POST'])
def api_admin_invite_codes(request):
    """
    GET  - list all invite codes (most recent first)
    POST - generate N new codes  body: {count, platform, notes}
    """
    if request.method == 'GET':
        with get_db_session() as db:
            codes = db.query(WebEarlyAccessCode).order_by(
                WebEarlyAccessCode.created_at.desc()
            ).limit(500).all()
            total = db.query(WebEarlyAccessCode).count()
            used = db.query(WebEarlyAccessCode).filter(
                WebEarlyAccessCode.used_by_user_id != None
            ).count()
            revoked = db.query(WebEarlyAccessCode).filter_by(is_revoked=True).count()
            result = [_eac_dict(c) for c in codes]
        return JsonResponse({
            'codes': result,
            'stats': {'total': total, 'used': used, 'revoked': revoked, 'unused': total - used - revoked},
        })

    # POST - generate codes
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    count = safe_int(data.get('count', 1), default=1, min_val=1, max_val=100)
    platform = (data.get('platform') or '').strip()[:20] or None
    notes = (data.get('notes') or '').strip()[:200] or None
    now = int(time.time())

    created = []
    with get_db_session() as db:
        for _ in range(count):
            # Retry until unique
            for _attempt in range(10):
                code_str = _gen_invite_code()
                if not db.query(WebEarlyAccessCode).filter_by(code=code_str).first():
                    break
            obj = WebEarlyAccessCode(
                code=code_str,
                platform=platform,
                notes=notes,
                created_at=now,
            )
            db.add(obj)
            db.commit()
            db.refresh(obj)
            created.append(_eac_dict(obj))

    log_admin_action(request, 'generate_invite_codes', 'invite_code', None,
                     f'Generated {count} invite codes (platform={platform})')
    return JsonResponse({'created': created}, status=201)


@web_admin_required
@require_http_methods(['DELETE'])
def api_admin_invite_code_detail(request, code_id):
    """DELETE - revoke a single invite code."""
    with get_db_session() as db:
        code = db.query(WebEarlyAccessCode).filter_by(id=code_id).first()
        if not code:
            return JsonResponse({'error': 'Not found'}, status=404)
        if code.used_by_user_id:
            return JsonResponse({'error': 'Cannot revoke a code that has already been used'}, status=400)
        code.is_revoked = True
        db.commit()

    log_admin_action(request, 'revoke_invite_code', 'invite_code', code_id,
                     f'Revoked invite code {code.code}')
    return JsonResponse({'success': True})


@web_admin_required
@require_http_methods(['POST'])
def api_admin_invite_codes_bulk_revoke(request):
    """
    POST body: {"ids": [1,2,3]}  - revoke specific unused codes by ID
          OR   {"revoke_all_unused": true}  - revoke every unused+unrevoked code
    Used codes are always skipped (never revoke a code someone already claimed).
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        if data.get('revoke_all_unused'):
            codes = db.query(WebEarlyAccessCode).filter_by(
                is_revoked=False
            ).filter(WebEarlyAccessCode.used_by_user_id == None).all()
        else:
            ids = [int(i) for i in (data.get('ids') or []) if str(i).isdigit()]
            if not ids:
                return JsonResponse({'error': 'No IDs provided'}, status=400)
            codes = db.query(WebEarlyAccessCode).filter(
                WebEarlyAccessCode.id.in_(ids),
                WebEarlyAccessCode.is_revoked == False,
                WebEarlyAccessCode.used_by_user_id == None,
            ).all()

        count = len(codes)
        for code in codes:
            code.is_revoked = True
        db.commit()

    log_admin_action(request, 'bulk_revoke_invite_codes', 'invite_code', None,
                     f'Bulk revoked {count} invite codes')
    return JsonResponse({'revoked': count})


# =============================================================================
# HERO SUBSCRIBERS
# =============================================================================

@web_admin_required
@require_http_methods(['GET'])
def api_admin_hero_subscribers(request):
    """GET - list active Hero subscribers + aggregate stats."""
    with get_db_session() as db:
        heroes = (
            db.query(WebUser)
            .filter(WebUser.is_hero == 1)
            .order_by(WebUser.hero_expires_at.desc())
            .all()
        )
        total_active = len(heroes)

        # Total revenue from subscription events
        from sqlalchemy import func
        rev_row = db.query(func.sum(WebSubscriptionEvent.amount_cents)).filter(
            WebSubscriptionEvent.event_type == 'renewed',
            WebSubscriptionEvent.amount_cents != None,
        ).scalar()
        total_revenue_cents = int(rev_row or 0)

        now = int(time.time())
        result = []
        for u in heroes:
            result.append({
                'id': u.id,
                'username': u.username,
                'display_name': u.display_name or u.username,
                'avatar_url': u.avatar_url,
                'is_hero': bool(u.is_hero),
                'hero_expires_at': u.hero_expires_at,
                'is_expired': bool(u.hero_expires_at and u.hero_expires_at < now),
                'stripe_customer_id': u.stripe_customer_id,
                'created_at': u.created_at,
            })

    return JsonResponse({
        'subscribers': result,
        'stats': {
            'total_active': total_active,
            'total_revenue_cents': total_revenue_cents,
            'mrr_cents': total_active * 500,  # $5/mo estimate
        },
    })


# =============================================================================
# BOT NETWORK OVERVIEW
# =============================================================================

@web_admin_required
@require_http_methods(['GET'])
def api_admin_bot_network(request):
    """GET - overview of all Discord guilds, Fluxer guilds, and network configs."""
    from sqlalchemy import text, func

    with get_db_session() as db:
        # Fluxer guilds: grouped from channel cache
        fluxer_rows = db.execute(text(
            "SELECT guild_id, COALESCE(NULLIF(MAX(guild_name), ''), guild_id) AS guild_name, COUNT(*) as channel_count "
            "FROM web_fluxer_guild_channels "
            "GROUP BY guild_id "
            "ORDER BY guild_name"
        )).fetchall()
        fluxer_guilds = [
            {'guild_id': r[0], 'guild_name': r[1], 'channel_count': r[2]}
            for r in fluxer_rows
        ]

        # Network subscriptions (community bot configs)
        configs = db.query(WebCommunityBotConfig).order_by(WebCommunityBotConfig.platform, WebCommunityBotConfig.guild_name).all()
        network_configs = [
            {
                'id': c.id,
                'platform': c.platform,
                'guild_id': c.guild_id,
                'guild_name': c.guild_name,
                'channel_id': c.channel_id,
                'channel_name': c.channel_name,
                'event_type': c.event_type,
                'is_enabled': bool(c.is_enabled),
            }
            for c in configs
        ]

        # Bridge configs
        bridges = db.query(WebBridgeConfig).order_by(WebBridgeConfig.id).all()
        bridge_list = [_admin_bridge_dict(b) for b in bridges]

        # Discord guilds from the main guilds table (WardenBot)
        discord_guilds = []
        try:
            discord_rows = db.execute(text(
                "SELECT guild_id, guild_name, subscription_tier, "
                "       (SELECT COUNT(*) FROM guild_members gm WHERE gm.guild_id = g.guild_id) as member_count "
                "FROM guilds g ORDER BY guild_name LIMIT 200"
            )).fetchall()
            discord_guilds = [
                {
                    'guild_id': str(r[0]),
                    'guild_name': r[1],
                    'subscription_tier': r[2],
                    'member_count': r[3],
                    'dashboard_url': f'/questlog/guild/{r[0]}/',
                }
                for r in discord_rows
            ]
        except Exception as e:
            logger.warning(f"api_admin_bot_network: guilds table query failed: {e}")

        # Matrix spaces
        matrix_spaces = []
        try:
            from .models import WebMatrixSpaceSettings as _MatrixSpace
            space_rows = db.query(_MatrixSpace).filter_by(bot_present=1).order_by(
                _MatrixSpace.space_name
            ).all()
            matrix_spaces = [
                {'space_id': r.space_id, 'space_name': r.space_name or r.space_id}
                for r in space_rows
            ]
        except Exception as e:
            logger.warning(f"api_admin_bot_network: matrix spaces query failed: {e}")

    return JsonResponse({
        'discord_guilds': discord_guilds,
        'fluxer_guilds': fluxer_guilds,
        'matrix_spaces': matrix_spaces,
        'network_configs': network_configs,
        'bridges': bridge_list,
    })


@web_admin_required
@require_http_methods(['GET'])
def api_admin_discord_guild_channels(request, guild_id):
    """GET cached Discord channels for a guild from guilds.cached_channels."""
    from sqlalchemy import text as sa_text
    with get_db_session() as db:
        row = db.execute(
            sa_text("SELECT cached_channels FROM guilds WHERE guild_id = :gid LIMIT 1"),
            {"gid": int(guild_id)},
        ).fetchone()
    channels = []
    if row and row[0]:
        try:
            raw = json.loads(row[0])
            # Include text channels (type 0) and unknown types; exclude categories (4) and voice (2)
            channels = [
                {'id': str(c.get('id')), 'name': c.get('name', ''), 'type': c.get('type')}
                for c in raw
                if c.get('type') not in (2, 4)
            ]
            channels.sort(key=lambda c: c['name'])
        except Exception:
            pass
    return JsonResponse({'channels': channels})


# =============================================================================
# MATRIX SPACE / ROOM LOOKUPS (for bridge pickers)
# =============================================================================

@web_admin_required
@require_http_methods(['GET'])
def api_admin_matrix_spaces(request):
    """GET all Matrix spaces the bot is in - for bridge space picker."""
    from .models import WebMatrixSpaceSettings
    from sqlalchemy import text as sa_text
    with get_db_session() as db:
        rows = db.query(WebMatrixSpaceSettings).filter_by(bot_present=1).order_by(
            WebMatrixSpaceSettings.space_name
        ).all()
        spaces = [
            {'id': r.space_id, 'name': r.space_name or r.space_id}
            for r in rows
        ]
    return JsonResponse({'spaces': spaces})


@web_admin_required
@require_http_methods(['GET'])
def api_admin_matrix_space_rooms(request, space_id):
    """GET cached rooms for a Matrix space - for bridge room picker."""
    from .models import WebMatrixRoom
    import urllib.parse as _urlparse
    space_id = _urlparse.unquote(space_id)
    with get_db_session() as db:
        rows = db.query(WebMatrixRoom).filter_by(space_id=space_id, is_space=0).order_by(
            WebMatrixRoom.room_name
        ).all()
        rooms = [
            {'id': r.room_id, 'name': r.room_name}
            for r in rows
            if r.room_name and r.room_name != r.room_id
        ]
    return JsonResponse({'rooms': rooms})


# =============================================================================
# BRIDGE CONFIG CRUD
# =============================================================================

def _admin_bridge_dict(b):
    return {
        'id': b.id,
        'name': b.name or '',
        'discord_guild_id': b.discord_guild_id or '',
        'discord_channel_id': b.discord_channel_id or '',
        'fluxer_guild_id': b.fluxer_guild_id or '',
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


@web_admin_required
@require_http_methods(['GET', 'POST'])
def api_admin_bridge_configs(request):
    """GET list / POST create bridge config."""
    if request.method == 'GET':
        with get_db_session() as db:
            bridges = db.query(WebBridgeConfig).order_by(WebBridgeConfig.id).all()
            return JsonResponse({'bridges': [_admin_bridge_dict(b) for b in bridges]})

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    discord_channel_id = str(data.get('discord_channel_id', '') or '').strip()[:20]
    fluxer_channel_id = str(data.get('fluxer_channel_id', '') or '').strip()[:20]
    matrix_room_id = str(data.get('matrix_room_id', '') or '').strip()[:255]

    if not discord_channel_id and not fluxer_channel_id and not matrix_room_id:
        return JsonResponse({'error': 'At least one channel endpoint is required'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        bridge = WebBridgeConfig(
            name=str(data.get('name', '') or '').strip()[:100] or None,
            discord_guild_id=str(data.get('discord_guild_id', '') or '').strip()[:20] or None,
            discord_channel_id=discord_channel_id or None,
            fluxer_guild_id=str(data.get('fluxer_guild_id', '') or '').strip()[:20] or None,
            fluxer_channel_id=fluxer_channel_id or None,
            matrix_space_id=str(data.get('matrix_space_id', '') or '').strip()[:255] or None,
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
        bridge_id = bridge.id

    log_admin_action(request, 'create_bridge_config', 'bridge', bridge_id,
                     f"Discord {discord_channel_id} <-> Fluxer {fluxer_channel_id} <-> Matrix {matrix_room_id}")
    return JsonResponse({'id': bridge_id, 'success': True}, status=201)


@web_admin_required
@require_http_methods(['PATCH', 'DELETE'])
def api_admin_bridge_config_detail(request, config_id):
    """PATCH update / DELETE remove bridge config."""
    with get_db_session() as db:
        bridge = db.query(WebBridgeConfig).filter_by(id=config_id).first()
        if not bridge:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.query(WebBridgeRelayQueue).filter_by(bridge_id=config_id).delete()
            db.delete(bridge)
            db.commit()
            log_admin_action(request, 'delete_bridge_config', 'bridge', config_id, '')
            return JsonResponse({'success': True})

        # PATCH
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, AttributeError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'name' in data:
            bridge.name = str(data['name'] or '').strip()[:100] or None
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
        if 'fluxer_channel_id' in data:
            bridge.fluxer_channel_id = str(data['fluxer_channel_id'] or '')[:20] or None
        if 'discord_guild_id' in data:
            bridge.discord_guild_id = str(data['discord_guild_id'] or '')[:20] or None
        if 'fluxer_guild_id' in data:
            bridge.fluxer_guild_id = str(data['fluxer_guild_id'] or '')[:20] or None
        if 'matrix_space_id' in data:
            bridge.matrix_space_id = str(data['matrix_space_id'] or '')[:255] or None
        if 'matrix_room_id' in data:
            bridge.matrix_room_id = str(data['matrix_room_id'] or '')[:255] or None
        if 'relay_matrix_outbound' in data:
            bridge.relay_matrix_outbound = 1 if data['relay_matrix_outbound'] else 0
        if 'relay_matrix_inbound' in data:
            bridge.relay_matrix_inbound = 1 if data['relay_matrix_inbound'] else 0
        db.commit()

    return JsonResponse({'success': True})


# ── Custom Emoji & Stickers ──────────────────────────────────────────────────

@web_mod_required
@require_http_methods(["GET", "POST"])
def api_admin_emoji(request):
    """GET: list all emoji/stickers. POST: upload new one (multipart form)."""
    if request.method == 'GET':
        with get_db_session() as db:
            rows = db.query(WebCustomEmoji).order_by(WebCustomEmoji.created_at.desc()).all()
            return JsonResponse({'emoji': [
                {
                    'id': e.id,
                    'shortcode': e.shortcode,
                    'image_url': e.image_url,
                    'is_animated': bool(e.is_animated),
                    'is_sticker': bool(e.is_sticker),
                    'created_at': e.created_at,
                }
                for e in rows
            ]})

    # POST - upload
    shortcode = (request.POST.get('shortcode') or '').strip().lower()
    is_sticker = request.POST.get('is_sticker') == '1'

    if not shortcode:
        return JsonResponse({'error': 'Shortcode is required.'}, status=400)
    if not shortcode.replace('_', '').replace('-', '').isalnum():
        return JsonResponse({'error': 'Shortcode may only contain letters, numbers, hyphens, and underscores.'}, status=400)
    if len(shortcode) > 50:
        return JsonResponse({'error': 'Shortcode too long (max 50 chars).'}, status=400)
    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image file provided.'}, status=400)

    # Size caps: emoji 512KB, sticker 2MB
    max_bytes = 2 * 1024 * 1024 if is_sticker else 512 * 1024
    try:
        result = process_uploaded_image(
            request.FILES['image'],
            dest_subdir='emoji',
            max_size_bytes=max_bytes,
            max_gif_size=max_bytes,
            max_dimension=512 if is_sticker else 128,
        )
    except ValueError as e:
        logger.error('Emoji upload validation error: %s', e)
        return JsonResponse({'error': 'Invalid image: check file type, size, and dimensions'}, status=400)
    except Exception as e:
        logger.error(f"Emoji upload error: {e}")
        return JsonResponse({'error': 'Upload failed.'}, status=500)

    is_animated = result.get('image_url', '').endswith('.gif')

    with get_db_session() as db:
        existing = db.query(WebCustomEmoji).filter_by(shortcode=shortcode).first()
        if existing:
            return JsonResponse({'error': f'Shortcode :{shortcode}: is already taken.'}, status=400)
        emoji = WebCustomEmoji(
            shortcode=shortcode,
            image_url=result['image_url'],
            is_animated=is_animated,
            is_sticker=is_sticker,
            created_by=request.web_user.id,
        )
        db.add(emoji)
        db.commit()
        db.refresh(emoji)
        return JsonResponse({'success': True, 'emoji': {
            'id': emoji.id,
            'shortcode': emoji.shortcode,
            'image_url': emoji.image_url,
            'is_animated': bool(emoji.is_animated),
            'is_sticker': bool(emoji.is_sticker),
            'created_at': emoji.created_at,
        }})


@web_mod_required
@require_http_methods(["DELETE"])
def api_admin_emoji_detail(request, emoji_id):
    """DELETE: remove a custom emoji/sticker."""
    with get_db_session() as db:
        emoji = db.query(WebCustomEmoji).filter_by(id=emoji_id).first()
        if not emoji:
            return JsonResponse({'error': 'Not found.'}, status=404)
        db.delete(emoji)
        db.commit()
    return JsonResponse({'success': True})


# ---------------------------------------------------------------------------
# Admin: Testimonials
# ---------------------------------------------------------------------------

@web_admin_required
@require_http_methods(["GET", "POST"])
def api_admin_testimonials(request):
    """GET: list all. POST: create new."""
    with get_db_session() as db:
        if request.method == 'GET':
            rows = db.query(WebTestimonial).order_by(
                WebTestimonial.sort_order, WebTestimonial.id
            ).all()
            return JsonResponse({'testimonials': [_serialize_testimonial(t) for t in rows]})

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        quote = str(data.get('quote', '')).strip()
        if not quote:
            return JsonResponse({'error': 'Quote is required'}, status=400)
        if len(quote) > 500:
            return JsonResponse({'error': 'Quote too long (max 500 chars)'}, status=400)

        member_name = str(data.get('member_name', '')).strip()[:100]
        if not member_name:
            return JsonResponse({'error': 'Member name is required'}, status=400)

        avatar_url = str(data.get('avatar_url', '')).strip()
        if avatar_url:
            if not validate_admin_image_url(avatar_url):
                return JsonResponse({'error': 'Invalid avatar URL'}, status=400)

        t = WebTestimonial(
            member_name=member_name,
            handle=str(data.get('handle', '')).strip()[:100] or None,
            avatar_url=avatar_url or None,
            quote=quote,
            game_tag=str(data.get('game_tag', '')).strip()[:100] or None,
            sort_order=safe_int(data.get('sort_order', 0), default=0),
            is_active=bool(data.get('is_active', True)),
            created_at=int(time.time()),
        )
        db.add(t)
        db.commit()
        db.refresh(t)
        log_admin_action(request, 'testimonial_create', f'Created testimonial for {member_name}')
        return JsonResponse({'success': True, 'testimonial': _serialize_testimonial(t)}, status=201)


@web_admin_required
@require_http_methods(["PATCH", "DELETE"])
def api_admin_testimonial_detail(request, testimonial_id):
    """PATCH: update. DELETE: remove."""
    with get_db_session() as db:
        t = db.query(WebTestimonial).filter_by(id=testimonial_id).first()
        if not t:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.delete(t)
            db.commit()
            log_admin_action(request, 'testimonial_delete', f'Deleted testimonial {testimonial_id}')
            return JsonResponse({'success': True})

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        if 'quote' in data:
            quote = str(data['quote']).strip()
            if not quote or len(quote) > 500:
                return JsonResponse({'error': 'Invalid quote'}, status=400)
            t.quote = quote
        if 'member_name' in data:
            t.member_name = str(data['member_name']).strip()[:100]
        if 'handle' in data:
            t.handle = str(data['handle']).strip()[:100] or None
        if 'avatar_url' in data:
            av = str(data['avatar_url']).strip()
            if av and not validate_admin_image_url(av):
                return JsonResponse({'error': 'Invalid avatar URL'}, status=400)
            t.avatar_url = av or None
        if 'game_tag' in data:
            t.game_tag = str(data['game_tag']).strip()[:100] or None
        if 'sort_order' in data:
            t.sort_order = safe_int(data['sort_order'], default=0)
        if 'is_active' in data:
            t.is_active = bool(data['is_active'])

        db.commit()
        log_admin_action(request, 'testimonial_update', f'Updated testimonial {testimonial_id}')
        return JsonResponse({'success': True, 'testimonial': _serialize_testimonial(t)})


def _serialize_testimonial(t):
    return {
        'id':          t.id,
        'member_name': t.member_name,
        'handle':      t.handle or '',
        'avatar_url':  t.avatar_url or '',
        'quote':       t.quote,
        'game_tag':    t.game_tag or '',
        'sort_order':  t.sort_order,
        'is_active':   bool(t.is_active),
        'created_at':  t.created_at,
    }


@add_web_user_context
@require_http_methods(['GET'])
def api_user_lookup(request):
    """Admin-only: look up a user by username for dev assignment."""
    if not (request.web_user and request.web_user.is_admin):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    username = (request.GET.get('username') or '').strip()
    if not username:
        return JsonResponse({'user': None})
    with get_db_session() as db:
        user = db.query(WebUser).filter(
            WebUser.username == username,
            WebUser.is_banned == False,
        ).first()
        if not user:
            return JsonResponse({'user': None})
        return JsonResponse({'user': {
            'id': user.id,
            'username': user.username,
            'display_name': user.display_name or user.username,
            'avatar_url': user.avatar_url or '',
        }})
