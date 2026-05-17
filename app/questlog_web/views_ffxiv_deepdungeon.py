import time
import logging
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from app.db import get_db_session
from app.questlog_web.models import WebFfxivDeepDungeonRun, WebFfxivDeepDungeonPB, WebUser, WebFfxivCharacter
from app.questlog_web.helpers import get_web_user, web_login_required, add_web_user_context, sanitize_text, safe_int

logger = logging.getLogger(__name__)

DUNGEONS = {
    'potd': {
        'key':        'potd',
        'name':       'Palace of the Dead',
        'short':      'PotD',
        'max_floor':  200,
        'clear_floor': 200,
        'start_floors': [1, 51],
        'milestones': [50, 100, 150, 200],
        'color':      'purple',
        'desc':       'Floors 1-200. Solo or party (1-4). 0 KOs required to enter 101-200.',
        'solo_title': 'The Necromancer',
        'icon':       'fa-skull',
    },
    'hoh': {
        'key':        'hoh',
        'name':       'Heaven on High',
        'short':      'HoH',
        'max_floor':  100,
        'clear_floor': 100,
        'start_floors': [1, 21],
        'milestones': [30, 50, 100],
        'color':      'sky',
        'desc':       'Floors 1-100. Solo or party (1-4). 0 KOs required to enter 31-100.',
        'solo_title': 'Lone Hero',
        'icon':       'fa-cloud',
    },
    'eo': {
        'key':        'eo',
        'name':       'Eureka Orthos',
        'short':      'EO',
        'max_floor':  100,
        'clear_floor': 100,
        'start_floors': [1, 21],
        'milestones': [30, 50, 100],
        'color':      'emerald',
        'desc':       'Floors 1-100. Solo or party (1-4). 0 KOs required to enter 31-100.',
        'solo_title': 'Once and Future King/Queen',
        'icon':       'fa-dragon',
    },
}

JOBS = [
    'Paladin','Warrior','Dark Knight','Gunbreaker',
    'White Mage','Scholar','Astrologian','Sage',
    'Monk','Dragoon','Ninja','Samurai','Reaper','Viper',
    'Bard','Machinist','Dancer',
    'Black Mage','Summoner','Red Mage','Pictomancer',
    # Note: Blue Mage and Beastmaster are Limited Jobs - cannot enter deep dungeons
]


@add_web_user_context
def ffxiv_deep_dungeon(request):
    web_user = get_web_user(request)

    my_runs = []
    my_pbs  = {}
    fc_lb   = {}   # dungeon -> list of {display_name, floor_end, kos, job, party_size, is_clear, run_at}

    with get_db_session() as db:
        if web_user:
            # Personal runs - most recent 50
            my_runs = (
                db.query(WebFfxivDeepDungeonRun)
                .filter_by(user_id=web_user.id)
                .order_by(WebFfxivDeepDungeonRun.run_at.desc())
                .limit(50)
                .all()
            )
            pbs = db.query(WebFfxivDeepDungeonPB).filter_by(user_id=web_user.id).all()
            my_pbs = {pb.dungeon: pb for pb in pbs}

        # FC leaderboard - top 10 per dungeon by floor_end desc, then kos asc
        for dkey in DUNGEONS:
            rows = (
                db.query(
                    WebFfxivDeepDungeonPB,
                    WebUser.display_name,
                    WebUser.avatar_url,
                )
                .join(WebUser, WebUser.id == WebFfxivDeepDungeonPB.user_id)
                .filter(WebFfxivDeepDungeonPB.dungeon == dkey)
                .filter(WebUser.is_banned == False)
                .order_by(
                    WebFfxivDeepDungeonPB.floor_end.desc(),
                    WebFfxivDeepDungeonPB.kos.asc(),
                )
                .limit(10)
                .all()
            )
            fc_lb[dkey] = [
                {
                    'display_name': r.display_name,
                    'avatar_url':   r.avatar_url or '',
                    'floor_end':    r.WebFfxivDeepDungeonPB.floor_end,
                    'kos':          r.WebFfxivDeepDungeonPB.kos,
                    'job':          r.WebFfxivDeepDungeonPB.job or '',
                    'party_size':   r.WebFfxivDeepDungeonPB.party_size,
                    'is_clear':     bool(r.WebFfxivDeepDungeonPB.is_clear),
                    'run_at':       r.WebFfxivDeepDungeonPB.run_at,
                }
                for r in rows
            ]

    runs_data = [
        {
            'id':          r.id,
            'dungeon':     r.dungeon,
            'floor_start': r.floor_start,
            'floor_end':   r.floor_end,
            'kos':         r.kos,
            'job':         r.job or '',
            'party_size':  r.party_size,
            'is_clear':    bool(r.is_clear),
            'notes':       r.notes or '',
            'run_at':      r.run_at,
        }
        for r in my_runs
    ]

    pbs_data = {
        dkey: {
            'floor_end':  pb.floor_end,
            'kos':        pb.kos,
            'job':        pb.job or '',
            'party_size': pb.party_size,
            'is_clear':   bool(pb.is_clear),
            'run_at':     pb.run_at,
        }
        for dkey, pb in my_pbs.items()
    }

    return render(request, 'questlog_web/ffxiv_deep_dungeon.html', {
        'active_page':   'ffxiv_deep_dungeon',
        'dungeons':      list(DUNGEONS.values()),
        'jobs':          JOBS,
        'my_runs':       runs_data,
        'my_pbs':        pbs_data,
        'fc_lb':         fc_lb,
        'is_logged_in':  bool(web_user),
        'is_admin':      bool(web_user and web_user.is_admin),
        'web_user':      web_user,
    })


@require_POST
@web_login_required
def api_ffxiv_dd_log_run(request):
    import json
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    dungeon     = body.get('dungeon', '').strip().lower()
    floor_start = safe_int(body.get('floor_start'), 1, 1, 200)
    floor_end   = safe_int(body.get('floor_end'),   1, 1, 200)
    kos         = safe_int(body.get('kos'),         0, 0, 999)
    job         = sanitize_text(body.get('job', '').strip())[:32]
    party_size  = safe_int(body.get('party_size'),  1, 1, 4)
    notes       = sanitize_text(body.get('notes', '').strip())[:200]

    if dungeon not in DUNGEONS:
        return JsonResponse({'error': 'Invalid dungeon'}, status=400)

    meta      = DUNGEONS[dungeon]
    is_clear  = 1 if floor_end >= meta['clear_floor'] else 0
    floor_end = min(floor_end, meta['max_floor'])

    if floor_start not in meta['start_floors']:
        floor_start = meta['start_floors'][0]

    if job and job not in JOBS:
        job = ''

    now = int(time.time())

    with get_db_session() as db:
        run = WebFfxivDeepDungeonRun(
            user_id     = web_user.id,
            dungeon     = dungeon,
            floor_start = floor_start,
            floor_end   = floor_end,
            kos         = kos,
            job         = job or None,
            party_size  = party_size,
            is_clear    = is_clear,
            notes       = notes or None,
            run_at      = now,
        )
        db.add(run)
        db.flush()
        run_id = run.id

        # Update PB if this run is better (higher floor, or same floor with fewer KOs)
        pb = db.query(WebFfxivDeepDungeonPB).filter_by(user_id=web_user.id, dungeon=dungeon).first()
        is_new_pb = False
        if not pb:
            pb = WebFfxivDeepDungeonPB(
                user_id    = web_user.id,
                dungeon    = dungeon,
                floor_end  = floor_end,
                kos        = kos,
                job        = job or None,
                party_size = party_size,
                is_clear   = is_clear,
                run_at     = now,
            )
            db.add(pb)
            is_new_pb = True
        elif floor_end > pb.floor_end or (floor_end == pb.floor_end and kos < pb.kos):
            pb.floor_end  = floor_end
            pb.kos        = kos
            pb.job        = job or None
            pb.party_size = party_size
            pb.is_clear   = is_clear
            pb.run_at     = now
            is_new_pb = True

        db.commit()

    return JsonResponse({
        'ok':       True,
        'run_id':   run_id,
        'is_new_pb': is_new_pb,
        'is_clear': bool(is_clear),
        'run': {
            'id':          run_id,
            'dungeon':     dungeon,
            'floor_start': floor_start,
            'floor_end':   floor_end,
            'kos':         kos,
            'job':         job,
            'party_size':  party_size,
            'is_clear':    bool(is_clear),
            'notes':       notes,
            'run_at':      now,
        },
    })


@require_POST
@web_login_required
def api_ffxiv_dd_edit_run(request):
    import json
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    run_id      = safe_int(body.get('run_id'), 0, 1)
    floor_start = safe_int(body.get('floor_start'), 1, 1, 200)
    floor_end   = safe_int(body.get('floor_end'),   1, 1, 200)
    kos         = safe_int(body.get('kos'),         0, 0, 999)
    job         = sanitize_text(body.get('job', '').strip())[:32]
    party_size  = safe_int(body.get('party_size'),  1, 1, 4)
    notes       = sanitize_text(body.get('notes', '').strip())[:200]

    if not run_id:
        return JsonResponse({'error': 'Missing run_id'}, status=400)
    if job and job not in JOBS:
        job = ''

    with get_db_session() as db:
        run = db.query(WebFfxivDeepDungeonRun).filter_by(id=run_id, user_id=web_user.id).first()
        if not run:
            return JsonResponse({'error': 'Not found'}, status=404)

        meta     = DUNGEONS.get(run.dungeon, {})
        is_clear = 1 if floor_end >= meta.get('clear_floor', 9999) else 0
        floor_end = min(floor_end, meta.get('max_floor', 200))

        if floor_start not in meta.get('start_floors', [1]):
            floor_start = meta.get('start_floors', [1])[0]

        run.floor_start = floor_start
        run.floor_end   = floor_end
        run.kos         = kos
        run.job         = job or None
        run.party_size  = party_size
        run.is_clear    = is_clear
        run.notes       = notes or None

        # Recalculate PB for this dungeon from all runs
        best = (
            db.query(WebFfxivDeepDungeonRun)
            .filter_by(user_id=web_user.id, dungeon=run.dungeon)
            .order_by(
                WebFfxivDeepDungeonRun.floor_end.desc(),
                WebFfxivDeepDungeonRun.kos.asc(),
            )
            .first()
        )
        pb = db.query(WebFfxivDeepDungeonPB).filter_by(user_id=web_user.id, dungeon=run.dungeon).first()
        if best and pb:
            pb.floor_end  = best.floor_end
            pb.kos        = best.kos
            pb.job        = best.job
            pb.party_size = best.party_size
            pb.is_clear   = best.is_clear
            pb.run_at     = best.run_at

        db.commit()

        updated = {
            'id':          run.id,
            'dungeon':     run.dungeon,
            'floor_start': run.floor_start,
            'floor_end':   run.floor_end,
            'kos':         run.kos,
            'job':         run.job or '',
            'party_size':  run.party_size,
            'is_clear':    bool(run.is_clear),
            'notes':       run.notes or '',
            'run_at':      run.run_at,
        }
        new_pb = {
            'floor_end':  pb.floor_end,
            'kos':        pb.kos,
            'job':        pb.job or '',
            'party_size': pb.party_size,
            'is_clear':   bool(pb.is_clear),
            'run_at':     pb.run_at,
        } if pb else None

    return JsonResponse({'ok': True, 'run': updated, 'pb': new_pb})


@require_POST
@web_login_required
def api_ffxiv_dd_delete_run(request):
    import json
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    run_id = safe_int(body.get('run_id'), 0, 1)
    if not run_id:
        return JsonResponse({'error': 'Missing run_id'}, status=400)

    with get_db_session() as db:
        # Admin can delete any run; users can only delete their own
        if web_user.is_admin:
            run = db.query(WebFfxivDeepDungeonRun).filter_by(id=run_id).first()
        else:
            run = db.query(WebFfxivDeepDungeonRun).filter_by(id=run_id, user_id=web_user.id).first()

        if not run:
            return JsonResponse({'error': 'Not found'}, status=404)

        owner_id = run.user_id
        dungeon  = run.dungeon
        db.delete(run)
        db.flush()

        # Recalculate PB for the owner after deletion
        best = (
            db.query(WebFfxivDeepDungeonRun)
            .filter_by(user_id=owner_id, dungeon=dungeon)
            .order_by(
                WebFfxivDeepDungeonRun.floor_end.desc(),
                WebFfxivDeepDungeonRun.kos.asc(),
            )
            .first()
        )
        pb = db.query(WebFfxivDeepDungeonPB).filter_by(user_id=owner_id, dungeon=dungeon).first()
        if pb:
            if best:
                pb.floor_end  = best.floor_end
                pb.kos        = best.kos
                pb.job        = best.job
                pb.party_size = best.party_size
                pb.is_clear   = best.is_clear
                pb.run_at     = best.run_at
            else:
                db.delete(pb)

        db.commit()

    return JsonResponse({'ok': True})


@require_POST
@web_login_required
def api_ffxiv_dd_admin_wipe(request):
    """Admin only: wipe all runs + PB for a given user+dungeon."""
    import json
    web_user = get_web_user(request)
    if not web_user.is_admin:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    target_name = body.get('display_name', '').strip()
    dungeon     = body.get('dungeon', '').strip().lower()

    if not target_name or dungeon not in DUNGEONS:
        return JsonResponse({'error': 'Missing fields'}, status=400)

    with get_db_session() as db:
        target = db.query(WebUser).filter_by(display_name=target_name).first()
        if not target:
            return JsonResponse({'error': 'User not found'}, status=404)

        db.query(WebFfxivDeepDungeonRun).filter_by(user_id=target.id, dungeon=dungeon).delete()
        db.query(WebFfxivDeepDungeonPB).filter_by(user_id=target.id, dungeon=dungeon).delete()
        db.commit()

    return JsonResponse({'ok': True, 'wiped': target_name, 'dungeon': dungeon})
