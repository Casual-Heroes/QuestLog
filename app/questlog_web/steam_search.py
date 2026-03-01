"""
Steam Search Execution
Uses Steam's storefront search API (tag-based) for game discovery.

SteamSpy is NOT used — it is blocked from this server.
Tag names are resolved to Steam numeric tag IDs via:
  1. An in-process cache seeded with known common tags
  2. Fallback: parse the Steam tag page to extract the ID

Coming-soon searches use filter=comingsoon on Steam's search endpoint.
Released-game searches use no filter (shows all released + EA games).
"""
import re
import json
import time
import asyncio
import logging
import requests

from app.steam_api import get_steam_api
from .models import WebFoundGame

logger = logging.getLogger(__name__)

# Platforms that are NOT consoles — filtered out when building console_platforms
_PC_PLATFORMS = {
    'pc (microsoft windows)', 'windows', 'mac', 'macos', 'linux',
    'pc dos', 'steamos', 'android', 'ios', 'windows phone',
}

# --- Tag ID resolution -------------------------------------------------------
# Steam tags have stable numeric IDs. We seed a cache with common tags so
# simple searches don't require a network call.

_KNOWN_TAG_IDS = {
    'souls-like': 29482,
    'soulslike': 29482,
    'action': 19,
    'rpg': 122,
    'indie': 492,
    'adventure': 21,
    'strategy': 9,
    'simulation': 599,
    'puzzle': 1664,
    'platformer': 1625,
    'roguelike': 1716,
    'roguelite': 3959,
    'metroidvania': 1628,
    'open world': 3831,
    'survival': 1662,
    'horror': 1667,
    'shooter': 1210,
    'fps': 1663,
    'multiplayer': 3859,
    'co-op': 3843,
    'co-operative': 3843,
    'early access': 493,
    'free to play': 113,
    'anime': 4085,
    'visual novel': 3799,
    'card game': 2767,
    'tower defense': 1700,
    'vr': 21978,
    'racing': 1644,
    'sports': 1645,
    'fighting': 1645,
    'story rich': 1716,
    'turn-based': 3808,
    'action rpg': 4182,
    'hack and slash': 1742,
    'stealth': 1647,
    'sandbox': 3695,
    'city builder': 1690,
    'sci-fi': 3942,
    'fantasy': 1684,
    'pixel graphics': 3964,
    'top-down': 1647,
    '2d': 3871,
    '3d': 4182,
}

_tag_id_cache = dict(_KNOWN_TAG_IDS)  # name (lower) → tag_id


def _get_steam_tag_id(tag_name):
    """
    Resolve a Steam tag name to its numeric tag ID.
    Checks the in-process cache first (seeded with KNOWN_TAG_IDS).
    Falls back to parsing Steam's tag page for the ID.
    Returns the int tag ID, or None if not resolvable.
    """
    key = tag_name.lower().strip()
    if key in _tag_id_cache:
        return _tag_id_cache[key]

    # Try to parse the tag ID from Steam's tag browsing page
    safe = requests.utils.quote(tag_name, safe='')
    try:
        r = requests.get(
            f'https://store.steampowered.com/tags/en/{safe}/',
            timeout=12,
            headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'},
        )
        if r.status_code == 200:
            for pattern in [
                r'"tagid"\s*:\s*(\d+)',
                r'data-tag-id=["\'](\d+)',
                r'tags=(\d+)',
            ]:
                m = re.search(pattern, r.text)
                if m:
                    tid = int(m.group(1))
                    _tag_id_cache[key] = tid
                    logger.info(f'steam_search: resolved "{tag_name}" → tag ID {tid}')
                    return tid
    except Exception as e:
        logger.warning(f'steam_search: tag ID lookup failed for "{tag_name}": {e}')

    logger.warning(f'steam_search: could not resolve Steam tag ID for "{tag_name}" — add it to KNOWN_TAG_IDS')
    return None


# --- Steam store search -------------------------------------------------------

_SEARCH_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36',
    'X-Requested-With': 'XMLHttpRequest',
}


def _steam_search_app_ids_html(tag_ids, filter_mode=None):
    """
    Search Steam by requesting the /search/results/ endpoint WITHOUT json=1.
    Returns HTML that properly respects both tags AND filter=comingsoon,
    unlike the json=1 endpoint which ignores tags when filter=comingsoon.
    Paginates up to 500 results. Returns a set of int app IDs.
    """
    if not tag_ids:
        return set()

    tag_ids_csv = ','.join(str(t) for t in tag_ids)
    app_ids = set()
    start = 0

    while True:
        params = {
            'tags': tag_ids_csv,
            'count': '100',
            'start': str(start),
            'cc': 'US',
            'l': 'english',
        }
        if filter_mode:
            params['filter'] = filter_mode

        try:
            r = requests.get(
                'https://store.steampowered.com/search/results/',
                params=params,
                timeout=15,
                headers=_SEARCH_HEADERS,
            )
            r.raise_for_status()
        except Exception as e:
            logger.warning(f'steam_search: HTML search failed (tags={tag_ids_csv}): {e}')
            break

        found = {int(x) for x in re.findall(r'data-ds-appid="(\d+)"', r.text)}
        if not found:
            break

        app_ids |= found
        if len(found) < 100 or start + 100 >= 500:
            break
        start += 100
        time.sleep(0.4)

    return app_ids


def _steam_search_app_ids(tag_ids, filter_mode=None):
    """
    Search Steam's storefront for games matching ALL given tag IDs.
    filter_mode: 'comingsoon', 'topsellers', None (all games), etc.
    Paginates up to 500 results. Returns a set of int app IDs.

    The API returns JSON with either:
      - {"items": [{"name": ..., "logo": ".../apps/APPID/..."}]}  (featured style)
      - {"results_html": "...data-ds-appid='APPID'..."}            (search style)
    We handle both.
    """
    if not tag_ids:
        return set()

    tag_ids_csv = ','.join(str(t) for t in tag_ids)
    app_ids = set()
    start = 0

    while True:
        params = {
            'tags': tag_ids_csv,
            'json': '1',
            'count': '100',
            'start': str(start),
            'cc': 'US',
            'l': 'english',
        }
        if filter_mode:
            params['filter'] = filter_mode

        try:
            r = requests.get(
                'https://store.steampowered.com/search/results/',
                params=params,
                timeout=15,
                headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'},
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            logger.warning(f'steam_search: search request failed (tags={tag_ids_csv}): {e}')
            break

        found = set()

        # Format 1: items list with logo URLs containing app IDs
        items = data.get('items') or []
        for item in items:
            logo = item.get('logo', '')
            m = re.search(r'/apps/(\d+)/', logo)
            if m:
                found.add(int(m.group(1)))

        # Format 2: results_html with data-ds-appid attributes
        html = data.get('results_html', '')
        for aid in re.findall(r'data-ds-appid="(\d+)"', html):
            found.add(int(aid))

        if not found:
            break

        app_ids |= found

        # Pagination: items-style has no total_count, stop when fewer than requested
        total = data.get('total_count') or 0
        if total:
            start += 100
            if start >= total or start >= 500:
                break
        else:
            # items-style: if we got fewer than 100, we've reached the end
            if len(found) < 100:
                break
            start += 100
            if start >= 500:
                break

        time.sleep(0.4)

    return app_ids


def _resolve_and_search(include_tags, exclude_tags, coming_soon=False):
    """
    Resolve tag names to IDs, search Steam by tag, apply exclusions.
    Returns a set of int app IDs.

    Steam's filter=comingsoon + json=1 endpoint IGNORES the tags parameter
    and returns all coming-soon games regardless of tag. To work around this:
      - Normal mode: tag search only (no filter). Steam returns released+EA games.
      - Coming-soon mode: intersect tag results (no filter) with coming-soon
        results (filter=comingsoon). The intersection = games that have the
        correct tag AND are coming-soon. "Big Beautiful Women" has no Souls-like
        tag so it won't survive the intersection.
    """
    include_ids = [_get_steam_tag_id(t) for t in include_tags]
    include_ids = [tid for tid in include_ids if tid is not None]

    if not include_ids:
        logger.warning(f'steam_search: no tag IDs resolved for {include_tags}')
        return set()

    if coming_soon:
        # Use the HTML endpoint (without json=1) — it correctly applies BOTH
        # the tags filter AND filter=comingsoon. The json=1 endpoint ignores
        # tags when filter=comingsoon is set, returning all coming-soon games.
        result = _steam_search_app_ids_html(include_ids, filter_mode='comingsoon')
    else:
        result = _steam_search_app_ids(include_ids, filter_mode=None)

    for t in (exclude_tags or []):
        tid = _get_steam_tag_id(t)
        if tid and result:
            fn = _steam_search_app_ids_html if coming_soon else _steam_search_app_ids
            excluded = fn([tid], filter_mode='comingsoon' if coming_soon else None)
            result -= excluded
            time.sleep(0.4)

    return result


# --- IGDB console enrichment -------------------------------------------------

def _igdb_console_platforms(game_name):
    """
    Search IGDB for game_name and return (igdb_id, igdb_url, [console platform names]).
    Returns (None, None, []) on failure or no match.
    """
    try:
        from app.utils.igdb import search_games

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(search_games(game_name, limit=5))
        finally:
            loop.close()

        if not results:
            return None, None, []

        # Best match: exact name first, then first result
        match = None
        name_lower = game_name.lower()
        for g in results:
            if g.name and g.name.lower() == name_lower:
                match = g
                break
        if match is None:
            match = results[0]

        # Filter to console platforms only
        consoles = [
            p for p in (match.platforms or [])
            if p.lower() not in _PC_PLATFORMS
        ]
        igdb_url = f'https://www.igdb.com/games/{match.slug}' if match.slug else None
        return match.id, igdb_url, consoles

    except Exception as e:
        logger.warning(f'steam_search: IGDB lookup for "{game_name}" failed: {e}')
        return None, None, []


# --- Main runner -------------------------------------------------------------

def run_steam_search_config(config, db):
    """
    Execute one WebSteamSearchConfig.

    Returns:
        (new_count: int, updated_count: int, error: str|None)
    """
    now = int(time.time())

    # Claim this run immediately so the cron job won't start a concurrent run
    # for the same config while we're still working.
    config.last_run_at = now
    db.commit()

    include_tags = json.loads(config.steam_tags or '[]')
    exclude_tags = json.loads(config.exclude_tags or '[]')

    if not include_tags:
        config.last_error = 'No steam_tags configured'
        config.last_run_at = now
        db.commit()
        return 0, 0, 'No steam_tags configured'

    # 1. Search Steam by tag
    # coming_soon_only → filter=comingsoon (upcoming games only)
    # normal           → no filter (released + early access)
    try:
        app_ids = _resolve_and_search(include_tags, exclude_tags, coming_soon=bool(config.coming_soon_only))
    except Exception as e:
        err = f'Steam search error: {e}'
        config.last_error = err
        config.last_run_at = now
        db.commit()
        return 0, 0, err

    if not app_ids:
        config.last_error = None
        config.last_run_at = now
        config.last_result_count = 0
        db.commit()
        return 0, 0, None

    # Limit candidates before fetching details (cap at max_results * 3)
    max_candidates = (config.max_results or 50) * 3
    app_ids = list(app_ids)[:max_candidates]

    # 2. Fetch Steam details + upsert
    steam_api = get_steam_api()
    new_count = 0
    updated_count = 0
    stored = 0
    max_results = config.max_results or 50

    for app_id in app_ids:
        if stored >= max_results:
            break

        try:
            details = steam_api.get_game_details(app_id)
        except Exception as e:
            logger.warning(f'steam_search: get_game_details({app_id}) error: {e}')
            continue

        if not details:
            continue

        # Apply config filters
        if config.coming_soon_only:
            # Safety check: skip anything that already has a release date
            if details.get('release_date') is not None:
                continue
        else:
            # min_reviews only applies to released games (coming-soon = 0 always)
            review_count = 0  # Steam appdetails doesn't expose review counts
            if config.min_reviews and review_count < config.min_reviews:
                continue

        # Build genres & platforms lists
        genres = details.get('tags', [])
        platforms = details.get('platforms', [])
        developer = (details.get('developers') or [''])[0] if details.get('developers') else None
        publisher = (details.get('publishers') or [''])[0] if details.get('publishers') else None

        # Release date as string
        release_date_ts = details.get('release_date')
        release_date_str = None
        if release_date_ts:
            import datetime
            try:
                release_date_str = datetime.datetime.fromtimestamp(release_date_ts).strftime('%b %d, %Y')
            except Exception:
                pass

        existing = db.query(WebFoundGame).filter_by(steam_app_id=app_id).first()

        if existing:
            existing.name = details['name'] or existing.name
            existing.cover_url = details.get('cover_url') or existing.cover_url
            existing.header_url = details.get('cover_url') or existing.header_url
            existing.summary = (details.get('description') or '')[:2000] or existing.summary
            existing.release_date = release_date_str or existing.release_date
            existing.developer = developer or existing.developer
            existing.publisher = publisher or existing.publisher
            existing.price = details.get('price') or existing.price
            existing.genres = json.dumps(genres)
            existing.platforms = json.dumps(platforms)
            existing.steam_tags = json.dumps(genres)
            existing.search_config_id = config.id
            existing.updated_at = now
            updated_count += 1
            game = existing
        else:
            game = WebFoundGame(
                steam_app_id=app_id,
                name=details['name'],
                steam_url=details.get('steam_url', f'https://store.steampowered.com/app/{app_id}'),
                cover_url=details.get('cover_url'),
                header_url=details.get('cover_url'),
                summary=(details.get('description') or '')[:2000],
                release_date=release_date_str,
                developer=developer,
                publisher=publisher,
                price=details.get('price'),
                genres=json.dumps(genres),
                platforms=json.dumps(platforms),
                steam_tags=json.dumps(genres),
                review_score=None,
                review_count=0,
                search_config_id=config.id,
                console_platforms='[]',
                found_at=now,
                updated_at=now,
            )
            db.add(game)
            new_count += 1

        try:
            db.flush()  # get game.id if new
        except Exception as flush_err:
            logger.warning(f'steam_search: flush error for app {app_id}, skipping: {flush_err}')
            db.rollback()
            continue

        # 3. IGDB console enrichment
        if config.include_consoles and details.get('name'):
            igdb_id, igdb_url, consoles = _igdb_console_platforms(details['name'])
            game.igdb_id = igdb_id
            game.igdb_url = igdb_url
            game.console_platforms = json.dumps(consoles)

        stored += 1

        # Commit per game to release row locks promptly.
        # A long-running transaction holding locks across many external API
        # calls causes Lock wait timeout on concurrent web requests.
        try:
            db.commit()
        except Exception as commit_err:
            logger.warning(f'steam_search: commit error for app {app_id}: {commit_err}')
            db.rollback()

    config.last_run_at = now
    config.last_result_count = new_count + updated_count
    config.last_error = None
    db.commit()

    return new_count, updated_count, None
