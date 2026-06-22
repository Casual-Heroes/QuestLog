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
    WebTestimonial,
)
from app.db import get_db_session
from .helpers import (
    web_login_required, web_verified_required, add_web_user_context, safe_int, EXCLUDED_USER_IDS,
    fluxer_login_required, create_notification, sanitize_text,
)
from .fluxer_webhooks import queue_lfg_embed_edit_for_group as _queue_lfg_embed_edit

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
@add_web_user_context
def home(request):
    """Casual Heroes / QuestLog landing page - accessible to all users."""
    # Load the primary community to drive the hub banner
    primary_community = None
    try:
        from .models import WebCommunity
        with get_db_session() as db:
            # Site owner (id=1) primary community drives the landing page hub banner
            c = db.query(WebCommunity).filter_by(
                is_primary=True,
                network_status='approved',
                is_active=True,
                owner_id=1,
            ).first()
            if c:
                # Resolve enum to string for template use
                plat = c.platform.value if hasattr(c.platform, 'value') else str(c.platform)
                primary_community = {
                    'name': c.name,
                    'platform': plat,
                    'icon_url': c.icon_url or '',
                    'invite_url': c.invite_url or '',
                    'short_description': c.short_description or '',
                }
    except Exception as _e:
        logger.error(f"home: failed to load primary_community: {_e}")

    return render(request, 'questlog_web/landing.html', {
        'web_user': request.web_user,
        'active_page': 'home',
        'primary_community': primary_community,
    })


@add_web_user_context
def community_guidelines(request):
    """QuestLog Network community guidelines page."""
    return render(request, 'questlog_web/community_guidelines.html', {
        'web_user': request.web_user,
        'active_page': 'community_guidelines',
    })


# =============================================================================
# DISCOVERY VIEW
# =============================================================================

@add_web_user_context
def discover(request):
    """Discovery homepage - Communities + LFG groups + Streamers + Game servers."""
    import random as _random
    import asyncio
    now = int(time.time())
    hour_ago = now - 3600

    live_streamers = []
    lfg_groups = []
    active_games = []
    featured_communities = []
    game_servers = []
    community_counts = {}  # platform -> count of approved communities
    groups_last_hour = 0

    recently_streamed = []
    try:
        from .models import WebUser, WebCreatorProfile, WebCommunity
        from sqlalchemy import func
        _STABLE_CDN = ('https://static-cdn.jtvnw.net/', 'https://yt3.', 'https://yt3.ggpht.')
        def _valid_avatar(a):
            if not a: return None
            if a.startswith('/media/'): return a
            if any(a.startswith(cdn) for cdn in _STABLE_CDN): return a
            return None
        thirty_days_ago = now - (30 * 86400)
        with get_db_session() as db:
            # --- Live streamers (max 4) and recently streamed (max 4) ---
            creator_rows = db.query(WebCreatorProfile, WebUser).join(
                WebUser, WebUser.id == WebCreatorProfile.user_id
            ).filter(
                WebCreatorProfile.allow_discovery == True,
                WebUser.is_banned == False,
                WebUser.is_hidden == False,
            ).order_by(
                WebUser.is_live.desc(),
                WebCreatorProfile.is_current_cotm.desc(),
                WebCreatorProfile.is_current_cotw.desc(),
                WebCreatorProfile.follower_count.desc(),
            ).limit(20).all()

            for cp, u in creator_rows:
                # All connected platforms (used for LIVE display - show all active streams)
                all_platforms = []
                if cp.twitch_url:
                    all_platforms.append({'platform': 'twitch', 'url': cp.twitch_url})
                if cp.youtube_url:
                    all_platforms.append({'platform': 'youtube', 'url': cp.youtube_url})
                if cp.kick_url:
                    all_platforms.append({'platform': 'kick', 'url': cp.kick_url})

                # For "Previously Live": only the platform actually detected live last session
                last_platform = cp.latest_stream_platform if cp.latest_stream_platform else None
                url_map = {'twitch': cp.twitch_url, 'youtube': cp.youtube_url, 'kick': cp.kick_url}
                prev_platforms = [{'platform': last_platform, 'url': url_map.get(last_platform)}] if last_platform and url_map.get(last_platform) else []

                # Primary platform = first connected (for backwards compat)
                platform = all_platforms[0]['platform'] if all_platforms else None
                stream_url = all_platforms[0]['url'] if all_platforms else None

                resolved_avatar = _valid_avatar(cp.avatar_url) or _valid_avatar(u.avatar_url)
                base_entry = {
                    'username': u.username,
                    'display_name': cp.display_name or u.username,
                    'avatar_url': resolved_avatar,
                    'is_cotm': bool(cp.is_current_cotm),
                    'is_cotw': bool(cp.is_current_cotw),
                    'current_game': u.current_game or '',
                    'platform': platform,
                    'stream_url': stream_url,
                    'follower_count': cp.follower_count or 0,
                }

                if u.is_live and len(live_streamers) < 4:
                    live_streamers.append({**base_entry, 'platforms': all_platforms})
                elif not u.is_live and platform and len(recently_streamed) < 4:
                    # Only show in "Recently Streamed" if they have a stream platform
                    # and have an actual stream history within the last 30 days
                    last_streamed = getattr(cp, 'latest_stream_ended_at', None) or 0
                    if last_streamed >= thirty_days_ago:
                        recently_streamed.append({**base_entry, 'platforms': prev_platforms})

            # --- LFG groups (6 most recent open groups) with urgency tags ---
            groups = db.query(WebLFGGroup).filter(
                WebLFGGroup.status == 'open',
            ).order_by(WebLFGGroup.created_at.desc()).limit(6).all()

            for g in groups:
                slots_left = (g.group_size or 4) - (g.current_size or 1)
                fill_pct = (g.current_size or 1) / (g.group_size or 4)
                if slots_left == 0:
                    urgency = 'full'
                elif fill_pct >= 0.75:
                    urgency = 'almost_full'
                elif g.created_at and g.created_at >= hour_ago:
                    urgency = 'new'
                else:
                    urgency = 'recruiting'
                lfg_groups.append({
                    'id': g.id,
                    'share_token': g.share_token,
                    'title': g.title,
                    'game_name': g.game_name,
                    'game_image_url': g.game_image_url,
                    'current_size': g.current_size,
                    'group_size': g.group_size,
                    'slots_left': slots_left,
                    'status': g.status,
                    'created_at': g.created_at,
                    'urgency': urgency,
                })

            # --- Groups active in last hour (for section header badge) ---
            groups_last_hour = db.query(WebLFGGroup).filter(
                WebLFGGroup.status == 'open',
                WebLFGGroup.created_at >= hour_ago,
            ).count()

            # --- Active games: aggregate groups by game_name ---
            game_counts = db.query(
                WebLFGGroup.game_name,
                WebLFGGroup.game_image_url,
                func.count(WebLFGGroup.id).label('group_count'),
            ).filter(
                WebLFGGroup.status == 'open',
            ).group_by(
                WebLFGGroup.game_name, WebLFGGroup.game_image_url
            ).order_by(func.count(WebLFGGroup.id).desc()).limit(6).all()

            live_by_game = {}
            for s in live_streamers:
                if s['is_live'] and s['current_game']:
                    key = s['current_game'].lower()
                    live_by_game[key] = live_by_game.get(key, 0) + 1

            for row in game_counts:
                live_count = live_by_game.get((row.game_name or '').lower(), 0)
                active_games.append({
                    'game_name': row.game_name,
                    'game_image_url': row.game_image_url,
                    'group_count': row.group_count,
                    'live_count': live_count,
                })

            # --- Communities (up to 6 random approved, shown in 2-col grid) ---
            # Order: primary first so dedup keeps the right one per owner
            all_communities = db.query(WebCommunity).filter(
                WebCommunity.network_status == 'approved',
            ).order_by(WebCommunity.is_primary.desc()).all()

            # Fetch live member counts from platform-specific tables for Fluxer communities
            fluxer_ids = [
                c.platform_id for c in all_communities
                if c.platform and c.platform.value == 'fluxer' and c.platform_id
            ]
            fluxer_member_counts = {}
            if fluxer_ids:
                placeholders = ','.join([':fid' + str(i) for i in range(len(fluxer_ids))])
                params = {'fid' + str(i): v for i, v in enumerate(fluxer_ids)}
                rows = db.execute(
                    text(f"SELECT guild_id, member_count FROM web_fluxer_guild_settings WHERE guild_id IN ({placeholders})"),
                    params,
                ).fetchall()
                fluxer_member_counts = {r[0]: r[1] for r in rows}

            # Deduplicate by owner - one card per owner, preferring is_primary=True
            seen_owners = set()
            serialized_communities = []
            for c in all_communities:
                if c.owner_id and c.owner_id in seen_owners:
                    continue
                seen_owners.add(c.owner_id)
                plat = c.platform.value if c.platform else 'discord'
                community_counts[plat] = community_counts.get(plat, 0) + 1
                # Use live count from bot settings table when available, fall back to stored value
                if plat == 'fluxer' and c.platform_id and c.platform_id in fluxer_member_counts:
                    live_count = fluxer_member_counts[c.platform_id] or c.member_count or 0
                else:
                    live_count = c.member_count or 0
                import re as _re
                c_slug = _re.sub(r'[^a-z0-9]+', '-', c.name.lower()).strip('-')
                serialized_communities.append({
                    'id': c.id,
                    'slug': c_slug,
                    'name': c.name,
                    'description': c.description or '',
                    'avatar_url': c.icon_url or '',
                    'platform': plat,
                    'member_count': live_count,
                })

            featured_communities = _random.sample(
                serialized_communities, min(6, len(serialized_communities))
            )

    except Exception as e:
        logger.error('discover view error: %s', e)

    # Game server strip is loaded client-side via JS after page load to avoid blocking LCP

    # --- Community Steam widgets ---
    # Raw pool data (expensive Steam API calls) cached 15 min - shared across workers.
    # Community Picks shuffle is re-run every request from the cached pool so it's
    # always random. Most Played is deterministic so it comes straight from cache.
    top_owned_games = []
    community_picks = []
    _POOL_CACHE_KEY = 'discover_steam_pool_v2'
    try:
        import random as _rng
        from collections import Counter
        import requests as _req
        from django.core.cache import cache as _cache
        from .models import WebUser as _WebUser
        from .helpers import STEAM_API_KEY as _STEAM_KEY
        from .helpers import get_steam_cover_url as _steam_cover_url

        _SEXUAL_DESCRIPTOR_IDS = {1, 3, 4}
        _NAME_EXCLUDE = ('test server', 'beta server', 'dedicated server', ' pts', 'public test', 'demo')

        def _ensure_steam_tags(aid, db, _req):
            existing = db.execute(
                text('SELECT COUNT(*) FROM web_steam_app_tags WHERE app_id = :a'),
                {'a': aid}
            ).scalar()
            if existing:
                return
            tags = set()
            try:
                r = _req.get(
                    f'https://store.steampowered.com/api/appdetails?appids={aid}&filters=content_descriptors,categories,genres',
                    timeout=4,
                )
                data = (r.json() or {}).get(str(aid), {}).get('data', {})
                descriptor_ids = set(data.get('content_descriptors', {}).get('ids') or [])
                if descriptor_ids & _SEXUAL_DESCRIPTOR_IDS:
                    tags.add('sexual content')
                for c in data.get('categories', []):
                    tags.add(c.get('description', '').lower())
                for g in data.get('genres', []):
                    tags.add(g.get('description', '').lower())
            except Exception:
                pass
            try:
                r = _req.get(
                    f'https://steamspy.com/api.php?request=appdetails&appid={aid}',
                    timeout=5,
                )
                for tag in ((r.json() or {}).get('tags') or {}).keys():
                    tags.add(tag.lower())
            except Exception:
                pass
            if not tags:
                tags.add('untagged')
            db.execute(
                text('INSERT IGNORE INTO web_steam_app_tags (app_id, tag_name) VALUES ' +
                     ', '.join(f"({aid}, :t{i})" for i, _ in enumerate(tags))),
                {f't{i}': t for i, t in enumerate(tags)}
            )
            db.commit()

        # Try to load the cached pool (raw counters + names + adult_ids)
        _pool = _cache.get(_POOL_CACHE_KEY)

        if _pool is None:
            # Cache miss - fetch from Steam APIs and store the raw pool
            with get_db_session() as db:
                steam_users = db.query(_WebUser.steam_id).filter(
                    _WebUser.share_steam_library == True,
                    _WebUser.steam_id.isnot(None),
                    _WebUser.steam_id != '',
                    _WebUser.is_banned == False,
                    _WebUser.is_disabled == False,
                    _WebUser.is_hidden == False,
                ).limit(50).all()
                adult_rows = db.execute(
                    text("""SELECT DISTINCT app_id FROM web_steam_app_tags
                            WHERE tag_name IN ('sexual content','adult only sexual content',
                            'frequent nudity or sexual content','hentai','eroge',
                            'explicit sexual content')""")
                ).fetchall()
                adult_ids = {r[0] for r in adult_rows}
                mp_rows = db.execute(
                    text("SELECT DISTINCT app_id FROM web_steam_app_tags WHERE tag_name IN ('multiplayer','co-op','online co-op','multi-player')")
                ).fetchall()
                mp_ids = {r[0] for r in mp_rows}

            owned_counts = Counter()
            hours_totals = Counter()
            game_names = {}
            for (steam_id,) in steam_users:
                try:
                    resp = _req.get(
                        'https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/',
                        params={'key': _STEAM_KEY, 'steamid': steam_id, 'count': 0},
                        timeout=4,
                    )
                    for g in resp.json().get('response', {}).get('games', []):
                        aid = g.get('appid')
                        gname = g.get('name', '')
                        if not aid or aid in adult_ids:
                            continue
                        if any(x in gname.lower() for x in _NAME_EXCLUDE):
                            continue
                        owned_counts[aid] += 1
                        hours_totals[aid] += g.get('playtime_2weeks', 0)
                        if aid not in game_names:
                            game_names[aid] = gname
                except Exception:
                    continue

            picks_owned = Counter()
            picks_names = {}
            for (steam_id,) in steam_users:
                try:
                    resp2 = _req.get(
                        'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/',
                        params={'key': _STEAM_KEY, 'steamid': steam_id,
                                'include_appinfo': 1, 'include_played_free_games': 1},
                        timeout=4,
                    )
                    for g in resp2.json().get('response', {}).get('games', []):
                        aid = g.get('appid')
                        gname = g.get('name', '')
                        if not aid or aid in adult_ids or not gname:
                            continue
                        if any(x in gname.lower() for x in _NAME_EXCLUDE):
                            continue
                        picks_owned[aid] += 1
                        if aid not in picks_names:
                            picks_names[aid] = gname
                except Exception:
                    continue

            # Seed tags for untagged picks candidates (max 20 per request)
            all_pick_aids = list(picks_owned.keys())
            with get_db_session() as db:
                if all_pick_aids:
                    tagged_rows = db.execute(
                        text('SELECT DISTINCT app_id FROM web_steam_app_tags WHERE app_id IN :aids'),
                        {'aids': tuple(all_pick_aids)}
                    ).fetchall()
                    already_tagged = {r[0] for r in tagged_rows}
                    for aid in [a for a in all_pick_aids if a not in already_tagged][:20]:
                        _ensure_steam_tags(aid, db, _req)
                adult_rows2 = db.execute(
                    text("""SELECT DISTINCT app_id FROM web_steam_app_tags
                            WHERE tag_name IN ('sexual content','adult only sexual content',
                            'frequent nudity or sexual content','hentai','eroge',
                            'explicit sexual content')""")
                ).fetchall()
                adult_ids.update(r[0] for r in adult_rows2)

            _pool = {
                'owned_counts': dict(owned_counts),
                'hours_totals': dict(hours_totals),
                'game_names': game_names,
                'picks_owned': dict(picks_owned),
                'picks_names': picks_names,
                'adult_ids': list(adult_ids),
                'mp_ids': list(mp_ids),
            }
            _cache.set(_POOL_CACHE_KEY, _pool, 900)

        # Build widgets from pool (always fresh shuffle for Community Picks)
        owned_counts = Counter(_pool['owned_counts'])
        hours_totals = Counter(_pool['hours_totals'])
        game_names = _pool['game_names']
        picks_owned = Counter(_pool['picks_owned'])
        picks_names = _pool['picks_names']
        adult_ids = set(_pool['adult_ids'])
        mp_ids = set(_pool['mp_ids'])

        if owned_counts:
            top_aids = [aid for aid, _ in hours_totals.most_common(5) if game_names.get(aid)]
            top_owned_games = [
                {
                    'app_id': aid,
                    'name': game_names[aid],
                    'count': owned_counts[aid],
                    'hours': round(hours_totals[aid] / 60, 1),
                    'cover_url': _steam_cover_url(aid),
                    'steam_url': f'https://store.steampowered.com/app/{aid}/',
                    'is_mp': aid in mp_ids,
                }
                for aid in top_aids
            ]

            # Community Picks: fresh random shuffle every request from the full owned pool
            exclude = set(top_aids)
            pool = [aid for aid in picks_owned
                    if aid not in exclude and aid not in adult_ids and picks_names.get(aid)]
            _rng.shuffle(pool)
            community_picks = [
                {
                    'app_id': aid,
                    'name': picks_names[aid],
                    'owners': picks_owned[aid],
                    'cover_url': _steam_cover_url(aid),
                    'steam_url': f'https://store.steampowered.com/app/{aid}/',
                    'is_mp': aid in mp_ids,
                }
                for aid in pool[:5]
                if picks_names.get(aid)
            ]
    except Exception as e:
        logger.error('discover steam widgets error: %s', e)

    context = {
        'web_user': request.web_user,
        'active_page': 'discover',
        'live_streamers': live_streamers,
        'recently_streamed': recently_streamed,
        'lfg_groups': lfg_groups,
        'active_games': active_games,
        'featured_communities': featured_communities,
        'community_counts': community_counts,
        'groups_last_hour': groups_last_hour,
        'game_servers': game_servers,
        'top_owned_games': top_owned_games,
        'community_picks': community_picks,
    }
    return render(request, 'questlog_web/discover.html', context)


@add_web_user_context
def community_guidelines(request):
    """QuestLog Network community guidelines page."""
    return render(request, 'questlog_web/community_guidelines.html', {
        'web_user': request.web_user,
        'active_page': 'community_guidelines',
    })


# =============================================================================
# DISCOVERY VIEW
# =============================================================================

@add_web_user_context
def discover(request):
    """Discovery homepage - Communities + LFG groups + Streamers + Game servers."""
    import random as _random
    import asyncio
    now = int(time.time())
    hour_ago = now - 3600

    live_streamers = []
    lfg_groups = []
    active_games = []
    featured_communities = []
    game_servers = []
    community_counts = {}  # platform -> count of approved communities
    groups_last_hour = 0

    recently_streamed = []
    try:
        from .models import WebUser, WebCreatorProfile, WebCommunity
        from sqlalchemy import func
        _STABLE_CDN = ('https://static-cdn.jtvnw.net/', 'https://yt3.', 'https://yt3.ggpht.')
        def _valid_avatar(a):
            if not a: return None
            if a.startswith('/media/'): return a
            if any(a.startswith(cdn) for cdn in _STABLE_CDN): return a
            return None
        thirty_days_ago = now - (30 * 86400)
        with get_db_session() as db:
            # --- Live streamers (max 4) and recently streamed (max 4) ---
            creator_rows = db.query(WebCreatorProfile, WebUser).join(
                WebUser, WebUser.id == WebCreatorProfile.user_id
            ).filter(
                WebCreatorProfile.allow_discovery == True,
                WebUser.is_banned == False,
            ).order_by(
                WebUser.is_live.desc(),
                WebCreatorProfile.is_current_cotm.desc(),
                WebCreatorProfile.is_current_cotw.desc(),
                WebCreatorProfile.follower_count.desc(),
            ).limit(20).all()

            for cp, u in creator_rows:
                # All connected platforms (used for LIVE display - show all active streams)
                all_platforms = []
                if cp.twitch_url:
                    all_platforms.append({'platform': 'twitch', 'url': cp.twitch_url})
                if cp.youtube_url:
                    all_platforms.append({'platform': 'youtube', 'url': cp.youtube_url})
                if cp.kick_url:
                    all_platforms.append({'platform': 'kick', 'url': cp.kick_url})

                # For "Previously Live": only the platform actually detected live last session
                last_platform = cp.latest_stream_platform if cp.latest_stream_platform else None
                url_map = {'twitch': cp.twitch_url, 'youtube': cp.youtube_url, 'kick': cp.kick_url}
                prev_platforms = [{'platform': last_platform, 'url': url_map.get(last_platform)}] if last_platform and url_map.get(last_platform) else []

                # Primary platform = first connected (for backwards compat)
                platform = all_platforms[0]['platform'] if all_platforms else None
                stream_url = all_platforms[0]['url'] if all_platforms else None

                resolved_avatar = _valid_avatar(cp.avatar_url) or _valid_avatar(u.avatar_url)
                base_entry = {
                    'username': u.username,
                    'display_name': cp.display_name or u.username,
                    'avatar_url': resolved_avatar,
                    'is_cotm': bool(cp.is_current_cotm),
                    'is_cotw': bool(cp.is_current_cotw),
                    'current_game': u.current_game or '',
                    'platform': platform,
                    'stream_url': stream_url,
                    'follower_count': cp.follower_count or 0,
                }

                if u.is_live and len(live_streamers) < 4:
                    live_streamers.append({**base_entry, 'platforms': all_platforms})
                elif not u.is_live and platform and len(recently_streamed) < 4:
                    # Only show in "Recently Streamed" if they have a stream platform
                    # and have an actual stream history within the last 30 days
                    last_streamed = getattr(cp, 'latest_stream_ended_at', None) or 0
                    if last_streamed >= thirty_days_ago:
                        recently_streamed.append({**base_entry, 'platforms': prev_platforms})

            # --- LFG groups (6 most recent open groups) with urgency tags ---
            groups = db.query(WebLFGGroup).filter(
                WebLFGGroup.status == 'open',
            ).order_by(WebLFGGroup.created_at.desc()).limit(6).all()

            for g in groups:
                slots_left = (g.group_size or 4) - (g.current_size or 1)
                fill_pct = (g.current_size or 1) / (g.group_size or 4)
                if slots_left == 0:
                    urgency = 'full'
                elif fill_pct >= 0.75:
                    urgency = 'almost_full'
                elif g.created_at and g.created_at >= hour_ago:
                    urgency = 'new'
                else:
                    urgency = 'recruiting'
                lfg_groups.append({
                    'id': g.id,
                    'share_token': g.share_token,
                    'title': g.title,
                    'game_name': g.game_name,
                    'game_image_url': g.game_image_url,
                    'current_size': g.current_size,
                    'group_size': g.group_size,
                    'slots_left': slots_left,
                    'status': g.status,
                    'created_at': g.created_at,
                    'urgency': urgency,
                })

            # --- Groups active in last hour (for section header badge) ---
            groups_last_hour = db.query(WebLFGGroup).filter(
                WebLFGGroup.status == 'open',
                WebLFGGroup.created_at >= hour_ago,
            ).count()

            # --- Active games: aggregate groups by game_name ---
            game_counts = db.query(
                WebLFGGroup.game_name,
                WebLFGGroup.game_image_url,
                func.count(WebLFGGroup.id).label('group_count'),
            ).filter(
                WebLFGGroup.status == 'open',
            ).group_by(
                WebLFGGroup.game_name, WebLFGGroup.game_image_url
            ).order_by(func.count(WebLFGGroup.id).desc()).limit(6).all()

            live_by_game = {}
            for s in live_streamers:
                if s['is_live'] and s['current_game']:
                    key = s['current_game'].lower()
                    live_by_game[key] = live_by_game.get(key, 0) + 1

            for row in game_counts:
                live_count = live_by_game.get((row.game_name or '').lower(), 0)
                active_games.append({
                    'game_name': row.game_name,
                    'game_image_url': row.game_image_url,
                    'group_count': row.group_count,
                    'live_count': live_count,
                })

            # --- Communities (up to 6 random approved, shown in 2-col grid) ---
            # Order: primary first so dedup keeps the right one per owner
            all_communities = db.query(WebCommunity).filter(
                WebCommunity.network_status == 'approved',
            ).order_by(WebCommunity.is_primary.desc()).all()

            # Fetch live member counts from platform-specific tables for Fluxer communities
            fluxer_ids = [
                c.platform_id for c in all_communities
                if c.platform and c.platform.value == 'fluxer' and c.platform_id
            ]
            fluxer_member_counts = {}
            if fluxer_ids:
                placeholders = ','.join([':fid' + str(i) for i in range(len(fluxer_ids))])
                params = {'fid' + str(i): v for i, v in enumerate(fluxer_ids)}
                rows = db.execute(
                    text(f"SELECT guild_id, member_count FROM web_fluxer_guild_settings WHERE guild_id IN ({placeholders})"),
                    params,
                ).fetchall()
                fluxer_member_counts = {r[0]: r[1] for r in rows}

            # Deduplicate by owner - one card per owner, preferring is_primary=True
            seen_owners = set()
            serialized_communities = []
            for c in all_communities:
                if c.owner_id and c.owner_id in seen_owners:
                    continue
                seen_owners.add(c.owner_id)
                plat = c.platform.value if c.platform else 'discord'
                community_counts[plat] = community_counts.get(plat, 0) + 1
                # Use live count from bot settings table when available, fall back to stored value
                if plat == 'fluxer' and c.platform_id and c.platform_id in fluxer_member_counts:
                    live_count = fluxer_member_counts[c.platform_id] or c.member_count or 0
                else:
                    live_count = c.member_count or 0
                import re as _re
                c_slug = _re.sub(r'[^a-z0-9]+', '-', c.name.lower()).strip('-')
                serialized_communities.append({
                    'id': c.id,
                    'slug': c_slug,
                    'name': c.name,
                    'description': c.description or '',
                    'avatar_url': c.icon_url or '',
                    'platform': plat,
                    'member_count': live_count,
                })

            featured_communities = _random.sample(
                serialized_communities, min(6, len(serialized_communities))
            )

    except Exception as e:
        logger.error('discover view error: %s', e)

    # Game server strip is loaded client-side via JS after page load to avoid blocking LCP

    # --- Community Steam widgets ---
    # Raw pool data (expensive Steam API calls) cached 15 min - shared across workers.
    # Community Picks shuffle is re-run every request from the cached pool so it's
    # always random. Most Played is deterministic so it comes straight from cache.
    top_owned_games = []
    community_picks = []
    _POOL_CACHE_KEY = 'discover_steam_pool_v2'
    try:
        import random as _rng
        from collections import Counter
        import requests as _req
        from django.core.cache import cache as _cache
        from .models import WebUser as _WebUser
        from .helpers import STEAM_API_KEY as _STEAM_KEY
        from .helpers import get_steam_cover_url as _steam_cover_url

        _SEXUAL_DESCRIPTOR_IDS = {1, 3, 4}
        _NAME_EXCLUDE = ('test server', 'beta server', 'dedicated server', ' pts', 'public test', 'demo')

        def _ensure_steam_tags(aid, db, _req):
            existing = db.execute(
                text('SELECT COUNT(*) FROM web_steam_app_tags WHERE app_id = :a'),
                {'a': aid}
            ).scalar()
            if existing:
                return
            tags = set()
            try:
                r = _req.get(
                    f'https://store.steampowered.com/api/appdetails?appids={aid}&filters=content_descriptors,categories,genres',
                    timeout=4,
                )
                data = (r.json() or {}).get(str(aid), {}).get('data', {})
                descriptor_ids = set(data.get('content_descriptors', {}).get('ids') or [])
                if descriptor_ids & _SEXUAL_DESCRIPTOR_IDS:
                    tags.add('sexual content')
                for c in data.get('categories', []):
                    tags.add(c.get('description', '').lower())
                for g in data.get('genres', []):
                    tags.add(g.get('description', '').lower())
            except Exception:
                pass
            try:
                r = _req.get(
                    f'https://steamspy.com/api.php?request=appdetails&appid={aid}',
                    timeout=5,
                )
                for tag in ((r.json() or {}).get('tags') or {}).keys():
                    tags.add(tag.lower())
            except Exception:
                pass
            if not tags:
                tags.add('untagged')
            db.execute(
                text('INSERT IGNORE INTO web_steam_app_tags (app_id, tag_name) VALUES ' +
                     ', '.join(f"({aid}, :t{i})" for i, _ in enumerate(tags))),
                {f't{i}': t for i, t in enumerate(tags)}
            )
            db.commit()

        # Try to load the cached pool (raw counters + names + adult_ids)
        _pool = _cache.get(_POOL_CACHE_KEY)

        if _pool is None:
            # Cache miss - fetch from Steam APIs and store the raw pool
            with get_db_session() as db:
                steam_users = db.query(_WebUser.steam_id).filter(
                    _WebUser.share_steam_library == True,
                    _WebUser.steam_id.isnot(None),
                    _WebUser.steam_id != '',
                    _WebUser.is_banned == False,
                    _WebUser.is_disabled == False,
                    _WebUser.is_hidden == False,
                ).limit(50).all()
                adult_rows = db.execute(
                    text("""SELECT DISTINCT app_id FROM web_steam_app_tags
                            WHERE tag_name IN ('sexual content','adult only sexual content',
                            'frequent nudity or sexual content','hentai','eroge',
                            'explicit sexual content')""")
                ).fetchall()
                adult_ids = {r[0] for r in adult_rows}
                mp_rows = db.execute(
                    text("SELECT DISTINCT app_id FROM web_steam_app_tags WHERE tag_name IN ('multiplayer','co-op','online co-op','multi-player')")
                ).fetchall()
                mp_ids = {r[0] for r in mp_rows}

            owned_counts = Counter()
            hours_totals = Counter()
            game_names = {}
            for (steam_id,) in steam_users:
                try:
                    resp = _req.get(
                        'https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/',
                        params={'key': _STEAM_KEY, 'steamid': steam_id, 'count': 0},
                        timeout=4,
                    )
                    for g in resp.json().get('response', {}).get('games', []):
                        aid = g.get('appid')
                        gname = g.get('name', '')
                        if not aid or aid in adult_ids:
                            continue
                        if any(x in gname.lower() for x in _NAME_EXCLUDE):
                            continue
                        owned_counts[aid] += 1
                        hours_totals[aid] += g.get('playtime_2weeks', 0)
                        if aid not in game_names:
                            game_names[aid] = gname
                except Exception:
                    continue

            picks_owned = Counter()
            picks_names = {}
            for (steam_id,) in steam_users:
                try:
                    resp2 = _req.get(
                        'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/',
                        params={'key': _STEAM_KEY, 'steamid': steam_id,
                                'include_appinfo': 1, 'include_played_free_games': 1},
                        timeout=4,
                    )
                    for g in resp2.json().get('response', {}).get('games', []):
                        aid = g.get('appid')
                        gname = g.get('name', '')
                        if not aid or aid in adult_ids or not gname:
                            continue
                        if any(x in gname.lower() for x in _NAME_EXCLUDE):
                            continue
                        picks_owned[aid] += 1
                        if aid not in picks_names:
                            picks_names[aid] = gname
                except Exception:
                    continue

            # Seed tags for untagged picks candidates (max 20 per request)
            all_pick_aids = list(picks_owned.keys())
            with get_db_session() as db:
                if all_pick_aids:
                    tagged_rows = db.execute(
                        text('SELECT DISTINCT app_id FROM web_steam_app_tags WHERE app_id IN :aids'),
                        {'aids': tuple(all_pick_aids)}
                    ).fetchall()
                    already_tagged = {r[0] for r in tagged_rows}
                    for aid in [a for a in all_pick_aids if a not in already_tagged][:20]:
                        _ensure_steam_tags(aid, db, _req)
                adult_rows2 = db.execute(
                    text("""SELECT DISTINCT app_id FROM web_steam_app_tags
                            WHERE tag_name IN ('sexual content','adult only sexual content',
                            'frequent nudity or sexual content','hentai','eroge',
                            'explicit sexual content')""")
                ).fetchall()
                adult_ids.update(r[0] for r in adult_rows2)

            _pool = {
                'owned_counts': dict(owned_counts),
                'hours_totals': dict(hours_totals),
                'game_names': game_names,
                'picks_owned': dict(picks_owned),
                'picks_names': picks_names,
                'adult_ids': list(adult_ids),
                'mp_ids': list(mp_ids),
            }
            _cache.set(_POOL_CACHE_KEY, _pool, 900)

        # Build widgets from pool (always fresh shuffle for Community Picks)
        owned_counts = Counter(_pool['owned_counts'])
        hours_totals = Counter(_pool['hours_totals'])
        game_names = _pool['game_names']
        picks_owned = Counter(_pool['picks_owned'])
        picks_names = _pool['picks_names']
        adult_ids = set(_pool['adult_ids'])
        mp_ids = set(_pool['mp_ids'])

        if owned_counts:
            top_aids = [aid for aid, _ in hours_totals.most_common(5) if game_names.get(aid)]
            top_owned_games = [
                {
                    'app_id': aid,
                    'name': game_names[aid],
                    'count': owned_counts[aid],
                    'hours': round(hours_totals[aid] / 60, 1),
                    'cover_url': _steam_cover_url(aid),
                    'steam_url': f'https://store.steampowered.com/app/{aid}/',
                    'is_mp': aid in mp_ids,
                }
                for aid in top_aids
            ]

            # Community Picks: fresh random shuffle every request from the full owned pool
            exclude = set(top_aids)
            pool = [aid for aid in picks_owned
                    if aid not in exclude and aid not in adult_ids and picks_names.get(aid)]
            _rng.shuffle(pool)
            community_picks = [
                {
                    'app_id': aid,
                    'name': picks_names[aid],
                    'owners': picks_owned[aid],
                    'cover_url': _steam_cover_url(aid),
                    'steam_url': f'https://store.steampowered.com/app/{aid}/',
                    'is_mp': aid in mp_ids,
                }
                for aid in pool[:5]
                if picks_names.get(aid)
            ]
    except Exception as e:
        logger.error('discover steam widgets error: %s', e)

    context = {
        'web_user': request.web_user,
        'active_page': 'discover',
        'live_streamers': live_streamers,
        'recently_streamed': recently_streamed,
        'lfg_groups': lfg_groups,
        'active_games': active_games,
        'featured_communities': featured_communities,
        'community_counts': community_counts,
        'groups_last_hour': groups_last_hour,
        'game_servers': game_servers,
        'top_owned_games': top_owned_games,
        'community_picks': community_picks,
    }
    return render(request, 'questlog_web/discover.html', context)


# =============================================================================
# LFG VIEWS
# =============================================================================

@add_web_user_context
def lfg_browse(request):
    """Browse LFG groups."""
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_browse',
    }
    return render(request, 'questlog_web/lfg_browse.html', context)


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

        lfg_events = [
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
                'type': 'lfg',
            }
            for g in groups
        ]

        # Community Game Nights - public communities with upcoming events
        from .models import WebCommunityEvent
        game_nights = db.query(WebCommunityEvent).filter(
            WebCommunityEvent.is_cancelled == False,
            WebCommunityEvent.starts_at >= cutoff,
        ).order_by(WebCommunityEvent.starts_at).limit(200).all()

        community_ids = list({e.community_id for e in game_nights})
        community_map = {}
        if community_ids:
            from .models import WebCommunity
            communities = db.query(WebCommunity).filter(
                WebCommunity.id.in_(community_ids),
                WebCommunity.is_active == True,
                WebCommunity.is_banned == False,
                WebCommunity.allow_discovery == True,
            ).all()
            community_map = {c.id: c for c in communities}

        # Fetch user's RSVPs for all game nights (if logged in)
        user_id = request.web_user.id if request.web_user else None
        gn_rsvp_map = {}
        if user_id and game_nights:
            from .models import WebCommunityEventRSVP
            gn_ids = [e.id for e in game_nights if e.community_id in community_map]
            if gn_ids:
                rsvp_rows = db.query(WebCommunityEventRSVP).filter(
                    WebCommunityEventRSVP.user_id == user_id,
                    WebCommunityEventRSVP.event_id.in_(gn_ids),
                ).all()
                gn_rsvp_map = {r.event_id: r.status for r in rsvp_rows}

        game_night_events = [
            {
                'id': 'gn-' + str(e.id),
                'title': e.title,
                'game_name': e.game_tag_name or '',
                'ts': e.starts_at,
                'status': 'open',
                'current_size': e.rsvp_going,
                'max_size': e.max_attendees or 0,
                'recurrence': e.recurrence or 'none',
                'guild_id': None,
                'guild_name': community_map[e.community_id].name if e.community_id in community_map else '',
                'community_name': community_map[e.community_id].name if e.community_id in community_map else '',
                'community_id': e.community_id,
                'community_slug': _community_slug(community_map[e.community_id].name) if e.community_id in community_map else '',
                'description': e.description or '',
                'type': 'game_night',
                'rsvp_going': e.rsvp_going,
                'duration_mins': e.duration_mins,
                'rsvp_maybe': e.rsvp_maybe,
                'my_rsvp': gn_rsvp_map.get(e.id),
            }
            for e in game_nights
            if e.community_id in community_map
        ]

        # Web-native LFG groups (QuestLog web, scheduled)
        web_lfg_groups = db.query(WebLFGGroup).filter(
            WebLFGGroup.scheduled_time.isnot(None),
            WebLFGGroup.scheduled_time >= cutoff,
            WebLFGGroup.status.in_(['open', 'full']),
            WebLFGGroup.allow_network_discovery == True,
        ).order_by(WebLFGGroup.scheduled_time).limit(200).all()

        web_lfg_events = [
            {
                'id': g.id,
                'share_token': g.share_token or '',
                'share_url': f'/ql/lfg/{g.share_token}/' if g.share_token else f'/ql/lfg/{g.id}/',
                'title': g.title,
                'game_name': g.game_name or '',
                'ts': g.scheduled_time,
                'status': g.status,
                'current_size': g.current_size,
                'max_size': g.group_size,
                'recurrence': 'none',
                'guild_id': None,
                'guild_name': g.origin_guild_name or '',
                'description': g.description or '',
                'type': 'lfg',
                'source': 'web',
                'creator_id': g.creator_id,
            }
            for g in web_lfg_groups
        ]

        events = lfg_events + web_lfg_events + game_night_events

    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_calendar',
        'events_json': json.dumps(events),
    }
    return render(request, 'questlog_web/lfg_calendar.html', context)


def _community_slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


@web_login_required
@add_web_user_context
def lfg_create(request):
    """Create LFG group."""
    import json as _json
    from .models import WebUserGame
    profile_games = []
    if request.web_user:
        with get_db_session() as db:
            lib_games = (
                db.query(WebUserGame)
                .filter(
                    WebUserGame.web_user_id == request.web_user.id,
                    WebUserGame.status == 'play_together',
                )
                .order_by(WebUserGame.updated_at.desc())
                .limit(10)
                .all()
            )
            for g in lib_games:
                profile_games.append({
                    'name': g.name,
                    'igdb_id': g.igdb_id,
                    'cover_url': g.cover_url or '',
                    'status': g.status,
                })
    context = {
        'web_user': request.web_user,
        'active_page': 'lfg_create',
        'profile_games_json': _json.dumps(profile_games),
        'profile_games': profile_games,
        'prefill_game': request.GET.get('game', '').strip()[:200],
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


@web_verified_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='10/h', block=True)
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
                raw_sel = {k: sanitize_text(str(v) if not isinstance(v, str) else v) for k, v in raw_sel.items() if isinstance(k, str)}
            existing.selections = json.dumps(raw_sel) if raw_sel else None
            existing.joined_at = now
        else:
            raw_sel = data.get('selections') or {}
            if isinstance(raw_sel, dict):
                raw_sel = {k: sanitize_text(str(v) if not isinstance(v, str) else v) for k, v in raw_sel.items() if isinstance(k, str)}
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

    # Award legacy to group creator when group fills
    if is_now_full and group_creator_id:
        try:
            from .helpers import award_legacy
            award_legacy(group_creator_id, 'lfg_group_filled', source='web', ref_id=f"lfg_fill_{web_group_id}")
        except Exception as e:
            logger.warning(f"[LFG] Failed to award legacy for fill on group {web_group_id}: {e}")

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

    lfg_url = f"https://questlog.casual-heroes.com/lfg/{web_group_token}/"

    return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='20/h', method='POST', block=True)
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
@ratelimit(key='ip', rate='30/h', method='POST', block=True)
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
        if isinstance(raw_sel, dict):
            raw_sel = {k: sanitize_text(str(v) if not isinstance(v, str) else v) for k, v in raw_sel.items() if isinstance(k, str)}
        member.selections = json.dumps(raw_sel) if raw_sel else None
        db.commit()

    return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='20/h', method='POST', block=True)
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
        is_site_admin = bool(getattr(request.web_user, 'is_admin', False) or getattr(request.web_user, 'is_mod', False))
        if group.creator_id != request.web_user.id and not is_site_admin:
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
@ratelimit(key='ip', rate='10/h', method='POST', block=True)
def lfg_delete(request, group_id):
    """Cancel an active group, or permanently delete an already-cancelled group."""
    now = int(time.time())
    with get_db_session() as db:
        group = db.query(WebLFGGroup).filter_by(id=group_id).first()
        if not group:
            return JsonResponse({'error': 'Group not found'}, status=404)
        is_site_admin = bool(getattr(request.web_user, 'is_admin', False) or getattr(request.web_user, 'is_mod', False))
        if group.creator_id != request.web_user.id and not is_site_admin:
            return JsonResponse({'error': 'Only the group creator can delete it'}, status=403)

        already_cancelled = group.status == 'cancelled'
        ran = group.status == 'full' or (group.current_size or 1) > 1
        creator_id = group.creator_id

        if already_cancelled:
            # Hard delete - remove members then the group (posts cascade via FK)
            db.query(WebLFGMember).filter_by(group_id=group_id).delete()
            db.delete(group)
            db.commit()
            return JsonResponse({'success': True, 'deleted': True})

        group.status = 'cancelled'
        group.updated_at = now
        db.commit()

    # Award legacy if group actually ran
    if ran and creator_id:
        try:
            from .helpers import award_legacy
            award_legacy(creator_id, 'lfg_completed', source='web', ref_id=f"lfg_done_{group_id}")
        except Exception as e:
            logger.warning(f"[LFG] Failed to award legacy for completion on group {group_id}: {e}")

    return JsonResponse({'success': True, 'deleted': False})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='20/h', method='POST', block=True)
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
@ratelimit(key='ip', rate='30/h', method='POST', block=True)
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
            "WHERE wu.is_banned = 0 AND wu.is_disabled = 0 AND wu.is_hidden = 0 "
            "AND wu.email_verified = 1 AND wu.web_xp > 0 "
            "AND wu.id NOT IN :excl "
            "ORDER BY wu.web_xp DESC "
            "LIMIT :limit OFFSET :offset"
        ), {'limit': per_page, 'offset': offset, 'excl': tuple(EXCLUDED_USER_IDS) or (0,)}).fetchall()

        total = db.execute(text(
            "SELECT COUNT(*) FROM web_users "
            "WHERE is_banned=0 AND is_disabled=0 AND is_hidden=0 AND email_verified=1 AND web_xp > 0 "
            "AND id NOT IN :excl"
        ), {'excl': tuple(EXCLUDED_USER_IDS) or (0,)}).scalar() or 0

        if request.web_user and getattr(request.web_user, 'id', None) not in EXCLUDED_USER_IDS:
            my_rank = db.execute(text(
                "SELECT COUNT(*) + 1 FROM web_users "
                "WHERE web_xp > :xp AND is_banned=0 AND is_disabled=0 AND email_verified=1 "
                "AND id NOT IN :excl"
            ), {'xp': request.web_user.web_xp or 0, 'excl': tuple(EXCLUDED_USER_IDS) or (0,)}).scalar()

        # Top 3 communities: one entry per owner (their highest-XP primary community).
        community_rows = db.execute(text("""
            SELECT id, name, icon_url, platform, active_members,
                   total_xp, total_messages, total_media, total_voice_mins, total_reactions
            FROM (
                SELECT wc.id, wc.name, wc.icon_url, wc.platform, wc.owner_id,
                       COALESCE(fgs.member_count, dc.member_count, 0) AS active_members,
                       COALESCE(fx.total_xp, dc.total_xp, 0) AS total_xp,
                       COALESCE(fx.total_messages, dc.total_messages, 0) AS total_messages,
                       COALESCE(fx.total_media, dc.total_media, 0) AS total_media,
                       COALESCE(fx.total_voice_mins, dc.total_voice_mins, 0) AS total_voice_mins,
                       COALESCE(fx.total_reactions, dc.total_reactions, 0) AS total_reactions,
                       ROW_NUMBER() OVER (PARTITION BY wc.owner_id ORDER BY COALESCE(fx.total_xp, dc.total_xp, 0) DESC) AS rn
                FROM web_communities wc
                LEFT JOIN web_fluxer_guild_settings fgs
                       ON fgs.guild_id = wc.platform_id AND wc.platform = 'fluxer'
                LEFT JOIN (
                    SELECT guild_id,
                           SUM(xp) AS total_xp,
                           SUM(message_count) AS total_messages,
                           SUM(media_count) AS total_media,
                           SUM(voice_minutes) AS total_voice_mins,
                           SUM(reaction_count) AS total_reactions
                    FROM fluxer_member_xp
                    GROUP BY guild_id
                ) fx ON fx.guild_id = CAST(wc.platform_id AS UNSIGNED) AND wc.platform = 'fluxer'
                LEFT JOIN (
                    SELECT gm.guild_id,
                           COALESCE(g.member_count, COUNT(DISTINCT gm.user_id)) AS member_count,
                           SUM(gm.xp) AS total_xp,
                           SUM(gm.message_count) AS total_messages,
                           SUM(gm.media_count) AS total_media,
                           SUM(gm.voice_minutes) AS total_voice_mins,
                           SUM(gm.reaction_count) AS total_reactions
                    FROM guild_members gm
                    LEFT JOIN guilds g ON g.guild_id = gm.guild_id
                    GROUP BY gm.guild_id
                ) dc ON dc.guild_id = CAST(wc.platform_id AS UNSIGNED) AND wc.platform = 'discord'
                WHERE wc.network_status='approved' AND wc.is_active=1 AND wc.is_primary=1
                  AND COALESCE(fx.total_xp, dc.total_xp, 0) > 0
            ) ranked
            WHERE rn = 1
            ORDER BY total_xp DESC LIMIT 3
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
            "WHERE wu.is_banned=0 AND wu.is_disabled=0 AND wu.is_hidden=0 AND wu.email_verified=1 AND wu.web_xp > 0 "
            "AND wu.id NOT IN :excl "
            "ORDER BY wu.web_xp DESC LIMIT :lim"
        ), {'lim': limit, 'excl': tuple(EXCLUDED_USER_IDS) or (0,)}).fetchall()
    return JsonResponse({'entries': [
        {'rank': i + 1, 'username': r[1], 'avatar_url': r[2] or '', 'xp': r[3], 'level': r[4]}
        for i, r in enumerate(rows)
    ]})


@add_web_user_context
def games(request):
    """Found Games / Game Discovery."""
    context = {
        'web_user': request.web_user,
        'active_page': 'games',
    }
    return render(request, 'questlog_web/games.html', context)


@add_web_user_context
def creators(request):
    """Featured Creators."""
    context = {
        'web_user': request.web_user,
        'active_page': 'creators',
    }
    return render(request, 'questlog_web/creators.html', context)


def creator_profile(request, username):
    """Redirect creators/<username>/ -> u/<username>/ - single unified profile page."""
    from django.shortcuts import redirect
    return redirect(f'u/{username}/', permanent=True)


@add_web_user_context
def gamers(request):
    """Gamers directory - searchable list of QuestLog members."""
    context = {
        'web_user': request.web_user,
        'active_page': 'gamers',
        'prefill_game': request.GET.get('game', '').strip()[:200],
    }
    return render(request, 'questlog_web/gamers.html', context)


@add_web_user_context
def gamers(request):
    """Gamers directory - searchable list of QuestLog members."""
    context = {
        'web_user': request.web_user,
        'active_page': 'gamers',
        'prefill_game': request.GET.get('game', '').strip()[:200],
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

    # --- Discord guilds owned by this user (live from Discord API via stored OAuth token) ---
    discord_guilds_data = []
    registered_discord_ids = set()
    discord_id = str(getattr(request.web_user, 'discord_id', '') or '')

    if discord_id:
        enc_token = getattr(request.web_user, 'discord_access_token_enc', None)
        if enc_token:
            try:
                import requests as _req
                from app.utils.encryption import decrypt_token as _dec
                access_token = _dec(enc_token)
                MANAGE_GUILD = 0x20
                resp = _req.get(
                    'https://discord.com/api/v10/users/@me/guilds',
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10,
                )
                if resp.status_code == 200:
                    all_guilds = resp.json()
                    discord_guilds_data = [
                        {
                            'id': g['id'],
                            'name': g['name'],
                            'member_count': 0,
                            'icon': (
                                f"https://cdn.discordapp.com/icons/{g['id']}/{g['icon']}.png"
                                if g.get('icon') else None
                            ),
                        }
                        for g in all_guilds
                        if (int(g.get('permissions', 0)) & MANAGE_GUILD) or g.get('owner')
                    ]
            except Exception:
                pass

        if discord_guilds_data:
            try:
                with get_db_session() as db:
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

    u = request.web_user
    context = {
        'web_user': u,
        'active_page': 'community_register',
        'has_discord': bool(getattr(u, 'discord_id', None)),
        'has_fluxer': bool(getattr(u, 'fluxer_id', None)),
        'has_matrix': bool(getattr(u, 'matrix_id', None)),
        'existing_revolt_url': getattr(u, 'revolt_url', None) or '',
        'existing_root_url': getattr(u, 'root_url', None) or '',
        **status_context,
        **picker_context,
    }
    return render(request, 'questlog_web/community_register.html', context)


@add_web_user_context
def community_detail(request, community_id):
    """Redirect legacy integer community URLs to slug-based URLs."""
    import re as _re
    with get_db_session() as db:
        c = db.query(WebCommunity).filter_by(id=community_id, is_active=True).first()
        if not c:
            from django.http import Http404
            raise Http404
        slug = _re.sub(r'[^a-z0-9]+', '-', c.name.lower()).strip('-')
    return redirect('questlog_web_community_detail_slug', slug=slug)


@add_web_user_context
def community_detail_slug(request, slug):
    """View community details by slug (generated from name)."""
    import re as _re
    with get_db_session() as db:
        # Find the primary community row whose name converts to the requested slug
        all_communities = db.query(WebCommunity).filter_by(is_active=True, is_primary=True).all()
        community = None
        for c in all_communities:
            c_slug = _re.sub(r'[^a-z0-9]+', '-', c.name.lower()).strip('-')
            if c_slug == slug:
                community = c
                break
        # Fallback: if no primary match, try any active row (handles communities with no is_primary set)
        if not community:
            all_communities = db.query(WebCommunity).filter_by(is_active=True).all()
            for c in all_communities:
                c_slug = _re.sub(r'[^a-z0-9]+', '-', c.name.lower()).strip('-')
                if c_slug == slug:
                    community = c
                    break
    if not community:
        from django.http import Http404
        raise Http404
    context = {
        'web_user': request.web_user,
        'active_page': 'communities',
        'community_id': community.id,
        'community_slug': slug,
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
    library_games_list = []
    ffxiv_char = None
    ffxiv_rewards = []
    steam_ach_events = []
    with get_db_session() as db:
        from .models import WebUserGame as _WebUserGame, WebFfxivCharacter as _WebFfxivChar, WebFfxivAchievementReward as _WebFfxivReward, WebXpEvent as _WebXpEvent, WebIndieGame as _WebIndieGame
        from sqlalchemy import case as _sa_case2
        _lib_order = _sa_case2(
            (_WebUserGame.status == 'play_together', 0),
            (_WebUserGame.status == 'playing', 1),
            else_=2,
        )
        import json as _json2
        _SOCIAL_MODES = {'multiplayer', 'co-operative', 'mmo', 'battle royale', 'massively multiplayer online (mmo)'}
        lib_rows = (
            db.query(_WebUserGame)
            .filter(_WebUserGame.web_user_id == wu.id)
            .order_by(_lib_order, _WebUserGame.updated_at.desc())
            .limit(50)
            .all()
        )
        for g in lib_rows:
            if len(library_games_list) >= 10:
                break
            # Filter out solo-only games: skip if game_modes is known and has no social modes
            if g.game_modes:
                try:
                    modes = [m.lower() for m in _json2.loads(g.game_modes)]
                    if modes and not any(m in _SOCIAL_MODES for m in modes):
                        continue
                except (ValueError, TypeError):
                    pass
            library_games_list.append({
                'name': g.name,
                'igdb_id': g.igdb_id,
                'cover_url': g.cover_url or '',
                'status': g.status,
            })
        # FFXIV achievements
        if wu.track_achievements:
            _fc = db.query(_WebFfxivChar).filter_by(user_id=wu.id, is_primary=True, sync_status='ok').first()
            if _fc:
                ffxiv_char = {
                    'character_name': _fc.character_name,
                    'world': _fc.world,
                    'datacenter': _fc.datacenter,
                    'avatar_url': _fc.avatar_url or '',
                    'active_job': _fc.active_job or '',
                }
                for r in db.query(_WebFfxivReward).filter_by(user_id=wu.id).order_by(_WebFfxivReward.awarded_at.desc()).limit(50).all():
                    ffxiv_rewards.append({
                        'name': r.achievement_name,
                        'xp': r.xp_awarded,
                        'legacy': r.legacy_awarded,
                        'awarded_at': r.awarded_at,
                    })
        # Steam achievement XP stats
        _day_start = int(time.time()) - 86400
        _steam_row = db.execute(
            text("SELECT COUNT(*), MIN(created_at), MAX(created_at) FROM web_xp_events WHERE user_id=:uid AND action_type='steam_achievement'"),
            {'uid': wu.id}
        ).fetchone()
        _xp_today_row = db.execute(
            text("SELECT LEAST(SUM(xp), 50) FROM web_xp_events WHERE user_id=:uid AND action_type='steam_achievement' AND created_at >= :day_start"),
            {'uid': wu.id, 'day_start': _day_start}
        ).fetchone()
        if _steam_row and _steam_row[0]:
            steam_ach_events = [{
                'count': int(_steam_row[0]),
                'xp_today': int(_xp_today_row[0] or 0) if _xp_today_row else 0,
                'first_at': int(_steam_row[1] or 0),
                'last_at': int(_steam_row[2] or 0),
            }]
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
        indie_games_raw = db.query(_WebIndieGame).filter(
            _WebIndieGame.dev_user_id == wu.id,
            _WebIndieGame.is_published == True,
        ).order_by(_WebIndieGame.created_at.desc()).all()
        indie_games = [
            {
                'name': g.name, 'slug': g.slug, 'cover_url': g.cover_url or '',
                'dev_bio': g.dev_bio or '', 'dev_devlog': g.dev_devlog or '',
                'status': g.status or '',
                'dev_website': g.dev_website or '', 'dev_twitter': g.dev_twitter or '',
                'dev_discord_url': g.dev_discord_url or '', 'dev_fluxer_url': g.dev_fluxer_url or '',
                'dev_itch_url': g.dev_itch_url or '', 'dev_youtube_url': g.dev_youtube_url or '',
                'dev_twitch_url': g.dev_twitch_url or '', 'dev_steam_url': g.dev_steam_url or '',
                'dev_tiktok_url': g.dev_tiktok_url or '', 'dev_instagram_url': g.dev_instagram_url or '',
                'dev_facebook_url': g.dev_facebook_url or '', 'dev_bsky_url': g.dev_bsky_url or '',
                'dev_kick_url': g.dev_kick_url or '',
            }
            for g in indie_games_raw
        ]
        # Also load pending/rejected submissions so dev can track status
        _pending_raw = db.query(_WebIndieGame).filter(
            _WebIndieGame.submitted_by == wu.id,
            _WebIndieGame.submission_status.in_(['pending', 'rejected', 'resubmitted']),
        ).order_by(_WebIndieGame.created_at.desc()).all()
        indie_pending = [
            {
                'name': g.name, 'slug': g.slug,
                'submission_status': g.submission_status,
                'submission_pitch': g.submission_pitch or '',
                'submission_link': g.submission_link or '',
                'submission_note': g.submission_note or '',
            }
            for g in _pending_raw
        ]

    context = {
        'web_user': wu,
        'active_page': 'profile',
        'indie_games': indie_games,
        'indie_pending': indie_pending,
        'gaming_platforms_list': _json.loads(wu.gaming_platforms) if wu.gaming_platforms else [],
        'favorite_genres_list':  _json.loads(wu.favorite_genres)  if wu.favorite_genres  else [],
        'favorite_games_list':   library_games_list,
        'favorite_games_json':   _json.dumps(library_games_list),
        'playstyle_list': (
            _json.loads(wu.playstyle) if wu.playstyle and wu.playstyle.startswith('[')
            else ([wu.playstyle] if wu.playstyle else [])
        ),
        'creator_profile': creator_profile,
        'user_communities': user_communities,
        'playstyle_choices': ['Casual', 'Hardcore', 'Competitive', 'Completionist', 'Explorer', 'Social'],
        'platform_choices': ['PC', 'PS5', 'PS4', 'Xbox Series', 'Xbox One', 'Switch', 'Mobile', 'Steam Deck'],
        'genre_choices': ['RPG', 'FPS', 'MOBA', 'MMO', 'Strategy', 'Simulation', 'Survival', 'Horror', 'Souls-like', 'Platformer', 'Roguelike', 'Sports', 'Racing', 'Fighting', 'Puzzle'],
        'ffxiv_char': ffxiv_char,
        'ffxiv_rewards': ffxiv_rewards,
        'steam_ach_events': steam_ach_events,
        'legacy_tier_names': {1: 'Wanderer', 2: 'Ranger', 3: 'Warden', 4: 'Champion', 5: 'Ascendant'},
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
    return redirect('/profile/#edit')


@add_web_user_context
def getting_started(request):
    """Getting Started guide - how QuestLog works."""
    return render(request, 'questlog_web/getting_started.html', {
        'web_user': request.web_user,
        'active_page': 'getting_started',
    })


@web_login_required
@add_web_user_context
def hero_shop(request):
    """Hero Shop — browse and buy flairs with Hero Points."""
    context = {
        'web_user': request.web_user,
        'active_page': 'shop',
    }
    return render(request, 'questlog_web/shop.html', context)


@add_web_user_context
def game_servers_ql(request):
    """Community-hosted game servers."""
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


@require_http_methods(["GET"])
def api_gameservers_status(request):
    """Return live player counts and status for all game servers (polling endpoint)."""
    import asyncio
    from app.models import SiteActivityGame
    from app.views import fetch_instance_data

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    servers = []
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
            amp_names = [g.amp_instance_id for g in db_games if g.amp_instance_id]
            amp_data_map = {}
            if amp_names:
                results = loop.run_until_complete(asyncio.gather(
                    *(fetch_instance_data(n) for n in amp_names),
                    return_exceptions=True
                ))
                amp_data_map = {r.get('id'): r for r in results if isinstance(r, dict)}

            for db_game in db_games:
                amp = amp_data_map.get(db_game.amp_instance_id)
                servers.append({
                    'id': db_game.game_key,
                    'online': amp.get('online', '-') if amp else '-',
                    'max': amp.get('max', '-') if amp else '-',
                    'status_label': amp.get('status_label', 'Unknown') if amp else 'Unknown',
                })
    except Exception as e:
        logger.error('api_gameservers_status: %s', e)
        return JsonResponse({'error': 'failed'}, status=500)
    finally:
        loop.close()

    return JsonResponse({'servers': servers})


@require_http_methods(["GET"])
def api_gameservers_discover_strip(request):
    """Return only servers with show_on_discover_strip=True for the discover page pill bar."""
    import asyncio
    from app.models import SiteActivityGame
    from app.views import fetch_instance_data

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    servers = []
    try:
        with get_db_session() as db:
            db_games = (
                db.query(SiteActivityGame)
                .filter(
                    SiteActivityGame.is_active == True,
                    SiteActivityGame.show_on_discover_strip == True,
                    SiteActivityGame.game_type.in_(['amp', 'both']),
                )
                .order_by(SiteActivityGame.sort_order)
                .all()
            )
            amp_names = [g.amp_instance_id for g in db_games if g.amp_instance_id]
            amp_data_map = {}
            if amp_names:
                results = loop.run_until_complete(asyncio.gather(
                    *(fetch_instance_data(n) for n in amp_names),
                    return_exceptions=True
                ))
                amp_data_map = {r.get('id'): r for r in results if isinstance(r, dict)}

            for db_game in db_games:
                amp = amp_data_map.get(db_game.amp_instance_id)
                online = amp.get('online', '-') if amp else '-'
                servers.append({
                    'name': db_game.display_name,
                    'online': online if amp else None,
                    'max': amp.get('max', '-') if amp else None,
                    'live_now': bool(amp and amp.get('live_now', False)),
                    'has_amp': bool(db_game.amp_instance_id),
                })
    except Exception as e:
        logger.error('api_gameservers_discover_strip: %s', e)
    finally:
        loop.close()

    return JsonResponse({'servers': servers})


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
@ratelimit(key='ip', rate='10/h', block=True)
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


LEGACY_MARKS = [
    {'tier': 1, 'name': 'Wanderer',   'img': 'Common.png',    'color': 'text-gray-400',   'border': 'border-gray-600',   'threshold': 0,
     'perks': ['QuestLog account', 'Basic LFG access', 'Community access', 'Open game servers (Minecraft, DragonWilds, Valheim)', '7DTD - Project SYNAPSE access']},
    {'tier': 2, 'name': 'Ranger',     'img': 'Rare.png',      'color': 'text-blue-400',   'border': 'border-blue-600',   'threshold': 500,
     'perks': ['Everything in Wanderer', 'Palworld server access', 'Soulmask server access', 'Hytale server access', 'Extra flair slots']},
    {'tier': 3, 'name': 'Warden',     'img': 'Epic.png',      'color': 'text-purple-400', 'border': 'border-purple-600', 'threshold': 2000,
     'perks': ['Everything in Ranger', 'Priority LFG placement', 'Extended posts (2,000 characters)', 'Warden role + exclusive channel on Fluxer and Discord', 'Community landing page (Coming Soon)']},
    {'tier': 4, 'name': 'Champion',   'img': 'Legendary.png', 'color': 'text-orange-400', 'border': 'border-orange-600', 'threshold': 7500,
     'perks': ['Everything in Warden', 'Priority queue on all servers', 'Mod tools access', 'Restricted zones (In Development)']},
    {'tier': 5, 'name': 'Ascendant',  'img': 'Mythic.png',    'color': 'text-yellow-400', 'border': 'border-yellow-500', 'threshold': 25000,
     'perks': ['Everything in Champion', 'Server mod by default', 'Co-host privileges', 'Top discovery placement']},
]


@add_web_user_context
def legacy_page(request):
    """Legacy Mark page - shows current mark, progress, perks."""
    MARKS = [dict(m) for m in LEGACY_MARKS]

    score = 0
    current_tier = 1
    if request.web_user:
        score = request.web_user.legacy_score or 0
        current_tier = request.web_user.legacy_tier or 1

    current_mark = MARKS[current_tier - 1]
    next_mark = MARKS[current_tier] if current_tier < 5 else None

    if next_mark:
        points_into_tier = score - current_mark['threshold']
        points_needed = next_mark['threshold'] - current_mark['threshold']
        progress_pct = min(100, int((points_into_tier / points_needed) * 100)) if points_needed > 0 else 100
        points_to_next = max(0, next_mark['threshold'] - score)
    else:
        progress_pct = 100
        points_to_next = 0

    # Annotate each mark with unlocked/current flags for the template
    for m in MARKS:
        m['is_current'] = m['tier'] == current_tier
        m['is_unlocked'] = m['tier'] <= current_tier

    context = {
        'web_user': request.web_user,
        'active_page': 'legacy',
        'score': score,
        'current_tier': current_tier,
        'current_mark': current_mark,
        'next_mark': next_mark,
        'progress_pct': progress_pct,
        'points_to_next': points_to_next,
        'marks': MARKS,
    }
    return render(request, 'questlog_web/legacy.html', context)


@add_web_user_context
def public_legacy(request, username):
    """Public Legacy Mark page for any user at u/<username>/legacy/."""
    from .models import WebUser
    from .helpers import LEGACY_TIERS, LEGACY_TIER_NAMES

    MARKS = [dict(m) for m in LEGACY_MARKS]

    with get_db_session() as db:
        profile_user = db.query(WebUser).filter_by(username=username).first()
        if not profile_user or profile_user.is_banned or not profile_user.email_verified:
            return render(request, 'questlog_web/public_legacy.html', {
                'web_user': request.web_user, 'error': True, 'active_page': 'legacy',
            })
        score        = profile_user.legacy_score or 0
        current_tier = profile_user.legacy_tier or 1
        avatar_url   = profile_user.avatar_url
        display_name = profile_user.display_name or profile_user.username
        pu_username  = profile_user.username

    current_mark = MARKS[current_tier - 1]
    next_mark    = MARKS[current_tier] if current_tier < 5 else None

    if next_mark:
        points_into_tier = score - current_mark['threshold']
        points_needed    = next_mark['threshold'] - current_mark['threshold']
        progress_pct     = min(100, int((points_into_tier / points_needed) * 100)) if points_needed > 0 else 100
        points_to_next   = max(0, next_mark['threshold'] - score)
    else:
        progress_pct   = 100
        points_to_next = 0

    for m in MARKS:
        m['is_current']  = m['tier'] == current_tier
        m['is_unlocked'] = m['tier'] <= current_tier

    context = {
        'web_user':     request.web_user,
        'active_page':  'legacy',
        'profile_user_username': pu_username,
        'profile_user_display_name': display_name,
        'profile_user_avatar': avatar_url,
        'score':         score,
        'current_mark':  current_mark,
        'next_mark':     next_mark,
        'progress_pct':  progress_pct,
        'points_to_next': points_to_next,
        'marks':         MARKS,
    }
    return render(request, 'questlog_web/public_legacy.html', context)


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

    # Award legacy to group creator when Fluxer LFG group fills
    if new_status == 'full' and group_creator_web_user_id:
        try:
            from .helpers import award_legacy
            award_legacy(group_creator_web_user_id, 'lfg_group_filled', source='fluxer', ref_id=f"fluxer_lfg_fill_{group_id}")
        except Exception as e:
            logger.warning(f"[LFG] Failed to award legacy for Fluxer fill on group {group_id}: {e}")

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
            lfg_url = f"https://questlog.casual-heroes.com/dashboard/fluxer/{notify_guild_id}/lfg/browse/"
            detail_field = {"name": "Class / Role", "value": join_detail, "inline": True} if join_detail else None
            profile_val = f"https://questlog.casual-heroes.com/profile/{username}/" if web_user else username
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
                "footer": "QuestLog Network - casual-heroes.comlfg/",
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

        ran = group.status == 'full' or (group.current_size or 1) > 1
        creator_web_user_id = group.creator_web_user_id
        group.status = 'closed'
        db.commit()

    # Award legacy if Fluxer group actually ran
    if ran and creator_web_user_id:
        try:
            from .helpers import award_legacy
            award_legacy(creator_web_user_id, 'lfg_completed', source='fluxer', ref_id=f"fluxer_lfg_done_{group_id}")
        except Exception as e:
            logger.warning(f"[LFG] Failed to award legacy for Fluxer completion on group {group_id}: {e}")

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
    """Queue a flair role sync for both Fluxer and Discord bots."""
    try:
        from .models import WebFluxerRoleUpdate, WebDiscordPendingRoleUpdate
        now = int(time.time())
        with get_db_session() as db:
            db.add(WebFluxerRoleUpdate(
                web_user_id=web_user_id,
                action=action,
                flair_emoji=flair_emoji,
                flair_name=flair_name,
                created_at=now,
            ))
            db.add(WebDiscordPendingRoleUpdate(
                web_user_id=web_user_id,
                action=action,
                flair_emoji=flair_emoji,
                flair_name=flair_name,
                created_at=now,
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


# ---------------------------------------------------------------------------
# Legacy Nominations
# ---------------------------------------------------------------------------

NOMINATION_CATEGORIES = [
    # Community-wide
    {'key': 'community',  'label': 'Most Helpful',        'icon': 'fas fa-globe',       'color': 'text-yellow-400',  'points': 15, 'desc': 'Went above and beyond for the community'},
    {'key': 'lfg_host',   'label': 'Best LFG Host',       'icon': 'fas fa-users',       'color': 'text-cyan-400',    'points': 12, 'desc': 'Ran the best groups and kept people coming back'},
    {'key': 'build',      'label': 'Most Creative Build',  'icon': 'fas fa-hammer',      'color': 'text-lime-400',    'points': 12, 'desc': 'Built something that made everyone stop and look'},
    # Per-server
    {'key': '7dtd',       'label': 'SYNAPSE MVP',          'icon': 'fas fa-skull',       'color': 'text-orange-400',  'points': 10, 'desc': 'Survived, helped, and led through Project SYNAPSE'},
    {'key': 'valheim',    'label': 'Valheim Wanderer',      'icon': 'fas fa-snowflake',   'color': 'text-blue-400',    'points': 10, 'desc': 'Explored, built, and kept the Norse spirit alive'},
    {'key': 'minecraft',  'label': 'Minecraft Builder',     'icon': 'fas fa-cube',        'color': 'text-green-400',   'points': 10, 'desc': 'Created something worth visiting on the server'},
    {'key': 'dayz',       'label': 'DayZ Survivor',         'icon': 'fas fa-biohazard',   'color': 'text-red-400',     'points': 10, 'desc': 'Helped others stay alive in the hardest game we run'},
    {'key': 'palworld',   'label': 'Palworld Tamer',        'icon': 'fas fa-dragon',      'color': 'text-emerald-400', 'points': 10, 'desc': 'Best Pal builds, trades, and server contributions'},
]


@web_login_required
@add_web_user_context
def legacy_nominate(request):
    """Nomination submission page at legacy/nominate/."""
    from .models import WebUser, WebLegacyNomination
    import datetime

    now = int(time.time())
    month_year = datetime.datetime.utcnow().strftime('%Y-%m')
    # Voting window: 26th onward - nominations closed
    day_of_month = datetime.datetime.utcnow().day
    nominations_open = day_of_month <= 25

    # Load this user's existing nominations this month (with nominated usernames)
    my_nominations = {}
    with get_db_session() as db:
        rows = db.query(WebLegacyNomination).filter_by(
            month_year=month_year,
            nominated_by_web_user_id=request.web_user.id,
        ).all()
        user_ids = [r.nominated_user_id for r in rows]
        username_map = {}
        if user_ids:
            users = db.query(WebUser).filter(WebUser.id.in_(user_ids)).all()
            username_map = {u.id: u.username for u in users}
        for row in rows:
            my_nominations[row.category] = {
                'username': username_map.get(row.nominated_user_id, ''),
                'reason': row.reason or '',
            }

    return render(request, 'questlog_web/legacy_nominate.html', {
        'web_user': request.web_user,
        'active_page': 'legacy',
        'categories': NOMINATION_CATEGORIES,
        'my_nominations_json': json.dumps(my_nominations),
        'month_year': month_year,
        'nominations_open': nominations_open,
    })


@web_login_required
@require_http_methods(['POST'])
def api_legacy_nominate(request):
    """POST api/legacy/nominate/ - submit or update a nomination."""
    from .models import WebUser, WebLegacyNomination
    import datetime

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    category = (data.get('category') or '').strip()
    nominated_username = (data.get('username') or '').strip()
    reason = sanitize_text((data.get('reason') or '').strip())[:500]

    valid_keys = {c['key'] for c in NOMINATION_CATEGORIES}
    if category not in valid_keys:
        return JsonResponse({'error': 'Invalid category'}, status=400)
    if not nominated_username:
        return JsonResponse({'error': 'Username required'}, status=400)

    now = int(time.time())
    month_year = datetime.datetime.utcnow().strftime('%Y-%m')
    day_of_month = datetime.datetime.utcnow().day
    if day_of_month > 25:
        return JsonResponse({'error': 'Nominations are closed for this month'}, status=400)

    with get_db_session() as db:
        # Resolve nominated user
        nominated = db.query(WebUser).filter_by(username=nominated_username).first()
        if not nominated or nominated.is_banned or not nominated.email_verified:
            return JsonResponse({'error': 'User not found'}, status=404)
        if nominated.id == request.web_user.id:
            return JsonResponse({'error': 'You cannot nominate yourself'}, status=400)

        # Upsert: one nomination per nominator per category per month
        existing = db.query(WebLegacyNomination).filter_by(
            month_year=month_year,
            category=category,
            nominated_by_web_user_id=request.web_user.id,
        ).first()

        if existing:
            existing.nominated_user_id = nominated.id
            existing.reason = reason
            existing.updated_at = now
        else:
            db.add(WebLegacyNomination(
                month_year=month_year,
                category=category,
                nominated_user_id=nominated.id,
                nominated_by_web_user_id=request.web_user.id,
                platform='web',
                reason=reason,
                created_at=now,
                updated_at=now,
            ))
        db.commit()

    return JsonResponse({'success': True, 'month_year': month_year, 'category': category})


@require_http_methods(['POST'])
def api_internal_close_nominations(request):
    """POST api/internal/close-nominations/ - called by cron at month end.
    Tallies votes, picks winners per category, awards Legacy + notification.
    Secured by BOT_API_SECRET header.
    """
    from .models import WebUser, WebLegacyNomination, WebNotification
    from .helpers import award_legacy, grant_flair_award
    import datetime
    from django.conf import settings as django_settings

    import hmac as _hmac
    secret = getattr(django_settings, 'BOT_INTERNAL_SECRET', '')
    provided = request.META.get('HTTP_X_BOT_SECRET', '')
    if not secret or not _hmac.compare_digest(provided, secret):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        data = {}

    # Default: close the previous month if called on 1st, else current month
    now_dt = datetime.datetime.utcnow()
    month_year = data.get('month_year') or now_dt.strftime('%Y-%m')

    results = []
    cat_points = {c['key']: c['points'] for c in NOMINATION_CATEGORIES}

    with get_db_session() as db:
        for cat in cat_points:
            # Tally: count nominations per nominated_user for this category/month
            rows = db.execute(
                text(
                    "SELECT nominated_user_id, COUNT(*) as cnt "
                    "FROM web_legacy_nominations "
                    "WHERE month_year = :my AND category = :cat AND awarded = 0 "
                    "GROUP BY nominated_user_id ORDER BY cnt DESC LIMIT 1"
                ),
                {'my': month_year, 'cat': cat}
            ).fetchone()

            if not rows:
                results.append({'category': cat, 'winner': None})
                continue

            winner_id = rows[0]
            now = int(time.time())

            # Mark all nominations in this category as awarded
            db.execute(
                text(
                    "UPDATE web_legacy_nominations SET awarded = 1, updated_at = :now "
                    "WHERE month_year = :my AND category = :cat"
                ),
                {'now': now, 'my': month_year, 'cat': cat}
            )

            # Create winner notification
            cat_label = next((c['label'] for c in NOMINATION_CATEGORIES if c['key'] == cat), cat)
            db.add(WebNotification(
                user_id=winner_id,
                notif_type='legacy_award',
                message=f'You won {cat_label} for {month_year}! +{cat_points[cat]} Legacy awarded.',
                created_at=now,
                is_read=0,
            ))
            db.commit()

            results.append({'category': cat, 'winner_id': winner_id})

        # Award Legacy outside the session loop to avoid DetachedInstanceError
    for r in results:
        if r.get('winner_id'):
            award_legacy(
                r['winner_id'],
                'most_helpful_vote',
                source='web',
                ref_id=f"{month_year}:{r['category']}",
            )
            grant_flair_award(r['winner_id'], r['category'], month_year)

    return JsonResponse({'success': True, 'month_year': month_year, 'results': results})


@add_web_user_context
def steamquest(request):
    """SteamQuest - random game picker from the user's Steam library."""
    web_user = request.web_user
    has_steam = bool(web_user and web_user.steam_id)
    return render(request, 'questlog_web/steamquest.html', {
        'web_user': web_user,
        'active_page': 'steamquest',
        'has_steam': has_steam,
    })


@add_web_user_context
@require_http_methods(['GET'])
@ratelimit(key='ip', rate='30/m', block=True)
def api_steamquest_library(request):
    """GET /ql/api/steamquest/library/ - fetch + cache user's Steam owned games."""
    from .helpers import STEAM_API_KEY
    from .steam_auth import get_steam_owned_games
    from django.core.cache import cache

    web_user = request.web_user
    if not web_user or not web_user.steam_id:
        return JsonResponse({'ok': False, 'error': 'Steam account not linked. Link Steam in your settings.'}, status=400)

    cache_key = f'steamquest_library_{web_user.steam_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({'ok': True, 'games': cached, 'cached': True})

    games = get_steam_owned_games(web_user.steam_id, STEAM_API_KEY, include_free=True)
    if games is None:
        return JsonResponse({'ok': False, 'error': 'Could not fetch Steam library. Make sure your Steam profile is set to Public in Steam privacy settings.'}, status=502)

    cache.set(cache_key, games, 600)
    return JsonResponse({'ok': True, 'games': games, 'cached': False})


@add_web_user_context
@require_http_methods(['GET'])
@ratelimit(key='ip', rate='60/m', block=True)
def api_steamquest_game_detail(request, app_id):
    """GET /ql/api/steamquest/game/<app_id>/ - on-demand rich game data from Steam store."""
    import requests as http_requests
    from .helpers import STEAM_API_KEY
    from django.core.cache import cache

    app_id = int(app_id)
    cache_key = f'steamquest_detail_{app_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({'ok': True, **cached})

    result = {}
    try:
        # Store details: description, genres, categories, screenshots, movies, metacritic
        resp = http_requests.get(
            f'https://store.steampowered.com/api/appdetails?appids={app_id}&cc=us&l=en',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=10
        )
        data = resp.json().get(str(app_id), {}).get('data', {})

        cats = {c['id'] for c in data.get('categories', [])}
        genres = [g['description'] for g in data.get('genres', [])]
        genre_ids = [int(g['id']) for g in data.get('genres', []) if 'id' in g]
        # Steam community tag IDs (dict of tagid -> vote_count, keys are strings)
        raw_tags = data.get('tags', {})
        steam_tag_ids = [int(k) for k in raw_tags.keys()] if isinstance(raw_tags, dict) else []

        result = {
            'name': data.get('name', ''),
            'short_description': data.get('short_description', ''),
            'header_image': data.get('header_image', ''),
            'background': data.get('background', ''),
            'capsule_image': data.get('capsule_imagev5', data.get('capsule_image', '')),
            'genres': genres,
            'genre_ids': genre_ids,
            'steam_tag_ids': steam_tag_ids,
            'developers': data.get('developers', []),
            'publishers': data.get('publishers', []),
            'release_date': data.get('release_date', {}).get('date', ''),
            'metacritic_score': data.get('metacritic', {}).get('score'),
            'metacritic_url': data.get('metacritic', {}).get('url'),
            'recommendations': data.get('recommendations', {}).get('total'),
            'achievements_total': data.get('achievements', {}).get('total', 0),
            'is_free': data.get('is_free', False),
            'website': data.get('website', ''),
            # Feature flags from categories
            'has_singleplayer':    2  in cats,
            'has_multiplayer':     1  in cats or 9 in cats,
            'has_co_op':           9  in cats or 38 in cats,
            'has_controller':      28 in cats or 33 in cats or 18 in cats,
            'has_full_controller': 28 in cats,
            'has_trading_cards':   29 in cats,
            'has_cloud':           23 in cats,
            'has_workshop':        30 in cats,
            'has_achievements':    22 in cats,
            'has_remote_play':     41 in cats or 42 in cats or 43 in cats,
            # Media
            'screenshots': [s['path_full'] for s in data.get('screenshots', [])[:8]],
            'movies': [
                {
                    'name': m.get('name', ''),
                    'thumbnail': m.get('thumbnail', ''),
                    'mp4': m.get('mp4', {}).get('max') or m.get('mp4', {}).get('480'),
                    'webm': m.get('webm', {}).get('max') or m.get('webm', {}).get('480'),
                }
                for m in data.get('movies', [])[:3]
            ],
        }
    except Exception as e:
        logger.warning(f'SteamQuest appdetails failed for {app_id}: {e}')

    # Review score (separate endpoint - more accurate)
    try:
        rev = http_requests.get(
            f'https://store.steampowered.com/appreviews/{app_id}?json=1&num_per_page=0&language=all',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=6
        ).json()
        qs = rev.get('query_summary', {})
        result['review_score_desc'] = qs.get('review_score_desc', '')
        result['review_score']      = qs.get('review_score', 0)
        result['reviews_positive']  = qs.get('total_positive', 0)
        result['reviews_total']     = qs.get('total_reviews', 0)
        if result['reviews_total'] > 0:
            result['review_pct'] = round(result['reviews_positive'] / result['reviews_total'] * 100)
        else:
            result['review_pct'] = None
    except Exception as e:
        logger.warning(f'SteamQuest reviews failed for {app_id}: {e}')

    # Per-user achievements if Steam ID available
    web_user = getattr(request, 'web_user', None)
    if web_user and web_user.steam_id and result.get('has_achievements'):
        try:
            ach_resp = http_requests.get(
                f'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/',
                params={'key': STEAM_API_KEY, 'steamid': web_user.steam_id, 'appid': app_id},
                timeout=6
            ).json()
            achievements = ach_resp.get('playerstats', {}).get('achievements', [])
            earned = sum(1 for a in achievements if a.get('achieved'))
            result['user_achievements_earned'] = earned
            result['user_achievements_total']  = len(achievements)
        except Exception:
            pass

    cache.set(cache_key, result, 3600)  # 1hr cache - game data rarely changes
    return JsonResponse({'ok': True, **result})


@add_web_user_context
@require_http_methods(['GET'])
def api_steamquest_tag_filter(request):
    """GET /ql/api/steamquest/tag/?tag_name=battle+royale
    Returns app IDs from local web_steam_app_tags table that have this tag.
    Client intersects with owned library for genre/theme filtering."""
    from django.core.cache import cache
    from sqlalchemy import text as sa_text

    tag_name = request.GET.get('tag_name', '').strip().lower()
    if not tag_name or len(tag_name) > 100:
        return JsonResponse({'ok': False, 'error': 'Invalid tag_name'}, status=400)

    cache_key = f'sqtag_{tag_name}'
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({'ok': True, 'app_ids': cached, 'source': 'cache'})

    with get_db_session() as db:
        rows = db.execute(
            sa_text('SELECT app_id FROM web_steam_app_tags WHERE tag_name = :tag'),
            {'tag': tag_name}
        ).fetchall()
    app_ids = [r[0] for r in rows]
    cache.set(cache_key, app_ids, 1800)  # 30min cache
    return JsonResponse({'ok': True, 'app_ids': app_ids, 'count': len(app_ids)})


@web_login_required
@require_http_methods(['POST'])
@ratelimit(key='ip', rate='2/m', block=True)
def api_steamquest_sync_tags(request):
    """POST /ql/api/steamquest/sync-tags/
    Fetches SteamSpy tags for all app_ids in the current user's library
    that aren't already in web_steam_app_tags. Runs in background thread."""
    import threading
    import requests as http_requests
    from django.core.cache import cache
    from sqlalchemy import text as sa_text
    from .helpers import STEAM_API_KEY
    from .steam_auth import get_steam_owned_games

    web_user = request.web_user
    if not web_user or not web_user.steam_id:
        return JsonResponse({'ok': True, 'queued': 0})

    # Use cached library if available, else fetch
    cache_key = f'steamquest_library_{web_user.steam_id}'
    games = cache.get(cache_key)
    if not games:
        games = get_steam_owned_games(web_user.steam_id, STEAM_API_KEY, include_free=True) or []

    all_ids = [int(g['app_id']) for g in games if g.get('app_id')]
    if not all_ids:
        return JsonResponse({'ok': True, 'queued': 0})

    # Find which ones aren't synced yet
    placeholders = ','.join(str(aid) for aid in all_ids)
    with get_db_session() as db:
        synced = {r[0] for r in db.execute(
            sa_text(f'SELECT DISTINCT app_id FROM web_steam_app_tags WHERE app_id IN ({placeholders})')
        ).fetchall()}
    to_sync = [aid for aid in all_ids if aid not in synced]

    if not to_sync:
        return JsonResponse({'ok': True, 'queued': 0, 'msg': 'all synced'})

    def sync_worker(app_ids):
        from concurrent.futures import ThreadPoolExecutor, as_completed as asc
        now = int(time.time())

        def fetch(aid):
            try:
                r = http_requests.get(
                    f'https://steamspy.com/api.php?request=appdetails&appid={aid}',
                    headers={'User-Agent': 'Mozilla/5.0'}, timeout=6
                ).json()
                tags = r.get('tags', {})
                return aid, [t.lower() for t in tags.keys()] if isinstance(tags, dict) and tags else None
            except Exception:
                return aid, None

        for i in range(0, len(app_ids), 20):
            batch = app_ids[i:i + 20]
            with ThreadPoolExecutor(max_workers=20) as ex:
                for fut in asc({ex.submit(fetch, aid): aid for aid in batch}):
                    aid, tags = fut.result()
                    if tags:
                        try:
                            with get_db_session() as db:
                                for tag in tags:
                                    db.execute(sa_text(
                                        'INSERT IGNORE INTO web_steam_app_tags (app_id, tag_name, synced_at) '
                                        'VALUES (:app_id, :tag, :now)'
                                    ), {'app_id': aid, 'tag': tag, 'now': now})
                                db.commit()
                        except Exception:
                            pass
            if i + 20 < len(app_ids):
                time.sleep(0.5)

    threading.Thread(target=sync_worker, args=(to_sync,), daemon=True).start()
    return JsonResponse({'ok': True, 'queued': len(to_sync)})


@add_web_user_context
@require_http_methods(['GET'])
@ratelimit(key='ip', rate='30/m', block=True)
def api_steamquest_who_owns(request):
    """GET /ql/api/steamquest/who-owns/?app_id=X
    Returns list of QuestLog members who have opted in to library sharing and own this game.
    Only checks users who have share_steam_library=True. Uses cached libraries where available.
    """
    from .helpers import STEAM_API_KEY
    from .steam_auth import get_steam_owned_games
    from .models import WebUser
    from django.core.cache import cache

    web_user = request.web_user
    if not web_user:
        return JsonResponse({'ok': False, 'error': 'Login required'}, status=401)

    app_id_str = request.GET.get('app_id', '').strip()
    if not app_id_str or not app_id_str.isdigit():
        return JsonResponse({'ok': False, 'error': 'Invalid app_id'}, status=400)
    app_id = int(app_id_str)

    # Find all opted-in users with Steam linked, excluding self
    with get_db_session() as db:
        candidates = db.query(
            WebUser.id, WebUser.steam_id, WebUser.username,
            WebUser.avatar_url, WebUser.steam_username
        ).filter(
            WebUser.share_steam_library == True,
            WebUser.steam_id.isnot(None),
            WebUser.steam_id != '',
            WebUser.is_banned == False,
            WebUser.is_disabled == False,
            WebUser.is_hidden == False,
        ).limit(100).all()

    if not candidates:
        return JsonResponse({'ok': True, 'owners': []})

    owners = []
    for u in candidates:
        cache_key = f'steamquest_library_{u.steam_id}'
        library = cache.get(cache_key)
        if library is None:
            # Fetch and cache their library (10 min)
            library = get_steam_owned_games(u.steam_id, STEAM_API_KEY, include_free=True)
            if library:
                cache.set(cache_key, library, 600)
            else:
                continue

        if any(g['app_id'] == app_id for g in library):
            playtime = next((g['playtime_hours'] for g in library if g['app_id'] == app_id), 0)
            owners.append({
                'username': u.username,
                'display_name': u.steam_username or u.username,
                'avatar_url': u.avatar_url or '',
                'playtime_hours': playtime,
                'profile_url': f'/ql/u/{u.username}/',
            })

    owners.sort(key=lambda x: x['playtime_hours'], reverse=True)
    return JsonResponse({'ok': True, 'owners': owners})


@add_web_user_context
@require_http_methods(['GET'])
def api_steamquest_community_owns(request):
    """GET /api/steamquest/community-owns/?names=Game1|Game2
    Returns how many QuestLog members (with share_steam_library=True and Steam linked)
    own each game, matched by name against their cached Steam libraries.
    """
    from .helpers import STEAM_API_KEY
    from .steam_auth import get_steam_owned_games
    from .models import WebUser
    from django.core.cache import cache

    raw = request.GET.get('names', '').strip()
    if not raw:
        return JsonResponse({'ok': False, 'error': 'names required'}, status=400)

    names = [n.strip() for n in raw.split('|') if n.strip()][:10]
    if not names:
        return JsonResponse({'ok': False, 'error': 'names required'}, status=400)

    cache_key = 'community_owns_' + '_'.join(sorted(n.lower() for n in names))
    cached = cache.get(cache_key)
    if cached is not None:
        return JsonResponse({'ok': True, 'counts': cached})

    with get_db_session() as db:
        candidates = db.query(WebUser.id, WebUser.steam_id).filter(
            WebUser.share_steam_library == True,
            WebUser.steam_id.isnot(None),
            WebUser.steam_id != '',
            WebUser.is_banned == False,
            WebUser.is_disabled == False,
            WebUser.is_hidden == False,
        ).limit(200).all()

    name_lower = {n.lower(): n for n in names}
    counts = {n: 0 for n in names}

    for u in candidates:
        lib_key = f'steamquest_library_{u.steam_id}'
        library = cache.get(lib_key)
        if library is None:
            library = get_steam_owned_games(u.steam_id, STEAM_API_KEY, include_free=True)
            if library:
                cache.set(lib_key, library, 600)
            else:
                continue
        for g in library:
            gname = (g.get('name') or '').lower()
            if gname in name_lower:
                counts[name_lower[gname]] += 1

    cache.set(cache_key, counts, 300)
    return JsonResponse({'ok': True, 'counts': counts})


from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def api_public_testimonials(request):
    """Public: return active testimonials ordered by sort_order."""
    with get_db_session() as db:
        rows = db.query(WebTestimonial).filter_by(is_active=True).order_by(
            WebTestimonial.sort_order, WebTestimonial.id
        ).all()
        data = [{
            'id':          t.id,
            'member_name': t.member_name,
            'handle':      t.handle or '',
            'avatar_url':  t.avatar_url or '',
            'quote':       t.quote,
            'game_tag':    t.game_tag or '',
        } for t in rows]
    return JsonResponse({'testimonials': data})


@require_GET
@add_web_user_context
def api_calendar_game_nights(request):
    """Public: return upcoming game night events for the calendar polling."""
    from .models import WebCommunityEvent, WebCommunity, WebCommunityEventRSVP
    now_ts = int(time.time())
    cutoff = now_ts - 86400

    with get_db_session() as db:
        game_nights = db.query(WebCommunityEvent).filter(
            WebCommunityEvent.is_cancelled == False,
            WebCommunityEvent.starts_at >= cutoff,
        ).order_by(WebCommunityEvent.starts_at).limit(200).all()

        community_ids = list({e.community_id for e in game_nights})
        community_map = {}
        if community_ids:
            communities = db.query(WebCommunity).filter(
                WebCommunity.id.in_(community_ids),
                WebCommunity.is_active == True,
                WebCommunity.is_banned == False,
                WebCommunity.allow_discovery == True,
            ).all()
            community_map = {c.id: c for c in communities}

        user_id = request.web_user.id if hasattr(request, 'web_user') and request.web_user else None
        gn_rsvp_map = {}
        if user_id and game_nights:
            gn_ids = [e.id for e in game_nights if e.community_id in community_map]
            if gn_ids:
                rsvp_rows = db.query(WebCommunityEventRSVP).filter(
                    WebCommunityEventRSVP.user_id == user_id,
                    WebCommunityEventRSVP.event_id.in_(gn_ids),
                ).all()
                gn_rsvp_map = {r.event_id: r.status for r in rsvp_rows}

        events = [
            {
                'id': 'gn-' + str(e.id),
                'title': e.title,
                'game_name': e.game_tag_name or '',
                'ts': e.starts_at,
                'status': 'open',
                'current_size': e.rsvp_going,
                'max_size': e.max_attendees or 0,
                'recurrence': e.recurrence or 'none',
                'guild_id': None,
                'guild_name': community_map[e.community_id].name if e.community_id in community_map else '',
                'community_name': community_map[e.community_id].name if e.community_id in community_map else '',
                'community_id': e.community_id,
                'community_slug': _community_slug(community_map[e.community_id].name) if e.community_id in community_map else '',
                'description': e.description or '',
                'type': 'game_night',
                'rsvp_going': e.rsvp_going,
                'duration_mins': e.duration_mins,
                'rsvp_maybe': e.rsvp_maybe,
                'my_rsvp': gn_rsvp_map.get(e.id),
            }
            for e in game_nights
            if e.community_id in community_map
        ]

    return JsonResponse({'events': events})


@require_GET
@add_web_user_context
def api_calendar_lfg_events(request):
    """Public: return active LFG events for calendar polling."""
    now_ts = int(time.time())
    cutoff = now_ts - 86400

    from .models import WebFluxerLfgGroup, WebFluxerLfgConfig, WebFluxerGuildSettings

    with get_db_session() as db:
        # Published Fluxer LFG groups
        published_guild_ids = [
            r[0] for r in db.query(WebFluxerLfgConfig.guild_id)
            .filter(WebFluxerLfgConfig.publish_to_network == 1).all()
        ]
        fluxer_groups = db.query(WebFluxerLfgGroup).filter(
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

        guild_ids = list({g.guild_id for g in fluxer_groups})
        guild_name_map = {}
        if guild_ids:
            settings_rows = db.query(
                WebFluxerGuildSettings.guild_id,
                WebFluxerGuildSettings.guild_name,
            ).filter(WebFluxerGuildSettings.guild_id.in_(guild_ids)).all()
            guild_name_map = {r[0]: r[1] or 'Unknown Server' for r in settings_rows}

        fluxer_events = [
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
                'type': 'lfg',
            }
            for g in fluxer_groups
        ]

        # Web-native LFG groups
        web_groups = db.query(WebLFGGroup).filter(
            WebLFGGroup.scheduled_time.isnot(None),
            WebLFGGroup.scheduled_time >= cutoff,
            WebLFGGroup.status.in_(['open', 'full']),
            WebLFGGroup.allow_network_discovery == True,
        ).order_by(WebLFGGroup.scheduled_time).limit(200).all()

        web_events = [
            {
                'id': g.id,
                'share_token': g.share_token or '',
                'share_url': f'/ql/lfg/{g.share_token}/' if g.share_token else f'/ql/lfg/{g.id}/',
                'title': g.title,
                'game_name': g.game_name or '',
                'ts': g.scheduled_time,
                'status': g.status,
                'current_size': g.current_size,
                'max_size': g.group_size,
                'recurrence': 'none',
                'guild_id': None,
                'guild_name': g.origin_guild_name or '',
                'description': g.description or '',
                'type': 'lfg',
                'source': 'web',
                'creator_id': g.creator_id,
            }
            for g in web_groups
        ]

    return JsonResponse({'events': fluxer_events + web_events})


# ---------------------------------------------------------------------------
# Site Announcements / What's New
# ---------------------------------------------------------------------------

@add_web_user_context
@require_http_methods(['GET'])
def page_whats_new(request):
    """Public What's New page listing all site announcements."""
    from .models import WebSiteAnnouncement
    with get_db_session() as db:
        announcements = db.query(WebSiteAnnouncement).order_by(
            WebSiteAnnouncement.is_pinned.desc(),
            WebSiteAnnouncement.created_at.desc()
        ).limit(50).all()

        now = int(time.time())
        seven_days = 7 * 86400

        items = []
        from django.utils.safestring import mark_safe
        from .helpers import sanitize_article_html
        for a in announcements:
            author = a.author
            items.append({
                'id': a.id,
                'title': a.title,
                'body_html': mark_safe(sanitize_article_html(a.body_md)),
                'category': a.category,
                'is_pinned': a.is_pinned,
                'is_new': (now - a.created_at) < seven_days,
                'created_at': a.created_at,
                'media_items': json.loads(a.media_items) if a.media_items else (
                    [{'url': a.media_url, 'type': a.media_type}] if a.media_url else []
                ),
                'game_tag_name': a.game_tag_name or '',
                'game_tag_steam_id': a.game_tag_steam_id or 0,
                'author_username': author.username if author else '',
                'author_display_name': (author.display_name or author.username) if author else 'Admin',
                'author_avatar': author.avatar_url or '' if author else '',
            })

    return render(request, 'questlog_web/whats_new.html', {
        'web_user': request.web_user,
        'announcements': items,
        'active_page': 'whats_new',
    })


@require_http_methods(['GET', 'POST'])
@add_web_user_context
def api_admin_announcements(request):
    """Admin: list all announcements (GET) or create one (POST)."""
    from .helpers import web_admin_required
    from .models import WebSiteAnnouncement

    if not (request.web_user and request.web_user.is_admin):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    with get_db_session() as db:
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

            title = (data.get('title', '').strip())[:200]
            body_md = (data.get('body_md') or '').strip()[:10000]
            category = data.get('category', 'update')
            if category not in ('update', 'event', 'maintenance', 'feature'):
                category = 'update'
            is_pinned = bool(data.get('is_pinned', False))

            from app.questlog_web.helpers import _is_valid_giphy_url
            game_tag_name = (data.get('game_tag_name') or '')[:200] or None
            game_tag_steam_id = safe_int(data.get('game_tag_steam_id'), None)

            # Multi-media: list of {url, type} - no limit for admins
            raw_items = data.get('media_items') or []
            media_items_clean = []
            for item in raw_items[:50]:
                url = (item.get('url') or '').strip()[:500]
                mtype = (item.get('type') or '').strip()
                if mtype == 'gif' and _is_valid_giphy_url(url):
                    media_items_clean.append({'url': url, 'type': 'gif'})
                elif mtype == 'image' and url.startswith('/media/uploads/'):
                    media_items_clean.append({'url': url, 'type': 'image'})
            # Legacy single-media compat
            media_url = media_items_clean[0]['url'] if media_items_clean else None
            media_type = media_items_clean[0]['type'] if media_items_clean else None

            if not title or (not body_md and not media_items_clean):
                return JsonResponse({'error': 'Title and body or media required'}, status=400)

            now = int(time.time())
            ann = WebSiteAnnouncement(
                author_id=request.web_user.id,
                title=title,
                body_md=body_md or '',
                category=category,
                is_pinned=is_pinned,
                media_url=media_url,
                media_type=media_type,
                media_items=json.dumps(media_items_clean) if media_items_clean else None,
                game_tag_name=game_tag_name,
                game_tag_steam_id=game_tag_steam_id,
                created_at=now,
                updated_at=now,
            )
            db.add(ann)
            db.commit()
            return JsonResponse({'ok': True, 'id': ann.id})

        # GET - list all
        items = db.query(WebSiteAnnouncement).order_by(
            WebSiteAnnouncement.is_pinned.desc(),
            WebSiteAnnouncement.created_at.desc()
        ).all()
        return JsonResponse({'announcements': [
            {
                'id': a.id,
                'title': a.title,
                'body_md': a.body_md,
                'category': a.category,
                'is_pinned': a.is_pinned,
                'created_at': a.created_at,
            }
            for a in items
        ]})


@require_http_methods(['GET', 'PUT', 'DELETE'])
@add_web_user_context
def api_admin_announcement_detail(request, ann_id):
    """Admin: get, update, or delete a specific announcement."""
    from .models import WebSiteAnnouncement

    if not (request.web_user and request.web_user.is_admin):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    with get_db_session() as db:
        ann = db.query(WebSiteAnnouncement).filter_by(id=ann_id).first()
        if not ann:
            return JsonResponse({'error': 'Not found'}, status=404)

        if request.method == 'DELETE':
            db.delete(ann)
            db.commit()
            return JsonResponse({'ok': True})

        if request.method == 'PUT':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

            if 'title' in data:
                ann.title = data['title'].strip()[:200]
            if 'body_md' in data:
                ann.body_md = data['body_md'].strip()[:10000]
            if 'category' in data and data['category'] in ('update', 'event', 'maintenance', 'feature'):
                ann.category = data['category']
            if 'is_pinned' in data:
                ann.is_pinned = bool(data['is_pinned'])
            from app.questlog_web.helpers import _is_valid_giphy_url
            if 'media_items' in data:
                raw_items = data.get('media_items') or []
                media_items_clean = []
                for item in raw_items[:50]:
                    url = (item.get('url') or '').strip()[:500]
                    mtype = (item.get('type') or '').strip()
                    if mtype == 'gif' and _is_valid_giphy_url(url):
                        media_items_clean.append({'url': url, 'type': 'gif'})
                    elif mtype == 'image' and url.startswith('/media/uploads/'):
                        media_items_clean.append({'url': url, 'type': 'image'})
                ann.media_items = json.dumps(media_items_clean) if media_items_clean else None
                ann.media_url = media_items_clean[0]['url'] if media_items_clean else None
                ann.media_type = media_items_clean[0]['type'] if media_items_clean else None
            if 'game_tag_name' in data:
                ann.game_tag_name = (data['game_tag_name'] or '')[:200] or None
                ann.game_tag_steam_id = safe_int(data.get('game_tag_steam_id'), None)
            ann.updated_at = int(time.time())
            db.commit()
            return JsonResponse({'ok': True})

        raw_items = json.loads(ann.media_items) if ann.media_items else (
            [{'url': ann.media_url, 'type': ann.media_type}] if ann.media_url else []
        )
        return JsonResponse({
            'id': ann.id,
            'title': ann.title,
            'body_md': ann.body_md,
            'category': ann.category,
            'is_pinned': ann.is_pinned,
            'media_items': raw_items,
            'game_tag_name': ann.game_tag_name or '',
            'game_tag_steam_id': ann.game_tag_steam_id or 0,
            'created_at': ann.created_at,
        })


@require_http_methods(['GET'])
@add_web_user_context
def api_announcements_latest(request):
    """Public: latest announcements for sidebar widget."""
    from .models import WebSiteAnnouncement
    with get_db_session() as db:
        items = db.query(WebSiteAnnouncement).order_by(
            WebSiteAnnouncement.is_pinned.desc(),
            WebSiteAnnouncement.created_at.desc()
        ).limit(5).all()
        now = int(time.time())
        seven_days = 7 * 86400
        return JsonResponse({'announcements': [
            {
                'id': a.id,
                'title': a.title,
                'category': a.category,
                'is_pinned': a.is_pinned,
                'is_new': (now - a.created_at) < seven_days,
                'created_at': a.created_at,
            }
            for a in items
        ]})


# ---------------------------------------------------------------------------
# Site Feedback
# ---------------------------------------------------------------------------

@require_http_methods(['POST'])
@add_web_user_context
@ratelimit(key='ip', rate='5/h', block=True)
def api_submit_feedback(request):
    """Submit user feedback. Logged-in preferred but anonymous allowed."""
    import requests as _requests
    from .models import WebSiteFeedback, WebSiteConfig

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    category = data.get('category', 'general')
    if category not in ('bug', 'feature', 'suggestion', 'general'):
        category = 'general'
    subject = sanitize_text((data.get('subject') or '').strip(), max_length=200)
    body = sanitize_text((data.get('body') or '').strip(), max_length=2000)

    if not subject or not body:
        return JsonResponse({'error': 'Subject and body required'}, status=400)

    from .helpers import _is_valid_giphy_url
    gif_url = (data.get('gif_url') or '').strip()[:500]
    image_url = (data.get('image_url') or '').strip()[:500]
    media_url = None
    media_type = None
    if gif_url and _is_valid_giphy_url(gif_url):
        media_url = gif_url
        media_type = 'gif'
    elif image_url and image_url.startswith('/media/uploads/'):
        media_url = image_url
        media_type = 'image'

    now = int(time.time())
    user_id = request.web_user.id if request.web_user else None

    CATEGORY_COLORS = {
        'bug': 0xef4444,
        'feature': 0x6366f1,
        'suggestion': 0xf59e0b,
        'general': 0x6b7280,
    }

    with get_db_session() as db:
        fb = WebSiteFeedback(
            user_id=user_id,
            category=category,
            subject=subject,
            body=body,
            media_url=media_url,
            media_type=media_type,
            status='new',
            created_at=now,
        )
        db.add(fb)
        db.commit()
        fb_id = fb.id

        # Read routing config
        fluxer_channel_cfg = db.query(WebSiteConfig).filter_by(key='feedback_fluxer_channel_id').first()
        discord_webhook_cfg = db.query(WebSiteConfig).filter_by(key='feedback_discord_webhook_url').first()
        fluxer_channel_id = fluxer_channel_cfg.value if fluxer_channel_cfg else None
        discord_webhook_url = discord_webhook_cfg.value if discord_webhook_cfg else None

    author_name = 'Anonymous'
    if request.web_user:
        author_name = request.web_user.display_name or request.web_user.username

    admin_url = f'https://questlog.casual-heroes.com/admin/?tab=feedback'
    embed = {
        'title': f'[{category.upper()}] {subject}',
        'description': body[:2000],
        'color': CATEGORY_COLORS.get(category, 0x6b7280),
        'fields': [
            {'name': 'From', 'value': author_name, 'inline': True},
            {'name': 'Category', 'value': category.capitalize(), 'inline': True},
            {'name': 'ID', 'value': f'#{fb_id}', 'inline': True},
            {'name': 'Review', 'value': f'[Open in Admin]({admin_url})', 'inline': False},
        ],
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now)),
    }

    # Send to Fluxer channel via pending broadcasts queue
    if fluxer_channel_id:
        try:
            with get_db_session() as db2:
                from sqlalchemy import text as _text
                db2.execute(_text(
                    "INSERT INTO fluxer_pending_broadcasts (guild_id, channel_id, payload, created_at) "
                    "VALUES (:g, :c, :p, :t)"
                ), {"g": 0, "c": int(fluxer_channel_id), "p": json.dumps(embed), "t": now})
                db2.commit()
        except Exception:
            pass

    # Send to Discord webhook
    if discord_webhook_url and discord_webhook_url.startswith('https://discord.com/api/webhooks/'):
        try:
            _requests.post(discord_webhook_url, json={'embeds': [embed]}, timeout=5)
        except Exception:
            pass

    return JsonResponse({'ok': True})


@require_http_methods(['GET'])
@web_login_required
@add_web_user_context
def api_my_feedback(request):
    """Logged-in user: list their own feedback submissions."""
    from .models import WebSiteFeedback
    with get_db_session() as db:
        items = db.query(WebSiteFeedback).filter_by(
            user_id=request.web_user.id
        ).order_by(WebSiteFeedback.created_at.desc()).limit(50).all()
        return JsonResponse({'feedback': [
            {
                'id': f.id,
                'category': f.category,
                'subject': f.subject,
                'body': f.body,
                'media_url': f.media_url or '',
                'media_type': f.media_type or '',
                'status': f.status,
                'admin_note': f.admin_note or '',
                'created_at': f.created_at,
            }
            for f in items
        ]})


@require_http_methods(['GET'])
@add_web_user_context
def api_admin_feedback(request):
    """Admin: list feedback submissions."""
    from .models import WebSiteFeedback
    if not (request.web_user and request.web_user.is_admin):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    status_filter = request.GET.get('status', '')
    with get_db_session() as db:
        q = db.query(WebSiteFeedback)
        if status_filter:
            q = q.filter(WebSiteFeedback.status == status_filter)
        items = q.order_by(WebSiteFeedback.created_at.desc()).limit(100).all()
        return JsonResponse({'feedback': [
            {
                'id': f.id,
                'category': f.category,
                'subject': f.subject,
                'body': f.body,
                'status': f.status,
                'created_at': f.created_at,
                'author': (f.user.display_name or f.user.username) if f.user else 'Anonymous',
            }
            for f in items
        ]})


@require_http_methods(['PUT'])
@add_web_user_context
def api_admin_feedback_detail(request, feedback_id):
    """Admin: update feedback status and/or admin note. Notifies user on completed/dismissed."""
    from .models import WebSiteFeedback
    if not (request.web_user and request.web_user.is_admin):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    with get_db_session() as db:
        fb = db.query(WebSiteFeedback).filter_by(id=feedback_id).first()
        if not fb:
            return JsonResponse({'error': 'Not found'}, status=404)
        old_status = fb.status
        valid_statuses = ('new', 'in_review', 'implementing', 'completed', 'dismissed')
        new_status = data.get('status')
        if new_status and new_status in valid_statuses:
            fb.status = new_status
        if 'admin_note' in data:
            fb.admin_note = (data['admin_note'] or '').strip()[:1000] or None
        db.commit()
        # Send notification when status changes to completed or dismissed
        if fb.user_id and new_status and new_status != old_status and new_status in ('completed', 'dismissed'):
            label = 'implemented' if new_status == 'completed' else 'reviewed'
            note_text = fb.admin_note or ''
            msg = f'Your feedback "{fb.subject[:60]}" has been {label}.'
            if note_text:
                msg += f' Note: {note_text[:200]}'
            create_notification(db, fb.user_id, request.web_user.id,
                                'feedback_update', target_type='feedback',
                                target_id=fb.id, message=msg, skip_self=False)
            db.commit()
    return JsonResponse({'ok': True})


@require_http_methods(['GET', 'POST'])
@add_web_user_context
def api_admin_feedback_settings(request):
    """Admin: get/set feedback routing (Fluxer channel + Discord webhook)."""
    from .models import WebSiteConfig
    if not (request.web_user and request.web_user.is_admin):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    with get_db_session() as db:
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            now = int(time.time())
            for key, val in [
                ('feedback_fluxer_channel_id', data.get('fluxer_channel_id', '').strip()),
                ('feedback_discord_webhook_url', data.get('discord_webhook_url', '').strip()),
            ]:
                cfg = db.query(WebSiteConfig).filter_by(key=key).first()
                if cfg:
                    cfg.value = val or None
                    cfg.updated_at = now
                else:
                    db.add(WebSiteConfig(key=key, value=val or None, updated_at=now))
            db.commit()
            return JsonResponse({'ok': True})

        fluxer_cfg = db.query(WebSiteConfig).filter_by(key='feedback_fluxer_channel_id').first()
        discord_cfg = db.query(WebSiteConfig).filter_by(key='feedback_discord_webhook_url').first()
        return JsonResponse({
            'fluxer_channel_id': fluxer_cfg.value or '' if fluxer_cfg else '',
            'discord_webhook_url': discord_cfg.value or '' if discord_cfg else '',
        })


@add_web_user_context
@require_http_methods(['GET'])
def page_feedback(request):
    """Public feedback submission page."""
    return render(request, 'questlog_web/feedback.html', {
        'web_user': request.web_user,
        'active_page': 'feedback',
    })


# =============================================================================
# SOULSLIKE HUB
# =============================================================================

@ensure_csrf_cookie
@add_web_user_context
def soulslike_hub(request):
    """SoulsLike hub landing page."""
    return render(request, 'questlog_web/soulslike_hub.html', {
        'web_user': request.web_user,
        'active_page': 'soulslike',
        'games_list': [
            'Elden Ring', 'Dark Souls III', 'Dark Souls II', 'Dark Souls',
            'Bloodborne', 'Sekiro', 'Lies of P', "Demon's Souls",
            'Lords of the Fallen', 'The First Berserker: Khazan',
        ],
    })


@ensure_csrf_cookie
@add_web_user_context
def soulslike_tracker(request):
    """QuestLog Mortality Tracker download & info page."""
    from app.db import get_db_session as _gds
    from sqlalchemy import text as _t
    import time as _time

    download_count = 0
    try:
        with _gds() as db:
            row = db.execute(_t(
                "SELECT COALESCE(SUM(count),0) FROM web_tracker_download_stats"
            )).scalar()
            download_count = int(row or 0)
    except Exception:
        pass  # table not yet created, show 0

    return render(request, 'questlog_web/soulslike_tracker.html', {
        'web_user': request.web_user,
        'active_page': 'soulslike_tracker',
        'download_count': download_count,
        'setup_steps': [
            'Create a free QuestLog account at questlog.casual-heroes.com/register/',
            'Download and run the listener for your OS',
            'Enter your QuestLog API token when prompted (Settings → API Token)',
            'Launch Elden Ring - deaths are tracked automatically via OCR',
            'Open your browser to manage runs, toggle bosses, and view your stats',
        ],
        'features_list': [
            'Auto death detection via OCR - no manual input needed',
            'Boss tracker for 200+ Elden Ring bosses',
            "Rage meter that escalates through Maiden's Grace to HOLLOW",
            'Deaths per hour stats and session tracking',
            'OBS overlay URL for streaming',
            'Multiple run support (vanilla, Reforged, NG+)',
            'Leaderboards coming soon',
            'LFG integration - find others in your NG cycle',
        ],
    })


@add_web_user_context
@require_http_methods(['POST'])
def api_tracker_download(request):
    """Record a download and serve the file URL."""
    import time as _time
    from app.db import get_db_session as _gds
    from sqlalchemy import text as _t

    platform = (request.POST.get('platform') or request.GET.get('platform') or 'unknown')[:20]
    ip = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', '')

    try:
        with _gds() as db:
            db.execute(_t("""
                INSERT INTO web_tracker_download_stats (platform, ip_hash, created_at)
                VALUES (:p, SHA2(:ip, 256), :ts)
            """), {'p': platform, 'ip': ip, 'ts': int(_time.time())})
            db.commit()
    except Exception:
        pass  # log and continue

    return JsonResponse({
        'ok': True,
        'url': '/static/downloads/QuestLogMortalityTracker.zip',
    })
