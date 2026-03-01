#!/usr/bin/env python
"""
Migration: add show_playing_status and current_game columns to web_users.
Run once: python create_steam_now_playing.py
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
        # show_playing_status
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'web_users' "
            "AND column_name = 'show_playing_status'"
        ))
        if result.scalar() == 0:
            conn.execute(text(
                "ALTER TABLE web_users "
                "ADD COLUMN show_playing_status BOOLEAN NOT NULL DEFAULT FALSE "
                "AFTER steam_hours_total"
            ))
            print("Added show_playing_status column.")
        else:
            print("show_playing_status already exists — skipping.")

        # current_game
        result = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'web_users' "
            "AND column_name = 'current_game'"
        ))
        if result.scalar() == 0:
            conn.execute(text(
                "ALTER TABLE web_users "
                "ADD COLUMN current_game VARCHAR(255) NULL "
                "AFTER show_playing_status"
            ))
            print("Added current_game column.")
        else:
            print("current_game already exists — skipping.")

        conn.commit()
        print("Migration complete.")

if __name__ == '__main__':
    run()
