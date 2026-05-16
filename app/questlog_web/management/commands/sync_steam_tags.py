"""
Syncs Steam app tags from SteamSpy for all app_ids in user Steam libraries.
Stores results in web_steam_app_tags for instant SteamQuest genre filtering.
Run: chwebsiteprj/bin/python3 manage.py sync_steam_tags [--limit N] [--app-id X]
"""
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.management.base import BaseCommand
import requests
from app.db import get_db_session
from app.questlog_web.models import WebUser, WebSteamAppTag
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy import text

logger = logging.getLogger(__name__)


def fetch_tags_from_steamspy(app_id):
    try:
        resp = requests.get(
            f'https://steamspy.com/api.php?request=appdetails&appid={app_id}',
            headers={'User-Agent': 'Mozilla/5.0 (SteamQuestSync/1.0)'},
            timeout=8
        )
        data = resp.json()
        tags_raw = data.get('tags', {})
        if not isinstance(tags_raw, dict) or not tags_raw:
            return app_id, None  # rate-limited or no tags - don't store
        return app_id, [t.lower() for t in tags_raw.keys()]
    except Exception:
        return app_id, None


class Command(BaseCommand):
    help = 'Sync Steam app tags from SteamSpy into web_steam_app_tags'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=0,
                            help='Max app_ids to process (0 = all)')
        parser.add_argument('--app-id', type=int, default=0,
                            help='Sync a single app_id')
        parser.add_argument('--workers', type=int, default=10,
                            help='Concurrent SteamSpy workers (default 10)')
        parser.add_argument('--force', action='store_true',
                            help='Re-fetch even if already synced')

    def handle(self, *args, **options):
        import json as _json

        single_app_id = options['app_id']
        limit = options['limit']
        workers = options['workers']
        force = options['force']

        if single_app_id:
            app_ids_to_process = [single_app_id]
        else:
            # Collect all unique app_ids from user libraries
            self.stdout.write('Collecting app_ids from user libraries...')
            all_ids = set()
            with get_db_session() as db:
                users = db.query(WebUser).filter(
                    WebUser.steam_library.isnot(None),
                    WebUser.share_steam_library == True
                ).all()
                for u in users:
                    try:
                        lib = _json.loads(u.steam_library) if isinstance(u.steam_library, str) else (u.steam_library or [])
                        for g in lib:
                            if isinstance(g, dict) and g.get('appid'):
                                all_ids.add(int(g['appid']))
                    except Exception:
                        pass
            self.stdout.write(f'Found {len(all_ids)} unique app_ids across all libraries.')

            if not force:
                # Find which ones we haven't synced yet
                with get_db_session() as db:
                    synced = {row[0] for row in db.execute(
                        text('SELECT DISTINCT app_id FROM web_steam_app_tags')
                    )}
                all_ids -= synced
                self.stdout.write(f'{len(all_ids)} app_ids not yet synced.')

            app_ids_to_process = list(all_ids)
            if limit:
                app_ids_to_process = app_ids_to_process[:limit]

        total = len(app_ids_to_process)
        self.stdout.write(f'Processing {total} app_ids with {workers} workers...')

        done = 0
        stored = 0
        now = int(time.time())

        # Process in batches of 50 to avoid memory buildup and give SteamSpy a break
        BATCH = 50
        for batch_start in range(0, total, BATCH):
            batch = app_ids_to_process[batch_start:batch_start + BATCH]
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(fetch_tags_from_steamspy, aid): aid for aid in batch}
                for future in as_completed(futures):
                    app_id, tags = future.result()
                    done += 1
                    if tags:
                        with get_db_session() as db:
                            for tag in tags:
                                db.execute(text(
                                    'INSERT IGNORE INTO web_steam_app_tags (app_id, tag_name, synced_at) '
                                    'VALUES (:app_id, :tag_name, :synced_at)'
                                ), {'app_id': app_id, 'tag_name': tag, 'synced_at': now})
                            db.commit()
                        stored += 1

            if batch_start + BATCH < total:
                time.sleep(1)  # be gentle with SteamSpy between batches

            if done % 100 == 0 or done == total:
                self.stdout.write(f'  {done}/{total} processed, {stored} stored tags for')

        self.stdout.write(self.style.SUCCESS(
            f'Done. {done} app_ids processed, tags stored for {stored} of them.'
        ))
