#!/usr/bin/env python3
"""
Migration: Add Hero subscription columns to web_users,
           create web_subscription_events table,
           add 'hero' to web_flairs.flair_type enum,
           create web_bridge_configs and web_bridge_relay_queue tables.

Run from project root:
    python alter_users_hero_subscription.py
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from sqlalchemy import text
from app.db import get_db_session

MIGRATIONS = [
    # Hero subscription columns on web_users
    """
    ALTER TABLE web_users
        ADD COLUMN IF NOT EXISTS is_hero TINYINT(1) NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS hero_expires_at BIGINT DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(64) DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(64) DEFAULT NULL
    """,

    # Index on stripe_customer_id for webhook lookups
    """
    ALTER TABLE web_users
        ADD INDEX IF NOT EXISTS idx_web_users_stripe_customer (stripe_customer_id)
    """,

    # Add 'hero' to web_flairs.flair_type enum
    """
    ALTER TABLE web_flairs
        MODIFY COLUMN flair_type ENUM('normal', 'seasonal', 'exclusive', 'hero') NOT NULL DEFAULT 'normal'
    """,

    # Subscription event audit log
    """
    CREATE TABLE IF NOT EXISTS web_subscription_events (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        user_id         INT NOT NULL,
        event_type      VARCHAR(32) NOT NULL,
        stripe_event_id VARCHAR(64) DEFAULT NULL,
        amount_cents    INT DEFAULT NULL,
        created_at      BIGINT NOT NULL,
        UNIQUE KEY uq_stripe_event (stripe_event_id),
        INDEX idx_sub_event_user (user_id),
        CONSTRAINT fk_sub_event_user FOREIGN KEY (user_id) REFERENCES web_users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # Bridge: config table linking Discord <-> Fluxer channels
    """
    CREATE TABLE IF NOT EXISTS web_bridge_configs (
        id                       INT AUTO_INCREMENT PRIMARY KEY,
        discord_guild_id         VARCHAR(20) NOT NULL,
        discord_channel_id       VARCHAR(20) NOT NULL,
        fluxer_guild_id          VARCHAR(20) NOT NULL,
        fluxer_channel_id        VARCHAR(20) NOT NULL,
        relay_discord_to_fluxer  TINYINT(1) NOT NULL DEFAULT 1,
        relay_fluxer_to_discord  TINYINT(1) NOT NULL DEFAULT 1,
        max_msg_len              INT NOT NULL DEFAULT 500,
        enabled                  TINYINT(1) NOT NULL DEFAULT 1,
        created_at               BIGINT NOT NULL,
        INDEX idx_bridge_discord_ch (discord_channel_id),
        INDEX idx_bridge_fluxer_ch  (fluxer_channel_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # Bridge: relay queue (messages waiting to be delivered)
    """
    CREATE TABLE IF NOT EXISTS web_bridge_relay_queue (
        id                INT AUTO_INCREMENT PRIMARY KEY,
        bridge_id         INT NOT NULL,
        source_platform   VARCHAR(10) NOT NULL,
        author_name       VARCHAR(80) NOT NULL,
        author_avatar     VARCHAR(300) DEFAULT NULL,
        content           TEXT NOT NULL,
        target_platform   VARCHAR(10) NOT NULL,
        target_channel_id VARCHAR(20) NOT NULL,
        created_at        BIGINT NOT NULL,
        delivered_at      BIGINT DEFAULT NULL,
        INDEX idx_relay_pending (target_platform, delivered_at, created_at),
        INDEX idx_relay_bridge  (bridge_id),
        CONSTRAINT fk_relay_bridge FOREIGN KEY (bridge_id) REFERENCES web_bridge_configs(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def run():
    print("Running Hero subscription + bridge migration...")
    with get_db_session() as db:
        for sql in MIGRATIONS:
            stmt = sql.strip()
            if not stmt:
                continue
            label = stmt.split('\n')[0][:80].strip()
            try:
                db.execute(text(stmt))
                db.commit()
                print(f"  OK: {label}")
            except Exception as e:
                db.rollback()
                # Already-exists errors are fine for ADD COLUMN IF NOT EXISTS
                if 'Duplicate' in str(e) or 'already exists' in str(e).lower():
                    print(f"  SKIP (already exists): {label}")
                else:
                    print(f"  ERROR: {label}\n    {e}")
                    raise
    print("Migration complete.")


if __name__ == '__main__':
    run()
