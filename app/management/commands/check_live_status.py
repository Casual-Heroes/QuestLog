"""
Management command: check_live_status
Runs every 5 minutes (via cron). Checks Twitch/YouTube live status for all users
who have a twitch_username or youtube_channel_id set.

On offline -> live transition: updates DB and queues a go_live Fluxer notification.
On live -> offline transition: clears live columns.

Also refreshes Twitch follower counts and YouTube subscriber counts on creator profiles
once per run (rate-limited to avoid quota exhaustion).

Cron setup (run as www-data or app user):
    */5 * * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py check_live_status >> /srv/ch-webserver/logs/live_status.log 2>&1
"""
import os
import time
import logging
import requests

from django.core.management.base import BaseCommand

from app.db import get_db_session
from app.questlog_web.models import WebUser, WebCreatorProfile

logger = logging.getLogger(__name__)

TWITCH_CLIENT_ID     = os.getenv('TWITCH_CLIENT_ID', '')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET', '')

# Module-level token cache so multiple runs in the same process reuse it.
_twitch_app_token: dict = {}   # {'token': str, 'expires_at': int}


def _get_twitch_app_token() -> str | None:
    """Obtain (or return cached) a Twitch app-level access token via client credentials."""
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        return None

    now = int(time.time())
    cached = _twitch_app_token
    if cached.get('token') and cached.get('expires_at', 0) > now + 60:
        return cached['token']

    try:
        resp = requests.post(
            'https://id.twitch.tv/oauth2/token',
            data={
                'client_id':     TWITCH_CLIENT_ID,
                'client_secret': TWITCH_CLIENT_SECRET,
                'grant_type':    'client_credentials',
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)
        _twitch_app_token['token'] = token
        _twitch_app_token['expires_at'] = now + expires_in
        return token
    except Exception as e:
        logger.error(f'check_live_status: Twitch token fetch failed: {e}')
        return None


def _check_twitch_live(username: str) -> dict | None:
    """
    Return stream info dict if `username` is live on Twitch, else None.
    Uses app-level client credentials (no user OAuth required).
    """
    token = _get_twitch_app_token()
    if not token:
        return None
    try:
        resp = requests.get(
            'https://api.twitch.tv/helix/streams',
            params={'user_login': username},
            headers={
                'Authorization': f'Bearer {token}',
                'Client-Id':     TWITCH_CLIENT_ID,
            },
            timeout=10,
        )
        resp.raise_for_status()
        streams = resp.json().get('data', [])
        if not streams:
            return None
        s = streams[0]
        return {
            'title': (s.get('title') or '')[:255],
            'url':   f'https://www.twitch.tv/{username}',
        }
    except Exception as e:
        logger.warning(f'check_live_status: Twitch check failed for {username}: {e}')
        return None


def _check_youtube_live(channel_id: str, api_key: str) -> dict | None:
    """
    Return stream info dict if `channel_id` is live on YouTube, else None.
    Uses YouTube Data API v3 search (no user OAuth required).
    """
    if not api_key:
        return None
    try:
        search_resp = requests.get(
            'https://www.googleapis.com/youtube/v3/search',
            params={
                'part':      'snippet',
                'channelId': channel_id,
                'eventType': 'live',
                'type':      'video',
                'maxResults': 1,
                'key':       api_key,
            },
            timeout=10,
        )
        search_resp.raise_for_status()
        items = search_resp.json().get('items', [])
        if not items:
            return None
        snippet   = items[0].get('snippet', {})
        video_id  = items[0].get('id', {}).get('videoId', '')
        title     = (snippet.get('title') or '')[:255]
        url       = f'https://www.youtube.com/watch?v={video_id}' if video_id else f'https://www.youtube.com/channel/{channel_id}'
        return {'title': title, 'url': url}
    except Exception as e:
        logger.warning(f'check_live_status: YouTube check failed for {channel_id}: {e}')
        return None


KICK_CLIENT_ID = os.getenv('KICK_CLIENT_ID', '')
KICK_CLIENT_SECRET = os.getenv('KICK_CLIENT_SECRET', '')
_kick_app_token: dict = {}


def _get_kick_app_token() -> str | None:
    if not KICK_CLIENT_ID or not KICK_CLIENT_SECRET:
        return None
    now = int(time.time())
    if _kick_app_token.get('token') and _kick_app_token.get('expires_at', 0) > now + 60:
        return _kick_app_token['token']
    try:
        resp = requests.post(
            'https://id.kick.com/oauth/token',
            data={'client_id': KICK_CLIENT_ID, 'client_secret': KICK_CLIENT_SECRET, 'grant_type': 'client_credentials'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        _kick_app_token['token'] = data.get('access_token')
        _kick_app_token['expires_at'] = now + data.get('expires_in', 3600)
        return _kick_app_token['token']
    except Exception as e:
        logger.error(f'check_live_status: Kick token fetch failed: {e}')
        return None


def _check_kick_live(slug: str) -> dict | None:
    token = _get_kick_app_token()
    if not token:
        return None
    try:
        resp = requests.get(
            'https://api.kick.com/public/v1/channels',
            params={'slug': slug},
            headers={'Authorization': f'Bearer {token}', 'Client-Id': KICK_CLIENT_ID},
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get('data', [])
        if not items:
            return None
        ch = items[0]
        stream = ch.get('stream') or {}
        if not stream.get('is_live'):
            return None
        return {'title': (ch.get('stream_title') or '')[:255], 'url': f'https://kick.com/{slug}'}
    except Exception as e:
        logger.warning(f'check_live_status: Kick check failed for {slug}: {e}')
        return None


def _get_twitch_follower_count(twitch_user_id: str) -> int | None:
    """Return the follower count for a Twitch user ID, or None on failure."""
    token = _get_twitch_app_token()
    if not token or not twitch_user_id:
        return None
    try:
        resp = requests.get(
            'https://api.twitch.tv/helix/channels/followers',
            params={'broadcaster_id': twitch_user_id},
            headers={
                'Authorization': f'Bearer {token}',
                'Client-Id': TWITCH_CLIENT_ID,
            },
            timeout=10,
        )
        if resp.status_code == 401:
            # App token can't read followers for non-authed users - skip silently
            return None
        resp.raise_for_status()
        return resp.json().get('total', None)
    except Exception as e:
        logger.warning(f'check_live_status: Twitch follower count failed for {twitch_user_id}: {e}')
        return None


def _get_youtube_subscriber_count(channel_id: str, api_key: str) -> int | None:
    """Return the subscriber count for a YouTube channel ID, or None on failure."""
    if not api_key or not channel_id:
        return None
    try:
        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            params={
                'part': 'statistics',
                'id': channel_id,
                'key': api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get('items', [])
        if not items:
            return None
        stats = items[0].get('statistics', {})
        count = stats.get('subscriberCount')
        return int(count) if count is not None else None
    except Exception as e:
        logger.warning(f'check_live_status: YouTube sub count failed for {channel_id}: {e}')
        return None


class Command(BaseCommand):
    help = 'Check Twitch/YouTube live status for users and update is_live columns.'

    def handle(self, *args, **options):
        from django.conf import settings
        youtube_api_key = getattr(settings, 'YOUTUBE_API_KEY', '') or ''

        with get_db_session() as db:
            users = db.query(WebUser).filter(
                (WebUser.twitch_username.isnot(None)) | (WebUser.youtube_channel_id.isnot(None)),
                WebUser.is_banned == False,
                WebUser.is_disabled == False,
            ).all()

        self.stdout.write(f'Checking live status for {len(users)} user(s)...')
        went_live = 0
        went_offline = 0

        for user in users:
            try:
                stream_info = None
                platform    = None

                if user.twitch_username:
                    result = _check_twitch_live(user.twitch_username.strip())
                    if result:
                        stream_info = result
                        platform    = 'twitch'

                if stream_info is None and user.youtube_channel_id:
                    result = _check_youtube_live(user.youtube_channel_id.strip(), youtube_api_key)
                    if result:
                        stream_info = result
                        platform    = 'youtube'

                was_live = bool(user.is_live)
                now      = int(time.time())

                with get_db_session() as db:
                    u = db.query(WebUser).filter_by(id=user.id).first()
                    if not u:
                        continue

                    if stream_info:
                        u.is_live        = 1
                        u.live_platform  = platform
                        u.live_title     = stream_info['title']
                        u.live_url       = stream_info['url']
                        u.live_checked_at = now
                        db.commit()

                        if not was_live:
                            # offline -> live transition: queue Fluxer notification
                            went_live += 1
                            self.stdout.write(
                                f'  {u.username} went LIVE on {platform}: {stream_info["title"][:60]}'
                            )
                            try:
                                from app.questlog_web.fluxer_webhooks import notify_go_live
                                notify_go_live(
                                    username=u.username,
                                    platform=platform,
                                    title=stream_info['title'],
                                    stream_url=stream_info['url'],
                                    profile_url=f'https://casual-heroes.com/ql/u/{u.username}/',
                                )
                            except Exception as exc:
                                logger.warning(f'check_live_status: go_live notification failed for {u.username}: {exc}')
                    else:
                        if was_live:
                            went_offline += 1
                            self.stdout.write(f'  {u.username} went OFFLINE')
                        u.is_live         = 0
                        u.live_platform   = None
                        u.live_title      = None
                        u.live_url        = None
                        u.live_checked_at = now
                        db.commit()

            except Exception as e:
                logger.error(f'check_live_status: error processing user {user.id}: {e}')
                continue

            # Avoid hammering APIs
            time.sleep(0.3)

        self.stdout.write(
            f'Done. Went live: {went_live}, went offline: {went_offline}.'
        )

        # Refresh counts + Kick live status on creator profiles
        with get_db_session() as db:
            profiles = db.query(WebCreatorProfile).filter(
                (WebCreatorProfile.twitch_user_id.isnot(None)) |
                (WebCreatorProfile.youtube_channel_id.isnot(None)) |
                (WebCreatorProfile.kick_slug.isnot(None))
            ).all()

        updated = 0
        for profile in profiles:
            changed = False
            try:
                # Check Twitch/YouTube live status from creator profile
                # (covers users who connected via OAuth but have no WebUser.twitch_username)
                with get_db_session() as db_live:
                    u_live = db_live.query(WebUser).filter_by(id=profile.user_id).first()
                    if u_live and not u_live.twitch_username and not u_live.youtube_channel_id:
                        # User not covered by the WebUser live check above - check via profile
                        stream_info = None
                        platform = None
                        if profile.twitch_display_name:
                            result = _check_twitch_live(profile.twitch_display_name.strip().lower())
                            if result:
                                stream_info = result
                                platform = 'twitch'
                        if stream_info is None and profile.youtube_channel_id:
                            result = _check_youtube_live(profile.youtube_channel_id.strip(), youtube_api_key)
                            if result:
                                stream_info = result
                                platform = 'youtube'
                        was_live = bool(u_live.is_live)
                        now_ts = int(time.time())
                        if stream_info:
                            u_live.is_live = 1
                            u_live.live_platform = platform
                            u_live.live_title = stream_info['title']
                            u_live.live_url = stream_info['url']
                            u_live.live_checked_at = now_ts
                            db_live.commit()
                            if not was_live:
                                went_live += 1
                                self.stdout.write(f'  {u_live.username} went LIVE on {platform}: {stream_info["title"][:60]}')
                                try:
                                    from app.questlog_web.fluxer_webhooks import notify_go_live
                                    notify_go_live(
                                        username=u_live.username,
                                        platform=platform,
                                        title=stream_info['title'],
                                        stream_url=stream_info['url'],
                                        profile_url=f'https://casual-heroes.com/ql/u/{u_live.username}/',
                                    )
                                except Exception as exc:
                                    logger.warning(f'check_live_status: go_live notification failed for {u_live.username}: {exc}')
                        elif was_live and u_live.live_platform in ('twitch', 'youtube'):
                            u_live.is_live = 0
                            u_live.live_platform = None
                            u_live.live_title = None
                            u_live.live_url = None
                            u_live.live_checked_at = now_ts
                            db_live.commit()
                            went_offline += 1
                            self.stdout.write(f'  {u_live.username} went OFFLINE')
                time.sleep(0.2)

                if profile.twitch_user_id:
                    count = _get_twitch_follower_count(profile.twitch_user_id)
                    if count is not None:
                        profile.twitch_follower_count = count
                        changed = True
                    time.sleep(0.2)

                if profile.youtube_channel_id:
                    count = _get_youtube_subscriber_count(profile.youtube_channel_id, youtube_api_key)
                    if count is not None:
                        profile.youtube_subscriber_count = count
                        changed = True
                    time.sleep(0.2)

                if profile.kick_slug:
                    kick_info = _check_kick_live(profile.kick_slug.strip())
                    # Update kick_follower_count via channel data (already fetched above)
                    # Store live state on the linked WebUser if possible
                    with get_db_session() as db2:
                        p2 = db2.query(WebCreatorProfile).filter_by(id=profile.id).first()
                        if p2:
                            # Check if user is already marked live from Twitch/YouTube
                            u2 = db2.query(WebUser).filter_by(id=p2.user_id).first()
                            if u2 and not u2.is_live and kick_info:
                                u2.is_live = 1
                                u2.live_platform = 'kick'
                                u2.live_title = kick_info['title']
                                u2.live_url = kick_info['url']
                                u2.live_checked_at = int(time.time())
                                db2.commit()
                                self.stdout.write(f'  {u2.username} went LIVE on kick')
                            elif u2 and u2.is_live and u2.live_platform == 'kick' and not kick_info:
                                u2.is_live = 0
                                u2.live_platform = None
                                u2.live_title = None
                                u2.live_url = None
                                u2.live_checked_at = int(time.time())
                                db2.commit()
                    changed = True
                    time.sleep(0.2)

                if changed:
                    with get_db_session() as db:
                        p = db.query(WebCreatorProfile).filter_by(id=profile.id).first()
                        if p:
                            if profile.twitch_user_id:
                                p.twitch_follower_count = profile.twitch_follower_count
                            if profile.youtube_channel_id:
                                p.youtube_subscriber_count = profile.youtube_subscriber_count
                            p.twitch_last_synced = int(time.time())
                            db.commit()
                            updated += 1

            except Exception as e:
                logger.error(f'check_live_status: count refresh failed for profile {profile.id}: {e}')
                continue

        self.stdout.write(f'Refreshed counts for {updated} creator profile(s).')
