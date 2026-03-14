"""
Migration: Add sync_paused column to web_matrix_ban_lists
Run: chwebsiteprj/bin/python3 alter_matrix_ban_lists_add_sync_paused.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE web_matrix_ban_lists ADD COLUMN sync_paused TINYINT(1) NOT NULL DEFAULT 0"
    ))
    conn.commit()
    print("Done: added sync_paused column to web_matrix_ban_lists")
