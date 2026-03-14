#!/usr/bin/env python3
# create_community_bot_config_table.py - Per-community bot subscription configs
# Run once: python3 app/questlog_web/scripts/create_community_bot_config_table.py

import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_community_bot_configs (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            community_id INT DEFAULT NULL,
            platform     VARCHAR(20) NOT NULL,
            guild_id     VARCHAR(100) NOT NULL,
            guild_name   VARCHAR(200) DEFAULT NULL,
            channel_id   VARCHAR(100) DEFAULT NULL,
            channel_name VARCHAR(200) DEFAULT NULL,
            webhook_url  VARCHAR(1000) DEFAULT NULL,
            event_type   VARCHAR(50) NOT NULL,
            is_enabled   TINYINT(1) NOT NULL DEFAULT 1,
            created_at   BIGINT NOT NULL,
            updated_at   BIGINT NOT NULL,
            UNIQUE KEY uq_bot_config (platform, guild_id, event_type),
            INDEX idx_bot_config_event (event_type, is_enabled),
            INDEX idx_bot_config_community (community_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("web_community_bot_configs - OK")
