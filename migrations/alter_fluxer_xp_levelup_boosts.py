#!/usr/bin/env python3
"""
Migration: Add level-up message columns to web_fluxer_guild_settings
               and create web_fluxer_xp_boost_events table.

Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_fluxer_xp_levelup_boosts.py
"""
import os
import sys
sys.path.insert(0, '/srv/ch-webserver')
os.environ['DJANGO_SETTINGS_MODULE'] = 'casualsite.settings'

import django
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    # 1. Level-up message columns on web_fluxer_guild_settings
    for col_sql in [
        "ALTER TABLE web_fluxer_guild_settings ADD COLUMN level_up_enabled TINYINT NOT NULL DEFAULT 0",
        "ALTER TABLE web_fluxer_guild_settings ADD COLUMN level_up_channel_id VARCHAR(25) NULL DEFAULT NULL",
        "ALTER TABLE web_fluxer_guild_settings ADD COLUMN level_up_destination VARCHAR(20) NOT NULL DEFAULT 'current'",
        "ALTER TABLE web_fluxer_guild_settings ADD COLUMN level_up_message TEXT NULL DEFAULT NULL",
    ]:
        try:
            conn.execute(text(col_sql))
            print(f"OK: {col_sql[:80]}")
        except Exception as e:
            if 'Duplicate column' in str(e):
                print(f"SKIP (already exists): {col_sql[:80]}")
            else:
                print(f"ERROR: {e}")

    # 2. XP boost events table
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_fluxer_xp_boost_events (
            id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            guild_id    VARCHAR(32) NOT NULL,
            name        VARCHAR(100) NOT NULL,
            multiplier  INT NOT NULL DEFAULT 2,
            is_active   TINYINT NOT NULL DEFAULT 0,
            start_time  BIGINT NULL DEFAULT NULL,
            end_time    BIGINT NULL DEFAULT NULL,
            created_at  BIGINT NOT NULL,
            created_by  INT NULL DEFAULT NULL,
            INDEX idx_fluxer_boost_guild (guild_id),
            INDEX idx_fluxer_boost_active (guild_id, is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print("OK: web_fluxer_xp_boost_events table")

    conn.commit()

print("Migration complete.")
