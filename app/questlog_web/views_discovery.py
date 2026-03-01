# QuestLog Web — public browse APIs

import json
import time
import asyncio
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .models import (
    WebLFGGroup, WebLFGMember, WebCommunity, WebCreatorProfile,
    WebFoundGame, WebRSSArticle, WebUser, PlatformType,
)
from app.db import get_db_session
from .helpers import add_web_user_context, web_login_required, safe_int

logger = logging.getLogger(__name__)


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
                scheduled_time=data.get('scheduled_time'),
                voice_platform=(data.get('voice_platform') or '')[:50] or None,
                voice_link=(data.get('voice_link') or '')[:500] or None,
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
            'is_creator': g.creator_id == viewer_id,
            'has_role_composition': bool(g.use_roles),
            'tanks_needed': g.tanks_needed or 0,
            'healers_needed': g.healers_needed or 0,
            'dps_needed': g.dps_needed or 0,
            'support_needed': g.support_needed or 0,
            'members': members_by_group[g.id],
        } for g in groups]

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

        # Resolve platform enum value
        platform_str = (data.get('platform') or 'discord').lower()
        try:
            platform = PlatformType(platform_str)
        except ValueError:
            platform = PlatformType.OTHER

        now = int(time.time())
        with get_db_session() as db:
            # Check for duplicate name for this owner
            existing = db.query(WebCommunity).filter_by(
                owner_id=request.web_user.id, name=name
            ).first()
            if existing:
                return JsonResponse({'error': 'You already have a community with that name'}, status=400)

            raw_tags = data.get('tags') or []
            tags_json = json.dumps([t for t in raw_tags if isinstance(t, str)][:8])

            community = WebCommunity(
                name=name,
                platform=platform,
                short_description=(data.get('short_description') or '')[:500] or None,
                description=(data.get('description') or '') or None,
                invite_url=(data.get('invite_url') or '')[:500] or None,
                website_url=(data.get('website_url') or '')[:500] or None,
                twitch_url=(data.get('twitch_url') or '')[:500] or None,
                youtube_url=(data.get('youtube_url') or '')[:500] or None,
                twitter_url=(data.get('twitter_url') or '')[:500] or None,
                tags=tags_json,
                member_count=safe_int(data.get('member_count') or 0, default=0, min_val=0),
                allow_discovery=bool(data.get('allow_discovery', False)),
                allow_joins=bool(data.get('allow_joins', False)),
                owner_id=request.web_user.id,
                network_status='pending',
                is_active=True,
                is_banned=False,
                created_at=now,
                updated_at=now,
            )
            db.add(community)
            db.commit()
            return JsonResponse({'success': True, 'id': community.id})

    # GET: list communities (approved only)
    with get_db_session() as db:
        communities = db.query(WebCommunity).filter(
            WebCommunity.network_status == 'approved',
            WebCommunity.allow_discovery == True,
            WebCommunity.is_active == True,
            WebCommunity.is_banned == False,
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
            # Only update social URLs if not OAuth-connected (OAuth sets these automatically)
            if not profile.twitch_user_id:
                profile.twitch_url = (data.get('twitch_url') or '')[:500] or None
            if not profile.youtube_channel_id:
                profile.youtube_url = (data.get('youtube_url') or '')[:500] or None
            profile.twitter_url = (data.get('twitter_url') or '')[:500] or None
            profile.tiktok_url = (data.get('tiktok_url') or '')[:500] or None
            profile.website_url = (data.get('website_url') or '')[:500] or None
            profile.discord_url = (data.get('discord_url') or '')[:500] or None
            profile.matrix_url = (data.get('matrix_url') or '')[:500] or None
            profile.valor_url = (data.get('valor_url') or '')[:500] or None
            profile.fluxer_url = (data.get('fluxer_url') or '')[:500] or None
            profile.kloak_url = (data.get('kloak_url') or '')[:500] or None
            profile.teamspeak_url = (data.get('teamspeak_url') or '')[:500] or None
            profile.revolt_url = (data.get('revolt_url') or '')[:500] or None
            profile.allow_discovery = bool(data.get('allow_discovery', True))
            db.commit()

            return JsonResponse({'success': True, 'id': profile.id})

    # GET: list creators — COTW/COTM first, then by follower count
    with get_db_session() as db:
        creators = db.query(WebCreatorProfile).filter(
            WebCreatorProfile.allow_discovery == True
        ).order_by(
            WebCreatorProfile.is_current_cotm.desc(),
            WebCreatorProfile.is_current_cotw.desc(),
            WebCreatorProfile.follower_count.desc(),
        ).limit(50).all()

        data = [{
            'id': c.id,
            'display_name': c.display_name,
            'bio': c.bio,
            'avatar_url': c.avatar_url,
            'twitch_url': c.twitch_url,
            'youtube_url': c.youtube_url,
            'tiktok_url': c.tiktok_url,
            'twitter_url': c.twitter_url,
            'is_verified': c.is_verified,
            'follower_count': c.follower_count,
            'is_current_cotw': c.is_current_cotw,
            'is_current_cotm': c.is_current_cotm,
        } for c in creators]

    return JsonResponse({'creators': data})


@add_web_user_context
def api_games(request):
    """API: List/search found games. Returns full data for client-side filtering.
    Intentionally public - no login required (read-only discovery endpoint)."""
    with get_db_session() as db:
        games = (
            db.query(WebFoundGame)
            .filter(WebFoundGame.is_hidden == False)
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
