"""
Management command: poll_steam_stats
Runs hourly (via cron). For each user who has opted in, fetches their
latest Steam achievement count and/or hours played, computes deltas,
and awards Hero Points accordingly.

Cron setup (run as www-data or the app user):
    0 * * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py poll_steam_stats >> /srv/ch-webserver/logs/steam_poll.log 2>&1
"""
import os
import time
import logging

from django.core.management.base import BaseCommand

from app.db import get_db_session
from app.questlog_web.models import WebUser
from app.questlog_web.steam_auth import get_steam_stats
from app.questlog_web.helpers import award_hero_points

logger = logging.getLogger(__name__)

STEAM_API_KEY = os.getenv('STEAM_API_KEY', '')


class Command(BaseCommand):
    help = 'Poll Steam API for opted-in users and award Hero Points for new achievements/hours.'

    def handle(self, *args, **options):
        if not STEAM_API_KEY:
            self.stderr.write('STEAM_API_KEY not set — aborting poll.')
            return

        with get_db_session() as db:
            users = db.query(WebUser).filter(
                WebUser.steam_id.isnot(None),
                (WebUser.track_achievements == True) | (WebUser.track_hours_played == True),
                WebUser.is_banned == False,
                WebUser.is_disabled == False,
            ).all()

        self.stdout.write(f'Polling Steam stats for {len(users)} user(s)...')
        total_hp = 0

        for user in users:
            try:
                stats = get_steam_stats(user.steam_id, STEAM_API_KEY)
                if not stats:
                    continue

                with get_db_session() as db:
                    u = db.query(WebUser).filter_by(id=user.id).first()
                    if not u:
                        continue

                    # --- Achievements ---
                    if u.track_achievements:
                        new_total = stats['achievements_total']
                        old_total = u.steam_achievements_total or 0
                        delta = max(0, new_total - old_total)
                        if delta > 0:
                            u.steam_achievements_total = new_total
                            db.commit()
                            for _ in range(delta):
                                pts = award_hero_points(u.id, 'steam_achievement', source='steam')
                                total_hp += pts
                            self.stdout.write(f'  {u.username}: +{delta} achievement(s), +{delta * 5} HP')

                    # --- Hours played ---
                    if u.track_hours_played:
                        new_minutes = stats['hours_total']
                        old_minutes = u.steam_hours_total or 0
                        # Award 1 HP per new hour (floor division of minutes)
                        new_hours = new_minutes // 60
                        old_hours = old_minutes // 60
                        delta_hours = max(0, new_hours - old_hours)
                        if delta_hours > 0:
                            u.steam_hours_total = new_minutes
                            db.commit()
                            pts = award_hero_points(u.id, 'steam_hours', source='steam',
                                                    ref_id=str(delta_hours))
                            total_hp += pts * delta_hours
                            self.stdout.write(f'  {u.username}: +{delta_hours}h played, +{delta_hours} HP')

            except Exception as e:
                logger.error(f'poll_steam_stats: error processing user {user.id}: {e}')
                continue

            # Rate limit — avoid hammering the Steam API
            time.sleep(0.5)

        self.stdout.write(f'Done. Total HP awarded this run: {total_hp}')
