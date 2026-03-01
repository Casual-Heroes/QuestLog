"""
Migration: RSS Feed Schedule Settings
Adds fetch_interval column to web_rss_feeds.
Run once: python create_rss_feed_settings.py
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
    ("fetch_interval", "INT NOT NULL DEFAULT 15"),
]

with engine.connect() as conn:
    for col_name, col_def in cols_to_add:
        try:
            conn.execute(text(f"ALTER TABLE web_rss_feeds ADD COLUMN {col_name} {col_def}"))
            print(f"  + web_rss_feeds.{col_name}")
        except Exception as e:
            if 'Duplicate column' in str(e) or 'already exists' in str(e).lower():
                print(f"  ~ web_rss_feeds.{col_name} already exists, skipping")
            else:
                raise
    conn.execute(text("COMMIT"))

print("Done.")
