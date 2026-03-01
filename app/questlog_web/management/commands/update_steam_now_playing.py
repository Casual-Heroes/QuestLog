"""
Management command: update_steam_now_playing
Runs every 2 minutes (via cron). Batch-fetches currently-playing game info
for all opted-in users using GetPlayerSummaries (up to 100 steam IDs per call).

Cron setup (run as www-data or the app user):
    */2 * * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py update_steam_now_playing >> /srv/ch-webserver/logs/steam_now_playing.log 2>&1
"""
import os
import logging
import requests

from django.core.management.base import BaseCommand

from app.db import get_db_session
from app.questlog_web.models import WebUser

logger = logging.getLogger(__name__)

STEAM_API_KEY = os.getenv('STEAM_API_KEY', '')
STEAM_API_URL = 'https://api.steampowered.com'
BATCH_SIZE = 100  # GetPlayerSummaries max per request


def _fetch_now_playing_batch(steam_ids: list[str]) -> dict[str, str | None]:
    """
    Call GetPlayerSummaries for up to 100 steam IDs.
    Returns dict: { steam_id: game_name_or_None }
    """
    url = f'{STEAM_API_URL}/ISteamUser/GetPlayerSummaries/v2/'
    params = {
        'key': STEAM_API_KEY,
        'steamids': ','.join(steam_ids),
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        players = resp.json().get('response', {}).get('players', [])
    except requests.RequestException as exc:
        logger.error('update_steam_now_playing: API request failed: %s', exc)
        return {}

    result = {}
    for player in players:
        sid = player.get('steamid')
        if not sid:
            continue
        # gameextrainfo is the human-readable game name; only present when playing
        result[sid] = player.get('gameextrainfo') or None
    return result


class Command(BaseCommand):
    help = 'Batch-update current_game for opted-in users via Steam GetPlayerSummaries.'

    def handle(self, *args, **options):
        if not STEAM_API_KEY:
            self.stderr.write('STEAM_API_KEY not set — aborting.')
            return

        with get_db_session() as db:
            users = db.query(WebUser).filter(
                WebUser.steam_id.isnot(None),
                WebUser.show_playing_status == True,
                WebUser.is_banned == False,
                WebUser.is_disabled == False,
            ).all()

        if not users:
            self.stdout.write('No opted-in users — nothing to do.')
            return

        self.stdout.write(f'Checking now-playing for {len(users)} user(s)...')

        # Map steam_id → user.id for fast lookup
        id_map = {u.steam_id: u.id for u in users}
        steam_ids = list(id_map.keys())

        updated = 0
        cleared = 0

        # Process in batches of 100
        for i in range(0, len(steam_ids), BATCH_SIZE):
            batch = steam_ids[i:i + BATCH_SIZE]
            now_playing = _fetch_now_playing_batch(batch)

            with get_db_session() as db:
                for sid in batch:
                    user_id = id_map[sid]
                    game = now_playing.get(sid)  # None if not returned or not playing

                    u = db.query(WebUser).filter_by(id=user_id).first()
                    if not u:
                        continue

                    if u.current_game != game:
                        if game:
                            self.stdout.write(f'  {u.username}: now playing "{game}"')
                            updated += 1
                        else:
                            cleared += 1
                        u.current_game = game

                db.commit()

        self.stdout.write(f'Done. Updated: {updated}, Cleared: {cleared}')
