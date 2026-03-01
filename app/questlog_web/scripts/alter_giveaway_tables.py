"""
Migration: Add multi-winner and HP ticket columns to giveaway tables
Run once: python app/questlog_web/scripts/alter_giveaway_tables.py
"""
import os
import sys
import django

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

with engine.connect() as conn:
    print("Altering web_giveaways...")
    conn.execute(text("""
        ALTER TABLE web_giveaways
        ADD COLUMN IF NOT EXISTS max_winners INT NOT NULL DEFAULT 1,
        ADD COLUMN IF NOT EXISTS max_entries_per_user INT NOT NULL DEFAULT 1,
        ADD COLUMN IF NOT EXISTS hp_per_extra_ticket INT NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS winners_json TEXT NULL
    """))

    print("Altering web_giveaway_entries...")
    conn.execute(text("""
        ALTER TABLE web_giveaway_entries
        ADD COLUMN IF NOT EXISTS ticket_count INT NOT NULL DEFAULT 1
    """))

    conn.commit()
    print("Done.")
