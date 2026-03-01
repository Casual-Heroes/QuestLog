# QuestLog Web — admin views & APIs

import json
import time
import logging
import os
import requests as _requests

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from sqlalchemy import or_

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
)
from app.security_middleware import MAINTENANCE_FLAG
from app.db import get_db_session
from app.models import SiteActivityGame, SiteActivityGuildRole
from .helpers import (
    web_login_required, web_admin_required, log_admin_action,
    serialize_post, fetch_rss_feed, create_notification,
    serialize_user_brief, safe_int, validate_admin_image_url,
)

logger = logging.getLogger(__name__)


@web_login_required
def admin_verify_pin(request):
    """Legacy endpoint — PIN auth replaced by Django superuser check."""
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect('questlog_web_admin')
    messages.error(request, "Access denied.")
    return redirect('questlog_web_home')


@web_admin_required
def admin_panel(request):
    """Admin panel — Django superusers only."""
    context = {
        'web_user': request.web_user,
        'active_page': 'admin',
    }
    return render(request, 'questlog_web/admin.html', context)


@web_admin_required
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


# --- LFG Game Config Admin ---

@web_admin_required
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
        log_admin_action(request, 'update_lfg_game', 'lfg_game', game_id, body)
        return JsonResponse({'success': True})


# --- Community Admin ---

@web_admin_required
def api_admin_communities(request):
    """API: List all communities for admin."""
    with get_db_session() as db:
        communities = db.query(WebCommunity).order_by(WebCommunity.created_at.desc()).all()
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
            'is_active': c.is_active,
            'is_banned': c.is_banned,
            'ban_reason': c.ban_reason,
            'created_at': c.created_at,
        } for c in communities]
    return JsonResponse({'communities': data})


@web_admin_required
@require_http_methods(["POST"])
def api_admin_community_action(request, community_id):
    """API: Admin actions on a community (approve, ban, unban, purge)."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = body.get('action')
    if action not in ('approve', 'deny', 'ban', 'unban', 'purge', 'toggle_discovery'):
        return JsonResponse({'error': 'Invalid action'}, status=400)

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

@web_admin_required
def api_admin_creators(request):
    """API: List all creators for admin."""
    with get_db_session() as db:
        creators = db.query(WebCreatorProfile).order_by(WebCreatorProfile.created_at.desc()).all()
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


@web_admin_required
@require_http_methods(["POST"])
def api_admin_creator_action(request, creator_id):
    """API: Admin actions on a creator (verify, unverify, feature, delete)."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = body.get('action')
    valid_actions = ('verify', 'unverify', 'feature', 'delete', 'set_cotw', 'unset_cotw', 'set_cotm', 'unset_cotm')
    if action not in valid_actions:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        creator = db.query(WebCreatorProfile).filter_by(id=creator_id).first()
        if not creator:
            return JsonResponse({'error': 'Not found'}, status=404)

        if action == 'verify':
            creator.is_verified = True
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
            # Clear existing COTW — a creator can't hold both titles at once
            db.query(WebCreatorProfile).filter(WebCreatorProfile.is_current_cotw == True).update({'is_current_cotw': False})
            creator.is_current_cotw = True
            creator.cotw_last_featured = now
            creator.times_featured = (creator.times_featured or 0) + 1
            creator.featured_at = now
        elif action == 'unset_cotw':
            creator.is_current_cotw = False
        elif action == 'set_cotm':
            # Same anti-double-dip logic as COTW
            db.query(WebCreatorProfile).filter(WebCreatorProfile.is_current_cotm == True).update({'is_current_cotm': False})
            creator.is_current_cotm = True
            creator.cotm_last_featured = now
            creator.times_featured = (creator.times_featured or 0) + 1
            creator.featured_at = now
        elif action == 'unset_cotm':
            creator.is_current_cotm = False

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


@web_admin_required
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


@web_admin_required
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
        log_admin_action(request, 'update_steam_search', 'steam_search', search_id, body)
        return JsonResponse({'success': True})


@web_admin_required
@require_http_methods(["POST"])
def api_admin_run_steam_search(request, search_id):
    """API: Immediately run a Steam search config.
    ?clear=1  — delete all WebFoundGame rows for this config first, then re-run.
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
    """API: List/manage found games."""
    with get_db_session() as db:
        games = db.query(WebFoundGame).order_by(WebFoundGame.found_at.desc()).limit(100).all()
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
            'found_at': g.found_at,
        } for g in games]
    return JsonResponse({'games': data})


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
            feeds = db.query(WebRSSFeed).order_by(WebRSSFeed.created_at.desc()).all()
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
def api_admin_users(request):
    """API: List users for admin."""
    q = request.GET.get('q', '').strip()
    with get_db_session() as db:
        query = db.query(WebUser).order_by(WebUser.created_at.desc())
        if q:
            query = query.filter(
                or_(WebUser.username.ilike(f'%{q}%'), WebUser.display_name.ilike(f'%{q}%'))
            )
        users = query.limit(200).all()
        data = [{
            'id': u.id,
            'username': u.username,
            'display_name': u.display_name,
            'email': u.email,
            'avatar_url': u.avatar_url,
            'is_admin': u.is_admin,
            'is_vip': bool(u.is_vip),
            'is_banned': u.is_banned,
            'ban_reason': u.ban_reason,
            'is_disabled': u.is_disabled,
            'posting_timeout_until': u.posting_timeout_until,
            'post_count': u.post_count,
            'web_xp': u.web_xp,
            'web_level': u.web_level,
            'hero_points': u.hero_points,
            'created_at': u.created_at,
            'last_login_at': u.last_login_at,
        } for u in users]
    return JsonResponse({'users': data})


@web_admin_required
@require_http_methods(["POST"])
def api_admin_user_action(request, user_id):
    """API: Admin actions on user (ban, unban, toggle admin)."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = body.get('action')
    valid_actions = ('ban', 'unban', 'disable', 'enable', 'timeout', 'clear_timeout',
                     'make_admin', 'remove_admin', 'set_hero_points', 'delete_posts',
                     'purge_user', 'grant_vip', 'revoke_vip')
    if action not in valid_actions:
        return JsonResponse({'error': 'Invalid action'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user:
            return JsonResponse({'error': 'Not found'}, status=404)

        # Prevent self-action on destructive operations
        if user_id == request.web_user.id and action in ('ban', 'disable', 'remove_admin'):
            return JsonResponse({'error': 'Cannot perform this action on your own account'}, status=400)

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
        elif action == 'remove_admin':
            user.is_admin = False
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
            # Leave the flair in their collection — it's a reward they earned

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
    log_admin_action(request, f'{action}_user', 'user', user_id, {
        'action': action,
        'target_username': user.username if user else 'unknown',
        'reason': body.get('reason', ''),
    })
    return JsonResponse({'success': True})


# --- Admin Audit Log ---

@web_admin_required
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

@web_admin_required
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


@web_admin_required
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


@web_admin_required
@require_http_methods(["POST"])
def api_admin_comment_action(request, comment_id):
    """POST: Admin action on a comment (delete/hide)."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')
    if action not in ('delete', 'hide'):
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

@web_admin_required
def admin_games_tracker(request):
    """Admin page for managing /gamesweplay/ game list."""
    with get_db_session() as db:
        games = db.query(SiteActivityGame).order_by(
            SiteActivityGame.sort_order, SiteActivityGame.display_name
        ).all()

        games_data = []
        for game in games:
            roles = db.query(SiteActivityGuildRole).filter_by(game_id=game.id, is_active=True).all()
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
            })

    return render(request, 'questlog_web/admin_games_tracker.html', {
        'games': games_data,
        'web_user': request.web_user,
        'active_page': 'admin',
    })


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
                    'sort_order': game.sort_order,
                    'roles': [{
                        'id': r.id,
                        'guild_id': str(r.guild_id),
                        'role_id': str(r.role_id),
                        'guild_name': r.guild_name,
                        'role_name': r.role_name,
                    } for r in roles],
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
            game.sort_order = data.get('sort_order', game.sort_order)
            game.updated_at = int(time.time())

            # Replace role mappings if provided
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


@web_admin_required
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


@web_admin_required
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
                'enabled': f.enabled,
                'display_order': f.display_order,
                'created_at': f.created_at,
                'owner_count': db.query(WebUserFlair).filter_by(flair_id=f.id).count(),
            } for f in flairs]})

        # POST — create
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
            enabled=bool(body.get('enabled', True)),
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

        # PUT — update
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
        if 'enabled' in body:
            flair.enabled = bool(body['enabled'])
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

        # POST — create
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
# ADMIN: STEAM GAME SEARCH (proxy — avoids browser CORS)
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

        # POST — create
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


@web_admin_required
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

        # PUT — update
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


@web_admin_required
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


@web_admin_required
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


@web_admin_required
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


@web_admin_required
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


@web_admin_required
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


@web_admin_required
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
        return JsonResponse({'success': True, 'notified': notif_count, 'giveaway': _giveaway_dict(g, db)})


@web_admin_required
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


@web_admin_required
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

        db.commit()
        log_admin_action(request, 'pick_giveaway_winner', 'giveaway', giveaway_id,
                         {'winner_ids': [w.user_id for w in winners]})
        return JsonResponse({'success': True, 'giveaway': _giveaway_dict(g, db, include_entries=False)})
