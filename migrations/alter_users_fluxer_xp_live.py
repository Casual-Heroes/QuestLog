#!/usr/bin/env python3
# alter_users_fluxer_xp_live.py
# Run once: chwebsiteprj/bin/python3 alter_users_fluxer_xp_live.py
# Adds: fluxer_xp_migrated, is_live, live_platform, live_title, live_url, live_checked_at to web_users
# Creates: fluxer_pending_role_updates table

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    # --- web_users new columns ---
    user_alters = [
        ("fluxer_xp_migrated", "ALTER TABLE web_users ADD COLUMN fluxer_xp_migrated TINYINT(1) NOT NULL DEFAULT 0 AFTER active_flair_id"),
        ("is_live",            "ALTER TABLE web_users ADD COLUMN is_live TINYINT(1) NOT NULL DEFAULT 0 AFTER fluxer_xp_migrated"),
        ("live_platform",      "ALTER TABLE web_users ADD COLUMN live_platform VARCHAR(20) DEFAULT NULL AFTER is_live"),
        ("live_title",         "ALTER TABLE web_users ADD COLUMN live_title VARCHAR(255) DEFAULT NULL AFTER live_platform"),
        ("live_url",           "ALTER TABLE web_users ADD COLUMN live_url VARCHAR(500) DEFAULT NULL AFTER live_title"),
        ("live_checked_at",    "ALTER TABLE web_users ADD COLUMN live_checked_at BIGINT DEFAULT NULL AFTER live_url"),
    ]
    for col, sql in user_alters:
        try:
            conn.execute(text(sql))
            print(f"  + web_users: added {col}")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print(f"  - web_users: {col} already exists")
            else:
                raise

    # --- fluxer_pending_role_updates table ---
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS fluxer_pending_role_updates (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            web_user_id  INT NOT NULL,
            action       VARCHAR(20) NOT NULL,
            flair_emoji  VARCHAR(20) DEFAULT NULL,
            flair_name   VARCHAR(100) DEFAULT NULL,
            created_at   BIGINT NOT NULL,
            processed_at BIGINT DEFAULT NULL,
            INDEX idx_role_update_pending (processed_at, created_at),
            INDEX idx_role_update_user (web_user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print("  + fluxer_pending_role_updates - OK")

    conn.commit()
    print("Migration complete.")
