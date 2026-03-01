# QuestLog Web — template renderers (GET only, return render())

import json
import logging
import time

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django.conf import settings as django_settings
from django_ratelimit.decorators import ratelimit

from .models import (
    WebCreatorProfile, PlatformType, WebLFGGroup, WebLFGMember,
    WebServerPoll, WebServerPollOption, WebServerPollVote,
)
from app.db import get_db_session
from .helpers import (
    web_login_required, add_web_user_context, safe_int,
)

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


# =============================================================================
# LFG VIEWS
# =============================================================================

@web_login_required
def lfg_browse(request):
    """Browse LFG groups."""
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_browse',
    }
    return render(request, 'questlog_web/lfg_browse.html', context)


@web_login_required
def lfg_create(request):
    """Create LFG group."""
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_create',
    }
    return render(request, 'questlog_web/lfg_create.html', context)


@web_login_required
def lfg_my_groups(request):
    """View user's LFG groups."""
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_my_groups',
    }
    return render(request, 'questlog_web/lfg_my_groups.html', context)


@web_login_required
def lfg_group_detail(request, group_id):
    """View LFG group details."""
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_browse',
        'group_id': group_id,
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
            # Rejoining after leaving — update the existing row
            existing.status = 'joined'
            existing.left_at = None
            existing.role = data.get('role') or None
            raw_sel = data.get('selections') or {}
            existing.selections = json.dumps(raw_sel) if raw_sel else None
            existing.joined_at = now
        else:
            raw_sel = data.get('selections') or {}
            db.add(WebLFGMember(
                group_id=group_id,
                user_id=request.web_user.id,
                role=data.get('role') or None,
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
        db.commit()

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
        if group.status == 'full':
            group.status = 'open'
        group.updated_at = now
        db.commit()

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

        member.role = data.get('role') or None
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
def network(request):
    """QuestLog Network page."""
    context = {
        'web_user': request.web_user,
        'active_page': 'network',
    }
    return render(request, 'questlog_web/network.html', context)


@web_login_required
def games(request):
    """Found Games / Game Discovery."""
    context = {
        'web_user': request.web_user,
        'active_page': 'games',
    }
    return render(request, 'questlog_web/games.html', context)


@web_login_required
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
def communities(request):
    """Community directory."""
    context = {
        'web_user': request.web_user,
        'active_page': 'communities',
    }
    return render(request, 'questlog_web/communities.html', context)


@web_login_required
def community_register(request):
    """Register a community."""
    context = {
        'web_user': request.web_user,
        'active_page': 'community_register',
        'platform_types': [(p.value, p.name.title()) for p in PlatformType if p != PlatformType.GUILDED],
    }
    return render(request, 'questlog_web/community_register.html', context)


@web_login_required
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
def profile(request):
    """View own profile."""
    import json as _json
    wu = request.web_user
    creator_profile = None
    with get_db_session() as db:
        cp = db.query(WebCreatorProfile).filter_by(user_id=wu.id).first()
        if cp:
            db.expunge(cp)
            creator_profile = cp
    context = {
        'web_user': wu,
        'active_page': 'profile',
        'gaming_platforms_list': _json.loads(wu.gaming_platforms) if wu.gaming_platforms else [],
        'favorite_genres_list':  _json.loads(wu.favorite_genres)  if wu.favorite_genres  else [],
        'favorite_games_list':   _json.loads(wu.favorite_games)   if wu.favorite_games   else [],
        'playstyle_list': (
            _json.loads(wu.playstyle) if wu.playstyle and wu.playstyle.startswith('[')
            else ([wu.playstyle] if wu.playstyle else [])
        ),
        'creator_profile': creator_profile,
        'playstyle_choices': ['Casual', 'Hardcore', 'Competitive', 'Completionist', 'Explorer', 'Social'],
        'platform_choices': ['PC', 'PS5', 'PS4', 'Xbox Series', 'Xbox One', 'Switch', 'Mobile', 'Steam Deck'],
        'genre_choices': ['RPG', 'FPS', 'MOBA', 'MMO', 'Strategy', 'Simulation', 'Survival', 'Horror', 'Souls-like', 'Platformer', 'Roguelike', 'Sports', 'Racing', 'Fighting', 'Puzzle'],
    }
    return render(request, 'questlog_web/profile.html', context)


@web_login_required
def profile_edit(request):
    """Edit own profile."""
    context = {
        'web_user': request.web_user,
        'active_page': 'profile',
    }
    return render(request, 'questlog_web/profile_edit.html', context)


@web_login_required
def creator_register(request):
    """Register/edit creator profile."""
    with get_db_session() as db:
        profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
        if profile:
            db.expunge(profile)

    context = {
        'web_user': request.web_user,
        'active_page': 'creator_register',
        'profile': profile,
        'twitch_configured': bool(django_settings.TWITCH_CLIENT_ID),
        'youtube_configured': bool(django_settings.YOUTUBE_CLIENT_ID),
    }
    return render(request, 'questlog_web/creator_register.html', context)


@web_login_required
def settings(request):
    """Settings page — redirected to profile edit tab."""
    return redirect('/ql/profile/#edit')


@web_login_required
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
            option = db.query(WebServerPollOption).filter_by(
                id=option_id, poll_id=poll_id
            ).first()
            if not option:
                return JsonResponse({'error': 'Invalid option'}, status=400)

            existing = db.query(WebServerPollVote).filter_by(
                poll_id=poll_id, user_id=request.web_user.id
            ).first()
            if existing:
                if existing.option_id == option_id:
                    # Already voted for this option — return current state
                    total = sum(
                        o.vote_count for o in
                        db.query(WebServerPollOption).filter_by(poll_id=poll_id).all()
                    )
                    return JsonResponse({'success': True, 'already_voted': True,
                                        'option_id': option_id, 'total_votes': total})
                # Change vote: decrement old, increment new
                old_opt = db.query(WebServerPollOption).filter_by(
                    id=existing.option_id
                ).first()
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
