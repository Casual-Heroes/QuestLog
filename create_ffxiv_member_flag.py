"""Migration: add is_ffxiv_member flag to web_users."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    try:
        conn.execute(sa_text(
            "ALTER TABLE web_users ADD COLUMN is_ffxiv_member TINYINT(1) NOT NULL DEFAULT 0 AFTER is_admin"
        ))
        conn.commit()
        print("Added is_ffxiv_member column to web_users")
    except Exception as e:
        if 'Duplicate column' in str(e) or '1060' in str(e):
            print("Column already exists - skipping")
        else:
            raise
