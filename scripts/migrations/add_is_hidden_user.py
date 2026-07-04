"""Add is_hidden column to web_users."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_users
        ADD COLUMN IF NOT EXISTS is_hidden TINYINT(1) NOT NULL DEFAULT 0
    """))
    conn.commit()
    print("Added is_hidden to web_users")
