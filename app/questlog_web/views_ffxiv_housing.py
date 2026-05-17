"""
FFXIV Housing Tracker - plot availability via PaissaDB (manual sync only, cached in DB).
Plot links go to Gametora's per-district viewer pre-filtered to the world.
"""
import json
import logging
import time
import urllib.request
import urllib.error

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from app.db import get_engine
from app.questlog_web.helpers import add_web_user_context, web_admin_required, get_web_user
from sqlalchemy import text

logger = logging.getLogger(__name__)

PAISSA_BASE = 'https://paissadb.zhu.codes'

PLOT_SIZE      = {0: 'S', 1: 'M', 2: 'L'}
PLOT_SIZE_LABEL = {0: 'Small', 1: 'Medium', 2: 'Large'}
PURCHASE_SYSTEM = {1: 'FCFS', 2: 'Lottery', 3: 'Lottery'}

GAMETORA_DISTRICT_SLUG = {
    339: 'mist',
    340: 'lavender-beds',
    341: 'goblet',
    641: 'shirogane',
    979: 'empyreum',
}

DISTRICT_COLOR = {
    339: 'blue',
    340: 'green',
    341: 'orange',
    641: 'pink',
    979: 'purple',
}

# Minimum seconds between plot syncs (15 minutes)
SYNC_COOLDOWN = 900
# Worlds list cache TTL (24 hours - datacenter/world list almost never changes)
WORLDS_CACHE_TTL = 86400


def _paissa_get(path):
    url = f'{PAISSA_BASE}{path}'
    req = urllib.request.Request(url, headers={'User-Agent': 'QuestLog-Housing-Tracker/1.0 (https://questlog.casual-heroes.com)'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _gametora_url(world_name, district_id):
    """Link to Gametora's district page pre-filtered to the world."""
    slug = GAMETORA_DISTRICT_SLUG.get(district_id, 'mist')
    return f'https://gametora.com/ffxiv/housing-plot-viewer/{slug}?server={world_name.lower()}'


def _shape_world_data(data):
    """Transform raw PaissaDB world response into our cache/response format."""
    world_name = data.get('name', '')
    districts = []
    total_open = 0

    for dist in data.get('districts', []):
        dist_id = dist['id']
        color = DISTRICT_COLOR.get(dist_id, 'blue')
        plots = []
        for p in dist.get('open_plots', []):
            ward = p['ward_number']
            plot = p['plot_number']
            size_int = p.get('size', 0)
            plots.append({
                'ward': ward + 1,
                'plot': plot + 1,
                'size': PLOT_SIZE.get(size_int, '?'),
                'size_label': PLOT_SIZE_LABEL.get(size_int, 'Unknown'),
                'price': p.get('price', 0),
                'first_seen': p.get('first_seen_time'),
                'last_updated': p.get('last_updated_time'),
                'lotto_phase': p.get('lotto_phase'),
                'lotto_phase_until': p.get('lotto_phase_until'),
                'lotto_entries': p.get('lotto_entries', 0),
                'purchase_system': PURCHASE_SYSTEM.get(p.get('purchase_system', 3), 'Lottery'),
                'gametora_url': _gametora_url(world_name, dist_id),
            })

        size_order = {'L': 0, 'M': 1, 'S': 2}
        plots.sort(key=lambda x: (size_order.get(x['size'], 9), x['price']))
        total_open += len(plots)

        districts.append({
            'id': dist_id,
            'name': dist['name'],
            'color': color,
            'open_count': len(plots),
            'plots': plots,
        })

    return {
        'world_name': world_name,
        'total_open': total_open,
        'districts': districts,
    }


@add_web_user_context
def ffxiv_housing(request):
    from django.shortcuts import render
    web_user = get_web_user(request)
    return render(request, 'questlog_web/ffxiv_housing.html', {
        'page': 'housing',
        'web_user': web_user,
        'is_logged_in': bool(web_user),
        'is_admin': bool(web_user and web_user.is_admin),
    })


@require_http_methods(['GET'])
def api_ffxiv_housing_worlds(request):
    """GET - worlds grouped by datacenter, served from DB cache (refreshed every 24h)."""
    engine = get_engine()
    now = int(time.time())

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT payload_json, cached_at FROM web_ffxiv_housing_worlds_cache WHERE id = 1 LIMIT 1")
        ).fetchone()

    if row and row.cached_at and (now - row.cached_at) < WORLDS_CACHE_TTL:
        return JsonResponse(json.loads(row.payload_json))

    # Cache miss or stale - fetch from PaissaDB
    try:
        worlds = _paissa_get('/worlds')
    except Exception as e:
        logger.warning(f'PaissaDB worlds fetch failed: {e}')
        # Return stale cache if we have it rather than error
        if row:
            return JsonResponse(json.loads(row.payload_json))
        return JsonResponse({'error': 'Could not reach PaissaDB'}, status=502)

    by_dc = {}
    for w in worlds:
        dc = w['datacenter_name']
        by_dc.setdefault(dc, []).append({'id': w['id'], 'name': w['name']})
    for dc in by_dc:
        by_dc[dc].sort(key=lambda x: x['name'])

    payload = {'datacenters': [{'datacenter': dc, 'worlds': wlist} for dc, wlist in sorted(by_dc.items())]}
    payload_str = json.dumps(payload)

    with engine.connect() as conn:
        if row:
            conn.execute(
                text("UPDATE web_ffxiv_housing_worlds_cache SET payload_json=:p, cached_at=:t WHERE id=1"),
                {'p': payload_str, 't': now}
            )
        else:
            conn.execute(
                text("INSERT INTO web_ffxiv_housing_worlds_cache (id, payload_json, cached_at) VALUES (1, :p, :t)"),
                {'p': payload_str, 't': now}
            )
        conn.commit()

    return JsonResponse(payload)


@require_http_methods(['GET'])
def api_ffxiv_housing_plots(request, world_id):
    """GET - open plots for a world, served from cache. Returns cached_at timestamp."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT world_name, payload_json, cached_at FROM web_ffxiv_housing_cache WHERE world_id = :w LIMIT 1"),
            {'w': world_id}
        ).fetchone()

    if not row:
        return JsonResponse({
            'world_id': world_id,
            'world_name': '',
            'total_open': 0,
            'districts': [],
            'cached_at': None,
            'never_synced': True,
        })

    payload = json.loads(row.payload_json)
    payload['world_id'] = world_id
    payload['cached_at'] = row.cached_at
    payload['never_synced'] = False
    return JsonResponse(payload)


@require_http_methods(['POST'])
@web_admin_required
def api_ffxiv_housing_sync(request):
    """POST (admin only) - fetch fresh data from PaissaDB and store in cache."""
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    world_id = body.get('world_id')
    if not world_id or not str(world_id).isdigit():
        return JsonResponse({'error': 'world_id required'}, status=400)
    world_id = int(world_id)

    engine = get_engine()

    # Cooldown check
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT cached_at FROM web_ffxiv_housing_cache WHERE world_id = :w LIMIT 1"),
            {'w': world_id}
        ).fetchone()
        if row and row.cached_at and (int(time.time()) - row.cached_at) < SYNC_COOLDOWN:
            wait = SYNC_COOLDOWN - (int(time.time()) - row.cached_at)
            return JsonResponse({'error': f'Synced too recently - wait {wait // 60}m {wait % 60}s'}, status=429)

    # Fetch from PaissaDB
    try:
        raw = _paissa_get(f'/worlds/{world_id}')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return JsonResponse({'error': 'World not found on PaissaDB'}, status=404)
        return JsonResponse({'error': f'PaissaDB error: {e.code}'}, status=502)
    except Exception as e:
        logger.warning(f'PaissaDB sync failed for world {world_id}: {e}')
        return JsonResponse({'error': 'Could not reach PaissaDB'}, status=502)

    shaped = _shape_world_data(raw)
    now = int(time.time())

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM web_ffxiv_housing_cache WHERE world_id = :w LIMIT 1"),
            {'w': world_id}
        ).fetchone()

        if existing:
            conn.execute(
                text("UPDATE web_ffxiv_housing_cache SET world_name=:n, payload_json=:p, cached_at=:t WHERE world_id=:w"),
                {'n': shaped['world_name'], 'p': json.dumps(shaped), 't': now, 'w': world_id}
            )
        else:
            conn.execute(
                text("INSERT INTO web_ffxiv_housing_cache (world_id, world_name, payload_json, cached_at) VALUES (:w, :n, :p, :t)"),
                {'w': world_id, 'n': shaped['world_name'], 'p': json.dumps(shaped), 't': now}
            )
        conn.commit()

    shaped['world_id'] = world_id
    shaped['cached_at'] = now
    shaped['never_synced'] = False
    return JsonResponse({'ok': True, 'data': shaped})
