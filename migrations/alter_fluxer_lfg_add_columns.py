#!/usr/bin/env python3
"""
Migration: Add new columns to web_fluxer_lfg_games and create attendance tables.

Run from project root:
    python alter_fluxer_lfg_add_columns.py
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
    # Add new columns to web_fluxer_lfg_games
    ("ADD igdb_id TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS igdb_id VARCHAR(20) DEFAULT NULL"),
    ("ADD game_short TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS game_short VARCHAR(20) DEFAULT NULL"),
    ("ADD platforms TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS platforms TEXT DEFAULT NULL"),
    ("ADD channel_id TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS channel_id VARCHAR(32) DEFAULT NULL"),
    ("ADD notify_role_id TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS notify_role_id VARCHAR(32) DEFAULT NULL"),
    ("ADD auto_archive_hours TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS auto_archive_hours INT NOT NULL DEFAULT 24"),
    ("ADD require_rank TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS require_rank INT NOT NULL DEFAULT 0"),
    ("ADD rank_label TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS rank_label VARCHAR(50) DEFAULT NULL"),
    ("ADD rank_min TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS rank_min INT DEFAULT NULL"),
    ("ADD rank_max TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS rank_max INT DEFAULT NULL"),
    ("ADD is_custom_game TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS is_custom_game INT NOT NULL DEFAULT 0"),
    ("ADD enabled TO web_fluxer_lfg_games",
     "ALTER TABLE web_fluxer_lfg_games ADD COLUMN IF NOT EXISTS enabled INT NOT NULL DEFAULT 1"),
]

NEW_TABLES = [
    (
        'web_fluxer_lfg_attendance',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_lfg_attendance (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            guild_id        VARCHAR(32) NOT NULL,
            group_id        INT NOT NULL,
            fluxer_user_id  VARCHAR(32) DEFAULT NULL,
            web_user_id     INT DEFAULT NULL,
            display_name    VARCHAR(100) DEFAULT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending',
            selections_json TEXT DEFAULT NULL,
            created_at      BIGINT NOT NULL DEFAULT 0,
            updated_at      BIGINT NOT NULL DEFAULT 0,
            INDEX idx_fluxer_attend_group (group_id),
            INDEX idx_fluxer_attend_user (guild_id, fluxer_user_id),
            INDEX idx_fluxer_attend_guild_status (guild_id, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_lfg_member_stats',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_lfg_member_stats (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            guild_id            VARCHAR(32) NOT NULL,
            fluxer_user_id      VARCHAR(32) NOT NULL,
            web_user_id         INT DEFAULT NULL,
            display_name        VARCHAR(100) DEFAULT NULL,
            total_signups       INT NOT NULL DEFAULT 0,
            showed_count        INT NOT NULL DEFAULT 0,
            no_show_count       INT NOT NULL DEFAULT 0,
            late_count          INT NOT NULL DEFAULT 0,
            cancelled_count     INT NOT NULL DEFAULT 0,
            pardoned_count      INT NOT NULL DEFAULT 0,
            reliability_score   INT NOT NULL DEFAULT 100,
            is_blacklisted      INT NOT NULL DEFAULT 0,
            blacklist_reason    TEXT DEFAULT NULL,
            blacklisted_at      BIGINT DEFAULT NULL,
            global_pardon_at    BIGINT DEFAULT NULL,
            updated_at          BIGINT NOT NULL DEFAULT 0,
            UNIQUE KEY idx_fluxer_lfg_stats_guild_user (guild_id, fluxer_user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_lfg_config',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_lfg_config (
            id                      INT AUTO_INCREMENT PRIMARY KEY,
            guild_id                VARCHAR(32) NOT NULL UNIQUE,
            attendance_enabled      INT NOT NULL DEFAULT 0,
            require_confirmation    INT NOT NULL DEFAULT 0,
            auto_noshow_hours       INT NOT NULL DEFAULT 1,
            warn_at_reliability     INT NOT NULL DEFAULT 50,
            min_required_score      INT NOT NULL DEFAULT 0,
            auto_blacklist_noshow   INT NOT NULL DEFAULT 0,
            updated_at              BIGINT NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
]


def run():
    with get_db_session() as db:
        print("Adding columns to web_fluxer_lfg_games...")
        for label, sql in ALTERS:
            try:
                db.execute(text(sql))
                db.commit()
                print(f"  OK: {label}")
            except Exception as e:
                if 'Duplicate column' in str(e) or '1060' in str(e):
                    print(f"  SKIP (already exists): {label}")
                else:
                    print(f"  ERROR: {label}: {e}")

        print("\nCreating new tables...")
        for table_name, sql in NEW_TABLES:
            try:
                db.execute(text(sql))
                db.commit()
                print(f"  OK: CREATE TABLE IF NOT EXISTS {table_name}")
            except Exception as e:
                print(f"  ERROR: {table_name}: {e}")

    print("\nDone.")


if __name__ == '__main__':
    run()
