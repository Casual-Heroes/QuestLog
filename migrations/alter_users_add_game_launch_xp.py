"""
Migration: Add game launch XP opt-in columns to web_users.
Run: chwebsiteprj/bin/python3 alter_users_add_game_launch_xp.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    for sql in [
        "ALTER TABLE web_users ADD COLUMN IF NOT EXISTS track_game_launches TINYINT(1) NOT NULL DEFAULT 0",
        "ALTER TABLE web_users ADD COLUMN IF NOT EXISTS last_game_launched_at BIGINT DEFAULT NULL",
    ]:
        try:
            conn.execute(text(sql))
            print(f"OK: {sql[:80]}")
        except Exception as e:
            print(f"SKIP: {e}")
    conn.commit()
print("Done.")
