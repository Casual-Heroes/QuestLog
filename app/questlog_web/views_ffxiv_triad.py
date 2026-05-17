import json
import time
import logging
import requests
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.cache import cache_page
from app.db import get_db_session
from app.questlog_web.models import WebFfxivTriadCard, WebFfxivTriadDeck, WebUser
from app.questlog_web.helpers import get_web_user, web_login_required, add_web_user_context, safe_int

logger = logging.getLogger(__name__)

XIVAPI_BASE = 'https://xivapi.com'
TRIAD_CARD_CACHE = {'cards': None, 'fetched_at': 0}
CACHE_TTL = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Static card data fetch
# ---------------------------------------------------------------------------

def _get_all_cards():
    """Fetch all Triple Triad cards from XIVAPI, cached in-process for 1h."""
    now = time.time()
    if TRIAD_CARD_CACHE['cards'] and (now - TRIAD_CARD_CACHE['fetched_at']) < CACHE_TTL:
        return TRIAD_CARD_CACHE['cards']

    try:
        cards = []
        page = 1
        while True:
            resp = requests.get(
                f'{XIVAPI_BASE}/TripleTriadCard',
                params={'limit': 500, 'page': page, 'columns': 'ID,Name,TripleTriadCardRarity.Stars'},
                timeout=10,
                headers={'User-Agent': 'QuestLog-CH/1.0'},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get('Results', [])
            if not results:
                break
            for r in results:
                cid = r.get('ID')
                if not cid:
                    continue
                stars = 0
                rarity = r.get('TripleTriadCardRarity')
                if rarity and rarity.get('Stars'):
                    stars = rarity['Stars']
                icon = f"https://ffxivcollect.com/images/cards/large/{cid}.png"
                cards.append({
                    'id':    cid,
                    'name':  r.get('Name', ''),
                    'icon':  icon,
                    'stars': stars,
                })
            if len(results) < 500:
                break
            page += 1

        cards.sort(key=lambda c: c['id'])
        TRIAD_CARD_CACHE['cards'] = cards
        TRIAD_CARD_CACHE['fetched_at'] = now
        return cards
    except Exception as e:
        logger.error('Failed to fetch Triple Triad cards from XIVAPI: %s', e)
        return TRIAD_CARD_CACHE['cards'] or []


# ---------------------------------------------------------------------------
# Card source data (static, maintained by hand - NPC/pack/drop sources)
# ---------------------------------------------------------------------------

# Maps card_id -> source info. Add more over time.
CARD_SOURCES = {
    1:   {'type': 'npc',  'source': 'Triple Triad Master (Gold Saucer)'},
    2:   {'type': 'npc',  'source': 'Triple Triad Master (Gold Saucer)'},
    3:   {'type': 'npc',  'source': 'Triple Triad Master (Gold Saucer)'},
    4:   {'type': 'npc',  'source': 'Triple Triad Master (Gold Saucer)'},
    5:   {'type': 'npc',  'source': 'Triple Triad Master (Gold Saucer)'},
    6:   {'type': 'pack', 'source': 'Starter Pack (MGP)'},
    7:   {'type': 'pack', 'source': 'Starter Pack (MGP)'},
    8:   {'type': 'pack', 'source': 'Starter Pack (MGP)'},
    9:   {'type': 'pack', 'source': 'Booster Pack I (MGP)'},
    10:  {'type': 'pack', 'source': 'Booster Pack I (MGP)'},
}


# ---------------------------------------------------------------------------
# Page view
# ---------------------------------------------------------------------------

@add_web_user_context
def ffxiv_triple_triad(request):
    web_user = get_web_user(request)
    my_owned = set()
    my_decks = []
    fc_counts = {}

    with get_db_session() as db:
        if web_user:
            rows = db.query(WebFfxivTriadCard).filter_by(user_id=web_user.id).all()
            my_owned = {r.card_id for r in rows}

            my_decks = [
                {
                    'id':       d.id,
                    'name':     d.name,
                    'card_ids': json.loads(d.card_ids),
                    'updated_at': d.updated_at,
                }
                for d in db.query(WebFfxivTriadDeck).filter_by(user_id=web_user.id).order_by(WebFfxivTriadDeck.updated_at.desc()).all()
            ]

        # FC leaderboard: users with the most cards
        rows = (
            db.query(
                WebFfxivTriadCard.user_id,
                WebUser.display_name,
                WebUser.avatar_url,
            )
            .join(WebUser, WebUser.id == WebFfxivTriadCard.user_id)
            .filter(WebUser.is_banned == False)
            .all()
        )
        # aggregate in Python
        from collections import defaultdict
        user_counts = defaultdict(lambda: {'display_name': '', 'avatar_url': '', 'count': 0})
        for row in rows:
            user_counts[row.user_id]['display_name'] = row.display_name or ''
            user_counts[row.user_id]['avatar_url'] = row.avatar_url or ''
            user_counts[row.user_id]['count'] += 1

        fc_counts = sorted(user_counts.values(), key=lambda x: x['count'], reverse=True)[:10]

    return render(request, 'questlog_web/ffxiv_triple_triad.html', {
        'active_page':    'ffxiv_triple_triad',
        'my_owned_data':  list(my_owned),
        'my_decks_data':  my_decks,
        'fc_counts_data': list(fc_counts),
        'is_logged_in':   bool(web_user),
        'is_admin':       bool(web_user and web_user.is_admin),
        'web_user':       web_user,
    })


# ---------------------------------------------------------------------------
# API: clear all owned cards for current user
# ---------------------------------------------------------------------------

@require_POST
@web_login_required
def api_triad_clear_all(request):
    web_user = get_web_user(request)
    with get_db_session() as db:
        db.query(WebFfxivTriadCard).filter_by(user_id=web_user.id).delete()
        db.commit()
    return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# API: get all cards (cached proxy)
# ---------------------------------------------------------------------------

@require_GET
def api_triad_cards(request):
    cards = _get_all_cards()
    return JsonResponse({'cards': cards})


# ---------------------------------------------------------------------------
# API: toggle card owned/not-owned
# ---------------------------------------------------------------------------

@require_POST
@web_login_required
def api_triad_toggle(request):
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    card_id = safe_int(body.get('card_id'), 0, 1, 99999)
    if not card_id:
        return JsonResponse({'error': 'Invalid card_id'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        existing = db.query(WebFfxivTriadCard).filter_by(user_id=web_user.id, card_id=card_id).first()
        if existing:
            db.delete(existing)
            db.commit()
            return JsonResponse({'owned': False, 'card_id': card_id})
        else:
            db.add(WebFfxivTriadCard(user_id=web_user.id, card_id=card_id, obtained_at=now))
            db.commit()
            return JsonResponse({'owned': True, 'card_id': card_id})


# ---------------------------------------------------------------------------
# API: bulk mark cards
# ---------------------------------------------------------------------------

@require_POST
@web_login_required
def api_triad_bulk_mark(request):
    """Mark multiple cards as owned at once."""
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    card_ids = body.get('card_ids', [])
    if not isinstance(card_ids, list) or len(card_ids) > 500:
        return JsonResponse({'error': 'Invalid card_ids'}, status=400)

    card_ids = [safe_int(c, 0, 1, 99999) for c in card_ids if safe_int(c, 0, 1, 99999)]

    now = int(time.time())
    with get_db_session() as db:
        existing = {r.card_id for r in db.query(WebFfxivTriadCard).filter_by(user_id=web_user.id).all()}
        new_ids = set(card_ids) - existing
        for cid in new_ids:
            db.add(WebFfxivTriadCard(user_id=web_user.id, card_id=cid, obtained_at=now))
        db.commit()

    return JsonResponse({'added': len(new_ids)})


# ---------------------------------------------------------------------------
# API: save deck
# ---------------------------------------------------------------------------

@require_POST
@web_login_required
def api_triad_deck_save(request):
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    deck_id  = safe_int(body.get('deck_id'), 0, 0, 999999)
    name     = body.get('name', '').strip()[:64]
    card_ids = body.get('card_ids', [])

    if not name:
        return JsonResponse({'error': 'Deck name required'}, status=400)
    if not isinstance(card_ids, list) or len(card_ids) != 5:
        return JsonResponse({'error': 'Exactly 5 cards required'}, status=400)

    card_ids = [safe_int(c, 0, 1, 99999) for c in card_ids if safe_int(c, 0, 1, 99999)]
    if len(card_ids) != 5:
        return JsonResponse({'error': 'Invalid card IDs'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        if deck_id:
            deck = db.query(WebFfxivTriadDeck).filter_by(id=deck_id, user_id=web_user.id).first()
            if not deck:
                return JsonResponse({'error': 'Deck not found'}, status=404)
            deck.name     = name
            deck.card_ids = json.dumps(card_ids)
            deck.updated_at = now
        else:
            # Max 10 decks per user
            count = db.query(WebFfxivTriadDeck).filter_by(user_id=web_user.id).count()
            if count >= 10:
                return JsonResponse({'error': 'Maximum 10 decks allowed'}, status=400)
            deck = WebFfxivTriadDeck(
                user_id=web_user.id,
                name=name,
                card_ids=json.dumps(card_ids),
                created_at=now,
                updated_at=now,
            )
            db.add(deck)
            db.flush()
            deck_id = deck.id
        db.commit()

    return JsonResponse({'ok': True, 'deck_id': deck_id, 'name': name, 'card_ids': card_ids})


# ---------------------------------------------------------------------------
# API: delete deck
# ---------------------------------------------------------------------------

@require_POST
@web_login_required
def api_triad_deck_delete(request):
    web_user = get_web_user(request)
    try:
        body = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    deck_id = safe_int(body.get('deck_id'), 0, 1, 999999)
    if not deck_id:
        return JsonResponse({'error': 'Invalid deck_id'}, status=400)

    with get_db_session() as db:
        deck = db.query(WebFfxivTriadDeck).filter_by(id=deck_id, user_id=web_user.id).first()
        if deck:
            db.delete(deck)
            db.commit()

    return JsonResponse({'ok': True})
