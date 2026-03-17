"""
Management command: archive stale LFG groups.

Rules:
  - Non-recurring groups: close if scheduled_time + 2h has passed,
    OR if no join activity in 7 days (updated_at < now - 7d) AND status is 'open'
  - Recurring groups: never auto-archive
  - On archive: set status='closed', queue embed unpin to all stored channels

Run via cron every hour:
    chwebsiteprj/bin/python3 manage.py archive_stale_lfg

Or add to crontab:
    0 * * * * cd /srv/ch-webserver && chwebsiteprj/bin/python3 manage.py archive_stale_lfg >> /var/log/lfg_archive.log 2>&1
"""

import time
import logging

from django.core.management.base import BaseCommand
from sqlalchemy import text

from app.db import get_db_session
from app.questlog_web.fluxer_webhooks import queue_lfg_embed_edit_for_group

logger = logging.getLogger(__name__)

STALE_DAYS = 7
SCHEDULED_GRACE_SECONDS = 2 * 3600  # 2 hours after scheduled time


class Command(BaseCommand):
    help = 'Archive stale non-recurring LFG groups'

    def handle(self, *args, **options):
        now = int(time.time())
        stale_cutoff = now - (STALE_DAYS * 86400)

        archived = []

        with get_db_session() as db:
            # Non-recurring, still open/full
            rows = db.execute(text("""
                SELECT id, title, game_name, scheduled_time, updated_at, recurrence
                FROM web_lfg_groups
                WHERE status IN ('open', 'full')
                  AND (recurrence IS NULL OR recurrence = 'none')
            """)).fetchall()

            for row in rows:
                group_id, title, game_name, scheduled_time, updated_at, recurrence = row

                should_archive = False

                if scheduled_time and (scheduled_time + SCHEDULED_GRACE_SECONDS) < now:
                    # Scheduled event has ended
                    should_archive = True
                elif not scheduled_time and (updated_at or 0) < stale_cutoff:
                    # Flexible group with no activity in 7 days
                    should_archive = True

                if should_archive:
                    db.execute(text("""
                        UPDATE web_lfg_groups
                        SET status='closed', updated_at=:now
                        WHERE id=:gid AND status IN ('open', 'full')
                    """), {"now": now, "gid": group_id})
                    archived.append(group_id)
                    logger.info(f"[archive_stale_lfg] Archived group {group_id}: {title} ({game_name})")

            if archived:
                db.commit()

        # Queue embed edits (unpin) for each archived group
        for group_id in archived:
            try:
                queue_lfg_embed_edit_for_group(group_id, 'web', pin_state='unpin')
            except Exception as e:
                logger.warning(f"[archive_stale_lfg] Failed to queue unpin for group {group_id}: {e}")

        self.stdout.write(f"Archived {len(archived)} stale LFG groups.")
