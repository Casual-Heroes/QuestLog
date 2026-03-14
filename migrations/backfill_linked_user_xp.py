#!/usr/bin/env python3
"""
Backfill XP merge for existing linked users.

For every web_user that already has discord_id or fluxer_id set:
  - Discord: find their guild_members rows in opted-in guilds,
    take MAX(discord_xp, web_xp) as unified, write to web_unified_leaderboard,
    zero out guild_members for opted-in guilds.
  - Fluxer: find their fluxer_member_xp rows in opted-in guilds,
    take MAX(fluxer_xp, web_xp) as unified, write to web_unified_leaderboard,
    zero out fluxer_member_xp for opted-in guilds.

Handles users who linked before the on-link XP merge code existed.
Users in PURGE_USER_IDS are reset to XP=0/level=1/HP=0.

Run once:
  source /srv/ch-webserver/chwebsiteprj/bin/activate
  python3 backfill_linked_user_xp.py [--dry-run]
"""
import sys, os, argparse, time as _time
sys.path.insert(0, '/srv/ch-webserver')
os.environ['DJANGO_SETTINGS_MODULE'] = 'casualsite.settings'
import django; django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

PURGE_USER_IDS = {1}


def get_web_level(xp):
    level = 1
    while level < 99:
        if xp < int(7 * ((level + 1) ** 1.5)):
            break
        level += 1
    return level


def backfill_discord_user(conn, web_user_id, discord_id, web_xp, hero_points, dry_run):
    now = int(_time.time())

    guild_rows = conn.execute(text(
        "SELECT gm.guild_id, gm.xp, gm.hero_tokens, gm.message_count, "
        "       gm.voice_minutes, gm.reaction_count, gm.media_count, gm.last_active "
        "FROM guild_members gm "
        "JOIN web_communities wc ON wc.platform='discord' "
        "    AND CAST(wc.platform_id AS UNSIGNED) = gm.guild_id "
        "    AND wc.site_xp_to_guild=1 AND wc.network_status='approved' AND wc.is_active=1 "
        "WHERE gm.user_id = :did AND gm.xp > 0"
    ), {"did": int(discord_id)}).fetchall()

    if not guild_rows:
        return 0

    if web_user_id in PURGE_USER_IDS:
        new_web_xp = 0
        new_level = 1
        new_hp = 0
        print(f"    [PURGE] web_user={web_user_id} discord={discord_id} -> XP=0 level=1 HP=0")
    else:
        max_discord_xp = max(int(r[1] or 0) for r in guild_rows)
        new_web_xp = max(web_xp, max_discord_xp)
        new_level = get_web_level(new_web_xp)
        discord_hp = sum(int(r[2] or 0) for r in guild_rows)
        new_hp = hero_points + discord_hp if max_discord_xp > web_xp else hero_points
        print(f"    web_user={web_user_id} discord={discord_id} "
              f"discord_xp={max_discord_xp} web_xp={web_xp} -> unified_xp={new_web_xp} "
              f"level={new_level} hp={new_hp}")

    if not dry_run:
        conn.execute(text(
            "UPDATE web_users SET web_xp=:xp, web_level=:lvl, hero_points=:hp WHERE id=:uid"
        ), {"xp": new_web_xp, "lvl": new_level, "hp": new_hp, "uid": web_user_id})

        for r in guild_rows:
            guild_id_str = str(int(r[0]))
            msg, voice, react, media = int(r[3] or 0), int(r[4] or 0), int(r[5] or 0), int(r[6] or 0)
            la = int(r[7] or now)

            conn.execute(text("""
                INSERT INTO web_unified_leaderboard
                    (user_id, guild_id, platform, messages, voice_mins, reactions,
                     media_count, xp_total, last_active, updated_at)
                VALUES (:uid, :gid, 'discord', :msg, :voice, :react, :media, :xp, :la, :now)
                ON DUPLICATE KEY UPDATE
                    messages=:msg, voice_mins=:voice, reactions=:react,
                    media_count=:media, xp_total=:xp, last_active=:la, updated_at=:now
            """), {"uid": web_user_id, "gid": guild_id_str,
                   "msg": msg, "voice": voice, "react": react,
                   "media": media, "xp": new_web_xp, "la": la, "now": now})

            conn.execute(text(
                "UPDATE guild_members SET xp=0, level=1, hero_tokens=0 "
                "WHERE guild_id=:gid AND user_id=:did"
            ), {"gid": int(r[0]), "did": int(discord_id)})

        conn.commit()
    return 1


def backfill_fluxer_user(conn, web_user_id, fluxer_id, web_xp, dry_run):
    now = int(_time.time())

    guild_rows = conn.execute(text(
        "SELECT fx.guild_id, fx.xp, fx.message_count, fx.last_active "
        "FROM fluxer_member_xp fx "
        "JOIN web_communities wc ON wc.platform='fluxer' "
        "    AND wc.platform_id = CAST(fx.guild_id AS CHAR) COLLATE utf8mb4_unicode_ci "
        "    AND wc.site_xp_to_guild=1 AND wc.network_status='approved' AND wc.is_active=1 "
        "WHERE fx.user_id = :fid AND fx.xp > 0"
    ), {"fid": int(fluxer_id)}).fetchall()

    if not guild_rows:
        return 0

    if web_user_id in PURGE_USER_IDS:
        new_web_xp = 0
        new_level = 1
        print(f"    [PURGE] web_user={web_user_id} fluxer={fluxer_id} -> XP=0 level=1")
    else:
        max_fluxer_xp = max(int(r[1] or 0) for r in guild_rows)
        new_web_xp = max(web_xp, max_fluxer_xp)
        new_level = get_web_level(new_web_xp)
        print(f"    web_user={web_user_id} fluxer={fluxer_id} "
              f"fluxer_xp={max_fluxer_xp} web_xp={web_xp} -> unified_xp={new_web_xp} level={new_level}")

    if not dry_run:
        conn.execute(text(
            "UPDATE web_users SET web_xp=:xp, web_level=:lvl WHERE id=:uid"
        ), {"xp": new_web_xp, "lvl": new_level, "uid": web_user_id})

        for r in guild_rows:
            guild_id_str = str(int(r[0]))
            msg = int(r[2] or 0)
            la = int(r[3] or now)

            conn.execute(text("""
                INSERT INTO web_unified_leaderboard
                    (user_id, guild_id, platform, messages, voice_mins, reactions,
                     media_count, xp_total, last_active, updated_at)
                VALUES (:uid, :gid, 'fluxer', :msg, 0, 0, 0, :xp, :la, :now)
                ON DUPLICATE KEY UPDATE
                    messages=:msg, xp_total=:xp, last_active=:la, updated_at=:now
            """), {"uid": web_user_id, "gid": guild_id_str,
                   "msg": msg, "xp": new_web_xp, "la": la, "now": now})

            conn.execute(text(
                "UPDATE fluxer_member_xp SET xp=0, level=1 "
                "WHERE guild_id=:gid AND user_id=:fid"
            ), {"gid": int(r[0]), "fid": int(fluxer_id)})

        conn.commit()
    return 1


def main():
    parser = argparse.ArgumentParser(description='Backfill XP merge for existing linked users')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print("=" * 60)
    print("QuestLog XP Backfill - Existing Linked Users")
    print(f"PURGE user IDs: {PURGE_USER_IDS}")
    print("All others: unified to MAX(platform_xp, web_xp) - no inflation")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN - no changes.\n")

    with engine.connect() as conn:
        # All linked users
        users = conn.execute(text(
            "SELECT id, username, discord_id, fluxer_id, web_xp, hero_points "
            "FROM web_users WHERE (discord_id IS NOT NULL OR fluxer_id IS NOT NULL) "
            "AND is_banned=0 AND is_disabled=0"
        )).fetchall()

        print(f"Found {len(users)} linked user(s).\n")

        total_discord = 0
        total_fluxer = 0

        for u in users:
            web_user_id = u[0]
            username = u[1]
            discord_id = u[2]
            fluxer_id = u[3]
            web_xp = int(u[4] or 0)
            hero_points = int(u[5] or 0)

            print(f"User: {username} (id={web_user_id}, web_xp={web_xp})")

            if discord_id:
                n = backfill_discord_user(conn, web_user_id, discord_id, web_xp, hero_points, args.dry_run)
                total_discord += n
                if n == 0:
                    print(f"    [Discord] No opted-in guild XP found.")

            if fluxer_id:
                # Re-read web_xp after discord backfill (may have increased)
                if not args.dry_run and discord_id:
                    web_xp = conn.execute(text(
                        "SELECT web_xp FROM web_users WHERE id=:uid"
                    ), {"uid": web_user_id}).scalar() or 0
                n = backfill_fluxer_user(conn, web_user_id, fluxer_id, web_xp, args.dry_run)
                total_fluxer += n
                if n == 0:
                    print(f"    [Fluxer] No opted-in guild XP found.")

    print("\n" + "=" * 60)
    print(f"Discord users merged: {total_discord}")
    print(f"Fluxer users merged:  {total_fluxer}")
    if args.dry_run:
        print("\nRe-run without --dry-run to apply.")
    else:
        print("\nDone. Restart casualheroes, wardenbot, fluxerbot.")
    print("=" * 60)


if __name__ == '__main__':
    main()
