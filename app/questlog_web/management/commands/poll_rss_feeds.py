"""
Management command: poll_rss_feeds
Runs every minute via cron. Checks each active RSS feed and fetches
new articles if the feed's fetch_interval has elapsed since last fetch.

Cron setup (run as www-data or the app user):
    * * * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py poll_rss_feeds >> /srv/ch-webserver/logs/rss_poll.log 2>&1
"""
import time
import logging

from django.core.management.base import BaseCommand

from app.db import get_db_session
from app.questlog_web.models import WebRSSFeed
from app.questlog_web.helpers import fetch_rss_feed

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Poll active RSS feeds and store new articles based on each feed\'s fetch interval.'

    def handle(self, *args, **options):
        now = int(time.time())

        with get_db_session() as db:
            feeds = db.query(WebRSSFeed).filter_by(is_active=True).all()

        due = []
        for feed in feeds:
            interval_seconds = (feed.fetch_interval or 1440) * 60
            last = feed.last_fetched_at or 0
            if now - last >= interval_seconds:
                due.append(feed)

        if not due:
            self.stdout.write('No feeds due for fetching.')
            return

        self.stdout.write(f'{len(due)} feed(s) due.')

        for feed in due:
            try:
                with get_db_session() as db:
                    f = db.query(WebRSSFeed).filter_by(id=feed.id).first()
                    if not f:
                        continue
                    new_count, error = fetch_rss_feed(f, db)
                if error:
                    self.stderr.write(f'  [{feed.name}] ERROR: {error}')
                else:
                    self.stdout.write(f'  [{feed.name}] +{new_count} new article(s)')
            except Exception as e:
                logger.error(f'poll_rss_feeds: error on feed {feed.id} ({feed.name}): {e}')
                self.stderr.write(f'  [{feed.name}] EXCEPTION: {e}')

        self.stdout.write('Done.')
