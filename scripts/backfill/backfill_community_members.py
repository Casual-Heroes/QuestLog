"""
Backfill web_community_members for all existing users who already have Discord or Fluxer linked.
Run once: chwebsiteprj/bin/python3 backfill_community_members.py
"""
import os, sys, django, time

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy.orm import Session
from sqlalchemy import text

engine = get_engine()
now = int(time.time())

with Session(engine) as db:
    # All users with a discord_id - find which Discord communities they're active in
    discord_users = db.execute(text(
        "SELECT id, discord_id FROM web_users WHERE discord_id IS NOT NULL AND is_banned=0 AND is_disabled=0"
    )).fetchall()

    discord_added = 0
    for u in discord_users:
        web_id, discord_id = u.id, u.discord_id
        try:
            community_ids = db.execute(text("""
                SELECT wc.id FROM web_communities wc
                JOIN guild_members gm
                  ON CAST(wc.platform_id AS UNSIGNED) = gm.guild_id
                  AND gm.user_id = :uid AND gm.left_at IS NULL
                WHERE wc.platform = 'discord' AND wc.is_active = 1
            """), {'uid': int(discord_id)}).fetchall()

            for (cid,) in community_ids:
                db.execute(text("""
                    INSERT IGNORE INTO web_community_members (user_id, community_id, role, joined_at)
                    VALUES (:uid, :cid, 'member', :now)
                """), {'uid': web_id, 'cid': cid, 'now': now})
                discord_added += 1
        except Exception as e:
            print(f"  Error for discord user {web_id} ({discord_id}): {e}")

    db.commit()
    print(f"Discord: processed {len(discord_users)} users, {discord_added} community memberships added")

    # All users with a fluxer_id
    fluxer_users = db.execute(text(
        "SELECT id, fluxer_id FROM web_users WHERE fluxer_id IS NOT NULL AND is_banned=0 AND is_disabled=0"
    )).fetchall()

    fluxer_added = 0
    for u in fluxer_users:
        web_id, fluxer_id = u.id, u.fluxer_id
        try:
            community_ids = db.execute(text("""
                SELECT wc.id FROM web_communities wc
                JOIN web_fluxer_members fm
                  ON CAST(wc.platform_id AS UNSIGNED) = fm.guild_id
                  AND fm.user_id = :uid AND fm.left_at IS NULL
                WHERE wc.platform = 'fluxer' AND wc.is_active = 1
            """), {'uid': int(fluxer_id)}).fetchall()

            for (cid,) in community_ids:
                db.execute(text("""
                    INSERT IGNORE INTO web_community_members (user_id, community_id, role, joined_at)
                    VALUES (:uid, :cid, 'member', :now)
                """), {'uid': web_id, 'cid': cid, 'now': now})
                fluxer_added += 1
        except Exception as e:
            print(f"  Error for fluxer user {web_id} ({fluxer_id}): {e}")

    db.commit()
    print(f"Fluxer: processed {len(fluxer_users)} users, {fluxer_added} community memberships added")

print("Done.")
