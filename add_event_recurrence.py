"""
Migration: add recurrence + recurrence_parent_id to web_community_events
Run: chwebsiteprj/bin/python3 add_event_recurrence.py
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
            "ALTER TABLE web_community_events "
            "ADD COLUMN recurrence VARCHAR(20) NOT NULL DEFAULT 'none', "
            "ADD COLUMN recurrence_parent_id INT NULL DEFAULT NULL"
        ))
        conn.commit()
        print("Added recurrence columns.")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("Already exist, skipping.")
        else:
            raise

    try:
        conn.execute(sa_text(
            "ALTER TABLE web_community_events "
            "ADD INDEX idx_ce_recurrence_parent (recurrence_parent_id)"
        ))
        conn.commit()
        print("Added index.")
    except Exception as e:
        if 'Duplicate key' in str(e):
            print("Index already exists.")
        else:
            raise

print("Done.")
