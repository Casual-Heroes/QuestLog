#!/usr/bin/env python3
"""
Migration: Add guild metadata fields to web_fluxer_guild_settings.

Brings web_fluxer_guild_settings to parity with WardenBot's guilds table:
- owner_id, guild_icon_hash, member_count, online_count
- cached_channels, cached_emojis, cached_members (JSON blobs)
- bot_present, left_at, joined_at (bot lifecycle tracking)
- is_vip, discovery_enabled, audit_logging_enabled, anti_raid_enabled,
  verification_enabled (feature/network flags)

Run once: python alter_fluxer_guild_settings_add_guild_fields.py
"""

import sys
import os

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_db_session
from sqlalchemy import text

MIGRATIONS = [
    # Guild metadata synced from bot
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN owner_id VARCHAR(25) NULL AFTER guild_name",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN guild_icon_hash VARCHAR(255) NULL",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN member_count INT NOT NULL DEFAULT 0",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN online_count INT NOT NULL DEFAULT 0",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN cached_channels MEDIUMTEXT NULL",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN cached_emojis TEXT NULL",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN cached_members MEDIUMTEXT NULL",
    # Bot lifecycle tracking
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN bot_present TINYINT NOT NULL DEFAULT 1",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN left_at BIGINT NULL",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN joined_at BIGINT NULL",
    # Network/admin flags
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN is_vip TINYINT NOT NULL DEFAULT 0",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN discovery_enabled TINYINT NOT NULL DEFAULT 0",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN audit_logging_enabled TINYINT NOT NULL DEFAULT 0",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN anti_raid_enabled TINYINT NOT NULL DEFAULT 0",
    "ALTER TABLE web_fluxer_guild_settings ADD COLUMN verification_enabled TINYINT NOT NULL DEFAULT 0",
]


def run():
    with get_db_session() as db:
        for stmt in MIGRATIONS:
            col = stmt.split('ADD COLUMN')[1].strip().split()[0]
            # Skip if column already exists
            check = db.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = DATABASE() "
                "AND table_name = 'web_fluxer_guild_settings' "
                "AND column_name = :col"
            ), {'col': col}).scalar()
            if check:
                print(f"  skip (exists): {col}")
                continue
            try:
                db.execute(text(stmt))
                db.commit()
                print(f"  added: {col}")
            except Exception as e:
                db.rollback()
                print(f"  ERROR on {col}: {e}")
                raise

    print("Migration complete.")


if __name__ == '__main__':
    run()
