"""Migration: add is_founder column to web_users."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE web_users ADD COLUMN is_founder TINYINT(1) NOT NULL DEFAULT 0"))
        print("Added is_founder column.")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("is_founder already exists.")
        else:
            raise
print("Done.")
