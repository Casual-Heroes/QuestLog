import time
import logging
import requests
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from app.db import get_db_session
from app.questlog_web.models import WebFfxivParseLink, WebUser
from app.questlog_web.helpers import (
    get_web_user, web_login_required, add_web_user_context, safe_int
)
from django.conf import settings

logger = logging.getLogger(__name__)

FFLOGS_TOKEN_URL = 'https://www.fflogs.com/oauth/token'
FFLOGS_API_URL   = 'https://www.fflogs.com/api/v2/client'
TOKEN_CACHE      = {'token': None, 'expires_at': 0}

# Current savage/ultimate zone IDs (DT = Arcadion Light-heavyweight/Cruiserweight M1-M8S, plus Ultimates)
# Zone IDs from FF Logs - these are stable
TRACKED_ZONES = [
    {'id': 63, 'name': 'Arcadion: Light-heavyweight (Savage)',  'tier': 'M1S-M4S',  'expansion': 'DT'},
    {'id': 64, 'name': 'Arcadion: Cruiserweight (Savage)',      'tier': 'M5S-M8S',  'expansion': 'DT'},
    {'id': 56, 'name': "Anabaseios (Savage)",                   'tier': 'P9S-P12S', 'expansion': 'EW'},
    {'id': 55, 'name': "Abyssos (Savage)",                      'tier': 'P5S-P8S',  'expansion': 'EW'},
    {'id': 54, 'name': "Asphodelos (Savage)",                   'tier': 'P1S-P4S',  'expansion': 'EW'},
    {'id': 53, 'name': "Eden's Promise (Savage)",               'tier': 'E9S-E12S', 'expansion': 'ShB'},
    {'id': 33, 'name': 'The Unending Coil of Bahamut (Ultimate)','tier': 'UCoB',    'expansion': 'SB'},
    {'id': 34, 'name': 'The Weapon\'s Refrain (Ultimate)',       'tier': 'UWU',     'expansion': 'SB'},
    {'id': 40, 'name': 'The Epic of Alexander (Ultimate)',       'tier': 'TEA',     'expansion': 'ShB'},
    {'id': 60, 'name': 'Dragonsong\'s Reprise (Ultimate)',       'tier': 'DSR',     'expansion': 'EW'},
    {'id': 61, 'name': 'The Omega Protocol (Ultimate)',          'tier': 'TOP',     'expansion': 'EW'},
    {'id': 62, 'name': 'Futures Rewritten (Ultimate)',           'tier': 'FRU',     'expansion': 'DT'},
]

PARSE_COLORS = [
    (100, 'text-orange-300',  'bg-orange-900/30',  'Legendary'),
    (99,  'text-pink-400',    'bg-pink-900/30',    'Epic'),
    (95,  'text-amber-300',   'bg-amber-900/30',   'Rare'),
    (75,  'text-violet-400',  'bg-violet-900/30',  'Uncommon'),
    (50,  'text-sky-300',     'bg-sky-900/30',     'Average'),
    (25,  'text-green-400',   'bg-green-900/30',   'Below Average'),
    (0,   'text-gray-400',    'bg-neutral-800',    'Poor'),
]

def _get_parse_color(pct):
    if pct is None:
        return 'text-gray-600', 'bg-neutral-900', '-'
    for threshold, text, bg, label in PARSE_COLORS:
        if pct >= threshold:
            return text, bg, label
    return 'text-gray-600', 'bg-neutral-900', '-'


def _get_access_token():
    """Get a cached client-credentials access token."""
    now = time.time()
    if TOKEN_CACHE['token'] and TOKEN_CACHE['expires_at'] > now + 60:
        return TOKEN_CACHE['token']

    client_id     = getattr(settings, 'FFLOGS_CLIENT_ID', None)
    client_secret = getattr(settings, 'FFLOGS_CLIENT_SECRET', None)
    if not client_id or not client_secret:
        raise ValueError('FFLOGS_CLIENT_ID / FFLOGS_CLIENT_SECRET not set in settings')

    resp = requests.post(
        FFLOGS_TOKEN_URL,
        data={'grant_type': 'client_credentials'},
        auth=(client_id, client_secret),
        timeout=10,
    )
    resp.raise_for_status()
    token_data = resp.json()
    TOKEN_CACHE['token']      = token_data['access_token']
    TOKEN_CACHE['expires_at'] = now + token_data.get('expires_in', 3600)
    return TOKEN_CACHE['token']


def _gql(query, variables=None):
    """Execute a GraphQL query against FF Logs v2 client API."""
    token = _get_access_token()
    resp = requests.post(
        FFLOGS_API_URL,
        json={'query': query, 'variables': variables or {}},
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if 'errors' in data:
        raise ValueError(f"GraphQL error: {data['errors']}")
    return data.get('data', {})


def _fetch_character_parses(char_name, server_slug, server_region, zone_id):
    """Fetch zone rankings for a character from FF Logs."""
    query = """
    query($name: String!, $serverSlug: String!, $serverRegion: String!, $zoneID: Int!) {
      characterData {
        character(name: $name, serverSlug: $serverSlug, serverRegion: $serverRegion) {
          id
          name
          zoneRankings(zoneID: $zoneID, difficulty: 100)
        }
      }
    }
    """
    data = _gql(query, {
        'name':         char_name,
        'serverSlug':   server_slug,
        'serverRegion': server_region,
        'zoneID':       zone_id,
    })
    return data.get('characterData', {}).get('character')


# ---------------------------------------------------------------------------
# Page view
# ---------------------------------------------------------------------------

@add_web_user_context
def ffxiv_parses(request):
    web_user = get_web_user(request)
    my_link  = None
    fc_data  = []

    has_credentials = bool(
        getattr(settings, 'FFLOGS_CLIENT_ID', None) and
        getattr(settings, 'FFLOGS_CLIENT_SECRET', None)
    )

    with get_db_session() as db:
        if web_user:
            my_link = db.query(WebFfxivParseLink).filter_by(user_id=web_user.id).first()

        # FC leaderboard - users who have linked their FF Logs character
        rows = (
            db.query(WebFfxivParseLink, WebUser.display_name, WebUser.avatar_url)
            .join(WebUser, WebUser.id == WebFfxivParseLink.user_id)
            .filter(WebUser.is_banned == False)
            .filter(WebFfxivParseLink.best_parse_pct != None)
            .order_by(WebFfxivParseLink.best_parse_pct.desc())
            .all()
        )
        fc_data = [
            {
                'display_name':  r.display_name,
                'avatar_url':    r.avatar_url or '',
                'char_name':     r.WebFfxivParseLink.char_name,
                'server':        r.WebFfxivParseLink.server_name,
                'best_parse':    r.WebFfxivParseLink.best_parse_pct,
                'best_fight':    r.WebFfxivParseLink.best_parse_fight,
                'best_job':      r.WebFfxivParseLink.best_parse_job,
                'parses_json':   r.WebFfxivParseLink.parses_json,
                'last_synced':   r.WebFfxivParseLink.last_synced_at,
            }
            for r in rows
        ]

    return render(request, 'questlog_web/ffxiv_parses.html', {
        'active_page':       'ffxiv_parses',
        'tracked_zones':     TRACKED_ZONES,
        'my_link':           my_link,
        'fc_data':           fc_data,
        'has_credentials':   has_credentials,
        'is_logged_in':      bool(web_user),
        'is_admin':          bool(web_user and web_user.is_admin),
        'web_user':          web_user,
        'parse_colors_json': _parse_colors_for_template(),
    })


def _parse_colors_for_template():
    return [
        {'min': t, 'text': tc, 'bg': bc, 'label': l}
        for t, tc, bc, l in PARSE_COLORS
    ]


# ---------------------------------------------------------------------------
# API: link character
# ---------------------------------------------------------------------------

@require_POST
@web_login_required
def api_ffxiv_parses_link(request):
    import json
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    char_name  = body.get('char_name', '').strip()[:64]
    server     = body.get('server', '').strip()[:64]      # e.g. "Faerie"
    region     = body.get('region', '').strip().upper()   # NA / EU / JP / OC

    if not char_name or not server or region not in ('NA', 'EU', 'JP', 'OC'):
        return JsonResponse({'error': 'char_name, server, and region (NA/EU/JP/OC) are required'}, status=400)

    server_slug = server.lower()

    with get_db_session() as db:
        existing = db.query(WebFfxivParseLink).filter_by(user_id=web_user.id).first()
        now = int(time.time())
        if existing:
            existing.char_name   = char_name
            existing.server_name = server
            existing.server_slug = server_slug
            existing.region      = region
            existing.linked_at   = now
            existing.last_synced_at = None
            existing.best_parse_pct   = None
            existing.best_parse_fight = None
            existing.best_parse_job   = None
            existing.parses_json      = None
        else:
            db.add(WebFfxivParseLink(
                user_id=web_user.id,
                char_name=char_name,
                server_name=server,
                server_slug=server_slug,
                region=region,
                linked_at=now,
            ))
        db.commit()

    return JsonResponse({'ok': True, 'char_name': char_name, 'server': server})


# ---------------------------------------------------------------------------
# API: sync parses (fetches from FF Logs and caches)
# ---------------------------------------------------------------------------

@require_POST
@web_login_required
def api_ffxiv_parses_sync(request):
    import json
    web_user = get_web_user(request)

    if not getattr(settings, 'FFLOGS_CLIENT_ID', None):
        return JsonResponse({'error': 'FF Logs API not configured yet'}, status=503)

    with get_db_session() as db:
        link = db.query(WebFfxivParseLink).filter_by(user_id=web_user.id).first()
        if not link:
            return JsonResponse({'error': 'No character linked'}, status=400)

        # Rate limit: max once per 5 minutes
        now = int(time.time())
        if link.last_synced_at and (now - link.last_synced_at) < 300:
            wait = 300 - (now - link.last_synced_at)
            return JsonResponse({'error': f'Please wait {wait}s before syncing again'}, status=429)

        try:
            all_parses = {}
            best_pct   = None
            best_fight = None
            best_job   = None

            for zone in TRACKED_ZONES:
                char = _fetch_character_parses(
                    link.char_name, link.server_slug, link.region, zone['id']
                )
                if not char:
                    continue

                zone_rankings = char.get('zoneRankings', {})
                rankings = zone_rankings.get('rankings', []) if zone_rankings else []

                zone_parses = []
                for r in rankings:
                    pct = r.get('rankPercent')
                    fight_name = (r.get('encounter') or {}).get('name', '')
                    job = (r.get('spec') or '')
                    zone_parses.append({
                        'fight':   fight_name,
                        'job':     job,
                        'pct':     round(pct, 1) if pct is not None else None,
                        'rdps':    round(r.get('rankTotal', 0), 0) if r.get('rankTotal') else None,
                        'kills':   r.get('totalKills', 0),
                        'fastest': r.get('fastestKill', 0),
                    })
                    if pct is not None and (best_pct is None or pct > best_pct):
                        best_pct   = round(pct, 1)
                        best_fight = fight_name
                        best_job   = job

                if zone_parses:
                    all_parses[str(zone['id'])] = zone_parses

            link.parses_json      = json.dumps(all_parses)
            link.best_parse_pct   = best_pct
            link.best_parse_fight = best_fight
            link.best_parse_job   = best_job
            link.last_synced_at   = now
            db.commit()

            return JsonResponse({
                'ok':        True,
                'parses':    all_parses,
                'best_pct':  best_pct,
                'best_fight':best_fight,
                'best_job':  best_job,
                'synced_at': now,
            })

        except ValueError as e:
            logger.error('FF Logs GraphQL error for user %s: %s', web_user.id, e)
            return JsonResponse({'error': str(e)}, status=502)
        except Exception as e:
            logger.error('FF Logs sync error for user %s: %s', web_user.id, e)
            return JsonResponse({'error': 'Sync failed - please try again'}, status=502)


# ---------------------------------------------------------------------------
# API: unlink character
# ---------------------------------------------------------------------------

@require_POST
@web_login_required
def api_ffxiv_parses_unlink(request):
    web_user = get_web_user(request)
    with get_db_session() as db:
        link = db.query(WebFfxivParseLink).filter_by(user_id=web_user.id).first()
        if link:
            db.delete(link)
            db.commit()
    return JsonResponse({'ok': True})
