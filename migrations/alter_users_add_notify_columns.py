#!/usr/bin/env python3
# alter_users_add_notify_columns.py
# Adds new notification preference columns + network_left_at to web_communities
# Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_users_add_notify_columns.py

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

MIGRATIONS = [
    # New notification prefs on web_users
    "ALTER TABLE web_users ADD COLUMN notify_shares TINYINT(1) NOT NULL DEFAULT 1",
    "ALTER TABLE web_users ADD COLUMN notify_mentions TINYINT(1) NOT NULL DEFAULT 1",
    "ALTER TABLE web_users ADD COLUMN notify_now_playing TINYINT(1) NOT NULL DEFAULT 1",
    "ALTER TABLE web_users ADD COLUMN notify_level_up TINYINT(1) NOT NULL DEFAULT 1",
    # network_left_at on web_communities (may already exist if alter_communities script ran)
    "ALTER TABLE web_communities ADD COLUMN network_left_at BIGINT NULL",
]

with engine.connect() as conn:
    for sql in MIGRATIONS:
        col = sql.split('ADD COLUMN')[1].strip().split()[0]
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"  Added column: {col}")
        except Exception as e:
            if '1060' in str(e):
                print(f"  Already exists, skipping: {col}")
            else:
                print(f"  ERROR on {col}: {e}")
                raise

print("Done.")
