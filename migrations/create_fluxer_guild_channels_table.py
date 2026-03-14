#!/usr/bin/env python3
# create_fluxer_guild_channels_table.py
# Run once: python3 create_fluxer_guild_channels_table.py

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_fluxer_guild_channels (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            guild_id     VARCHAR(32) NOT NULL,
            channel_id   VARCHAR(32) NOT NULL,
            channel_name VARCHAR(200) NOT NULL,
            channel_type INT NOT NULL DEFAULT 0,
            synced_at    BIGINT NOT NULL,
            UNIQUE KEY uq_fluxer_guild_channel (guild_id, channel_id),
            KEY idx_fluxer_guild_channels_guild (guild_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("web_fluxer_guild_channels - OK")
