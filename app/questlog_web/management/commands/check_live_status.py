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

import json
from sqlalchemy import text
from app.db import get_db_session
from app.questlog_web.models import WebUser, WebCreatorProfile, WebFluxerStreamerSub

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


def _get_latest_youtube_video(channel_id: str, api_key: str) -> dict | None:
    """
    Return the most recent public uploaded video for a YouTube channel using the API key.
    Returns dict with id, title, thumbnail_url, published_at (epoch int), or None on failure.
    """
    if not api_key or not channel_id:
        return None
    try:
        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/search',
            params={
                'part': 'snippet',
                'channelId': channel_id,
                'type': 'video',
                'order': 'date',
                'maxResults': 1,
                'key': api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        items = resp.json().get('items', [])
        if not items:
            return None
        item = items[0]
        snippet = item.get('snippet', {})
        video_id = item.get('id', {}).get('videoId', '')
        if not video_id:
            return None
        published_str = snippet.get('publishedAt', '')  # ISO 8601
        published_epoch = 0
        if published_str:
            from datetime import datetime, timezone as tz
            try:
                dt = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
                published_epoch = int(dt.timestamp())
            except Exception:
                pass
        thumbnail = (
            snippet.get('thumbnails', {}).get('high', {}).get('url') or
            snippet.get('thumbnails', {}).get('medium', {}).get('url') or
            snippet.get('thumbnails', {}).get('default', {}).get('url') or
            f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg'
        )
        return {
            'id': video_id,
            'title': (snippet.get('title') or '')[:300],
            'thumbnail_url': thumbnail,
            'published_at': published_epoch,
        }
    except Exception as e:
        logger.warning(f'check_live_status: latest YouTube video failed for {channel_id}: {e}')
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
                            # Snapshot the stream title + platform for the creator card
                            try:
                                profile = db.query(WebCreatorProfile).filter_by(user_id=u.id).first()
                                if profile and u.live_title:
                                    profile.latest_stream_title = u.live_title
                                    profile.latest_stream_platform = u.live_platform
                                    profile.latest_stream_ended_at = now
                            except Exception:
                                pass
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

        # Refresh follower/subscriber counts on creator profiles
        with get_db_session() as db:
            profiles = db.query(WebCreatorProfile).filter(
                (WebCreatorProfile.twitch_user_id.isnot(None)) |
                (WebCreatorProfile.youtube_channel_id.isnot(None))
            ).all()

        updated = 0
        for profile in profiles:
            changed = False
            try:
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
                    # Fetch latest video (runs every sync cycle - ~5 min)
                    video = _get_latest_youtube_video(profile.youtube_channel_id, youtube_api_key)
                    if video and video['id'] != profile.latest_youtube_video_id:
                        profile.latest_youtube_video_id = video['id']
                        profile.latest_youtube_video_title = video['title']
                        profile.latest_youtube_thumbnail_url = video['thumbnail_url']
                        profile.latest_youtube_video_published_at = video['published_at']
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
                                if profile.latest_youtube_video_id:
                                    p.latest_youtube_video_id = profile.latest_youtube_video_id
                                    p.latest_youtube_video_title = profile.latest_youtube_video_title
                                    p.latest_youtube_thumbnail_url = profile.latest_youtube_thumbnail_url
                                    p.latest_youtube_video_published_at = profile.latest_youtube_video_published_at
                            p.twitch_last_synced = int(time.time())
                            db.commit()
                            updated += 1

            except Exception as e:
                logger.error(f'check_live_status: count refresh failed for profile {profile.id}: {e}')
                continue

        self.stdout.write(f'Refreshed counts for {updated} creator profile(s).')

        # ---------------------------------------------------------------------------
        # Check subscribed streamers (guild live alert subscriptions)
        # ---------------------------------------------------------------------------
        with get_db_session() as db:
            subs = db.query(WebFluxerStreamerSub).filter_by(is_active=1).all()

        self.stdout.write(f'Checking {len(subs)} guild streamer subscription(s)...')
        sub_notified = 0
        sub_cleared = 0

        for sub in subs:
            try:
                stream_info = None
                if sub.streamer_platform == 'twitch':
                    stream_info = _check_twitch_live(sub.streamer_handle.strip())
                elif sub.streamer_platform == 'youtube':
                    stream_info = _check_youtube_live(sub.streamer_handle.strip(), youtube_api_key)

                was_live = bool(sub.is_currently_live)
                now = int(time.time())

                with get_db_session() as db:
                    s = db.query(WebFluxerStreamerSub).filter_by(id=sub.id).first()
                    if not s:
                        continue

                    if stream_info:
                        s.is_currently_live = 1
                        s.updated_at = now

                        if not was_live:
                            # offline -> live: fire guild notification
                            sub_notified += 1
                            display = s.streamer_display_name or s.streamer_handle
                            platform_label = 'Twitch' if s.streamer_platform == 'twitch' else 'YouTube'
                            icon = '\U0001f534' if s.streamer_platform == 'twitch' else '\U0001f4fa'
                            title = stream_info['title']
                            url = stream_info['url']
                            self.stdout.write(
                                f'  [{s.guild_id}] {display} went LIVE on {platform_label}: {title[:60]}'
                            )

                            # Build embed
                            embed_data = {
                                'title': f'{icon} {display} is live on {platform_label}!',
                                'description': (
                                    f'**{title}**\n\n'
                                    f'[Watch Stream]({url})'
                                ),
                                'url': url,
                                'color': 0xF43F5E,
                                'footer': 'QuestLog Live Alerts - casual-heroes.com/ql/',
                            }

                            # Prepend custom message if set
                            prefix = ''
                            if s.custom_message:
                                from app.questlog_web.fluxer_webhooks import _format_template
                                prefix = _format_template(
                                    s.custom_message,
                                    streamer=display,
                                    title=title,
                                    url=url,
                                )
                            payload = json.dumps({'content': prefix, 'embed': embed_data} if prefix else embed_data)

                            try:
                                db.execute(text("""
                                    INSERT INTO fluxer_pending_broadcasts
                                        (guild_id, channel_id, payload, created_at)
                                    VALUES (:guild_id, :channel_id, :payload, :now)
                                """), {
                                    'guild_id': int(s.guild_id) if s.guild_id.isdigit() else 0,
                                    'channel_id': int(s.notify_channel_id),
                                    'payload': payload,
                                    'now': now,
                                })
                                s.last_notified_at = now
                            except Exception as exc:
                                logger.warning(
                                    f'check_live_status: streamer sub broadcast failed for sub {s.id}: {exc}'
                                )

                        db.commit()

                    else:
                        if was_live:
                            sub_cleared += 1
                            self.stdout.write(
                                f'  [{s.guild_id}] {s.streamer_display_name or s.streamer_handle} went OFFLINE'
                            )
                        s.is_currently_live = 0
                        s.updated_at = now
                        db.commit()

            except Exception as e:
                logger.error(f'check_live_status: error processing streamer sub {sub.id}: {e}')
                continue

            time.sleep(0.3)

        self.stdout.write(
            f'Streamer subs done. Notified: {sub_notified}, cleared: {sub_cleared}.'
        )
