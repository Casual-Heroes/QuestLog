"""Migration: add show_on_discover_strip to site_activity_games."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE site_activity_games "
        "ADD COLUMN show_on_discover_strip BOOLEAN NOT NULL DEFAULT TRUE"
    ))
    conn.commit()
    print("Added show_on_discover_strip to site_activity_games")
