import logging
import requests
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from app.questlog_web.helpers import add_web_user_context, get_web_user

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static data - Data Centers and Worlds
# ---------------------------------------------------------------------------

DATA_CENTERS = [
    # North America
    {'name': 'Aether',   'region': 'North America', 'worlds': ['Adamantoise','Cactuar','Faerie','Gilgamesh','Jenova','Midgardsormr','Sargatanas','Siren']},
    {'name': 'Crystal',  'region': 'North America', 'worlds': ['Balmung','Brynhildr','Coeurl','Diabolos','Goblin','Malboro','Mateus','Zalera']},
    {'name': 'Dynamis',  'region': 'North America', 'worlds': ['Cuchulainn','Golem','Halicarnassus','Kraken','Maduin','Marilith','Rafflesia','Seraph']},
    {'name': 'Primal',   'region': 'North America', 'worlds': ['Behemoth','Excalibur','Exodus','Famfrit','Hyperion','Lamia','Leviathan','Ultros']},
    # Europe
    {'name': 'Chaos',    'region': 'Europe', 'worlds': ['Cerberus','Louisoix','Moogle','Omega','Phantom','Ragnarok','Sagittarius','Spriggan']},
    {'name': 'Light',    'region': 'Europe', 'worlds': ['Alpha','Lich','Odin','Phoenix','Raiden','Shiva','Twintania','Zodiark']},
    # Oceania
    {'name': 'Materia',  'region': 'Oceania', 'worlds': ['Bismarck','Ravana','Sephirot','Sophia','Zurvan']},
    # Japan
    {'name': 'Elemental','region': 'Japan', 'worlds': ['Aegis','Atomos','Carbuncle','Garuda','Gungnir','Kujata','Tonberry','Typhon']},
    {'name': 'Gaia',     'region': 'Japan', 'worlds': ['Alexander','Bahamut','Durandal','Fenrir','Ifrit','Ridill','Tiamat','Ultima']},
    {'name': 'Mana',     'region': 'Japan', 'worlds': ['Anima','Asura','Chocobo','Hades','Ixion','Masamune','Pandaemonium','Titan']},
    {'name': 'Meteor',   'region': 'Japan', 'worlds': ['Belias','Mandragora','Ramuh','Shinryu','Unicorn','Valefor','Yojimbo','Zeromus']},
]

# Flat world list for validation
ALL_WORLDS = {w for dc in DATA_CENTERS for w in dc['worlds']}
ALL_DCS    = {dc['name'] for dc in DATA_CENTERS}

XIVAPI_BASE        = 'https://xivapi.com'
TEAMCRAFT_API_BASE = 'https://api.ffxivteamcraft.com'
UNIVERSALIS_BASE   = 'https://universalis.app/api/v2'
REQUEST_TIMEOUT    = 8

# ---------------------------------------------------------------------------
# Page view
# ---------------------------------------------------------------------------

@add_web_user_context
def ffxiv_market_board(request):
    web_user = get_web_user(request)
    return render(request, 'questlog_web/ffxiv_market_board.html', {
        'active_page':  'ffxiv_market_board',
        'data_centers': DATA_CENTERS,
        'is_logged_in': bool(web_user),
        'is_admin':     bool(web_user and web_user.is_admin),
        'web_user':     web_user,
    })

# ---------------------------------------------------------------------------
# API: item search (proxies XIVAPI)
# ---------------------------------------------------------------------------

@require_GET
def api_mb_search(request):
    query = request.GET.get('q', '').strip()[:100]
    if len(query) < 2:
        return JsonResponse({'error': 'Query too short'}, status=400)

    try:
        resp = requests.get(
            f'{TEAMCRAFT_API_BASE}/search',
            params={
                'query':    query,
                'type':     'Item',
                'language': 'en',
            },
            timeout=REQUEST_TIMEOUT,
            headers={'User-Agent': 'QuestLog-CH/1.0'},
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            {
                'id':       r.get('itemId'),
                'name':     r.get('en', ''),
                'icon':     f"{XIVAPI_BASE}{r['icon']}" if r.get('icon') else '',
                'ilvl':     r.get('ilvl', 0),
                'category': '',
            }
            for r in data
            if r.get('en') and r.get('itemId') and r.get('type') == 'Item'
        ][:20]
        return JsonResponse({'results': results})
    except Exception as e:
        logger.error('MB item search error: %s', e)
        return JsonResponse({'error': 'Item search failed'}, status=502)

# ---------------------------------------------------------------------------
# API: price lookup (proxies Universalis)
# ---------------------------------------------------------------------------

@require_GET
def api_mb_prices(request):
    item_id = request.GET.get('item_id', '').strip()
    world   = request.GET.get('world', '').strip()

    if not item_id or not item_id.isdigit():
        return JsonResponse({'error': 'Invalid item_id'}, status=400)

    # world can be a world name or DC name
    if world not in ALL_WORLDS and world not in ALL_DCS:
        return JsonResponse({'error': 'Invalid world or data center'}, status=400)

    try:
        resp = requests.get(
            f'{UNIVERSALIS_BASE}/{world}/{item_id}',
            params={'listings': 20, 'entries': 10},
            timeout=REQUEST_TIMEOUT,
            headers={'User-Agent': 'QuestLog-CH/1.0'},
        )
        if resp.status_code == 404:
            return JsonResponse({'error': 'No market data for this item/world'}, status=404)
        resp.raise_for_status()
        data = resp.json()

        listings = data.get('listings', [])
        history  = data.get('recentHistory', [])

        def fmt_listing(l):
            return {
                'price':         l.get('pricePerUnit', 0),
                'quantity':      l.get('quantity', 1),
                'total':         l.get('total', 0),
                'hq':            l.get('hq', False),
                'retainer':      l.get('retainerName', ''),
                'retainer_city': _city_name(l.get('retainerCity', 0)),
                'world':         l.get('worldName', world),
                'last_reviewed': l.get('lastReviewTime', 0),
            }

        def fmt_history(h):
            return {
                'price':     h.get('pricePerUnit', 0),
                'quantity':  h.get('quantity', 1),
                'hq':        h.get('hq', False),
                'buyer':     h.get('buyerName', ''),
                'timestamp': h.get('timestamp', 0),
                'world':     h.get('worldName', world),
            }

        return JsonResponse({
            'item_id':          data.get('itemID'),
            'world':            data.get('worldName', world),
            'last_upload':      data.get('lastUploadTime', 0),
            'listings':         [fmt_listing(l) for l in listings],
            'history':          [fmt_history(h) for h in history],
            'min_price_nq':     data.get('minPriceNQ'),
            'min_price_hq':     data.get('minPriceHQ'),
            'avg_price_nq':     data.get('currentAveragePriceNQ'),
            'avg_price_hq':     data.get('currentAveragePriceHQ'),
            'sale_velocity_nq': round(data.get('nqSaleVelocity', 0), 1),
            'sale_velocity_hq': round(data.get('hqSaleVelocity', 0), 1),
            'listings_count':   data.get('listingsCount', 0),
            'units_for_sale':   data.get('unitsForSale', 0),
        })
    except Exception as e:
        logger.error('MB price lookup error: %s', e)
        return JsonResponse({'error': 'Price lookup failed'}, status=502)


def _city_name(city_id):
    cities = {1: 'Limsa', 2: 'Gridania', 3: "Ul'dah", 4: 'Ishgard', 7: 'Kugane', 8: 'Crystarium', 9: "Old Sharlayan", 10: 'Tuliyollal'}
    return cities.get(city_id, 'Unknown')
