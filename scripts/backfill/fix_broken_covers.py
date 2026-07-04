"""
Find all games where the Steam library_600x900.jpg URL 404s and fix via IGDB.
Run: chwebsiteprj/bin/python3 fix_broken_covers.py
"""
import os, sys, django, asyncio, time, re, requests
sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.utils.igdb import search_games as igdb_search

engine = get_engine()

# Suffixes that are Steam-specific noise, not part of the real game title
_NOISE_SUFFIXES = [
    r"\s*[-–]\s*(Public Test|Staging Branch|Unstable|Beta|Demo|Playtest|Beta Weekend|Beta Demo|Friend.s Pass)",
    r'\s*(Playtest|Demo|Beta)$',
    r'\s+NA$',
]
_NOISE_RE = re.compile('|'.join(_NOISE_SUFFIXES), re.IGNORECASE)

# Unicode junk
_UNICODE_JUNK = re.compile(r'[®™©]')

# Edition suffixes - try without these if exact match fails
_EDITION_SUFFIXES = re.compile(
    r'\s*[-–:]\s*(Ultimate Edition|Deluxe Edition|Premium Edition|Enhanced Edition|'
    r'HD Edition|4K/HD EDITION|Complete Edition|Game of the Year Edition|GOTY Edition)$',
    re.IGNORECASE
)

def clean_name(name):
    name = _UNICODE_JUNK.sub('', name)
    name = _NOISE_RE.sub('', name)
    return name.strip()

def check_url(url):
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False

def igdb_cover(name):
    loop = asyncio.new_event_loop()
    # Try clean name first, then without edition suffix
    searches = [clean_name(name)]
    no_edition = _EDITION_SUFFIXES.sub('', clean_name(name)).strip()
    if no_edition != searches[0]:
        searches.append(no_edition)

    for search_name in searches:
        try:
            results = loop.run_until_complete(igdb_search(search_name, limit=1))
            if results and results[0].cover_url:
                loop.close()
                return results[0].cover_url, search_name
        except Exception as e:
            print(f"  IGDB error for {search_name!r}: {e}")
    loop.close()
    return None, None

with Session(engine) as db:
    rows = db.execute(text("""
        SELECT DISTINCT name, steam_app_id, cover_url
        FROM web_user_games
        WHERE cover_url LIKE '%steamstatic.com%'
           OR cover_url LIKE '%steamcdn%'
           OR cover_url LIKE '%akamaihd%'
        ORDER BY name
    """)).fetchall()

    print(f"Checking {len(rows)} distinct Steam cover URLs...")
    broken = []

    for r in rows:
        if not check_url(r.cover_url):
            print(f"  BROKEN: {r.name!r}")
            broken.append(r)

    print(f"\nFound {len(broken)} broken Steam covers, fetching IGDB replacements...")
    fixed = 0

    for r in broken:
        print(f"  Fixing: {r.name!r} (steam={r.steam_app_id})")
        new_url, matched_name = igdb_cover(r.name)
        if new_url:
            result = db.execute(text("""
                UPDATE web_user_games SET cover_url = :url
                WHERE name = :name AND cover_url NOT LIKE 'https://images.igdb.com%'
            """), {'url': new_url, 'name': r.name})
            print(f"    -> matched as {matched_name!r}, {result.rowcount} rows updated")
            fixed += 1
        else:
            print(f"    -> No IGDB cover found (tried: {clean_name(r.name)!r})")
        time.sleep(0.25)

    db.commit()
    print(f"\nDone. Fixed {fixed} / {len(broken)} broken covers.")
