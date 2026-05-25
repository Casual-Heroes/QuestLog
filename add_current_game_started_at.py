"""
Migration: add current_game_started_at to web_users
Run once with: chwebsiteprj/bin/python3 add_current_game_started_at.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(sa_text("""
        ALTER TABLE web_users
        ADD COLUMN IF NOT EXISTS current_game_started_at BIGINT NULL
        COMMENT 'Unix epoch when current game session started - only updated on game change'
    """))
    conn.commit()
    print("Done: current_game_started_at added to web_users")
