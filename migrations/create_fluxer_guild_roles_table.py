#!/usr/bin/env python3
"""
Migration: Create web_fluxer_guild_roles table.

Run from project root:
    python create_fluxer_guild_roles_table.py
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
CREATE TABLE IF NOT EXISTS web_fluxer_guild_roles (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    guild_id    VARCHAR(32) NOT NULL,
    role_id     VARCHAR(32) NOT NULL,
    role_name   VARCHAR(200) NOT NULL,
    role_color  INT NOT NULL DEFAULT 0,
    position    INT NOT NULL DEFAULT 0,
    is_managed  INT NOT NULL DEFAULT 0,
    synced_at   BIGINT NOT NULL,
    UNIQUE KEY uq_fluxer_guild_role (guild_id, role_id),
    INDEX idx_fluxer_role_guild (guild_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def run():
    with get_db_session() as db:
        try:
            db.execute(text(SQL))
            db.commit()
            print("  OK: CREATE TABLE IF NOT EXISTS web_fluxer_guild_roles")
        except Exception as e:
            print(f"  ERROR: {e}")
    print("Done.")


if __name__ == '__main__':
    run()
