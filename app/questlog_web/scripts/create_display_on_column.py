#!/usr/bin/env python
"""
Migration: add display_on column to site_activity_games.
Run once: python create_display_on_column.py
"""
import os, sys
sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_engine
from sqlalchemy import text

def run():
    engine = get_engine()
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'site_activity_games' "
            "AND column_name = 'display_on'"
        ))
        if result.scalar() > 0:
            print("display_on column already exists — nothing to do.")
            return

        conn.execute(text(
            "ALTER TABLE site_activity_games "
            "ADD COLUMN display_on VARCHAR(20) NOT NULL DEFAULT 'gamesweplay' "
            "AFTER game_type"
        ))

        # Existing AMP-type games default to 'gameservers' so they don't
        # suddenly appear on /gamesweplay/ after the migration.
        conn.execute(text(
            "UPDATE site_activity_games "
            "SET display_on = 'gameservers' "
            "WHERE game_type IN ('amp', 'both')"
        ))

        conn.commit()
        print("Migration complete. AMP games defaulted to 'gameservers', Discord games to 'gamesweplay'.")

if __name__ == '__main__':
    run()
