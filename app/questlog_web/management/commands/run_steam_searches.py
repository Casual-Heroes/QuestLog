"""
Management command: run_steam_searches
Runs every minute via cron. Checks each active Steam search config and
executes it if its fetch_interval has elapsed since last run.

Cron setup (run as www-data or the app user):
    * * * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py run_steam_searches >> /srv/ch-webserver/logs/steam_search.log 2>&1
"""
import time
import logging

from django.core.management.base import BaseCommand

from app.db import get_db_session
from app.questlog_web.models import WebSteamSearchConfig
from app.questlog_web.steam_search import run_steam_search_config

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Run active Steam search configs that are due based on their fetch_interval.'

    def handle(self, *args, **options):
        now = int(time.time())

        with get_db_session() as db:
            configs = db.query(WebSteamSearchConfig).filter_by(enabled=True).all()

        due = []
        for cfg in configs:
            interval_seconds = (cfg.fetch_interval or 1440) * 60
            last = cfg.last_run_at or 0
            if now - last >= interval_seconds:
                due.append(cfg)

        if not due:
            self.stdout.write('No searches due.')
            return

        self.stdout.write(f'{len(due)} search(es) due.')

        for cfg in due:
            try:
                with get_db_session() as db:
                    c = db.query(WebSteamSearchConfig).filter_by(id=cfg.id).first()
                    if not c:
                        continue
                    new_count, updated_count, error = run_steam_search_config(c, db)
                if error:
                    self.stderr.write(f'  [{cfg.name}] ERROR: {error}')
                else:
                    self.stdout.write(f'  [{cfg.name}] +{new_count} new, {updated_count} updated')
            except Exception as e:
                logger.error(f'run_steam_searches: error on config {cfg.id} ({cfg.name}): {e}')
                self.stderr.write(f'  [{cfg.name}] EXCEPTION: {e}')

        self.stdout.write('Done.')
