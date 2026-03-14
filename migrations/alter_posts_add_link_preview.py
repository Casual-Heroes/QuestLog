"""
Migration: add link_preview (TEXT, nullable) column to web_posts.
Run with: chwebsiteprj/bin/python3 alter_posts_add_link_preview.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_posts
        ADD COLUMN IF NOT EXISTS link_preview TEXT NULL DEFAULT NULL
    """))
    conn.commit()
    print("Done: added link_preview column to web_posts")
