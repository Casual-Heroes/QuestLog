# QuestLog Web — public browse APIs

import json
import re
import time
import asyncio
import logging


def _community_slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from sqlalchemy import text

from .models import (
    WebLFGGroup, WebLFGMember, WebCommunity, WebCreatorProfile,
    WebFoundGame, WebRSSArticle, WebUser, PlatformType,
    WebCommunityBotConfig, WebLFGGameConfig,
    WebFluxerLfgGroup, WebFluxerLfgConfig, WebFluxerGuildChannel,
    WebFluxerLfgMember, WebFluxerGuildSettings, WebFluxerLfgGame,
    WebPost, WebFollow,
)
from app.db import get_db_session
from .helpers import add_web_user_context, web_login_required, web_verified_required, safe_int, EXCLUDED_USER_IDS, generate_post_public_id, create_notification
from .fluxer_webhooks import notify_lfg_post as _fluxer_lfg_post, build_lfg_embed_data as _build_lfg_embed_data

logger = logging.getLogger(__name__)

_VOICE_LINK_SCHEMES = ('https://',)
_VOICE_LINK_MAX = 500

# Allowlist for platform invite URLs (invite_url field only - must be a known platform)
_INVITE_URL_DOMAINS = {
    'discord.gg', 'discord.com',
    'fluxer.gg',
    'matrix.to',
    'stoat.gg',
    'root.gg',
    'revolt.chat',
    'teamspeak.com',
    'mumble.info',
}

# Allowlist for social link fields
_SOCIAL_URL_DOMAINS = {
    'twitch.tv', 'www.twitch.tv',
    'youtube.com', 'www.youtube.com', 'youtu.be',
    'twitter.com', 'x.com', 'www.twitter.com', 'www.x.com',
    'bsky.app', 'bsky.social',
    'tiktok.com', 'www.tiktok.com',
    'instagram.com', 'www.instagram.com',
    'bluesky.social',
}

# Valid in-game guild slugs - single source of truth
VALID_GUILD_GAMES = frozenset({'ffxiv', 'eso', 'wow', 'gw2', 'lost_ark', 'bdo', 'swtor', 'other'})

# ── Survival game sub-choices (mirrors lfg_browse.html GAME_TEMPLATES) ───────
_SURVIVAL_SUB_CHOICES = {
    'palworld':   [
        ('Tank/Defender',  'tank'), ('Support/Healer', 'healer'),
        ('Combat (Melee)', 'dps'),  ('Combat (Ranged)', 'dps'), ('Scout/Explorer', 'dps'),
        ('Builder', 'support'), ('Gatherer', 'support'), ('Tamer/Breeder', 'support'), ('Crafter', 'support'),
    ],
    'enshrouded': [
        ('Tank', 'tank'), ('Healer', 'healer'),
        ('Ranger (DPS)', 'dps'), ('Mage (DPS)', 'dps'), ('Fighter (DPS)', 'dps'),
        ('Builder', 'support'), ('Crafter', 'support'),
    ],
    'valheim': [
        ('Berserker (Tank)', 'tank'), ('Healer/Support', 'healer'),
        ('Archer (DPS)', 'dps'), ('Warrior (DPS)', 'dps'),
        ('Builder', 'support'), ('Gatherer', 'support'),
    ],
    'rust': [
        ('Raider', 'tank'), ('Medic/Support', 'healer'),
        ('Gunner (DPS)', 'dps'), ('Scout', 'dps'),
        ('Builder', 'support'), ('Farmer/Gatherer', 'support'),
    ],
}

_SURVIVAL_GAME_NAMES = {
    'palworld': ['palworld'], 'enshrouded': ['enshrouded'],
    'valheim': ['valheim'], 'rust': ['rust'],
}

def _detect_survival_game_type(game_name):
    """Return survival game key if game_name matches, else None."""
    if not game_name:
        return None
    nl = game_name.lower()
    for key, aliases in _SURVIVAL_GAME_NAMES.items():
        if any(a in nl for a in aliases):
            return key
    return None

def _is_survival_schema(role_schema_raw):
    """Return True if the stored role_schema is the survival variant."""
    import json as _json
    if not role_schema_raw:
        return False
    try:
        schema = _json.loads(role_schema_raw)
    except (ValueError, TypeError):
        return False
    if not isinstance(schema, list):
        return False
    return any(
        r.get('slot') == 'tank' and (r.get('label') == 'Combat' or r.get('color') == 'orange')
        for r in schema
    )

# ── Role schema helpers ───────────────────────────────────────────────────────

_DEFAULT_ROLE_SCHEMA = [
    {'slot': 'tank',    'label': 'Tank',    'color': 'blue',   'icon': 'shield-alt'},
    {'slot': 'healer',  'label': 'Healer',  'color': 'green',  'icon': 'heart'},
    {'slot': 'dps',     'label': 'DPS',     'color': 'red',    'icon': 'bolt'},
    {'slot': 'support', 'label': 'Support', 'color': 'yellow', 'icon': 'music'},
]
_VALID_SLOTS = {'tank', 'healer', 'dps', 'support'}
_VALID_COLORS = {'blue', 'green', 'red', 'yellow', 'orange', 'cyan', 'pink', 'purple', 'gray'}


def _parse_role_schema(raw_json):
    """Parse role_schema Text column. Returns list of 4 dicts with slot/label/color/icon.
    Falls back to default if null, invalid JSON, wrong structure, or bad slot keys."""
    if not raw_json:
        return _DEFAULT_ROLE_SCHEMA
    try:
        schema = json.loads(raw_json)
    except (ValueError, TypeError):
        return _DEFAULT_ROLE_SCHEMA
    if not isinstance(schema, list) or len(schema) != 4:
        return _DEFAULT_ROLE_SCHEMA
    seen_slots = set()
    result = []
    for entry in schema:
        if not isinstance(entry, dict):
            return _DEFAULT_ROLE_SCHEMA
        slot = entry.get('slot', '')
        if slot not in _VALID_SLOTS or slot in seen_slots:
            return _DEFAULT_ROLE_SCHEMA
        seen_slots.add(slot)
        label = str(entry.get('label', slot))[:30]
        color = str(entry.get('color', 'gray'))[:20]
        if color not in _VALID_COLORS:
            color = 'gray'
        icon = str(entry.get('icon', 'circle'))[:40]
        result.append({'slot': slot, 'label': label, 'color': color, 'icon': icon})
    return result


def _validate_role_schema(raw):
    """Validate incoming role_schema from client (list or JSON string).
    Returns JSON string to store, or None if default/invalid."""
    if not raw:
        return None
    if isinstance(raw, list):
        raw_json = json.dumps(raw)
    elif isinstance(raw, str):
        raw_json = raw
    else:
        return None
    parsed = _parse_role_schema(raw_json)
    # Store None if it matches the default (keeps DB clean)
    if all(
        parsed[i]['slot'] == _DEFAULT_ROLE_SCHEMA[i]['slot'] and
        parsed[i]['label'] == _DEFAULT_ROLE_SCHEMA[i]['label']
        for i in range(4)
    ):
        return None
    return json.dumps(parsed)


def _notify_lfg_game_owners(group_id, game_name, creator_id, now):
    """Notify all members who own `game_name` (via Steam library cache) that a new LFG was created."""
    from django.core.cache import cache
    from app.db import get_db_session
    from app.questlog_web.models import WebUser, WebNotification

    game_lower = game_name.lower()

    with get_db_session() as db:
        candidates = db.query(WebUser.id, WebUser.steam_id).filter(
            WebUser.steam_id.isnot(None),
            WebUser.steam_id != '',
            WebUser.share_steam_library == True,
            WebUser.notify_lfg_game_owned == True,
            WebUser.is_banned == False,
            WebUser.is_disabled == False,
            WebUser.id != creator_id,
        ).all()

        notified = []
        for user_id, steam_id in candidates:
            lib_key = f'steamquest_library_{steam_id}'
            library = cache.get(lib_key) or []
            owns = any(
                g.get('name', '').lower() == game_lower
                for g in library
            )
            if not owns:
                continue
            db.add(WebNotification(
                user_id=user_id,
                actor_id=creator_id,
                notification_type='lfg_game_owned',
                target_type='lfg',
                target_id=str(group_id),
                message=f'A new LFG group was created for {game_name}',
                created_at=now,
                is_read=False,
            ))
            notified.append(user_id)

        if notified:
            db.commit()


def _validate_voice_link(url):
    """Only allow https:// URLs. Prevents javascript:/file: URI injection."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()[:_VOICE_LINK_MAX]
    if not url.startswith('https://'):
        return None
    return url or None


def _validate_invite_url(url):
    """Invite URLs must be https:// AND from a known platform domain."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()[:_VOICE_LINK_MAX]
    if not url.startswith('https://'):
        return None
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip('www.')
        if not any(host == d or host.endswith('.' + d) for d in _INVITE_URL_DOMAINS):
            return None
    except Exception:
        return None
    return url


def _validate_social_url(url):
    """Social links must be https:// AND from a known social platform domain."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()[:_VOICE_LINK_MAX]
    if not url.startswith('https://'):
        return None
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        if not any(host == d or host.endswith('.' + d) for d in _SOCIAL_URL_DOMAINS):
            return None
    except Exception:
        return None
    return url


@ratelimit(key='user_or_ip', rate='20/h', method='POST', block=True)
@add_web_user_context
@require_http_methods(["GET", "POST"])
def api_lfg_list(request):
    """API: List LFG groups (GET) or create a new one (POST)."""

    if request.method == "POST":
        if not request.web_user:
            return JsonResponse({'error': 'Login required'}, status=401)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        game_name = (data.get('game_name') or '').strip()
        title = (data.get('title') or '').strip()
        if not game_name:
            return JsonResponse({'error': 'Game name is required'}, status=400)
        if not title:
            return JsonResponse({'error': 'Group title is required'}, status=400)
        if len(title) > 200:
            return JsonResponse({'error': 'Title too long (max 200 chars)'}, status=400)

        group_size = safe_int(data.get('group_size') or 4, default=4, min_val=2, max_val=40)
        if not (2 <= group_size <= 40):
            return JsonResponse({'error': 'Group size must be between 2 and 40'}, status=400)

        now = int(time.time())
        with get_db_session() as db:
            # Generate a unique share token
            share_token = generate_post_public_id()
            while db.query(WebLFGGroup).filter_by(share_token=share_token).first():
                share_token = generate_post_public_id()

            group = WebLFGGroup(
                creator_id=request.web_user.id,
                title=title,
                description=(data.get('description') or '')[:2000] or None,
                game_name=game_name[:200],
                game_id=(data.get('game_id') or '')[:50] or None,
                game_image_url=_validate_voice_link(data.get('game_image_url')),
                group_size=group_size,
                current_size=1,
                use_roles=bool(data.get('use_roles', False)),
                tanks_needed=safe_int(data.get('tanks_needed') or 0, default=0, min_val=0, max_val=40),
                healers_needed=safe_int(data.get('healers_needed') or 0, default=0, min_val=0, max_val=40),
                dps_needed=safe_int(data.get('dps_needed') or 0, default=0, min_val=0, max_val=40),
                support_needed=safe_int(data.get('support_needed') or 0, default=0, min_val=0, max_val=40),
                role_schema=_validate_role_schema(data.get('role_schema')),
                scheduled_time=safe_int(data.get('scheduled_time'), default=None, min_val=0, max_val=9999999999),
                voice_platform=(data.get('voice_platform') or '')[:50] or None,
                voice_link=_validate_voice_link(data.get('voice_link')),
                server_invite_link=_validate_voice_link(data.get('server_invite_link')),
                status='open',
                share_token=share_token,
                created_at=now,
                updated_at=now,
            )
            db.add(group)
            db.flush()

            # Creator is first member — store game-specific selections (class/spec/activity)
            raw_selections = data.get('selections') or {}
            # Sanitize all string values to prevent XSS if rendered in templates
            from .helpers import sanitize_text as _st
            if raw_selections and isinstance(raw_selections, dict):
                raw_selections = {
                    k: (_st(str(v)[:200]) if isinstance(v, str) else
                        ([_st(str(i)[:200]) for i in v if isinstance(i, str)] if isinstance(v, list) else v))
                    for k, v in raw_selections.items() if isinstance(k, str)
                }
            selections_json = json.dumps(raw_selections) if raw_selections else None
            db.add(WebLFGMember(
                group_id=group.id,
                user_id=request.web_user.id,
                role=data.get('selected_role') or None,
                selections=selections_json,
                is_creator=True,
                status='joined',
                joined_at=now,
            ))
            db.commit()

        # Notify members who own this game (fire-and-forget)
        try:
            _notify_lfg_game_owners(group.id, game_name, request.web_user.id, now)
        except Exception:
            pass

        # Notify admin LFG channel (fire-and-forget, never raises)
        try:
            lfg_url = f"https://casual-heroes.com/ql/lfg/{group.share_token or group.id}/"
            _fluxer_lfg_post(
                creator=request.web_user.display_name or request.web_user.username,
                game_name=game_name,
                title=title,
                description=group.description or '',
                group_size=group_size,
                current_size=1,
                scheduled_time=group.scheduled_time,
                duration_hours=group.duration_hours,
                lfg_url=lfg_url,
                game_image_url=group.game_image_url,
                use_roles=group.use_roles or False,
                tanks_needed=group.tanks_needed or 0,
                healers_needed=group.healers_needed or 0,
                dps_needed=group.dps_needed or 0,
                support_needed=group.support_needed or 0,
                role_schema=_parse_role_schema(group.role_schema),
                creator_selections=raw_selections,
                group_id=group.id,
                voice_link=group.voice_link,
                server_invite_link=group.server_invite_link,
            )
        except Exception:
            pass

        return JsonResponse({'success': True, 'id': group.id, 'share_token': group.share_token})

    # GET — list groups; ?mine=true returns groups the user created or joined
    mine = request.GET.get('mine') == 'true'
    with get_db_session() as db:
        if mine and request.web_user:
            # Groups where user is creator OR active member
            member_group_ids = [
                m.group_id for m in db.query(WebLFGMember).filter_by(
                    user_id=request.web_user.id, status='joined'
                ).all()
            ]
            groups = db.query(WebLFGGroup).filter(
                WebLFGGroup.id.in_(member_group_ids)
            ).order_by(WebLFGGroup.created_at.desc()).limit(100).all()
        else:
            groups = db.query(WebLFGGroup).filter(
                WebLFGGroup.status.in_(['open', 'full'])
            ).order_by(WebLFGGroup.created_at.desc()).limit(50).all()

        viewer_id = request.web_user.id if request.web_user else None

        # Fetch all members for the listed groups in one query
        group_ids = [g.id for g in groups]
        members_raw = db.query(WebLFGMember, WebUser).join(
            WebUser, WebLFGMember.user_id == WebUser.id
        ).filter(
            WebLFGMember.group_id.in_(group_ids),
            WebLFGMember.status == 'joined',
        ).all() if group_ids else []

        from collections import defaultdict
        members_by_group = defaultdict(list)
        for m, u in members_raw:
            members_by_group[m.group_id].append({
                'user_id': m.user_id,
                'username': u.username,
                'display_name': u.display_name or u.username,
                'role': m.role,
                'selections': json.loads(m.selections) if m.selections else {},
                'is_creator': m.is_creator,
                'is_co_leader': m.is_co_leader,
            })

        # Build creator name + platform lookup from members (is_creator=True)
        creator_name_by_group = {}
        creator_platform_by_group = {}
        for m, u in members_raw:
            if m.is_creator:
                creator_name_by_group[m.group_id] = u.display_name or u.username
                # Determine creator's primary linked platform (for badge display)
                if u.discord_id:
                    creator_platform_by_group[m.group_id] = 'discord'
                elif u.fluxer_id:
                    creator_platform_by_group[m.group_id] = 'fluxer'
                elif u.matrix_id:
                    creator_platform_by_group[m.group_id] = 'matrix'
                else:
                    creator_platform_by_group[m.group_id] = 'web'

        data = [{
            'id': g.id,
            'share_token': g.share_token,
            'title': g.title,
            'description': g.description,
            'game_name': g.game_name,
            'game_id': g.game_id,
            'game_image_url': g.game_image_url,
            'group_size': g.group_size,
            'current_size': g.current_size,
            'scheduled_time': g.scheduled_time,
            'status': g.status,
            'created_at': g.created_at,
            'voice_platform': g.voice_platform,
            'voice_link': g.voice_link,
            'creator_id': g.creator_id,
            'creator_name': creator_name_by_group.get(g.id),
            'creator_platform': creator_platform_by_group.get(g.id, 'web'),
            'is_creator': g.creator_id == viewer_id,
            'has_role_composition': bool(g.use_roles),
            'tanks_needed': g.tanks_needed or 0,
            'healers_needed': g.healers_needed or 0,
            'dps_needed': g.dps_needed or 0,
            'support_needed': g.support_needed or 0,
            'role_schema': _parse_role_schema(g.role_schema),
            'members': members_by_group[g.id],
            'platform': 'web',
            'origin_platform': g.origin_platform,
            'origin_group_id': g.origin_group_id,
            'origin_guild_id': g.origin_guild_id,
            'origin_guild_name': g.origin_guild_name,
        } for g in groups]

        # Merge active Fluxer LFG posts (bot-created) when not in ?mine mode
        if not mine:
            try:
                now_ts = int(time.time())
                fluxer_rows = db.execute(
                    text(
                        "SELECT id, user_id, username, game, game_cover_url, description, "
                        "group_size, scheduled_time, created_at, expires_at, guild_id "
                        "FROM fluxer_lfg_posts "
                        "WHERE is_active = 1 AND expires_at > :now "
                        "ORDER BY created_at DESC LIMIT 25"
                    ),
                    {"now": now_ts},
                ).fetchall()

                # Determine the current user's fluxer_id for can_manage check
                my_fluxer_id = None
                if request.web_user:
                    my_fluxer_id = getattr(request.web_user, 'fluxer_id', None)

                for row in fluxer_rows:
                    fid, fuid, funame, fgame, fcover, fdesc, fsize, fsched, fcreated, fexpires, fguild = row
                    can_manage = bool(my_fluxer_id and str(fuid) == str(my_fluxer_id))
                    data.append({
                        'id': f'fluxer_{fid}',
                        'title': fgame,
                        'description': fdesc,
                        'game_name': fgame,
                        'game_id': None,
                        'game_image_url': fcover,
                        'group_size': fsize or 4,
                        'current_size': 1,
                        'scheduled_time': fsched,
                        'status': 'open',
                        'created_at': fcreated,
                        'voice_platform': None,
                        'voice_link': None,
                        'creator_id': None,
                        'is_creator': can_manage,
                        'can_manage': can_manage,
                        'has_role_composition': False,
                        'tanks_needed': 0,
                        'healers_needed': 0,
                        'dps_needed': 0,
                        'support_needed': 0,
                        'role_schema': _DEFAULT_ROLE_SCHEMA,
                        'members': [],
                        'platform': 'fluxer',
                        'fluxer_username': funame,
                        'fluxer_post_id': fid,
                        'fluxer_guild_id': str(fguild),
                        'expires_at': fexpires,
                    })
            except Exception as e:
                logger.warning(f"Could not fetch Fluxer LFG posts: {e}")

        # Merge guild LFG groups from guilds that opted into the network
        try:
            published_configs = db.query(WebFluxerLfgConfig).filter_by(publish_to_network=1).all()
            published_guild_ids = [c.guild_id for c in published_configs]
            if published_guild_ids:
                # Guild name: try channels table first (skip empty strings), fall back to settings
                guild_name_rows = db.query(
                    WebFluxerGuildChannel.guild_id,
                    WebFluxerGuildChannel.guild_name,
                ).filter(
                    WebFluxerGuildChannel.guild_id.in_(published_guild_ids),
                    WebFluxerGuildChannel.guild_name.isnot(None),
                    WebFluxerGuildChannel.guild_name != '',
                ).all()
                guild_names = {}
                for r in guild_name_rows:
                    if r.guild_id not in guild_names:
                        guild_names[r.guild_id] = r.guild_name

                settings_rows = db.query(
                    WebFluxerGuildSettings.guild_id,
                    WebFluxerGuildSettings.guild_name,
                ).filter(
                    WebFluxerGuildSettings.guild_id.in_(published_guild_ids),
                    WebFluxerGuildSettings.guild_name.isnot(None),
                    WebFluxerGuildSettings.guild_name != '',
                ).all()
                for r in settings_rows:
                    if r.guild_id not in guild_names:
                        guild_names[r.guild_id] = r.guild_name

                now_ts = int(time.time())
                guild_groups = db.query(WebFluxerLfgGroup).filter(
                    WebFluxerLfgGroup.guild_id.in_(published_guild_ids),
                    WebFluxerLfgGroup.status.in_(['open', 'full']),
                    WebFluxerLfgGroup.created_at > now_ts - 86400 * 7,
                ).order_by(WebFluxerLfgGroup.created_at.desc()).limit(50).all()

                if guild_groups:
                    guild_group_ids = [g.id for g in guild_groups]

                    # Game cover URLs from WebFluxerLfgGame keyed by game id
                    game_ids = list({g.game_id for g in guild_groups if g.game_id})
                    game_cover_map = {}
                    game_meta_map = {}  # id -> {cover_url, options, has_roles, tank_slots, ...}
                    if game_ids:
                        game_rows = db.query(WebFluxerLfgGame).filter(
                            WebFluxerLfgGame.id.in_(game_ids),
                        ).all()
                        for gr in game_rows:
                            if gr.id not in game_cover_map and gr.cover_url:
                                game_cover_map[gr.id] = gr.cover_url
                            if gr.id not in game_meta_map:
                                game_meta_map[gr.id] = {
                                    'has_roles': bool(gr.has_roles),
                                    'tank_slots': gr.tank_slots or 0,
                                    'healer_slots': gr.healer_slots or 0,
                                    'dps_slots': gr.dps_slots or 0,
                                    'support_slots': gr.support_slots or 0,
                                    'options': json.loads(gr.options_json) if gr.options_json else [],
                                }

                    guild_members_raw = db.query(WebFluxerLfgMember).filter(
                        WebFluxerLfgMember.group_id.in_(guild_group_ids),
                        WebFluxerLfgMember.left_at.is_(None),
                    ).all()
                    from collections import defaultdict as _dd
                    guild_members_by_group = _dd(list)
                    for m in guild_members_raw:
                        guild_members_by_group[m.group_id].append({
                            'user_id': m.fluxer_user_id or m.web_user_id,
                            'username': m.username or 'Unknown',
                            'display_name': m.username or 'Unknown',
                            'role': m.role,
                            'selections': json.loads(m.selections_json) if m.selections_json else {},
                            'is_creator': bool(m.is_creator),
                            'is_co_leader': False,
                            'fluxer_user_id': m.fluxer_user_id,
                            'web_user_id': m.web_user_id,
                            'member_id': m.id,
                        })

                    _my_fid = None
                    if request.web_user:
                        _fid = getattr(request.web_user, 'fluxer_id', None)
                        _my_fid = str(_fid) if _fid else None

                    for g in guild_groups:
                        group_members = guild_members_by_group[g.id]
                        is_creator = bool(
                            (_my_fid and g.creator_fluxer_id and _my_fid == str(g.creator_fluxer_id)) or
                            (viewer_id and g.creator_web_user_id == viewer_id)
                        )
                        is_member = is_creator or any(
                            (_my_fid and m['fluxer_user_id'] and _my_fid == str(m['fluxer_user_id'])) or
                            (viewer_id and m['web_user_id'] == viewer_id)
                            for m in group_members
                        )
                        # When fetching "mine", skip groups the user has no membership in
                        if mine and not is_member:
                            continue
                        gmeta = game_meta_map.get(g.game_id, {}) if g.game_id else {}
                        data.append({
                            'id': f'guild_lfg_{g.id}',
                            'title': g.title or g.game_name,
                            'description': g.description,
                            'game_name': g.game_name,
                            'game_id': g.game_id,
                            'game_image_url': game_cover_map.get(g.game_id) if g.game_id else None,
                            'group_size': g.max_size,
                            'current_size': g.current_size,
                            'scheduled_time': g.scheduled_time,
                            'status': g.status,
                            'created_at': g.created_at,
                            'voice_platform': None,
                            'voice_link': None,
                            'creator_id': None,
                            'is_creator': is_creator,
                            'is_member': is_member,
                            'has_role_composition': gmeta.get('has_roles', False),
                            'tanks_needed': gmeta.get('tank_slots', 0),
                            'healers_needed': gmeta.get('healer_slots', 0),
                            'dps_needed': gmeta.get('dps_slots', 0),
                            'support_needed': gmeta.get('support_slots', 0),
                            'role_schema': _DEFAULT_ROLE_SCHEMA,
                            'game_options': gmeta.get('options', []),
                            'members': group_members,
                            'platform': 'fluxer_guild',
                            'guild_id': g.guild_id,
                            'guild_name': guild_names.get(g.guild_id, 'Unknown Server'),
                            'creator_name': g.creator_name,
                            'guild_lfg_id': g.id,
                        })
        except Exception as e:
            logger.warning(f"Could not fetch guild LFG groups for network: {e}")

    # Sort merged results by created_at descending
    data.sort(key=lambda x: x['created_at'], reverse=True)

    return JsonResponse({'groups': data})


@add_web_user_context
def api_lfg_detail(request, group_id):
    """API: Get LFG group details including full member list."""
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        members_raw = db.query(WebLFGMember, WebUser).join(
            WebUser, WebLFGMember.user_id == WebUser.id
        ).filter(
            WebLFGMember.group_id == group_id,
            WebLFGMember.status == 'joined',
        ).all()

        viewer_id = request.web_user.id if request.web_user else None
        viewer_is_member = False
        viewer_is_creator = group.creator_id == viewer_id
        viewer_is_co_leader = False

        members = []
        for m, u in members_raw:
            if viewer_id and m.user_id == viewer_id:
                viewer_is_member = True
                viewer_is_co_leader = m.is_co_leader
            members.append({
                'user_id': m.user_id,
                'username': u.username,
                'display_name': u.display_name or u.username,
                'avatar_url': u.avatar_url,
                'role': m.role,
                'selections': json.loads(m.selections) if m.selections else {},
                'is_creator': m.is_creator,
                'is_co_leader': m.is_co_leader,
                'joined_at': m.joined_at,
            })

        data = {
            'id': group.id,
            'share_token': group.share_token,
            'title': group.title,
            'description': group.description,
            'game_name': group.game_name,
            'game_id': group.game_id,
            'game_image_url': group.game_image_url,
            'group_size': group.group_size,
            'current_size': group.current_size,
            'scheduled_time': group.scheduled_time,
            'status': group.status,
            'use_roles': group.use_roles,
            'tanks_needed': group.tanks_needed,
            'healers_needed': group.healers_needed,
            'dps_needed': group.dps_needed,
            'support_needed': group.support_needed,
            'role_schema': _parse_role_schema(group.role_schema),
            'voice_platform': group.voice_platform,
            'voice_link': group.voice_link,
            'created_at': group.created_at,
            'creator_id': group.creator_id,
            'members': members,
            'viewer_is_member': viewer_is_member,
            'viewer_is_creator': viewer_is_creator,
            'viewer_is_co_leader': viewer_is_co_leader,
        }

    return JsonResponse(data)


@ratelimit(key='user_or_ip', rate='5/h', method='POST', block=True)
@add_web_user_context
@require_http_methods(["GET", "POST"])
def api_communities(request):
    """API: List communities (GET) or register a new one (POST)."""

    if request.method == 'POST':
        if not request.web_user:
            return JsonResponse({'error': 'Login required'}, status=401)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        name = (data.get('name') or '').strip()
        if not name or len(name) > 200:
            return JsonResponse({'error': 'Community name is required (max 200 chars)'}, status=400)

        # platforms is a list of {platform, platform_id} dicts - one per bot being linked
        raw_platforms = data.get('platforms') or []
        if not isinstance(raw_platforms, list):
            raw_platforms = []

        # Validate and resolve each platform entry
        discord_id = str(getattr(request.web_user, 'discord_id', '') or '')
        fluxer_id_str = str(getattr(request.web_user, 'fluxer_id', '') or '')

        resolved_platforms = []  # list of (PlatformType, platform_id_str, invite_url, member_count)
        for entry in raw_platforms[:5]:  # max 5 (discord + fluxer + matrix + stoat + root)
            ptype_str = (entry.get('platform') or '').lower()
            pid = (entry.get('platform_id') or '').strip()[:500]
            if not ptype_str or not pid:
                continue
            try:
                ptype = PlatformType(ptype_str)
            except ValueError:
                continue

            p_invite_url = (entry.get('invite_url') or '')[:500] or None
            p_member_count = safe_int(entry.get('member_count') or 0, default=0, min_val=0)

            # Invite-link-only platforms: Stoat and Root have no bot, no ownership check
            if ptype in (PlatformType.STOAT, PlatformType.ROOT):
                # For these platforms the invite URL IS the platform_id
                resolved_platforms.append((ptype, pid, p_invite_url, p_member_count))
                continue

            # Verify ownership per platform
            if ptype == PlatformType.FLUXER:
                # If pid looks like a URL it's a manual invite link - skip ownership check
                if pid.startswith('http://') or pid.startswith('https://'):
                    resolved_platforms.append((ptype, pid, p_invite_url, p_member_count))
                    continue
                linked = [i for i in [discord_id, fluxer_id_str] if i]
                if not linked:
                    return JsonResponse({'error': 'Connect your Fluxer account to link a Fluxer server'}, status=403)
                with get_db_session() as db:
                    ph = ','.join(f':lid{i}' for i in range(len(linked)))
                    params = {f'lid{i}': v for i, v in enumerate(linked)}
                    params['gid'] = pid
                    row = db.execute(
                        text(f"SELECT guild_id FROM web_fluxer_guild_settings WHERE guild_id=:gid AND owner_id IN ({ph}) LIMIT 1"),
                        params,
                    ).fetchone()
                if not row:
                    return JsonResponse({'error': 'You are not the owner of that Fluxer server'}, status=403)

            elif ptype == PlatformType.DISCORD:
                # If pid isn't a numeric guild ID it's a manual invite URL - skip ownership check
                try:
                    discord_guild_id = int(pid)
                except (ValueError, TypeError):
                    resolved_platforms.append((ptype, pid, p_invite_url, p_member_count))
                    continue
                if not discord_id:
                    return JsonResponse({'error': 'Connect your Discord account to link a Discord server'}, status=403)
                with get_db_session() as db:
                    row = db.execute(
                        text("SELECT guild_id FROM guilds WHERE guild_id=:gid AND owner_id=:oid AND bot_present=1 LIMIT 1"),
                        {'gid': discord_guild_id, 'oid': int(discord_id)},
                    ).fetchone()
                if not row:
                    return JsonResponse({'error': 'You are not the owner of that Discord server'}, status=403)

            elif ptype == PlatformType.MATRIX:
                matrix_id_str = str(getattr(request.web_user, 'matrix_id', '') or '')
                if not matrix_id_str:
                    return JsonResponse({'error': 'Connect your Matrix account to link a Matrix space'}, status=403)
                with get_db_session() as db:
                    row = db.execute(
                        text("SELECT space_id FROM web_matrix_space_settings WHERE space_id=:sid AND owner_matrix_id=:mid LIMIT 1"),
                        {'sid': pid, 'mid': matrix_id_str},
                    ).fetchone()
                if not row:
                    return JsonResponse({'error': 'You are not the owner of that Matrix space'}, status=403)

            resolved_platforms.append((ptype, pid, p_invite_url, p_member_count))

        # If no valid platforms selected, fall through as platform-less community
        # (allowed - community just won't be linked to a bot)

        now = int(time.time())
        raw_tags = data.get('tags') or []
        tags_json = json.dumps([t for t in raw_tags if isinstance(t, str)][:8])

        raw_guild_games = data.get('guild_game') or []
        if isinstance(raw_guild_games, str):
            raw_guild_games = [raw_guild_games] if raw_guild_games else []
        guild_games_clean = [g.strip().lower() for g in raw_guild_games if isinstance(g, str) and g.strip().lower() in VALID_GUILD_GAMES]
        raw_games = data.get('games') or []
        games_json = json.dumps([g.strip() for g in raw_games if isinstance(g, str) and g.strip()][:20])
        shared_fields = dict(
            name=name,
            short_description=(data.get('short_description') or '')[:500] or None,
            description=(data.get('description') or '') or None,
            website_url=_validate_voice_link(data.get('website_url')),
            twitch_url=_validate_social_url(data.get('twitch_url')),
            youtube_url=_validate_social_url(data.get('youtube_url')),
            twitter_url=_validate_social_url(data.get('twitter_url')),
            bluesky_url=_validate_social_url(data.get('bluesky_url')),
            tiktok_url=_validate_social_url(data.get('tiktok_url')),
            instagram_url=_validate_social_url(data.get('instagram_url')),
            tags=tags_json,
            games=games_json,
            allow_discovery=bool(data.get('allow_discovery', False)),
            allow_joins=bool(data.get('allow_joins', False)),
            site_xp_to_guild=bool(data.get('site_xp_to_guild', False)),  # stored; only active once network_status='approved'
            guild_game=json.dumps(guild_games_clean) if guild_games_clean else None,
            guild_game_name=(data.get('guild_game_name') or '')[:200].strip() or None,
            owner_id=request.web_user.id,
            network_status='pending',
            is_active=True,
            is_banned=False,
            created_at=now,
            updated_at=now,
        )

        first_id = None
        with get_db_session() as db:
            if resolved_platforms:
                # Pre-flight duplicate checks
                for ptype, pid, p_invite_url, p_member_count in resolved_platforms:
                    dup = db.query(WebCommunity).filter_by(platform=ptype, platform_id=pid).first()
                    if dup:
                        return JsonResponse(
                            {'error': f'That {ptype.value} server is already registered in the directory'},
                            status=400,
                        )

                # Create all rows; if more than one platform, share a community_group_id
                created_ids = []
                for ptype, pid, p_invite_url, p_member_count in resolved_platforms:
                    # Auto-populate icon_url from cached guild icon hash
                    p_icon_url = None
                    if ptype == PlatformType.FLUXER:
                        icon_row = db.execute(
                            text("SELECT guild_icon_hash FROM web_fluxer_guild_settings WHERE guild_id=:gid LIMIT 1"),
                            {'gid': pid},
                        ).fetchone()
                        if icon_row and icon_row[0]:
                            p_icon_url = f'https://cdn.discordapp.com/icons/{pid}/{icon_row[0]}.png?size=256'
                    elif ptype == PlatformType.DISCORD:
                        try:
                            discord_gid = int(pid)
                        except (ValueError, TypeError):
                            discord_gid = None
                        if discord_gid:
                            icon_row = db.execute(
                                text("SELECT guild_icon_hash FROM guilds WHERE guild_id=:gid LIMIT 1"),
                                {'gid': discord_gid},
                            ).fetchone()
                            if icon_row and icon_row[0]:
                                p_icon_url = f'https://cdn.discordapp.com/icons/{pid}/{icon_row[0]}.png?size=256'
                    # Matrix spaces don't have a cached icon URL - leave as None

                    community = WebCommunity(
                        platform=ptype, platform_id=pid,
                        invite_url=p_invite_url, member_count=p_member_count,
                        icon_url=p_icon_url,
                        **shared_fields
                    )
                    db.add(community)
                    db.flush()
                    created_ids.append(community.id)

                # Link rows as one unified community when multiple platforms selected
                if len(created_ids) > 1:
                    group_id = created_ids[0]  # use the first row's id as the group anchor
                    db.query(WebCommunity).filter(WebCommunity.id.in_(created_ids)).update(
                        {'community_group_id': group_id}, synchronize_session=False
                    )

                first_id = created_ids[0]
            else:
                # No bot linked - single row with no platform_id
                community = WebCommunity(
                    platform=PlatformType.OTHER, platform_id=None,
                    invite_url=None, member_count=0,
                    **shared_fields
                )
                db.add(community)
                db.flush()
                first_id = community.id
            db.commit()

        return JsonResponse({'success': True, 'id': first_id})

    # GET: list communities (approved only, primary row per owner)
    with get_db_session() as db:
        from sqlalchemy import text as sa_text
        communities = db.query(WebCommunity).filter(
            WebCommunity.network_status == 'approved',
            WebCommunity.allow_discovery == True,
            WebCommunity.is_active == True,
            WebCommunity.is_banned == False,
            WebCommunity.is_primary == True,
        ).order_by(WebCommunity.member_count.desc()).limit(50).all()

        # Resolve live member counts from bot tables
        fluxer_counts = {str(r[0]): int(r[1]) for r in db.execute(sa_text(
            "SELECT guild_id, member_count FROM web_fluxer_guild_settings WHERE member_count > 0"
        )).fetchall()}
        discord_counts = {str(r[0]): int(r[1]) for r in db.execute(sa_text(
            "SELECT guild_id, member_count FROM guilds WHERE member_count > 0"
        )).fetchall()}

        data = []
        for c in communities:
            platform = c.platform.value if hasattr(c.platform, 'value') else str(c.platform)
            pid = str(c.platform_id or '')
            if platform == 'fluxer' and pid in fluxer_counts:
                live_count = fluxer_counts[pid]
            elif platform == 'discord' and pid in discord_counts:
                live_count = discord_counts[pid]
            else:
                live_count = c.member_count
            # Keep stored count in sync so ordering stays accurate
            if live_count != c.member_count:
                c.member_count = live_count
            data.append({
                'id': c.id,
                'slug': _community_slug(c.name),
                'name': c.name,
                'short_description': c.short_description,
                'description': c.description,
                'platform': platform,
                'icon_url': c.icon_url,
                'banner_url': c.banner_url,
                'member_count': live_count,
                'activity_level': c.activity_level,
                'allow_joins': c.allow_joins,
                'invite_url': c.invite_url if c.allow_joins else None,
                'tags': json.loads(c.tags or '[]'),
                'owner_id': c.owner_id,
                'guild_game': (json.loads(c.guild_game) if c.guild_game and c.guild_game.startswith('[') else ([c.guild_game] if c.guild_game else [])),
                'guild_game_name': c.guild_game_name or None,
                'games': json.loads(c.games or '[]'),
            })
        db.commit()

    return JsonResponse({'communities': data})


def _enrich_community_games(db, game_names):
    """Return list of {name, cover_url, steam_app_id, multiplayer} dicts for community games."""
    if not game_names:
        return []
    from sqlalchemy import text as _t
    result = []
    for name in game_names:
        row = db.execute(_t(
            "SELECT cover_url, steam_app_id FROM web_user_games "
            "WHERE name=:n LIMIT 1"
        ), {'n': name}).fetchone()
        cover = row[0] if row else None
        app_id = row[1] if row else None

        # Fall back to IGDB if no cover stored
        if not cover:
            cover = _igdb_cover_for_game(name)

        is_mp = name in _MULTIPLAYER_OVERRIDES
        if not is_mp:
            tag_rows = db.execute(_t(
                "SELECT DISTINCT t.tag_name FROM web_steam_app_tags t "
                "JOIN web_user_games g ON g.steam_app_id = t.app_id "
                "WHERE g.name = :name LIMIT 30"
            ), {'name': name}).fetchall()
            tags = {r[0].lower() for r in tag_rows}
            is_mp = bool(tags & _MULTIPLAYER_TAGS) or not tag_rows
        result.append({'name': name, 'cover_url': cover, 'steam_app_id': app_id, 'multiplayer': is_mp})
    return result


def _igdb_cover_for_game(name):
    """Look up a cover URL from IGDB by game name. Returns URL string or None."""
    try:
        import asyncio as _asyncio
        from app.utils.igdb import search_games as _igdb_search
        loop = _asyncio.new_event_loop()
        try:
            games = loop.run_until_complete(_igdb_search(name, limit=1))
        finally:
            loop.close()
        if games and games[0].cover_url:
            return games[0].cover_url
    except Exception:
        pass
    return None


_MULTIPLAYER_TAGS = {
    'multi-player', 'multiplayer', 'co-op', 'online co-op', 'co-op campaign',
    'local co-op', 'lan co-op', 'local multiplayer', 'massively multiplayer',
    'cross-platform multiplayer', 'online pvp', 'pvp', 'asynchronous multiplayer',
    'shared/split screen co-op',
}
# Games confirmed multiplayer but whose SteamSpy tags haven't caught up yet
_MULTIPLAYER_OVERRIDES = {
    'No Rest for the Wicked',
}



@add_web_user_context
@require_http_methods(["GET", "PUT"])
def api_community_detail(request, community_id):
    """API: Get community details (GET) or update it (PUT, owner only)."""
    with get_db_session() as db:
        community = db.query(WebCommunity).filter_by(id=community_id).first()
        if not community:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'PUT':
            if not request.web_user or community.owner_id != request.web_user.id:
                return JsonResponse({'error': 'Not your community'}, status=403)

            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

            name = (data.get('name') or '').strip()
            if not name or len(name) > 200:
                return JsonResponse({'error': 'Name is required (max 200 chars)'}, status=400)

            # Prevent platform type changes after registration
            if 'platform' in data and data['platform'] != community.platform.value:
                return JsonResponse({'error': 'Platform type cannot be changed after registration'}, status=400)

            raw_tags = data.get('tags') or []
            community.name = name
            community.short_description = (data.get('short_description') or '')[:500] or None
            community.description = data.get('description') or None
            community.invite_url = _validate_invite_url(data.get('invite_url'))
            community.website_url = _validate_voice_link(data.get('website_url'))
            community.twitch_url = _validate_social_url(data.get('twitch_url'))
            community.youtube_url = _validate_social_url(data.get('youtube_url'))
            community.twitter_url = _validate_social_url(data.get('twitter_url'))
            community.tags = json.dumps([t for t in raw_tags if isinstance(t, str)][:8])
            raw_games = data.get('games') or []
            community.games = json.dumps([g.strip() for g in raw_games if isinstance(g, str) and g.strip()][:20])
            community.member_count = safe_int(data.get('member_count') or community.member_count, default=community.member_count, min_val=0)
            VALID_ACTIVITY = {'unknown', 'dormant', 'squire', 'champion', 'legendary', 'mythic'}
            if data.get('activity_level') in VALID_ACTIVITY:
                community.activity_level = data['activity_level']
            community.allow_discovery = bool(data.get('allow_discovery', community.allow_discovery))
            community.allow_joins = bool(data.get('allow_joins', community.allow_joins))
            # In-game guild fields
            raw_guild_games = data.get('guild_game') or []
            if isinstance(raw_guild_games, str):
                raw_guild_games = [raw_guild_games] if raw_guild_games else []
            guild_games_clean = [g.strip().lower() for g in raw_guild_games if isinstance(g, str) and g.strip().lower() in VALID_GUILD_GAMES]
            community.guild_game = json.dumps(guild_games_clean) if guild_games_clean else None
            community.guild_game_name = (data.get('guild_game_name') or '')[:200].strip() or None
            # Owner can disable unified XP but cannot enable it - that requires admin approval
            if 'site_xp_to_guild' in data and not data['site_xp_to_guild']:
                community.site_xp_to_guild = False
            community.updated_at = int(time.time())
            db.commit()
            return JsonResponse({'success': True})

        # GET
        is_owner = bool(request.web_user and community.owner_id == request.web_user.id)

        # Auto-sync from platform API when owner loads - pull live member count and icon
        if is_owner:
            try:
                updated = False
                if community.platform == PlatformType.DISCORD and community.platform_id:
                    enc_token = getattr(request.web_user, 'discord_access_token_enc', None)
                    if enc_token:
                        import requests as _req
                        from app.utils.encryption import decrypt_token as _dec
                        token = _dec(enc_token)
                        resp = _req.get(
                            'https://discord.com/api/v10/users/@me/guilds',
                            headers={'Authorization': f'Bearer {token}'},
                            timeout=8,
                        )
                        if resp.status_code == 200:
                            for g in resp.json():
                                if g['id'] == str(community.platform_id):
                                    # member_count not in /guilds list - need /guilds/{id} (requires bot)
                                    # but we can update icon
                                    if g.get('icon') and not community.icon_url:
                                        community.icon_url = f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png?size=256"
                                        updated = True
                                    break
                elif community.platform == PlatformType.FLUXER and community.platform_id:
                    fluxer_settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=community.platform_id).first()
                    if fluxer_settings:
                        if fluxer_settings.member_count and fluxer_settings.member_count != community.member_count:
                            community.member_count = fluxer_settings.member_count
                            updated = True
                        if fluxer_settings.guild_icon_hash and not community.icon_url:
                            community.icon_url = f"https://cdn.fluxer.app/icons/{community.platform_id}/{fluxer_settings.guild_icon_hash}.png"
                            updated = True
                if updated:
                    community.updated_at = int(time.time())
                    db.commit()
            except Exception:
                pass

        # Final member count - prefer live Fluxer count
        member_count = community.member_count
        if community.platform == PlatformType.FLUXER and community.platform_id:
            fluxer_settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=community.platform_id).first()
            if fluxer_settings and fluxer_settings.member_count:
                member_count = fluxer_settings.member_count

        return JsonResponse({
            'id': community.id,
            'slug': _community_slug(community.name),
            'name': community.name,
            'short_description': community.short_description,
            'description': community.description,
            'platform': community.platform.value,
            'icon_url': community.icon_url,
            'banner_url': community.banner_url,
            'invite_url': community.invite_url if (community.allow_joins or is_owner) else None,
            'website_url': community.website_url,
            'twitch_url': community.twitch_url,
            'youtube_url': community.youtube_url,
            'twitter_url': community.twitter_url,
            'tags': json.loads(community.tags or '[]'),
            'member_count': member_count,
            'activity_level': community.activity_level,
            'allow_discovery': community.allow_discovery,
            'allow_joins': community.allow_joins,
            'site_xp_to_guild': bool(community.site_xp_to_guild),
            'guild_game': (json.loads(community.guild_game) if community.guild_game and community.guild_game.startswith('[') else ([community.guild_game] if community.guild_game else [])),
            'guild_game_name': community.guild_game_name or None,
            'games': _enrich_community_games(db, json.loads(community.games or '[]')),
            'is_owner': is_owner,
        })


@add_web_user_context
def api_creators(request):
    """API: List creators (GET) or save creator profile (POST).
    GET is intentionally public (no login required) - discovery is open browsing.
    POST requires login (enforced below via request.web_user check)."""
    if request.method == 'POST':
        if not request.web_user:
            return JsonResponse({'error': 'Login required'}, status=401)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        display_name = (data.get('display_name') or '').strip()
        if not display_name or len(display_name) > 100:
            return JsonResponse({'error': 'Display name is required (max 100 chars)'}, status=400)

        now = int(time.time())
        with get_db_session() as db:
            profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
            if not profile:
                profile = WebCreatorProfile(
                    user_id=request.web_user.id,
                    display_name=display_name,
                    allow_discovery=bool(data.get('allow_discovery', False)),
                    created_at=now,
                    updated_at=now,
                )
                db.add(profile)
            else:
                profile.display_name = display_name
                profile.updated_at = now

            profile.bio = (data.get('bio') or '')[:2000]
            profile.avatar_url = (data.get('avatar_url') or '')[:500] or None
            profile.banner_url = (data.get('banner_url') or '')[:500] or None
            # Only update social URLs if not OAuth-connected (OAuth sets these automatically)
            if not profile.twitch_user_id:
                profile.twitch_url = (data.get('twitch_url') or '')[:500] or None
            if not profile.youtube_channel_id:
                profile.youtube_url = (data.get('youtube_url') or '')[:500] or None
            profile.kick_url = (data.get('kick_url') or '')[:500] or None
            profile.twitter_url = (data.get('twitter_url') or '')[:500] or None
            profile.tiktok_url = (data.get('tiktok_url') or '')[:500] or None
            profile.instagram_url = (data.get('instagram_url') or '')[:500] or None
            profile.facebook_url = (data.get('facebook_url') or '')[:500] or None
            profile.website_url = (data.get('website_url') or '')[:500] or None
            profile.discord_url = (data.get('discord_url') or '')[:500] or None
            profile.matrix_url = (data.get('matrix_url') or '')[:500] or None
            profile.valor_url = (data.get('valor_url') or '')[:500] or None
            profile.fluxer_url = (data.get('fluxer_url') or '')[:500] or None
            profile.kloak_url = (data.get('kloak_url') or '')[:500] or None
            profile.teamspeak_url = (data.get('teamspeak_url') or '')[:500] or None
            profile.revolt_url = (data.get('revolt_url') or '')[:500] or None
            # Extract kick slug from URL for live status checks
            kick_url = profile.kick_url or ''
            if kick_url and 'kick.com/' in kick_url:
                profile.kick_slug = kick_url.rstrip('/').split('/')[-1] or None
            elif not kick_url:
                profile.kick_slug = None
            profile.allow_discovery = bool(data.get('allow_discovery', True))
            profile.show_steam_on_profile = bool(data.get('show_steam_on_profile', False))
            db.commit()

            return JsonResponse({'success': True, 'id': profile.id})

    # GET: list creators — live first, then COTW/COTM, then by follower count
    with get_db_session() as db:
        from sqlalchemy.orm import aliased
        Community = aliased(WebCommunity)
        rows = db.query(WebCreatorProfile, WebUser, Community).join(
            WebUser, WebUser.id == WebCreatorProfile.user_id
        ).outerjoin(
            Community, Community.id == WebUser.primary_community_id
        ).filter(
            WebCreatorProfile.allow_discovery == True
        ).order_by(
            WebUser.is_live.desc(),
            WebCreatorProfile.is_current_cotm.desc(),
            WebCreatorProfile.is_current_cotw.desc(),
            WebCreatorProfile.follower_count.desc(),
        ).limit(50).all()

        _STABLE_CDN = ('https://static-cdn.jtvnw.net/', 'https://yt3.', 'https://yt3.ggpht.')
        def _resolve_avatar(creator_avatar, user_avatar):
            """Prefer local upload. Also allow Twitch/YouTube CDN (stable).
            Skip Discord CDN URLs (they expire). Fall back to web user's local avatar."""
            if creator_avatar:
                if creator_avatar.startswith('/media/'):
                    return creator_avatar
                if any(creator_avatar.startswith(cdn) for cdn in _STABLE_CDN):
                    return creator_avatar
            if user_avatar and user_avatar.startswith('/media/'):
                return user_avatar
            return None

        data = [{
            'id': c.id,
            'username': u.username,
            'display_name': c.display_name,
            'bio': c.bio,
            'avatar_url': _resolve_avatar(c.avatar_url, u.avatar_url),
            'banner_url': c.banner_url,
            'twitch_url': c.twitch_url,
            'youtube_url': c.youtube_url,
            'kick_url': c.kick_url,
            'tiktok_url': c.tiktok_url,
            'twitter_url': c.twitter_url,
            'instagram_url': c.instagram_url,
            'facebook_url': c.facebook_url,
            'bluesky_url': c.bluesky_url,
            'website_url': c.website_url,
            'discord_url': c.discord_url,
            'matrix_url': c.matrix_url,
            'fluxer_url': c.fluxer_url,
            'kick_follower_count': c.kick_follower_count or 0,
            'categories': json.loads(c.categories or '[]'),
            'games': json.loads(c.games or '[]'),
            'is_verified': c.is_verified,
            'follower_count': c.follower_count,
            'twitch_follower_count': c.twitch_follower_count or 0,
            'youtube_subscriber_count': c.youtube_subscriber_count or 0,
            'is_current_cotw': c.is_current_cotw,
            'is_current_cotm': c.is_current_cotm,
            'is_live': bool(u.is_live),
            'live_platform': u.live_platform or '',
            'live_title': u.live_title or '',
            'live_url': u.live_url or '',
            # Rich card extras
            'current_game': u.current_game or '',
            'current_game_appid': u.current_game_appid or 0,
            'show_steam_on_profile': bool(c.show_steam_on_profile),
            'primary_community_name': comm.name if comm else '',
            'primary_community_platform': comm.platform.value if comm else '',
            'primary_community_icon_url': comm.icon_url or '' if comm else '',
            'latest_youtube_video_id': c.latest_youtube_video_id or '',
            'latest_youtube_video_title': c.latest_youtube_video_title or '',
            'latest_youtube_thumbnail_url': c.latest_youtube_thumbnail_url or '',
            'latest_youtube_video_published_at': c.latest_youtube_video_published_at or 0,
            'latest_stream_title': c.latest_stream_title or '',
            'latest_stream_thumbnail_url': c.latest_stream_thumbnail_url or '',
            'latest_stream_platform': c.latest_stream_platform or '',
            'latest_stream_ended_at': c.latest_stream_ended_at or 0,
        } for c, u, comm in rows]

    return JsonResponse({'creators': data})


@add_web_user_context
def api_games(request):
    """API: List/search found games. Returns full data for client-side filtering.
    Intentionally public - no login required (read-only discovery endpoint)."""
    with get_db_session() as db:
        ADULT_TAGS = ['Sexual Content', 'Adult Only Sexual Content', 'Frequent Nudity or Sexual Content', 'Hentai', 'Eroge', 'Explicit Sexual Content']
        from sqlalchemy import and_
        tag_filters = [~WebFoundGame.genres.ilike(f'%{tag}%') for tag in ADULT_TAGS]
        games = (
            db.query(WebFoundGame)
            .filter(WebFoundGame.is_hidden == False)
            .filter(and_(*tag_filters))
            .order_by(WebFoundGame.found_at.desc())
            .all()
        )

        data = [{
            'id': g.id,
            'name': g.name,
            'cover_url': g.cover_url,
            'header_url': g.header_url,
            'steam_app_id': g.steam_app_id,
            'steam_url': g.steam_url,
            'igdb_url': getattr(g, 'igdb_url', None),
            'summary': g.summary,
            'release_date': g.release_date,
            'developer': g.developer,
            'price': g.price,
            'review_score': g.review_score,
            'review_count': g.review_count,
            'genres': json.loads(g.genres or '[]'),
            'platforms': json.loads(g.platforms or '[]'),
            'console_platforms': json.loads(getattr(g, 'console_platforms', None) or '[]'),
            'is_featured': g.is_featured,
            'found_at': g.found_at,
        } for g in games]

    return JsonResponse({'games': data})


@add_web_user_context
def api_articles(request):
    """API: List RSS articles. Intentionally public - no login required (read-only)."""
    with get_db_session() as db:
        articles = db.query(WebRSSArticle).order_by(
            WebRSSArticle.published_at.desc()
        ).limit(50).all()

        data = [{
            'id': a.id,
            'title': a.title,
            'url': a.url,
            'summary': a.summary,
            'author': a.author,
            'image_url': a.image_url,
            'published_at': a.published_at,
        } for a in articles]

    return JsonResponse({'articles': data})


@require_http_methods(["GET"])
@ratelimit(key='header:cf-connecting-ip', rate='60/m', block=True)
def api_steam_game_search(request):
    """API: Search Steam store for games. Used by game suggest autocomplete.
    ?q=<query>  (min 2 chars)
    Returns: [{appid, name, header_url, tiny_image}]
    """
    import requests as _requests
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'results': []})
    try:
        resp = _requests.get(
            'https://store.steampowered.com/api/storesearch/',
            params={'term': q, 'cc': 'US', 'l': 'english'},
            timeout=5,
        )
        resp.raise_for_status()
        items = resp.json().get('items', [])[:8]
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
        logger.warning('api_steam_game_search: %s', e)
        return JsonResponse({'results': []})


@require_http_methods(["GET"])
@ratelimit(key='header:cf-connecting-ip', rate='60/m', block=True)
def api_steam_app_details(request):
    """API: Fetch Steam app details for game suggest enrichment.
    ?appid=<steam_app_id>
    Returns: {description, genres, tags, recommendations, metacritic, trailer_thumbnail}
    """
    import requests as _requests
    appid = safe_int(request.GET.get('appid', 0) or 0, default=0)
    if not appid:
        return JsonResponse({'error': 'appid required'}, status=400)
    try:
        resp = _requests.get(
            'https://store.steampowered.com/api/appdetails',
            params={'appids': appid, 'cc': 'US', 'l': 'english'},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json().get(str(appid), {})
        if not data.get('success'):
            return JsonResponse({'error': 'not found'}, status=404)
        d = data.get('data', {})
        movies = d.get('movies') or []
        trailer_thumb = movies[0].get('thumbnail') if movies else None
        genres = [g['description'] for g in (d.get('genres') or [])]
        categories = [c['description'] for c in (d.get('categories') or [])[:6]]
        recs = (d.get('recommendations') or {}).get('total')
        meta = (d.get('metacritic') or {}).get('score')
        return JsonResponse({
            'description': d.get('short_description', ''),
            'genres': genres,
            'categories': categories,
            'recommendations': recs,
            'metacritic': meta,
            'trailer_thumbnail': trailer_thumb,
        })
    except Exception as e:
        logger.warning('api_steam_app_details: %s', e)
        return JsonResponse({'error': 'Steam API error'}, status=502)


@require_http_methods(["GET"])
@ratelimit(key='header:cf-connecting-ip', rate='60/m', block=True)
def api_igdb_search(request):
    """API: Search IGDB directly for games. Used by LFG create/browse autocomplete.
    No login required — IGDB is public game data.
    ?q=<query>  (min 2 chars)
    ?limit=<n>  (max 10)
    """
    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'games': []})

    limit = safe_int(request.GET.get('limit', 8) or 8, default=8, min_val=1, max_val=10)

    try:
        from app.utils.igdb import search_games

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            games = loop.run_until_complete(search_games(q, limit=limit))
        finally:
            loop.close()

        # Enrich steam_id for games IGDB doesn't have a Steam mapping for.
        # Priority: IGDB external_games > web_found_games > web_lfg_game_configs > web_users.current_game_appid
        game_names_no_steam = [g.name for g in games if not g.steam_id]
        steam_id_by_name = {}
        if game_names_no_steam:
            with get_db_session() as db:
                # 1. web_found_games (Steam-scraped, most reliable)
                for row in db.query(WebFoundGame.name, WebFoundGame.steam_app_id).filter(
                    WebFoundGame.name.in_(game_names_no_steam)
                ).all():
                    steam_id_by_name[row.name] = row.steam_app_id

                # 2. web_lfg_game_configs (admin-configured LFG games with known Steam IDs)
                still_missing = [n for n in game_names_no_steam if n not in steam_id_by_name]
                if still_missing:
                    for row in db.query(WebLFGGameConfig.game_name, WebLFGGameConfig.steam_app_id).filter(
                        WebLFGGameConfig.game_name.in_(still_missing),
                        WebLFGGameConfig.steam_app_id.isnot(None),
                    ).all():
                        steam_id_by_name[row.game_name] = row.steam_app_id

                # 3. web_users.current_game_appid - players actively playing this game right now
                still_missing = [n for n in game_names_no_steam if n not in steam_id_by_name]
                if still_missing:
                    for row in db.query(WebUser.current_game, WebUser.current_game_appid).filter(
                        WebUser.current_game.in_(still_missing),
                        WebUser.current_game_appid.isnot(None),
                    ).distinct(WebUser.current_game).all():
                        steam_id_by_name[row.current_game] = row.current_game_appid

        # 4. Steam store search fallback for any still-missing steam_ids (exact name match only)
        still_missing = [g.name for g in games if not (g.steam_id or steam_id_by_name.get(g.name))]
        if still_missing:
            import requests as _requests
            for name in still_missing[:3]:  # cap at 3 to avoid slow searches
                try:
                    resp = _requests.get(
                        'https://store.steampowered.com/api/storesearch/',
                        params={'term': name, 'cc': 'US', 'l': 'english'},
                        timeout=3,
                    )
                    if resp.status_code == 200:
                        items = resp.json().get('items', [])
                        for item in items:
                            if item.get('name', '').lower() == name.lower() and item.get('id'):
                                steam_id_by_name[name] = item['id']
                                break
                except Exception:
                    pass

        data = [{
            'id': g.id,
            'name': g.name,
            'cover_url': g.cover_url,
            'platforms': ', '.join(g.platforms[:3]) if g.platforms else '',
            'release_year': g.release_year,
            'steam_id': g.steam_id or steam_id_by_name.get(g.name),
            'game_modes': g.game_modes if g.game_modes else [],
        } for g in games]

        return JsonResponse({'games': data})

    except Exception as e:
        logger.error(f"IGDB search error: {e}", exc_info=True)
        return JsonResponse({'games': []})


@add_web_user_context
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='60/m', block=True)
def api_gamers(request):
    """API: Searchable gamers directory.
    ?q=<search>          - search username/display_name/bio
    ?platform=<val>      - filter by gaming_platforms (pc, ps5, xbox, mobile, switch)
    ?playstyle=<val>     - filter by playstyle (casual, competitive, etc.)
    ?sort=followers|new  - sort order (default: followers)
    ?page=<n>            - pagination (20 per page)
    """
    q = request.GET.get('q', '').strip()
    platform_filter = request.GET.get('platform', '').strip().lower()
    playstyle_filter = request.GET.get('playstyle', '').strip().lower()
    sort = request.GET.get('sort', 'followers')
    page = safe_int(request.GET.get('page', 1) or 1, default=1, min_val=1, max_val=500)
    per_page = 20

    try:
        with get_db_session() as db:
            current_uid = request.web_user.id if request.web_user else None

            query = db.query(WebUser).filter(
                WebUser.is_banned == False,
                WebUser.is_disabled == False,
                WebUser.email_verified == True,
                WebUser.allow_discovery == True,
                ~WebUser.id.in_(EXCLUDED_USER_IDS),
            )

            # Don't exclude the logged-in user - they should see themselves in the directory

            if q:
                like = f'%{q}%'
                from sqlalchemy import or_
                query = query.filter(or_(
                    WebUser.username.ilike(like),
                    WebUser.display_name.ilike(like),
                    WebUser.bio.ilike(like),
                ))

            if platform_filter:
                query = query.filter(WebUser.gaming_platforms.ilike(f'%{platform_filter}%'))

            if playstyle_filter:
                query = query.filter(WebUser.playstyle.ilike(f'%{playstyle_filter}%'))

            if sort == 'new':
                query = query.order_by(WebUser.created_at.desc())
            elif sort == 'followers':
                query = query.order_by(WebUser.follower_count.desc(), WebUser.created_at.desc())
            else:
                query = query.order_by(WebUser.username.asc())

            total = query.count()
            offset = (page - 1) * per_page
            users = query.offset(offset).limit(per_page).all()

            # Build mutual follow set for logged-in user
            mutual_ids = set()
            if current_uid:
                page_ids = [u.id for u in users]
                i_follow = {r.following_id for r in db.query(WebFollow.following_id).filter(
                    WebFollow.follower_id == current_uid,
                    WebFollow.following_id.in_(page_ids),
                ).all()}
                they_follow = {r.follower_id for r in db.query(WebFollow.follower_id).filter(
                    WebFollow.following_id == current_uid,
                    WebFollow.follower_id.in_(page_ids),
                ).all()}
                mutual_ids = i_follow & they_follow

            data = []
            for u in users:
                data.append({
                    'id': u.id,
                    'username': u.username,
                    'display_name': u.display_name or u.username,
                    'avatar_url': u.avatar_url or '',
                    'bio': (u.bio or '')[:120],
                    'follower_count': u.follower_count or 0,
                    'post_count': u.post_count or 0,
                    'web_level': u.web_level or 1,
                    'gaming_platforms': json.loads(u.gaming_platforms) if u.gaming_platforms else [],
                    'playstyle': (
                        json.loads(u.playstyle) if u.playstyle and u.playstyle.startswith('[')
                        else ([u.playstyle] if u.playstyle else [])
                    ),
                    'twitch_username': u.twitch_username or '',
                    'youtube_channel_name': u.youtube_channel_name or '',
                    'is_live': bool(u.is_live),
                    'live_platform': u.live_platform or '',
                    'live_url': u.live_url or '',
                    'current_game': (u.current_game if u.show_playing_status else None) or '',
                    'is_admin': bool(u.is_admin),
                    'is_mod': bool(u.is_mod),
                    'is_contributor': bool(u.is_contributor),
                    'is_ffxiv_member': bool(u.is_ffxiv_member),
                    'is_eso_member': bool(u.is_eso_member),
                    'can_message': bool(u.id in mutual_ids and u.allow_messages and u.id != current_uid),
                })

            return JsonResponse({
                'users': data,
                'total': total,
                'page': page,
                'pages': max(1, (total + per_page - 1) // per_page),
            })

    except Exception as e:
        logger.error(f"api_gamers error: {e}", exc_info=True)
        return JsonResponse({'users': [], 'total': 0, 'page': 1, 'pages': 1})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='10/h', block=True)
def api_lfg_broadcast_network(request, group_id):
    """
    POST /api/lfg/<id>/broadcast-network/
    Queues LFG broadcast to all subscribed communities on the QuestLog Network.
    - Fluxer guilds -> fluxer_pending_broadcasts (polled by QuestLogFluxer bot)
    - Discord guilds -> discord_pending_broadcasts (polled by WardenBot)
    Rate-limited to 10/h per user.
    """
    with get_db_session() as db:
        lfg = db.query(WebLFGGroup).filter_by(id=group_id, creator_id=request.web_user.id).first()
        if not lfg:
            return JsonResponse({'error': 'LFG not found or not yours'}, status=404)
        if lfg.status not in ('open', 'full'):
            return JsonResponse({'error': 'LFG is not active'}, status=400)

        configs = db.query(WebCommunityBotConfig).filter_by(
            event_type='lfg_announce'
        ).all()

        if not configs:
            return JsonResponse({'success': True, 'queued': 0, 'message': 'No communities subscribed yet'})

        creator_name = request.web_user.display_name or request.web_user.username
        group_url = f"https://casual-heroes.com/ql/lfg/{lfg.share_token or lfg.id}/"
        _broadcast_game = lfg.game_name.lower() if lfg.game_name else ''

        # Build the embed using the same builder as guild webhooks (identical card layout)
        role_schema = _parse_role_schema(lfg.role_schema)
        embed_data = _build_lfg_embed_data(
            creator=creator_name,
            game_name=lfg.game_name,
            title=lfg.title,
            description=lfg.description or '',
            group_size=lfg.group_size,
            current_size=lfg.current_size,
            scheduled_time=lfg.scheduled_time,
            lfg_url=group_url,
            game_image_url=lfg.game_image_url,
            tanks_needed=lfg.tanks_needed or 0,
            healers_needed=lfg.healers_needed or 0,
            dps_needed=lfg.dps_needed or 0,
            support_needed=lfg.support_needed or 0,
            use_roles=bool(lfg.use_roles),
            role_schema=role_schema,
            duration_hours=lfg.duration_hours,
            group_id=lfg.id,
            voice_link=lfg.voice_link,
            group_platform='web',
        )

        embed_data["color"] = 0xFEE75C  # gold - matches QuestLog Network brand

        origin = lfg.origin_platform or 'web'
        if origin == 'fluxer':
            origin_label = "Fluxer"
        elif origin == 'discord':
            origin_label = "Discord"
        else:
            origin_label = "QuestLog Web"

        embed_data["footer"] = "QuestLog Network - casual-heroes.com/ql/lfg/"
        embed_data["fields"].append({"name": "Posted via", "value": origin_label, "inline": True})
        embed_data["thread_name"] = f"{lfg.title} - {lfg.game_name} - {creator_name}"

        payload_json = json.dumps(embed_data)
        now_ts = int(time.time())
        fluxer_count = 0
        discord_count = 0

        for cfg in configs:
            # Per-game opt-in: find the channel configured for this specific game
            if cfg.platform == 'discord':
                _game_row = db.execute(text(
                    "SELECT lfg_channel_id FROM lfg_games WHERE guild_id=:g AND LOWER(game_name)=:gn "
                    "AND receive_network_lfg=1 AND enabled=1 LIMIT 1"
                ), {"g": int(cfg.guild_id), "gn": _broadcast_game}).fetchone()
            else:
                _game_row = db.execute(text(
                    "SELECT channel_id FROM web_fluxer_lfg_games WHERE guild_id=:g AND LOWER(name)=:gn "
                    "AND receive_network_lfg=1 AND enabled=1 AND is_active=1 LIMIT 1"
                ), {"g": cfg.guild_id, "gn": _broadcast_game}).fetchone()

            if not _game_row:
                continue

            _dest_channel = str(_game_row[0]).strip() if _game_row[0] else cfg.channel_id
            if not _dest_channel:
                continue

            if cfg.platform == 'discord':
                db.execute(
                    text(
                        "INSERT INTO discord_pending_broadcasts "
                        "(guild_id, channel_id, payload, created_at) "
                        "VALUES (:guild_id, :channel_id, :payload, :now)"
                    ),
                    {
                        "guild_id": int(cfg.guild_id),
                        "channel_id": int(_dest_channel),
                        "payload": payload_json,
                        "now": now_ts,
                    },
                )
                discord_count += 1
            else:
                db.execute(
                    text(
                        "INSERT INTO fluxer_pending_broadcasts "
                        "(guild_id, channel_id, payload, created_at) "
                        "VALUES (:guild_id, :channel_id, :payload, :now)"
                    ),
                    {
                        "guild_id": cfg.guild_id,
                        "channel_id": _dest_channel,
                        "payload": payload_json,
                        "now": now_ts,
                    },
                )
                fluxer_count += 1

        db.commit()

    total = fluxer_count + discord_count
    logger.info(f"LFG {group_id} broadcast: {fluxer_count} Fluxer, {discord_count} Discord")
    return JsonResponse({'success': True, 'queued': total, 'fluxer': fluxer_count, 'discord': discord_count})


@require_http_methods(["GET"])
def api_lfg_community_guilds(request):
    """GET /api/lfg/community-guilds/ - All guilds (Fluxer + Discord) with LFG configured."""
    with get_db_session() as db:
        rows = db.query(WebCommunityBotConfig).filter_by(
            event_type='lfg_announce', is_enabled=True
        ).filter(WebCommunityBotConfig.channel_id.isnot(None)).order_by(
            WebCommunityBotConfig.guild_name
        ).all()

        data = [
            {
                'guild_id': str(c.guild_id),
                'guild_name': c.guild_name or 'Unnamed Server',
                'channel_name': c.channel_name,
                'platform': c.platform,
            }
            for c in rows
            if 'test' not in (c.guild_name or '').lower()
        ]
    return JsonResponse({'guilds': data, 'total': len(data)})


# ---------------------------------------------------------------------------
# Fluxer LFG management (requires linked Fluxer account)
# ---------------------------------------------------------------------------

def _get_fluxer_post_for_user(db, post_id, web_user):
    """Return a Fluxer LFG post row if it exists and the user owns it. Raises ValueError otherwise."""
    if not web_user:
        raise ValueError("login_required")
    fluxer_id = getattr(web_user, 'fluxer_id', None)
    if not fluxer_id:
        raise ValueError("no_fluxer_link")
    row = db.execute(
        text("SELECT id, user_id FROM fluxer_lfg_posts WHERE id = :id"),
        {"id": post_id},
    ).fetchone()
    if not row:
        raise ValueError("not_found")
    if str(row.user_id) != str(fluxer_id):
        raise ValueError("forbidden")
    return row


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='30/m', block=True)
def api_lfg_fluxer_edit(request, post_id):
    """POST /api/lfg/fluxer/<id>/edit/ - Edit a Fluxer LFG post the user created."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        with get_db_session() as db:
            _get_fluxer_post_for_user(db, post_id, request.web_user)

            _LFG_FLUXER_EDIT_ALLOWED_COLS = {'description', 'group_size', 'scheduled_time', 'status'}

            updates = {}
            if 'description' in data and data['description'] is not None:
                from .helpers import sanitize_text
                updates['description'] = sanitize_text(str(data['description'])[:500])
            if 'group_size' in data:
                updates['group_size'] = safe_int(data['group_size'], default=4, min_val=2, max_val=40)
            if 'scheduled_time' in data and data['scheduled_time'] is not None:
                updates['scheduled_time'] = safe_int(data['scheduled_time'], default=None, min_val=0, max_val=9999999999)

            updates = {k: v for k, v in updates.items() if k in _LFG_FLUXER_EDIT_ALLOWED_COLS}
            if not updates:
                return JsonResponse({'error': 'No valid fields to update'}, status=400)
            set_clause = ', '.join(f"{k} = :{k}" for k in updates)
            updates['post_id'] = post_id
            db.execute(
                text(f"UPDATE fluxer_lfg_posts SET {set_clause} WHERE id = :post_id"),
                updates,
            )
        return JsonResponse({'success': True})
    except ValueError as e:
        err = str(e)
        if err == 'login_required':
            return JsonResponse({'error': 'Login required'}, status=401)
        if err == 'no_fluxer_link':
            return JsonResponse({'error': 'Link your Fluxer account first in Settings'}, status=403)
        if err in ('not_found', 'forbidden'):
            return JsonResponse({'error': 'Post not found or not yours'}, status=404)
        raise


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='30/m', block=True)
def api_lfg_fluxer_close(request, post_id):
    """POST /api/lfg/fluxer/<id>/close/ - Cancel/close a Fluxer LFG post."""
    try:
        with get_db_session() as db:
            _get_fluxer_post_for_user(db, post_id, request.web_user)
            db.execute(
                text("UPDATE fluxer_lfg_posts SET is_active = 0 WHERE id = :id"),
                {"id": post_id},
            )
        return JsonResponse({'success': True})
    except ValueError as e:
        err = str(e)
        if err == 'login_required':
            return JsonResponse({'error': 'Login required'}, status=401)
        if err == 'no_fluxer_link':
            return JsonResponse({'error': 'Link your Fluxer account first in Settings'}, status=403)
        return JsonResponse({'error': 'Post not found or not yours'}, status=404)


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='30/m', block=True)
def api_lfg_fluxer_mark_full(request, post_id):
    """POST /api/lfg/fluxer/<id>/mark-full/ - Mark a Fluxer LFG post as full (closes it)."""
    try:
        with get_db_session() as db:
            row = _get_fluxer_post_for_user(db, post_id, request.web_user)
            # Mark full: set current_size = group_size and deactivate
            db.execute(
                text(
                    "UPDATE fluxer_lfg_posts SET is_active = 0, "
                    "description = CONCAT(COALESCE(description, ''), ' [GROUP FULL]') "
                    "WHERE id = :id"
                ),
                {"id": post_id},
            )
        return JsonResponse({'success': True})
    except ValueError as e:
        err = str(e)
        if err == 'login_required':
            return JsonResponse({'error': 'Login required'}, status=401)
        if err == 'no_fluxer_link':
            return JsonResponse({'error': 'Link your Fluxer account first in Settings'}, status=403)
        return JsonResponse({'error': 'Post not found or not yours'}, status=404)


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='20/m', block=True)
def api_lfg_fluxer_guild_close(request, group_id):
    """POST /api/lfg/fluxer-guild/<id>/close/ - Creator closes their Fluxer guild LFG group."""
    if not request.web_user:
        return JsonResponse({'error': 'Login required'}, status=401)

    viewer_id = request.web_user.id
    _fid = getattr(request.web_user, 'fluxer_id', None)
    my_fid = str(_fid) if _fid else None

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        is_creator = (
            (my_fid and group.creator_fluxer_id and my_fid == str(group.creator_fluxer_id)) or
            (viewer_id and group.creator_web_user_id == viewer_id)
        )
        if not is_creator:
            return JsonResponse({'error': 'Not the group creator'}, status=403)

        group.status = 'closed'
        group.closed_at = int(time.time())
        db.commit()

    return JsonResponse({'success': True})


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='20/m', block=True)
def api_lfg_fluxer_guild_edit(request, group_id):
    """POST /api/lfg/fluxer-guild/<id>/edit/ - Creator edits their group details."""
    if not request.web_user:
        return JsonResponse({'error': 'Login required'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    viewer_id = request.web_user.id
    _fid = getattr(request.web_user, 'fluxer_id', None)
    my_fid = str(_fid) if _fid else None

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        is_creator = (
            (my_fid and group.creator_fluxer_id and my_fid == str(group.creator_fluxer_id)) or
            (viewer_id and group.creator_web_user_id == viewer_id)
        )
        if not is_creator:
            return JsonResponse({'error': 'Not the group creator'}, status=403)

        if 'title' in data:
            t = (data['title'] or '').strip()[:200]
            if not t:
                return JsonResponse({'error': 'Title cannot be empty'}, status=400)
            group.title = t
        if 'description' in data:
            group.description = (data.get('description') or '')[:2000] or None
        if 'max_size' in data:
            group.max_size = safe_int(data['max_size'], default=group.max_size, min_val=2, max_val=100)
        if 'scheduled_time' in data:
            st = data.get('scheduled_time')
            group.scheduled_time = safe_int(st, default=0, min_val=1, max_val=9999999999) if st else None

        if group.current_size >= group.max_size:
            group.status = 'full'
        elif group.status == 'full':
            group.status = 'open'
        db.commit()

    return JsonResponse({'success': True})


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='30/m', block=True)
def api_lfg_fluxer_guild_update_member(request, group_id):
    """POST /api/lfg/fluxer-guild/<id>/update-member/ - Member updates their class/role."""
    if not request.web_user:
        return JsonResponse({'error': 'Login required'}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    viewer_id = request.web_user.id
    _fid = getattr(request.web_user, 'fluxer_id', None)
    my_fid = str(_fid) if _fid else None

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        if group.status == 'closed':
            return JsonResponse({'error': 'Group is closed'}, status=400)

        member = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id == group_id,
            WebFluxerLfgMember.left_at.is_(None),
        ).filter(
            (WebFluxerLfgMember.web_user_id == viewer_id) |
            ((WebFluxerLfgMember.fluxer_user_id == my_fid) if my_fid else False)
        ).first()

        if not member:
            return JsonResponse({'error': 'You are not in this group'}, status=403)

        role = (data.get('role') or 'member')[:20]
        selections = data.get('selections') or {}
        if not isinstance(selections, dict):
            selections = {}

        member.role = role
        member.selections_json = json.dumps(selections) if selections else None
        db.commit()

    return JsonResponse({'success': True})


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='10/m', block=True)
def api_lfg_fluxer_guild_reopen(request, group_id):
    """POST /api/lfg/fluxer-guild/<id>/reopen/ - Creator reopens a closed group."""
    if not request.web_user:
        return JsonResponse({'error': 'Login required'}, status=401)

    viewer_id = request.web_user.id
    _fid = getattr(request.web_user, 'fluxer_id', None)
    my_fid = str(_fid) if _fid else None

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        is_creator = (
            (my_fid and group.creator_fluxer_id and my_fid == str(group.creator_fluxer_id)) or
            (viewer_id and group.creator_web_user_id == viewer_id)
        )
        if not is_creator:
            return JsonResponse({'error': 'Not the group creator'}, status=403)

        group.status = 'full' if group.current_size >= group.max_size else 'open'
        group.closed_at = None
        db.commit()

    return JsonResponse({'success': True})


@add_web_user_context
@web_login_required
@require_http_methods(["GET"])
def api_lfg_fluxer_guild_my_closed(request):
    """GET /api/lfg/fluxer-guild/my-closed/ - Creator's own closed groups (last 30 days)."""
    if not request.web_user:
        return JsonResponse({'error': 'Login required'}, status=401)

    viewer_id = request.web_user.id
    _fid = getattr(request.web_user, 'fluxer_id', None)
    my_fid = str(_fid) if _fid else None

    cutoff = int(time.time()) - 86400 * 30
    groups = []
    with get_db_session() as db:
        from sqlalchemy import or_ as _or
        q = db.query(WebFluxerLfgGroup).filter(
            WebFluxerLfgGroup.status == 'closed',
            WebFluxerLfgGroup.created_at > cutoff,
        )
        conditions = []
        if viewer_id:
            conditions.append(WebFluxerLfgGroup.creator_web_user_id == viewer_id)
        if my_fid:
            conditions.append(WebFluxerLfgGroup.creator_fluxer_id == my_fid)
        if not conditions:
            return JsonResponse({'groups': []})
        q = q.filter(_or(*conditions))
        raw = q.order_by(WebFluxerLfgGroup.created_at.desc()).limit(20).all()

        game_ids = list({g.game_id for g in raw if g.game_id})
        guild_ids = list({g.guild_id for g in raw})
        cover_map = {}
        guild_map = {}

        if game_ids:
            for gr in db.query(WebFluxerLfgGame).filter(WebFluxerLfgGame.id.in_(game_ids)).all():
                if gr.id not in cover_map and gr.cover_url:
                    cover_map[gr.id] = gr.cover_url

        if guild_ids:
            for r in db.query(
                WebFluxerGuildChannel.guild_id,
                WebFluxerGuildChannel.guild_name,
            ).filter(
                WebFluxerGuildChannel.guild_id.in_(guild_ids),
                WebFluxerGuildChannel.guild_name.isnot(None),
                WebFluxerGuildChannel.guild_name != '',
            ).all():
                if r.guild_id not in guild_map:
                    guild_map[r.guild_id] = r.guild_name

        for g in raw:
            groups.append({
                'id': f'guild_lfg_{g.id}',
                'guild_lfg_id': g.id,
                'title': g.title or g.game_name,
                'game_name': g.game_name,
                'game_id': g.game_id,
                'game_image_url': cover_map.get(g.game_id) if g.game_id else None,
                'group_size': g.max_size,
                'current_size': g.current_size,
                'scheduled_time': g.scheduled_time,
                'status': g.status,
                'created_at': g.created_at,
                'platform': 'fluxer_guild',
                'guild_id': g.guild_id,
                'guild_name': guild_map.get(g.guild_id, 'Unknown Server'),
                'creator_name': g.creator_name,
                'is_creator': True,
                'is_member': True,
            })

    return JsonResponse({'groups': groups})


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='20/m', block=True)
def api_lfg_fluxer_guild_join(request, group_id):
    """POST /api/lfg/fluxer-guild/<id>/join/ - Join a Fluxer guild LFG group via web."""
    if not request.web_user:
        return JsonResponse({'error': 'Login required'}, status=401)

    viewer_id = request.web_user.id

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        if group.status == 'closed':
            return JsonResponse({'error': 'Group is closed'}, status=400)
        if group.current_size >= group.max_size:
            return JsonResponse({'error': 'Group is full'}, status=400)

        existing = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id == group_id,
            WebFluxerLfgMember.web_user_id == viewer_id,
            WebFluxerLfgMember.left_at.is_(None),
        ).first()
        if existing:
            return JsonResponse({'error': 'Already in this group'}, status=400)

        member = WebFluxerLfgMember(
            group_id=group_id,
            web_user_id=viewer_id,
            username=request.web_user.username or '',
            role='member',
            is_creator=0,
            joined_at=int(time.time()),
        )
        db.add(member)
        group.current_size = group.current_size + 1
        if group.current_size >= group.max_size:
            group.status = 'full'

        # Capture for post-commit notification
        notify_guild_id = group.guild_id
        notify_channel_id = group.channel_id
        notify_game = group.game_name
        notify_title = group.title or group.game_name
        group_creator_web_user_id = group.creator_web_user_id
        joiner_name = request.web_user.display_name or request.web_user.username
        joiner_username = request.web_user.username
        new_size = group.current_size
        new_status = group.status

        db.commit()

    # Site notification to group creator (if they have a web account)
    if group_creator_web_user_id:
        try:
            with get_db_session() as db:
                create_notification(
                    db, group_creator_web_user_id, viewer_id,
                    'lfg_join',
                    target_type='fluxer_lfg_group', target_id=group_id,
                    message=f"{joiner_name} joined your LFG group: {notify_title}",
                )
                db.commit()
        except Exception as e:
            logger.warning(f"[LFG] Failed to create site join notification for Fluxer group {group_id}: {e}")

    # Send join notification to the Fluxer guild channel
    if notify_channel_id and notify_guild_id:
        try:
            lfg_url = f"https://casual-heroes.com/ql/fluxer/{notify_guild_id}/lfg/browse/"
            embed_data = {
                "title": f"New Member Joined: {notify_title}",
                "description": (
                    f"**{joiner_name}** joined the group from the QuestLog site.\n"
                    f"[View on QuestLog]({lfg_url})"
                ),
                "color": 0x57F287,
                "fields": [
                    {"name": "Game", "value": notify_game, "inline": True},
                    {"name": "Profile", "value": f"casual-heroes.com/ql/profile/{joiner_username}/", "inline": True},
                ],
                "footer": "QuestLog Network - casual-heroes.com/ql/lfg/",
            }
            with get_db_session() as db:
                db.execute(
                    text("INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at) VALUES (:g, :c, :p, :t)"),
                    {"g": notify_guild_id, "c": notify_channel_id, "p": json.dumps(embed_data), "t": int(time.time())}
                )
                db.commit()
        except Exception as e:
            logger.warning(f"[LFG] Failed to queue Fluxer join notification for group {group_id}: {e}")

    return JsonResponse({'success': True, 'new_size': new_size, 'status': new_status})


@add_web_user_context
@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='20/m', block=True)
def api_lfg_fluxer_guild_leave(request, group_id):
    """POST /api/lfg/fluxer-guild/<id>/leave/ - Leave a Fluxer guild LFG group via web."""
    if not request.web_user:
        return JsonResponse({'error': 'Login required'}, status=401)

    viewer_id = request.web_user.id

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        member = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id == group_id,
            WebFluxerLfgMember.web_user_id == viewer_id,
            WebFluxerLfgMember.left_at.is_(None),
        ).first()
        if not member:
            return JsonResponse({'error': 'Not in this group'}, status=400)
        if member.is_creator:
            return JsonResponse({'error': 'Close the group instead of leaving as creator'}, status=400)

        member.left_at = int(time.time())
        group.current_size = max(1, group.current_size - 1)
        if group.status == 'full' and group.current_size < group.max_size:
            group.status = 'open'
        db.commit()
        return JsonResponse({'success': True, 'new_size': group.current_size, 'status': group.status})


# =============================================================================
# NETWORK LEAVE / REJOIN
# =============================================================================

@web_login_required
@add_web_user_context
@require_http_methods(["POST"])
def api_community_leave_network(request, community_id):
    """Owner voluntarily leaves the QuestLog Network. Can rejoin within 90 days."""
    with get_db_session() as db:
        community = db.query(WebCommunity).filter_by(
            id=community_id, owner_id=request.web_user.id,
        ).first()
        if not community:
            return JsonResponse({'error': 'Community not found'}, status=404)
        if community.network_status not in ('approved', 'pending'):
            return JsonResponse({'error': 'Community is not in the network'}, status=400)
        community.network_status = 'left'
        community.network_left_at = int(time.time())
        community.network_member = False
        community.updated_at = int(time.time())
        db.commit()
    return JsonResponse({'success': True})


@web_login_required
@add_web_user_context
@require_http_methods(["POST"])
def api_community_rejoin_network(request, community_id):
    """Owner rejoins within the 90-day window - sets status back to pending."""
    REAPPLY_DAYS = 90
    with get_db_session() as db:
        community = db.query(WebCommunity).filter_by(
            id=community_id, owner_id=request.web_user.id,
        ).first()
        if not community:
            return JsonResponse({'error': 'Community not found'}, status=404)
        if community.network_status != 'left':
            return JsonResponse({'error': 'Community has not left the network'}, status=400)
        left_at = community.network_left_at or 0
        days_since_left = (time.time() - left_at) / 86400
        if days_since_left >= REAPPLY_DAYS:
            return JsonResponse({'error': f'Rejoin window expired. Please submit a new application.'}, status=400)
        community.network_status = 'pending'
        community.network_left_at = None
        community.updated_at = int(time.time())
        db.commit()
    return JsonResponse({'success': True})


@web_login_required
@add_web_user_context
@require_http_methods(["POST"])
def api_community_set_primary(request, community_id):
    """Set a community as the owner's primary - clears is_primary on all others."""
    with get_db_session() as db:
        community = db.query(WebCommunity).filter_by(
            id=community_id, owner_id=request.web_user.id,
        ).first()
        if not community:
            return JsonResponse({'error': 'Community not found'}, status=404)
        # Clear primary on all owner's communities, then set this one
        db.query(WebCommunity).filter_by(owner_id=request.web_user.id).update({'is_primary': False})
        community.is_primary = True
        community.updated_at = int(time.time())
        db.commit()
    return JsonResponse({'success': True})


@add_web_user_context
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='30/m', block=True)
def api_top_posts(request):
    """API: Top posts by engagement (likes + comments + reposts) from the last 7 days.
    No login required. Excludes banned/disabled authors and hidden/deleted posts.
    ?limit=<n>  (max 10)
    """
    limit = safe_int(request.GET.get('limit', 5) or 5, default=5, min_val=1, max_val=10)
    since = int(time.time()) - (7 * 24 * 3600)

    with get_db_session() as db:
        posts = (
            db.query(WebPost)
            .join(WebUser, WebUser.id == WebPost.author_id)
            .filter(
                WebPost.is_deleted == False,
                WebPost.is_hidden == False,
                WebPost.created_at >= since,
                WebUser.is_banned == False,
                WebUser.is_disabled == False,
                ~WebUser.id.in_(EXCLUDED_USER_IDS),
            )
            .order_by(
                (WebPost.like_count + WebPost.comment_count + WebPost.repost_count).desc()
            )
            .limit(limit)
            .all()
        )

        data = []
        for p in posts:
            engagement = (p.like_count or 0) + (p.comment_count or 0) + (p.repost_count or 0)
            if engagement == 0:
                continue
            author = p.author
            data.append({
                'id': p.id,
                'public_id': p.public_id,
                'content': (p.content or '')[:120],
                'like_count': p.like_count or 0,
                'comment_count': p.comment_count or 0,
                'repost_count': p.repost_count or 0,
                'game_tag_name': p.game_tag_name,
                'author_username': author.username if author else '',
                'author_display_name': author.display_name or author.username if author else '',
                'author_avatar_url': author.avatar_url if author else None,
                'created_at': p.created_at,
            })

    return JsonResponse({'posts': data})


@require_http_methods(["GET"])
def api_post_game_tags(request):
    """GET /api/posts/game-tags/
    Returns the most-used game tags from recent posts (last 30 days).
    Used to build the feed filter bar. No auth required.
    ?limit=<n> (max 20, default 15)
    """
    limit = safe_int(request.GET.get('limit', 15) or 15, default=15, min_val=1, max_val=20)

    with get_db_session() as db:
        # Group by name only so posts with/without steam_id are counted together.
        # MAX(steam_id) picks one if any post for that game has one.
        # LEFT JOIN web_found_games to get IGDB cover_url when available.
        rows = db.execute(text(
            "SELECT p.game_tag_name, MAX(p.game_tag_steam_id) as steam_id, "
            "       MAX(fg.cover_url) as igdb_cover, COUNT(*) as cnt "
            "FROM web_posts p "
            "JOIN web_users u ON u.id = p.author_id "
            "LEFT JOIN web_found_games fg ON fg.steam_app_id = p.game_tag_steam_id "
            "WHERE p.game_tag_name IS NOT NULL AND p.game_tag_name != '' "
            "  AND p.is_deleted = 0 AND p.is_hidden = 0 "
            "  AND u.is_banned = 0 "
            "GROUP BY p.game_tag_name "
            "ORDER BY cnt DESC "
            "LIMIT :limit"
        ), {'limit': limit}).fetchall()

    tags = []
    for row in rows:
        steam_id = row[1]
        igdb_cover = row[2]
        # Prefer IGDB cover, fall back to Steam header image (more reliable than library_600x900)
        cover_url = igdb_cover or (
            f'https://cdn.cloudflare.steamstatic.com/steam/apps/{steam_id}/header.jpg'
            if steam_id else None
        )
        tags.append({
            'name': row[0],
            'post_count': row[3],
            'cover_url': cover_url,
        })

    return JsonResponse({'tags': tags})


@web_login_required
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='20/h', block=True)
def api_user_discord_guilds(request):
    """GET /api/user/discord-guilds/
    Returns Discord guilds the user has MANAGE_GUILD permission on,
    fetched live from Discord API using their stored OAuth token.
    """
    from app.utils.encryption import decrypt_token as _dec
    import requests as _req

    user = request.web_user
    if not user or not user.discord_id:
        return JsonResponse({'error': 'Discord not linked'}, status=400)

    enc_token = getattr(user, 'discord_access_token_enc', None)
    if not enc_token:
        return JsonResponse({'error': 'no_token', 'guilds': []})

    try:
        access_token = _dec(enc_token)
    except Exception:
        return JsonResponse({'error': 'no_token', 'guilds': []})

    try:
        resp = _req.get(
            'https://discord.com/api/v10/users/@me/guilds',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        if resp.status_code == 401:
            return JsonResponse({'error': 'token_expired', 'guilds': []})
        resp.raise_for_status()
        all_guilds = resp.json()
    except Exception as e:
        logger.error(f"api_user_discord_guilds: fetch failed: {e}")
        return JsonResponse({'error': 'fetch_failed', 'guilds': []})

    MANAGE_GUILD = 0x20
    owned = [
        {
            'id': g['id'],
            'name': g['name'],
            'icon': (
                f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png"
                if g.get('icon') else None
            ),
        }
        for g in all_guilds
        if (int(g.get('permissions', 0)) & MANAGE_GUILD) or g.get('owner')
    ]

    # Mark which are already registered as communities
    if owned:
        guild_ids = [g['id'] for g in owned]
        with get_db_session() as db:
            ph = ','.join(f':d{i}' for i in range(len(guild_ids)))
            params = {f'd{i}': v for i, v in enumerate(guild_ids)}
            rows = db.execute(
                text(f"SELECT platform_id FROM web_communities WHERE platform='discord' AND platform_id IN ({ph})"),
                params,
            ).fetchall()
            registered = {r[0] for r in rows}
        for g in owned:
            g['registered'] = g['id'] in registered

    return JsonResponse({'guilds': owned})


@web_login_required
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='20/h', block=True)
def api_user_fluxer_guilds(request):
    """GET /api/user/fluxer-guilds/
    Returns Fluxer guilds the user owns or admins,
    fetched from our DB (web_fluxer_guild_settings) using their stored fluxer_id.
    """
    user = request.web_user
    if not user or not user.fluxer_id:
        return JsonResponse({'error': 'Fluxer not linked'}, status=400)

    with get_db_session() as db:
        rows = db.execute(
            text("""
                SELECT s.guild_id, s.guild_name, s.member_count, s.guild_icon_hash
                FROM web_fluxer_guild_settings s
                WHERE s.owner_id = :fid
                LIMIT 20
            """),
            {'fid': user.fluxer_id},
        ).fetchall()

        guilds = []
        for r in rows:
            icon = None
            if r[3]:
                icon = f"https://cdn.fluxer.app/icons/{r[0]}/{r[3]}.png"
            guilds.append({
                'id': r[0],
                'name': r[1] or r[0],
                'member_count': r[2] or 0,
                'icon': icon,
            })

        if guilds:
            guild_ids = [g['id'] for g in guilds]
            ph = ','.join(f':f{i}' for i in range(len(guild_ids)))
            params = {f'f{i}': v for i, v in enumerate(guild_ids)}
            rows2 = db.execute(
                text(f"SELECT platform_id FROM web_communities WHERE platform='fluxer' AND platform_id IN ({ph})"),
                params,
            ).fetchall()
            registered = {r[0] for r in rows2}
            for g in guilds:
                g['registered'] = g['id'] in registered

    return JsonResponse({'guilds': guilds})
