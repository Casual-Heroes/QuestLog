"""
Migration: Privacy & Notification Preferences
Adds 6 user preference columns to web_users.
Run once: python create_user_prefs_columns.py
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

cols_to_add = [
    # Privacy
    ("show_steam_profile",  "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("show_activity",       "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("allow_messages",      "BOOLEAN NOT NULL DEFAULT FALSE"),
    # Notifications
    ("notify_lfg_join",     "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("notify_lfg_full",     "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("notify_community_join", "BOOLEAN NOT NULL DEFAULT FALSE"),
]

with engine.connect() as conn:
    for col_name, col_def in cols_to_add:
        try:
            conn.execute(text(f"ALTER TABLE web_users ADD COLUMN {col_name} {col_def}"))
            print(f"  + web_users.{col_name}")
        except Exception as e:
            if 'Duplicate column' in str(e) or 'already exists' in str(e).lower():
                print(f"  ~ web_users.{col_name} already exists, skipping")
            else:
                raise
    conn.execute(text("COMMIT"))

print("Done.")
