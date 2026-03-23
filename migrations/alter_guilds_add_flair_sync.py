#!/usr/bin/env python3
"""
Migration: Add flair_sync_enabled to Discord guilds table.

Discord guild admins can opt in to automatic flair role sync via the
QuestLog Discord dashboard (Flair Management page). Defaults to 0 (disabled).

Run: chwebsiteprj/bin/python3 migrations/alter_guilds_add_flair_sync.py
"""

import sys
import os

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_db_session
from sqlalchemy import text


def run():
    with get_db_session() as db:
        check = db.execute(text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'guilds' "
            "AND column_name = 'flair_sync_enabled'"
        )).scalar()
        if check:
            print("  skip (exists): flair_sync_enabled")
        else:
            db.execute(text(
                "ALTER TABLE guilds "
                "ADD COLUMN flair_sync_enabled TINYINT(1) NOT NULL DEFAULT 0"
            ))
            db.commit()
            print("  added: flair_sync_enabled to guilds")
    print("Migration complete.")


if __name__ == '__main__':
    run()
