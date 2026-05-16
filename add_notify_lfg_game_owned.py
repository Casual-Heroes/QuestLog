"""Migration: add notify_lfg_game_owned column to web_users"""
import os, sys, django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_users
        ADD COLUMN IF NOT EXISTS notify_lfg_game_owned BOOLEAN NOT NULL DEFAULT TRUE
    """))
    conn.commit()
    print("Done.")
