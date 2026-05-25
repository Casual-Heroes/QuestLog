"""
Migration: add parent_id and reply_count to web_community_posts
Run: chwebsiteprj/bin/python3 add_wall_reply_columns.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()

with engine.connect() as conn:
    # Add parent_id (NULL = top-level, int = reply to that post)
    try:
        conn.execute(sa_text(
            "ALTER TABLE web_community_posts "
            "ADD COLUMN parent_id INT NULL DEFAULT NULL, "
            "ADD COLUMN reply_count INT NOT NULL DEFAULT 0"
        ))
        conn.commit()
        print("Added parent_id and reply_count columns.")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("Columns already exist, skipping.")
        else:
            raise

    # Index for fast reply lookups
    try:
        conn.execute(sa_text(
            "ALTER TABLE web_community_posts "
            "ADD INDEX idx_cp_parent (parent_id)"
        ))
        conn.commit()
        print("Added idx_cp_parent index.")
    except Exception as e:
        if 'Duplicate key name' in str(e):
            print("Index already exists, skipping.")
        else:
            raise

print("Done.")
