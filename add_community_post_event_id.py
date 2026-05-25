"""
Migration: add event_id to web_community_posts
Run: chwebsiteprj/bin/python3 add_community_post_event_id.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    try:
        conn.execute(sa_text(
            "ALTER TABLE web_community_posts "
            "ADD COLUMN event_id INT NULL DEFAULT NULL, "
            "ADD CONSTRAINT fk_cp_event FOREIGN KEY (event_id) "
            "REFERENCES web_community_events(id) ON DELETE SET NULL"
        ))
        conn.commit()
        print("Added event_id column.")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("Already exists, skipping.")
        else:
            raise

    try:
        conn.execute(sa_text(
            "ALTER TABLE web_community_posts "
            "ADD INDEX idx_cp_event_id (event_id)"
        ))
        conn.commit()
        print("Added index.")
    except Exception as e:
        if 'Duplicate key' in str(e):
            print("Index already exists.")
        else:
            raise

print("Done.")
