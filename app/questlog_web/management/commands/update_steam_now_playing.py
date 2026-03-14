"""
Management command: update_steam_now_playing
Runs every 2 minutes (via cron). Batch-fetches currently-playing game info
for all opted-in users using GetPlayerSummaries (up to 100 steam IDs per call).
Also syncs Fluxer custom status for users who have opted in.

Cron setup (run as www-data or the app user):
    */2 * * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py update_steam_now_playing >> /srv/ch-webserver/logs/steam_now_playing.log 2>&1
"""
import os
import time
import logging
import requests

from django.core.management.base import BaseCommand

from app.db import get_db_session
from app.questlog_web.models import WebUser

GAME_LAUNCH_COOLDOWN = 1800  # 30 minutes between XP awards for game launches

logger = logging.getLogger(__name__)

STEAM_API_KEY = os.getenv('STEAM_API_KEY', '')
STEAM_API_URL = 'https://api.steampowered.com'
FLUXER_API_URL = 'https://api.fluxer.app/v1'
BATCH_SIZE = 100  # GetPlayerSummaries max per request


def _fetch_now_playing_batch(steam_ids: list[str]) -> dict[str, str | None]:
    """
    Call GetPlayerSummaries for up to 100 steam IDs.
    Returns dict: { steam_id: (game_name_or_None, appid_or_None) }
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
        # gameextrainfo is the human-readable game name; gameid is the Steam app ID
        game_name = player.get('gameextrainfo') or None
        game_appid = int(player['gameid']) if game_name and player.get('gameid') else None
        result[sid] = (game_name, game_appid)
    return result


def _refresh_fluxer_token(user: WebUser) -> str | None:
    """
    Attempt to refresh the Fluxer access token using the stored refresh token.
    Updates the user object in place (caller must commit).
    Returns the new access token on success, None on failure.
    """
    from app.utils.encryption import decrypt_token, encrypt_token
    from django.conf import settings as dj_settings

    if not user.fluxer_refresh_token_enc:
        return None

    try:
        refresh_token = decrypt_token(user.fluxer_refresh_token_enc)
    except Exception:
        return None

    try:
        resp = requests.post(f'{FLUXER_API_URL}/oauth2/token', data={
            'grant_type':    'refresh_token',
            'refresh_token': refresh_token,
            'client_id':     getattr(dj_settings, 'FLUXER_CLIENT_ID', ''),
            'client_secret': getattr(dj_settings, 'FLUXER_CLIENT_SECRET', ''),
        }, timeout=10)
        resp.raise_for_status()
        token_data = resp.json()
    except Exception as exc:
        logger.warning(f'fluxer_token_refresh: failed for user {user.id}: {exc}')
        return None

    new_access  = token_data.get('access_token')
    new_refresh = token_data.get('refresh_token')
    expires_in  = int(token_data.get('expires_in', 0) or 0)

    if not new_access:
        return None

    user.fluxer_access_token_enc  = encrypt_token(new_access)
    if new_refresh:
        user.fluxer_refresh_token_enc = encrypt_token(new_refresh)
    user.fluxer_token_expires_at = int(time.time()) + expires_in if expires_in else None

    return new_access


def _get_fluxer_access_token(user: WebUser, db) -> str | None:
    """
    Return a valid Fluxer access token for the user.
    Refreshes automatically if expired or within 5 minutes of expiry.
    Returns None if not available or refresh fails.
    """
    from app.utils.encryption import decrypt_token

    if not user.fluxer_access_token_enc:
        return None

    now = int(time.time())
    expires_at = user.fluxer_token_expires_at or 0
    # Refresh if expired or expiring within 5 minutes
    if expires_at and now >= expires_at - 300:
        new_token = _refresh_fluxer_token(user)
        if new_token:
            db.commit()
            return new_token
        # Refresh failed - token is expired, can't proceed
        if now >= expires_at:
            return None

    try:
        return decrypt_token(user.fluxer_access_token_enc)
    except Exception:
        return None


def _set_fluxer_custom_status(access_token: str, status_text: str | None, user_id: int) -> bool:
    """
    PATCH /users/@me to set or clear Fluxer custom status.
    status_text=None clears the status.
    Returns True on success.
    """
    payload = {'custom_status': {'text': status_text} if status_text else None}
    try:
        resp = requests.patch(
            f'{FLUXER_API_URL}/users/@me',
            json=payload,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
            timeout=8,
        )
        if resp.status_code in (200, 204):
            return True
        logger.warning(f'fluxer_custom_status: HTTP {resp.status_code} for user {user_id}: {resp.text[:200]}')
        return False
    except Exception as exc:
        logger.warning(f'fluxer_custom_status: request failed for user {user_id}: {exc}')
        return False


class Command(BaseCommand):
    help = 'Batch-update current_game for opted-in users via Steam GetPlayerSummaries.'

    def handle(self, *args, **options):
        if not STEAM_API_KEY:
            self.stderr.write('STEAM_API_KEY not set - aborting.')
            return

        with get_db_session() as db:
            users = db.query(WebUser).filter(
                WebUser.steam_id.isnot(None),
                WebUser.show_playing_status == True,
                WebUser.is_banned == False,
                WebUser.is_disabled == False,
            ).all()

        if not users:
            self.stdout.write('No opted-in users - nothing to do.')
            return

        self.stdout.write(f'Checking now-playing for {len(users)} user(s)...')

        # Map steam_id -> user.id for fast lookup
        id_map = {u.steam_id: u.id for u in users}
        steam_ids = list(id_map.keys())

        updated = 0
        cleared = 0

        # Process in batches of 100
        for i in range(0, len(steam_ids), BATCH_SIZE):
            batch = steam_ids[i:i + BATCH_SIZE]
            now_playing = _fetch_now_playing_batch(batch)

            # Collect XP/status work to do AFTER the DB session closes.
            # award_xp() uses get_db_session() internally (scoped_session = same
            # thread-local session), so calling it inside the outer session would
            # close the shared session mid-flight and silently discard our writes.
            xp_queue = []     # list of (user_id, username, last_launched_at)
            status_queue = [] # list of (user_id, username, access_token_enc, refresh_token_enc, expires_at, status_text)

            with get_db_session() as db:
                for sid in batch:
                    user_id = id_map[sid]
                    game_name, game_appid = now_playing.get(sid, (None, None))

                    u = db.query(WebUser).filter_by(id=user_id).first()
                    if not u:
                        continue

                    if u.current_game != game_name:
                        if game_name:
                            self.stdout.write(f'  {u.username}: now playing "{game_name}" (appid={game_appid})')
                            updated += 1
                            # Queue XP award (opt-in, 30-min cooldown) — run after session closes
                            if u.track_game_launches:
                                now_ts = int(time.time())
                                last = u.last_game_launched_at or 0
                                if now_ts - last >= GAME_LAUNCH_COOLDOWN:
                                    xp_queue.append((u.id, u.username, now_ts))
                                    u.last_game_launched_at = now_ts
                        else:
                            cleared += 1

                        u.current_game = game_name
                        u.current_game_appid = game_appid

                        # Queue Fluxer status update — run after session closes
                        if u.fluxer_sync_custom_status and u.fluxer_id and u.fluxer_access_token_enc:
                            status_text = f'Now Playing {game_name}' if game_name else None
                            status_queue.append((
                                u.id, u.username,
                                u.fluxer_access_token_enc, u.fluxer_refresh_token_enc,
                                u.fluxer_token_expires_at, status_text,
                            ))
                # Session commits and closes here — game state is now persisted

            # Award XP outside the session (award_xp opens its own session)
            from app.questlog_web.helpers import award_xp
            for uid, uname, launch_ts in xp_queue:
                try:
                    award_xp(uid, 'steam_game_launch', source='steam', ref_id=None)
                    self.stdout.write(f'    -> +2 XP game launch for {uname}')
                except Exception as xp_exc:
                    logger.warning(f'update_steam_now_playing: XP award failed for {uid}: {xp_exc}')

            # Sync Fluxer custom status outside the session
            for uid, uname, at_enc, rt_enc, exp_at, status_text in status_queue:
                try:
                    # Build a minimal token-holder so _get_fluxer_access_token can work
                    class _TokenHolder:
                        pass
                    th = _TokenHolder()
                    th.fluxer_access_token_enc  = at_enc
                    th.fluxer_refresh_token_enc = rt_enc
                    th.fluxer_token_expires_at  = exp_at
                    th.id = uid

                    from app.utils.encryption import decrypt_token
                    now_ts = int(time.time())
                    exp = exp_at or 0
                    if exp and now_ts >= exp - 300:
                        # Token near/past expiry — attempt refresh via a real DB session
                        with get_db_session() as db2:
                            real_u = db2.query(WebUser).filter_by(id=uid).first()
                            if real_u:
                                access_token = _get_fluxer_access_token(real_u, db2)
                            else:
                                access_token = None
                    else:
                        try:
                            access_token = decrypt_token(at_enc)
                        except Exception:
                            access_token = None

                    if access_token:
                        ok = _set_fluxer_custom_status(access_token, status_text, uid)
                        if ok:
                            action = f'set to "{status_text}"' if status_text else 'cleared'
                            self.stdout.write(f'    -> Fluxer status {action} for {uname}')
                    else:
                        logger.warning(f'update_steam_now_playing: no valid Fluxer token for user {uid}')
                except Exception as fe:
                    logger.warning(f'update_steam_now_playing: Fluxer status failed for {uid}: {fe}')

        self.stdout.write(f'Done. Updated: {updated}, Cleared: {cleared}')
