"""Migration: add jobs_json column to web_ffxiv_characters."""
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
            "ALTER TABLE web_ffxiv_characters ADD COLUMN jobs_json TEXT NULL AFTER minions_json"
        ))
        conn.commit()
        print("Added jobs_json column to web_ffxiv_characters")
    except Exception as e:
        if 'Duplicate column' in str(e) or '1060' in str(e):
            print("Column already exists - skipping")
        else:
            raise
