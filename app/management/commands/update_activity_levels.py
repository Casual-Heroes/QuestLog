"""
Management command: update_activity_levels

Computes an activity score for each approved community and updates
web_communities.activity_level.

Score = SUM across all members: messages + media*2 + floor(voice_minutes/10) + reactions
(pulled from guild_members for Discord, fluxer_member_xp for Fluxer)

Tiers:
  dormant   - score == 0         (no activity recorded)
  squire    - score 1-499        (just getting started)
  champion  - score 500-2999     (active community)
  legendary - score 3000-9999    (very active)
  mythic    - score 10000+       (elite activity)

Cron setup (daily at 3am):
    0 3 * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py update_activity_levels >> /srv/ch-webserver/logs/activity_levels.log 2>&1
"""
import time
from django.core.management.base import BaseCommand
from sqlalchemy import text
from app.db import get_db_session


def _score_to_level(score):
    if score == 0:
        return 'dormant'
    if score < 500:
        return 'squire'
    if score < 3000:
        return 'champion'
    if score < 10000:
        return 'legendary'
    return 'mythic'


def compute_and_update():
    updated = 0
    with get_db_session() as db:
        communities = db.execute(
            text(
                "SELECT id, platform, platform_id FROM web_communities "
                "WHERE network_status='approved' AND is_active=1 AND is_banned=0 "
                "AND platform_id IS NOT NULL"
            )
        ).fetchall()

        for row in communities:
            comm_id = row[0]
            platform = row[1]
            platform_id = row[2]
            score = 0

            try:
                if platform == 'discord':
                    agg = db.execute(
                        text(
                            "SELECT COALESCE(SUM(message_count),0), "
                            "COALESCE(SUM(media_count),0), "
                            "COALESCE(SUM(voice_minutes),0), "
                            "COALESCE(SUM(reaction_count),0) "
                            "FROM guild_members WHERE guild_id=:gid AND is_bot=0"
                        ),
                        {'gid': int(platform_id)},
                    ).fetchone()
                    if agg:
                        score = int(agg[0]) + int(agg[1]) * 2 + int(agg[2]) // 10 + int(agg[3])

                elif platform == 'fluxer':
                    agg = db.execute(
                        text(
                            "SELECT COALESCE(SUM(message_count),0), "
                            "COALESCE(SUM(media_count),0), "
                            "COALESCE(SUM(voice_minutes),0), "
                            "COALESCE(SUM(reaction_count),0) "
                            "FROM fluxer_member_xp WHERE guild_id=:gid"
                        ),
                        {'gid': platform_id},
                    ).fetchone()
                    if agg:
                        score = int(agg[0]) + int(agg[1]) * 2 + int(agg[2]) // 10 + int(agg[3])

                # Matrix: no per-member stats available yet, leave unchanged
                else:
                    continue

            except Exception:
                continue

            new_level = _score_to_level(score)
            db.execute(
                text(
                    "UPDATE web_communities SET activity_level=:lvl, updated_at=:ts "
                    "WHERE id=:cid"
                ),
                {'lvl': new_level, 'ts': int(time.time()), 'cid': comm_id},
            )
            updated += 1

        db.commit()

    return updated


class Command(BaseCommand):
    help = 'Update activity_level for all approved communities based on member activity data.'

    def handle(self, *args, **options):
        self.stdout.write('Updating community activity levels...')
        updated = compute_and_update()
        self.stdout.write(self.style.SUCCESS(f'Done - updated {updated} communities.'))
