# QuestLog Web — template renderers (GET only, return render())

import json
import logging
import re
import time

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.conf import settings as django_settings
from django_ratelimit.decorators import ratelimit
from sqlalchemy import or_, and_, text

from .models import (
    WebCreatorProfile, PlatformType, WebLFGGroup, WebLFGMember,
    WebServerPoll, WebServerPollOption, WebServerPollVote,
    WebFluxerLfgGroup, WebFluxerLfgConfig, WebFluxerGuildSettings,
    WebCommunity, WebCommunityMember, WebFluxerRssFeed, WebFluxerRssArticle, WebFluxerRaffle, WebFluxerRaffleEntry,
    WebFluxerLfgGame, WebFluxerLfgMember,
    WebFluxerFoundGame, WebFluxerGameSearchConfig,
)
from app.db import get_db_session
from .helpers import (
    web_login_required, add_web_user_context, safe_int, EXCLUDED_USER_IDS,
    fluxer_login_required, create_notification, sanitize_text,
)
from .fluxer_webhooks import queue_lfg_embed_edit_for_group as _queue_lfg_embed_edit

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
@add_web_user_context
def home(request):
    """QuestLog Web home page."""
    context = {
        'web_user': request.web_user,
        'active_page': 'home',
    }
    return render(request, 'questlog_web/home.html', context)


@add_web_user_context
def community_guidelines(request):
    """QuestLog Network community guidelines page."""
    return render(request, 'questlog_web/community_guidelines.html', {
        'web_user': request.web_user,
        'active_page': 'community_guidelines',
    })


# =============================================================================
# LFG VIEWS
# =============================================================================

@web_login_required
@add_web_user_context
def lfg_browse(request):
    """Browse LFG groups."""
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_browse',
    }
    return render(request, 'questlog_web/lfg_browse.html', context)


@web_login_required
@add_web_user_context
def lfg_calendar(request):
    """Public LFG calendar - shows published events from all Fluxer guilds."""
    now_ts = int(time.time())
    cutoff = now_ts - 86400  # include events from yesterday onwards

    with get_db_session() as db:
        # Guilds with publish_to_network enabled
        published_guild_ids = [
            r[0] for r in db.query(WebFluxerLfgConfig.guild_id)
            .filter(WebFluxerLfgConfig.publish_to_network == 1).all()
        ]

        # Events: published to network
        # Include if: explicit publish_override=1, OR guild default is on and group hasn't opted out (NULL)
        groups = db.query(WebFluxerLfgGroup).filter(
            WebFluxerLfgGroup.scheduled_time.isnot(None),
            WebFluxerLfgGroup.scheduled_time >= cutoff,
            WebFluxerLfgGroup.status.in_(['open', 'full']),
            or_(
                WebFluxerLfgGroup.publish_override == 1,
                and_(
                    WebFluxerLfgGroup.guild_id.in_(published_guild_ids) if published_guild_ids else False,
                    WebFluxerLfgGroup.publish_override.is_(None),
                ),
            ),
        ).order_by(WebFluxerLfgGroup.scheduled_time).limit(365).all()

        guild_ids = list({g.guild_id for g in groups})
        guild_name_map = {}
        if guild_ids:
            settings_rows = db.query(
                WebFluxerGuildSettings.guild_id,
                WebFluxerGuildSettings.guild_name,
            ).filter(WebFluxerGuildSettings.guild_id.in_(guild_ids)).all()
            guild_name_map = {r[0]: r[1] or 'Unknown Server' for r in settings_rows}

        events = [
            {
                'id': g.id,
                'title': g.title or g.game_name,
                'game_name': g.game_name or '',
                'ts': g.scheduled_time,
                'status': g.status,
                'current_size': g.current_size,
                'max_size': g.max_size,
                'recurrence': g.recurrence or 'none',
                'guild_id': g.guild_id,
                'guild_name': guild_name_map.get(g.guild_id, 'Unknown Server'),
                'description': g.description or '',
            }
            for g in groups
        ]

    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_calendar',
        'events_json': json.dumps(events),
    }
    return render(request, 'questlog_web/lfg_calendar.html', context)


@web_login_required
@add_web_user_context
def lfg_create(request):
    """Create LFG group."""
    import json as _json
    profile_games = []
    if request.web_user:
        raw = getattr(request.web_user, 'favorite_games', None) or '[]'
        try:
            games = _json.loads(raw)
            for g in games:
                if isinstance(g, dict) and g.get('name'):
                    profile_games.append(g)
                elif isinstance(g, str) and g:
                    profile_games.append({'name': g, 'igdb_id': None, 'cover_url': ''})
        except Exception:
            pass
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_create',
        'profile_games_json': _json.dumps(profile_games),
        'profile_games': profile_games,
    }
    return render(request, 'questlog_web/lfg_create.html', context)


@web_login_required
@add_web_user_context
def lfg_my_groups(request):
    """View user's LFG groups."""
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_my_groups',
    }
    return render(request, 'questlog_web/lfg_my_groups.html', context)


@add_web_user_context
def lfg_group_detail(request, group_id):
    """Legacy integer-ID URL - redirect to token URL if group has one."""
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).first()
        if not group:
            return redirect('questlog_web_lfg_browse')
        if group.share_token:
            return redirect('questlog_web_lfg_detail_token', share_token=group.share_token)
        # No token yet (pre-migration row) - render directly with integer ID
        context = {
            'web_user': request.web_user,
            'active_page': 'lfg_browse',
            'group_id': group_id,
        }
        return render(request, 'questlog_web/lfg_detail.html', context)


@add_web_user_context
def lfg_group_detail_token(request, share_token):
    """View LFG group details via non-guessable share token."""
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(share_token=share_token).first()
        if not group:
            return redirect('questlog_web_lfg_browse')
        context = {
            'web_user': request.web_user,
            'active_page': 'lfg_browse',
            'group_id': group.id,
        }
        return render(request, 'questlog_web/lfg_detail.html', context)


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/h', block=True)
def lfg_join(request, group_id):
    """Join an LFG group with class/spec/role selections."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).with_for_update().first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        if group.status not in ('open',):
            return JsonResponse({'error': 'Group is not open for joining'}, status=400)
        if group.current_size >= group.group_size:
            return JsonResponse({'error': 'Group is full'}, status=400)

        existing = db.query(WebLFGMember).filter_by(
            group_id=group_id, user_id=request.web_user.id
        ).first()
        if existing:
            if existing.status == 'joined':
                return JsonResponse({'error': 'You are already in this group'}, status=400)
            # Rejoin capacity check - must re-verify even though we checked above (TOCTOU)
            if group.current_size >= group.group_size:
                return JsonResponse({'error': 'Group is full'}, status=400)
            # Rejoining after leaving — update the existing row
            existing.status = 'joined'
            existing.left_at = None
            raw_role = data.get('role') or None
            existing.role = sanitize_text(raw_role) if raw_role else None
            raw_sel = data.get('selections') or {}
            if isinstance(raw_sel, dict):
                raw_sel = {k: sanitize_text(v) if isinstance(v, str) else v for k, v in raw_sel.items()}
            existing.selections = json.dumps(raw_sel) if raw_sel else None
            existing.joined_at = now
        else:
            raw_sel = data.get('selections') or {}
            if isinstance(raw_sel, dict):
                raw_sel = {k: sanitize_text(v) if isinstance(v, str) else v for k, v in raw_sel.items()}
            raw_role = data.get('role') or None
            db.add(WebLFGMember(
                group_id=group_id,
                user_id=request.web_user.id,
                role=sanitize_text(raw_role) if raw_role else None,
                selections=json.dumps(raw_sel) if raw_sel else None,
                is_creator=False,
                is_co_leader=False,
                status='joined',
                joined_at=now,
            ))

        group.current_size += 1
        if group.current_size >= group.group_size:
            group.status = 'full'
        group.updated_at = now

        # Capture for embed update before session closes
        origin_platform = group.origin_platform
        origin_group_id = group.origin_group_id
        web_group_id = group.id
        web_group_token = group.share_token or str(group.id)
        web_group_title = group.title
        web_group_game = group.game_name
        allow_network = group.allow_network_discovery
        group_creator_id = group.creator_id
        joiner_name = request.web_user.display_name or request.web_user.username
        joiner_username = request.web_user.username
        raw_sel = data.get('selections') or {}
        joiner_role = data.get('role') or None

        db.commit()

    # Site notification to group creator
    try:
        with get_db_session() as db:
            create_notification(
                db, group_creator_id, request.web_user.id,
                'lfg_join',
                target_type='lfg_group', target_id=web_group_id,
                message=f"{joiner_name} joined your LFG group: {web_group_title}",
            )
            db.commit()
    except Exception as e:
        logger.warning(f"[LFG] Failed to create site join notification for group {web_group_id}: {e}")

    # Edit the pinned embed to show updated roster; unpin if group is now full
    try:
        with get_db_session() as db:
            _grp = db.query(WebLFGGroup).filter_by(id=web_group_id).first()
            is_now_full = _grp and _grp.status == 'full'
        pin_state = 'unpin' if is_now_full else None
        _queue_lfg_embed_edit(web_group_id, 'web', pin_state=pin_state)
    except Exception as e:
        logger.warning(f"[LFG] Failed to queue embed edit for group {web_group_id}: {e}")

    # Helper: build detail string from selections
    def _join_detail(role, sel):
        parts = []
        if role:
            parts.append(role.title())
        for key, val in sel.items():
            if key.lower() in ('activity', 'role', 'player_role'):
                continue
            v = val[0] if isinstance(val, list) and val else val
            if v:
                parts.append(str(v))
        return ', '.join(parts) if parts else 'No class selected'

    lfg_url = f"https://casual-heroes.com/ql/lfg/{web_group_token}/"

    return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def lfg_leave(request, group_id):
    """Leave an LFG group."""
    now = int(time.time())
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        member = db.query(WebLFGMember).filter_by(
            group_id=group_id, user_id=request.web_user.id, status='joined'
        ).first()
        if not member:
            return JsonResponse({'error': 'You are not in this group'}, status=400)
        if member.is_creator:
            return JsonResponse({'error': 'Creators cannot leave their own group — delete it instead'}, status=400)

        member.status = 'left'
        member.left_at = now
        group.current_size = max(0, group.current_size - 1)
        reopened = group.status == 'full'
        if group.status == 'full':
            group.status = 'open'
        group.updated_at = now
        db.commit()

    # Edit the pinned embed to reflect updated roster; re-pin if group reopened
    try:
        pin_state = 'pin' if reopened else None
        _queue_lfg_embed_edit(group_id, 'web', pin_state=pin_state)
    except Exception as e:
        logger.warning(f"[LFG] Failed to queue embed edit after leave for group {group_id}: {e}")

    return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def lfg_update_member(request, group_id):
    """Update own class/spec/role in a group after joining."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        member = db.query(WebLFGMember).filter_by(
            group_id=group_id, user_id=request.web_user.id, status='joined'
        ).first()
        if not member:
            return JsonResponse({'error': 'You are not in this group'}, status=400)

        member.role = sanitize_text(data.get('role') or '', max_length=100) or None
        raw_sel = data.get('selections') or {}
        member.selections = json.dumps(raw_sel) if raw_sel else None
        db.commit()

    return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def lfg_edit(request, group_id):
    """Edit a group — creator only."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        if group.creator_id != request.web_user.id:
            return JsonResponse({'error': 'Only the group creator can edit it'}, status=403)

        title = (data.get('title') or '').strip()
        if not title:
            return JsonResponse({'error': 'Title is required'}, status=400)
        if len(title) > 200:
            return JsonResponse({'error': 'Title too long (max 200 chars)'}, status=400)

        group_size = safe_int(data.get('group_size') or group.group_size, default=group.group_size, min_val=2, max_val=40)
        if not (2 <= group_size <= 40):
            return JsonResponse({'error': 'Group size must be between 2 and 40'}, status=400)
        if group_size < group.current_size:
            return JsonResponse({'error': f'Group size cannot be less than current member count ({group.current_size})'}, status=400)

        group.title = title
        group.description = (data.get('description') or '')[:2000] or None
        group.group_size = group_size
        group.scheduled_time = data.get('scheduled_time') or None
        group.voice_platform = (data.get('voice_platform') or '')[:50] or None
        group.voice_link = (data.get('voice_link') or '')[:500] or None
        group.updated_at = now
        db.commit()

    return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def lfg_delete(request, group_id):
    """Delete (cancel) a group — creator only."""
    now = int(time.time())
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        if group.creator_id != request.web_user.id:
            return JsonResponse({'error': 'Only the group creator can delete it'}, status=403)

        group.status = 'cancelled'
        group.updated_at = now
        db.commit()

    return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def lfg_kick(request, group_id, user_id):
    """Kick a member — creator or co-leader only."""
    now = int(time.time())
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        actor = db.query(WebLFGMember).filter_by(
            group_id=group_id, user_id=request.web_user.id, status='joined'
        ).first()
        if not actor or (not actor.is_creator and not actor.is_co_leader):
            return JsonResponse({'error': 'Only the creator or co-leaders can kick members'}, status=403)

        target = db.query(WebLFGMember).filter_by(
            group_id=group_id, user_id=user_id, status='joined'
        ).first()
        if not target:
            return JsonResponse({'error': 'Member not found'}, status=404)
        if target.is_creator:
            return JsonResponse({'error': 'Cannot kick the group creator'}, status=400)

        target.status = 'kicked'
        target.left_at = now
        group.current_size = max(0, group.current_size - 1)
        if group.status == 'full':
            group.status = 'open'
        group.updated_at = now
        db.commit()

    return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def lfg_set_co_leader(request, group_id):
    """Set co-leaders for a group — creator only."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    co_leader_ids = set(int(uid) for uid in (data.get('co_leader_ids') or []))

    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        if group.creator_id != request.web_user.id:
            return JsonResponse({'error': 'Only the creator can set co-leaders'}, status=403)

        members = db.query(WebLFGMember).filter_by(
            group_id=group_id, status='joined'
        ).all()
        for m in members:
            if m.is_creator:
                continue
            m.is_co_leader = m.user_id in co_leader_ids
        db.commit()

    return JsonResponse({'success': True})


# =============================================================================
# DISCOVERY VIEWS
# =============================================================================

@web_login_required
@add_web_user_context
def network(request):
    """QuestLog Network page."""
    context = {
        'web_user': request.web_user,
        'active_page': 'network',
    }
    return render(request, 'questlog_web/network.html', context)


@add_web_user_context
def network_leaderboard(request):
    """QuestLog Network leaderboard - top users by unified web_xp."""
    page = safe_int(request.GET.get('page', 1), 1, 1, 500)
    per_page = 50
    offset = (page - 1) * per_page

    my_rank = None
    with get_db_session() as db:
        rows = db.execute(text(
            "SELECT wu.id, wu.username, wu.avatar_url, wu.web_xp, wu.web_level, wu.hero_points, "
            "       wr.title as rank_title, wu.is_live, wu.live_platform, wu.live_url, "
            "       wu.current_game, wu.current_game_appid, wu.show_playing_status "
            "FROM web_users wu "
            "LEFT JOIN web_rank_titles wr ON wr.level = wu.web_level "
            "WHERE wu.is_banned = 0 AND wu.is_disabled = 0 "
            "AND wu.email_verified = 1 AND wu.web_xp > 0 "
            f"AND wu.id NOT IN ({','.join(str(i) for i in EXCLUDED_USER_IDS)}) "
            "ORDER BY wu.web_xp DESC "
            "LIMIT :limit OFFSET :offset"
        ), {'limit': per_page, 'offset': offset}).fetchall()

        total = db.execute(text(
            "SELECT COUNT(*) FROM web_users "
            f"WHERE is_banned=0 AND is_disabled=0 AND email_verified=1 AND web_xp > 0 "
            f"AND id NOT IN ({','.join(str(i) for i in EXCLUDED_USER_IDS)})"
        )).scalar() or 0

        if request.web_user and getattr(request.web_user, 'id', None) not in EXCLUDED_USER_IDS:
            my_rank = db.execute(text(
                "SELECT COUNT(*) + 1 FROM web_users "
                f"WHERE web_xp > :xp AND is_banned=0 AND is_disabled=0 AND email_verified=1 "
                f"AND id NOT IN ({','.join(str(i) for i in EXCLUDED_USER_IDS)})"
            ), {'xp': request.web_user.web_xp or 0}).scalar()

        # Top communities: one entry per primary community, using the right XP source per platform.
        # Fluxer guilds: fluxer_member_xp (has all members + rich stats)
        # Discord/other: web_unified_leaderboard
        community_rows = db.execute(text("""
            SELECT wc.id, wc.name, wc.icon_url, wc.platform,
                   COALESCE(fx.member_count, wul.member_count, 0) AS active_members,
                   COALESCE(fx.total_xp, wul.total_xp, 0) AS total_xp,
                   COALESCE(fx.total_messages, 0) AS total_messages,
                   COALESCE(fx.total_media, 0) AS total_media,
                   COALESCE(fx.total_voice_mins, 0) AS total_voice_mins,
                   COALESCE(fx.total_reactions, 0) AS total_reactions
            FROM web_communities wc
            LEFT JOIN (
                SELECT guild_id,
                       COUNT(*) AS member_count,
                       SUM(xp) AS total_xp,
                       SUM(message_count) AS total_messages,
                       SUM(media_count) AS total_media,
                       SUM(voice_minutes) AS total_voice_mins,
                       SUM(reaction_count) AS total_reactions
                FROM fluxer_member_xp
                GROUP BY guild_id
            ) fx ON fx.guild_id = CAST(wc.platform_id AS UNSIGNED) AND wc.platform = 'fluxer'
            LEFT JOIN (
                SELECT guild_id,
                       COUNT(DISTINCT user_id) AS member_count,
                       SUM(xp_total) AS total_xp
                FROM web_unified_leaderboard
                GROUP BY guild_id
            ) wul ON wul.guild_id = wc.platform_id COLLATE utf8mb4_general_ci AND wc.platform != 'fluxer'
            WHERE wc.network_status='approved' AND wc.is_active=1 AND wc.is_primary=1
              AND COALESCE(fx.total_xp, wul.total_xp, 0) > 0
            ORDER BY total_xp DESC LIMIT 5
        """)).fetchall()

    entries = [
        {
            'rank': offset + i + 1,
            'user_id': r[0],
            'username': r[1],
            'avatar_url': r[2],
            'xp': r[3],
            'level': r[4],
            'hero_points': r[5],
            'rank_title': r[6] or '',
            'is_live': bool(r[7]),
            'live_platform': r[8] or '',
            'live_url': r[9] or '',
            'current_game': (r[10] if r[12] else None) or '',
            'current_game_appid': (r[11] if r[12] else 0) or 0,
        }
        for i, r in enumerate(rows)
    ]

    top_communities = [
        {
            'id': r[0],
            'name': r[1],
            'icon_url': r[2] or '',
            'platform': r[3],
            'active_members': int(r[4] or 0),
            'total_xp': int(r[5] or 0),
            'total_messages': int(r[6] or 0),
            'total_media': int(r[7] or 0),
            'total_voice_hours': round((r[8] or 0) / 60, 1),
            'total_reactions': int(r[9] or 0),
        }
        for r in community_rows
    ]

    context = {
        'web_user': request.web_user,
        'active_page': 'leaderboard',
        'entries': entries,
        'page': page,
        'total': total,
        'has_next': (offset + per_page) < total,
        'has_prev': page > 1,
        'my_rank': my_rank,
        'top_communities': top_communities,
    }
    return render(request, 'questlog_web/leaderboard.html', context)


@add_web_user_context
def api_leaderboard_top(request):
    """Return top N players for sidebar widget. Public."""
    limit = min(safe_int(request.GET.get('limit', 5), 5, 1, 20), 20)
    with get_db_session() as db:
        rows = db.execute(text(
            "SELECT wu.id, wu.username, wu.avatar_url, wu.web_xp, wu.web_level "
            "FROM web_users wu "
            "WHERE wu.is_banned=0 AND wu.is_disabled=0 AND wu.email_verified=1 AND wu.web_xp > 0 "
            f"AND wu.id NOT IN ({','.join(str(i) for i in EXCLUDED_USER_IDS)}) "
            "ORDER BY wu.web_xp DESC LIMIT :lim"
        ), {'lim': limit}).fetchall()
    return JsonResponse({'entries': [
        {'rank': i + 1, 'username': r[1], 'avatar_url': r[2] or '', 'xp': r[3], 'level': r[4]}
        for i, r in enumerate(rows)
    ]})


@web_login_required
@add_web_user_context
def games(request):
    """Found Games / Game Discovery."""
    context = {
        'web_user': request.web_user,
        'active_page': 'games',
    }
    return render(request, 'questlog_web/games.html', context)


@web_login_required
@add_web_user_context
def creators(request):
    """Featured Creators."""
    context = {
        'web_user': request.web_user,
        'active_page': 'creators',
    }
    return render(request, 'questlog_web/creators.html', context)


@add_web_user_context
def gamers(request):
    """Gamers directory - searchable list of QuestLog members."""
    context = {
        'web_user': request.web_user,
        'active_page': 'gamers',
    }
    return render(request, 'questlog_web/gamers.html', context)


@add_web_user_context
def articles(request):
    """RSS Articles."""
    context = {
        'web_user': request.web_user,
        'active_page': 'articles',
    }
    return render(request, 'questlog_web/articles.html', context)


# =============================================================================
# COMMUNITY VIEWS
# =============================================================================

@web_login_required
@add_web_user_context
def communities(request):
    """Community directory."""
    context = {
        'web_user': request.web_user,
        'active_page': 'communities',
    }
    return render(request, 'questlog_web/communities.html', context)


@web_login_required
@add_web_user_context
def community_register(request):
    """Register a community."""
    import json as _json
    import time as _time
    from sqlalchemy import text as sa_text

    NETWORK_REAPPLY_DAYS = 90

    # Fetch ALL of this user's communities in any active network state
    all_communities = []
    try:
        with get_db_session() as db:
            rows = db.query(WebCommunity).filter(
                WebCommunity.owner_id == request.web_user.id,
                WebCommunity.network_status.in_(['pending', 'approved', 'left']),
            ).order_by(WebCommunity.is_primary.desc(), WebCommunity.created_at.desc()).all()
            for r in rows:
                db.expunge(r)
            all_communities = rows
    except Exception:
        pass

    # Separate active (pending/approved) from left
    active_communities = [c for c in all_communities if c.network_status in ('pending', 'approved')]
    left_communities = []
    rejoinable_communities = []
    for c in all_communities:
        if c.network_status == 'left':
            days_since = (_time.time() - (c.network_left_at or 0)) / 86400
            if days_since < NETWORK_REAPPLY_DAYS:
                rejoinable_communities.append(c)
            else:
                left_communities.append(c)

    # Determine if we're showing status page vs registration form
    show_status_page = bool(active_communities or rejoinable_communities)
    status_context = {}

    if show_status_page:
        # Ensure exactly one is_primary - if none set, mark the first approved or first pending
        if not any(c.is_primary for c in active_communities):
            approved = [c for c in active_communities if c.network_status == 'approved']
            if approved:
                try:
                    with get_db_session() as db:
                        db.query(WebCommunity).filter_by(id=approved[0].id).update({'is_primary': True})
                        db.commit()
                    approved[0].is_primary = True
                except Exception:
                    pass
            elif active_communities:
                try:
                    with get_db_session() as db:
                        db.query(WebCommunity).filter_by(id=active_communities[0].id).update({'is_primary': True})
                        db.commit()
                    active_communities[0].is_primary = True
                except Exception:
                    pass
        has_approved = any(c.network_status == 'approved' for c in active_communities)
        status_context = {
            'show_status_page': True,
            'active_communities': active_communities,
            'rejoinable_communities': rejoinable_communities,
            'has_approved': has_approved,
        }

    # --- Fluxer guilds owned by this user ---
    owned_fluxer = getattr(request.web_user, 'owned_fluxer_guilds', [])
    fluxer_guilds_data = []
    registered_fluxer_ids = set()

    if owned_fluxer:
        fluxer_ids = [g['id'] for g in owned_fluxer]
        try:
            with get_db_session() as db:
                rows = db.query(
                    WebFluxerGuildSettings.guild_id,
                    WebFluxerGuildSettings.guild_name,
                    WebFluxerGuildSettings.member_count,
                    WebFluxerGuildSettings.guild_icon_hash,
                ).filter(WebFluxerGuildSettings.guild_id.in_(fluxer_ids)).all()
                fluxer_guilds_data = [
                    {'id': r[0], 'name': r[1] or r[0], 'member_count': r[2] or 0}
                    for r in rows
                ]
        except Exception:
            pass

        try:
            with get_db_session() as db:
                ph = ','.join(f':f{i}' for i in range(len(fluxer_ids)))
                params = {f'f{i}': v for i, v in enumerate(fluxer_ids)}
                rows2 = db.execute(
                    sa_text(f"SELECT platform_id FROM web_communities WHERE platform='fluxer' AND platform_id IN ({ph})"),
                    params,
                ).fetchall()
                registered_fluxer_ids = {r[0] for r in rows2}
        except Exception:
            pass

    # --- Discord guilds owned by this user (from WardenBot's guilds table) ---
    discord_guilds_data = []
    registered_discord_ids = set()
    discord_id = str(getattr(request.web_user, 'discord_id', '') or '')

    if discord_id:
        try:
            with get_db_session() as db:
                rows = db.execute(
                    sa_text(
                        "SELECT guild_id, guild_name, member_count FROM guilds "
                        "WHERE owner_id = :oid AND bot_present = 1"
                    ),
                    {'oid': int(discord_id)},
                ).fetchall()
                discord_guilds_data = [
                    {'id': str(r[0]), 'name': r[1] or str(r[0]), 'member_count': r[2] or 0}
                    for r in rows
                ]
                if discord_guilds_data:
                    discord_ids = [g['id'] for g in discord_guilds_data]
                    ph = ','.join(f':d{i}' for i in range(len(discord_ids)))
                    params = {f'd{i}': v for i, v in enumerate(discord_ids)}
                    rows3 = db.execute(
                        sa_text(f"SELECT platform_id FROM web_communities WHERE platform='discord' AND platform_id IN ({ph})"),
                        params,
                    ).fetchall()
                    registered_discord_ids = {r[0] for r in rows3}
        except Exception:
            pass

    # --- Matrix spaces owned by this user ---
    matrix_spaces_data = []
    registered_matrix_ids = set()
    matrix_id = str(getattr(request.web_user, 'matrix_id', '') or '')

    if matrix_id:
        try:
            with get_db_session() as db:
                rows = db.execute(
                    sa_text(
                        "SELECT space_id, space_name, member_count FROM web_matrix_space_settings "
                        "WHERE owner_matrix_id = :mid"
                    ),
                    {'mid': matrix_id},
                ).fetchall()
                matrix_spaces_data = [
                    {'id': r[0], 'name': r[1] or r[0], 'member_count': r[2] or 0}
                    for r in rows
                ]
                if matrix_spaces_data:
                    space_ids = [s['id'] for s in matrix_spaces_data]
                    ph = ','.join(f':m{i}' for i in range(len(space_ids)))
                    params = {f'm{i}': v for i, v in enumerate(space_ids)}
                    rows4 = db.execute(
                        sa_text(f"SELECT platform_id FROM web_communities WHERE platform='matrix' AND platform_id IN ({ph})"),
                        params,
                    ).fetchall()
                    registered_matrix_ids = {r[0] for r in rows4}
        except Exception:
            pass

    picker_context = {
        'fluxer_guilds_json': _json.dumps(fluxer_guilds_data),
        'discord_guilds_json': _json.dumps(discord_guilds_data),
        'matrix_spaces_json': _json.dumps(matrix_spaces_data),
        'registered_fluxer_ids_json': _json.dumps(list(registered_fluxer_ids)),
        'registered_discord_ids_json': _json.dumps(list(registered_discord_ids)),
        'registered_matrix_ids_json': _json.dumps(list(registered_matrix_ids)),
    }

    context = {
        'web_user': request.web_user,
        'active_page': 'community_register',
        **status_context,
        **picker_context,
    }
    return render(request, 'questlog_web/community_register.html', context)


@web_login_required
@add_web_user_context
def community_detail(request, community_id):
    """View community details."""
    context = {
        'web_user': request.web_user,
        'active_page': 'communities',
        'community_id': community_id,
    }
    return render(request, 'questlog_web/community_detail.html', context)


# =============================================================================
# PROFILE VIEWS
# =============================================================================

@web_login_required
@add_web_user_context
def profile(request):
    """View own profile."""
    import json as _json
    wu = request.web_user
    creator_profile = None
    user_communities = []
    seen_ids = set()
    with get_db_session() as db:
        cp = db.query(WebCreatorProfile).filter_by(user_id=wu.id).first()
        if cp:
            db.expunge(cp)
            creator_profile = cp
        # Communities for primary community picker: membership records, owned, and bot activity
        def _add_community(c):
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                user_communities.append({
                    'id': c.id, 'name': c.name,
                    'platform': c.platform.value if hasattr(c.platform, 'value') else c.platform,
                    'icon_url': c.icon_url or '',
                })
        # 1. Explicit membership records
        memberships = db.query(WebCommunityMember).filter_by(user_id=wu.id).all()
        member_ids = [m.community_id for m in memberships]
        if member_ids:
            for c in db.query(WebCommunity).filter(
                WebCommunity.id.in_(member_ids),
                WebCommunity.is_active == True,
                WebCommunity.network_status == 'approved',
            ).order_by(WebCommunity.name).all():
                _add_community(c)
        # 2. Owned communities
        for c in db.query(WebCommunity).filter(
            WebCommunity.owner_id == wu.id,
            WebCommunity.is_active == True,
            WebCommunity.network_status == 'approved',
        ).order_by(WebCommunity.name).all():
            _add_community(c)
        # 3. Communities via Fluxer bot activity (fluxer_member_xp)
        if wu.fluxer_id:
            fluxer_guild_rows = db.execute(
                text("SELECT DISTINCT guild_id FROM fluxer_member_xp WHERE user_id = :uid"),
                {'uid': wu.fluxer_id}
            ).fetchall()
            fluxer_guild_ids = [str(r[0]) for r in fluxer_guild_rows]
            if fluxer_guild_ids:
                for c in db.query(WebCommunity).filter(
                    WebCommunity.platform == 'fluxer',
                    WebCommunity.platform_id.in_(fluxer_guild_ids),
                    WebCommunity.is_active == True,
                    WebCommunity.network_status == 'approved',
                ).order_by(WebCommunity.name).all():
                    _add_community(c)
        # 4. Communities via Discord bot activity (guild_members)
        if wu.discord_id:
            discord_guild_rows = db.execute(
                text("SELECT DISTINCT guild_id FROM guild_members WHERE user_id = :uid"),
                {'uid': wu.discord_id}
            ).fetchall()
            discord_guild_ids = [str(r[0]) for r in discord_guild_rows]
            if discord_guild_ids:
                for c in db.query(WebCommunity).filter(
                    WebCommunity.platform == 'discord',
                    WebCommunity.platform_id.in_(discord_guild_ids),
                    WebCommunity.is_active == True,
                    WebCommunity.network_status == 'approved',
                ).order_by(WebCommunity.name).all():
                    _add_community(c)
    context = {
        'web_user': wu,
        'active_page': 'profile',
        'gaming_platforms_list': _json.loads(wu.gaming_platforms) if wu.gaming_platforms else [],
        'favorite_genres_list':  _json.loads(wu.favorite_genres)  if wu.favorite_genres  else [],
        'favorite_games_list':   [
            g if isinstance(g, dict) else {'name': g, 'igdb_id': None, 'cover_url': ''}
            for g in (_json.loads(wu.favorite_games) if wu.favorite_games else [])
        ],
        'favorite_games_json':   wu.favorite_games or '[]',
        'playstyle_list': (
            _json.loads(wu.playstyle) if wu.playstyle and wu.playstyle.startswith('[')
            else ([wu.playstyle] if wu.playstyle else [])
        ),
        'creator_profile': creator_profile,
        'user_communities': user_communities,
        'playstyle_choices': ['Casual', 'Hardcore', 'Competitive', 'Completionist', 'Explorer', 'Social'],
        'platform_choices': ['PC', 'PS5', 'PS4', 'Xbox Series', 'Xbox One', 'Switch', 'Mobile', 'Steam Deck'],
        'genre_choices': ['RPG', 'FPS', 'MOBA', 'MMO', 'Strategy', 'Simulation', 'Survival', 'Horror', 'Souls-like', 'Platformer', 'Roguelike', 'Sports', 'Racing', 'Fighting', 'Puzzle'],
    }
    return render(request, 'questlog_web/profile.html', context)


@web_login_required
@add_web_user_context
def profile_edit(request):
    """Edit own profile."""
    user_communities = []
    seen_ids = set()
    with get_db_session() as db:
        # Collect communities from explicit membership records
        memberships = db.query(WebCommunityMember).filter_by(user_id=request.web_user.id).all()
        community_ids = [m.community_id for m in memberships]
        if community_ids:
            communities = db.query(WebCommunity).filter(
                WebCommunity.id.in_(community_ids),
                WebCommunity.is_active == True,
                WebCommunity.network_status == 'approved',
            ).order_by(WebCommunity.name).all()
            for c in communities:
                seen_ids.add(c.id)
                user_communities.append({
                    'id': c.id,
                    'name': c.name,
                    'platform': c.platform.value if hasattr(c.platform, 'value') else c.platform,
                    'icon_url': c.icon_url or '',
                })
        # Also include communities the user owns (owners are implicit members)
        owned = db.query(WebCommunity).filter(
            WebCommunity.owner_id == request.web_user.id,
            WebCommunity.is_active == True,
            WebCommunity.network_status == 'approved',
        ).order_by(WebCommunity.name).all()
        for c in owned:
            if c.id not in seen_ids:
                seen_ids.add(c.id)
                user_communities.append({
                    'id': c.id,
                    'name': c.name,
                    'platform': c.platform.value if hasattr(c.platform, 'value') else c.platform,
                    'icon_url': c.icon_url or '',
                })
        # Also include communities found via Fluxer bot activity
        wu = request.web_user
        if wu.fluxer_id:
            fluxer_rows = db.execute(
                text("SELECT DISTINCT guild_id FROM fluxer_member_xp WHERE user_id = :uid"),
                {'uid': wu.fluxer_id}
            ).fetchall()
            fids = [str(r[0]) for r in fluxer_rows]
            if fids:
                for c in db.query(WebCommunity).filter(
                    WebCommunity.platform == 'fluxer',
                    WebCommunity.platform_id.in_(fids),
                    WebCommunity.is_active == True,
                    WebCommunity.network_status == 'approved',
                ).order_by(WebCommunity.name).all():
                    if c.id not in seen_ids:
                        seen_ids.add(c.id)
                        user_communities.append({
                            'id': c.id, 'name': c.name,
                            'platform': c.platform.value if hasattr(c.platform, 'value') else c.platform,
                            'icon_url': c.icon_url or '',
                        })
        # Also include communities found via Discord bot activity
        if wu.discord_id:
            discord_rows = db.execute(
                text("SELECT DISTINCT guild_id FROM guild_members WHERE user_id = :uid"),
                {'uid': wu.discord_id}
            ).fetchall()
            dids = [str(r[0]) for r in discord_rows]
            if dids:
                for c in db.query(WebCommunity).filter(
                    WebCommunity.platform == 'discord',
                    WebCommunity.platform_id.in_(dids),
                    WebCommunity.is_active == True,
                    WebCommunity.network_status == 'approved',
                ).order_by(WebCommunity.name).all():
                    if c.id not in seen_ids:
                        seen_ids.add(c.id)
                        user_communities.append({
                            'id': c.id, 'name': c.name,
                            'platform': c.platform.value if hasattr(c.platform, 'value') else c.platform,
                            'icon_url': c.icon_url or '',
                        })

    import json as _json2
    raw_fav = getattr(request.web_user, 'favorite_games', None) or '[]'
    try:
        fav_games_parsed = _json2.loads(raw_fav)
        fav_games = []
        for g in fav_games_parsed:
            if isinstance(g, dict) and g.get('name'):
                fav_games.append(g)
            elif isinstance(g, str) and g:
                fav_games.append({'name': g, 'igdb_id': None, 'cover_url': ''})
    except Exception:
        fav_games = []

    context = {
        'web_user': request.web_user,
        'active_page': 'profile',
        'user_communities': user_communities,
        'favorite_games_json': _json2.dumps(fav_games),
    }
    return render(request, 'questlog_web/profile_edit.html', context)


@web_login_required
@add_web_user_context
def creator_register(request):
    """Register/edit creator profile."""
    with get_db_session() as db:
        profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
        if profile and not profile.banner_url and profile.youtube_channel_id and profile.youtube_access_token:
            # Backfill YouTube banner for existing connections
            try:
                from app.utils.encryption import decrypt_token
                from app.services.youtube_service import YouTubeService
                svc = YouTubeService()
                access_token = decrypt_token(profile.youtube_access_token)
                channel_info = svc.get_channel_info(access_token)
                if channel_info.get('banner_url'):
                    profile.banner_url = channel_info['banner_url']
                    db.commit()
            except Exception:
                pass
        if profile:
            db.expunge(profile)

    context = {
        'web_user': request.web_user,
        'active_page': 'creator_register',
        'profile': profile,
        'twitch_configured': bool(django_settings.TWITCH_CLIENT_ID),
        'youtube_configured': bool(django_settings.YOUTUBE_CLIENT_ID),
        'kick_configured': bool(getattr(django_settings, 'KICK_CLIENT_ID', '')),
    }
    return render(request, 'questlog_web/creator_register.html', context)


@web_login_required
def settings(request):
    """Settings page — redirected to profile edit tab."""
    return redirect('/ql/profile/#edit')


@web_login_required
@add_web_user_context
def hero_shop(request):
    """Hero Shop — browse and buy flairs with Hero Points."""
    context = {
        'web_user': request.web_user,
        'active_page': 'shop',
    }
    return render(request, 'questlog_web/shop.html', context)


@web_login_required
@add_web_user_context
def game_servers_ql(request):
    """Community-hosted game servers — login required."""
    import asyncio
    from app.models import SiteActivityGame
    from app.views import fetch_instance_data

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    hosted_games = []

    try:
        with get_db_session() as db:
            db_games = (
                db.query(SiteActivityGame)
                .filter(
                    SiteActivityGame.is_active == True,
                    SiteActivityGame.display_on.in_(['gameservers', 'both']),
                )
                .order_by(SiteActivityGame.sort_order)
                .all()
            )

            amp_instance_names = [g.amp_instance_id for g in db_games if g.amp_instance_id]
            amp_data_map = {}
            if amp_instance_names:
                amp_results = loop.run_until_complete(asyncio.gather(
                    *(fetch_instance_data(name) for name in amp_instance_names),
                    return_exceptions=True
                ))
                amp_data_map = {g.get('id'): g for g in amp_results if isinstance(g, dict)}

            for db_game in db_games:
                game_dict = {
                    'id': db_game.game_key,
                    'name': db_game.display_name,
                    'description': db_game.description or '',
                    'steam_appid': db_game.steam_appid,
                    'steam_header_url': db_game.steam_header_url,
                    'custom_img': db_game.custom_img,
                    'steam_link': db_game.steam_link,
                    'discord_invite': db_game.discord_invite,
                    'link_label': db_game.link_label or 'View on Steam',
                    'online': '-',
                    'max': '-',
                    'live_now': False,
                }
                amp_data = amp_data_map.get(db_game.amp_instance_id)
                if amp_data:
                    game_dict.update({
                        'online': amp_data.get('online', '-'),
                        'max': amp_data.get('max', '-'),
                        'live_now': amp_data.get('live_now', False),
                        'ip': amp_data.get('ip', 'Unavailable'),
                        'connect_pw': amp_data.get('connect_pw', ''),
                        'status_label': amp_data.get('status_label', 'Unknown'),
                    })
                hosted_games.append(game_dict)
    except Exception as e:
        logger.error('game_servers_ql: failed to load servers: %s', e)

    # Fetch active server rotation poll
    active_poll = None
    try:
        with get_db_session() as db:
            poll = (
                db.query(WebServerPoll)
                .filter_by(is_active=True, is_ended=False)
                .first()
            )
            if poll:
                options = (
                    db.query(WebServerPollOption)
                    .filter_by(poll_id=poll.id)
                    .order_by(WebServerPollOption.sort_order, WebServerPollOption.id)
                    .all()
                )
                total_votes = sum(o.vote_count for o in options)
                user_vote_option_id = None
                if request.web_user:
                    uv = db.query(WebServerPollVote).filter_by(
                        poll_id=poll.id, user_id=request.web_user.id
                    ).first()
                    if uv:
                        user_vote_option_id = uv.option_id
                active_poll = {
                    'id': poll.id,
                    'title': poll.title,
                    'description': poll.description,
                    'show_results': poll.show_results_before_end,
                    'ends_at': poll.ends_at,
                    'total_votes': total_votes,
                    'user_vote_option_id': user_vote_option_id,
                    'options': [
                        {
                            'id': o.id,
                            'game_name': o.game_name,
                            'description': o.description,
                            'image_url': o.image_url,
                            'steam_appid': o.steam_appid,
                            'vote_count': o.vote_count,
                            'pct': round((o.vote_count / total_votes) * 100) if total_votes > 0 else 0,
                        }
                        for o in options
                    ],
                }
    except Exception as e:
        logger.error('game_servers_ql: failed to load poll: %s', e)

    context = {
        'web_user': request.web_user,
        'active_page': 'game_servers',
        'games': hosted_games,
        'active_poll': active_poll,
    }
    return render(request, 'questlog_web/gameservers.html', context)


# =============================================================================
# SERVER ROTATION POLL — PUBLIC API
# =============================================================================

@require_http_methods(["GET"])
def api_active_poll(request):
    """Return the active server rotation poll (public)."""
    try:
        with get_db_session() as db:
            poll = (
                db.query(WebServerPoll)
                .filter_by(is_active=True, is_ended=False)
                .first()
            )
            if not poll:
                return JsonResponse({'poll': None})
            options = (
                db.query(WebServerPollOption)
                .filter_by(poll_id=poll.id)
                .order_by(WebServerPollOption.sort_order, WebServerPollOption.id)
                .all()
            )
            total_votes = sum(o.vote_count for o in options)
            user_vote_option_id = None
            if request.web_user:
                uv = db.query(WebServerPollVote).filter_by(
                    poll_id=poll.id, user_id=request.web_user.id
                ).first()
                if uv:
                    user_vote_option_id = uv.option_id
            return JsonResponse({
                'poll': {
                    'id': poll.id,
                    'title': poll.title,
                    'description': poll.description,
                    'show_results': poll.show_results_before_end,
                    'ends_at': poll.ends_at,
                    'total_votes': total_votes,
                    'user_vote_option_id': user_vote_option_id,
                    'options': [
                        {
                            'id': o.id,
                            'game_name': o.game_name,
                            'description': o.description,
                            'image_url': o.image_url,
                            'steam_appid': o.steam_appid,
                            'vote_count': o.vote_count,
                        }
                        for o in options
                    ],
                }
            })
    except Exception as e:
        logger.error('api_active_poll: %s', e)
        return JsonResponse({'error': 'Failed to load poll'}, status=500)


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/h', block=True)
def api_poll_vote(request, poll_id):
    """Cast or change a vote on a server rotation poll."""
    try:
        data = json.loads(request.body)
        option_id = int(data.get('option_id', 0))
        if not option_id:
            return JsonResponse({'error': 'option_id required'}, status=400)
    except (ValueError, KeyError):
        return JsonResponse({'error': 'Invalid data'}, status=400)

    try:
        with get_db_session() as db:
            poll = db.query(WebServerPoll).filter_by(
                id=poll_id, is_active=True, is_ended=False
            ).first()
            if not poll:
                return JsonResponse({'error': 'Poll not found or closed'}, status=404)
            # Lock new option row first to prevent race conditions on concurrent votes
            option = db.query(WebServerPollOption).filter_by(
                id=option_id, poll_id=poll_id
            ).with_for_update().first()
            if not option:
                return JsonResponse({'error': 'Invalid option'}, status=400)

            existing = db.query(WebServerPollVote).filter_by(
                poll_id=poll_id, user_id=request.web_user.id
            ).with_for_update().first()
            if existing:
                if existing.option_id == option_id:
                    # Already voted for this option — return current state
                    total = sum(
                        o.vote_count for o in
                        db.query(WebServerPollOption).filter_by(poll_id=poll_id).all()
                    )
                    return JsonResponse({'success': True, 'already_voted': True,
                                        'option_id': option_id, 'total_votes': total})
                # Change vote: lock old option row before decrementing
                old_opt = db.query(WebServerPollOption).filter_by(
                    id=existing.option_id
                ).with_for_update().first()
                if old_opt and old_opt.vote_count > 0:
                    old_opt.vote_count -= 1
                existing.option_id = option_id
                existing.created_at = int(time.time())
                option.vote_count = (option.vote_count or 0) + 1
            else:
                db.add(WebServerPollVote(
                    poll_id=poll_id,
                    option_id=option_id,
                    user_id=request.web_user.id,
                    created_at=int(time.time()),
                ))
                option.vote_count = (option.vote_count or 0) + 1
            db.commit()

            total = sum(
                o.vote_count for o in
                db.query(WebServerPollOption).filter_by(poll_id=poll_id).all()
            )
            options = (
                db.query(WebServerPollOption)
                .filter_by(poll_id=poll_id)
                .order_by(WebServerPollOption.sort_order, WebServerPollOption.id)
                .all()
            )
            return JsonResponse({
                'success': True,
                'option_id': option_id,
                'total_votes': total,
                'options': [
                    {'id': o.id, 'vote_count': o.vote_count}
                    for o in options
                ],
            })
    except Exception as e:
        logger.error('api_poll_vote: %s', e)
        return JsonResponse({'error': 'Vote failed'}, status=500)


@add_web_user_context
def giveaways_page(request):
    """Giveaways page - shows active and recent giveaways."""
    context = {
        'web_user': request.web_user,
        'active_page': 'giveaways',
    }
    return render(request, 'questlog_web/giveaways.html', context)


# =============================================================================
# FLUXER MEMBER PORTAL
# =============================================================================

@web_login_required
@add_web_user_context
def fluxer_member_portal(request, guild_id):
    """Member-facing portal for a Fluxer guild. Shown when clicking My Servers."""
    from django.contrib import messages as dj_messages
    guild_id = guild_id.strip()

    with get_db_session() as db:
        settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
        if settings:
            db.expunge(settings)

    if not settings:
        dj_messages.error(request, "Server not found.")
        return redirect('questlog_web_home')

    guild_name = settings.guild_name or guild_id

    # Guild icon URL from Fluxer CDN
    _icon_hash = getattr(settings, 'guild_icon_hash', None) or ''
    if _icon_hash and not re.match(r'^[A-Za-z0-9_\-]+$', _icon_hash):
        _icon_hash = ''
    guild_icon_url = (
        f'https://fluxerusercontent.com/icons/{guild_id}/{_icon_hash}.png'
        if _icon_hash else None
    )

    # Determine if current user is the guild owner or admin
    _discord_id = str(getattr(request.web_user, 'discord_id', '') or '')
    _fluxer_id = str(getattr(request.web_user, 'fluxer_id', '') or '')
    _owner_id = str(getattr(settings, 'owner_id', '') or '')
    is_owner = bool(_owner_id and _owner_id in (_discord_id, _fluxer_id))
    # Fallback: check owned_fluxer_guilds set by add_web_user_context (includes admin-role members)
    if not is_owner and request.web_user:
        _owned_ids = {str(g.get('id', '')) for g in getattr(request.web_user, 'owned_fluxer_guilds', []) or []}
        if guild_id in _owned_ids:
            is_owner = True
    # Fallback: check web_communities ownership (owner_id = web_user.id)
    if not is_owner and request.web_user:
        try:
            with get_db_session() as db:
                comm_owned = db.query(WebCommunity).filter_by(
                    platform=PlatformType.FLUXER,
                    platform_id=guild_id,
                    owner_id=request.web_user.id,
                ).first()
                if comm_owned:
                    is_owner = True
        except Exception:
            pass

    # Get user's XP in this guild and open LFG group count
    user_xp = 0
    open_lfg_count = 0
    fluxer_id = getattr(request.web_user, 'fluxer_id', None) or getattr(request.web_user, 'discord_id', None)

    if fluxer_id:
        try:
            with get_db_session() as db:
                xp_row = db.execute(
                    text("SELECT xp FROM fluxer_member_xp WHERE guild_id = :g AND user_id = :u LIMIT 1"),
                    {'g': guild_id, 'u': str(fluxer_id)},
                ).fetchone()
                if xp_row:
                    user_xp = int(xp_row[0])
        except Exception:
            pass

    try:
        with get_db_session() as db:
            lfg_row = db.execute(
                text("SELECT COUNT(*) FROM web_fluxer_lfg_groups WHERE guild_id = :g AND status = 'open'"),
                {'g': guild_id},
            ).fetchone()
            open_lfg_count = int(lfg_row[0]) if lfg_row else 0
    except Exception:
        pass

    # Check if this guild has an approved QuestLog Network community listing
    is_network_approved = False
    try:
        with get_db_session() as db:
            comm = db.query(WebCommunity).filter_by(
                platform=PlatformType.FLUXER,
                platform_id=guild_id,
                network_status='approved',
            ).first()
            is_network_approved = comm is not None
    except Exception:
        pass

    context = {
        'web_user': request.web_user,
        'active_page': 'dashboard',
        'guild_id': guild_id,
        'guild_name': guild_name,
        'guild_settings': settings,
        'guild_icon_url': guild_icon_url,
        'is_owner': is_owner,
        'user_xp': user_xp,
        'unified_xp': getattr(request.web_user, 'web_xp', 0) or 0,
        'open_lfg_count': open_lfg_count,
        'is_network_approved': is_network_approved,
    }
    return render(request, 'questlog_web/fluxer_member_portal.html', context)


# ---------------------------------------------------------------------------
# Helper: resolve guild settings + icon URL for member sub-pages
# ---------------------------------------------------------------------------
def _fluxer_guild_base_context(request, guild_id):
    """Returns (settings, base_ctx_dict) or raises Http404."""
    from django.http import Http404
    guild_id = guild_id.strip()
    with get_db_session() as db:
        settings = db.query(WebFluxerGuildSettings).filter_by(guild_id=guild_id).first()
        if settings:
            db.expunge(settings)
    if not settings:
        raise Http404
    guild_name = settings.guild_name or guild_id
    _icon_hash = getattr(settings, 'guild_icon_hash', None) or ''
    if _icon_hash and not re.match(r'^[A-Za-z0-9_\-]+$', _icon_hash):
        _icon_hash = ''
    guild_icon_url = (
        f'https://fluxerusercontent.com/icons/{guild_id}/{_icon_hash}.png'
        if _icon_hash else None
    )
    _discord_id = str(getattr(request.web_user, 'discord_id', '') or '')
    _fluxer_id = str(getattr(request.web_user, 'fluxer_id', '') or '')
    _owner_id = str(getattr(settings, 'owner_id', '') or '')
    is_owner = bool(_owner_id and _owner_id in (_discord_id, _fluxer_id))
    # Fallback: check owned_fluxer_guilds set by add_web_user_context (includes admin-role members)
    if not is_owner and request.web_user:
        _owned_ids = {str(g.get('id', '')) for g in getattr(request.web_user, 'owned_fluxer_guilds', []) or []}
        if guild_id in _owned_ids:
            is_owner = True
    is_network_approved = False
    try:
        with get_db_session() as db:
            comm = db.query(WebCommunity).filter_by(
                platform=PlatformType.FLUXER,
                platform_id=guild_id,
                network_status='approved',
            ).first()
            is_network_approved = comm is not None
            # Fallback: check web_communities ownership when owner_id is missing from settings
            if not is_owner and request.web_user and comm and comm.owner_id == request.web_user.id:
                is_owner = True
    except Exception:
        pass
    return settings, {
        'web_user': request.web_user,
        'guild_id': guild_id,
        'guild_name': guild_name,
        'guild_settings': settings,
        'guild_icon_url': guild_icon_url,
        'is_owner': is_owner,
        'is_network_approved': is_network_approved,
    }


# =============================================================================
# FLUXER MEMBER SUB-PAGES
# =============================================================================

@web_login_required
@add_web_user_context
def fluxer_guild_member_profile(request, guild_id):
    """Member's guild-specific profile: XP, LFG stats, flair."""
    settings, ctx = _fluxer_guild_base_context(request, guild_id)
    fluxer_id = str(getattr(request.web_user, 'fluxer_id', '') or getattr(request.web_user, 'discord_id', '') or '')
    guild_xp = 0
    lfg_stats = None
    try:
        with get_db_session() as db:
            if fluxer_id:
                row = db.execute(
                    text("SELECT xp FROM fluxer_member_xp WHERE guild_id=:g AND user_id=:u LIMIT 1"),
                    {'g': guild_id, 'u': fluxer_id},
                ).fetchone()
                if row:
                    guild_xp = int(row[0])
            # LFG attendance stats
            from .models import WebFluxerLfgMemberStats
            if fluxer_id:
                lfg_stats = db.query(WebFluxerLfgMemberStats).filter_by(
                    guild_id=guild_id, fluxer_user_id=fluxer_id,
                ).first()
                if lfg_stats:
                    db.expunge(lfg_stats)
    except Exception:
        pass
    ctx.update({
        'active_page': 'profile',
        'guild_xp': guild_xp,
        'lfg_stats': lfg_stats,
        'unified_xp': getattr(request.web_user, 'web_xp', 0) or 0,
        'unified_level': getattr(request.web_user, 'web_level', 1) or 1,
    })
    return render(request, 'questlog_web/fluxer_guild_member_profile.html', ctx)


@web_login_required
@add_web_user_context
def fluxer_guild_member_raffles(request, guild_id):
    """Member-facing raffle browser for a Fluxer guild."""
    _settings, ctx = _fluxer_guild_base_context(request, guild_id)
    ctx['active_page'] = 'raffles'
    return render(request, 'questlog_web/fluxer_guild_member_raffles.html', ctx)


@web_login_required
@add_web_user_context
@require_http_methods(['GET'])
def api_fluxer_member_raffles(request, guild_id):
    """JSON: list of active + ended raffles for this guild."""
    guild_id = guild_id.strip()
    fluxer_id = str(getattr(request.web_user, 'fluxer_id', '') or getattr(request.web_user, 'discord_id', '') or '')
    web_user_id = getattr(request.web_user, 'id', None)
    import time as _time
    now = int(_time.time())
    try:
        with get_db_session() as db:
            raffles = db.query(WebFluxerRaffle).filter_by(guild_id=guild_id).order_by(
                WebFluxerRaffle.created_at.desc()
            ).limit(50).all()
            # My entries
            my_entry_map = {}
            if web_user_id and raffles:
                raffle_ids = [r.id for r in raffles]
                entries = db.query(WebFluxerRaffleEntry).filter(
                    WebFluxerRaffleEntry.raffle_id.in_(raffle_ids),
                    WebFluxerRaffleEntry.web_user_id == web_user_id,
                ).all()
                my_entry_map = {e.raffle_id: e.ticket_count for e in entries}
            active, ended = [], []
            for r in raffles:
                import json as _json
                try:
                    winners = _json.loads(r.winners_json) if r.winners_json else []
                except Exception:
                    winners = []
                is_active = r.status == 'active' and (not r.ends_at or r.ends_at > now)
                d = {
                    'id': r.id,
                    'title': r.title,
                    'description': r.description or '',
                    'prize': r.prize or '',
                    'cost_hp': r.ticket_cost_hp or 0,
                    'max_winners': r.max_winners or 1,
                    'max_entries_per_user': r.max_entries_per_user or 0,
                    'status': r.status,
                    'start_at': r.starts_at,
                    'end_at': r.ends_at,
                    'winners': winners,
                    'my_tickets': my_entry_map.get(r.id, 0),
                }
                if is_active:
                    active.append(d)
                else:
                    ended.append(d)
        return JsonResponse({'active': active, 'ended': ended, 'hp': getattr(request.web_user, 'hero_points', 0)})
    except Exception as e:
        logger.error('api_fluxer_member_raffles error', exc_info=True)
        return JsonResponse({'error': 'An error occurred'}, status=500)


@web_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_fluxer_member_raffle_enter(request, guild_id, raffle_id):
    """POST: enter a guild raffle with Hero Points."""
    import json as _json, time as _time
    guild_id = guild_id.strip()
    web_user_id = getattr(request.web_user, 'id', None)
    if not web_user_id:
        return JsonResponse({'error': 'Not logged in'}, status=403)
    try:
        body = _json.loads(request.body)
        tickets = max(1, int(body.get('tickets', 1)))
    except Exception:
        tickets = 1
    try:
        with get_db_session() as db:
            from .models import WebUser
            raffle = db.query(WebFluxerRaffle).filter_by(id=raffle_id, guild_id=guild_id).first()
            if not raffle:
                return JsonResponse({'error': 'Raffle not found'}, status=404)
            now = int(_time.time())
            if raffle.status != 'active' or (raffle.ends_at and raffle.ends_at <= now):
                return JsonResponse({'error': 'Raffle is not active'}, status=400)
            cost_per = raffle.ticket_cost_hp or 0
            total_cost = cost_per * tickets
            user = db.query(WebUser).filter_by(id=web_user_id).first()
            if not user:
                return JsonResponse({'error': 'User not found'}, status=404)
            if user.hero_points < total_cost:
                return JsonResponse({'error': f'Not enough Hero Points. Need {total_cost}, have {user.hero_points}'}, status=400)
            # Check max entries
            if raffle.max_entries_per_user:
                existing = db.query(WebFluxerRaffleEntry).filter_by(
                    raffle_id=raffle_id, web_user_id=web_user_id
                ).first()
                current = existing.ticket_count if existing else 0
                if current + tickets > raffle.max_entries_per_user:
                    return JsonResponse({'error': f'Max {raffle.max_entries_per_user} entries allowed'}, status=400)
                if existing:
                    existing.ticket_count = current + tickets
                else:
                    db.add(WebFluxerRaffleEntry(
                        raffle_id=raffle_id, web_user_id=web_user_id,
                        fluxer_user_id=str(getattr(request.web_user, 'fluxer_id', '') or ''),
                        username=request.web_user.username,
                        ticket_count=tickets, entered_at=now,
                    ))
            else:
                existing = db.query(WebFluxerRaffleEntry).filter_by(
                    raffle_id=raffle_id, web_user_id=web_user_id
                ).first()
                if existing:
                    existing.ticket_count += tickets
                else:
                    db.add(WebFluxerRaffleEntry(
                        raffle_id=raffle_id, web_user_id=web_user_id,
                        fluxer_user_id=str(getattr(request.web_user, 'fluxer_id', '') or ''),
                        username=request.web_user.username,
                        ticket_count=tickets, entered_at=now,
                    ))
            user.hero_points -= total_cost
            db.commit()
            remaining_hp = user.hero_points
        return JsonResponse({'message': f'Entered {tickets} time(s)!', 'hp_remaining': remaining_hp})
    except Exception as e:
        logger.error('api_fluxer_member_raffle_enter error', exc_info=True)
        return JsonResponse({'error': 'An error occurred'}, status=500)


@web_login_required
@add_web_user_context
def fluxer_guild_member_rss(request, guild_id):
    """Member-facing RSS articles viewer for a Fluxer guild."""
    import json as _json
    from datetime import datetime
    _settings, ctx = _fluxer_guild_base_context(request, guild_id)

    feed_filter = safe_int(request.GET.get('feed_id', ''), default=0)

    feeds = []
    articles = []
    total_articles = 0

    try:
        with get_db_session() as db:
            feed_rows = db.query(WebFluxerRssFeed).filter_by(
                guild_id=guild_id, is_active=1
            ).order_by(WebFluxerRssFeed.created_at.asc()).all()
            for f in feed_rows:
                feeds.append({'id': f.id, 'label': f.label or f.url})

            q = db.query(WebFluxerRssArticle).filter_by(guild_id=guild_id)
            if feed_filter:
                q = q.filter(WebFluxerRssArticle.feed_id == feed_filter)
            total_articles = q.count()
            raw_articles = q.order_by(
                WebFluxerRssArticle.posted_at.desc()
            ).limit(200).all()

            for a in raw_articles:
                cats = []
                if a.entry_categories:
                    try:
                        cats = _json.loads(a.entry_categories)[:5]
                    except Exception:
                        pass
                published_str = None
                if a.published_at:
                    try:
                        published_str = datetime.fromtimestamp(a.published_at).strftime('%b %d, %Y')
                    except Exception:
                        pass
                posted_str = None
                if a.posted_at:
                    try:
                        posted_str = datetime.fromtimestamp(a.posted_at).strftime('%b %d, %Y')
                    except Exception:
                        pass
                safe_link = None
                if a.entry_link:
                    l = a.entry_link.lower().strip()
                    if l.startswith('http://') or l.startswith('https://'):
                        safe_link = a.entry_link
                articles.append({
                    'id': a.id,
                    'feed_id': a.feed_id,
                    'feed_label': a.feed_label or 'Feed',
                    'title': a.entry_title or 'Untitled',
                    'summary': a.entry_summary or '',
                    'link': safe_link,
                    'author': a.entry_author or '',
                    'thumbnail': a.entry_thumbnail or '',
                    'categories': cats,
                    'published_at': published_str,
                    'posted_at': posted_str,
                })
    except Exception:
        pass

    ctx.update({
        'active_page': 'rss',
        'feeds': feeds,
        'feeds_json': _json.dumps(feeds),
        'articles': articles,
        'total_articles': total_articles,
        'selected_feed_id': str(feed_filter) if feed_filter else '',
    })
    return render(request, 'questlog_web/fluxer_guild_member_rss.html', ctx)


@web_login_required
@add_web_user_context
def fluxer_guild_member_games(request, guild_id):
    """Member-facing found games page (from game discovery, mirrors Discord found-games page)."""
    import json as _json
    from datetime import datetime
    _settings, ctx = _fluxer_guild_base_context(request, guild_id)

    sort_by = request.GET.get('sort', 'release')
    game_name_filter = request.GET.get('game_name', '').strip()
    mode_filters = request.GET.getlist('mode')
    keyword_filters = request.GET.getlist('keyword')
    min_hype_param = request.GET.get('min_hype', '')
    min_hype = int(min_hype_param) if min_hype_param and min_hype_param.isdigit() else None
    search_id = request.GET.get('search_id', '')

    games = []
    search_configs = []
    total_found = 0

    try:
        with get_db_session() as db:
            query = db.query(WebFluxerFoundGame).filter_by(guild_id=guild_id)
            if search_id:
                query = query.filter(WebFluxerFoundGame.search_config_id == int(search_id))
            raw = query.order_by(WebFluxerFoundGame.found_at.desc()).limit(300).all()
            total_found = db.query(WebFluxerFoundGame).filter_by(guild_id=guild_id).count()

            # Public search configs for filter dropdown (show_on_website=1 only)
            cfg_rows = db.query(WebFluxerGameSearchConfig).filter_by(
                guild_id=guild_id, enabled=1, show_on_website=1
            ).order_by(WebFluxerGameSearchConfig.name).all()
            for c in cfg_rows:
                search_configs.append({'id': c.id, 'name': c.name})

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
                rd = g.release_date
                if rd:
                    try:
                        fmt_date = datetime.utcfromtimestamp(rd).strftime('%b %d, %Y')
                    except Exception:
                        fmt_date = 'TBD'
                else:
                    fmt_date = 'TBD'
                genres = _json.loads(g.genres) if g.genres else []
                tags = _json.loads(g.keywords) if g.keywords else []
                platforms = _json.loads(g.platforms_json) if g.platforms_json else []
                games.append({
                    'id': g.id,
                    'game_name': g.game_name,
                    'cover_url': g.cover_url or '',
                    'igdb_url': g.igdb_url or '',
                    'steam_url': g.steam_url or '',
                    'release_date': rd,
                    'release_date_fmt': fmt_date,
                    'genres': genres,
                    'keywords': tags,
                    'platforms': platforms,
                    'hypes': g.hypes,
                    'rating': g.rating,
                    'summary': g.summary or '',
                    'search_config_name': g.search_config_name or '',
                })

        # Sorting
        if sort_by == 'release':
            games.sort(key=lambda g: (0, g['release_date']) if g['release_date'] else (1, 0))
        elif sort_by == 'hype':
            games.sort(key=lambda g: -(g['hypes'] or 0))
        elif sort_by == 'name':
            games.sort(key=lambda g: g['game_name'].lower())
        # else: keep found_at desc

    except Exception:
        pass

    ctx.update({
        'active_page': 'games',
        'games': games,
        'total_found': total_found,
        'search_configs': search_configs,
        'sort_by': sort_by,
        'game_name_filter': game_name_filter,
        'min_hype_param': min_hype_param,
    })
    return render(request, 'questlog_web/fluxer_guild_member_games.html', ctx)


@web_login_required
@add_web_user_context
def fluxer_guild_member_flairs(request, guild_id):
    """Member-facing flair store for a Fluxer guild - shows guild-specific flairs."""
    from .models import WebFluxerGuildFlair, WebFluxerMemberFlair
    _settings, ctx = _fluxer_guild_base_context(request, guild_id)
    web_user_id = getattr(request.web_user, 'id', None)
    guild_flairs = []
    owned_flair_ids = set()
    equipped_flair_id = None
    try:
        with get_db_session() as db:
            flair_rows = db.query(WebFluxerGuildFlair).filter_by(
                guild_id=guild_id, enabled=1, admin_only=0
            ).order_by(WebFluxerGuildFlair.display_order, WebFluxerGuildFlair.id).all()
            for f in flair_rows:
                db.expunge(f)
            guild_flairs = flair_rows
            if web_user_id:
                owned_rows = db.query(WebFluxerMemberFlair).filter_by(
                    guild_id=guild_id, web_user_id=web_user_id
                ).all()
                owned_flair_ids = {o.guild_flair_id for o in owned_rows}
                equipped = next((o for o in owned_rows if o.equipped), None)
                equipped_flair_id = equipped.guild_flair_id if equipped else None
    except Exception:
        pass
    ctx.update({
        'active_page': 'flairs',
        'guild_flairs': guild_flairs,
        'owned_flair_ids': owned_flair_ids,
        'equipped_flair_id': equipped_flair_id,
        'hero_points': getattr(request.web_user, 'hero_points', 0) or 0,
    })
    return render(request, 'questlog_web/fluxer_guild_member_flairs.html', ctx)


# =============================================================================
# FLUXER MEMBER LFG BROWSE + JOIN/LEAVE
# =============================================================================

def _lfg_member_filter(query, request):
    """Filter WebFluxerLfgMember by the current user - matches on web_user_id OR fluxer_user_id."""
    web_user = getattr(request, 'web_user', None)
    fluxer_id = getattr(request, 'fluxer_id', None) or ''
    conditions = []
    if web_user and web_user.id:
        conditions.append(WebFluxerLfgMember.web_user_id == web_user.id)
    if fluxer_id:
        conditions.append(WebFluxerLfgMember.fluxer_user_id == fluxer_id)
    if not conditions:
        return query.filter(False)
    from sqlalchemy import or_
    return query.filter(or_(*conditions))

def _lfg_is_me(member, request):
    """Return True if a WebFluxerLfgMember row belongs to the current requester."""
    web_user = getattr(request, 'web_user', None)
    fluxer_id = getattr(request, 'fluxer_id', None) or ''
    if web_user and member.web_user_id and member.web_user_id == web_user.id:
        return True
    if fluxer_id and member.fluxer_user_id and member.fluxer_user_id == fluxer_id:
        return True
    return False


# WoW spec -> role mapping (ported from WardenBot lfg_role_mappings.py)
_WOW_SPEC_ROLE = {
    # Tanks
    'blood': 'tank', 'vengeance': 'tank', 'guardian': 'tank',
    'brewmaster': 'tank', 'protection': 'tank',
    # Healers
    'restoration': 'healer', 'preservation': 'healer', 'mistweaver': 'healer',
    'holy': 'healer', 'discipline': 'healer',
    # Support
    'augmentation': 'support',
    # DPS (everything else with explicit keys to avoid ambiguity)
    'frost': 'dps', 'unholy': 'dps', 'havoc': 'dps',
    'balance': 'dps', 'feral': 'dps', 'devastation': 'dps',
    'beast mastery': 'dps', 'marksmanship': 'dps', 'survival': 'dps',
    'arcane': 'dps', 'fire': 'dps',
    'windwalker': 'dps', 'retribution': 'dps', 'shadow': 'dps',
    'assassination': 'dps', 'outlaw': 'dps', 'subtlety': 'dps',
    'elemental': 'dps', 'enhancement': 'dps',
    'affliction': 'dps', 'demonology': 'dps', 'destruction': 'dps',
    'arms': 'dps', 'fury': 'dps',
}


def _detect_lfg_role(selections, options_json_str):
    """Detect a member's role (tank/healer/dps/support) from their LFG selections.

    Handles:
    - Games with an explicit Role field with {value, role} choices (e.g. ESO)
    - WoW-style spec -> role mapping via Specialization field
    - Fallback: plain Role string value
    Returns one of 'tank', 'healer', 'dps', 'support', or 'member'.
    """
    if not selections:
        return 'member'

    opts = []
    if options_json_str:
        try:
            opts = json.loads(options_json_str) or []
        except (json.JSONDecodeError, TypeError):
            opts = []

    # 1. Check for explicit Role field with {value, role} choices (ESO pattern)
    role_val = selections.get('Role') or selections.get('role')
    if role_val:
        if isinstance(role_val, list):
            role_val = role_val[0] if role_val else None
        if role_val:
            for opt in opts:
                if opt.get('name', '').lower() == 'role' and isinstance(opt.get('choices'), list):
                    for ch in opt['choices']:
                        if isinstance(ch, dict) and ch.get('value') == role_val and ch.get('role'):
                            return ch['role']
            # Plain string fallback (e.g. "tank", "healer")
            if role_val.lower() in ('tank', 'healer', 'dps', 'support'):
                return role_val.lower()

    # 2. WoW-style: detect from Specialization field
    spec_val = selections.get('Specialization') or selections.get('specialization') or selections.get('Spec') or ''
    if spec_val:
        if isinstance(spec_val, list):
            spec_val = spec_val[0] if spec_val else ''
        role = _WOW_SPEC_ROLE.get(spec_val.lower())
        if role:
            return role

    return 'member'


@fluxer_login_required
def fluxer_guild_member_lfg_browse(request, guild_id):
    """Member-facing LFG group browser for a Fluxer guild."""
    from .views_bot_dashboard import _lfg_game_dict
    _settings, ctx = _fluxer_guild_base_context(request, guild_id)

    with get_db_session() as db:
        groups = (
            db.query(WebFluxerLfgGroup)
            .filter_by(guild_id=guild_id, status='open')
            .order_by(WebFluxerLfgGroup.created_at.desc())
            .limit(100)
            .all()
        )
        games = (
            db.query(WebFluxerLfgGame)
            .filter_by(guild_id=guild_id, is_active=1)
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
            }
            for g in groups
        ]
        games_data = [
            {'id': gm.id, 'name': gm.name, 'emoji': gm.emoji or ''}
            for gm in games
        ]
        games_full = [_lfg_game_dict(gm) for gm in games]

    ctx.update({
        'active_page': 'lfg_browser',
        'groups_data': groups_data,
        'games_data': games_data,
        'games_full_data': games_full,
    })
    return render(request, 'questlog_web/fluxer_guild_member_lfg_browse.html', ctx)


@fluxer_login_required
@require_http_methods(['POST'])
def api_fluxer_member_lfg_join(request, guild_id, group_id):
    """POST join a Fluxer LFG group. Works for native Fluxer users and linked QL web users."""
    guild_id = guild_id.strip()
    group_id = safe_int(group_id, default=0, min_val=1)
    if not group_id:
        return JsonResponse({'error': 'Invalid group'}, status=400)

    web_user = request.web_user
    fluxer_id = request.fluxer_id or ''
    username = (web_user.display_name or web_user.username) if web_user else 'Fluxer User'
    now = int(time.time())

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        data = {}

    selections = data.get('selections') or {}

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(
            id=group_id, guild_id=guild_id, status='open'
        ).first()
        if not group:
            return JsonResponse({'error': 'Group not found or closed'}, status=404)
        if group.current_size >= group.max_size:
            return JsonResponse({'error': 'Group is full'}, status=400)

        existing_q = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id == group_id,
            WebFluxerLfgMember.left_at.is_(None),
        )
        existing_q = _lfg_member_filter(existing_q, request)
        if existing_q.first():
            return JsonResponse({'error': 'Already a member'}, status=400)

        # Detect role from selections using shared helper (handles ESO {value,role} + WoW spec mapping)
        game = db.query(WebFluxerLfgGame).filter_by(id=group.game_id).first()
        detected_role = _detect_lfg_role(selections, game.options_json if game else None)

        # Enforce role slot limits if enabled
        tanks_needed = getattr(group, 'tanks_needed', 0) or 0
        healers_needed = getattr(group, 'healers_needed', 0) or 0
        dps_needed = getattr(group, 'dps_needed', 0) or 0
        support_needed = getattr(group, 'support_needed', 0) or 0
        has_slots = tanks_needed + healers_needed + dps_needed + support_needed > 0
        if has_slots and getattr(group, 'enforce_role_limits', 1) and detected_role != 'member':
            limit_map = {'tank': tanks_needed, 'healer': healers_needed, 'dps': dps_needed, 'support': support_needed}
            slot_limit = limit_map.get(detected_role, 0)
            if slot_limit > 0:
                current_members = db.query(WebFluxerLfgMember).filter(
                    WebFluxerLfgMember.group_id == group_id,
                    WebFluxerLfgMember.left_at.is_(None),
                    WebFluxerLfgMember.role == detected_role,
                ).count()
                if current_members >= slot_limit:
                    label = detected_role.capitalize()
                    return JsonResponse({'error': f'All {label} slots are full ({slot_limit}/{slot_limit}). Choose a different role.'}, status=400)

        db.add(WebFluxerLfgMember(
            group_id=group_id,
            web_user_id=web_user.id if web_user else None,
            fluxer_user_id=fluxer_id or None,
            username=username,
            role=detected_role,
            selections_json=json.dumps(selections) if selections else None,
            is_creator=0,
            joined_at=now,
        ))
        group.current_size = (group.current_size or 0) + 1
        if group.current_size >= group.max_size:
            group.status = 'full'

        # Capture for post-commit notification
        notify_guild_id = group.guild_id
        notify_channel_id = group.channel_id
        notify_game = group.game_name
        notify_title = group.title or group.game_name
        new_size = group.current_size
        new_status = group.status
        group_creator_web_user_id = group.creator_web_user_id

        db.commit()

    # Site notification to group creator (if they have a web account)
    if group_creator_web_user_id and web_user:
        try:
            with get_db_session() as db:
                create_notification(
                    db, group_creator_web_user_id, web_user.id,
                    'lfg_join',
                    target_type='fluxer_lfg_group', target_id=group_id,
                    message=f"{username} joined your LFG group: {notify_title}",
                )
                db.commit()
        except Exception as e:
            logger.warning(f"[LFG] Failed to create site join notification for Fluxer group {group_id}: {e}")

    # Build role detail from selections
    sel_parts = []
    for key, val in selections.items():
        if key.lower() in ('activity', 'role', 'player_role'):
            continue
        v = val[0] if isinstance(val, list) and val else val
        if v:
            sel_parts.append(str(v))
    if detected_role and detected_role != 'member':
        sel_parts.insert(0, detected_role.title())
    join_detail = ', '.join(sel_parts) if sel_parts else ''

    # Send join notification to Fluxer guild channel
    if notify_channel_id and notify_guild_id:
        try:
            from sqlalchemy import text as _text
            lfg_url = f"https://casual-heroes.com/ql/fluxer/{notify_guild_id}/lfg/browse/"
            detail_field = {"name": "Class / Role", "value": join_detail, "inline": True} if join_detail else None
            profile_val = f"casual-heroes.com/ql/profile/{username}/" if web_user else username
            embed_data = {
                "title": f"New Member Joined: {notify_title}",
                "description": (
                    f"**{username}** joined the group.\n"
                    f"[View on QuestLog]({lfg_url})"
                ),
                "color": 0x57F287,
                "fields": [f for f in [
                    {"name": "Game", "value": notify_game, "inline": True},
                    detail_field,
                    {"name": "Profile", "value": profile_val, "inline": True},
                ] if f],
                "footer": "QuestLog Network - casual-heroes.com/ql/lfg/",
            }
            with get_db_session() as db:
                db.execute(
                    _text("INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at) VALUES (:g, :c, :p, :t)"),
                    {"g": notify_guild_id, "c": notify_channel_id, "p": json.dumps(embed_data), "t": int(time.time())}
                )
                db.commit()
        except Exception as e:
            logger.warning(f"[LFG] Failed to queue Fluxer member join notification for group {group_id}: {e}")

    return JsonResponse({'success': True, 'new_size': new_size, 'status': new_status})


@fluxer_login_required
@require_http_methods(['POST'])
def api_fluxer_member_lfg_leave(request, guild_id, group_id):
    """POST leave a Fluxer LFG group."""
    guild_id = guild_id.strip()
    group_id = safe_int(group_id, default=0, min_val=1)
    if not group_id:
        return JsonResponse({'error': 'Invalid group'}, status=400)

    now = int(time.time())

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id, guild_id=guild_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        member_q = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id == group_id,
            WebFluxerLfgMember.left_at.is_(None),
        )
        member = _lfg_member_filter(member_q, request).first()
        if not member:
            return JsonResponse({'error': 'Not a member of this group'}, status=400)
        if member.is_creator:
            return JsonResponse({'error': 'Group leaders cannot leave - delete the group instead'}, status=400)

        member.left_at = now
        group.current_size = max(0, (group.current_size or 1) - 1)
        if group.status == 'full':
            group.status = 'open'
        db.commit()
        return JsonResponse({'success': True, 'new_size': group.current_size, 'status': group.status})

    return JsonResponse({'success': True})


@fluxer_login_required
def fluxer_guild_member_lfg_calendar(request, guild_id):
    """Member-facing LFG calendar for a Fluxer guild."""
    guild_id = guild_id.strip()
    now_ts = int(time.time())
    cutoff = now_ts - 86400
    current_user_id = getattr(request.web_user, 'id', None) if request.web_user else None

    _settings, ctx = _fluxer_guild_base_context(request, guild_id)

    with get_db_session() as db:
        groups = (
            db.query(WebFluxerLfgGroup)
            .filter(
                WebFluxerLfgGroup.guild_id == guild_id,
                WebFluxerLfgGroup.scheduled_time != None,  # noqa: E711
                WebFluxerLfgGroup.scheduled_time >= cutoff,
                WebFluxerLfgGroup.status.in_(['open', 'full']),
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

    ctx.update({
        'active_page': 'lfg_calendar',
        'events_json': json.dumps(events),
        'my_group_ids_json': json.dumps(my_group_ids),
        'my_creator_ids_json': json.dumps(my_creator_ids),
    })
    return render(request, 'questlog_web/fluxer_guild_member_lfg_calendar.html', ctx)


@fluxer_login_required
@require_http_methods(['GET', 'POST'])
def api_fluxer_member_lfg_groups(request, guild_id):
    """GET list / POST create LFG groups for the member portal."""
    if request.method == 'POST':
        from .views_bot_dashboard import api_fluxer_guild_lfg_groups
        return api_fluxer_guild_lfg_groups(request, guild_id)
    from .views_bot_dashboard import _group_dict
    guild_id = guild_id.strip()
    web_user = request.web_user
    fluxer_id = request.fluxer_id or ''

    with get_db_session() as db:
        groups = db.query(WebFluxerLfgGroup).filter(
            WebFluxerLfgGroup.guild_id == guild_id,
            WebFluxerLfgGroup.status.in_(['open', 'full']),
        ).order_by(WebFluxerLfgGroup.created_at.desc()).limit(100).all()

        group_ids = [g.id for g in groups]
        members_raw = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id.in_(group_ids),
            WebFluxerLfgMember.left_at.is_(None),
        ).all() if group_ids else []

        # Determine current user's web_user_id for the JS CURRENT_WEB_USER_ID check
        # For native Fluxer users we also expose fluxer_user_id so the template can match
        members_by_group: dict = {}
        for m in members_raw:
            members_by_group.setdefault(m.group_id, []).append({
                'id': m.id,
                'username': m.username or 'Unknown',
                'role': m.role or 'member',
                'is_creator': bool(m.is_creator),
                'is_co_leader': (m.role or '') == 'co_leader',
                'web_user_id': m.web_user_id,
                'fluxer_user_id': m.fluxer_user_id or '',
                'selections': json.loads(m.selections_json) if m.selections_json else {},
                'joined_at': m.joined_at,
            })

        return JsonResponse({'success': True, 'groups': [
            _group_dict(g, members_by_group.get(g.id, [])) for g in groups
        ]})


@fluxer_login_required
@require_http_methods(['DELETE'])
def api_fluxer_member_lfg_group_delete(request, guild_id, group_id):
    """DELETE own LFG group (creator only)."""
    guild_id = guild_id.strip()
    group_id = safe_int(group_id, default=0, min_val=1)
    if not group_id:
        return JsonResponse({'error': 'Invalid group'}, status=400)

    web_user = request.web_user
    fluxer_id = request.fluxer_id or ''

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id, guild_id=guild_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        # Check ownership: match by web_user_id OR fluxer creator id
        is_owner = False
        if web_user and group.creator_web_user_id and group.creator_web_user_id == web_user.id:
            is_owner = True
        if not is_owner and fluxer_id:
            creator_member = db.query(WebFluxerLfgMember).filter_by(
                group_id=group_id, is_creator=1
            ).filter(WebFluxerLfgMember.fluxer_user_id == fluxer_id).first()
            if creator_member:
                is_owner = True
        if not is_owner:
            return JsonResponse({'error': 'Only the group creator can delete this group'}, status=403)

        group.status = 'closed'
        db.commit()

    return JsonResponse({'success': True})


@fluxer_login_required
@require_http_methods(['POST'])
def api_fluxer_member_lfg_kick(request, guild_id, group_id, member_id):
    """POST kick a member (leader or co-leader; co-leader cannot kick the leader)."""
    guild_id = guild_id.strip()
    group_id = safe_int(group_id, default=0, min_val=1)
    member_id = safe_int(member_id, default=0, min_val=1)
    if not group_id or not member_id:
        return JsonResponse({'error': 'Invalid group or member'}, status=400)

    now = int(time.time())

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id, guild_id=guild_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        requester_q = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id == group_id,
            WebFluxerLfgMember.left_at.is_(None),
        )
        requester = _lfg_member_filter(requester_q, request).first()
        if not requester:
            return JsonResponse({'error': 'You are not in this group'}, status=403)
        is_leader = bool(requester.is_creator)
        is_co_leader = (requester.role or '') == 'co_leader'
        if not is_leader and not is_co_leader:
            return JsonResponse({'error': 'Only leaders and co-leaders can kick members'}, status=403)

        target = db.query(WebFluxerLfgMember).filter_by(
            id=member_id, group_id=group_id
        ).filter(WebFluxerLfgMember.left_at.is_(None)).first()
        if not target:
            return JsonResponse({'error': 'Member not found'}, status=404)
        if _lfg_is_me(target, request):
            return JsonResponse({'error': 'Cannot kick yourself'}, status=400)
        if target.is_creator and not is_leader:
            return JsonResponse({'error': 'Co-leaders cannot kick the group leader'}, status=403)

        target.left_at = now
        group.current_size = max(0, (group.current_size or 1) - 1)
        if group.status == 'full':
            group.status = 'open'
        db.commit()

    return JsonResponse({'success': True})


@fluxer_login_required
@require_http_methods(['POST'])
def api_fluxer_member_lfg_ban(request, guild_id, group_id, member_id):
    """POST ban a member from LFG in this guild (leader only; co-leaders cannot ban)."""
    guild_id = guild_id.strip()
    group_id = safe_int(group_id, default=0, min_val=1)
    member_id = safe_int(member_id, default=0, min_val=1)
    if not group_id or not member_id:
        return JsonResponse({'error': 'Invalid group or member'}, status=400)

    now = int(time.time())

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        data = {}
    from .helpers import sanitize_text
    ban_reason = sanitize_text(data.get('reason', '') or '').strip()[:200] or 'Banned from LFG group by group leader'

    with get_db_session() as db:
        group = db.query(WebFluxerLfgGroup).filter_by(id=group_id, guild_id=guild_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)

        requester_q = db.query(WebFluxerLfgMember).filter(
            WebFluxerLfgMember.group_id == group_id,
            WebFluxerLfgMember.left_at.is_(None),
        )
        requester = _lfg_member_filter(requester_q, request).first()
        if not requester or not requester.is_creator:
            return JsonResponse({'error': 'Only the group leader can ban members'}, status=403)

        target = db.query(WebFluxerLfgMember).filter_by(
            id=member_id, group_id=group_id
        ).filter(WebFluxerLfgMember.left_at.is_(None)).first()
        if not target:
            return JsonResponse({'error': 'Member not found'}, status=404)
        if _lfg_is_me(target, request):
            return JsonResponse({'error': 'Cannot ban yourself'}, status=400)

        # Prefer the target's own fluxer_user_id; fall back to resolving via web_user
        target_fluxer_id = target.fluxer_user_id or None
        if not target_fluxer_id and target.web_user_id:
            from .models import WebUser
            target_wu = db.query(WebUser).filter_by(id=target.web_user_id).first()
            if target_wu:
                target_fluxer_id = target_wu.fluxer_id

        target.left_at = now
        group.current_size = max(0, (group.current_size or 1) - 1)
        if group.status == 'full':
            group.status = 'open'

        if target_fluxer_id:
            from .models import WebFluxerLfgMemberStats
            stats = db.query(WebFluxerLfgMemberStats).filter_by(
                guild_id=guild_id, fluxer_user_id=str(target_fluxer_id)
            ).first()
            if stats:
                stats.is_blacklisted = 1
                stats.blacklist_reason = ban_reason
                stats.blacklisted_at = now
                stats.updated_at = now
            else:
                db.add(WebFluxerLfgMemberStats(
                    guild_id=guild_id,
                    fluxer_user_id=str(target_fluxer_id),
                    is_blacklisted=1,
                    blacklist_reason=ban_reason,
                    blacklisted_at=now,
                    updated_at=now,
                    reliability_score=100,
                ))

        db.commit()

    return JsonResponse({'success': True})


# =============================================================================
# FLUXER GUILD FLAIR STORE - BUY / EQUIP / UNEQUIP
# =============================================================================

def _queue_guild_flair_role_update(web_user_id: int, action: str, flair_emoji: str | None, flair_name: str | None):
    """Queue a flair role sync for the Fluxer bot."""
    try:
        from .models import WebFluxerRoleUpdate
        with get_db_session() as db:
            db.add(WebFluxerRoleUpdate(
                web_user_id=web_user_id,
                action=action,
                flair_emoji=flair_emoji,
                flair_name=flair_name,
                created_at=int(time.time()),
            ))
            db.commit()
    except Exception as exc:
        logger.warning(f'_queue_guild_flair_role_update: failed for user {web_user_id}: {exc}')


@web_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_fluxer_guild_flair_buy(request, guild_id, flair_id):
    """Buy a guild flair with Hero Points."""
    from .models import WebFluxerGuildFlair, WebFluxerMemberFlair, WebUser, WebHeroPointEvent
    guild_id = guild_id.strip()
    web_user_id = request.web_user.id

    with get_db_session() as db:
        flair = db.query(WebFluxerGuildFlair).filter_by(
            id=flair_id, guild_id=guild_id, enabled=1
        ).first()
        if not flair:
            return JsonResponse({'error': 'Flair not found'}, status=404)
        if flair.admin_only:
            return JsonResponse({'error': 'This flair can only be assigned by an admin'}, status=403)

        already = db.query(WebFluxerMemberFlair).filter_by(
            guild_id=guild_id, web_user_id=web_user_id, guild_flair_id=flair_id
        ).first()
        if already:
            return JsonResponse({'error': 'You already own this flair'}, status=400)

        cost = flair.hp_cost or 0
        user = db.query(WebUser).filter_by(id=web_user_id).with_for_update().first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        if (user.hero_points or 0) < cost:
            return JsonResponse({'error': f'Not enough Hero Points (need {cost}, have {user.hero_points or 0})'}, status=400)

        now = int(time.time())
        if cost > 0:
            user.hero_points = (user.hero_points or 0) - cost
            db.add(WebHeroPointEvent(
                user_id=user.id,
                action_type='guild_flair_purchase',
                points=-cost,
                source='fluxer_store',
                ref_id=f'gf_{flair_id}',
                created_at=now,
            ))
        db.add(WebFluxerMemberFlair(
            guild_id=guild_id,
            web_user_id=web_user_id,
            guild_flair_id=flair_id,
            equipped=0,
            bought_at=now,
        ))
        db.commit()

    return JsonResponse({'success': True, 'hero_points': user.hero_points})


@web_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_fluxer_guild_flair_equip(request, guild_id, flair_id):
    """Equip a guild flair the member owns. Unequips all others in this guild."""
    from .models import WebFluxerGuildFlair, WebFluxerMemberFlair, WebUser
    guild_id = guild_id.strip()
    web_user_id = request.web_user.id

    with get_db_session() as db:
        owned = db.query(WebFluxerMemberFlair).filter_by(
            guild_id=guild_id, web_user_id=web_user_id, guild_flair_id=flair_id
        ).first()
        if not owned:
            return JsonResponse({'error': 'You do not own this flair'}, status=403)

        flair = db.query(WebFluxerGuildFlair).filter_by(id=flair_id).first()

        # Unequip all in this guild, then equip this one
        db.query(WebFluxerMemberFlair).filter_by(
            guild_id=guild_id, web_user_id=web_user_id, equipped=1
        ).update({'equipped': 0}, synchronize_session=False)
        owned.equipped = 1
        db.commit()

    flair_emoji = flair.emoji if flair else ''
    flair_name = flair.flair_name if flair else ''
    _queue_guild_flair_role_update(web_user_id, 'set_flair', flair_emoji, flair_name)

    return JsonResponse({'success': True, 'equipped_flair_id': flair_id})


@web_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_fluxer_guild_flair_unequip(request, guild_id, flair_id):
    """Unequip a guild flair."""
    from .models import WebFluxerMemberFlair
    guild_id = guild_id.strip()
    web_user_id = request.web_user.id

    with get_db_session() as db:
        owned = db.query(WebFluxerMemberFlair).filter_by(
            guild_id=guild_id, web_user_id=web_user_id, guild_flair_id=flair_id
        ).first()
        if not owned:
            return JsonResponse({'error': 'You do not own this flair'}, status=403)

        db.query(WebFluxerMemberFlair).filter_by(
            guild_id=guild_id, web_user_id=web_user_id
        ).update({'equipped': 0}, synchronize_session=False)
        db.commit()

    _queue_guild_flair_role_update(web_user_id, 'clear_flair', None, None)
    return JsonResponse({'success': True, 'equipped_flair_id': None})
