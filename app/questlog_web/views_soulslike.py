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
    Body: {
        build_name, game, spoiler_mode,
        items: [{ item_type, item_id, item_name, location_hint }]
    }
    Creates a collection session and returns the token + overlay URLs.
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
    items = data.get('items', [])
    now   = int(time.time())
    token = secrets.token_urlsafe(16)

    with get_db_session() as db:
        db.execute(text("""
            INSERT INTO sl_collection_sessions
                (build_id, game, user_id, spoiler_mode, build_name, started_at,
                 session_type, game_mode, session_start_ts, current_life_start,
                 total_survival_sec, longest_life_sec, rage_pct, rage_name,
                 hollow_streak, time_in_hollow_sec)
            VALUES (:bid, :game, :uid, :sm, :bn, :ts,
                    :stype, :gmode, :ts, :ts,
                    0, 0, 0, 'Maiden''s Grace',
                    0, 0)
        """), {
            'bid': safe_int(data.get('build_id'), None),
            'game': game, 'uid': user_id,
            'sm': spoiler_mode, 'bn': build_name, 'ts': now,
            'stype': session_type, 'gmode': game_mode,
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

        # If Listener didn't supply a boss name, use last boss the player was attempting
        if not boss and last_attempted_boss:
            boss = last_attempted_boss

        if (death_count or 0) >= 9999:
            return JsonResponse({'error': 'Death count limit reached'}, status=429)

        # ── Survival time calculation ─────────────────────────────────────────
        life_start = life_start or session_start or now
        life_duration = max(0, now - life_start)
        new_total_survival = (total_survival or 0) + life_duration
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
                total_survival_sec = :total_surv,
                longest_life_sec   = :longest,
                rage_pct           = :rage,
                rage_name          = :rage_name,
                hollow_streak      = :hollow_streak,
                time_in_hollow_sec = :time_hollow,
                hollow_entered_at  = :hollow_entered
            WHERE id = :sid
        """), {
            'boss': boss or None, 'now': now,
            'total_surv': new_total_survival, 'longest': new_longest,
            'rage': new_rage, 'rage_name': rage_name,
            'hollow_streak': new_hollow_streak,
            'time_hollow': new_time_in_hollow,
            'hollow_entered': new_hollow_entered,
            'sid': sid,
        })
        db.commit()

        new_death_count = (death_count or 0) + 1

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
                   last_attempted_boss
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
         last_attempted_boss) = session

        is_active   = ended_at is None
        rage_pct    = rage_pct or 0
        rage_name   = rage_name or _rage_name(rage_pct)
        is_hollow   = rage_pct >= 100
        death_count = death_count or 0

        # Listener connection status: connected if pinged within last 10s
        listener_connected = bool(listener_last_ping and (now - listener_last_ping) <= 10)
        # Session time = only time Listener was actively connected
        listener_sec = listener_session_sec or 0
        # If currently connected, add time since last ping
        if listener_connected and listener_last_ping:
            listener_sec += max(0, now - listener_last_ping)

        # Live survival time (current life so far) - only when listener active
        life_start_ts = life_start or now
        current_life_sec = max(0, now - life_start_ts) if (is_active and listener_connected) else 0
        total_surv_live  = (total_survival or 0) + current_life_sec

        # True death/hr = deaths / (total_survival_hours)
        surv_hours = total_surv_live / 3600 if total_surv_live > 0 else 0
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
        'listener_connected':   listener_connected,
        'listener_session_sec': listener_sec,
        'session_time_fmt':     _fmt_time(listener_sec),
        # Survival & timing
        'total_survival_sec':   total_surv_live,
        'survival_time_fmt':    _fmt_time(total_surv_live),
        'current_life_sec':     current_life_sec,
        'current_life_fmt':     _fmt_time(current_life_sec),
        'longest_life_sec':     longest_life or 0,
        'longest_life_fmt':     _fmt_time(longest_life or 0),
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
    Called by QuestLog Listener every 5s while active.
    Accumulates listener_session_sec (true session play time).
    No auth required - token is the secret.
    """
    now = int(time.time())
    with get_db_session() as db:
        row = db.execute(text(
            "SELECT id, listener_last_ping FROM sl_collection_sessions "
            "WHERE session_token=:tok AND ended_at IS NULL"
        ), {'tok': token}).fetchone()
        if not row:
            return JsonResponse({'error': 'Session not found'}, status=404)
        sid, last_ping = row
        # Only add time if last ping was recent (within 10s) - prevents huge jumps on reconnect
        delta = 0
        if last_ping and (now - last_ping) <= 10:
            delta = now - last_ping
        db.execute(text(
            "UPDATE sl_collection_sessions "
            "SET listener_last_ping=:now, listener_session_sec=listener_session_sec+:delta "
            "WHERE id=:sid"
        ), {'now': now, 'delta': delta, 'sid': sid})
        db.commit()
    response = JsonResponse({'ok': True})
    response['Access-Control-Allow-Origin'] = '*'
    return response


@web_login_required
@require_http_methods(['POST'])
def api_sl_reset_deaths(request, token):
    """POST /api/soulslike/session/<token>/reset-deaths/ - reset death counter to 0"""
    uid = request.web_user.id
    with get_db_session() as db:
        result = db.execute(text(
            "UPDATE sl_collection_sessions SET "
            "death_count=0, last_death_boss=NULL, "
            "rage_pct=0, rage_name='Maiden''s Grace', "
            "hollow_streak=0, time_in_hollow_sec=0, hollow_entered_at=NULL, "
            "total_survival_sec=0, longest_life_sec=0, current_life_start=:now "
            "WHERE session_token=:tok AND user_id=:uid AND ended_at IS NULL"
        ), {'tok': token, 'uid': uid, 'now': int(time.time())})
        if result.rowcount:
            db.execute(text(
                "DELETE FROM sl_death_events WHERE session_id=("
                "SELECT id FROM sl_collection_sessions WHERE session_token=:tok)"
            ), {'tok': token})
        db.commit()
    if result.rowcount:
        return JsonResponse({'ok': True})
    return JsonResponse({'error': 'Session not found or already ended'}, status=404)



# ── Set boss focus (for Listener death attribution) ──────────────────────────

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
                rage_pct           = :rage,
                rage_name          = :rage_name,
                time_in_hollow_sec = :time_hollow,
                hollow_entered_at  = :hollow_entered
            WHERE id = :sid
        """), {
            'rage': new_rage, 'rage_name': rage_name,
            'time_hollow': new_time_in_hollow,
            'hollow_entered': None if not now_hollow else hollow_entered,
            'sid': sid,
        })
        db.commit()

    return JsonResponse({
        'ok': True,
        'boss_key': boss_key,
        'tier': tier,
        'rage_pct': new_rage,
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
    """List user's collection runs."""
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT session_token, build_name, game, started_at, ended_at,
                   death_count, last_death_boss,
                   (SELECT COUNT(*) FROM sl_collection_item_status WHERE session_id=s.id) as total,
                   (SELECT SUM(is_collected) FROM sl_collection_item_status WHERE session_id=s.id) as done
            FROM sl_collection_sessions s
            WHERE user_id=:uid ORDER BY started_at DESC LIMIT 20
        """), {'uid': request.web_user.id}).fetchall()

    runs = [
        {
            'token':      r[0],
            'build_name': r[1],
            'game':       r[2],
            'started_at': r[3],
            'ended_at':   r[4],
            'is_active':  r[4] is None,
            'deaths':     r[5] or 0,
            'last_death': r[6] or '',
            'total':      r[7] or 0,
            'collected':  int(r[8] or 0),
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
                   death_count, last_death_boss, user_id, session_type, game_mode
            FROM sl_collection_sessions WHERE session_token=:tok
        """), {'tok': token}).fetchone()
        if not session:
            raise Http404

    is_owner = request.web_user and request.web_user.id == session[8]
    # Non-owners get a 403 - run detail is private management view
    if not is_owner:
        from django.http import HttpResponseForbidden
        return HttpResponseForbidden('This run belongs to another user.')

    return render(request, 'questlog_web/sl_run_detail.html', {
        'web_user': request.web_user,
        'active_page': 'soulslike',
        'token': token,
        'build_name': session[1],
        'game': session[2],
        'spoiler_mode': session[3],
        'is_active': session[5] is None,
        'is_owner': True,
        'session_type': session[9] or 'run',
        'game_mode': session[10] or 'vanilla',
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
