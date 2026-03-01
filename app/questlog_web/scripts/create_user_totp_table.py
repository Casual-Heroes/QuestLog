"""
Migration: TOTP 2FA Table
- Creates web_user_totp table for per-user TOTP secrets and backup codes

Run once: python create_user_totp_table.py
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
    print("Creating web_user_totp table...")
    try:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS web_user_totp (
                id          INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id     INT NOT NULL,
                secret_enc  TEXT NOT NULL,
                is_enabled  TINYINT(1) NOT NULL DEFAULT 0,
                backup_codes TEXT NOT NULL DEFAULT '[]',
                created_at  BIGINT NOT NULL,
                enabled_at  BIGINT NULL,
                UNIQUE KEY uq_user_totp (user_id),
                CONSTRAINT fk_totp_user
                    FOREIGN KEY (user_id) REFERENCES web_users(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        conn.commit()
        print("  Done.")
    except Exception as e:
        if 'already exists' in str(e).lower():
            print("  Table already exists, skipping.")
        else:
            raise

print("\nMigration complete.")
