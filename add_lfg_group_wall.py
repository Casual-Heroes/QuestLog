"""
Migration: add lfg_group_id to web_community_posts for LFG group discussion threads.
Run: chwebsiteprj/bin/python3 add_lfg_group_wall.py
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
            "ADD COLUMN lfg_group_id INT NULL DEFAULT NULL, "
            "ADD CONSTRAINT fk_cp_lfg_group FOREIGN KEY (lfg_group_id) "
            "REFERENCES web_lfg_groups(id) ON DELETE CASCADE"
        ))
        conn.commit()
        print("Added lfg_group_id column.")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("Already exists, skipping.")
        else:
            raise

    try:
        conn.execute(sa_text(
            "ALTER TABLE web_community_posts "
            "ADD INDEX idx_cp_lfg_group (lfg_group_id, is_deleted, created_at)"
        ))
        conn.commit()
        print("Added index.")
    except Exception as e:
        if 'Duplicate key' in str(e):
            print("Index already exists.")
        else:
            raise

print("Done.")
