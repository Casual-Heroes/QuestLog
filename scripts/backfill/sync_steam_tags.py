#!/usr/bin/env python3
"""
Syncs Steam app tags from SteamSpy for all app_ids in user Steam libraries.
Run: chwebsiteprj/bin/python3 sync_steam_tags.py [--limit N]
"""
import os, sys, django, time, json, threading, argparse
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from sqlalchemy import text
from app.db import get_db_session, get_engine
from app.questlog_web.models import WebUser

parser = argparse.ArgumentParser()
parser.add_argument('--limit', type=int, default=0)
parser.add_argument('--workers', type=int, default=15)
parser.add_argument('--force', action='store_true')
parser.add_argument('--steam-id', type=str, default='', help='Steam ID to fetch library for')
args = parser.parse_args()

print('Collecting app_ids from Steam libraries...')
all_ids = set()

# Fetch library for all users with steam_id set
from app.questlog_web.steam_auth import get_steam_owned_games
from app.questlog_web.helpers import STEAM_API_KEY

with get_db_session() as db:
    users = db.query(WebUser).filter(WebUser.steam_id.isnot(None)).all()
    steam_ids = [(u.id, u.steam_id) for u in users if u.steam_id]

steam_ids_to_fetch = [(uid, sid) for uid, sid in steam_ids]
if args.steam_id:
    steam_ids_to_fetch = [(0, args.steam_id)]

for uid, sid in steam_ids_to_fetch:
    try:
        games = get_steam_owned_games(sid, STEAM_API_KEY, include_free=True)
        if games:
            for g in games:
                if g.get('app_id'):
                    all_ids.add(int(g['app_id']))
        print(f'  User steam_id={sid}: {len(games or [])} games')
    except Exception as e:
        print(f'  Failed for steam_id={sid}: {e}')

print(f'Found {len(all_ids)} unique app_ids.')

if not args.force:
    with get_db_session() as db:
        rows = db.execute(text('SELECT DISTINCT app_id FROM web_steam_app_tags')).fetchall()
        synced = {r[0] for r in rows}
    all_ids -= synced
    print(f'{len(all_ids)} not yet synced.')

to_process = list(all_ids)
if args.limit:
    to_process = to_process[:args.limit]

total = len(to_process)
print(f'Processing {total} app_ids with {args.workers} workers...')

done = 0
stored = 0
now = int(time.time())

def fetch_tags(app_id):
    try:
        resp = requests.get(
            f'https://steamspy.com/api.php?request=appdetails&appid={app_id}',
            headers={'User-Agent': 'Mozilla/5.0'}, timeout=8
        ).json()
        tags = resp.get('tags', {})
        if isinstance(tags, dict) and tags:
            return app_id, [t.lower() for t in tags.keys()]
        return app_id, None
    except Exception:
        return app_id, None

BATCH = 50
for batch_start in range(0, total, BATCH):
    batch = to_process[batch_start:batch_start + BATCH]
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(fetch_tags, aid): aid for aid in batch}
        for fut in as_completed(futures):
            app_id, tags = fut.result()
            done += 1
            if tags:
                try:
                    with get_db_session() as db:
                        for tag in tags:
                            db.execute(text(
                                'INSERT IGNORE INTO web_steam_app_tags (app_id, tag_name, synced_at) '
                                'VALUES (:app_id, :tag, :now)'
                            ), {'app_id': app_id, 'tag': tag, 'now': now})
                        db.commit()
                    stored += 1
                except Exception as e:
                    print(f'  DB error for {app_id}: {e}')

    if batch_start + BATCH < total:
        time.sleep(1)

    if done % 50 == 0 or done == total:
        print(f'  {done}/{total} processed, tags stored for {stored}')

print(f'Done. {done} processed, tags stored for {stored}.')
