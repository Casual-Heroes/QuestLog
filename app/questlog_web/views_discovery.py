# QuestLog Web — public browse APIs

import json
import time
import asyncio
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from sqlalchemy import text

from .models import (
    WebLFGGroup, WebLFGMember, WebCommunity, WebCreatorProfile,
    WebFoundGame, WebRSSArticle, WebUser, PlatformType,
    WebCommunityBotConfig,
    WebFluxerLfgGroup, WebFluxerLfgConfig, WebFluxerGuildChannel,
    WebFluxerLfgMember, WebFluxerGuildSettings, WebFluxerLfgGame,
)
from app.db import get_db_session
from .helpers import add_web_user_context, web_login_required, safe_int, EXCLUDED_USER_IDS
from .fluxer_webhooks import notify_lfg_post as _fluxer_lfg_post

logger = logging.getLogger(__name__)

_VOICE_LINK_SCHEMES = ('https://',)
_VOICE_LINK_MAX = 500


def _validate_voice_link(url):
    """Only allow https:// voice links to prevent javascript: / file: URI injection."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()[:_VOICE_LINK_MAX]
    if not any(url.startswith(s) for s in _VOICE_LINK_SCHEMES):
        return None
    return url or None


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
            group = WebLFGGroup(
                creator_id=request.web_user.id,
                title=title,
                description=(data.get('description') or '')[:2000] or None,
                game_name=game_name[:200],
                game_id=(data.get('game_id') or '')[:50] or None,
                game_image_url=(data.get('game_image_url') or '')[:500] or None,
                group_size=group_size,
                current_size=1,
                use_roles=bool(data.get('use_roles', False)),
                tanks_needed=safe_int(data.get('tanks_needed') or 0, default=0, min_val=0, max_val=40),
                healers_needed=safe_int(data.get('healers_needed') or 0, default=0, min_val=0, max_val=40),
                dps_needed=safe_int(data.get('dps_needed') or 0, default=0, min_val=0, max_val=40),
                support_needed=safe_int(data.get('support_needed') or 0, default=0, min_val=0, max_val=40),
                scheduled_time=safe_int(data.get('scheduled_time'), default=None, min_val=0, max_val=9999999999),
                voice_platform=(data.get('voice_platform') or '')[:50] or None,
                voice_link=_validate_voice_link(data.get('voice_link')),
                status='open',
                created_at=now,
                updated_at=now,
            )
            db.add(group)
            db.flush()

            # Creator is first member — store game-specific selections (class/spec/activity)
            raw_selections = data.get('selections') or {}
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

        # Notify admin LFG channel (fire-and-forget, never raises)
        try:
            lfg_url = f"https://casual-heroes.com/ql/lfg/?group={group.id}"
            _fluxer_lfg_post(
                creator=request.web_user.username,
                game_name=game_name,
                title=title,
                description=group.description or '',
                group_size=group_size,
                current_size=1,
                scheduled_time=group.scheduled_time,
                lfg_url=lfg_url,
                game_image_url=group.game_image_url,
            )
        except Exception:
            pass

        return JsonResponse({'success': True, 'id': group.id})

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
        for entry in raw_platforms[:3]:  # max 3 (discord + fluxer + matrix)
            ptype_str = (entry.get('platform') or '').lower()
            pid = (entry.get('platform_id') or '').strip()[:100]
            if not ptype_str or not pid:
                continue
            try:
                ptype = PlatformType(ptype_str)
            except ValueError:
                continue

            p_invite_url = (entry.get('invite_url') or '')[:500] or None
            p_member_count = safe_int(entry.get('member_count') or 0, default=0, min_val=0)

            # Verify ownership per platform
            if ptype == PlatformType.FLUXER:
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
                if not discord_id:
                    return JsonResponse({'error': 'Connect your Discord account to link a Discord server'}, status=403)
                with get_db_session() as db:
                    row = db.execute(
                        text("SELECT guild_id FROM guilds WHERE guild_id=:gid AND owner_id=:oid AND bot_present=1 LIMIT 1"),
                        {'gid': int(pid), 'oid': int(discord_id)},
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

        shared_fields = dict(
            name=name,
            short_description=(data.get('short_description') or '')[:500] or None,
            description=(data.get('description') or '') or None,
            website_url=(data.get('website_url') or '')[:500] or None,
            twitch_url=(data.get('twitch_url') or '')[:500] or None,
            youtube_url=(data.get('youtube_url') or '')[:500] or None,
            twitter_url=(data.get('twitter_url') or '')[:500] or None,
            bluesky_url=(data.get('bluesky_url') or '')[:500] or None,
            tiktok_url=(data.get('tiktok_url') or '')[:500] or None,
            instagram_url=(data.get('instagram_url') or '')[:500] or None,
            tags=tags_json,
            allow_discovery=bool(data.get('allow_discovery', False)),
            allow_joins=bool(data.get('allow_joins', False)),
            site_xp_to_guild=bool(data.get('site_xp_to_guild', False)),  # stored; only active once network_status='approved'
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
                    existing = db.query(WebCommunity).filter_by(
                        owner_id=request.web_user.id, name=name, platform=ptype
                    ).first()
                    if existing:
                        return JsonResponse(
                            {'error': f'You already have a {ptype.value} community with that name'},
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
                        icon_row = db.execute(
                            text("SELECT guild_icon_hash FROM guilds WHERE guild_id=:gid LIMIT 1"),
                            {'gid': int(pid)},
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
        communities = db.query(WebCommunity).filter(
            WebCommunity.network_status == 'approved',
            WebCommunity.allow_discovery == True,
            WebCommunity.is_active == True,
            WebCommunity.is_banned == False,
            WebCommunity.is_primary == True,
        ).order_by(WebCommunity.member_count.desc()).limit(50).all()

        data = [{
            'id': c.id,
            'name': c.name,
            'short_description': c.short_description,
            'description': c.description,
            'platform': c.platform.value,
            'icon_url': c.icon_url,
            'banner_url': c.banner_url,
            'member_count': c.member_count,
            'activity_level': c.activity_level,
            'allow_joins': c.allow_joins,
            'invite_url': c.invite_url if c.allow_joins else None,
            'tags': json.loads(c.tags or '[]'),
            'owner_id': c.owner_id,
        } for c in communities]

    return JsonResponse({'communities': data})


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

            platform_str = (data.get('platform') or community.platform.value).lower()
            try:
                platform = PlatformType(platform_str)
            except ValueError:
                platform = PlatformType.OTHER

            raw_tags = data.get('tags') or []
            community.name = name
            community.platform = platform
            community.short_description = (data.get('short_description') or '')[:500] or None
            community.description = data.get('description') or None
            community.invite_url = (data.get('invite_url') or '')[:500] or None
            community.website_url = (data.get('website_url') or '')[:500] or None
            community.twitch_url = (data.get('twitch_url') or '')[:500] or None
            community.youtube_url = (data.get('youtube_url') or '')[:500] or None
            community.twitter_url = (data.get('twitter_url') or '')[:500] or None
            community.tags = json.dumps([t for t in raw_tags if isinstance(t, str)][:8])
            community.member_count = safe_int(data.get('member_count') or community.member_count, default=community.member_count, min_val=0)
            community.allow_discovery = bool(data.get('allow_discovery', community.allow_discovery))
            community.allow_joins = bool(data.get('allow_joins', community.allow_joins))
            # Owner can disable unified XP but cannot enable it - that requires admin approval
            if 'site_xp_to_guild' in data and not data['site_xp_to_guild']:
                community.site_xp_to_guild = False
            community.updated_at = int(time.time())
            db.commit()
            return JsonResponse({'success': True})

        # GET
        is_owner = bool(request.web_user and community.owner_id == request.web_user.id)
        return JsonResponse({
            'id': community.id,
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
            'member_count': community.member_count,
            'activity_level': community.activity_level,
            'allow_discovery': community.allow_discovery,
            'allow_joins': community.allow_joins,
            'site_xp_to_guild': bool(community.site_xp_to_guild),
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

        data = [{
            'id': c.id,
            'username': u.username,
            'display_name': c.display_name,
            'bio': c.bio,
            'avatar_url': c.avatar_url,
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
        ADULT_TAGS = ['Sexual Content', 'Nudity', 'Adult Only', 'Hentai', 'NSFW', 'Explicit']
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
@ratelimit(key='ip', rate='30/m', block=True)
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

        data = [{
            'id': g.id,
            'name': g.name,
            'cover_url': g.cover_url,
            'platforms': ', '.join(g.platforms[:3]) if g.platforms else '',
            'release_year': g.release_year,
            'steam_id': g.steam_id,
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
            )

            if current_uid:
                query = query.filter(WebUser.id != current_uid)

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
            else:
                query = query.order_by(WebUser.follower_count.desc(), WebUser.created_at.desc())

            total = query.count()
            offset = (page - 1) * per_page
            users = query.offset(offset).limit(per_page).all()

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
