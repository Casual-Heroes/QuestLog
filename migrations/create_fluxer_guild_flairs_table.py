#!/usr/bin/env python3
"""
Migration: Create web_fluxer_guild_flairs table.

Run from project root:
    python create_fluxer_guild_flairs_table.py
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
CREATE TABLE IF NOT EXISTS web_fluxer_guild_flairs (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    guild_id     VARCHAR(32) NOT NULL,
    flair_id     INT NULL,
    flair_name   VARCHAR(100) NOT NULL,
    flair_type   VARCHAR(20) NOT NULL DEFAULT 'normal',
    emoji        VARCHAR(20) NOT NULL DEFAULT '',
    enabled      INT NOT NULL DEFAULT 1,
    hp_cost      INT NOT NULL DEFAULT 0,
    display_order INT NOT NULL DEFAULT 0,
    created_at   BIGINT NOT NULL,
    INDEX idx_fluxer_guild_flair_guild (guild_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def run():
    with get_db_session() as db:
        try:
            db.execute(text(SQL))
            db.commit()
            print("  OK: CREATE TABLE IF NOT EXISTS web_fluxer_guild_flairs")
        except Exception as e:
            print(f"  ERROR: {e}")
    print("Done.")


if __name__ == '__main__':
    run()
