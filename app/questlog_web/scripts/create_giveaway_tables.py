"""
Migration: Giveaway tables
Run once: python app/questlog_web/scripts/create_giveaway_tables.py
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
    print("Creating web_giveaways...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_giveaways (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            title           VARCHAR(200) NOT NULL,
            description     TEXT,
            prize           VARCHAR(500) NOT NULL,
            image_url       VARCHAR(500),
            status          VARCHAR(20) NOT NULL DEFAULT 'draft',
            ends_at         BIGINT,
            entry_count     INT NOT NULL DEFAULT 0,
            winner_user_id  INT,
            created_by_id   INT NOT NULL,
            created_at      BIGINT NOT NULL,
            updated_at      BIGINT NOT NULL,
            launched_at     BIGINT,
            closed_at       BIGINT,
            INDEX idx_giveaway_status (status),
            FOREIGN KEY (winner_user_id) REFERENCES web_users(id) ON DELETE SET NULL,
            FOREIGN KEY (created_by_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

    print("Creating web_giveaway_entries...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_giveaway_entries (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            giveaway_id INT NOT NULL,
            user_id     INT NOT NULL,
            entered_at  BIGINT NOT NULL,
            UNIQUE KEY uq_giveaway_entry (giveaway_id, user_id),
            INDEX idx_giveaway_entry_giveaway (giveaway_id),
            INDEX idx_giveaway_entry_user (user_id),
            FOREIGN KEY (giveaway_id) REFERENCES web_giveaways(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

print("Giveaway tables created successfully.")
