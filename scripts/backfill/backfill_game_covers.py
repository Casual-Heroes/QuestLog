"""
Backfill cover URLs for WebUserGame rows where the stored Steam cover URL returns 404.
Falls back to IGDB. Checks distinct cover URLs only (not per-user row).
Run: chwebsiteprj/bin/python3 backfill_game_covers.py
"""
import os, sys, django, time, asyncio, requests

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from app.utils.igdb import search_games
from sqlalchemy.orm import Session
from sqlalchemy import text


def igdb_cover(name):
    try:
        loop = asyncio.new_event_loop()
        results = loop.run_until_complete(search_games(name, limit=1))
        loop.close()
        if results and results[0].cover_url:
            return results[0].cover_url
    except Exception as e:
        print(f"  IGDB error for {name}: {e}")
    return None


def url_ok(url):
    try:
        r = requests.head(url, timeout=5, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False


engine = get_engine()
with Session(engine) as db:
    rows = db.execute(text(
        "SELECT name, cover_url FROM web_user_games "
        "WHERE cover_url IS NOT NULL "
        "GROUP BY name, cover_url ORDER BY name"
    )).fetchall()

    print(f"Checking {len(rows)} distinct game+cover combos...")
    fixed = 0

    for i, row in enumerate(rows):
        name, cover_url = row

        if not url_ok(cover_url):
            print(f"  [{i+1}/{len(rows)}] BROKEN: {name}")
            new_url = igdb_cover(name)
            if new_url:
                print(f"    -> {new_url}")
                db.execute(text(
                    "UPDATE web_user_games SET cover_url = :url "
                    "WHERE name = :name AND cover_url = :old"
                ), {'url': new_url, 'name': name, 'old': cover_url})
                db.commit()
                fixed += 1
            else:
                print(f"    -> No IGDB cover found")
            time.sleep(0.25)
        elif (i + 1) % 100 == 0:
            print(f"  Progress: {i+1}/{len(rows)}")

    print(f"\nDone. {fixed} covers fixed out of {len(rows)} checked.")
