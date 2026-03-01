"""
Migration: Invite / Referral System
- Adds invite_code and referral_count columns to web_users
- Creates web_referrals table
Run once: python create_referral_tables.py
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
    # --- web_users: invite tracking columns ---
    cols_to_add = [
        ("invite_code",     "VARCHAR(16) NULL DEFAULT NULL"),
        ("referral_count",  "INT NOT NULL DEFAULT 0"),
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

    # Unique index on invite_code (sparse — only indexes non-NULL values in MySQL 8+)
    try:
        conn.execute(text("ALTER TABLE web_users ADD UNIQUE INDEX idx_web_users_invite_code (invite_code)"))
        print("  + index idx_web_users_invite_code")
    except Exception as e:
        if 'Duplicate key name' in str(e) or 'already exists' in str(e).lower():
            print("  ~ index idx_web_users_invite_code already exists, skipping")
        else:
            raise

    # --- web_referrals table ---
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_referrals (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            referrer_id     INT NOT NULL,
            invited_user_id INT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at      BIGINT NOT NULL,
            completed_at    BIGINT NULL,
            INDEX idx_referral_referrer (referrer_id),
            INDEX idx_referral_invited  (invited_user_id),
            FOREIGN KEY (referrer_id)     REFERENCES web_users(id) ON DELETE CASCADE,
            FOREIGN KEY (invited_user_id) REFERENCES web_users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print("  + table web_referrals")

    conn.execute(text("COMMIT"))

print("Done.")
