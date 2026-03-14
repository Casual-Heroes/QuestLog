#!/usr/bin/env python3
# create_fluxer_webhook_tables.py - Create Fluxer webhook config table
# Run once: python3 app/questlog_web/scripts/create_fluxer_webhook_tables.py

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_fluxer_webhook_configs (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            event_type  VARCHAR(50) NOT NULL UNIQUE,
            label       VARCHAR(100) NOT NULL,
            webhook_url VARCHAR(1000) DEFAULT NULL,
            is_enabled  TINYINT(1) NOT NULL DEFAULT 0,
            created_at  BIGINT NOT NULL,
            updated_at  BIGINT NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))

    now = int(time.time())
    # Seed the default event types
    defaults = [
        ('new_post',        'New Post',         'A new post is created on QuestLog'),
        ('new_member',      'New Member',        'A new user registers on QuestLog'),
        ('giveaway_start',  'Giveaway Started',  'A giveaway is launched'),
        ('giveaway_winner', 'Giveaway Winner',   'A giveaway winner is picked'),
    ]
    for event_type, label, _ in defaults:
        conn.execute(text("""
            INSERT IGNORE INTO web_fluxer_webhook_configs
                (event_type, label, webhook_url, is_enabled, created_at, updated_at)
            VALUES (:et, :label, NULL, 0, :now, :now)
        """), {"et": event_type, "label": label, "now": now})

    conn.commit()
    print("web_fluxer_webhook_configs - OK")
    print("Default event types seeded: new_post, new_member, giveaway_start, giveaway_winner")
