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
    WebFluxerWebhookConfig,
    WebCommunityBotConfig,
    WebEarlyAccessCode,
    WebSubscriptionEvent,
    WebBridgeConfig, WebBridgeRelayQueue,
    WebFluxerGuildChannel,
    WebCustomEmoji,
)
from app.security_middleware import MAINTENANCE_FLAG
from app.db import get_db_session
from .fluxer_webhooks import notify_giveaway_start as _fluxer_giveaway_start, notify_giveaway_winner as _fluxer_giveaway_winner
from app.models import SiteActivityGame, SiteActivityGuildRole
from .helpers import (
    web_login_required, web_admin_required, log_admin_action,
    serialize_post, fetch_rss_feed, create_notification,
    serialize_user_brief, safe_int, validate_admin_image_url,
    process_uploaded_image,
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
            'site_xp_to_guild': bool(c.site_xp_to_guild),
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
    if action not in ('approve', 'deny', 'ban', 'unban', 'purge', 'toggle_discovery', 'remove_from_network', 'toggle_unified_xp'):
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
        elif action == 'toggle_unified_xp':
            community.site_xp_to_guild = not community.site_xp_to_guild
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

        # Notify Fluxer channel
        _fluxer_giveaway_start(
            title=g.title,
            prize=g.prize or '',
            giveaway_url="https://casual-heroes.com/ql/giveaways/",
        )
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
        'embed_color': cfg.embed_color or '',
        'message_template': cfg.message_template or '',
        'embed_title': cfg.embed_title or '',
        'embed_footer': cfg.embed_footer or '',
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

    guild_id        = data.get('guild_id', '').strip()[:32]
    channel_id      = data.get('channel_id', '').strip()[:32]
    channel_name    = data.get('channel_name', '').strip()[:200]
    embed_color     = data.get('embed_color', '').strip()[:7]
    message_template = (data.get('message_template') or '').strip()[:4000]
    embed_title     = (data.get('embed_title') or '').strip()[:255]
    embed_footer    = (data.get('embed_footer') or '').strip()[:255]
    is_enabled      = bool(data.get('is_enabled', False))

    if embed_color and not (embed_color.startswith('#') and len(embed_color) == 7):
        return JsonResponse({'error': 'embed_color must be #RRGGBB format'}, status=400)

    with get_db_session() as db:
        cfg = db.query(WebFluxerWebhookConfig).filter_by(id=config_id).first()
        if not cfg:
            return JsonResponse({'error': 'Config not found'}, status=404)

        cfg.guild_id         = guild_id or cfg.guild_id
        cfg.channel_id       = channel_id or cfg.channel_id
        cfg.channel_name     = channel_name or cfg.channel_name
        cfg.embed_color      = embed_color or cfg.embed_color
        cfg.message_template = message_template or cfg.message_template
        cfg.embed_title      = embed_title or cfg.embed_title
        cfg.embed_footer     = embed_footer or cfg.embed_footer
        cfg.is_enabled       = is_enabled and bool(cfg.channel_id)
        cfg.updated_at       = int(time.time())
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
            "footer": cfg.embed_footer or f"QuestLog - casual-heroes.com/ql/",
        }
        if cfg.event_type in _default_fields:
            embed["fields"] = _default_fields[cfg.event_type]
        if cfg.event_type == 'lfg_announce':
            embed["url"] = "https://casual-heroes.com/ql/lfg/"

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

@web_admin_required
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
        return JsonResponse({'error': str(e)}, status=400)
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


@web_admin_required
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
