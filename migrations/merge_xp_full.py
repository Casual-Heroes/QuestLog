"""
merge_xp_full.py - One-time XP merge: set each linked user's web_xp to the
MAX of their current site XP, best Discord guild XP, and best Fluxer guild XP.
Recomputes web_level from the merged value. No HP changes.

Run with:
    source /srv/ch-webserver/chwebsiteprj/bin/activate
    python3 /srv/ch-webserver/merge_xp_full.py
"""
import sys
import os

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_engine
from sqlalchemy import text
from sqlalchemy.orm import Session


def _get_web_level(xp: int) -> int:
    """Same formula used by the site and Fluxer bot."""
    level = 1
    while level < 99:
        if xp < int(7 * ((level + 1) ** 1.5)):
            break
        level += 1
    return level


def run():
    engine = get_engine()
    with Session(engine) as db:
        # Fetch all web users who have either discord_id or fluxer_id set
        users = db.execute(text(
            "SELECT id, username, discord_id, fluxer_id, web_xp, web_level "
            "FROM web_users "
            "WHERE discord_id IS NOT NULL OR fluxer_id IS NOT NULL"
        )).fetchall()

        print(f"Found {len(users)} linked users to process.")

        updated = 0
        skipped = 0

        for row in users:
            user_id     = row.id
            username    = row.username
            discord_id  = row.discord_id
            fluxer_id   = row.fluxer_id
            current_xp  = int(row.web_xp or 0)

            best_xp = current_xp

            # Best XP across all Discord guilds (guild_members table - WardenBot)
            if discord_id:
                try:
                    discord_row = db.execute(text(
                        "SELECT MAX(xp) as best FROM guild_members WHERE user_id = :uid"
                    ), {"uid": int(discord_id)}).fetchone()
                    if discord_row and discord_row.best:
                        discord_xp = int(discord_row.best)
                        if discord_xp > best_xp:
                            best_xp = discord_xp
                except Exception as e:
                    print(f"  [WARN] discord lookup failed for user {username} ({discord_id}): {e}")

            # Best XP across all Fluxer guilds (fluxer_member_xp table)
            if fluxer_id:
                try:
                    fluxer_row = db.execute(text(
                        "SELECT MAX(xp) as best FROM fluxer_member_xp WHERE user_id = :uid"
                    ), {"uid": int(fluxer_id)}).fetchone()
                    if fluxer_row and fluxer_row.best:
                        fluxer_xp = int(fluxer_row.best)
                        if fluxer_xp > best_xp:
                            best_xp = fluxer_xp
                except Exception as e:
                    print(f"  [WARN] fluxer lookup failed for user {username} ({fluxer_id}): {e}")

            if best_xp <= current_xp:
                skipped += 1
                continue

            new_level = _get_web_level(best_xp)
            db.execute(text(
                "UPDATE web_users SET web_xp = :xp, web_level = :lvl WHERE id = :uid"
            ), {"xp": best_xp, "lvl": new_level, "uid": user_id})

            print(f"  {username}: {current_xp} XP (level {row.web_level}) -> {best_xp} XP (level {new_level})")
            updated += 1

        db.commit()
        print(f"\nDone. Updated: {updated}, Skipped (no improvement): {skipped}")


if __name__ == '__main__':
    run()
