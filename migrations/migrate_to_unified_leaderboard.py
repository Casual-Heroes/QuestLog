#!/usr/bin/env python3
"""
Migration: Import existing Discord (guild_members) and Fluxer (fluxer_member_xp)
stats into web_unified_leaderboard for opted-in guilds.

XP STRATEGY:
- User ID 1 (admin): full reset to XP=0, Level=1, HP=0 (explicit request)
- All other users: take MAX(discord_xp, fluxer_xp, web_xp) as unified XP.
  This preserves their current level without inflation from additive XP.
  Stats (messages, voice, reactions, media) copied as-is for leaderboard history.

- Only migrates guilds where web_communities.site_xp_to_guild = 1
- Matches users via web_users.discord_id and web_users.fluxer_id
- Zeroes out guild_members.xp/level/hero_tokens and fluxer_member_xp.xp/level
  for migrated users so bots start writing to unified tables going forward

Run once per guild after setting site_xp_to_guild=1:
  source /srv/ch-webserver/chwebsiteprj/bin/activate
  python3 migrate_to_unified_leaderboard.py [--dry-run] [--guild-id GUILD_ID]

Without --guild-id: migrates ALL opted-in guilds.
"""
import sys, os, argparse, time as _time
sys.path.insert(0, '/srv/ch-webserver')
os.environ['DJANGO_SETTINGS_MODULE'] = 'casualsite.settings'
import django; django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

# Users to fully reset to XP=0/level=1/HP=0 regardless of existing XP
PURGE_USER_IDS = {1}


def get_web_level(xp):
    """Same formula as site and bots."""
    level = 1
    while level < 99:
        if xp < int(7 * ((level + 1) ** 1.5)):
            break
        level += 1
    return level


def migrate_discord_guild(conn, community_id, guild_id, dry_run):
    """Migrate one Discord guild's guild_members into web_unified_leaderboard."""
    print(f"\n  [Discord] guild_id={guild_id}")

    rows = conn.execute(text(
        "SELECT gm.user_id, gm.xp, gm.level, gm.hero_tokens, "
        "gm.message_count, gm.voice_minutes, gm.reaction_count, gm.media_count, "
        "gm.last_active, wu.id as web_user_id, wu.web_xp, wu.hero_points "
        "FROM guild_members gm "
        "JOIN web_users wu ON wu.discord_id = CAST(gm.user_id AS CHAR) COLLATE utf8mb4_unicode_ci "
        "WHERE gm.guild_id = :gid AND gm.xp > 0"
    ), {"gid": int(guild_id)}).fetchall()

    if not rows:
        print("    No linked users with XP found.")
        return 0

    migrated = 0
    now = int(_time.time())

    for row in rows:
        discord_xp = int(row.xp or 0)
        discord_hp = int(row.hero_tokens or 0)
        old_web_xp = int(row.web_xp or 0)
        old_hp = int(row.hero_points or 0)
        web_user_id = row.web_user_id

        msg_count = int(row.message_count or 0) if hasattr(row, 'message_count') else 0
        voice_mins = int(row.voice_minutes or 0) if hasattr(row, 'voice_minutes') else 0
        reactions = int(row.reaction_count or 0) if hasattr(row, 'reaction_count') else 0
        media = int(row.media_count or 0) if hasattr(row, 'media_count') else 0
        last_active = int(row.last_active or now)

        if web_user_id in PURGE_USER_IDS:
            new_web_xp = 0
            new_level = 1
            new_hp = 0
            print(f"    [PURGE] user_id={web_user_id} discord_xp={discord_xp} -> XP=0 level=1 HP=0")
        else:
            # Take MAX to avoid double-counting (bots may have already dual-written)
            new_web_xp = max(old_web_xp, discord_xp)
            new_level = get_web_level(new_web_xp)
            # Only add discord HP if discord had more XP (wasn't already synced)
            new_hp = old_hp + discord_hp if old_web_xp < discord_xp else old_hp
            print(f"    user_id={web_user_id} discord_xp={discord_xp} web_xp={old_web_xp} "
                  f"-> unified_xp={new_web_xp} level={new_level} hp={new_hp}")

        if not dry_run:
            # Upsert stats into unified leaderboard
            conn.execute(text("""
                INSERT INTO web_unified_leaderboard
                    (user_id, guild_id, platform, messages, voice_mins, reactions,
                     media_count, xp_total, last_active, updated_at)
                VALUES
                    (:uid, :gid, 'discord', :msg, :voice, :react,
                     :media, :xp, :la, :now)
                ON DUPLICATE KEY UPDATE
                    messages    = :msg,
                    voice_mins  = :voice,
                    reactions   = :react,
                    media_count = :media,
                    xp_total    = :xp,
                    last_active = :la,
                    updated_at  = :now
            """), {
                "uid": web_user_id, "gid": str(guild_id),
                "msg": msg_count, "voice": voice_mins, "react": reactions,
                "media": media, "xp": new_web_xp, "la": last_active, "now": now,
            })

            # Update web_users unified totals
            conn.execute(text(
                "UPDATE web_users SET web_xp=:xp, web_level=:lvl, hero_points=:hp WHERE id=:uid"
            ), {"xp": new_web_xp, "lvl": new_level, "hp": new_hp, "uid": web_user_id})

            # Zero out guild_members so bot writes to unified going forward
            conn.execute(text(
                "UPDATE guild_members SET xp=0, level=1, hero_tokens=0 "
                "WHERE guild_id=:gid AND user_id=:uid"
            ), {"gid": int(guild_id), "uid": row.user_id})

        migrated += 1

    if not dry_run:
        conn.commit()

    print(f"    Migrated {migrated} Discord user(s).")
    return migrated


def migrate_fluxer_guild(conn, community_id, guild_id, dry_run):
    """Migrate one Fluxer guild's fluxer_member_xp into web_unified_leaderboard."""
    print(f"\n  [Fluxer] guild_id={guild_id}")

    rows = conn.execute(text(
        "SELECT fx.user_id, fx.xp, fx.level, fx.message_count, "
        "fx.last_active, wu.id as web_user_id, wu.web_xp, wu.hero_points "
        "FROM fluxer_member_xp fx "
        "JOIN web_users wu ON wu.fluxer_id = fx.user_id "
        "WHERE fx.guild_id = :gid AND fx.xp > 0"
    ), {"gid": guild_id}).fetchall()

    if not rows:
        print("    No linked users with XP found.")
        return 0

    migrated = 0
    now = int(_time.time())

    for row in rows:
        fluxer_xp = int(row.xp or 0)
        old_web_xp = int(row.web_xp or 0)
        old_hp = int(row.hero_points or 0)
        web_user_id = row.web_user_id

        msg_count = int(row.message_count or 0) if hasattr(row, 'message_count') else 0
        last_active = int(row.last_active or now)

        if web_user_id in PURGE_USER_IDS:
            new_web_xp = 0
            new_level = 1
            new_hp = 0
            print(f"    [PURGE] user_id={web_user_id} fluxer_xp={fluxer_xp} -> XP=0 level=1 HP=0")
        else:
            new_web_xp = max(old_web_xp, fluxer_xp)
            new_level = get_web_level(new_web_xp)
            new_hp = old_hp  # Fluxer doesn't track HP separately
            print(f"    user_id={web_user_id} fluxer_xp={fluxer_xp} web_xp={old_web_xp} "
                  f"-> unified_xp={new_web_xp} level={new_level}")

        if not dry_run:
            conn.execute(text("""
                INSERT INTO web_unified_leaderboard
                    (user_id, guild_id, platform, messages, voice_mins, reactions,
                     media_count, xp_total, last_active, updated_at)
                VALUES
                    (:uid, :gid, 'fluxer', :msg, 0, 0, 0, :xp, :la, :now)
                ON DUPLICATE KEY UPDATE
                    messages    = :msg,
                    xp_total    = :xp,
                    last_active = :la,
                    updated_at  = :now
            """), {
                "uid": web_user_id, "gid": str(guild_id),
                "msg": msg_count, "xp": new_web_xp, "la": last_active, "now": now,
            })

            # Update web_users unified totals
            conn.execute(text(
                "UPDATE web_users SET web_xp=:xp, web_level=:lvl, hero_points=:hp WHERE id=:uid"
            ), {"xp": new_web_xp, "lvl": new_level, "hp": new_hp, "uid": web_user_id})

            # Zero out fluxer_member_xp
            conn.execute(text(
                "UPDATE fluxer_member_xp SET xp=0, level=1 "
                "WHERE guild_id=:gid AND user_id=:uid"
            ), {"gid": guild_id, "uid": row.user_id})

        migrated += 1

    if not dry_run:
        conn.commit()

    print(f"    Migrated {migrated} Fluxer user(s).")
    return migrated


def main():
    parser = argparse.ArgumentParser(description='Migrate to unified leaderboard')
    parser.add_argument('--dry-run', action='store_true', help='Preview only, no DB writes')
    parser.add_argument('--guild-id', help='Migrate specific community ID (web_communities.id)')
    args = parser.parse_args()

    print("=" * 60)
    print("QuestLog Unified Leaderboard Migration")
    print(f"PURGE user IDs (reset to 0): {PURGE_USER_IDS}")
    print("All others: unified to MAX(discord, fluxer, site) XP")
    print("=" * 60)
    if args.dry_run:
        print("DRY RUN - no changes will be written.\n")

    with engine.connect() as conn:
        query = "SELECT id, name, platform, platform_id FROM web_communities WHERE site_xp_to_guild=1 AND network_status='approved' AND is_active=1"
        params = {}
        if args.guild_id:
            query += " AND id=:cid"
            params['cid'] = int(args.guild_id)

        communities = conn.execute(text(query), params).fetchall()

        if not communities:
            print("No opted-in approved communities found.")
            print("Set site_xp_to_guild=1 on a web_communities row first.")
            return

        print(f"Found {len(communities)} opted-in community/communities:\n")

        total_discord = 0
        total_fluxer = 0

        for c in communities:
            platform = c.platform if isinstance(c.platform, str) else c.platform
            print(f"Community: {c.name} (id={c.id}, platform={platform}, platform_id={c.platform_id})")

            if platform == 'discord':
                total_discord += migrate_discord_guild(conn, c.id, c.platform_id, args.dry_run)
            elif platform == 'fluxer':
                total_fluxer += migrate_fluxer_guild(conn, c.id, c.platform_id, args.dry_run)

    print("\n" + "=" * 60)
    print("Migration complete.")
    print(f"  Discord users migrated: {total_discord}")
    print(f"  Fluxer users migrated:  {total_fluxer}")
    if args.dry_run:
        print("\nRe-run without --dry-run to apply.")
    else:
        print("\nNEXT STEPS:")
        print("  1. Restart casualheroes, wardenbot, fluxerbot services")
        print("  2. Verify web_unified_leaderboard rows look correct")
        print("  3. Update bot XP writers to use web_unified_leaderboard")
    print("=" * 60)


if __name__ == '__main__':
    main()
