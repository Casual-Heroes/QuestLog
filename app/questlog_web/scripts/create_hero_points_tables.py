"""
Migration: Hero Points + Steam Tracking
Creates web_hero_point_events table and adds Steam tracking + HP columns to web_users.
Run once: python create_hero_points_tables.py
"""
import os
import sys
import django

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

with engine.connect() as conn:
    # --- web_users: Steam tracking opt-ins ---
    cols_to_add = [
        ("track_achievements",      "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("track_hours_played",      "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("steam_achievements_total","INT NOT NULL DEFAULT 0"),
        ("steam_hours_total",       "INT NOT NULL DEFAULT 0"),
    ]
    for col_name, col_def in cols_to_add:
        try:
            conn.execute(text(f"ALTER TABLE web_users ADD COLUMN {col_name} {col_def}"))
            print(f"  + web_users.{col_name}")
        except Exception as e:
            if 'Duplicate column' in str(e) or 'already exists' in str(e).lower():
                print(f"  ~ web_users.{col_name} already exists, skipping")
            else:
                raise

    # --- web_hero_point_events table ---
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_hero_point_events (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id     INT NOT NULL,
            action_type VARCHAR(50) NOT NULL,
            points      INT NOT NULL,
            source      VARCHAR(20) NOT NULL DEFAULT 'web',
            ref_id      VARCHAR(100),
            created_at  BIGINT NOT NULL,
            INDEX idx_hp_user_action_date (user_id, action_type, created_at),
            FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print("  + web_hero_point_events table ready")

    conn.execute(text("COMMIT"))

print("\nMigration complete.")
