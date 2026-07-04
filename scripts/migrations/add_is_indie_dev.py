"""Add is_indie_dev column to web_users."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    try:
        conn.execute(text(
            "ALTER TABLE web_users ADD COLUMN is_indie_dev TINYINT(1) NOT NULL DEFAULT 0"
        ))
        conn.commit()
        print("Added is_indie_dev to web_users")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("Column already exists, skipping.")
        else:
            raise
