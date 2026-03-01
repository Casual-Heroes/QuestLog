"""
Migration: Add granular notification preference columns to web_users
Run once: python app/questlog_web/scripts/alter_user_notify_prefs.py
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
    print("Altering web_users - adding notification preferences...")
    conn.execute(text("""
        ALTER TABLE web_users
        ADD COLUMN IF NOT EXISTS notify_follows BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS notify_likes BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS notify_comments BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS notify_comment_likes BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS notify_giveaways BOOLEAN NOT NULL DEFAULT TRUE,
        ADD COLUMN IF NOT EXISTS notify_lfg_leave BOOLEAN NOT NULL DEFAULT TRUE
    """))
    conn.commit()
    print("Done.")
