"""Add is_eso_member column to web_users table."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_users
        ADD COLUMN is_eso_member TINYINT(1) NOT NULL DEFAULT 0
    """))
    conn.commit()
    print("Done - is_eso_member column added to web_users.")
