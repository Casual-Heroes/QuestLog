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
    items = data.get('items', [])
    now   = int(time.time())
    token = secrets.token_urlsafe(16)

    with get_db_session() as db:
        db.execute(text("""
            INSERT INTO sl_collection_sessions
                (build_id, game, user_id, spoiler_mode, build_name, started_at,
                 session_type, game_mode, timing_mode, session_start_ts, current_life_start,
                 total_survival_sec, longest_life_sec, rage_pct, rage_name,
                 hollow_streak, time_in_hollow_sec)
            VALUES (:bid, :game, :uid, :sm, :bn, :ts,
                    :stype, :gmode, :tmode, :ts, :ts,
                    0, 0, 0, 'Maiden''s Grace',
                    0, 0)
        """), {
            'bid': safe_int(data.get('build_id'), None),
            'game': game, 'uid': user_id,
            'sm': spoiler_mode, 'bn': build_name, 'ts': now,
            'stype': session_type, 'gmode': game_mode, 'tmode': timing_mode,
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
        for item in items[:100]:
            itype = str(item.get('item_type', 'weapon'))[:16]
            iid   = safe_int(item.get('item_id'), None)
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
    Marks an item as collected. No login required - token is the auth.
    """
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
            "SELECT id FROM sl_collection_sessions WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
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
    Unmarks an item (web mode - user misclicked).
    """
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    item_name = sanitize_text(str(data.get('item_name', ''))[:200])

    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id FROM sl_collection_sessions WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
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
                   last_attempted_boss
            FROM sl_collection_sessions WHERE session_token=:tok AND ended_at IS NULL
        """), {'tok': token}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)

        (sid, death_count, life_start, total_survival, longest_life,
         rage_pct, hollow_streak, time_in_hollow, hollow_entered, session_start,
         last_attempted_boss) = session

        # Only use last_attempted_boss fallback for Listener deaths (source='listener')
        # Manual web deaths (source='manual') should NOT inherit the last boss
        source = sanitize_text(str(data.get('source', 'listener'))[:20])
        if not boss and last_attempted_boss and source == 'listener':
            boss = last_attempted_boss

        if (death_count or 0) >= 9999:
            return JsonResponse({'error': 'Death count limit reached'}, status=429)

        # ── Survival time / longest life ──────────────────────────────────────
        # total_survival_sec is accumulated by heartbeat (game-running only).
        # On death we just snapshot the current life duration from the heartbeat
        # delta since last death, stored in listener_session_sec diff.
        # We use current_life_start only to compute longest life - NOT to add
        # to total_survival (heartbeat already did that second by second).
        life_start_ts = life_start or now
        life_duration = max(0, now - life_start_ts) if life_start else 0
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
                death_count        = death_count + 1,
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

        new_death_count = (death_count or 0) + 1

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
        'total_deaths':   new_death_count,
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
                   app_session_sec, app_streak_sec, app_longest_sec
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
         app_session_sec, app_streak_sec, app_longest_sec) = session

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
            grace_remaining = max(0, 600 - elapsed)
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

        # Deaths/HR = deaths / cumulative alive time
        # When app is connected: total_survival_sec IS the cumulative alive time (app keeps it accurate)
        # When web-only: total_survival_sec is server-accumulated
        cumulative_alive = total_survival or 0
        surv_hours = cumulative_alive / 3600 if cumulative_alive > 0 else 0
        true_death_rate = round(death_count / surv_hours, 1) if surv_hours > 0.01 else 0.0

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
        # Survival & timing
        # survival_time = current life streak (resets on death, like "days without accident")
        'survival_time_sec':    current_life_sec,
        'survival_time_fmt':    _fmt_time(current_life_sec),
        'current_life_sec':     current_life_sec,
        'current_life_fmt':     _fmt_time(current_life_sec),
        'longest_life_sec':     (app_longest_sec or longest_life or 0) if has_app_timers else (longest_life or 0),
        'longest_life_fmt':     _fmt_time((app_longest_sec or longest_life or 0) if has_app_timers else (longest_life or 0)),
        'true_death_rate':      true_death_rate,
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
    # App reports authoritative timer values - server stores them directly
    app_session_sec  = int(body.get('session_sec',  -1))
    app_streak_sec   = int(body.get('streak_sec',   -1))
    app_longest_sec  = int(body.get('longest_sec',  -1))
    app_survival_sec = int(body.get('survival_sec', -1))  # cumulative alive time for D/HR

    GRACE_PERIOD_SEC = 600  # 10 minutes - covers crashes and alt-tab freezes

    with get_db_session() as db:
        row = db.execute(text(
            "SELECT id, listener_last_ping, listener_game_running, game_stopped_at "
            "FROM sl_collection_sessions "
            "WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
        if not row:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid, last_ping, was_game_running, game_stopped_at = row

        # Only accumulate time if last ping was recent (within 10s)
        delta = 0
        if last_ping and (now - last_ping) <= 10:
            delta = now - last_ping

        if game_running:
            if app_session_sec >= 0:
                # App is the source of truth - use its timer values directly
                surv = app_survival_sec if app_survival_sec >= 0 else max(0, app_streak_sec)
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=1, "
                    "    game_stopped_at=NULL, "
                    "    listener_session_sec=:sess, "
                    "    total_survival_sec=:surv, "
                    "    longest_life_sec=GREATEST(longest_life_sec, :longest), "
                    "    app_session_sec=:sess, app_streak_sec=:streak, app_longest_sec=:longest "
                    "WHERE id=:sid"
                ), {'now': now, 'sid': sid,
                    'sess':   app_session_sec,
                    'surv':   surv,
                    'streak': max(0, app_streak_sec),
                    'longest': max(0, app_longest_sec)})
            elif game_stopped_at and (now - game_stopped_at) > GRACE_PERIOD_SEC:
                # Grace period expired, no app timers - reset server timers
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=1, "
                    "    game_stopped_at=NULL, "
                    "    listener_session_sec=:delta, total_survival_sec=:delta "
                    "WHERE id=:sid"
                ), {'now': now, 'delta': delta, 'sid': sid})
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
                # Grace period expired while game was stopped - reset session time
                db.execute(text(
                    "UPDATE sl_collection_sessions "
                    "SET listener_last_ping=:now, listener_game_running=0, "
                    "    game_stopped_at=NULL, "
                    "    listener_session_sec=0, total_survival_sec=0 "
                    "WHERE id=:sid"
                ), {'now': now, 'sid': sid})
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

    response = JsonResponse({'ok': True})
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
        # Resolve session - check ownership via web session OR allow token-only access
        uid = request.session.get('web_user_id') if hasattr(request, 'session') else None
        if uid:
            where = "session_token=:tok AND user_id=:uid AND ended_at IS NULL"
            params = {'tok': token, 'uid': uid, 'now': now}
        else:
            # Desktop app - token is the auth (no web session)
            where = "session_token=:tok AND ended_at IS NULL"
            params = {'tok': token, 'now': now}

        result = db.execute(text(
            f"UPDATE sl_collection_sessions SET "
            "death_count=0, last_death_boss=NULL, last_attempted_boss=NULL, "
            "rage_pct=0, rage_name='Maiden''s Grace', "
            "hollow_streak=0, time_in_hollow_sec=0, hollow_entered_at=NULL, "
            "total_survival_sec=0, longest_life_sec=0, current_life_start=:now, "
            "listener_session_sec=0, "
            "app_session_sec=0, app_streak_sec=0, app_longest_sec=0 "
            f"WHERE {where}"
        ), params)
        if result.rowcount:
            db.execute(text(
                "DELETE FROM sl_death_events WHERE session_id=("
                "SELECT id FROM sl_collection_sessions WHERE session_token=:tok)"
            ), {'tok': token})
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
            "SELECT id, death_count, rage_pct, hollow_streak FROM sl_collection_sessions "
            "WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid, death_count, rage_pct, hollow_streak = session
        if (death_count or 0) <= 0:
            return JsonResponse({'ok': True, 'deaths': 0})

        # Reverse one death: -1 death, -25% rage
        new_rage = max(0, (rage_pct or 0) - 25)
        new_deaths = max(0, (death_count or 0) - 1)
        new_rage_name = _rage_name(new_rage)

        # Remove the most recent death event
        db.execute(text(
            "DELETE FROM sl_death_events WHERE id = ("
            "SELECT id FROM sl_death_events WHERE session_id=:sid "
            "ORDER BY died_at DESC LIMIT 1)"
        ), {'sid': sid})

        db.execute(text(
            "UPDATE sl_collection_sessions SET "
            "death_count=:deaths, rage_pct=:rage, rage_name=:rname, "
            "hollow_streak=GREATEST(0, hollow_streak - CASE WHEN :rage < 100 AND :old_rage >= 100 THEN 1 ELSE 0 END) "
            "WHERE id=:sid"
        ), {'deaths': new_deaths, 'rage': new_rage, 'rname': new_rage_name,
            'old_rage': rage_pct or 0, 'sid': sid})
        db.commit()

    response = JsonResponse({'ok': True, 'deaths': new_deaths, 'rage_pct': new_rage, 'rage_name': new_rage_name})
    response['Access-Control-Allow-Origin'] = '*'
    return response


# ── Active runs for EldenTracker on launch ───────────────────────────────────

@ratelimit(key='ip', rate='30/m', block=True)
@require_http_methods(['GET'])
def api_sl_active_runs(request):
    """
    GET /api/soulslike/runs/active/
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
        db.execute(text(
            "UPDATE sl_collection_sessions SET timing_mode='manual', "
            "session_start_ts=COALESCE(session_start_ts, :now), "
            "current_life_start=COALESCE(current_life_start, :now) "
            "WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL "
            "AND timing_mode != 'listener'"
        ), {'tok': token, 'uid': uid, 'now': now})
        db.commit()
    return JsonResponse({'ok': True})


@csrf_exempt
@ratelimit(key='ip', rate='60/m', block=True)
@require_http_methods(['POST'])
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
    with get_db_session() as db:
        db.execute(text(
            "UPDATE sl_collection_sessions SET last_attempted_boss=:name "
            "WHERE session_token=:tok AND ended_at IS NULL"
        ), {'name': boss_name, 'tok': token})
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
    """POST /api/soulslike/session/<token>/boss/mark/ - mark boss defeated + decay rage"""
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
            WHERE session_token=:tok AND ended_at IS NULL
        """), {'tok': token}).fetchone()
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

        # Mark defeated
        db.execute(text(
            "UPDATE sl_session_bosses SET is_defeated=1, defeated_at=:ts "
            "WHERE session_id=:sid AND boss_key=:key"
        ), {'ts': now, 'sid': sid, 'key': boss_key})

        # Rage decay by tier
        old_rage = rage_pct or 0
        was_hollow = old_rage >= 100

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
    """POST /api/soulslike/session/<token>/boss/unmark/ - unmark boss (undo)"""
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    boss_key = sanitize_text(str(data.get('boss_key', ''))[:200])
    if not boss_key:
        return JsonResponse({'error': 'boss_key required'}, status=400)

    with get_db_session() as db:
        session = db.execute(text(
            "SELECT id FROM sl_collection_sessions WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
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
                   session_start_ts, session_type, rage_pct
            FROM sl_collection_sessions
            WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL
        """), {'tok': token, 'uid': uid}).fetchone()
        if not session:
            return JsonResponse({'error': 'Session not found or already ended'}, status=404)

        (sid, game, game_mode, deaths, total_surv, longest_life,
         hollow_streak, time_in_hollow, hollow_entered, session_start,
         session_type, rage_pct) = session

        # Finalize hollow time if still hollow at end
        final_hollow = time_in_hollow or 0
        if (rage_pct or 0) >= 100 and hollow_entered:
            final_hollow += max(0, now - hollow_entered)

        # Session wall clock duration
        session_dur = max(0, now - (session_start or now))

        # Final survival = accumulated + current life if never tracked
        final_surv = total_surv or 0

        # True death/hr
        surv_hr = final_surv / 3600 if final_surv > 0 else 0
        death_rate = round((deaths or 0) / surv_hr, 2) if surv_hr > 0.01 else 0.0

        # Boss count
        bosses_def = db.execute(text(
            "SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=:sid AND is_defeated=1"
        ), {'sid': sid}).scalar() or 0

        db.execute(text(
            "UPDATE sl_collection_sessions SET ended_at=:ts, time_in_hollow_sec=:tih WHERE id=:sid"
        ), {'ts': now, 'tih': final_hollow, 'sid': sid})

        # Snapshot to leaderboard for any run with at least 1 death
        if (deaths or 0) > 0:
            username = getattr(request.web_user, 'username', '') or ''
            db.execute(text("""
                INSERT INTO sl_leaderboard_entries
                    (user_id, username, session_id, game, game_mode,
                     session_deaths, total_survival_sec, longest_life_sec,
                     true_death_rate, hollow_streak, time_in_hollow_sec,
                     bosses_defeated, session_duration_sec, created_at)
                VALUES
                    (:uid, :uname, :sid, :game, :gmode,
                     :deaths, :surv, :longest,
                     :rate, :hstreak, :tih,
                     :bdef, :dur, :now)
            """), {
                'uid': uid, 'uname': username, 'sid': sid,
                'game': game or 'elden_ring', 'gmode': game_mode or 'vanilla',
                'deaths': deaths or 0, 'surv': final_surv, 'longest': longest_life or 0,
                'rate': death_rate, 'hstreak': hollow_streak or 0, 'tih': final_hollow,
                'bdef': bosses_def, 'dur': session_dur, 'now': now,
            })

        db.commit()
        logger.info("sl_session_end uid=%s sid=%s deaths=%s surv=%ss rate=%.1f",
                    uid, sid, deaths, final_surv, death_rate)

    return JsonResponse({'ok': True})


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
                   (SELECT COUNT(*) FROM sl_session_bosses WHERE session_id=s.id AND is_defeated=1) as bosses_killed
            FROM sl_collection_sessions s
            WHERE user_id=:uid AND (is_archived = 0 OR is_archived IS NULL)
            ORDER BY started_at DESC LIMIT 30
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
        }
        for r in rows
    ]

    return render(request, 'questlog_web/sl_runs.html', {
        'web_user': request.web_user,
        'active_page': 'soulslike',
        'runs': runs,
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
    """GET /api/soulslike/leaderboards/?category=longest_life&game=elden_ring&scope=community"""
    category = request.GET.get('category', 'longest_life')[:30]
    game     = request.GET.get('game', 'elden_ring')[:32]
    scope    = request.GET.get('scope', 'community')[:20]  # community | personal
    uid      = request.session.get('web_user_id')

    VALID_CATEGORIES = {
        'longest_life':   ('longest_life_sec', 'DESC'),
        'true_grit':      ('true_death_rate',   'ASC'),
        'death_machine':  ('session_deaths',    'DESC'),
        'hollow_lord':    ('time_in_hollow_sec','DESC'),
        'hollow_depth':   ('hollow_streak',     'DESC'),
        'boss_slayer':    ('bosses_defeated',   'DESC'),
    }
    col, direction = VALID_CATEGORIES.get(category, ('longest_life_sec', 'DESC'))

    with get_db_session() as db:
        if scope == 'personal' and uid:
            rows = db.execute(text(f"""
                SELECT username, session_deaths, total_survival_sec, longest_life_sec,
                       true_death_rate, hollow_streak, time_in_hollow_sec,
                       bosses_defeated, session_duration_sec, game, game_mode, created_at
                FROM sl_leaderboard_entries
                WHERE user_id=:uid AND game=:g
                ORDER BY {col} {direction} LIMIT 50
            """), {'uid': uid, 'g': game}).fetchall()
        else:
            rows = db.execute(text(f"""
                SELECT username, session_deaths, total_survival_sec, longest_life_sec,
                       true_death_rate, hollow_streak, time_in_hollow_sec,
                       bosses_defeated, session_duration_sec, game, game_mode, created_at
                FROM sl_leaderboard_entries
                WHERE game=:g
                ORDER BY {col} {direction} LIMIT 100
            """), {'g': game}).fetchall()

    def fmt(sec):
        sec = int(sec or 0)
        h, m, s = sec//3600, (sec%3600)//60, sec%60
        return f'{h:02d}:{m:02d}:{s:02d}'

    return JsonResponse({'entries': [
        {
            'rank':           i + 1,
            'username':       r[0],
            'session_deaths': r[1] or 0,
            'survival_fmt':   fmt(r[2]),
            'longest_life_fmt': fmt(r[3]),
            'true_death_rate':  round(r[4] or 0, 1),
            'hollow_streak':  r[5] or 0,
            'hollow_time_fmt': fmt(r[6]),
            'bosses_defeated': r[7] or 0,
            'session_dur_fmt': fmt(r[8]),
            'game':           r[9],
            'game_mode':      r[10] or '',
            'created_at':     r[11],
        }
        for i, r in enumerate(rows)
    ], 'category': category, 'game': game, 'scope': scope})


@web_login_required
@add_web_user_context
def sl_run_detail(request, token):
    """Manage a single run - web tracking interface. Login required; only the owner sees controls."""
    from django.http import Http404
    with get_db_session() as db:
        session = db.execute(text("""
            SELECT id, build_name, game, spoiler_mode, started_at, ended_at,
                   death_count, last_death_boss, user_id, session_type, game_mode, timing_mode,
                   total_survival_sec, longest_life_sec, listener_session_sec,
                   hollow_streak, time_in_hollow_sec, rage_pct
            FROM sl_collection_sessions WHERE session_token=:tok
        """), {'tok': token}).fetchone()
        if not session:
            raise Http404

        is_owner = request.web_user and request.web_user.id == session[8]
        if not is_owner:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden('This run belongs to another user.')

        is_active = session[5] is None
        summary = None

        if not is_active:
            # Build summary for completed run view
            sid = session[0]
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

            total_surv   = session[12] or 0
            longest_life = session[13] or 0
            session_sec  = session[14] or 0
            hollow_streak = session[15] or 0
            deaths       = session[6] or 0
            started_at   = session[4]
            ended_at     = session[5]
            duration_sec = max(0, (ended_at - started_at)) if ended_at and started_at else session_sec

            surv_hrs     = total_surv / 3600 if total_surv > 0 else 0
            deaths_hr    = round(deaths / surv_hrs, 1) if surv_hrs > 0.01 else 0.0

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
            }

    return render(request, 'questlog_web/sl_run_detail.html', {
        'web_user': request.web_user,
        'active_page': 'soulslike_hub',
        'token': token,
        'build_name': session[1],
        'game': session[2],
        'spoiler_mode': session[3],
        'is_active': is_active,
        'is_owner': True,
        'session_type': session[9] or 'run',
        'game_mode': session[10] or 'vanilla',
        'timing_mode': session[11] or 'listener',
        'summary': summary,
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
        'display': 'standalone',
        'background_color': '#0a0a0f',
        'theme_color': '#d97706',
        'orientation': 'portrait',
        'icons': [
            {'src': '/static/img/siteassets/ql-icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
            {'src': '/static/img/siteassets/ql-icon-512.png', 'sizes': '512x512', 'type': 'image/png'},
        ],
    }
    return JsonResponse(manifest)


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
    items = data.get('items', [])
    now   = int(time.time())
    token = _sec.token_urlsafe(16)

    with get_db_session() as db:
        db.execute(text("""
            INSERT INTO sl_collection_sessions
                (build_id, game, user_id, spoiler_mode, build_name, started_at,
                 session_type, game_mode, timing_mode, session_start_ts, current_life_start,
                 total_survival_sec, longest_life_sec, rage_pct, rage_name,
                 hollow_streak, time_in_hollow_sec)
            VALUES (:bid, :game, :uid, :sm, :bn, :ts,
                    :stype, :gmode, :tmode, :ts, :ts,
                    0, 0, 0, 'Maiden''s Grace', 0, 0)
        """), {
            'bid': safe_int(data.get('build_id'), None),
            'game': game, 'uid': user_id,
            'sm': spoiler_mode, 'bn': build_name, 'ts': now,
            'stype': session_type, 'gmode': game_mode, 'tmode': timing_mode,
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

        for item in items[:100]:
            itype = str(item.get('item_type', 'weapon'))[:16]
            iid   = safe_int(item.get('item_id'), None)
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
