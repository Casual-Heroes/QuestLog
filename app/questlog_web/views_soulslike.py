"""
QuestLog SoulsLike - Collection sessions, death tracking, overlays.
All session endpoints use the session token as auth - no login required for POSTing.
"""
import json
import time
import secrets
import logging

from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt

from app.db import get_db_session
from sqlalchemy import text

from django_ratelimit.decorators import ratelimit
from .helpers import add_web_user_context, web_login_required, safe_int, sanitize_text

logger = logging.getLogger(__name__)

# Rage tier constants (matching EldenTracker)
RAGE_TIER_ENEMY       = 'enemy'
RAGE_TIER_GREAT_ENEMY = 'great_enemy'
RAGE_TIER_LEGEND      = 'legend'
RAGE_TIER_DEMIGOD     = 'demigod'
RAGE_TIER_GOD         = 'god'

RAGE_DECAY = {
    RAGE_TIER_ENEMY:       25,
    RAGE_TIER_GREAT_ENEMY: 50,
    RAGE_TIER_LEGEND:      100,
    RAGE_TIER_DEMIGOD:     125,
    RAGE_TIER_GOD:         100,  # Full reset handled separately
}

# ── Hardcore mode point values ────────────────────────────────────────────────
HC_POINTS = {
    RAGE_TIER_ENEMY:       10,   # mini-boss / field boss
    RAGE_TIER_GREAT_ENEMY: 25,   # great enemy
    RAGE_TIER_LEGEND:      50,   # legend
    RAGE_TIER_DEMIGOD:     100,  # demigod
    RAGE_TIER_GOD:         250,  # god / final boss
}
HC_ITEM_POINTS        = 5    # per item collected
HC_COMPLETION_MULT    = 2.0  # score multiplier for deathless full clear

def _rage_name(pct):
    if pct >= 100: return 'HOLLOW'
    if pct >= 75:  return 'Cursed'
    if pct >= 50:  return 'Frenzied'
    if pct >= 25:  return 'Staggered'
    return "Maiden's Grace"

def _fmt_time(seconds):
    seconds = int(seconds or 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f'{h:02d}:{m:02d}:{s:02d}'


# ── Session creation ──────────────────────────────────────────────────────────

@web_login_required
@require_http_methods(['POST'])
def api_sl_session_create(request):
    """
    POST /api/soulslike/session/create/
    Web session auth + CSRF. For desktop app use /api/soulslike/desktop/session/create/ instead.
    """
    from .helpers import require_verified
    gate = require_verified(request)
    if gate: return gate
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id      = request.web_user.id
    raw_game     = str(data.get('game', 'elden_ring'))[:32]
    build_name   = sanitize_text(str(data.get('build_name', 'My Build'))[:200])
    spoiler_mode = str(data.get('spoiler_mode', 'region'))[:16]
    game_mode    = str(data.get('game_mode', 'vanilla'))[:32]
    if spoiler_mode not in ('blind', 'region', 'full'):
        spoiler_mode = 'region'
    # Normalize: boss registry uses game='elden_ring' with game_mode='err' for ERR.
    # If the builder sends game='err', translate to game='elden_ring', game_mode='err'.
    if raw_game == 'err':
        game = 'elden_ring'
        game_mode = 'err'
    else:
        game = raw_game
        if game_mode not in ('vanilla', 'err'):
            game_mode = 'vanilla'
    # All runs are unified - one type with bosses + items + deaths
    session_type = 'run'
    timing_mode  = str(data.get('timing_mode', 'listener'))[:10]
    if timing_mode not in ('listener', 'manual'):
        timing_mode = 'listener'
    is_hardcore  = 1 if data.get('is_hardcore') else 0
    items = data.get('items', [])
    now   = int(time.time())
    token = secrets.token_urlsafe(16)
    build_id = safe_int(data.get('build_id'), None)

    with get_db_session() as db:
        # Inherit is_public from the build if one was linked
        is_public = 0
        if build_id:
            pub_row = db.execute(text(
                "SELECT is_public FROM sl_er_builds WHERE id=:bid AND user_id=:uid "
                "UNION SELECT is_public FROM sl_err_builds WHERE id=:bid AND user_id=:uid LIMIT 1"
            ), {'bid': build_id, 'uid': user_id}).fetchone()
            if pub_row:
                is_public = 1 if pub_row[0] else 0

        db.execute(text("""
            INSERT INTO sl_collection_sessions
                (build_id, game, user_id, spoiler_mode, build_name, started_at,
                 session_type, game_mode, timing_mode, is_hardcore, is_public,
                 session_start_ts, current_life_start,
                 total_survival_sec, longest_life_sec, rage_pct, rage_name,
                 hollow_streak, time_in_hollow_sec)
            VALUES (:bid, :game, :uid, :sm, :bn, :ts,
                    :stype, :gmode, :tmode, :hc, :pub, :ts, :ts,
                    0, 0, 0, 'Maiden''s Grace',
                    0, 0)
        """), {
            'bid': build_id,
            'game': game, 'uid': user_id,
            'sm': spoiler_mode, 'bn': build_name, 'ts': now,
            'stype': session_type, 'gmode': game_mode, 'tmode': timing_mode,
            'hc': is_hardcore, 'pub': is_public,
        })
        session_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()

        db.execute(text(
            "UPDATE sl_collection_sessions SET session_token=:tok WHERE id=:sid"
        ), {'tok': token, 'sid': session_id})

        # Always seed boss list from registry for this game/mode
        boss_rows = db.execute(text(
            "SELECT boss_key, boss_name, location, region, tier FROM sl_boss_registry "
            "WHERE game=:g AND game_mode=:gm ORDER BY sort_order"
        ), {'g': game, 'gm': game_mode}).fetchall()
        for b in boss_rows:
            db.execute(text("""
                INSERT IGNORE INTO sl_session_bosses
                    (session_id, boss_key, boss_name, location, region, tier, game, game_mode)
                VALUES (:sid, :key, :name, :loc, :region, :tier, :g, :gm)
            """), {
                'sid': session_id, 'key': b[0], 'name': b[1],
                'loc': b[2], 'region': b[3], 'tier': b[4],
                'g': game, 'gm': game_mode,
            })

        # Always seed build items checklist (weapons, armor, spells, etc.)
        for item in items[:200]:
            itype = str(item.get('item_type', 'weapon'))[:16]
            iid   = safe_int(item.get('item_id'), 0) or 0  # 0 for items without DB ids
            iname = sanitize_text(str(item.get('item_name', ''))[:200])
            hint  = sanitize_text(str(item.get('location_hint', ''))[:300])
            if not iname:
                continue
            db.execute(text("""
                INSERT INTO sl_collection_item_status
                    (session_id, item_type, item_id, item_name, location_hint,
                     is_collected, collection_method)
                VALUES (:sid, :itype, :iid, :iname, :hint, 0, NULL)
            """), {'sid': session_id, 'itype': itype, 'iid': iid,
                   'iname': iname, 'hint': hint})

        logger.info("sl_session_create uid=%s game=%s/%s session_id=%s bosses=%d items=%d",
                    user_id, game, game_mode, session_id, len(boss_rows), len(items))
        db.commit()
    # Use request.build_absolute_uri so the host is always derived from the actual request,
    # never from a hardcoded string that could diverge from the real host.
    def _url(path):
        return request.build_absolute_uri(path)

    return JsonResponse({
        'ok': True,
        'session_id':   session_id,
        'session_type': session_type,
        'token':        token,
        'overlay_combined':   _url(f'/soulslike/overlay/{token}/combined/'),
        'overlay_collection': _url(f'/soulslike/overlay/{token}/collection/'),
        'overlay_mortality':  _url(f'/soulslike/overlay/{token}/mortality/'),
        'overlay_deaths':     _url(f'/soulslike/overlay/{token}/deaths/'),
        'overlay_hollow':     _url(f'/soulslike/overlay/{token}/hollow/'),
        'manage_url':         _url(f'/soulslike/runs/{token}/'),
    })


# ── Item collect (OCR app or web click) ──────────────────────────────────────

@csrf_exempt
@ratelimit(key='ip', rate='120/m', block=True)
@require_http_methods(['POST'])
def api_sl_collect(request, token):
    """
    POST /api/soulslike/session/<token>/collect/
    Body: { "item_name": "Moonveil" }  OR  { "item_id": 42, "item_type": "weapon" }
    Requires owner: web session OR X-Listener-Key.
    """
    uid = _owner_uid_from_request(request)
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    item_name = sanitize_text(str(data.get('item_name', ''))[:200])
    item_id   = safe_int(data.get('item_id'), None)
    item_type = str(data.get('item_type', ''))[:16]
    method    = str(data.get('method', 'ocr'))[:16]  # ocr | web | hotkey
    now       = int(time.time())

    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id FROM sl_collection_sessions WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        ), {'tok': token, 'uid': uid}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found or ended'}, status=404)
        sid = session[0]

        # Match by name (case-insensitive) or by id+type
        if item_name:
            row = db.execute(text(
                "SELECT id FROM sl_collection_item_status "
                "WHERE session_id=:sid AND LOWER(item_name)=LOWER(:name) LIMIT 1"
            ), {'sid': sid, 'name': item_name}).fetchone()
        elif item_id and item_type:
            row = db.execute(text(
                "SELECT id FROM sl_collection_item_status "
                "WHERE session_id=:sid AND item_id=:iid AND item_type=:itype LIMIT 1"
            ), {'sid': sid, 'iid': item_id, 'itype': item_type}).fetchone()
        else:
            return JsonResponse({'error': 'item_name or item_id+item_type required'}, status=400)

        if not row:
            return JsonResponse({'error': 'Item not in this session'}, status=404)

        db.execute(text("""
            UPDATE sl_collection_item_status
            SET is_collected=1, collected_at=:ts, collection_method=:method
            WHERE id=:iid
        """), {'ts': now, 'method': method, 'iid': row[0]})
        db.commit()

        # Return progress
        counts = db.execute(text(
            "SELECT COUNT(*), SUM(is_collected) FROM sl_collection_item_status WHERE session_id=:sid"
        ), {'sid': sid}).fetchone()
        total     = counts[0] or 0
        collected = int(counts[1] or 0)

    return JsonResponse({
        'ok': True,
        'item_name': item_name,
        'progress': f'{collected}/{total}',
        'collected': collected,
        'total': total,
    })


@csrf_exempt
@ratelimit(key='ip', rate='120/m', block=True)
@require_http_methods(['POST'])
def api_sl_uncollect(request, token):
    """
    POST /api/soulslike/session/<token>/uncollect/
    Body: { "item_name": "Moonveil" }
    Requires owner: web session OR X-Listener-Key.
    """
    uid = _owner_uid_from_request(request)
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    item_name = sanitize_text(str(data.get('item_name', ''))[:200])

    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id FROM sl_collection_sessions WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        ), {'tok': token, 'uid': uid}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid = session[0]

        db.execute(text("""
            UPDATE sl_collection_item_status
            SET is_collected=0, collected_at=NULL, collection_method=NULL
            WHERE session_id=:sid AND LOWER(item_name)=LOWER(:name)
        """), {'sid': sid, 'name': item_name})
        db.commit()

    return JsonResponse({'ok': True})


# ── Death tracking ────────────────────────────────────────────────────────────

@csrf_exempt
@ratelimit(key='ip', rate='60/m', block=True)
@ratelimit(key=lambda g, r: r.resolver_match.kwargs.get('token', 'anon'), rate='20/m', block=True)
@require_http_methods(['POST'])
def api_sl_death(request, token):
    """
    POST /api/soulslike/session/<token>/death/
    Body: { "boss": "Malenia", "area": "Haligtree" }  ← both optional
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    boss = sanitize_text(str(data.get('boss', ''))[:200])
    area = sanitize_text(str(data.get('area', ''))[:200])
    now  = int(time.time())

    with get_db_session() as db:
        session = db.execute(text("""
            SELECT id, death_count, current_life_start, total_survival_sec,
                   longest_life_sec, rage_pct, hollow_streak,
                   time_in_hollow_sec, hollow_entered_at, session_start_ts,
                   last_attempted_boss, is_hardcore, hc_score, session_death_count
            FROM sl_collection_sessions WHERE session_token=:tok AND ended_at IS NULL
        """), {'tok': token}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        (sid, death_count, life_start, total_survival, longest_life,
         rage_pct, hollow_streak, time_in_hollow, hollow_entered, session_start,
         last_attempted_boss, is_hardcore, hc_score, session_death_count) = session

        # Only use last_attempted_boss fallback for Listener deaths (source='listener')
        source = sanitize_text(str(data.get('source', 'listener'))[:20])
        if not boss and last_attempted_boss and source == 'listener':
            boss = last_attempted_boss

        if (death_count or 0) >= 9999:
            return JsonResponse({'error': 'Death count limit reached'}, status=429)

        # ── Hardcore mode: first death ends the run ───────────────────────────
        if is_hardcore and (death_count or 0) == 0:
            # Calculate final HC score from bosses + items killed so far
            bosses_pts = db.execute(text("""
                SELECT COALESCE(SUM(CASE tier
                    WHEN 'enemy'       THEN 10
                    WHEN 'great_enemy' THEN 25
                    WHEN 'legend'      THEN 50
                    WHEN 'demigod'     THEN 100
                    WHEN 'god'         THEN 250
                    ELSE 10 END), 0)
                FROM sl_session_bosses WHERE session_id=:sid AND is_defeated=1
            """), {'sid': sid}).scalar() or 0
            items_pts = db.execute(text(
                "SELECT COUNT(*) * :pts FROM sl_collection_item_status "
                "WHERE session_id=:sid AND is_collected=1"
            ), {'sid': sid, 'pts': HC_ITEM_POINTS}).scalar() or 0
            final_hc_score = int(bosses_pts + items_pts)

            # Record the death then immediately end the session
            db.execute(text("""
                INSERT INTO sl_death_events
                    (session_id, boss_name, area_name, died_at, life_duration_sec)
                VALUES (:sid, :boss, :area, :ts, :life)
            """), {'sid': sid, 'boss': boss or None, 'area': None,
                   'ts': now, 'life': 0})
            db.execute(text("""
                UPDATE sl_collection_sessions SET
                    death_count=1, last_death_boss=:boss,
                    ended_at=:now, hc_score=:score, hc_death_boss=:boss
                WHERE id=:sid
            """), {'boss': boss or None, 'now': now, 'score': final_hc_score, 'sid': sid})
            db.commit()

            sse_publish(token, {
                'event': 'hc_death',
                'boss': boss or '',
                'hc_score': final_hc_score,
                'message': 'Hardcore run ended - permadeath!',
            })
            return JsonResponse({
                'ok': True, 'hc_death': True,
                'hc_score': final_hc_score,
                'boss': boss or '',
                'message': 'Run ended - Hardcore Permadeath',
            })
        elif is_hardcore:
            # Already died once in HC - this shouldn't happen, run should be ended
            return JsonResponse({'error': 'Hardcore run already ended'}, status=400)

        # ── Survival time / longest life ──────────────────────────────────────
        # total_survival_sec is accumulated by heartbeat (game-running only).
        # On death we just snapshot the current life duration from the heartbeat
        # delta since last death, stored in listener_session_sec diff.
        # We use current_life_start only to compute longest life - NOT to add
        # to total_survival (heartbeat already did that second by second).
        life_start_ts = life_start or now
        raw_duration = max(0, now - life_start_ts) if life_start else 0
        # Cap life duration at 12h to prevent stale timestamps inflating survival time
        MAX_LIFE_SEC = 43200  # 12 hours
        life_duration = min(raw_duration, MAX_LIFE_SEC)
        new_total_survival = total_survival or 0  # heartbeat owns this, don't touch
        new_longest = max(longest_life or 0, life_duration)

        # ── Rage calculation (+25% per death, caps at 100%) ──────────────────
        old_rage = rage_pct or 0
        new_rage = min(100, old_rage + 25)
        was_hollow = old_rage >= 100
        now_hollow = new_rage >= 100

        # Hollow state tracking
        new_hollow_streak = hollow_streak or 0
        new_time_in_hollow = time_in_hollow or 0
        new_hollow_entered = hollow_entered

        if now_hollow and not was_hollow:
            # Just entered hollow
            new_hollow_entered = now
        elif now_hollow and was_hollow:
            # Already hollow → increment streak counter
            new_hollow_streak += 1
        if not now_hollow and was_hollow and hollow_entered:
            # Left hollow - accumulate time spent hollow
            new_time_in_hollow += max(0, now - hollow_entered)
            new_hollow_entered = None

        rage_name = _rage_name(new_rage)

        # ── Insert death event ────────────────────────────────────────────────
        db.execute(text("""
            INSERT INTO sl_death_events
                (session_id, boss_name, area_name, died_at, life_duration_sec)
            VALUES (:sid, :boss, :area, :ts, :life)
        """), {'sid': sid, 'boss': boss or None, 'area': area or None,
               'ts': now, 'life': life_duration})

        # ── Update session ────────────────────────────────────────────────────
        db.execute(text("""
            UPDATE sl_collection_sessions SET
                death_count         = death_count + 1,
                session_death_count = session_death_count + 1,
                last_death_boss    = :boss,
                current_life_start = :now,
                longest_life_sec   = :longest,
                rage_pct           = :rage,
                rage_name          = :rage_name,
                hollow_streak      = :hollow_streak,
                time_in_hollow_sec = :time_hollow,
                hollow_entered_at  = :hollow_entered
            WHERE id = :sid
        """), {
            'boss': boss or None, 'now': now,
            'longest': new_longest,
            'rage': new_rage, 'rage_name': rage_name,
            'hollow_streak': new_hollow_streak,
            'time_hollow': new_time_in_hollow,
            'hollow_entered': new_hollow_entered,
            'sid': sid,
        })
        db.commit()

        new_death_count   = (death_count or 0) + 1
        new_session_deaths = (session_death_count or 0) + 1

    # Push to all browser clients instantly via SSE
    sse_publish(token, {
        'event':        'death',
        'deaths':       new_death_count,
        'boss':         boss or '',
        'rage_pct':     new_rage,
        'rage_name':    rage_name,
        'is_hollow':    now_hollow,
        'hollow_streak': new_hollow_streak,
    })

    return JsonResponse({
        'ok':             True,
        'deaths':         new_death_count,      # total for this run (leaderboard)
        'total_deaths':   new_death_count,      # alias
        'session_deaths': new_session_deaths,   # this sitting only (resets on relaunch)
        'boss':           boss,
        'rage_pct':       new_rage,
        'rage_name':      rage_name,
        'is_hollow':      now_hollow,
        'hollow_streak':  new_hollow_streak,
        'just_went_hollow': (now_hollow and not was_hollow),
        'life_duration':  life_duration,
        'total_survival': new_total_survival,
        'longest_life':   new_longest,
    })


# ── Session status (overlay polls this) ──────────────────────────────────────

@csrf_exempt
@require_http_methods(['GET'])
def api_sl_session_status(request, token):
    """GET /api/soulslike/session/<token>/status/ - polled by overlay every 3s"""
    now = int(time.time())
    with get_db_session() as db:
        session = db.execute(text("""
            SELECT id, build_name, game, spoiler_mode, started_at,
                   death_count, last_death_boss, ended_at,
                   session_type, game_mode,
                   rage_pct, rage_name, hollow_streak,
                   time_in_hollow_sec, hollow_entered_at,
                   total_survival_sec, longest_life_sec,
                   current_life_start, session_start_ts,
                   listener_last_ping, listener_session_sec,
                   last_attempted_boss, listener_game_running, game_stopped_at,
                   app_session_sec, app_streak_sec, app_longest_sec,
                   is_hardcore, hc_score, hc_completed,
                   session_death_count
            FROM sl_collection_sessions WHERE session_token=:tok
        """), {'tok': token}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        (sid, build_name, game, spoiler, started_at, death_count, last_death,
         ended_at, session_type, game_mode,
         rage_pct, rage_name, hollow_streak,
         time_in_hollow, hollow_entered, total_survival, longest_life,
         life_start, session_start,
         listener_last_ping, listener_session_sec,
         last_attempted_boss, listener_game_running, game_stopped_at,
         app_session_sec, app_streak_sec, app_longest_sec,
         is_hardcore, hc_score, hc_completed,
         session_death_count) = session

        is_active   = ended_at is None
        rage_pct    = rage_pct or 0
        rage_name   = rage_name or _rage_name(rage_pct)
        is_hollow   = rage_pct >= 100
        death_count = death_count or 0

        # Listener connection: connected if pinged within last 10s
        listener_connected = bool(listener_last_ping and (now - listener_last_ping) <= 10)
        # Game running: only true if connected AND game process detected
        game_active = listener_connected and bool(listener_game_running)
        # Grace period
        grace_remaining = 0
        in_grace = False
        if listener_connected and not game_active and game_stopped_at:
            elapsed = now - game_stopped_at
            grace_remaining = max(0, 180 - elapsed)
            in_grace = grace_remaining > 0
        # Session time - app is authoritative when connected
        has_app_timers = game_active and (app_session_sec or 0) > 0
        listener_sec = (app_session_sec or 0) if has_app_timers else (listener_session_sec or 0)

        # Current streak - app is authoritative when connected, else server calculates
        app_streak  = getattr(session, 'app_streak_sec',  None) or 0
        app_session = getattr(session, 'app_session_sec', None) or 0
        app_longest = getattr(session, 'app_longest_sec', None) or 0

        if game_active and app_streak > 0:
            # App reported its streak directly - use it
            current_life_sec = app_streak
        elif game_active and life_start:
            current_life_sec = max(0, now - life_start)
        else:
            current_life_sec = 0

        # Deaths per Boss = total deaths / bosses defeated (calculated after boss_rows query below)
        # true_death_rate set after bosses_defeated is known

        # Hollow time accumulation (add current hollow session if active)
        total_hollow = time_in_hollow or 0
        if is_hollow and hollow_entered and is_active:
            total_hollow += max(0, now - hollow_entered)

        spoiler_mode_val = spoiler

        # Always fetch items (if any exist for this session)
        items = db.execute(text("""
            SELECT item_name, item_type, is_collected, collected_at,
                   collection_method, location_hint
            FROM sl_collection_item_status
            WHERE session_id=:sid ORDER BY is_collected ASC, item_type, item_name
        """), {'sid': sid}).fetchall()

        # Always fetch boss progress
        boss_rows = db.execute(text("""
            SELECT boss_name, location, region, tier, is_defeated, defeated_at, boss_key
            FROM sl_session_bosses WHERE session_id=:sid
            ORDER BY region, location, boss_name
        """), {'sid': sid}).fetchall()
        bosses_defeated = sum(1 for b in boss_rows if b[4])
        bosses_total    = len(boss_rows)

        # Deaths per Boss: meaningful souls metric - how many deaths does it take per boss kill
        if bosses_defeated >= 1:
            true_death_rate = round((death_count or 0) / bosses_defeated, 1)
        else:
            true_death_rate = None  # "--" until first boss killed
        bosses = [
            {'name': b[0], 'location': b[1], 'region': b[2], 'tier': b[3],
             'defeated': bool(b[4]), 'defeated_at': b[5], 'key': b[6]}
            for b in boss_rows
        ]

        deaths_log = db.execute(text("""
            SELECT boss_name, area_name, died_at, life_duration_sec
            FROM sl_death_events WHERE session_id=:sid
            ORDER BY died_at DESC LIMIT 10
        """), {'sid': sid}).fetchall()

    total_items = len(items)
    collected   = sum(1 for i in items if i[2])

    def item_hint(item):
        if spoiler_mode_val == 'blind': return None
        if spoiler_mode_val == 'region':
            h = item[5] or ''
            return h.split(',')[0].strip() if h else None
        return item[5] or None

    payload = {
        'build_name':       build_name,
        'game':             game,
        'game_mode':        game_mode,
        'session_type':     session_type,
        'spoiler_mode':     spoiler_mode_val,
        'started_at':       started_at,
        'is_active':        is_active,
        'deaths':           death_count,
        'last_death':           last_death or '',
        'last_attempted_boss':  last_attempted_boss or '',
        # Rage / Hollow
        'rage_pct':         rage_pct,
        'rage_name':        rage_name,
        'is_hollow':        is_hollow,
        'hollow_streak':    hollow_streak or 0,
        'time_in_hollow':   total_hollow,
        'time_in_hollow_fmt': _fmt_time(total_hollow),
        # Listener
        'listener_connected':    listener_connected,
        'listener_game_running': game_active,
        'listener_in_grace':     in_grace,
        'grace_remaining_sec':   grace_remaining,
        'listener_session_sec':  listener_sec,
        'session_time_fmt':      _fmt_time(listener_sec),
        'session_started':       bool(session_start),
        # Survival & timing
        # survival_time = current life streak (resets on death, like "days without accident")
        'survival_time_sec':    current_life_sec,
        'survival_time_fmt':    _fmt_time(current_life_sec),
        'current_life_sec':     current_life_sec,
        'current_life_fmt':     _fmt_time(current_life_sec),
        'longest_life_sec':     (app_longest_sec or longest_life or 0) if has_app_timers else (longest_life or 0),
        'longest_life_fmt':     _fmt_time((app_longest_sec or longest_life or 0) if has_app_timers else (longest_life or 0)),
        'total_survival_fmt':   _fmt_time(total_survival or 0),
        'true_death_rate':      true_death_rate,  # None = under 10min threshold
        'death_rate_ready':     true_death_rate is not None,
        # Boss progress (mortality)
        'bosses_defeated':  bosses_defeated,
        'bosses_total':     bosses_total,
        'bosses':           bosses,
        # Collection progress
        'progress':     f'{collected}/{total_items}',
        'collected':    collected,
        'total':        total_items,
        'items': [
            {'name': i[0], 'type': i[1], 'collected': bool(i[2]),
             'collected_at': i[3], 'method': i[4] or '', 'hint': item_hint(i)}
            for i in items
        ],
        'recent_deaths': [
            {'boss': d[0] or '', 'area': d[1] or '', 'at': d[2], 'life': d[3] or 0}
            for d in deaths_log
        ],
        # Hardcore
        'is_hardcore':   bool(is_hardcore),
        'hc_score':      hc_score or 0,
        'hc_completed':  bool(hc_completed),
        # Session vs total deaths
        'deaths':        death_count or 0,          # total for this run
        'session_deaths': session_death_count or 0, # this sitting only
    }
    response = JsonResponse(payload)
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET'
    return response


# ── Reset deaths ─────────────────────────────────────────────────────────────

@csrf_exempt
@ratelimit(key='ip', rate='120/m', block=True)
@require_http_methods(['POST'])
def api_sl_heartbeat(request, token):
    """
    POST /api/soulslike/session/<token>/heartbeat/
    Body: { "game_running": true/false }
    Called by QuestLog Listener every 5s.
    - Always accumulates listener_session_sec (Listener is connected)
    - Only accumulates survival time when game_running=True (game process detected)
    """
    now = int(time.time())
    try:
        body = json.loads(request.body) if request.body else {}
    except Exception:
        body = {}
    game_running = bool(body.get('game_running', False))
    # App reports authoritative timer values - capped at 24h to prevent leaderboard fraud
    _MAX_TIMER = 86400  # 24 hours in seconds
    def _safe_timer(key):
        v = body.get(key, -1)
        try:
            v = int(v)
        except (TypeError, ValueError):
            return -1
        return min(v, _MAX_TIMER) if v >= 0 else -1
    app_session_sec  = _safe_timer('session_sec')
    app_streak_sec   = _safe_timer('streak_sec')
    app_longest_sec  = _safe_timer('longest_sec')
    app_survival_sec = _safe_timer('survival_sec')

    GRACE_PERIOD_SEC = 180  # 3 minutes - covers crashes and alt-tab freezes

    with get_db_session() as db:
        row = db.execute(text(
            "SELECT id, listener_last_ping, listener_game_running, game_stopped_at, "
            "       death_count, session_death_count "
            "FROM sl_collection_sessions "
            "WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
        if not row:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid, last_ping, was_game_running, game_stopped_at, total_deaths, session_deaths = row
        total_deaths   = total_deaths or 0
        session_deaths = session_deaths or 0

        # Only accumulate time if last ping was recent (within 10s)
        delta = 0
        if last_ping and (now - last_ping) <= 10:
            delta = now - last_ping

        # Detect game relaunch: was stopped (or in grace), now running again after grace expired
        game_relaunched = (
            game_running and not was_game_running and
            game_stopped_at and (now - game_stopped_at) > GRACE_PERIOD_SEC
        )
        # Also reset if this is the very first time game_running goes true (no prior stop)
        game_first_start = game_running and not was_game_running and not game_stopped_at and last_ping is None

        if game_running:
            if app_session_sec >= 0:
                # App is the source of truth - use its timer values directly
                surv = app_survival_sec if app_survival_sec >= 0 else max(0, app_streak_sec)
                reset_session = "session_death_count=0, session_death_baseline=:tdeath, " if (game_relaunched or game_first_start) else ""
                extra_params  = {'tdeath': total_deaths} if (game_relaunched or game_first_start) else {}
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=1, "
                    "    game_stopped_at=NULL, "
                    f"   {reset_session}"
                    "    listener_session_sec=:sess, "
                    "    total_survival_sec=GREATEST(total_survival_sec, :surv), "
                    "    longest_life_sec=GREATEST(longest_life_sec, :longest), "
                    "    app_session_sec=:sess, app_streak_sec=:streak, app_longest_sec=:longest "
                    "WHERE id=:sid"
                ), {'now': now, 'sid': sid,
                    'sess':   app_session_sec,
                    'surv':   surv,
                    'streak': max(0, app_streak_sec),
                    'longest': max(0, app_longest_sec),
                    **extra_params})
                if game_relaunched or game_first_start:
                    session_deaths = 0
            elif game_stopped_at and (now - game_stopped_at) > GRACE_PERIOD_SEC:
                # Grace period expired, game relaunched without app timers - fresh session
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=1, "
                    "    game_stopped_at=NULL, "
                    "    session_start_ts=:now, current_life_start=:now, "
                    "    listener_session_sec=:delta, total_survival_sec=:delta, "
                    "    session_death_count=0, session_death_baseline=:tdeath, "
                    "    app_session_sec=0, app_streak_sec=0, app_longest_sec=0 "
                    "WHERE id=:sid"
                ), {'now': now, 'delta': delta, 'sid': sid, 'tdeath': total_deaths})
                session_deaths = 0
            else:
                # Web-only session - server accumulates
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=1, "
                    "    game_stopped_at=NULL, "
                    "    listener_session_sec=listener_session_sec+:delta, "
                    "    total_survival_sec=total_survival_sec+:delta "
                    "WHERE id=:sid"
                ), {'now': now, 'delta': delta, 'sid': sid})
        else:
            # Game not running
            if was_game_running:
                # Game just stopped - stamp the stop time, start grace period
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=0, "
                    "    game_stopped_at=:stopped "
                    "WHERE id=:sid"
                ), {'now': now, 'stopped': now, 'sid': sid})
            elif game_stopped_at and (now - game_stopped_at) > GRACE_PERIOD_SEC:
                # Grace period expired - reset session timers, keep run-level stats
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=0, "
                    "    game_stopped_at=NULL, "
                    "    session_start_ts=NULL, current_life_start=NULL, "
                    "    listener_session_sec=0, total_survival_sec=0, "
                    "    session_death_count=0, session_death_baseline=:tdeath, "
                    "    app_session_sec=0, app_streak_sec=0, app_longest_sec=0 "
                    "WHERE id=:sid"
                ), {'now': now, 'sid': sid, 'tdeath': total_deaths})
            else:
                # Still in grace period or game never ran - just update ping
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=0 WHERE id=:sid"
                ), {'now': now, 'sid': sid})
        db.commit()

    # Push timer update to browser clients instantly when game is running
    if game_running and app_session_sec >= 0:
        surv = app_survival_sec if app_survival_sec >= 0 else max(0, app_streak_sec)
        sse_publish(token, {
            'event':        'timers',
            'session_sec':  app_session_sec,
            'streak_sec':   max(0, app_streak_sec),
            'longest_sec':  max(0, app_longest_sec),
            'survival_sec': surv,
            'game_running': True,
            'listener_connected': True,
        })

    response = JsonResponse({
        'ok': True,
        'session_deaths': session_deaths,
        'total_deaths':   total_deaths,
    })
    response['Access-Control-Allow-Origin'] = '*'
    return response


@csrf_exempt
@ratelimit(key='ip', rate='30/m', block=True)
@require_http_methods(['POST'])
def api_sl_reset_deaths(request, token):
    """
    POST /api/soulslike/session/<token>/reset-deaths/
    Auth: web session (user_id check) OR token-only (desktop app - token is the secret).
    Resets all death + timing stats to zero.
    """
    now = int(time.time())
    with get_db_session() as db:
        # Resolve session owner - web session OR API key (desktop app)
        uid = request.session.get('web_user_id') if hasattr(request, 'session') else None
        if not uid:
            api_key = request.headers.get('X-Listener-Key', '').strip()
            if api_key and api_key.startswith('ql_'):
                key_row = db.execute(text(
                    "SELECT id FROM web_users WHERE listener_api_key=:k AND is_banned=0"
                ), {'k': api_key}).fetchone()
                if key_row:
                    uid = key_row[0]
        if not uid:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        where = "session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        params = {'tok': token, 'uid': uid, 'now': now}

        result = db.execute(text(
            f"UPDATE sl_collection_sessions SET "
            "death_count=0, last_death_boss=NULL, last_attempted_boss=NULL, "
            "session_death_count=0, session_death_baseline=0, "
            "rage_pct=0, rage_name='Maiden''s Grace', "
            "hollow_streak=0, time_in_hollow_sec=0, hollow_entered_at=NULL, "
            "total_survival_sec=0, longest_life_sec=0, current_life_start=:now, "
            "session_start_ts=:now, listener_session_sec=0, hollow_boss_kills=0, "
            "listener_game_running=0, game_stopped_at=NULL, "
            "reset_count=reset_count+1, "
            "app_session_sec=0, app_streak_sec=0, app_longest_sec=0 "
            f"WHERE {where}"
        ), params)
        if result.rowcount:
            db.execute(text(
                "DELETE FROM sl_death_events WHERE session_id=("
                "SELECT id FROM sl_collection_sessions WHERE session_token=:tok AND user_id=:uid)"
            ), {'tok': token, 'uid': uid})
        db.commit()
    if result.rowcount:
        # Push reset to all browser clients instantly
        sse_publish(token, {
            'event':        'reset',
            'deaths':       0,
            'rage_pct':     0,
            'rage_name':    "Maiden's Grace",
            'session_sec':  0,
            'streak_sec':   0,
            'longest_sec':  0,
        })
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Session not found or already ended'}, status=404)


# ── Set total deaths (manual correction) ─────────────────────────────────────

@web_login_required
@require_http_methods(['POST'])
def api_sl_set_deaths(request, token):
    """
    POST /api/soulslike/session/<token>/set-deaths/
@csrf_exempt
    Body: { "count": 184 }
    Owner-only. Lets the player correct their total death count manually.
    session_death_count is also updated to match if it would exceed the new total.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    count = safe_int(data.get('count'), None, 0, 99999)
    if count is None:
        return JsonResponse({'error': 'count required (0-99999)'}, status=400)

    uid = request.web_user.id
    with get_db_session() as db:
        row = db.execute(text(
            "SELECT id, user_id, session_death_count FROM sl_collection_sessions "
            "WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
        if not row:
            return JsonResponse({'error': 'Session not found or already ended'}, status=404)
        if row[1] != uid:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # session_death_count can't exceed new total
        new_session = min(row[2] or 0, count)
        db.execute(text(
            "UPDATE sl_collection_sessions SET death_count=:c, session_death_count=:sc "
            "WHERE id=:sid"
        ), {'c': count, 'sc': new_session, 'sid': row[0]})
        db.commit()
        logger.info("sl_set_deaths uid=%s sid=%s count=%s", uid, row[0], count)

    return JsonResponse({'ok': True, 'deaths': count, 'session_deaths': new_session})


# ── Subtract death (F10 undo) ────────────────────────────────────────────────

@csrf_exempt
@ratelimit(key='ip', rate='60/m', block=True)
@require_http_methods(['POST'])
def api_sl_subtract_death(request, token):
    """
    POST /api/soulslike/session/<token>/subtract-death/
    Removes the last death - decrements counter, adjusts rage, removes last death event.
    Used by EldenTracker F10 undo and web tracker undo.
    No auth required - token is the secret.
    """
    now = int(time.time())
    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id, death_count, rage_pct, hollow_streak, session_death_count FROM sl_collection_sessions "
            "WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid, death_count, rage_pct, hollow_streak, session_death_count = session
        if (death_count or 0) <= 0:
            return JsonResponse({'ok': True, 'deaths': 0, 'session_deaths': 0})

        # Reverse one death: -1 death, -25% rage
        new_rage = max(0, (rage_pct or 0) - 25)
        new_deaths = max(0, (death_count or 0) - 1)
        new_session_deaths = max(0, (session_death_count or 0) - 1)
        new_rage_name = _rage_name(new_rage)

        # Remove the most recent death event
        db.execute(text(
            "DELETE FROM sl_death_events WHERE id = ("
            "SELECT id FROM sl_death_events WHERE session_id=:sid "
            "ORDER BY died_at DESC LIMIT 1)"
        ), {'sid': sid})

        db.execute(text(
            "UPDATE sl_collection_sessions SET "
            "death_count=:deaths, session_death_count=:sdeath, "
            "rage_pct=:rage, rage_name=:rname, "
            "hollow_streak=GREATEST(0, hollow_streak - CASE WHEN :rage < 100 AND :old_rage >= 100 THEN 1 ELSE 0 END) "
            "WHERE id=:sid"
        ), {'deaths': new_deaths, 'sdeath': new_session_deaths,
            'rage': new_rage, 'rname': new_rage_name,
            'old_rage': rage_pct or 0, 'sid': sid})
        db.commit()

    response = JsonResponse({'ok': True, 'deaths': new_deaths, 'session_deaths': new_session_deaths,
                             'rage_pct': new_rage, 'rage_name': new_rage_name})
    response['Access-Control-Allow-Origin'] = '*'
    return response


# ── Active runs for EldenTracker on launch ───────────────────────────────────

@ratelimit(key='ip', rate='30/m', block=True)
@require_http_methods(['GET'])
def api_sl_active_runs(request):
    """
    GET /api/soulslike/runs/active/
@csrf_exempt
    Header: X-Listener-Key: ql_xxxxx
    Returns active runs - same as /api/listener/runs/ but also includes
    full status snapshot so EldenTracker can sync state on launch.
    """
    key = request.headers.get('X-Listener-Key', '').strip()
    if not key or not key.startswith('ql_'):
        return JsonResponse({'error': 'Missing or invalid API key'}, status=401)

    with get_db_session() as db:
        user = db.execute(text(
            "SELECT id, username FROM web_users WHERE listener_api_key=:key AND is_banned=0"
        ), {'key': key}).fetchone()
        if not user:
            return JsonResponse({'error': 'Invalid API key'}, status=401)

        uid, username = user
        runs = db.execute(text("""
            SELECT session_token, build_name, game, game_mode, started_at,
                   death_count, rage_pct, rage_name, hollow_streak,
                   total_survival_sec, longest_life_sec, listener_session_sec,
                   last_attempted_boss
            FROM sl_collection_sessions
            WHERE user_id=:uid AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 10
        """), {'uid': uid}).fetchall()

        run_list = []
        for r in runs:
            tok = r[0]
            # Boss state
            boss_rows = db.execute(text(
                "SELECT boss_key, is_defeated FROM sl_session_bosses WHERE session_id=("
                "SELECT id FROM sl_collection_sessions WHERE session_token=:tok)"
            ), {'tok': tok}).fetchall()
            defeated_keys = [b[0] for b in boss_rows if b[1]]

            BASE = 'https://questlog.casual-heroes.com'
            run_list.append({
                'token':          tok,
                'build_name':     r[1],
                'game':           r[2],
                'game_mode':      r[3] or 'vanilla',
                'started_at':     r[4],
                'deaths':         r[5] or 0,
                'rage_pct':       r[6] or 0,
                'rage_name':      r[7] or "Maiden's Grace",
                'hollow_streak':  r[8] or 0,
                'survival_sec':   r[9] or 0,
                'longest_life':   r[10] or 0,
                'session_sec':    r[11] or 0,
                'last_boss':      r[12] or '',
                'defeated_bosses': defeated_keys,
                # Web tracker + all overlay URLs ready to paste into OBS/Meld
                'web_tracker':        f'{BASE}/soulslike/runs/{tok}/',
                'overlay_combined':   f'{BASE}/soulslike/overlay/{tok}/combined/',
                'overlay_mortality':  f'{BASE}/soulslike/overlay/{tok}/mortality/',
                'overlay_deaths':     f'{BASE}/soulslike/overlay/{tok}/deaths/',
                'overlay_hollow':     f'{BASE}/soulslike/overlay/{tok}/hollow/',
                'overlay_collection': f'{BASE}/soulslike/overlay/{tok}/collection/',
            })

    return JsonResponse({'ok': True, 'username': username, 'runs': run_list})


@csrf_exempt
@require_http_methods(['POST'])
def api_sl_stop_session(request, token):
    """
    POST /api/soulslike/session/<token>/stop-session/
    Stops the current gaming session - resets session timers and session death count
    WITHOUT resetting total deaths, bosses, or items. Use when you close the game
    mid-run and want a clean slate for the next gaming session.
    """
    now = int(time.time())
    uid = _owner_uid_from_request(request)
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    with get_db_session() as db:
        row = db.execute(text(
            "SELECT id, death_count FROM sl_collection_sessions "
            "WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        ), {'tok': token, 'uid': uid}).fetchone()
        if not row:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid, total_deaths = row

        db.execute(text("""
            UPDATE sl_collection_sessions SET
                session_death_count    = 0,
                session_death_baseline = :tdeath,
                session_start_ts       = NULL,
                current_life_start     = NULL,
                total_survival_sec     = 0,
                listener_session_sec   = 0,
                listener_game_running  = 0,
                game_stopped_at        = NULL,
                app_session_sec        = 0,
                app_streak_sec         = 0,
                app_longest_sec        = 0,
                last_attempted_boss    = NULL,
                timing_mode            = 'listener'
            WHERE id=:sid
        """), {'now': now, 'tdeath': total_deaths or 0, 'sid': sid})
        db.commit()

    sse_publish(token, {
        'event': 'session_stopped',
        'session_deaths': 0,
        'total_survival': 0,
        'session_sec': 0,
        'message': 'Session stopped - timers reset. Total deaths and boss progress kept.',
    })
    return JsonResponse({'ok': True, 'message': 'Session stopped'})


# ── Set boss focus (for Listener death attribution) ──────────────────────────

@web_login_required
@require_http_methods(['POST'])
def api_sl_manual_start(request, token):
    """
    POST /api/soulslike/session/<token>/manual-start/
    Called when a web/console user opens the run page - marks the session
    as manual timing mode so the status API knows to return timing_mode='manual'.
    The client handles timing locally via JS; this just records the mode.
    """
    uid = request.web_user.id
    now = int(time.time())
    with get_db_session() as db:
        # Get current death_count to set as baseline for this session
        row = db.execute(text(
            "SELECT death_count FROM sl_collection_sessions "
            "WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        ), {'tok': token, 'uid': uid}).fetchone()
        baseline = row[0] if row else 0
        db.execute(text(
            "UPDATE sl_collection_sessions SET timing_mode='manual', "
            "session_start_ts=COALESCE(session_start_ts, :now), "
            "current_life_start=COALESCE(current_life_start, :now), "
            "session_death_count=0, session_death_baseline=:baseline "
            "WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL "
            "AND timing_mode != 'listener'"
        ), {'tok': token, 'uid': uid, 'now': now, 'baseline': baseline})
        db.commit()
    return JsonResponse({'ok': True})


@csrf_exempt
@ratelimit(key='user_or_ip', rate='20/m', block=True)
@require_http_methods(['POST'])
def api_sl_test_hollow(request, token):
    """
    POST /api/soulslike/session/<token>/test-hollow/
    Owner only. Temporarily sets rage to 100 (HOLLOW) in DB so the polling
    overlay picks it up. Auto-reverts after 5 seconds.
    """
    uid = _owner_uid_from_request(request)
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id, rage_pct, rage_name, hollow_streak FROM sl_collection_sessions "
            "WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        ), {'tok': token, 'uid': uid}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid              = session[0]
        orig_rage_pct    = session[1] or 0
        orig_rage_name   = session[2] or "Maiden's Grace"
        hollow_streak    = session[3] or 0

        # Set to HOLLOW so next poll picks it up
        db.execute(text(
            "UPDATE sl_collection_sessions SET rage_pct=100, rage_name='HOLLOW', "
            "hollow_entered_at=COALESCE(hollow_entered_at, :now) WHERE id=:sid"
        ), {'sid': sid, 'now': int(time.time())})
        db.commit()

    # Revert after 5 seconds in background thread
    import threading
    def revert():
        import time as _t
        _t.sleep(5)
        try:
            with get_db_session() as _db:
                _db.execute(text(
                    "UPDATE sl_collection_sessions SET rage_pct=:pct, rage_name=:name, "
                    "hollow_entered_at=NULL WHERE id=:sid"
                ), {'pct': orig_rage_pct, 'name': orig_rage_name, 'sid': sid})
                _db.commit()
        except Exception as e:
            logger.error("test_hollow revert failed sid=%s: %s", sid, e)
    threading.Thread(target=revert, daemon=True).start()

    return JsonResponse({'ok': True, 'message': 'Test hollow active for 5 seconds - check your overlay'})


@csrf_exempt
@require_http_methods(['POST'])
def api_sl_test_hollow(request, token):
    """
    POST /api/soulslike/session/<token>/test-hollow/
    Owner only. Temporarily sets rage to 100 (HOLLOW) in DB so the polling
    overlay picks it up. Auto-reverts after 5 seconds.
    """
    uid = _owner_uid_from_request(request)
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id, rage_pct, rage_name, hollow_streak FROM sl_collection_sessions "
            "WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        ), {'tok': token, 'uid': uid}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid              = session[0]
        orig_rage_pct    = session[1] or 0
        orig_rage_name   = session[2] or "Maiden's Grace"
        hollow_streak    = session[3] or 0

        # Set to HOLLOW so next poll picks it up
        db.execute(text(
            "UPDATE sl_collection_sessions SET rage_pct=100, rage_name='HOLLOW', "
            "hollow_entered_at=COALESCE(hollow_entered_at, :now) WHERE id=:sid"
        ), {'sid': sid, 'now': int(time.time())})
        db.commit()

    # Revert after 5 seconds in background thread
    import threading
    def revert():
        import time as _t
        _t.sleep(5)
        try:
            with get_db_session() as _db:
                _db.execute(text(
                    "UPDATE sl_collection_sessions SET rage_pct=:pct, rage_name=:name, "
                    "hollow_entered_at=NULL WHERE id=:sid"
                ), {'pct': orig_rage_pct, 'name': orig_rage_name, 'sid': sid})
                _db.commit()
        except Exception as e:
            logger.error("test_hollow revert failed sid=%s: %s", sid, e)
    threading.Thread(target=revert, daemon=True).start()

    return JsonResponse({'ok': True, 'message': 'Test hollow active for 5 seconds - check your overlay'})


def api_sl_set_focus(request, token):
    """
    POST /api/soulslike/session/<token>/set-focus/
    Body: { "boss_name": "Malenia" }  (empty string to clear)
    Sets last_attempted_boss so Listener deaths get the right label.
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    boss_name = sanitize_text(str(data.get('boss_name', ''))[:200]) or None
    # Require owner: web session OR API key
    uid = request.session.get('web_user_id') if hasattr(request, 'session') else None
    if not uid:
        api_key = request.headers.get('X-Listener-Key', '').strip()
        if api_key and api_key.startswith('ql_'):
            with get_db_session() as _db:
                _row = _db.execute(text(
                    "SELECT id FROM web_users WHERE listener_api_key=:k AND is_banned=0"
                ), {'k': api_key}).fetchone()
                if _row:
                    uid = _row[0]
    with get_db_session() as db:
        # Include user_id guard if we resolved an owner; otherwise deny
        if uid:
            db.execute(text(
                "UPDATE sl_collection_sessions SET last_attempted_boss=:name "
                "WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
            ), {'name': boss_name, 'tok': token, 'uid': uid})
        else:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        db.commit()
    # Push to web tracker immediately so Fighting banner appears instantly
    sse_publish(token, {
        'event':      'focus',
        'boss_name':  boss_name or '',
        'fighting':   bool(boss_name),
    })
    response = JsonResponse({'ok': True})
    response['Access-Control-Allow-Origin'] = '*'
    return response


# ── Boss seed (backfill old sessions that predate unified run type) ───────────

@csrf_exempt
@ratelimit(key='ip', rate='30/m', block=True)
@require_http_methods(['POST'])
def api_sl_seed_bosses(request, token):
    """
    POST /api/soulslike/session/<token>/seed-bosses/
    Seeds sl_session_bosses from the registry if the session has none.
    Called by the run page on load when loadBossRegistry() finds bosses in the
    registry but toggleBoss() would 404 (old pre-unified sessions).
    """
    now = int(time.time())
    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id, game, game_mode FROM sl_collection_sessions "
            "WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid, game, game_mode = session
        existing = db.execute(text(
            "SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=:sid"
        ), {'sid': sid}).scalar() or 0
        if existing > 0:
            return JsonResponse({'ok': True, 'seeded': 0, 'already': existing})
        # Normalize game/mode for old sessions
        g  = 'elden_ring'
        gm = 'err' if (game == 'err') else (game_mode or 'vanilla')
        boss_rows = db.execute(text(
            "SELECT boss_key, boss_name, location, region, tier FROM sl_boss_registry "
            "WHERE game=:g AND game_mode=:gm ORDER BY sort_order"
        ), {'g': g, 'gm': gm}).fetchall()
        for b in boss_rows:
            db.execute(text("""
                INSERT IGNORE INTO sl_session_bosses
                    (session_id, boss_key, boss_name, location, region, tier, game, game_mode)
                VALUES (:sid, :key, :name, :loc, :region, :tier, :g, :gm)
            """), {'sid': sid, 'key': b[0], 'name': b[1], 'loc': b[2],
                   'region': b[3], 'tier': b[4], 'g': g, 'gm': gm})
        db.commit()
    response = JsonResponse({'ok': True, 'seeded': len(boss_rows)})
    response['Access-Control-Allow-Origin'] = '*'
    return response


# ── Boss mark / unmark ────────────────────────────────────────────────────────

@csrf_exempt
@ratelimit(key='ip', rate='120/m', block=True)
@require_http_methods(['POST'])
def api_sl_boss_mark(request, token):
    """POST /api/soulslike/session/<token>/boss/mark/ - mark boss defeated + decay rage. Owner only."""
    uid = _owner_uid_from_request(request)
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    boss_key = sanitize_text(str(data.get('boss_key', ''))[:200])
    if not boss_key:
        return JsonResponse({'error': 'boss_key required'}, status=400)

    now = int(time.time())

    with get_db_session() as db:
        session = db.execute(text("""
            SELECT id, rage_pct, hollow_streak, time_in_hollow_sec,
                   hollow_entered_at
            FROM sl_collection_sessions
            WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL
        """), {'tok': token, 'uid': uid}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        (sid, rage_pct, hollow_streak, time_in_hollow, hollow_entered) = session

        # Get boss tier from session bosses, or seed on-demand from registry
        boss = db.execute(text(
            "SELECT tier, is_defeated, boss_name FROM sl_session_bosses "
            "WHERE session_id=:sid AND boss_key=:key"
        ), {'sid': sid, 'key': boss_key}).fetchone()
        if not boss:
            # Boss not in session yet - look up in registry and seed it
            session_meta = db.execute(text(
                "SELECT game, game_mode FROM sl_collection_sessions WHERE id=:sid"
            ), {'sid': sid}).fetchone()
            if session_meta:
                g = session_meta[0] or 'elden_ring'
                gm = session_meta[1] or 'vanilla'
                reg_boss = db.execute(text(
                    "SELECT boss_name, location, region, tier FROM sl_boss_registry "
                    "WHERE game=:g AND game_mode=:gm AND boss_key=:key LIMIT 1"
                ), {'g': g, 'gm': gm, 'key': boss_key}).fetchone()
                if not reg_boss:
                    # Try with normalized game (old sessions stored game='err')
                    gm2 = 'err' if g == 'err' else gm
                    g2  = 'elden_ring'
                    reg_boss = db.execute(text(
                        "SELECT boss_name, location, region, tier FROM sl_boss_registry "
                        "WHERE game=:g AND game_mode=:gm AND boss_key=:key LIMIT 1"
                    ), {'g': g2, 'gm': gm2, 'key': boss_key}).fetchone()
                if reg_boss:
                    db.execute(text("""
                        INSERT IGNORE INTO sl_session_bosses
                            (session_id, boss_key, boss_name, location, region, tier, game, game_mode)
                        VALUES (:sid, :key, :name, :loc, :region, :tier, :g, :gm)
                    """), {'sid': sid, 'key': boss_key, 'name': reg_boss[0],
                           'loc': reg_boss[1], 'region': reg_boss[2], 'tier': reg_boss[3],
                           'g': g2 if reg_boss else g, 'gm': gm2 if reg_boss else gm})
                    boss = (reg_boss[3], False)
            if not boss:
                return JsonResponse({'error': 'Boss not found in registry'}, status=404)
        if boss[1]:
            return JsonResponse({'ok': True, 'already_defeated': True})

        tier      = boss[0]
        boss_name = boss[2] if len(boss) > 2 else boss_key

        # Track last attempted boss so Listener deaths get labelled correctly
        db.execute(text(
            "UPDATE sl_collection_sessions SET last_attempted_boss=:name WHERE id=:sid"
        ), {'name': boss_name, 'sid': sid})

        # Mark defeated - only if not already defeated (prevents race-condition double-count)
        mark_result = db.execute(text(
            "UPDATE sl_session_bosses SET is_defeated=1, defeated_at=:ts "
            "WHERE session_id=:sid AND boss_key=:key AND is_defeated=0"
        ), {'ts': now, 'sid': sid, 'key': boss_key})
        boss_newly_defeated = mark_result.rowcount > 0

        # ── Hardcore: add points only if boss was just now defeated (not already) ──
        if boss_newly_defeated:
            hc_pts = HC_POINTS.get(tier, 10)
            is_hc = db.execute(text(
                "SELECT is_hardcore FROM sl_collection_sessions WHERE id=:sid"
            ), {'sid': sid}).scalar() or 0
            if is_hc:
                db.execute(text(
                    "UPDATE sl_collection_sessions SET hc_score=hc_score+:pts WHERE id=:sid"
                ), {'pts': hc_pts, 'sid': sid})

        # Rage decay by tier
        old_rage = rage_pct or 0
        was_hollow = old_rage >= 100

        # Track boss kills while hollow (for "From Hollow, Rising" leaderboard)
        if was_hollow:
            db.execute(text(
                "UPDATE sl_collection_sessions SET hollow_boss_kills=hollow_boss_kills+1 WHERE id=:sid"
            ), {'sid': sid})

        if tier == RAGE_TIER_GOD:
            new_rage = 0
        else:
            decay = RAGE_DECAY.get(tier, 25)
            new_rage = max(0, old_rage - decay)

        now_hollow = new_rage >= 100
        new_hollow_streak = hollow_streak or 0
        new_time_in_hollow = time_in_hollow or 0

        # If leaving hollow state, accumulate hollow time
        if was_hollow and not now_hollow and hollow_entered:
            new_time_in_hollow += max(0, now - hollow_entered)

        rage_name = _rage_name(new_rage)

        db.execute(text("""
            UPDATE sl_collection_sessions SET
                rage_pct             = :rage,
                rage_name            = :rage_name,
                time_in_hollow_sec   = :time_hollow,
                hollow_entered_at    = :hollow_entered,
                last_attempted_boss  = NULL
            WHERE id = :sid
        """), {
            'rage': new_rage, 'rage_name': rage_name,
            'time_hollow': new_time_in_hollow,
            'hollow_entered': None if not now_hollow else hollow_entered,
            'sid': sid,
        })
        db.commit()

    # Push boss defeat + rage change to web instantly
    sse_publish(token, {
        'event':       'boss',
        'boss_key':    boss_key,
        'defeated':    True,
        'rage_pct':    new_rage,
        'rage_name':   rage_name,
        'is_hollow':   now_hollow,
        'left_hollow': (was_hollow and not now_hollow),
        'focus':       '',  # clear fighting banner on defeat
    })

    return JsonResponse({
        'ok': True,
        'boss_key':  boss_key,
        'tier':      tier,
        'rage_pct':  new_rage,
        'rage_name': rage_name,
        'is_hollow': now_hollow,
        'left_hollow': (was_hollow and not now_hollow),
    })


@csrf_exempt
@ratelimit(key='ip', rate='120/m', block=True)
@require_http_methods(['POST'])
def api_sl_boss_unmark(request, token):
    """POST /api/soulslike/session/<token>/boss/unmark/ - unmark boss (undo). Owner only."""
    uid = _owner_uid_from_request(request)
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    boss_key = sanitize_text(str(data.get('boss_key', ''))[:200])
    if not boss_key:
        return JsonResponse({'error': 'boss_key required'}, status=400)

    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id FROM sl_collection_sessions WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        ), {'tok': token, 'uid': uid}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        sid = session[0]
        # Get boss name to update last_attempted
        brow = db.execute(text(
            "SELECT boss_name FROM sl_session_bosses WHERE session_id=:sid AND boss_key=:key"
        ), {'sid': sid, 'key': boss_key}).fetchone()
        if brow:
            db.execute(text(
                "UPDATE sl_collection_sessions SET last_attempted_boss=:name WHERE id=:sid"
            ), {'name': brow[0], 'sid': sid})
        db.execute(text(
            "UPDATE sl_session_bosses SET is_defeated=0, defeated_at=NULL "
            "WHERE session_id=:sid AND boss_key=:key"
        ), {'sid': sid, 'key': boss_key})
        db.commit()

    return JsonResponse({'ok': True, 'boss_key': boss_key})


# ── End session ───────────────────────────────────────────────────────────────

@csrf_exempt
@web_login_required
@require_http_methods(['POST'])
def api_sl_session_end(request, token):
    """POST /api/soulslike/session/<token>/end/ - end a run, snapshot leaderboard"""
    now = int(time.time())
    uid = request.web_user.id
    with get_db_session() as db:
        session = db.execute(text("""
            SELECT id, game, game_mode, death_count, total_survival_sec, longest_life_sec,
                   hollow_streak, time_in_hollow_sec, hollow_entered_at,
                   session_start_ts, session_type, rage_pct,
                   hollow_boss_kills, reset_count, listener_session_sec
            FROM sl_collection_sessions
            WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL
        """), {'tok': token, 'uid': uid}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found or already ended'}, status=404)

        (sid, game, game_mode, deaths, total_surv, longest_life,
         hollow_streak, time_in_hollow, hollow_entered, session_start,
         session_type, rage_pct, hollow_boss_kills, reset_count, session_sec) = session

        # Finalize hollow time if still hollow at end
        final_hollow = time_in_hollow or 0
        if (rage_pct or 0) >= 100 and hollow_entered:
            final_hollow += max(0, now - hollow_entered)

        # Session wall clock duration
        session_dur = max(0, now - (session_start or now))

        # Final survival = accumulated + current life if never tracked
        final_surv = total_surv or 0

        # Boss count
        bosses_def = db.execute(text(
            "SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=:sid AND is_defeated=1"
        ), {'sid': sid}).scalar() or 0

        # Deaths per Boss (stored in true_death_rate column)
        death_rate = round((deaths or 0) / bosses_def, 1) if bosses_def >= 1 else 0.0

        # HC: check if completed (all bosses, 0 deaths) and calculate final score
        is_hc = db.execute(text(
            "SELECT is_hardcore, hc_score, hc_completed FROM sl_collection_sessions WHERE id=:sid"
        ), {'sid': sid}).fetchone()
        is_hardcore_run = bool(is_hc and is_hc[0])
        hc_score_val = (is_hc[1] or 0) if is_hc else 0
        hc_completed_val = bool(is_hc and is_hc[2]) if is_hc else False

        if is_hardcore_run:
            # Add item points
            items_pts = (db.execute(text(
                "SELECT COUNT(*) FROM sl_collection_item_status "
                "WHERE session_id=:sid AND is_collected=1"
            ), {'sid': sid}).scalar() or 0) * HC_ITEM_POINTS
            hc_score_val += items_pts
            # Check for deathless completion bonus
            bosses_total = db.execute(text(
                "SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=:sid"
            ), {'sid': sid}).scalar() or 0
            if (deaths or 0) == 0 and bosses_def == bosses_total and bosses_total > 0:
                hc_completed_val = True
                hc_score_val = int(hc_score_val * HC_COMPLETION_MULT)
                db.execute(text(
                    "UPDATE sl_collection_sessions SET hc_completed=1, hc_score=:s WHERE id=:sid"
                ), {'s': hc_score_val, 'sid': sid})

        db.execute(text(
            "UPDATE sl_collection_sessions SET ended_at=:ts, time_in_hollow_sec=:tih WHERE id=:sid"
        ), {'ts': now, 'tih': final_hollow, 'sid': sid})

        # Snapshot to leaderboard - must be public, and HC or have 1+ death
        run_is_public = db.execute(text(
            "SELECT is_public FROM sl_collection_sessions WHERE id=:sid"
        ), {'sid': sid}).scalar() or 0
        should_snapshot = bool(run_is_public) and ((deaths or 0) > 0 or is_hardcore_run)
        if should_snapshot:
            username = getattr(request.web_user, 'username', '') or ''
            db.execute(text("""
                INSERT INTO sl_leaderboard_entries
                    (user_id, username, session_id, game, game_mode,
                     session_deaths, total_survival_sec, longest_life_sec,
                     true_death_rate, hollow_streak, time_in_hollow_sec,
                     bosses_defeated, session_duration_sec,
                     hollow_boss_kills, is_hardcore, hc_score, hc_completed,
                     created_at)
                VALUES
                    (:uid, :uname, :sid, :game, :gmode,
                     :deaths, :surv, :longest,
                     :rate, :hstreak, :tih,
                     :bdef, :dur,
                     :hbk, :hc, :hcs, :hcc,
                     :now)
            """), {
                'uid': uid, 'uname': username, 'sid': sid,
                'game': game or 'elden_ring', 'gmode': game_mode or 'vanilla',
                'deaths': deaths or 0, 'surv': final_surv, 'longest': longest_life or 0,
                'rate': death_rate, 'hstreak': hollow_streak or 0, 'tih': final_hollow,
                'hbk': hollow_boss_kills or 0,
                'hc': 1 if is_hardcore_run else 0,
                'hcs': hc_score_val,
                'hcc': 1 if hc_completed_val else 0,
                'bdef': bosses_def, 'dur': session_dur, 'now': now,
            })

        # Auto-enter into tournaments user registered for
        session_snapshot = {
            'deaths':            deaths or 0,
            'longest_life_sec':  longest_life or 0,
            'true_death_rate':   death_rate,
            'time_in_hollow_sec': final_hollow,
            'hollow_streak':     hollow_streak or 0,
            'bosses_defeated':   bosses_def,
            'hollow_boss_kills': hollow_boss_kills or 0,
            'reset_count':       reset_count or 0,
            'session_sec':       session_sec or session_dur,
            'is_hardcore':       is_hardcore_run,
            'hc_score':          hc_score_val,
            'hc_completed':      hc_completed_val,
        }
        _auto_enter_tournaments(
            db, sid, uid, username,
            game or 'elden_ring', game_mode or 'vanilla',
            session_snapshot, session_start or now, now
        )

        db.commit()
        logger.info("sl_session_end uid=%s sid=%s deaths=%s surv=%ss rate=%.1f",
                    uid, sid, deaths, final_surv, death_rate)

    return JsonResponse({'ok': True})


@csrf_exempt
@require_http_methods(['POST'])
@add_web_user_context
def api_sl_hc_complete(request, token):
    """POST /api/soulslike/session/<token>/hc-complete/ - manual HC completion signal.
    Called by desktop app when player has defeated the final boss deathless.
    Applies the 2x multiplier and marks the run as completed.
    """
    # Auth: web session OR X-Listener-Key (desktop app)
    uid = getattr(request.web_user, 'id', None) if hasattr(request, 'web_user') and request.web_user else None
    if not uid:
        api_key = request.headers.get('X-Listener-Key', '').strip()
        if api_key:
            uid = _resolve_listener_key(request, api_key)
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    now = int(time.time())
    with get_db_session() as db:
        session = db.execute(text("""
            SELECT id, is_hardcore, hc_score, hc_completed, death_count, user_id
            FROM sl_collection_sessions
            WHERE session_token=:tok AND ended_at IS NULL
        """), {'tok': token}).fetchone()

        if not session:
            return JsonResponse({'error': 'Session not found or already ended'}, status=404)

        sid, is_hc, hc_score, hc_completed, deaths, owner_id = session

        if owner_id != uid:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        if not is_hc:
            return JsonResponse({'error': 'Not a hardcore session'}, status=400)

        if hc_completed:
            return JsonResponse({'ok': True, 'already_completed': True, 'hc_score': hc_score})

        if (deaths or 0) > 0:
            return JsonResponse({'error': 'Hardcore run has deaths - cannot complete'}, status=400)

        # Add item points then apply 2x multiplier
        items_collected = db.execute(text(
            "SELECT COUNT(*) FROM sl_collection_item_status "
            "WHERE session_id=:sid AND is_collected=1"
        ), {'sid': sid}).scalar() or 0
        item_pts = items_collected * HC_ITEM_POINTS
        final_score = int((hc_score + item_pts) * HC_COMPLETION_MULT)

        db.execute(text(
            "UPDATE sl_collection_sessions SET hc_completed=1, hc_score=:s WHERE id=:sid"
        ), {'s': final_score, 'sid': sid})
        db.commit()
        logger.info("sl_hc_complete uid=%s sid=%s score=%s", uid, sid, final_score)

    return JsonResponse({'ok': True, 'hc_score': final_score, 'hc_completed': True})


def _owner_uid_from_request(request):
    """
    Resolve the authenticated user ID from web session or X-Listener-Key header.
    Used to enforce owner-only access on write endpoints without @web_login_required
    (which blocks desktop app requests that use API key auth instead of cookies).
    Returns uid int or None if unauthenticated.
    """
    uid = request.session.get('web_user_id') if hasattr(request, 'session') else None
    if uid:
        return uid
    api_key = request.headers.get('X-Listener-Key', '').strip()
    if api_key:
        return _resolve_listener_key(request, api_key)
    return None


def _resolve_listener_key(request, api_key):
    """Resolve X-Listener-Key to user_id. Returns None if invalid or banned."""
    if not api_key or not api_key.startswith('ql_'):
        return None
    with get_db_session() as db:
        row = db.execute(text(
            "SELECT id FROM web_users WHERE listener_api_key=:k AND is_banned=0 LIMIT 1"
        ), {'k': api_key}).fetchone()
        return row[0] if row else None


# ── User's run list ───────────────────────────────────────────────────────────

@web_login_required
@add_web_user_context
def sl_runs(request):
    """List user's collection runs. Auto-archives completed runs older than 30 days."""
    uid = request.web_user.id
    archive_cutoff = int(time.time()) - (30 * 24 * 3600)  # 30 days ago

    with get_db_session() as db:
        # Archive completed runs older than 30 days.
        # ONLY runs where ended_at IS NOT NULL (completed) AND ended_at < cutoff.
        # Active runs (ended_at IS NULL) are NEVER archived regardless of age.
        db.execute(text("""
            UPDATE sl_collection_sessions
            SET is_archived = 1
            WHERE user_id = :uid
              AND ended_at IS NOT NULL
              AND ended_at < :cutoff
              AND (is_archived = 0 OR is_archived IS NULL)
        """), {'uid': uid, 'cutoff': archive_cutoff})
        db.commit()

        rows = db.execute(text("""
            SELECT session_token, build_name, game, started_at, ended_at,
                   death_count, last_death_boss,
                   (SELECT COUNT(*) FROM sl_collection_item_status WHERE session_id=s.id) as total,
                   (SELECT SUM(is_collected) FROM sl_collection_item_status WHERE session_id=s.id) as done,
                   longest_life_sec, listener_session_sec,
                   (SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=s.id AND is_defeated=1) as bosses_killed,
                   (SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=s.id) as bosses_total,
                   game_mode
            FROM sl_collection_sessions s
            WHERE user_id=:uid AND (is_archived = 0 OR is_archived IS NULL)
            ORDER BY started_at DESC LIMIT 30
        """), {'uid': uid}).fetchall()

        # Builds with no active run - ER
        # Exclude if matched by build_id OR by build_name (handles runs started before build_id was tracked)
        er_builds = db.execute(text("""
            SELECT b.id, b.name, b.playstyle_tag, b.total_level, b.is_public,
                   b.share_token, 'elden_ring' as game, 'vanilla' as game_mode
            FROM sl_er_builds b
            WHERE b.user_id=:uid
              AND NOT EXISTS (
                SELECT 1 FROM sl_collection_sessions s
                WHERE s.user_id=:uid AND s.ended_at IS NULL
                  AND (s.build_id=b.id OR s.build_name=b.name)
              )
            ORDER BY b.updated_at DESC LIMIT 20
        """), {'uid': uid}).fetchall()

        # Builds with no active run - ERR
        err_builds = db.execute(text("""
            SELECT b.id, b.name, b.playstyle_tag, b.total_level, b.is_public,
                   b.share_token, 'elden_ring' as game, 'err' as game_mode
            FROM sl_err_builds b
            WHERE b.user_id=:uid
              AND NOT EXISTS (
                SELECT 1 FROM sl_collection_sessions s
                WHERE s.user_id=:uid AND s.ended_at IS NULL
                  AND (s.build_id=b.id OR s.build_name=b.name)
              )
            ORDER BY b.updated_at DESC LIMIT 20
        """), {'uid': uid}).fetchall()

    runs = [
        {
            'token':        r[0],
            'build_name':   r[1],
            'game':         r[2],
            'started_at':   r[3],
            'ended_at':     r[4],
            'is_active':    r[4] is None,
            'deaths':       r[5] or 0,
            'last_death':   r[6] or '',
            'total':        r[7] or 0,
            'collected':    int(r[8] or 0),
            'longest_life': _fmt_time(r[9] or 0),
            'session_time': _fmt_time(r[10] or 0),
            'bosses_killed': r[11] or 0,
            'bosses_total':  r[12] or 0,
            'game_mode':    r[13] or 'vanilla',
        }
        for r in rows
    ]

    idle_builds = [
        {
            'id':          r[0],
            'name':        r[1],
            'playstyle':   r[2] or '',
            'level':       r[3] or 1,
            'is_public':   bool(r[4]),
            'share_token': r[5] or '',
            'game':        r[6],
            'game_mode':   r[7],
            'game_label':  'ERR' if r[7] == 'err' else 'ER',
        }
        for r in (list(er_builds) + list(err_builds))
    ]

    return render(request, 'questlog_web/sl_runs.html', {
        'web_user':    request.web_user,
        'active_page': 'questlog_web_sl_runs',
        'runs':        runs,
        'idle_builds': idle_builds,
    })


@add_web_user_context
def sl_community_runs(request):
    """Public community runs - live and recently completed public runs."""
    game     = request.GET.get('game', '')[:32]
    now      = int(time.time())
    cutoff   = now - (7 * 24 * 3600)  # last 7 days for completed runs

    # R2 runs live in a separate table - handle separately
    if game == 'remnant2':
        with get_db_session() as db:
            r2_rows = db.execute(text("""
                SELECT r.token, r.name, r.run_type, r.is_hardcore, r.is_active,
                       r.death_count, r.bosses_killed, r.items_found,
                       r.created_at, r.completed_at,
                       u.username, u.avatar_url,
                       GROUP_CONCAT(z.world ORDER BY z.world SEPARATOR ', ') as zones
                FROM r2_runs r
                JOIN web_users u ON r.user_id = u.id
                LEFT JOIN r2_run_zones z ON z.run_id = r.id
                WHERE r.is_public = 1 AND u.is_banned = 0
                GROUP BY r.id
                ORDER BY r.is_active DESC, r.created_at DESC LIMIT 50
            """)).fetchall()
        r2_runs_list = [{
            'token': r[0], 'build_name': r[1], 'game': 'remnant2',
            'game_mode': r[2], 'game_label': 'Remnant 2',
            'deaths': r[3] or 0, 'is_active': bool(r[4]),
            'bosses_killed': r[6] or 0, 'items_collected': r[7] or 0,
            'username': r[10], 'avatar': r[11], 'zones': r[12] or '',
            'is_hardcore': bool(r[3]),
        } for r in r2_rows]
        return render(request, 'questlog_web/sl_community_runs.html', {
            'web_user': request.web_user, 'active_page': 'sl_community_runs',
            'runs': r2_runs_list, 'active_count': sum(1 for r in r2_runs_list if r['is_active']),
            'game_filter': game,
        })

    with get_db_session() as db:
        filters = "WHERE s.is_public=1 AND u.is_banned=0 AND (s.is_archived=0 OR s.is_archived IS NULL)"
        params  = {}
        ALLOWED_GAME_FILTERS = {'elden_ring', 'err'}
        if game == 'err':
            filters += " AND s.game_mode='err'"
        elif game == 'elden_ring':
            filters += " AND s.game='elden_ring' AND (s.game_mode IS NULL OR s.game_mode != 'err')"
        elif game and game in ALLOWED_GAME_FILTERS:
            filters += " AND s.game=:game"
            params['game'] = game
        elif game:
            return render(request, 'questlog_web/sl_community_runs.html', {
                'web_user': request.web_user, 'active_page': 'sl_community_runs',
                'runs': [], 'active_count': 0, 'game_filter': game,
            })

        rows = db.execute(text(f"""
            SELECT s.session_token, s.build_name, s.game, s.game_mode,
                   s.death_count, s.ended_at, s.started_at,
                   s.is_hardcore, s.hc_score,
                   s.listener_session_sec, s.total_survival_sec,
                   (SELECT COUNT(*) FROM sl_session_bosses b WHERE b.session_id=s.id AND b.is_defeated=1) as bosses_killed,
                   (SELECT COUNT(*) FROM sl_session_bosses b WHERE b.session_id=s.id) as bosses_total,
                   (SELECT SUM(is_collected) FROM sl_collection_item_status WHERE session_id=s.id) as items_collected,
                   (SELECT COUNT(*) FROM sl_collection_item_status WHERE session_id=s.id) as items_total,
                   u.username, u.avatar_url, u.is_live, u.live_platform,
                   u.twitch_username, u.live_url
            FROM sl_collection_sessions s
            JOIN web_users u ON u.id = s.user_id
            {filters}
              AND (s.ended_at IS NULL OR s.ended_at > :cutoff)
            ORDER BY
                (s.ended_at IS NULL) DESC,  -- active first
                s.started_at DESC
            LIMIT 50
        """), {**params, 'cutoff': cutoff}).fetchall()

    def stream_url(row):
        if not row[17]: return None  # not live
        if row[18] == 'twitch' and row[19]: return f'https://twitch.tv/{row[19]}'
        if row[20]: return row[20]  # live_url
        return None

    runs = [
        {
            'token':       r[0],
            'build_name':  r[1],
            'game':        r[2],
            'game_mode':   r[3] or 'vanilla',
            'game_label':  'ERR' if r[3] == 'err' else 'Elden Ring',
            'deaths':      r[4] or 0,
            'is_active':   r[5] is None,
            'started_at':  r[6],
            'is_hardcore': bool(r[7]),
            'hc_score':    r[8] or 0,
            'session_sec': r[9] or 0,
            'session_fmt': _fmt_time(r[9] or 0),
            'bosses_killed':    r[11] or 0,
            'bosses_total':     r[12] or 0,
            'boss_pct':         round((r[11] or 0) / r[12] * 100) if r[12] else 0,
            'items_collected':  int(r[13] or 0),
            'items_total':      r[14] or 0,
            'username':    r[15],
            'avatar':      r[16] or '',
            'is_live':     bool(r[17]),
            'stream_url':  stream_url(r),
        }
        for r in rows
    ]

    active_count = sum(1 for r in runs if r['is_active'])

    return render(request, 'questlog_web/sl_community_runs.html', {
        'web_user':     request.web_user,
        'active_page':  'sl_community_runs',
        'runs':         runs,
        'active_count': active_count,
        'game_filter':  game,
    })


@add_web_user_context
def sl_leaderboards(request):
    """Public leaderboards - personal + community tabs."""
    return render(request, 'questlog_web/sl_leaderboards.html', {
        'web_user': request.web_user,
        'active_page': 'soulslike_leaderboards',
    })


@require_http_methods(['GET'])
def api_sl_leaderboards(request):
    """
    GET /api/soulslike/leaderboards/
    ?category=longest_life&game=elden_ring&scope=community|personal
    ?api_key=ql_xxx  (desktop app auth)

    Per-session categories (from sl_leaderboard_entries):
      longest_life, true_grit, death_machine, hollow_lord, hollow_depth, boss_slayer

    Lifetime aggregate categories (computed across all sessions):
      tarnished_legend - most total bosses ever killed
      undying          - most deathless completed runs
      veteran          - most completed runs total
    """
    category = request.GET.get('category', 'longest_life')[:30]
    game     = request.GET.get('game', 'elden_ring')[:32]
    scope    = request.GET.get('scope', 'community')[:20]

    # Resolve uid from web session OR API key (desktop app)
    uid = request.session.get('web_user_id') if hasattr(request, 'session') else None
    if not uid:
        ak = request.headers.get('X-Listener-Key', '') or request.GET.get('api_key', '')
        if ak.startswith('ql_'):
            with get_db_session() as _db:
                _u = _db.execute(text(
                    "SELECT id FROM web_users WHERE listener_api_key=:k AND is_banned=0"
                ), {'k': ak}).fetchone()
                if _u:
                    uid = _u[0]

    def fmt(sec):
        sec = int(sec or 0)
        h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
        return f'{h:02d}:{m:02d}:{s:02d}'

    # ── Per-session categories ─────────────────────────────────────────────────
    SESSION_CATEGORIES = {
        'longest_life':  ('longest_life_sec',  'DESC', 'min_deaths', 0),
        'true_grit':     ('true_death_rate',    'ASC',  'min_deaths', 5),
        'death_machine': ('session_deaths',     'DESC', 'min_deaths', 1),
        'hollow_lord':   ('time_in_hollow_sec', 'DESC', 'min_deaths', 1),
        'hollow_depth':  ('hollow_streak',      'DESC', 'min_deaths', 1),
        'boss_slayer':   ('bosses_defeated',    'DESC', 'min_deaths', 1),
        # Hardcore per-session category
        'hc_score':      ('hc_score',           'DESC', 'min_deaths', 0),
    }

    # Full category metadata for API consumers (desktop app, web UI)
    ALL_CATEGORIES = [
        # Per-session
        {'id': 'longest_life',      'name': 'Iron Tarnished',      'desc': 'Longest single life before dying',              'type': 'session',  'min_deaths': 0},
        {'id': 'true_grit',         'name': 'True Grit',           'desc': 'Lowest Deaths/Boss (min 5 deaths)',             'type': 'session',  'min_deaths': 5},
        {'id': 'death_machine',     'name': 'Death Machine',       'desc': 'Most deaths in a single session',              'type': 'session',  'min_deaths': 1},
        {'id': 'hollow_lord',       'name': 'Hollow Lord',         'desc': 'Most time spent in HOLLOW state',              'type': 'session',  'min_deaths': 1},
        {'id': 'hollow_depth',      'name': 'Hollow Depth',        'desc': 'Most times gone hollow in a single session',   'type': 'session',  'min_deaths': 1},
        {'id': 'boss_slayer',       'name': 'Boss Slayer',         'desc': 'Most bosses defeated in a single session',     'type': 'session',  'min_deaths': 1},
        {'id': 'glass_cannon',      'name': 'Glass Cannon',        'desc': 'Highest Deaths/Boss with 5+ bosses killed',    'type': 'session',  'min_deaths': 5},
        {'id': 'from_hollow_rising','name': 'From Hollow, Rising', 'desc': 'Most boss kills while in HOLLOW state',        'type': 'session',  'min_deaths': 1},
        # Lifetime
        {'id': 'tarnished_legend',  'name': 'Tarnished Legend',   'desc': 'Most bosses killed across all runs ever',       'type': 'lifetime', 'min_deaths': 0},
        {'id': 'undying',           'name': 'Undying',            'desc': 'Most completed runs with 0 deaths',             'type': 'lifetime', 'min_deaths': 0},
        {'id': 'veteran',           'name': 'Veteran',            'desc': 'Most completed runs total',                     'type': 'lifetime', 'min_deaths': 0},
        {'id': 'the_grind',         'name': 'The Grind',          'desc': 'Most total hours played across all runs',       'type': 'lifetime', 'min_deaths': 0},
        {'id': 'sisyphus',          'name': 'Sisyphus',           'desc': 'Most resets in a single session',              'type': 'lifetime', 'min_deaths': 0},
        # Hardcore
        {'id': 'hc_score',          'name': 'HC Score',           'desc': 'Highest point score in Hardcore mode (bosses + items = points, death ends run)', 'type': 'hardcore', 'min_deaths': 0},
        {'id': 'hc_completions',    'name': 'HC Completions',     'desc': 'Fastest full clear with 0 deaths in Hardcore mode', 'type': 'hardcore', 'min_deaths': 0},
        {'id': 'hc_perma',          'name': 'Perma Deaths',       'desc': 'Most Hardcore permadeaths - how many times did you die for good?', 'type': 'hardcore', 'min_deaths': 1},
    ]

    # If just requesting the category list (for UI building)
    if request.GET.get('list') == '1':
        return JsonResponse({'categories': ALL_CATEGORIES})

    # ── Lifetime aggregate categories ──────────────────────────────────────────
    LIFETIME_CATEGORIES = {
        'tarnished_legend', 'undying', 'veteran',
        'the_grind', 'glass_cannon', 'from_hollow_rising', 'sisyphus',
        'hc_perma', 'hc_completions',
    }

    with get_db_session() as db:
        if category in LIFETIME_CATEGORIES:
            # These aggregate across ALL completed sessions per user
            is_personal = (scope == 'personal' and uid)

            if category == 'tarnished_legend':
                # Total bosses killed across all sessions
                sql = f"""
                    SELECT u.username, SUM(le.bosses_defeated) as total_bosses,
                           COUNT(le.id) as run_count, u.id as uid
                    FROM sl_leaderboard_entries le
                    JOIN web_users u ON u.id = le.user_id
                    WHERE le.game=:g AND u.is_banned=0
                    {'AND le.user_id=:uid' if is_personal else 'AND le.is_public=1'}
                    GROUP BY le.user_id, u.username
                    HAVING total_bosses > 0
                    ORDER BY total_bosses DESC LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0], 'value': r[1] or 0,
                     'value_fmt': str(r[1] or 0), 'run_count': r[2] or 0,
                     'label': 'Total Bosses Killed'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

            elif category == 'undying':
                # Most deathless completed runs (deaths=0)
                sql = f"""
                    SELECT u.username, COUNT(s.id) as deathless_runs, u.id as uid
                    FROM sl_collection_sessions s
                    JOIN web_users u ON u.id = s.user_id
                    WHERE s.game=:g AND s.ended_at IS NOT NULL
                      AND s.death_count = 0 AND u.is_banned=0
                    {'AND s.user_id=:uid' if is_personal else 'AND s.is_public=1'}
                    GROUP BY s.user_id, u.username
                    HAVING deathless_runs > 0
                    ORDER BY deathless_runs DESC LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0], 'value': r[1] or 0,
                     'value_fmt': str(r[1] or 0), 'label': 'Deathless Runs'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

            elif category == 'veteran':
                # Most completed runs total
                sql = f"""
                    SELECT u.username, COUNT(s.id) as total_runs,
                           SUM(s.death_count) as total_deaths
                    FROM sl_collection_sessions s
                    JOIN web_users u ON u.id = s.user_id
                    WHERE s.game=:g AND s.ended_at IS NOT NULL AND u.is_banned=0
                    {'AND s.user_id=:uid' if is_personal else 'AND s.is_public=1'}
                    GROUP BY s.user_id, u.username
                    HAVING total_runs > 0
                    ORDER BY total_runs DESC LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0], 'value': r[1] or 0,
                     'value_fmt': str(r[1] or 0), 'total_deaths': r[2] or 0,
                     'label': 'Completed Runs'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

            elif category == 'the_grind':
                # Most total hours played across all runs
                sql = f"""
                    SELECT u.username,
                           SUM(s.listener_session_sec) as total_sec,
                           COUNT(s.id) as run_count
                    FROM sl_collection_sessions s
                    JOIN web_users u ON u.id = s.user_id
                    WHERE s.game=:g AND s.ended_at IS NOT NULL AND u.is_banned=0
                      AND s.listener_session_sec > 0
                    {'AND s.user_id=:uid' if is_personal else 'AND s.is_public=1'}
                    GROUP BY s.user_id, u.username
                    HAVING total_sec > 0
                    ORDER BY total_sec DESC LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0], 'value': r[1] or 0,
                     'value_fmt': fmt(r[1] or 0), 'run_count': r[2] or 0,
                     'label': 'Total Time Played'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

            elif category == 'glass_cannon':
                # Highest Deaths/Boss with at least 5 bosses killed - chaos meets skill
                sql = f"""
                    SELECT le.username, le.true_death_rate, le.bosses_defeated,
                           le.session_deaths, le.longest_life_sec
                    FROM sl_leaderboard_entries le
                    JOIN web_users u ON u.id = le.user_id
                    WHERE le.game=:g AND le.bosses_defeated >= 5
                      AND le.session_deaths >= 5 AND u.is_banned=0
                    {'AND le.user_id=:uid' if is_personal else 'AND le.is_public=1'}
                    ORDER BY le.true_death_rate DESC, le.bosses_defeated DESC
                    LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0],
                     'value': round(r[1] or 0, 1),
                     'value_fmt': f'{round(r[1] or 0, 1)}/boss',
                     'bosses_defeated': r[2] or 0,
                     'session_deaths': r[3] or 0,
                     'longest_life_fmt': fmt(r[4] or 0),
                     'label': 'Deaths/Boss'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

            elif category == 'from_hollow_rising':
                # Most boss kills while in HOLLOW state in a single session
                sql = f"""
                    SELECT le.username, le.hollow_boss_kills,
                           le.hollow_streak, le.bosses_defeated
                    FROM sl_leaderboard_entries le
                    JOIN web_users u ON u.id = le.user_id
                    WHERE le.game=:g AND le.hollow_boss_kills > 0 AND u.is_banned=0
                    {'AND le.user_id=:uid' if is_personal else 'AND le.is_public=1'}
                    ORDER BY le.hollow_boss_kills DESC LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0], 'value': r[1] or 0,
                     'value_fmt': str(r[1] or 0),
                     'hollow_streak': r[2] or 0,
                     'bosses_total': r[3] or 0,
                     'label': 'Bosses Killed While Hollow'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

            elif category == 'sisyphus':
                # Most resets in a single session (tracked via reset_count on sessions)
                sql = f"""
                    SELECT u.username, MAX(s.reset_count) as max_resets,
                           SUM(s.reset_count) as total_resets
                    FROM sl_collection_sessions s
                    JOIN web_users u ON u.id = s.user_id
                    WHERE s.game=:g AND s.ended_at IS NOT NULL
                      AND s.reset_count > 0 AND u.is_banned=0
                    {'AND s.user_id=:uid' if is_personal else 'AND s.is_public=1'}
                    GROUP BY s.user_id, u.username
                    HAVING max_resets > 0
                    ORDER BY max_resets DESC LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0], 'value': r[1] or 0,
                     'value_fmt': str(r[1] or 0),
                     'total_resets': r[2] or 0,
                     'label': 'Most Resets in One Session'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

            elif category == 'hc_perma':
                # Lifetime total HC permadeaths - how many HC runs ended in death across all time
                sql = f"""
                    SELECT u.username, COUNT(s.id) as perma_deaths,
                           SUM(s.hc_score) as total_hc_score
                    FROM sl_collection_sessions s
                    JOIN web_users u ON u.id = s.user_id
                    WHERE s.game=:g AND s.ended_at IS NOT NULL
                      AND s.is_hardcore=1 AND s.death_count >= 1
                      AND u.is_banned=0
                    {'AND s.user_id=:uid' if is_personal else 'AND s.is_public=1'}
                    GROUP BY s.user_id, u.username
                    HAVING perma_deaths > 0
                    ORDER BY perma_deaths DESC LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0], 'value': r[1] or 0,
                     'value_fmt': str(r[1] or 0),
                     'total_hc_score': r[2] or 0,
                     'label': 'Perma-Deaths'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

            elif category == 'hc_completions':
                # Fastest deathless HC full clears - lifetime, ordered by best time
                sql = f"""
                    SELECT u.username, MIN(s.listener_session_sec) as best_time,
                           COUNT(s.id) as total_clears, MAX(s.hc_score) as best_score
                    FROM sl_collection_sessions s
                    JOIN web_users u ON u.id = s.user_id
                    WHERE s.game=:g AND s.ended_at IS NOT NULL
                      AND s.is_hardcore=1 AND s.hc_completed=1
                      AND s.death_count=0 AND u.is_banned=0
                    {'AND s.user_id=:uid' if is_personal else 'AND s.is_public=1'}
                    GROUP BY s.user_id, u.username
                    HAVING total_clears > 0
                    ORDER BY best_time ASC LIMIT {'50' if is_personal else '100'}
                """
                params = {'g': game, **({'uid': uid} if is_personal else {})}
                rows = db.execute(text(sql), params).fetchall()
                return JsonResponse({'entries': [
                    {'rank': i+1, 'username': r[0], 'value': r[1] or 0,
                     'value_fmt': _fmt_time(r[1] or 0),
                     'session_dur_fmt': _fmt_time(r[1] or 0),
                     'total_clears': r[2] or 0,
                     'hc_score': r[3] or 0,
                     'label': 'Best Clear Time'}
                    for i, r in enumerate(rows)
                ], 'category': category, 'game': game, 'scope': scope})

        # ── Per-session query ──────────────────────────────────────────────────
        col, direction, _, min_deaths = SESSION_CATEGORIES.get(
            category, ('longest_life_sec', 'DESC', 'min_deaths', 0)
        )
        is_personal = (scope == 'personal' and uid)
        death_filter = f"AND session_deaths >= {int(min_deaths)}" if min_deaths > 0 else ""

        # Hardcore categories require is_hardcore=1 + special filters
        hc_filter = ""
        if category in ('hc_score', 'hc_completions', 'hc_perma'):
            hc_filter = "AND is_hardcore=1"
            if category == 'hc_completions':
                hc_filter += " AND hc_completed=1 AND session_deaths=0"
            elif category == 'hc_perma':
                hc_filter += " AND session_deaths >= 1"

        all_filters = f"{death_filter} {hc_filter}"

        if is_personal:
            rows = db.execute(text(f"""
                SELECT username, session_deaths, total_survival_sec, longest_life_sec,
                       true_death_rate, hollow_streak, time_in_hollow_sec,
                       bosses_defeated, session_duration_sec, game, game_mode, created_at,
                       hc_score, is_hardcore, hc_completed
                FROM sl_leaderboard_entries
                WHERE user_id=:uid AND game=:g {all_filters}
                ORDER BY {col} {direction} LIMIT 50
            """), {'uid': uid, 'g': game}).fetchall()
        else:
            # Community: one best entry per user
            rows = db.execute(text(f"""
                SELECT le.username, le.session_deaths, le.total_survival_sec, le.longest_life_sec,
                       le.true_death_rate, le.hollow_streak, le.time_in_hollow_sec,
                       le.bosses_defeated, le.session_duration_sec, le.game, le.game_mode, le.created_at,
                       le.hc_score, le.is_hardcore, le.hc_completed
                FROM sl_leaderboard_entries le
                INNER JOIN (
                    SELECT user_id, {direction == 'DESC' and 'MAX' or 'MIN'}({col}) as best_val
                    FROM sl_leaderboard_entries
                    WHERE game=:g {all_filters}
                    GROUP BY user_id
                ) best ON le.user_id = best.user_id AND le.{col} = best.best_val
                WHERE le.game=:g {all_filters}
                GROUP BY le.user_id
                ORDER BY le.{col} {direction} LIMIT 100
            """), {'g': game}).fetchall()

    return JsonResponse({'entries': [
        {
            'rank':             i + 1,
            'username':         r[0],
            'session_deaths':   r[1] or 0,
            'survival_fmt':     fmt(r[2]),
            'longest_life_fmt': fmt(r[3]),
            'true_death_rate':  round(r[4] or 0, 1),
            'hollow_streak':    r[5] or 0,
            'hollow_time_fmt':  fmt(r[6]),
            'bosses_defeated':  r[7] or 0,
            'session_dur_fmt':  fmt(r[8]),
            'game':             r[9],
            'game_mode':        r[10] or '',
            'created_at':       r[11],
            'hc_score':         r[12] if len(r) > 12 else 0,
            'is_hardcore':      bool(r[13]) if len(r) > 13 else False,
            'hc_completed':     bool(r[14]) if len(r) > 14 else False,
        }
        for i, r in enumerate(rows)
    ], 'category': category, 'game': game, 'scope': scope})


@add_web_user_context
def sl_run_detail(request, token):
    """Run detail - owner sees full controls; public runs visible to anyone; private = 404 for non-owners."""
    from django.http import Http404
    with get_db_session() as db:
        session = db.execute(text("""
            SELECT s.id, s.build_name, s.game, s.spoiler_mode, s.started_at, s.ended_at,
                   s.death_count, s.last_death_boss, s.user_id, s.session_type, s.game_mode, s.timing_mode,
                   s.total_survival_sec, s.longest_life_sec, s.listener_session_sec,
                   s.hollow_streak, s.time_in_hollow_sec, s.rage_pct,
                   s.is_hardcore, s.hc_score, s.hc_completed, s.is_public,
                   u.username, u.avatar_url, u.is_live, u.live_platform,
                   u.twitch_username, u.youtube_channel_id, u.is_banned, u.live_url,
                   s.session_start_ts
            FROM sl_collection_sessions s
            JOIN web_users u ON u.id = s.user_id
            WHERE s.session_token=:tok
        """), {'tok': token}).fetchone()
        if not session:
            raise Http404

        uid = request.web_user.id if request.web_user else None
        is_owner = uid == session[8]
        is_public = bool(session[21])
        owner_banned = bool(session[28])

        # Non-owners can only view public runs from non-banned users - 404 to avoid confirming existence
        if not is_owner and (not is_public or owner_banned):
            raise Http404

        sid       = session[0]
        is_active = session[5] is None
        summary   = None

        # Owner streaming info
        owner_is_live     = bool(session[24])
        owner_platform    = session[25] or ''
        owner_twitch      = session[26] or ''
        owner_youtube_id  = session[27] or ''
        owner_live_url    = session[29] or ''  # custom stream URL from profile
        stream_url = None
        if owner_is_live:
            if owner_platform == 'twitch' and owner_twitch:
                stream_url = f'https://twitch.tv/{owner_twitch}'
            elif owner_platform == 'youtube' and owner_youtube_id:
                stream_url = f'https://youtube.com/channel/{owner_youtube_id}/live'
            elif owner_live_url:
                stream_url = owner_live_url  # Kick or any other platform set in profile

        if not is_active:
            # Build summary for completed run view
            bosses_killed = db.execute(text(
                "SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=:sid AND is_defeated=1"
            ), {'sid': sid}).scalar() or 0
            bosses_total = db.execute(text(
                "SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=:sid"
            ), {'sid': sid}).scalar() or 0
            items_found = db.execute(text(
                "SELECT COUNT(*) FROM sl_collection_item_status WHERE session_id=:sid AND is_collected=1"
            ), {'sid': sid}).scalar() or 0
            items_total = db.execute(text(
                "SELECT COUNT(*) FROM sl_collection_item_status WHERE session_id=:sid"
            ), {'sid': sid}).scalar() or 0
            death_log = db.execute(text(
                "SELECT boss_name, life_duration_sec FROM sl_death_events WHERE session_id=:sid ORDER BY died_at ASC"
            ), {'sid': sid}).fetchall()

            total_surv    = session[12] or 0
            longest_life  = session[13] or 0
            session_sec   = session[14] or 0
            hollow_streak = session[15] or 0
            deaths        = session[6] or 0
            started_at    = session[4]
            ended_at      = session[5]
            duration_sec  = max(0, (ended_at - started_at)) if ended_at and started_at else session_sec
            deaths_hr     = round(deaths / bosses_killed, 1) if bosses_killed >= 1 else 0.0

            hc_score_summary = db.execute(text(
                "SELECT hc_score, hc_completed FROM sl_collection_sessions WHERE id=:sid"
            ), {'sid': sid}).fetchone()

            summary = {
                'deaths':        deaths,
                'deaths_hr':     deaths_hr,
                'session_time':  _fmt_time(session_sec or duration_sec),
                'longest_life':  _fmt_time(longest_life),
                'survival_time': _fmt_time(total_surv),
                'bosses_killed': bosses_killed,
                'bosses_total':  bosses_total,
                'items_found':   items_found,
                'items_total':   items_total,
                'hollow_streak': hollow_streak,
                'death_log':     [{'boss': d[0] or 'Unknown', 'life': _fmt_time(d[1] or 0)} for d in death_log],
                'hc_score':      hc_score_summary[0] if hc_score_summary else 0,
                'hc_completed':  bool(hc_score_summary[1]) if hc_score_summary else False,
            }

    return render(request, 'questlog_web/sl_run_detail.html', {
        'web_user':    request.web_user,
        'active_page': 'soulslike_hub',
        'token':       token,
        'build_name':  session[1],
        'game':        session[2],
        'spoiler_mode': session[3],
        'run_started_at': session[4] or 0,
        'is_active':   is_active,
        'is_owner':    is_owner,
        'is_public':   is_public,
        'session_type': session[9] or 'run',
        'game_mode':   session[10] or 'vanilla',
        'timing_mode': session[11] or 'listener',
        'session_started': bool(session[30]),
        'is_hardcore': bool(session[18]),
        'hc_score':    session[19] or 0,
        'hc_completed': bool(session[20]),
        # Owner profile for viewer
        'owner_username':  session[22] or '',
        'owner_avatar':    session[23] or '',
        'owner_is_live':   owner_is_live,
        'owner_platform':  owner_platform,
        'stream_url':      stream_url,
        'summary':         summary,
    })


# ── OBS Overlays ─────────────────────────────────────────────────────────────

def sl_overlay_collection(request, token):
    """Collection overlay - OBS/Meld browser source."""
    poll_url = request.build_absolute_uri(f'/api/soulslike/session/{token}/status/')
    response = render(request, 'questlog_web/sl_overlay_collection.html', {
        'token': token,
        'poll_url': poll_url,
    })
    response['Access-Control-Allow-Origin'] = '*'
    return response


def sl_overlay_deaths(request, token):
    """Death counter overlay - OBS/Meld browser source."""
    poll_url = request.build_absolute_uri(f'/api/soulslike/session/{token}/status/')
    response = render(request, 'questlog_web/sl_overlay_deaths.html', {
        'token': token, 'poll_url': poll_url,
    })
    response['Access-Control-Allow-Origin'] = '*'
    return response


def sl_overlay_mortality(request, token):
    """Mortality Monitor overlay - full stats widget for OBS/Meld."""
    poll_url = request.build_absolute_uri(f'/api/soulslike/session/{token}/status/')
    response = render(request, 'questlog_web/sl_overlay_mortality.html', {
        'token': token, 'poll_url': poll_url,
    })
    response['Access-Control-Allow-Origin'] = '*'
    return response


def sl_overlay_hollow(request, token):
    """GONE HOLLOW alert overlay - pops when hollow state triggered."""
    poll_url = request.build_absolute_uri(f'/api/soulslike/session/{token}/status/')
    response = render(request, 'questlog_web/sl_overlay_hollow.html', {
        'token': token, 'poll_url': poll_url,
    })
    response['Access-Control-Allow-Origin'] = '*'
    return response


def sl_overlay_combined(request, token):
    """Combined overlay - Deaths + Rage + Boss Tracker + Items. Single OBS source."""
    poll_url = request.build_absolute_uri(f'/api/soulslike/session/{token}/status/')
    response = render(request, 'questlog_web/sl_overlay_combined.html', {
        'token': token, 'poll_url': poll_url,
    })
    response['Access-Control-Allow-Origin'] = '*'
    return response


def sl_run_manifest(request, token):
    """PWA manifest for a run page - allows "Add to Home Screen" on mobile."""
    import json as _json
    with get_db_session() as db:
        row = db.execute(text(
            "SELECT build_name FROM sl_collection_sessions WHERE session_token=:tok"
        ), {'tok': token}).fetchone()
    name = row[0] if row else 'QuestLog Run'
    manifest = {
        'name': name,
        'short_name': 'QL Run',
        'description': 'QuestLog SoulsLike Run Tracker',
        'start_url': f'/soulslike/runs/{token}/',
        'scope': '/soulslike/runs/',
        'display': 'standalone',
        'background_color': '#0a0a0f',
        'theme_color': '#d97706',
        'orientation': 'portrait-primary',
        'icons': [
            {'src': '/static/img/siteassets/ql-logo.png', 'sizes': 'any', 'type': 'image/png', 'purpose': 'any maskable'},
        ],
    }
    response = JsonResponse(manifest)
    response['Content-Type'] = 'application/manifest+json'
    return response


# ── Desktop app session create (API key auth, no CSRF) ────────────────────────

@csrf_exempt
@ratelimit(key='ip', rate='20/h', block=True)
@require_http_methods(['POST'])
def api_sl_desktop_session_create(request):
    """
    POST /api/soulslike/desktop/session/create/
    Header: X-Listener-Key: ql_xxx
    Same as web session create but authenticated via API key for the desktop app.
    No CSRF needed - API key is the auth.
    """
    from .views_pages import _check_app_version
    gate = _check_app_version(request)
    if gate: return gate
    api_key = request.headers.get('X-Listener-Key', '').strip()
    if not api_key or not api_key.startswith('ql_'):
        return JsonResponse({'error': 'Missing or invalid API key'}, status=401)

    with get_db_session() as _db:
        _u = _db.execute(text(
            "SELECT id FROM web_users WHERE listener_api_key=:k AND is_banned=0"
        ), {'k': api_key}).fetchone()
    if not _u:
        return JsonResponse({'error': 'Invalid API key'}, status=401)

    # Inject user_id so the existing create logic can use request.web_user.id pattern
    class _FakeUser:
        id = _u[0]
    request.web_user = _FakeUser()

    # Delegate entirely to the shared create logic
    return _sl_session_create_inner(request)


def _sl_session_create_inner(request):
    """Shared session create logic used by both web and desktop endpoints."""
    import secrets as _sec
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id      = request.web_user.id
    raw_game     = str(data.get('game', 'elden_ring'))[:32]
    build_name   = sanitize_text(str(data.get('build_name', 'My Build'))[:200])
    spoiler_mode = str(data.get('spoiler_mode', 'region'))[:16]
    game_mode    = str(data.get('game_mode', 'vanilla'))[:32]
    if spoiler_mode not in ('blind', 'region', 'full'):
        spoiler_mode = 'region'
    if raw_game == 'err':
        game = 'elden_ring'
        game_mode = 'err'
    else:
        game = raw_game
        if game_mode not in ('vanilla', 'err'):
            game_mode = 'vanilla'
    session_type = 'run'
    timing_mode  = str(data.get('timing_mode', 'listener'))[:10]
    if timing_mode not in ('listener', 'manual'):
        timing_mode = 'listener'
    is_hardcore  = 1 if data.get('is_hardcore') else 0
    items = data.get('items', [])
    now   = int(time.time())
    token = _sec.token_urlsafe(16)
    build_id = safe_int(data.get('build_id'), None)

    with get_db_session() as db:
        is_public = 0
        if build_id:
            pub_row = db.execute(text(
                "SELECT is_public FROM sl_er_builds WHERE id=:bid AND user_id=:uid "
                "UNION SELECT is_public FROM sl_err_builds WHERE id=:bid AND user_id=:uid LIMIT 1"
            ), {'bid': build_id, 'uid': user_id}).fetchone()
            if pub_row:
                is_public = 1 if pub_row[0] else 0

        db.execute(text("""
            INSERT INTO sl_collection_sessions
                (build_id, game, user_id, spoiler_mode, build_name, started_at,
                 session_type, game_mode, timing_mode, is_hardcore, is_public,
                 session_start_ts, current_life_start,
                 total_survival_sec, longest_life_sec, rage_pct, rage_name,
                 hollow_streak, time_in_hollow_sec)
            VALUES (:bid, :game, :uid, :sm, :bn, :ts,
                    :stype, :gmode, :tmode, :hc, :pub, :ts, :ts,
                    0, 0, 0, 'Maiden''s Grace', 0, 0)
        """), {
            'bid': build_id,
            'game': game, 'uid': user_id,
            'sm': spoiler_mode, 'bn': build_name, 'ts': now,
            'stype': session_type, 'gmode': game_mode, 'tmode': timing_mode,
            'hc': is_hardcore, 'pub': is_public,
        })
        session_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        db.execute(text(
            "UPDATE sl_collection_sessions SET session_token=:tok WHERE id=:sid"
        ), {'tok': token, 'sid': session_id})

        boss_rows = db.execute(text(
            "SELECT boss_key, boss_name, location, region, tier FROM sl_boss_registry "
            "WHERE game=:g AND game_mode=:gm ORDER BY sort_order"
        ), {'g': game, 'gm': game_mode}).fetchall()
        for b in boss_rows:
            db.execute(text("""
                INSERT IGNORE INTO sl_session_bosses
                    (session_id, boss_key, boss_name, location, region, tier, game, game_mode)
                VALUES (:sid, :key, :name, :loc, :region, :tier, :g, :gm)
            """), {'sid': session_id, 'key': b[0], 'name': b[1],
                   'loc': b[2], 'region': b[3], 'tier': b[4],
                   'g': game, 'gm': game_mode})

        for item in items[:200]:
            itype = str(item.get('item_type', 'weapon'))[:16]
            iid   = safe_int(item.get('item_id'), 0) or 0  # 0 for non-DB items
            iname = sanitize_text(str(item.get('item_name', ''))[:200])
            hint  = sanitize_text(str(item.get('location_hint', ''))[:300])
            if not iname:
                continue
            db.execute(text("""
                INSERT INTO sl_collection_item_status
                    (session_id, item_type, item_id, item_name, location_hint, is_collected, collection_method)
                VALUES (:sid, :itype, :iid, :iname, :hint, 0, NULL)
            """), {'sid': session_id, 'itype': itype, 'iid': iid, 'iname': iname, 'hint': hint})

        logger.info("sl_session_create uid=%s game=%s/%s session_id=%s bosses=%d items=%d",
                    user_id, game, game_mode, session_id, len(boss_rows), len(items))
        db.commit()

    def _url(path):
        return f'https://questlog.casual-heroes.com{path}'

    return JsonResponse({
        'ok': True,
        'session_id':     session_id,
        'token':          token,
        'overlay_combined':   _url(f'/soulslike/overlay/{token}/combined/'),
        'overlay_mortality':  _url(f'/soulslike/overlay/{token}/mortality/'),
        'overlay_deaths':     _url(f'/soulslike/overlay/{token}/deaths/'),
        'overlay_hollow':     _url(f'/soulslike/overlay/{token}/hollow/'),
        'overlay_collection': _url(f'/soulslike/overlay/{token}/collection/'),
        'manage_url':         _url(f'/soulslike/runs/{token}/'),
    })


# ── Server-Sent Events (real-time push) ───────────────────────────────────────

import threading as _threading

# In-memory registry of active SSE subscribers per session token
# { token: [queue, queue, ...] }
_SSE_SUBSCRIBERS = {}
_SSE_LOCK = _threading.Lock()


def sse_publish(token, data):
    """
    Push data to all browser clients subscribed to this session.
    Called by death, heartbeat, boss mark etc whenever state changes.
    data = dict that will be JSON-encoded and sent as SSE event.
    """
    with _SSE_LOCK:
        queues = _SSE_SUBSCRIBERS.get(token, [])
        dead = []
        for q in queues:
            try:
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            queues.remove(q)


@csrf_exempt
@require_http_methods(['GET'])
def api_sl_stream(request, token):
    """
    GET /api/soulslike/session/<token>/stream/
    Server-Sent Events stream. Browser connects once, server pushes updates instantly.
    No auth needed - token is the secret (same as all other session endpoints).
    """
    import queue as _queue

    q = _queue.Queue(maxsize=50)

    with _SSE_LOCK:
        if token not in _SSE_SUBSCRIBERS:
            _SSE_SUBSCRIBERS[token] = []
        # Cap at 20 concurrent SSE connections per session token (prevents memory exhaustion)
        if len(_SSE_SUBSCRIBERS[token]) >= 20:
            return JsonResponse({'error': 'Too many concurrent stream connections'}, status=429)
        _SSE_SUBSCRIBERS[token].append(q)

    def event_stream():
        # Send initial ping so browser knows it's connected
        yield 'event: connected\ndata: {"ok":true}\n\n'
        try:
            while True:
                try:
                    data = q.get(timeout=25)  # 25s timeout = keep-alive ping
                    yield f'data: {json.dumps(data)}\n\n'
                except _queue.Empty:
                    # Keep-alive ping to prevent proxy timeout
                    yield ': ping\n\n'
        except GeneratorExit:
            pass
        finally:
            with _SSE_LOCK:
                subs = _SSE_SUBSCRIBERS.get(token, [])
                if q in subs:
                    subs.remove(q)

    response = HttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control']     = 'no-cache'
    response['X-Accel-Buffering'] = 'no'   # disable nginx buffering
    response['Access-Control-Allow-Origin'] = '*'
    return response


# =============================================================================
# TOURNAMENTS
# =============================================================================

def _fmt_time(sec):
    sec = int(sec or 0)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f'{h:02d}:{m:02d}:{s:02d}'


def _get_score_for_category(category: str, session_data: dict):
    """Returns (score_numeric, score_fmt) or (None, None) if doesn't qualify."""
    c = category
    deaths = session_data.get('deaths', 0) or 0
    bosses = session_data.get('bosses_defeated', 0) or 0

    if c == 'longest_life':
        v = session_data.get('longest_life_sec', 0) or 0
        return (v, _fmt_time(v))
    elif c == 'true_grit':
        if deaths < 5: return (None, None)
        v = session_data.get('true_death_rate', 0) or 0
        # Store as negative so DESC sort = lowest rate wins
        return (-round(v, 4), f'{round(v, 1)}/hr')
    elif c == 'death_machine':
        return (deaths, str(deaths))
    elif c == 'hollow_lord':
        v = session_data.get('time_in_hollow_sec', 0) or 0
        return (v, _fmt_time(v))
    elif c == 'hollow_depth':
        v = session_data.get('hollow_streak', 0) or 0
        return (v, str(v))
    elif c == 'boss_slayer':
        return (bosses, str(bosses))
    elif c == 'glass_cannon':
        if deaths < 5 or bosses < 5: return (None, None)
        v = session_data.get('true_death_rate', 0) or 0
        return (round(v, 4), f'{round(v, 1)}/hr ({bosses} bosses)')
    elif c == 'from_hollow_rising':
        v = session_data.get('hollow_boss_kills', 0) or 0
        return (v, str(v))
    elif c == 'undying':
        return (1, '1 deathless run') if deaths == 0 else (None, None)
    elif c == 'tarnished_legend':
        return (bosses, str(bosses)) if bosses > 0 else (None, None)
    elif c == 'veteran':
        return (1, '1 run')
    elif c == 'the_grind':
        v = session_data.get('session_sec', 0) or 0
        return (v, _fmt_time(v)) if v > 0 else (None, None)
    elif c == 'sisyphus':
        v = session_data.get('reset_count', 0) or 0
        return (v, str(v)) if v > 0 else (None, None)
    elif c == 'hc_score':
        if not session_data.get('is_hardcore'): return (None, None)
        v = session_data.get('hc_score', 0) or 0
        return (v, f'{v} pts') if v > 0 else (None, None)
    elif c == 'hc_completions':
        if not session_data.get('is_hardcore'): return (None, None)
        if not session_data.get('hc_completed') or deaths > 0: return (None, None)
        v = session_data.get('session_sec', 0) or 0
        # Store as negative so DESC sort = fastest time wins
        return (-v, _fmt_time(v)) if v > 0 else (None, None)
    elif c == 'hc_perma':
        if not session_data.get('is_hardcore'): return (None, None)
        return (1, '1 perma-death') if deaths > 0 else (None, None)
    elif c.startswith('custom:'):
        # Custom tournaments - score = bosses defeated (a reasonable default)
        return (bosses, str(bosses)) if bosses > 0 else (deaths, str(deaths))
    return (None, None)


def _auto_enter_tournaments(db, sid: int, uid: int, username: str,
                             game: str, game_mode: str,
                             session_data: dict, started_at: int, now: int):
    """
    Called at session end. Enters the run into all tournaments the user
    registered for, where this session started within the tournament window.
    Only runs that started AND ended within the window count.
    """
    # Find tournaments user registered for that match this run
    tournaments = db.execute(text("""
        SELECT t.id, t.category, t.starts_at, t.ends_at
        FROM sl_tournament_registrations r
        JOIN sl_tournaments t ON t.id = r.tournament_id
        WHERE r.user_id = :uid
          AND t.game = :g AND t.game_mode = :gm
          AND t.is_active = 1 AND t.is_finalized = 0
          AND t.starts_at <= :started
          AND t.ends_at >= :now
    """), {'uid': uid, 'g': game, 'gm': game_mode,
           'started': started_at, 'now': now}).fetchall()

    for tid, cat, tstart, tend in tournaments:
        score, score_fmt = _get_score_for_category(cat, session_data)
        if score is None:
            continue

        try:
            # Upsert - keep best score per user per tournament
            db.execute(text("""
                INSERT INTO sl_tournament_entries
                    (tournament_id, user_id, username, session_id,
                     score, score_fmt, created_at)
                VALUES (:tid, :uid, :uname, :sid, :score, :sfmt, :now)
                ON DUPLICATE KEY UPDATE
                    score = GREATEST(score, :score),
                    score_fmt = IF(score < :score, :sfmt, score_fmt),
                    session_id = IF(score < :score, :sid, session_id)
            """), {
                'tid': tid, 'uid': uid, 'uname': username,
                'sid': sid, 'score': float(score),
                'sfmt': score_fmt, 'now': now
            })
            logger.info("tournament_entry uid=%s tid=%s cat=%s score=%s",
                        uid, tid, cat, score)
        except Exception as e:
            logger.warning("tournament_entry failed tid=%s: %s", tid, e)


# ── Tournament register/unregister ───────────────────────────────────────────

@csrf_exempt
@ratelimit(key='ip', rate='30/m', block=True)
@require_http_methods(['POST'])
def api_sl_tournament_join(request, tournament_id):
    """
    POST /api/soulslike/tournaments/<id>/join/
    POST /api/soulslike/tournaments/<id>/leave/
    Opt in or out of a tournament. Web session OR X-Listener-Key.
    """
    leaving = request.path.endswith('/leave/')
    uid = None
    session_uid = request.session.get('web_user_id') if hasattr(request, 'session') else None
    if session_uid:
        # Verify session user is not banned
        with get_db_session() as _db:
            _u = _db.execute(text(
                "SELECT id FROM web_users WHERE id=:uid AND is_banned=0"
            ), {'uid': session_uid}).fetchone()
            if _u: uid = _u[0]
    if not uid:
        ak = request.headers.get('X-Listener-Key', '').strip()
        if ak.startswith('ql_'):
            with get_db_session() as _db:
                _u = _db.execute(text(
                    "SELECT id FROM web_users WHERE listener_api_key=:k AND is_banned=0"
                ), {'k': ak}).fetchone()
                if _u: uid = _u[0]
    if not uid:
        return JsonResponse({'error': 'Authentication required'}, status=401)

    now = int(time.time())
    with get_db_session() as db:
        t = db.execute(text(
            "SELECT id, ends_at, is_finalized FROM sl_tournaments WHERE id=:id"
        ), {'id': tournament_id}).fetchone()
        if not t:
            return JsonResponse({'error': 'Tournament not found'}, status=404)
        if t[2]:
            return JsonResponse({'error': 'Tournament already finalized'}, status=400)
        if t[1] < now:
            return JsonResponse({'error': 'Tournament has ended'}, status=400)

        if leaving:
            db.execute(text(
                "DELETE FROM sl_tournament_registrations "
                "WHERE tournament_id=:tid AND user_id=:uid"
            ), {'tid': tournament_id, 'uid': uid})
        else:
            db.execute(text(
                "INSERT IGNORE INTO sl_tournament_registrations "
                "(tournament_id, user_id, registered_at) VALUES (:tid, :uid, :now)"
            ), {'tid': tournament_id, 'uid': uid, 'now': now})
        db.commit()

    response = JsonResponse({'ok': True, 'joined': not leaving})
    response['Access-Control-Allow-Origin'] = '*'
    return response


# ── Tournament list ───────────────────────────────────────────────────────────

@require_http_methods(['GET'])
def api_sl_tournaments(request):
    """
    GET /api/soulslike/tournaments/
    ?game=elden_ring&status=active|upcoming|past|all
    Returns tournaments with participant counts and user's join status.
    """
    game   = request.GET.get('game', 'elden_ring')[:32]
    status = request.GET.get('status', 'active')[:10]
    now    = int(time.time())

    uid = request.session.get('web_user_id') if hasattr(request, 'session') else None
    if not uid:
        ak = request.headers.get('X-Listener-Key', '') or request.GET.get('api_key', '')
        if ak.startswith('ql_'):
            with get_db_session() as _db:
                _u = _db.execute(text(
                    "SELECT id FROM web_users WHERE listener_api_key=:k"
                ), {'k': ak}).fetchone()
                if _u: uid = _u[0]

    if status == 'active':
        where = "t.starts_at <= :now AND t.ends_at >= :now AND t.is_active=1"
    elif status == 'upcoming':
        where = "t.starts_at > :now AND t.is_active=1"
    elif status == 'past':
        # Only show past tournaments that actually had participants
        where = "(t.ends_at < :now OR t.is_finalized=1)"
        having = "HAVING participant_count > 0"
    else:
        where = "1=1"

    having = locals().get('having', '')

    with get_db_session() as db:
        rows = db.execute(text(f"""
            SELECT t.id, t.name, t.season_type, t.game, t.game_mode,
                   t.category, t.starts_at, t.ends_at,
                   t.is_finalized, t.banner_color, t.description,
                   COUNT(DISTINCT r.user_id) as participant_count,
                   MAX(CASE WHEN r.user_id=:uid THEN 1 ELSE 0 END) as is_joined
            FROM sl_tournaments t
            LEFT JOIN sl_tournament_registrations r ON r.tournament_id=t.id
            WHERE t.game=:g AND {where}
            GROUP BY t.id
            {having}
            ORDER BY t.starts_at DESC LIMIT 100
        """), {'g': game, 'now': now, 'uid': uid or -1}).fetchall()

    def time_str(start, end):
        if now < start:
            d = (start - now) // 86400
            return f'Starts in {d}d' if d > 0 else f'Starts in {(start-now)//3600}h'
        elif now <= end:
            diff = end - now
            d, h = diff // 86400, (diff % 86400) // 3600
            return f'{d}d {h}h left' if d > 0 else f'{h}h left'
        return 'Ended'

    return JsonResponse({'tournaments': [
        {
            'id':                r[0],
            'name':              r[1],
            'season_type':       r[2],
            'game':              r[3],
            'game_mode':         r[4] or 'vanilla',
            'category':          r[5],
            'starts_at':         r[6],
            'ends_at':           r[7],
            'is_finalized':      bool(r[8]),
            'is_active':         r[6] <= now <= r[7],
            'banner_color':      r[9] or '#d97706',
            'description':       r[10] or '',
            'participant_count': r[11] or 0,
            'is_joined':         bool(r[12]),
            'time_str':          time_str(r[6], r[7]),
        }
        for r in rows
    ]})


# ── Tournament detail + live leaderboard ─────────────────────────────────────

@require_http_methods(['GET'])
def api_sl_tournament_detail(request, tournament_id):
    """
    GET /api/soulslike/tournaments/<id>/
    Tournament info + live leaderboard + user's current rank.
    """
    now = int(time.time())
    uid = request.session.get('web_user_id') if hasattr(request, 'session') else None
    if not uid:
        ak = request.headers.get('X-Listener-Key', '') or request.GET.get('api_key', '')
        if ak.startswith('ql_'):
            with get_db_session() as _db:
                _u = _db.execute(text(
                    "SELECT id FROM web_users WHERE listener_api_key=:k"
                ), {'k': ak}).fetchone()
                if _u: uid = _u[0]

    with get_db_session() as db:
        t = db.execute(text("""
            SELECT t.id, t.name, t.season_type, t.game, t.game_mode,
                   t.category, t.starts_at, t.ends_at,
                   t.is_finalized, t.banner_color, t.description,
                   COUNT(DISTINCT r.user_id) as participant_count,
                   MAX(CASE WHEN r.user_id=:uid THEN 1 ELSE 0 END) as is_joined
            FROM sl_tournaments t
            LEFT JOIN sl_tournament_registrations r ON r.tournament_id=t.id
            WHERE t.id=:id GROUP BY t.id
        """), {'id': tournament_id, 'uid': uid or -1}).fetchone()
        if not t:
            return JsonResponse({'error': 'Tournament not found'}, status=404)

        if t[8]:  # finalized
            entries = db.execute(text("""
                SELECT username, final_rank, score, score_fmt, flair_awarded, user_id
                FROM sl_tournament_results
                WHERE tournament_id=:id ORDER BY final_rank LIMIT 100
            """), {'id': tournament_id}).fetchall()
            leaderboard = [
                {'rank': r[1], 'username': r[0], 'score': float(r[2]),
                 'score_fmt': r[3], 'flair_awarded': bool(r[4]),
                 'is_me': r[5] == uid}
                for r in entries
            ]
        else:  # live
            entries = db.execute(text("""
                SELECT username, MAX(score) as best, score_fmt,
                       COUNT(*) as run_count, user_id
                FROM sl_tournament_entries
                WHERE tournament_id=:id
                GROUP BY user_id, username
                ORDER BY best DESC LIMIT 100
            """), {'id': tournament_id}).fetchall()
            leaderboard = [
                {'rank': i+1, 'username': r[0], 'score': float(r[1]),
                 'score_fmt': r[2], 'run_count': r[3], 'is_me': r[4] == uid}
                for i, r in enumerate(entries)
            ]

        # Personal rank
        personal = None
        if uid:
            my_score = db.execute(text(
                "SELECT MAX(score), score_fmt FROM sl_tournament_entries "
                "WHERE tournament_id=:tid AND user_id=:uid GROUP BY user_id"
            ), {'tid': tournament_id, 'uid': uid}).fetchone()
            if my_score:
                my_rank = next((e['rank'] for e in leaderboard if e.get('is_me')), None)
                personal = {'rank': my_rank, 'score': float(my_score[0]),
                            'score_fmt': my_score[1]}

    def time_str(start, end):
        if now < start:
            d = (start - now) // 86400
            return f'Starts in {d}d' if d > 0 else f'Starts in {(start-now)//3600}h'
        elif now <= end:
            diff = end - now
            d, h = diff // 86400, (diff % 86400) // 3600
            return f'{d}d {h}h left' if d > 0 else f'{h}h left'
        return 'Ended'

    return JsonResponse({
        'id':                t[0],
        'name':              t[1],
        'season_type':       t[2],
        'game':              t[3],
        'game_mode':         t[4] or 'vanilla',
        'category':          t[5],
        'starts_at':         t[6],
        'ends_at':           t[7],
        'is_finalized':      bool(t[8]),
        'is_active':         t[6] <= now <= t[7],
        'banner_color':      t[9] or '#d97706',
        'description':       t[10] or '',
        'participant_count': t[11] or 0,
        'is_joined':         bool(t[12]),
        'time_str':          time_str(t[6], t[7]),
        'leaderboard':       leaderboard,
        'personal':          personal,
    })


# ── Admin: finalize + create ──────────────────────────────────────────────────

@web_login_required
@require_http_methods(['POST'])
def api_sl_tournament_finalize(request, tournament_id):
    """Admin only - lock results, award flairs to top 3."""
    if not request.web_user.is_admin:
        return JsonResponse({'error': 'Admin only'}, status=403)
    now = int(time.time())
    with get_db_session() as db:
        t = db.execute(text(
            "SELECT id, prize_flair_id FROM sl_tournaments WHERE id=:id"
        ), {'id': tournament_id}).fetchone()
        if not t:
            return JsonResponse({'error': 'Not found'}, status=404)

        entries = db.execute(text("""
            SELECT user_id, username, MAX(score) as best, score_fmt
            FROM sl_tournament_entries WHERE tournament_id=:id
            GROUP BY user_id, username ORDER BY best DESC LIMIT 100
        """), {'id': tournament_id}).fetchall()

        for i, (fuid, funame, fscore, sfmt) in enumerate(entries):
            rank = i + 1
            flair_awarded = 0
            if rank <= 3 and t[1]:
                flair_awarded = 1
                db.execute(text(
                    "INSERT IGNORE INTO web_user_flairs (user_id, flair_id, earned_at) "
                    "VALUES (:uid, :fid, :now)"
                ), {'uid': fuid, 'fid': t[1], 'now': now})
            db.execute(text("""
                INSERT INTO sl_tournament_results
                    (tournament_id, user_id, username, final_rank,
                     score, score_fmt, flair_awarded, created_at)
                VALUES (:tid, :uid, :uname, :rank, :score, :sfmt, :fa, :now)
                ON DUPLICATE KEY UPDATE final_rank=:rank, flair_awarded=:fa
            """), {'tid': tournament_id, 'uid': fuid, 'uname': funame,
                   'rank': rank, 'score': float(fscore), 'sfmt': sfmt,
                   'fa': flair_awarded, 'now': now})

        db.execute(text(
            "UPDATE sl_tournaments SET is_finalized=1, is_active=0 WHERE id=:id"
        ), {'id': tournament_id})
        db.commit()

    return JsonResponse({'ok': True, 'ranked': len(entries)})


@web_login_required
@require_http_methods(['GET', 'POST'])
def api_sl_admin_tournaments(request, tournament_id=None):
    """Admin: list / create / delete tournaments."""
    if not request.web_user.is_admin:
        return JsonResponse({'error': 'Admin only'}, status=403)

    now = int(time.time())

    # DELETE a specific tournament
    if request.method == 'DELETE' and tournament_id:
        with get_db_session() as db:
            db.execute(text("DELETE FROM sl_tournament_entries WHERE tournament_id=:id"), {'id': tournament_id})
            db.execute(text("DELETE FROM sl_tournament_registrations WHERE tournament_id=:id"), {'id': tournament_id})
            db.execute(text("DELETE FROM sl_tournament_results WHERE tournament_id=:id"), {'id': tournament_id})
            db.execute(text("DELETE FROM sl_tournaments WHERE id=:id"), {'id': tournament_id})
            db.commit()
        return JsonResponse({'ok': True})

    if request.method == 'GET':
        with get_db_session() as db:
            rows = db.execute(text("""
                SELECT t.id, t.name, t.season_type, t.game, t.game_mode,
                       t.category, t.starts_at, t.ends_at,
                       t.is_finalized, t.is_active,
                       COUNT(DISTINCT r.user_id) as participants
                FROM sl_tournaments t
                LEFT JOIN sl_tournament_registrations r ON r.tournament_id=t.id
                GROUP BY t.id ORDER BY t.starts_at DESC LIMIT 200
            """)).fetchall()
        return JsonResponse({'tournaments': [
            {'id': r[0], 'name': r[1], 'season_type': r[2], 'game': r[3],
             'game_mode': r[4], 'category': r[5], 'starts_at': r[6],
             'ends_at': r[7], 'is_finalized': bool(r[8]),
             'is_active': bool(r[9]), 'participants': r[10]}
            for r in rows
        ]})

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        db.execute(text("""
            INSERT INTO sl_tournaments
                (name, description, season_type, game, game_mode, category,
                 starts_at, ends_at, is_active, banner_color, created_by, created_at)
            VALUES
                (:name, :desc, :stype, :game, :gmode, :cat,
                 :start, :end, 1, :color, :uid, :now)
        """), {
            'name':  sanitize_text(str(data.get('name', ''))[:200]),
            'desc':  sanitize_text(str(data.get('description', ''))[:1000]),
            'stype': str(data.get('season_type', 'custom'))[:30],
            'game':  str(data.get('game', 'elden_ring'))[:32],
            'gmode': str(data.get('game_mode', 'vanilla'))[:32],
            'cat':   str(data.get('category', 'longest_life'))[:40],
            'start': safe_int(data.get('starts_at'), now),
            'end':   safe_int(data.get('ends_at'), now + 604800),
            'color': str(data.get('banner_color', '#d97706'))[:20],
            'uid':   request.web_user.id, 'now': now,
        })
        tid = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        db.commit()

    return JsonResponse({'ok': True, 'tournament_id': tid})
