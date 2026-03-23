#!/usr/bin/env python3
"""
Migration: Create discord_pending_role_updates table.

Queues flair role sync operations for WardenBot (Discord bot) to process.
When a QuestLog user equips/unequips a flair, the web app inserts a row here.
WardenBot polls every 10s and applies the changes to opted-in Discord guilds.

Run: chwebsiteprj/bin/python3 migrations/create_discord_pending_role_updates_table.py
"""

import sys
import os

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_db_session
from sqlalchemy import text


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS discord_pending_role_updates (
    id            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    web_user_id   INT NOT NULL,
    action        VARCHAR(20) NOT NULL,
    flair_emoji   VARCHAR(20) NULL,
    flair_name    VARCHAR(100) NULL,
    created_at    BIGINT NOT NULL,
    processed_at  BIGINT NULL,
    INDEX idx_discord_role_update_pending (processed_at, created_at),
    INDEX idx_discord_role_update_user (web_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


def run():
    with get_db_session() as db:
        check = db.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'discord_pending_role_updates'"
        )).scalar()
        if check:
            print("  skip: table discord_pending_role_updates already exists")
        else:
            db.execute(text(CREATE_SQL))
            db.commit()
            print("  created: discord_pending_role_updates")
    print("Migration complete.")


if __name__ == '__main__':
    run()
