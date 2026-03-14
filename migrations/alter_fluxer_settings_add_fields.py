#!/usr/bin/env python3
"""
Migration: Add missing fields to web_fluxer_guild_settings and create web_fluxer_level_roles.

Run from project root:
    python3 alter_fluxer_settings_add_fields.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_db_session
from sqlalchemy import text

ALTERS = [
    ("web_fluxer_guild_settings", "role_persistence_enabled",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN role_persistence_enabled TINYINT NOT NULL DEFAULT 0"),
    ("web_fluxer_guild_settings", "admin_roles",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN admin_roles TEXT NULL"),
    ("web_fluxer_guild_settings", "channel_notify_channel_id",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN channel_notify_channel_id VARCHAR(25) NULL"),
    ("web_fluxer_guild_settings", "temp_voice_category_ids",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN temp_voice_category_ids TEXT NULL"),
    # XP source toggles + gaming/media XP
    ("web_fluxer_guild_settings", "track_messages",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN track_messages TINYINT NOT NULL DEFAULT 1"),
    ("web_fluxer_guild_settings", "track_media",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN track_media TINYINT NOT NULL DEFAULT 1"),
    ("web_fluxer_guild_settings", "track_reactions",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN track_reactions TINYINT NOT NULL DEFAULT 1"),
    ("web_fluxer_guild_settings", "track_voice",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN track_voice TINYINT NOT NULL DEFAULT 1"),
    ("web_fluxer_guild_settings", "track_gaming",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN track_gaming TINYINT NOT NULL DEFAULT 0"),
    ("web_fluxer_guild_settings", "xp_per_media",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN xp_per_media INT NOT NULL DEFAULT 3"),
    ("web_fluxer_guild_settings", "xp_per_gaming_hour",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN xp_per_gaming_hour INT NOT NULL DEFAULT 10"),
    # token customization
    ("web_fluxer_guild_settings", "token_name",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN token_name VARCHAR(50) NOT NULL DEFAULT 'Hero Tokens'"),
    ("web_fluxer_guild_settings", "token_emoji",
     "ALTER TABLE web_fluxer_guild_settings ADD COLUMN token_emoji VARCHAR(20) NOT NULL DEFAULT ':coin:'"),
]

CREATE_LEVEL_ROLES = """
CREATE TABLE IF NOT EXISTS web_fluxer_level_roles (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    guild_id     VARCHAR(32) NOT NULL,
    level_required INT NOT NULL,
    role_id      VARCHAR(32) NOT NULL,
    role_name    VARCHAR(200) NOT NULL DEFAULT '',
    remove_previous TINYINT NOT NULL DEFAULT 0,
    created_at   BIGINT NOT NULL,
    UNIQUE KEY uq_fluxer_level_role (guild_id, level_required),
    INDEX idx_fluxer_lr_guild (guild_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def col_exists(db, table, col):
    row = db.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t AND COLUMN_NAME = :c"
    ), {'t': table, 'c': col}).scalar()
    return row > 0


def run():
    with get_db_session() as db:
        for table, col, sql in ALTERS:
            if col_exists(db, table, col):
                print(f"  SKIP: {table}.{col} already exists")
            else:
                try:
                    db.execute(text(sql))
                    db.commit()
                    print(f"  OK: added {table}.{col}")
                except Exception as e:
                    print(f"  ERROR {table}.{col}: {e}")

        try:
            db.execute(text(CREATE_LEVEL_ROLES))
            db.commit()
            print("  OK: CREATE TABLE IF NOT EXISTS web_fluxer_level_roles")
        except Exception as e:
            print(f"  ERROR web_fluxer_level_roles: {e}")

    print("Done.")


if __name__ == '__main__':
    run()
