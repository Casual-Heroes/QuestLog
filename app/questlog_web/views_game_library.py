"""Game Library views - user game shelves, Play Together matching, nudges."""
import json
import time
import asyncio
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from app.db import get_db_session
from sqlalchemy import text
from .models import WebUserGame, WebUser, WebNotification, WebCommunity, WebSteamAchievement, WebSteamAchievementShowcase, WebFollow
from .helpers import web_login_required, add_web_user_context, api_login_required, safe_int

logger = logging.getLogger(__name__)

VALID_STATUSES = ('playing', 'played', 'backlog', 'play_together')
STATUS_LABELS = {
    'playing':      'Playing',
    'played':       'Played',
    'backlog':      'Backlog',
    'play_together': 'Play Together',
}

# How many members flagging the same game triggers a nudge
NUDGE_THRESHOLD = 3
NUDGE_WINDOW_DAYS = 7


# ---------------------------------------------------------------------------
# Helper: resolve cover art - Steam first, IGDB fallback
# ---------------------------------------------------------------------------

def _steam_cover(steam_app_id):
    if not steam_app_id:
        return None
    return f"https://shared.steamstatic.com/store_item_assets/steam/apps/{steam_app_id}/library_600x900.jpg"


def _serialize_game(g):
    return {
        'id':            g.id,
        'igdb_id':       g.igdb_id,
        'steam_app_id':  g.steam_app_id,
        'name':          g.name,
        'cover_url':     g.cover_url or _steam_cover(g.steam_app_id),
        'status':        g.status,
        'status_label':  STATUS_LABELS.get(g.status, g.status),
        'playtime_hours': g.playtime_hours,
        'platform':      g.platform,
        'is_favorite':   bool(g.is_favorite),
        'added_at':      g.added_at,
        'updated_at':    g.updated_at,
    }


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@add_web_user_context
@require_http_methods(["GET"])
def game_library_page(request):
    """My game library management page."""
    web_user = request.web_user
    return render(request, 'questlog_web/game_library.html', {
        'web_user':    web_user,
        'active_page': 'game_library',
        'status_labels': STATUS_LABELS,
    })


# ---------------------------------------------------------------------------
# API: get a user's library (own or public profile)
# ---------------------------------------------------------------------------

@add_web_user_context
@require_http_methods(["GET"])
def api_user_library(request, username=None):
    """GET /api/library/<username>/ or /api/library/ (own)."""
    viewer = request.web_user

    with get_db_session() as db:
        if username:
            profile_user = db.query(WebUser).filter_by(username=username).first()
            if not profile_user:
                return JsonResponse({'error': 'User not found.'}, status=404)
            target_id = profile_user.id
        else:
            if not viewer:
                return JsonResponse({'error': 'Login required.'}, status=401)
            target_id = viewer.id

        status_filter = request.GET.get('status', '')
        q = db.query(WebUserGame).filter_by(web_user_id=target_id)
        if status_filter in VALID_STATUSES:
            q = q.filter_by(status=status_filter)
        games = q.order_by(WebUserGame.updated_at.desc()).all()

        # Counts per status
        all_games = db.query(WebUserGame).filter_by(web_user_id=target_id).all()
        counts = {s: 0 for s in VALID_STATUSES}
        counts['total'] = 0
        counts['favorites'] = 0
        for g in all_games:
            counts['total'] += 1
            if g.status in counts:
                counts[g.status] += 1
            if g.is_favorite:
                counts['favorites'] += 1

        # In-common games (if viewer is different from target)
        in_common = []
        if viewer and viewer.id != target_id:
            viewer_game_keys = set()
            viewer_games = db.query(WebUserGame).filter_by(web_user_id=viewer.id).all()
            for vg in viewer_games:
                if vg.steam_app_id:
                    viewer_game_keys.add(('steam', vg.steam_app_id))
                if vg.igdb_id:
                    viewer_game_keys.add(('igdb', vg.igdb_id))
            for g in all_games:
                match = (g.steam_app_id and ('steam', g.steam_app_id) in viewer_game_keys) or \
                        (g.igdb_id and ('igdb', g.igdb_id) in viewer_game_keys)
                if match:
                    in_common.append(g.name)

        return JsonResponse({
            'success': True,
            'games':    [_serialize_game(g) for g in games],
            'counts':   counts,
            'in_common': in_common,
        })


# ---------------------------------------------------------------------------
# API: add a game
# ---------------------------------------------------------------------------

@ratelimit(key='ip', rate='60/h', method='POST', block=True)
@web_login_required
@add_web_user_context
@require_http_methods(["POST"])
def api_library_add(request):
    """POST /api/library/add/ - add a game to the library."""
    viewer = request.web_user
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    name = (data.get('name') or '').strip()[:200]
    if not name:
        return JsonResponse({'error': 'Game name is required.'}, status=400)

    status = data.get('status', 'playing')
    if status not in VALID_STATUSES:
        status = 'playing'

    igdb_id      = safe_int(data.get('igdb_id'), None)
    steam_app_id = safe_int(data.get('steam_app_id'), None)
    cover_url    = (data.get('cover_url') or '').strip()[:500] or None
    playtime     = data.get('playtime_hours')
    platform     = (data.get('platform') or '').strip()[:50] or None
    raw_modes    = data.get('game_modes')
    game_modes_json = None
    if isinstance(raw_modes, list):
        safe_modes = [str(m)[:50] for m in raw_modes if isinstance(m, str)][:10]
        if safe_modes:
            game_modes_json = json.dumps(safe_modes)
    now          = int(time.time())

    # Validate cover_url to trusted CDNs only (SSRF/XSS prevention)
    if cover_url:
        from urllib.parse import urlparse as _up
        _parsed = _up(cover_url)
        _allowed = (
            'images.igdb.com',
            'shared.cloudflare.steamstatic.com',
            'cdn.akamai.steamstatic.com',
            'shared.steamstatic.com',
            'shared.akamai.steamstatic.com',
            'cdn.cloudflare.steamstatic.com',
            'steamcdn-a.akamaihd.net',
        )
        if _parsed.scheme != 'https' or not any(_parsed.netloc.endswith(h) for h in _allowed):
            cover_url = None

    # Prefer IGDB cover if provided (exact URL), else fall back to Steam CDN
    if steam_app_id and not cover_url:
        cover_url = _steam_cover(steam_app_id)

    with get_db_session() as db:
        # Check for duplicate
        existing = db.query(WebUserGame).filter_by(web_user_id=viewer.id)
        if steam_app_id:
            existing = existing.filter_by(steam_app_id=steam_app_id)
        elif igdb_id:
            existing = existing.filter_by(igdb_id=igdb_id)
        else:
            existing = existing.filter_by(name=name)
        dup = existing.first()

        if dup:
            # Update status instead
            dup.status     = status
            dup.updated_at = now
            if playtime is not None:
                dup.playtime_hours = float(playtime)
            if game_modes_json and not dup.game_modes:
                dup.game_modes = game_modes_json
            db.commit()
            _maybe_trigger_nudge(dup.id, viewer.id, steam_app_id, igdb_id, name, status)
            return JsonResponse({'success': True, 'game': _serialize_game(dup), 'updated': True})

        game = WebUserGame(
            web_user_id   = viewer.id,
            igdb_id       = igdb_id,
            steam_app_id  = steam_app_id,
            name          = name,
            cover_url     = cover_url,
            status        = status,
            playtime_hours= float(playtime) if playtime is not None else None,
            platform      = platform,
            game_modes    = game_modes_json,
            added_at      = now,
            updated_at    = now,
        )
        db.add(game)
        db.commit()
        db.refresh(game)
        game_id = game.id
        game_data = _serialize_game(game)

    _maybe_trigger_nudge(game_id, viewer.id, steam_app_id, igdb_id, name, status)
    _emit_ticker(viewer.id, name, status, steam_app_id)
    return JsonResponse({'success': True, 'game': game_data, 'updated': False})


# ---------------------------------------------------------------------------
# API: update status
# ---------------------------------------------------------------------------

@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@web_login_required
@add_web_user_context
@require_http_methods(["POST"])
def api_library_update(request, game_id):
    """POST /api/library/<id>/update/ - change status."""
    viewer = request.web_user
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    status = data.get('status', '')
    if status not in VALID_STATUSES:
        return JsonResponse({'error': 'Invalid status.'}, status=400)

    with get_db_session() as db:
        game = db.query(WebUserGame).filter_by(id=game_id, web_user_id=viewer.id).first()
        if not game:
            return JsonResponse({'error': 'Game not found.'}, status=404)
        game.status     = status
        game.updated_at = int(time.time())
        db.commit()
        game_data = _serialize_game(game)
        steam_app_id = game.steam_app_id
        igdb_id      = game.igdb_id
        name         = game.name

    _maybe_trigger_nudge(game_id, viewer.id, steam_app_id, igdb_id, name, status)
    return JsonResponse({'success': True, 'game': game_data})


# ---------------------------------------------------------------------------
# API: remove a game
# ---------------------------------------------------------------------------

@ratelimit(key='ip', rate='60/h', method='POST', block=True)
@web_login_required
@add_web_user_context
@require_http_methods(["POST"])
def api_library_remove(request, game_id):
    """POST /api/library/<id>/remove/"""
    viewer = request.web_user
    with get_db_session() as db:
        game = db.query(WebUserGame).filter_by(id=game_id, web_user_id=viewer.id).first()
        if not game:
            return JsonResponse({'error': 'Game not found.'}, status=404)
        db.delete(game)
        db.commit()
    return JsonResponse({'success': True})


@add_web_user_context
@require_http_methods(["GET"])
def api_library_favorites(request, username=None):
    """GET /api/library/favorites/<username>/ or /api/library/favorites/ (own)
    Returns up to 10 favorite games for a user.
    """
    with get_db_session() as db:
        if username:
            profile_user = db.query(WebUser).filter_by(username=username).first()
            if not profile_user:
                return JsonResponse({'error': 'User not found.'}, status=404)
            target_id = profile_user.id
        else:
            if not request.web_user:
                return JsonResponse({'error': 'Login required.'}, status=401)
            target_id = request.web_user.id
        games = db.query(WebUserGame).filter_by(web_user_id=target_id, is_favorite=True)\
                  .order_by(WebUserGame.updated_at.desc()).limit(10).all()
        return JsonResponse({'success': True, 'favorites': [_serialize_game(g) for g in games]})


@web_login_required
@require_http_methods(["POST"])
def api_library_toggle_favorite(request, game_id):
    """POST /api/library/<id>/favorite/ - toggle is_favorite. Max 10 favorites per user."""
    viewer = request.web_user
    with get_db_session() as db:
        game = db.query(WebUserGame).filter_by(id=game_id, web_user_id=viewer.id).first()
        if not game:
            return JsonResponse({'error': 'Game not found.'}, status=404)
        if not game.is_favorite:
            fav_count = db.query(WebUserGame).filter_by(web_user_id=viewer.id, is_favorite=True).count()
            if fav_count >= 10:
                return JsonResponse({'error': 'Maximum 10 favorites allowed.', 'at_limit': True}, status=400)
        game.is_favorite = not game.is_favorite
        import time as _time
        game.updated_at = int(_time.time())
        db.commit()
        return JsonResponse({'success': True, 'is_favorite': game.is_favorite})


# ---------------------------------------------------------------------------
# API: who wants to play together for a game
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def api_play_together(request):
    """GET /api/library/play-together/?steam_app_id=X&igdb_id=Y&name=Z
    Returns all members who flagged this game as play_together.
    Public endpoint.
    """
    steam_app_id = safe_int(request.GET.get('steam_app_id'), None)
    igdb_id      = safe_int(request.GET.get('igdb_id'), None)
    name         = (request.GET.get('name') or '').strip()[:200]

    with get_db_session() as db:
        q = db.query(WebUserGame).filter_by(status='play_together')
        if steam_app_id:
            q = q.filter_by(steam_app_id=steam_app_id)
        elif igdb_id:
            q = q.filter_by(igdb_id=igdb_id)
        elif name:
            q = q.filter(WebUserGame.name.ilike(f'%{name}%'))
        else:
            return JsonResponse({'error': 'Provide steam_app_id, igdb_id, or name.'}, status=400)

        entries = q.limit(50).all()
        user_ids = [e.web_user_id for e in entries]
        if not user_ids:
            return JsonResponse({'success': True, 'members': [], 'count': 0})

        users = {u.id: u for u in db.query(WebUser).filter(
            WebUser.id.in_(user_ids),
            WebUser.is_banned == False,
            WebUser.is_hidden == False,
        ).all()}

        # Check mutual follow + allow_messages for the current viewer
        current_uid = request.web_user.id if request.web_user else None
        mutual_ids = set()
        if current_uid and user_ids:
            i_follow = {r.followee_id for r in db.query(WebFollow.followee_id).filter(
                WebFollow.follower_id == current_uid,
                WebFollow.followee_id.in_(user_ids),
            ).all()}
            they_follow = {r.follower_id for r in db.query(WebFollow.follower_id).filter(
                WebFollow.follower_id.in_(user_ids),
                WebFollow.followee_id == current_uid,
            ).all()}
            mutual_ids = i_follow & they_follow

        members = []
        for e in entries:
            u = users.get(e.web_user_id)
            if not u:
                continue
            is_mutual = u.id in mutual_ids
            can_dm = bool(current_uid and current_uid != u.id and is_mutual and u.allow_messages)
            members.append({
                'user_id':        u.id,
                'username':       u.username,
                'display_name':   u.display_name or u.username,
                'avatar_url':     u.avatar_url,
                'playtime_hours': e.playtime_hours,
                'added_at':       e.added_at,
                'can_dm':         can_dm,
            })

    return JsonResponse({'success': True, 'members': members, 'count': len(members)})


# ---------------------------------------------------------------------------
# API: community stats for a game (for game pages)
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def api_game_community_stats(request):
    """GET /api/library/game-stats/?steam_app_id=X&igdb_id=Y&name=Z
    Returns counts per status for a game across all CH members.
    """
    steam_app_id = safe_int(request.GET.get('steam_app_id'), None)
    igdb_id      = safe_int(request.GET.get('igdb_id'), None)
    name         = (request.GET.get('name') or '').strip()[:200]

    with get_db_session() as db:
        def _count(status):
            q = db.query(WebUserGame).filter_by(status=status)
            if steam_app_id:
                q = q.filter_by(steam_app_id=steam_app_id)
            elif igdb_id:
                q = q.filter_by(igdb_id=igdb_id)
            elif name:
                q = q.filter(WebUserGame.name.ilike(f'%{name}%'))
            return q.count()

        playing      = _count('playing')
        played       = _count('played')
        backlog      = _count('backlog')
        play_together = _count('play_together')

        # Active LFG groups for this game
        lfg_count = 0
        if name:
            row = db.execute(text(
                "SELECT COUNT(*) FROM web_lfg_groups "
                "WHERE status='open' AND LOWER(game_name) LIKE :name"
            ), {'name': f'%{name.lower()}%'}).scalar()
            lfg_count = row or 0

    return JsonResponse({
        'success': True,
        'playing': playing,
        'played':  played,
        'backlog': backlog,
        'play_together': play_together,
        'total': playing + played + backlog + play_together,
        'lfg_count': lfg_count,
    })


# ---------------------------------------------------------------------------
# API: find players by game (discover page)
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def api_find_players(request):
    """GET /api/library/find-players/?steam_app_id=X&igdb_id=Y&name=Z&play_together_only=1"""
    steam_app_id     = safe_int(request.GET.get('steam_app_id'), None)
    igdb_id          = safe_int(request.GET.get('igdb_id'), None)
    name             = (request.GET.get('name') or '').strip()
    play_together_only = request.GET.get('play_together_only') == '1'

    if not steam_app_id and not igdb_id and not name:
        return JsonResponse({'error': 'Provide steam_app_id, igdb_id, or name.'}, status=400)

    with get_db_session() as db:
        q = db.query(WebUserGame)
        if steam_app_id:
            q = q.filter_by(steam_app_id=steam_app_id)
        elif igdb_id:
            q = q.filter_by(igdb_id=igdb_id)
        else:
            q = q.filter(WebUserGame.name.ilike(f'%{name}%'))
        if play_together_only:
            q = q.filter_by(status='play_together')
        else:
            q = q.filter(WebUserGame.status.in_(['playing', 'play_together']))

        entries = q.limit(100).all()
        user_ids = list({e.web_user_id for e in entries})
        if not user_ids:
            return JsonResponse({'success': True, 'players': []})

        users = {u.id: u for u in db.query(WebUser).filter(
            WebUser.id.in_(user_ids),
            WebUser.is_banned == False,
            WebUser.is_hidden == False,
        ).all()}

        # Build one entry per user (take most relevant status)
        user_entries = {}
        for e in entries:
            uid = e.web_user_id
            if uid not in user_entries or e.status == 'play_together':
                user_entries[uid] = e

        players = []
        for uid, e in user_entries.items():
            u = users.get(uid)
            if not u:
                continue
            players.append({
                'user_id':       u.id,
                'username':      u.username,
                'display_name':  u.display_name or u.username,
                'avatar_url':    u.avatar_url,
                'status':        e.status,
                'status_label':  STATUS_LABELS.get(e.status, e.status),
                'playtime_hours': e.playtime_hours,
            })

        # Sort: play_together first, then by playtime desc
        players.sort(key=lambda p: (0 if p['status'] == 'play_together' else 1, -(p['playtime_hours'] or 0)))

    return JsonResponse({'success': True, 'players': players})


# ---------------------------------------------------------------------------
# API: nudge opportunities (for discover page)
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
def api_nudge_opportunities(request):
    """GET /api/library/nudges/ - games where 3+ members flagged play_together recently."""
    window = int(time.time()) - (NUDGE_WINDOW_DAYS * 86400)
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT
                COALESCE(steam_app_id, igdb_id) as game_key,
                name,
                MAX(steam_app_id) as steam_app_id,
                MAX(igdb_id) as igdb_id,
                MAX(cover_url) as cover_url,
                COUNT(DISTINCT web_user_id) as member_count,
                GROUP_CONCAT(DISTINCT web_user_id ORDER BY updated_at DESC SEPARATOR ',') as user_ids
            FROM web_user_games
            WHERE status = 'play_together'
              AND updated_at >= :window
            GROUP BY COALESCE(steam_app_id, igdb_id), name
            HAVING COUNT(DISTINCT web_user_id) >= :threshold
            ORDER BY member_count DESC
            LIMIT 10
        """), {'window': window, 'threshold': NUDGE_THRESHOLD}).fetchall()

        nudges = []
        for row in rows:
            game_name    = row[1]
            steam_app_id = row[2]
            igdb_id      = row[3]
            cover_url    = row[4] or _steam_cover(steam_app_id)
            member_count = row[5]
            user_id_list = [int(x) for x in (row[6] or '').split(',') if x][:5]

            users = db.query(WebUser).filter(
                WebUser.id.in_(user_id_list),
                WebUser.is_banned == False,
                WebUser.is_hidden == False,
            ).all()

            avatars = [{'username': u.username, 'display_name': u.display_name or u.username,
                        'avatar_url': u.avatar_url} for u in users]

            nudges.append({
                'name':         game_name,
                'steam_app_id': steam_app_id,
                'igdb_id':      igdb_id,
                'cover_url':    cover_url,
                'member_count': member_count,
                'avatars':      avatars,
            })

    return JsonResponse({'success': True, 'nudges': nudges})


# ---------------------------------------------------------------------------
# Internal: nudge trigger
# ---------------------------------------------------------------------------

def _maybe_trigger_nudge(game_id, user_id, steam_app_id, igdb_id, name, status):
    """If play_together threshold just crossed, queue Fluxer DM to all flaggers."""
    if status != 'play_together':
        return
    try:
        window = int(time.time()) - (NUDGE_WINDOW_DAYS * 86400)
        with get_db_session() as db:
            q = db.query(WebUserGame).filter_by(status='play_together')
            if steam_app_id:
                q = q.filter_by(steam_app_id=steam_app_id)
            elif igdb_id:
                q = q.filter_by(igdb_id=igdb_id)
            else:
                q = q.filter(WebUserGame.name.ilike(f'%{name}%'))
            entries = q.filter(WebUserGame.updated_at >= window).all()
            count = len({e.web_user_id for e in entries})

            if count == NUDGE_THRESHOLD:
                # Exactly hit threshold - send bell notifications to all flaggers
                user_ids = list({e.web_user_id for e in entries})
                now = int(time.time())
                for uid in user_ids:
                    notif = WebNotification(
                        user_id=uid,
                        actor_id=None,
                        notification_type='play_together_nudge',
                        target_type='game',
                        target_id=0,
                        message=f"{count} CH members want to play {name} together - create a group!",
                        is_read=False,
                        created_at=now,
                    )
                    db.add(notif)
                db.commit()

                # Queue Fluxer notification
                try:
                    from .fluxer_webhooks import _queue_notification, BRAND_COLOR
                    cover = _steam_cover(steam_app_id) or ''
                    embed = {
                        'title': '\U0001f3ae Play Together Opportunity',
                        'description': (
                            f"**{count} members** want to play **{name}** together!\n\n"
                            f"[Create a group now](https://questlog.casual-heroes.com/lfg/create/)"
                        ),
                        'thumbnail': {'url': cover} if cover else None,
                        'footer': 'QuestLog - Game Library',
                    }
                    _queue_notification('play_together_nudge', embed, BRAND_COLOR)
                except Exception as e:
                    logger.error(f"play_together nudge Fluxer notify failed: {e}")
    except Exception as e:
        logger.error(f"_maybe_trigger_nudge failed: {e}")


@add_web_user_context
@require_http_methods(["GET"])
def api_library_game_owners(request):
    """GET /api/library/game-owners/?names=Game1|Game2|...
    Returns how many CH members have each game in their library (any status).
    Used for the "X others own this" badge on the library shelf.
    Max 20 game names. Adult games are excluded server-side.
    """
    raw = request.GET.get('names', '').strip()
    if not raw:
        return JsonResponse({'ok': False, 'counts': {}})

    ADULT_TAGS = {'sexual content', 'adult only sexual content',
                  'frequent nudity or sexual content', 'hentai', 'eroge',
                  'explicit sexual content'}

    names = [n.strip() for n in raw.split('|') if n.strip()][:20]
    if not names:
        return JsonResponse({'ok': True, 'counts': {}})

    current_uid = request.web_user.id if request.web_user else None

    with get_db_session() as db:
        # Get adult steam app IDs to exclude
        adult_rows = db.execute(text(
            "SELECT DISTINCT app_id FROM web_steam_app_tags "
            "WHERE LOWER(tag_name) IN :tags AND app_id IS NOT NULL"
        ), {'tags': tuple(ADULT_TAGS)}).fetchall()
        adult_ids = {r[0] for r in adult_rows}

        counts = {}
        for name in names:
            q = db.query(WebUserGame).join(
                WebUser, WebUser.id == WebUserGame.web_user_id
            ).filter(
                WebUserGame.name.ilike(name),
                WebUser.is_banned == False,
                WebUser.is_hidden == False,
            )
            if current_uid:
                q = q.filter(WebUserGame.web_user_id != current_uid)
            if adult_ids:
                q = q.filter(
                    (WebUserGame.steam_app_id == None) |
                    (~WebUserGame.steam_app_id.in_(adult_ids))
                )
            counts[name] = q.count()

    return JsonResponse({'ok': True, 'counts': counts})


@require_http_methods(["GET"])
def api_library_game_communities(request):
    """GET /api/library/game-communities/?name=<game>
    Returns communities that have tagged this game in their games list.
    Public endpoint. Only returns discoverable communities.
    """
    name = (request.GET.get('name') or '').strip()[:200]
    if not name:
        return JsonResponse({'ok': False, 'communities': []})

    name_lower = name.lower()

    with get_db_session() as db:
        communities = db.query(WebCommunity).filter(
            WebCommunity.allow_discovery == True,
            WebCommunity.games != None,
            WebCommunity.games != '[]',
        ).all()

        matched = []
        for c in communities:
            try:
                games_list = json.loads(c.games or '[]')
            except (ValueError, TypeError):
                continue
            if any(name_lower in g.lower() for g in games_list if isinstance(g, str)):
                matched.append({
                    'id': c.id,
                    'name': c.name,
                    'short_description': c.short_description or '',
                    'icon_url': c.icon_url or '',
                    'platform': c.platform.value if c.platform else 'other',
                    'member_count': c.member_count or 0,
                    'activity_level': c.activity_level or 'unknown',
                    'invite_url': c.invite_url if c.allow_joins else None,
                })
        matched = matched[:20]

    return JsonResponse({'ok': True, 'communities': matched})


# ---------------------------------------------------------------------------
# API: sync Steam library into web_user_games
# ---------------------------------------------------------------------------

@ratelimit(key='ip', rate='5/h', method='POST', block=True)
@web_login_required
@add_web_user_context
@require_http_methods(["POST"])
def api_library_sync_steam(request):
    """POST /api/library/sync-steam/
    Pulls all owned Steam games and inserts any not already in the user's library (status=backlog).
    Requires Steam linked and profile public.
    """
    from .helpers import STEAM_API_KEY
    from .steam_auth import get_steam_owned_games

    viewer = request.web_user
    if not viewer.steam_id:
        return JsonResponse({'ok': False, 'error': 'No Steam account linked. Connect Steam first.'}, status=400)

    games = get_steam_owned_games(viewer.steam_id, STEAM_API_KEY, include_free=True)
    if games is None:
        return JsonResponse({'ok': False, 'error': 'Could not fetch Steam library. Make sure your Steam profile is set to Public in Steam privacy settings.'}, status=502)

    if not games:
        return JsonResponse({'ok': True, 'added': 0, 'skipped': 0})

    added = 0
    skipped = 0
    now = int(time.time())

    with get_db_session() as db:
        existing_app_ids = {
            r[0] for r in db.execute(
                text('SELECT steam_app_id FROM web_user_games WHERE web_user_id = :uid AND steam_app_id IS NOT NULL'),
                {'uid': viewer.id}
            ).fetchall()
        }

        for g in games:
            app_id = g.get('app_id')
            name = (g.get('name') or '').strip()[:200]
            if not app_id or not name:
                skipped += 1
                continue
            if app_id in existing_app_ids:
                skipped += 1
                continue

            playtime = g.get('playtime_hours')
            cover_url = _steam_cover(app_id)
            status = 'backlog'

            game = WebUserGame(
                web_user_id=viewer.id,
                steam_app_id=app_id,
                name=name,
                cover_url=cover_url,
                status=status,
                playtime_hours=float(playtime) if playtime else None,
                platform='PC',
                added_at=now,
                updated_at=now,
            )
            db.add(game)
            existing_app_ids.add(app_id)
            added += 1

        db.commit()

    return JsonResponse({'ok': True, 'added': added, 'skipped': skipped})


# ---------------------------------------------------------------------------
# API: sync Steam achievements for a user
# ---------------------------------------------------------------------------

@api_login_required
@ratelimit(key='ip', rate='10/h', method='POST', block=True)
@require_http_methods(["POST"])
def api_steam_sync_achievements(request):
    """POST /api/steam/sync-achievements/
    For each game with achievements in the user's Steam library, fetches unlocked
    achievements and upserts into web_steam_achievements.
    Can be slow for large libraries - runs synchronously but returns early on timeout.
    """
    import requests as http_requests
    from .helpers import STEAM_API_KEY
    from .steam_auth import get_steam_owned_games

    viewer = request.web_user
    if not viewer.steam_id:
        return JsonResponse({'ok': False, 'error': 'No Steam account linked.'}, status=400)

    STEAM_API = 'https://api.steampowered.com'
    now = int(time.time())
    total_synced = 0
    total_new = 0
    games_processed = 0
    start = time.time()
    MAX_SECONDS = 50  # leave 10s buffer for gunicorn 60s timeout

    # Fetch game list from Steam
    games = get_steam_owned_games(viewer.steam_id, STEAM_API_KEY, include_free=True)
    if not games:
        return JsonResponse({'ok': False, 'error': 'Could not fetch Steam library or library is empty.'}, status=502)

    with get_db_session() as db:
        for g in games:
            if time.time() - start > MAX_SECONDS:
                break

            app_id = g.get('app_id')
            game_name = (g.get('name') or '').strip()[:200]
            if not app_id:
                continue

            try:
                resp = http_requests.get(
                    f'{STEAM_API}/ISteamUserStats/GetPlayerAchievements/v1/',
                    params={
                        'key': STEAM_API_KEY,
                        'steamid': viewer.steam_id,
                        'appid': app_id,
                        'l': 'english',
                    },
                    timeout=5,
                )
                data = resp.json().get('playerstats', {})
                if not data.get('success'):
                    continue
                achievements = data.get('achievements', [])
            except Exception:
                continue

            # Fetch achievement schema for icons (GetSchemaForGame returns icon hash per achievement)
            icon_map = {}
            try:
                schema_resp = http_requests.get(
                    f'{STEAM_API}/ISteamUserStats/GetSchemaForGame/v2/',
                    params={'key': STEAM_API_KEY, 'appid': app_id, 'l': 'english'},
                    timeout=5,
                )
                schema_achs = (
                    schema_resp.json()
                    .get('game', {})
                    .get('availableGameStats', {})
                    .get('achievements', [])
                )
                for sa in schema_achs:
                    name_key = (sa.get('name') or '').strip()
                    icon = (sa.get('icon') or '').strip()
                    if name_key and icon:
                        icon_map[name_key] = icon
            except Exception:
                pass

            for ach in achievements:
                if not ach.get('achieved'):
                    continue
                api_name = (ach.get('apiname') or '').strip()[:200]
                if not api_name:
                    continue
                display_name = (ach.get('name') or api_name).strip()[:200]
                description = (ach.get('description') or '').strip()[:500] or None
                # Filter adult/sexual content
                _combined = f"{display_name} {description or ''}".lower()
                _adult_kw = ('sex', 'nude', 'naked', 'porn', 'hentai', 'erotic', 'adult only', 'nsfw', 'xxx')
                if any(kw in _combined for kw in _adult_kw):
                    continue
                unlocked_at = ach.get('unlocktime') or None
                icon_url = icon_map.get(api_name) or None

                existing = db.query(WebSteamAchievement).filter_by(
                    web_user_id=viewer.id, app_id=app_id, api_name=api_name
                ).first()

                if existing:
                    existing.synced_at = now
                    if icon_url and not existing.icon_url:
                        existing.icon_url = icon_url
                    total_synced += 1
                else:
                    db.add(WebSteamAchievement(
                        web_user_id=viewer.id,
                        app_id=app_id,
                        game_name=game_name,
                        api_name=api_name,
                        display_name=display_name,
                        description=description,
                        icon_url=icon_url,
                        unlocked_at=unlocked_at,
                        synced_at=now,
                    ))
                    total_new += 1

            games_processed += 1
            # Commit per game to avoid lock timeout on large libraries
            db.commit()

        # Update steam_achievements_total on the user
        total = db.query(WebSteamAchievement).filter_by(web_user_id=viewer.id).count()
        db.execute(
            text('UPDATE web_users SET steam_achievements_total = :n WHERE id = :uid'),
            {'n': total, 'uid': viewer.id}
        )
        db.commit()

    return JsonResponse({
        'ok': True,
        'games_processed': games_processed,
        'new': total_new,
        'updated': total_synced,
        'total': total,
    })


# ---------------------------------------------------------------------------
# API: get synced achievements (for showcase picker)
# ---------------------------------------------------------------------------

@api_login_required
@require_http_methods(["GET"])
def api_steam_achievements_list(request):
    """GET /api/steam/achievements/?game_name=X&games[]=X&games[]=Y&page=N
    Returns paginated list of synced achievements for the logged-in user.
    """
    viewer = request.web_user
    # Support single game_name= or multiple games[]=
    game_filter = (request.GET.get('game_name') or '').strip()[:200]
    games_filter = [g.strip()[:200] for g in request.GET.getlist('games[]') if g.strip()]
    page = max(1, safe_int(request.GET.get('page'), 1))
    per_page = 48

    with get_db_session() as db:
        q = db.query(WebSteamAchievement).filter_by(web_user_id=viewer.id)
        if games_filter:
            q = q.filter(WebSteamAchievement.game_name.in_(games_filter))
        elif game_filter:
            q = q.filter(WebSteamAchievement.game_name == game_filter)
        total = q.count()
        achievements = q.order_by(
            WebSteamAchievement.game_name, WebSteamAchievement.display_name
        ).offset((page - 1) * per_page).limit(per_page).all()

        # Get pinned IDs for this user
        pinned_ids = {
            r.achievement_id
            for r in db.query(WebSteamAchievementShowcase).filter_by(web_user_id=viewer.id).all()
        }

        # Distinct game names for filter dropdown
        game_names = [
            r[0] for r in db.execute(
                text('SELECT DISTINCT game_name FROM web_steam_achievements WHERE web_user_id = :uid ORDER BY game_name'),
                {'uid': viewer.id}
            ).fetchall()
        ]

    return JsonResponse({
        'ok': True,
        'total': total,
        'page': page,
        'per_page': per_page,
        'achievements': [
            {
                'id': a.id,
                'app_id': a.app_id,
                'game_name': a.game_name,
                'api_name': a.api_name,
                'display_name': a.display_name,
                'description': a.description or '',
                'icon_url': a.icon_url or '',
                'unlocked_at': a.unlocked_at,
                'pinned': a.id in pinned_ids,
            }
            for a in achievements
        ],
        'game_names': game_names,
        'pinned_count': len(pinned_ids),
    })


# ---------------------------------------------------------------------------
# API: get showcase (own or public)
# ---------------------------------------------------------------------------

@add_web_user_context
@require_http_methods(["GET"])
def api_steam_showcase_get(request, username=None):
    """GET /api/steam/showcase/ or /api/steam/showcase/<username>/
    Returns pinned achievements for a user (public).
    """
    with get_db_session() as db:
        if username:
            profile_user = db.query(WebUser).filter_by(username=username).first()
            if not profile_user:
                return JsonResponse({'error': 'User not found.'}, status=404)
            target_id = profile_user.id
        else:
            if not request.web_user:
                return JsonResponse({'error': 'Login required.'}, status=401)
            target_id = request.web_user.id

        rows = db.query(WebSteamAchievementShowcase, WebSteamAchievement).join(
            WebSteamAchievement, WebSteamAchievementShowcase.achievement_id == WebSteamAchievement.id
        ).filter(
            WebSteamAchievementShowcase.web_user_id == target_id
        ).order_by(WebSteamAchievementShowcase.sort_order).all()

    return JsonResponse({
        'ok': True,
        'showcase': [
            {
                'id': s.id,
                'achievement_id': a.id,
                'app_id': a.app_id,
                'game_name': a.game_name,
                'display_name': a.display_name,
                'description': a.description or '',
                'icon_url': a.icon_url or '',
                'unlocked_at': a.unlocked_at,
                'sort_order': s.sort_order,
            }
            for s, a in rows
        ],
    })


# ---------------------------------------------------------------------------
# API: save showcase (pin/unpin up to 6)
# ---------------------------------------------------------------------------

@api_login_required
@require_http_methods(["POST"])
def api_steam_showcase_save(request):
    """POST /api/steam/showcase/save/
    Body: {"achievement_ids": [1,2,3,...]} - ordered list of up to 10 achievement IDs.
    Replaces existing showcase entirely.
    """
    viewer = request.web_user
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON.'}, status=400)

    raw_ids = data.get('achievement_ids', [])
    if not isinstance(raw_ids, list):
        return JsonResponse({'error': 'achievement_ids must be a list.'}, status=400)

    # Validate: max 10, positive ints
    ach_ids = []
    for v in raw_ids[:10]:
        try:
            ach_ids.append(int(v))
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid achievement ID.'}, status=400)

    now = int(time.time())

    with get_db_session() as db:
        # Verify all IDs belong to this user
        if ach_ids:
            owned = {
                r.id for r in db.query(WebSteamAchievement).filter(
                    WebSteamAchievement.id.in_(ach_ids),
                    WebSteamAchievement.web_user_id == viewer.id,
                ).all()
            }
            invalid = [i for i in ach_ids if i not in owned]
            if invalid:
                return JsonResponse({'error': 'One or more achievements not found.'}, status=400)

        # Delete existing showcase
        db.query(WebSteamAchievementShowcase).filter_by(web_user_id=viewer.id).delete()

        # Insert new
        for order, ach_id in enumerate(ach_ids):
            db.add(WebSteamAchievementShowcase(
                web_user_id=viewer.id,
                achievement_id=ach_id,
                sort_order=order,
                pinned_at=now,
            ))
        db.commit()

    return JsonResponse({'ok': True, 'pinned': len(ach_ids)})


_cover_fallback_cache = {}  # simple in-memory cache: name -> url


@ratelimit(key='ip', rate='60/h', method='GET', block=True)
@require_http_methods(["GET"])
def api_cover_fallback(request):
    """GET /api/library/cover-fallback/?name=X&sid=Y
    Called by the frontend when a stored cover URL 404s.
    Fetches from IGDB, caches in memory, updates the DB row, returns redirect to cover URL.
    """
    from django.http import HttpResponseRedirect
    name = (request.GET.get('name') or '').strip()[:200]
    steam_app_id = safe_int(request.GET.get('sid'), None)
    if not name:
        return JsonResponse({'error': 'name required'}, status=400)

    cache_key = name.lower()
    if cache_key in _cover_fallback_cache:
        url = _cover_fallback_cache[cache_key]
        if url:
            return HttpResponseRedirect(url)
        return JsonResponse({'error': 'no cover'}, status=404)

    url = None
    try:
        loop = asyncio.new_event_loop()
        from app.utils.igdb import search_games as _igdb_search
        results = loop.run_until_complete(_igdb_search(name, limit=1))
        loop.close()
        if results and results[0].cover_url:
            url = results[0].cover_url
    except Exception:
        pass

    _cover_fallback_cache[cache_key] = url

    if url:
        # Backfill the DB so this game won't need a proxy call next time
        try:
            with get_db_session() as db:
                db.execute(text(
                    "UPDATE web_user_games SET cover_url = :url WHERE LOWER(name) = :name AND (cover_url IS NULL OR cover_url NOT LIKE 'https://images.igdb.com%')"
                ), {'url': url, 'name': cache_key})
                db.commit()
        except Exception:
            pass
        return HttpResponseRedirect(url)

    return JsonResponse({'error': 'no cover found'}, status=404)


def _emit_ticker(user_id, name, status, steam_app_id):
    """Emit a ticker event when someone adds a play_together game."""
    if status != 'play_together':
        return
    try:
        with get_db_session() as db:
            db.execute(text("""
                INSERT INTO web_ticker_events (user_id, event_type, game_name, steam_app_id, created_at)
                VALUES (:uid, 'game_added', :name, :appid, :now)
            """), {'uid': user_id, 'name': name, 'appid': steam_app_id, 'now': int(time.time())})
            db.commit()
    except Exception:
        pass  # ticker table may not exist yet - non-critical
