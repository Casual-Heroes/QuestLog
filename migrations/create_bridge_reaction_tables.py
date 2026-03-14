#!/usr/bin/env python3
"""
Migration: add bridge message map and pending reactions tables.
Also adds source_message_id and reply_quote columns to web_bridge_relay_queue.

Run from project root:
    python create_bridge_reaction_tables.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_db_session
from sqlalchemy import text

ALTERS = [
    # Add columns to relay queue (IF NOT EXISTS pattern via IGNORE)
    """ALTER TABLE web_bridge_relay_queue
       ADD COLUMN IF NOT EXISTS source_message_id VARCHAR(25) DEFAULT NULL AFTER source_platform""",
    """ALTER TABLE web_bridge_relay_queue
       ADD COLUMN IF NOT EXISTS reply_quote VARCHAR(200) DEFAULT NULL AFTER content""",

    # Message map table
    """CREATE TABLE IF NOT EXISTS web_bridge_message_map (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        relay_queue_id  INT NOT NULL,
        platform        VARCHAR(10) NOT NULL,
        message_id      VARCHAR(25) NOT NULL,
        channel_id      VARCHAR(25) NOT NULL,
        created_at      BIGINT NOT NULL,
        INDEX idx_msg_map_lookup (platform, message_id),
        INDEX idx_msg_map_relay  (relay_queue_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",

    # Pending reactions table
    """CREATE TABLE IF NOT EXISTS web_bridge_pending_reactions (
        id                INT AUTO_INCREMENT PRIMARY KEY,
        source_platform   VARCHAR(10) NOT NULL,
        emoji             VARCHAR(100) NOT NULL,
        target_platform   VARCHAR(10) NOT NULL,
        target_message_id VARCHAR(25) NOT NULL,
        target_channel_id VARCHAR(25) NOT NULL,
        created_at        BIGINT NOT NULL,
        delivered_at      BIGINT DEFAULT NULL,
        INDEX idx_pending_react (target_platform, delivered_at, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
]

def run():
    with get_db_session() as db:
        for sql in ALTERS:
            try:
                db.execute(text(sql))
                db.commit()
                print(f"OK: {sql.strip().splitlines()[0][:80]}")
            except Exception as e:
                print(f"ERROR: {e}")
                db.rollback()

if __name__ == '__main__':
    run()
    print("Done.")
