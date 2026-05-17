"""
Management command: warm_discover_cache
Runs every 15 minutes (via cron). Pre-builds the discover Steam widgets cache
so the first visitor after idle never hits a cold Steam API call and gets a 521.

Cron setup:
    */15 * * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py warm_discover_cache >> /srv/ch-webserver/logs/warm_cache.log 2>&1
"""
import os
import time
import logging

from django.core.management.base import BaseCommand
from django.core.cache import cache

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Pre-warms the discover page Steam widgets cache'

    def handle(self, *args, **options):
        # Ensure cache files are group-readable so www-data (gunicorn) can read them
        os.umask(0o002)
        from app.db import get_db_session
        from app.questlog_web.models import WebUser
        from app.questlog_web.steam_auth import get_steam_owned_games
        from app.questlog_web.helpers import STEAM_API_KEY
        from collections import Counter
        from sqlalchemy import text

        start = time.time()
        self.stdout.write('Warming discover cache...')

        # Always refresh per-user library caches first (10 min TTL)
        with get_db_session() as db:
            steam_users = db.query(WebUser.steam_id).filter(
                WebUser.share_steam_library == True,
                WebUser.steam_id.isnot(None),
                WebUser.steam_id != '',
                WebUser.is_banned == False,
                WebUser.is_disabled == False,
            ).limit(200).all()

            adult_rows = db.execute(
                text("SELECT DISTINCT app_id FROM web_steam_app_tags WHERE tag_name = 'sexual content'")
            ).fetchall()
            adult_ids = {r[0] for r in adult_rows}

            mp_rows = db.execute(
                text("SELECT DISTINCT app_id FROM web_steam_app_tags WHERE tag_name IN ('multiplayer','co-op','online co-op','multi-player')")
            ).fetchall()
            mp_ids = {r[0] for r in mp_rows}

        fetched = 0
        for (steam_id,) in steam_users:
            lib_key = f'steamquest_library_{steam_id}'
            library = cache.get(lib_key)
            if library is None:
                library = get_steam_owned_games(steam_id, STEAM_API_KEY, include_free=True)
                if library:
                    cache.set(lib_key, library, 600)
                    fetched += 1
                    self.stdout.write(f'  Fetched library for {steam_id} ({len(library)} games)')
                else:
                    self.stdout.write(f'  Skipped {steam_id} (private or unavailable)')
            else:
                self.stdout.write(f'  Cache hit for {steam_id}')

        # Now rebuild the widget aggregate cache using recent (2-week) playtime
        import requests as _req
        owned_counts = Counter()
        hours_totals = Counter()  # minutes of recent playtime per app
        game_names = {}

        for (steam_id,) in steam_users:
            try:
                resp = _req.get(
                    'https://api.steampowered.com/IPlayerService/GetRecentlyPlayedGames/v1/',
                    params={'key': STEAM_API_KEY, 'steamid': steam_id, 'count': 0},
                    timeout=5,
                )
                for g in resp.json().get('response', {}).get('games', []):
                    aid = g.get('appid')
                    if not aid or aid in adult_ids:
                        continue
                    owned_counts[aid] += 1
                    hours_totals[aid] += g.get('playtime_2weeks', 0)
                    if aid not in game_names:
                        game_names[aid] = g.get('name', '')
            except Exception:
                continue

        if owned_counts:
            def _entry(aid, count, mins=None):
                return {
                    'app_id': aid,
                    'name': game_names[aid],
                    'count': count,
                    'hours': round(mins / 60, 1) if mins is not None else None,
                    'cover_url': f'https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/capsule_sm_120.jpg',
                    'steam_url': f'https://store.steampowered.com/app/{aid}/',
                    'is_mp': aid in mp_ids,
                }

            top_hours = [_entry(aid, owned_counts[aid], mins)
                         for aid, mins in hours_totals.most_common(5)]

            steam_data = {
                'hours': top_hours,
                'all_owned': list(owned_counts.keys()),
                'owned_counts': dict(owned_counts),
                'game_names': game_names,
                'mp_ids': mp_ids,
            }
            cache.set('discover_steam_widgets', steam_data, 1800)
            self.stdout.write(f'  Widget cache rebuilt: {len(owned_counts)} games, top={top_hours[0]["name"] if top_hours else "none"}')
        else:
            self.stdout.write('  No library data available - widget cache not set')

        elapsed = time.time() - start
        self.stdout.write(f'Done in {elapsed:.1f}s (fetched {fetched} fresh libraries)')
