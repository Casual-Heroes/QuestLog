"""Migration: add is_favorite column to web_user_games."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(sa_text(
        "ALTER TABLE web_user_games ADD COLUMN IF NOT EXISTS is_favorite TINYINT(1) NOT NULL DEFAULT 0"
    ))
    conn.commit()
    print("Done: is_favorite column added to web_user_games.")
