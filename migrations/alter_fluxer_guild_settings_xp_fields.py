#!/usr/bin/env python3
"""
Migration: add xp_per_reaction and xp_per_voice_minute columns to web_fluxer_guild_settings.

Run once: python alter_fluxer_guild_settings_xp_fields.py
"""

import sys
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.questlog_web.helpers import get_db_session
from sqlalchemy import text


def run():
    with get_db_session() as db:
        # Check if columns already exist
        cols = db.execute(text(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'web_fluxer_guild_settings' "
            "AND COLUMN_NAME IN ('xp_per_reaction', 'xp_per_voice_minute')"
        )).fetchall()
        existing = {row[0] for row in cols}

        if 'xp_per_reaction' not in existing:
            db.execute(text(
                "ALTER TABLE web_fluxer_guild_settings "
                "ADD COLUMN xp_per_reaction INT NOT NULL DEFAULT 1 "
                "AFTER xp_per_message"
            ))
            print("Added xp_per_reaction column.")
        else:
            print("xp_per_reaction already exists - skipping.")

        if 'xp_per_voice_minute' not in existing:
            db.execute(text(
                "ALTER TABLE web_fluxer_guild_settings "
                "ADD COLUMN xp_per_voice_minute INT NOT NULL DEFAULT 1 "
                "AFTER xp_per_reaction"
            ))
            print("Added xp_per_voice_minute column.")
        else:
            print("xp_per_voice_minute already exists - skipping.")

        db.commit()
        print("Migration complete.")


if __name__ == '__main__':
    run()
