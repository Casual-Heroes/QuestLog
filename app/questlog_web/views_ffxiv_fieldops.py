import time
import logging
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from app.db import get_db_session
from app.questlog_web.models import WebFfxivFieldOps, WebUser
from app.questlog_web.helpers import get_web_user, web_login_required, web_admin_required, add_web_user_context, safe_int

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static zone metadata
# ---------------------------------------------------------------------------

ZONES = {
    'eureka_anemos': {
        'key':       'eureka_anemos',
        'tab':       'eureka',
        'name':      'Eureka Anemos',
        'short':     'Anemos',
        'expansion': 'SB',
        'color':     'cyan',
        'icon':      'fa-wind',
        'el_range':  (1, 20),
        'relic_stages': [
            'None', 'Antiquated Weapon', 'Anemos Weapon', 'Anemos +1', 'Anemos +2',
        ],
        'armor_stages': [
            'None', 'Anemos Armor', 'Anemos +1', 'Anemos +2',
        ],
        'desc': 'Elemental Levels 1-20. Farm Protean Crystals from NMs for the Anemos weapon.',
    },
    'eureka_pagos': {
        'key':       'eureka_pagos',
        'tab':       'eureka',
        'name':      'Eureka Pagos',
        'short':     'Pagos',
        'expansion': 'SB',
        'color':     'sky',
        'icon':      'fa-snowflake',
        'el_range':  (20, 35),
        'relic_stages': [
            'None', 'Elemental Weapon', 'Elemental +1', 'Elemental +2',
        ],
        'armor_stages': [
            'None', 'Elemental Armor', 'Elemental +1', 'Elemental +2',
        ],
        'desc': 'Elemental Levels 20-35. Frosted Protean Crystals from Pagos NMs.',
    },
    'eureka_pyros': {
        'key':       'eureka_pyros',
        'tab':       'eureka',
        'name':      'Eureka Pyros',
        'short':     'Pyros',
        'expansion': 'SB',
        'color':     'orange',
        'icon':      'fa-fire',
        'el_range':  (35, 50),
        'relic_stages': [
            'None', 'Pyros Weapon', 'Pyros +1', 'Pyros +2',
        ],
        'armor_stages': [
            'None', 'Elemental Armor', 'Elemental +1', 'Elemental +2',
        ],
        'desc': 'Elemental Levels 35-50. Logos Actions unlock here (56 total).',
        'has_logos': True,
    },
    'eureka_hydatos': {
        'key':       'eureka_hydatos',
        'tab':       'eureka',
        'name':      'Eureka Hydatos',
        'short':     'Hydatos',
        'expansion': 'SB',
        'color':     'teal',
        'icon':      'fa-water',
        'el_range':  (50, 60),
        'relic_stages': [
            'None', 'Eureka Weapon', 'Eureka +1', 'Hydatos Weapon', 'Physeos Weapon',
        ],
        'armor_stages': [
            'None', 'Elemental Armor', 'Elemental +1', 'Elemental +2', 'Hydatos Armor', 'Elemental +2 (Dyeable)',
        ],
        'desc': 'Elemental Levels 50-60. Final Eureka zone - complete for the Physeos weapon.',
        'has_logos': True,
    },
    'bozja': {
        'key':       'bozja',
        'tab':       'bozja',
        'name':      'Bozja & Zadnor',
        'short':     'Bozja',
        'expansion': 'ShB',
        'color':     'yellow',
        'icon':      'fa-shield-alt',
        'rank_range': (1, 25),
        'relic_stages': [
            'None',
            'Resistance Weapon', 'Augmented Resistance Weapon',
            'Recollection Weapon', "Law's Order Weapon", "Augmented Law's Order Weapon",
            "Blade's Weapon",
        ],
        'rank_milestones': [10, 15, 20, 25],
        'desc': 'Resistance Rank 1-25 shared across BSF and Zadnor. Unlock Zadnor at Rank 10.',
    },
    'occult_crescent': {
        'key':       'occult_crescent',
        'tab':       'occult',
        'name':      'Occult Crescent',
        'short':     'OC',
        'expansion': 'DT',
        'color':     'violet',
        'icon':      'fa-moon',
        'kl_range':  (1, 40),
        'phantom_jobs': [
            'Freelancer','Knight','Monk','Bard','Thief','Samurai',
            'Berserker','Ranger','Time Mage','Chemist','Geomancer',
            'Oracle','Cannoneer','Mystic Knight','Gladiator','Dancer',
        ],
        'relic_stages': [
            'None', 'Phantom Weapon', 'Augmented Phantom Weapon',
        ],
        'desc': 'Knowledge Level 1-40. 16 Phantom Jobs to unlock and master. Forked Tower at KL 20+.',
    },
}

BOZJA_RANKS = [
    (1,0),(2,300),(3,1100),(4,2200),(5,3800),(6,9400),(7,18000),(8,32000),
    (9,51300),(10,78000),(11,106000),(12,157400),(13,252000),(14,416000),
    (15,703200),(16,1124000),(17,1930000),(18,2790000),(19,4435000),(20,6163000),
    (21,8663000),(22,11471000),(23,15602000),(24,20516000),(25,25870000),
]


def _zone_row_to_dict(row):
    return {
        'zone':             row.zone,
        'elemental_level':  row.elemental_level,
        'logos_actions':    row.logos_actions,
        'resistance_rank':  row.resistance_rank,
        'mettle':           row.mettle,
        'ces_completed':    row.ces_completed,
        'knowledge_level':  row.knowledge_level,
        'phantom_unlocked': row.phantom_unlocked,
        'phantom_mastered': row.phantom_mastered,
        'forked_clears':    row.forked_clears,
        'relic_stage':      row.relic_stage or '',
        'armor_stage':      row.armor_stage or '',
        'updated_at':       row.updated_at,
    }


@add_web_user_context
def ffxiv_field_ops(request):
    web_user = get_web_user(request)

    my_progress = {}
    fc_lb = {zkey: [] for zkey in ZONES}

    with get_db_session() as db:
        if web_user:
            rows = db.query(WebFfxivFieldOps).filter_by(user_id=web_user.id).all()
            my_progress = {r.zone: _zone_row_to_dict(r) for r in rows}

        # FC leaderboard per zone
        for zkey, zmeta in ZONES.items():
            tab = zmeta['tab']
            if tab == 'eureka':
                order_col = WebFfxivFieldOps.elemental_level
            elif tab == 'bozja':
                order_col = WebFfxivFieldOps.resistance_rank
            else:
                order_col = WebFfxivFieldOps.knowledge_level

            rows = (
                db.query(WebFfxivFieldOps, WebUser.display_name, WebUser.avatar_url)
                .join(WebUser, WebUser.id == WebFfxivFieldOps.user_id)
                .filter(WebFfxivFieldOps.zone == zkey)
                .filter(WebUser.is_banned == False)
                .order_by(order_col.desc())
                .limit(10)
                .all()
            )
            fc_lb[zkey] = [
                {
                    'user_id':         r.WebFfxivFieldOps.user_id,
                    'display_name':    r.display_name,
                    'avatar_url':      r.avatar_url or '',
                    'elemental_level': r.WebFfxivFieldOps.elemental_level,
                    'logos_actions':   r.WebFfxivFieldOps.logos_actions,
                    'resistance_rank': r.WebFfxivFieldOps.resistance_rank,
                    'mettle':          r.WebFfxivFieldOps.mettle,
                    'ces_completed':   r.WebFfxivFieldOps.ces_completed,
                    'knowledge_level': r.WebFfxivFieldOps.knowledge_level,
                    'phantom_unlocked':r.WebFfxivFieldOps.phantom_unlocked,
                    'phantom_mastered':r.WebFfxivFieldOps.phantom_mastered,
                    'forked_clears':   r.WebFfxivFieldOps.forked_clears,
                    'relic_stage':     r.WebFfxivFieldOps.relic_stage or '',
                    'armor_stage':     r.WebFfxivFieldOps.armor_stage or '',
                    'updated_at':      r.WebFfxivFieldOps.updated_at,
                }
                for r in rows
            ]

    return render(request, 'questlog_web/ffxiv_field_ops.html', {
        'active_page':   'ffxiv_field_ops',
        'zones':         list(ZONES.values()),
        'bozja_ranks':   BOZJA_RANKS,
        'my_progress':   my_progress,
        'fc_lb':         fc_lb,
        'is_logged_in':  bool(web_user),
        'is_admin':      bool(web_user and web_user.is_admin),
        'web_user':      web_user,
    })


@require_POST
@web_login_required
def api_ffxiv_fo_update(request):
    """Upsert a user's field ops progress for one zone."""
    import json
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    zone = body.get('zone', '').strip()
    if zone not in ZONES:
        return JsonResponse({'error': 'Invalid zone'}, status=400)

    zmeta = ZONES[zone]
    now   = int(time.time())

    # Parse fields based on zone type
    tab = zmeta['tab']
    elemental_level  = None
    logos_actions    = None
    resistance_rank  = None
    mettle           = None
    ces_completed    = None
    knowledge_level  = None
    phantom_unlocked = None
    phantom_mastered = None
    forked_clears    = None

    relic_stage = body.get('relic_stage', '').strip()[:64]
    if relic_stage and relic_stage not in zmeta['relic_stages']:
        relic_stage = ''

    armor_stage = body.get('armor_stage', '').strip()[:64]
    armor_stages = zmeta.get('armor_stages', [])
    if armor_stage and armor_stage not in armor_stages:
        armor_stage = ''

    if tab == 'eureka':
        lo, hi = zmeta['el_range']
        elemental_level = safe_int(body.get('elemental_level'), None, lo, hi)
        if zmeta.get('has_logos'):
            logos_actions = safe_int(body.get('logos_actions'), None, 0, 56)

    elif tab == 'bozja':
        resistance_rank = safe_int(body.get('resistance_rank'), None, 1, 25)
        mettle          = safe_int(body.get('mettle'), None, 0, 25870000)
        ces_completed   = safe_int(body.get('ces_completed'), None, 0, 99999)

    elif tab == 'occult':
        knowledge_level  = safe_int(body.get('knowledge_level'),  None, 1, 40)
        phantom_unlocked = safe_int(body.get('phantom_unlocked'), None, 0, 16)
        phantom_mastered = safe_int(body.get('phantom_mastered'), None, 0, 16)
        forked_clears    = safe_int(body.get('forked_clears'),    None, 0, 99999)

    with get_db_session() as db:
        row = db.query(WebFfxivFieldOps).filter_by(user_id=web_user.id, zone=zone).first()
        if row:
            row.elemental_level  = elemental_level
            row.logos_actions    = logos_actions
            row.resistance_rank  = resistance_rank
            row.mettle           = mettle
            row.ces_completed    = ces_completed
            row.knowledge_level  = knowledge_level
            row.phantom_unlocked = phantom_unlocked
            row.phantom_mastered = phantom_mastered
            row.forked_clears    = forked_clears
            row.relic_stage      = relic_stage or None
            row.armor_stage      = armor_stage or None
            row.updated_at       = now
        else:
            row = WebFfxivFieldOps(
                user_id=web_user.id, zone=zone,
                elemental_level=elemental_level, logos_actions=logos_actions,
                resistance_rank=resistance_rank, mettle=mettle, ces_completed=ces_completed,
                knowledge_level=knowledge_level, phantom_unlocked=phantom_unlocked,
                phantom_mastered=phantom_mastered, forked_clears=forked_clears,
                relic_stage=relic_stage or None, armor_stage=armor_stage or None, updated_at=now,
            )
            db.add(row)
        db.commit()

    return JsonResponse({
        'ok': True,
        'progress': {
            'zone': zone,
            'elemental_level':  elemental_level,
            'logos_actions':    logos_actions,
            'resistance_rank':  resistance_rank,
            'mettle':           mettle,
            'ces_completed':    ces_completed,
            'knowledge_level':  knowledge_level,
            'phantom_unlocked': phantom_unlocked,
            'phantom_mastered': phantom_mastered,
            'forked_clears':    forked_clears,
            'relic_stage':      relic_stage,
            'armor_stage':      armor_stage,
            'updated_at':       now,
        }
    })


@require_POST
@web_login_required
def api_ffxiv_fo_delete(request):
    """Delete the current user's progress row for one zone."""
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    zone = body.get('zone', '').strip()
    if zone not in ZONES:
        return JsonResponse({'error': 'Invalid zone'}, status=400)

    with get_db_session() as db:
        row = db.query(WebFfxivFieldOps).filter_by(user_id=web_user.id, zone=zone).first()
        if row:
            db.delete(row)
            db.commit()

    return JsonResponse({'ok': True})


@require_POST
@web_admin_required
def api_ffxiv_fo_admin_delete(request):
    """Admin: delete any user's progress row for one zone."""
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    zone = body.get('zone', '').strip()
    user_id = body.get('user_id')
    if zone not in ZONES or not user_id:
        return JsonResponse({'error': 'Invalid request'}, status=400)

    with get_db_session() as db:
        row = db.query(WebFfxivFieldOps).filter_by(user_id=int(user_id), zone=zone).first()
        if row:
            db.delete(row)
            db.commit()

    return JsonResponse({'ok': True})
