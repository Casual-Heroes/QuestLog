#!/usr/bin/env python3
"""
Migration: create web_fluxer_guild_settings table for per-guild Fluxer bot dashboard settings.

Run from project root:
    python create_fluxer_guild_settings_table.py
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

SQL = """
CREATE TABLE IF NOT EXISTS web_fluxer_guild_settings (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    guild_id            VARCHAR(25) NOT NULL,
    guild_name          VARCHAR(100) DEFAULT NULL,

    -- XP & Leveling (implemented)
    xp_enabled          TINYINT(1) NOT NULL DEFAULT 1,
    xp_per_message      INT NOT NULL DEFAULT 2,
    xp_cooldown_secs    INT NOT NULL DEFAULT 60,
    xp_ignored_channels TEXT DEFAULT NULL,

    -- Moderation (implemented)
    mod_log_channel_id  VARCHAR(25) DEFAULT NULL,
    warn_threshold      INT NOT NULL DEFAULT 3,
    auto_ban_after_warns TINYINT(1) NOT NULL DEFAULT 0,

    -- LFG (implemented)
    lfg_channel_id      VARCHAR(25) DEFAULT NULL,

    -- Welcome Messages (bot update required)
    welcome_channel_id  VARCHAR(25) DEFAULT NULL,
    welcome_message     TEXT DEFAULT NULL,
    goodbye_channel_id  VARCHAR(25) DEFAULT NULL,
    goodbye_message     TEXT DEFAULT NULL,

    -- General
    bot_prefix          VARCHAR(10) NOT NULL DEFAULT '!',
    language            VARCHAR(10) NOT NULL DEFAULT 'en',
    timezone            VARCHAR(50) NOT NULL DEFAULT 'UTC',

    created_at          BIGINT NOT NULL,
    updated_at          BIGINT NOT NULL,

    UNIQUE KEY uq_guild_id (guild_id),
    INDEX idx_fgs_guild (guild_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def run():
    with get_db_session() as db:
        try:
            db.execute(text(SQL))
            db.commit()
            print("OK: CREATE TABLE web_fluxer_guild_settings")
        except Exception as e:
            print(f"ERROR: {e}")
            db.rollback()


if __name__ == '__main__':
    run()
    print("Done.")
