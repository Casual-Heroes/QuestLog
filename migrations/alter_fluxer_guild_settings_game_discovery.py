#!/usr/bin/env python3
"""
Migration: Add game discovery columns to web_fluxer_guild_settings
and create web_fluxer_announced_games table.

Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_fluxer_guild_settings_game_discovery.py
"""
import sys
import os
sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

ALTER_GUILD_SETTINGS = """
ALTER TABLE web_fluxer_guild_settings
    ADD COLUMN IF NOT EXISTS game_discovery_enabled TINYINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS game_discovery_channel_id VARCHAR(25) NULL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS game_discovery_ping_role_id VARCHAR(25) NULL DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS game_check_interval_hours INT NOT NULL DEFAULT 24,
    ADD COLUMN IF NOT EXISTS last_game_check_at BIGINT NULL DEFAULT NULL;
"""

CREATE_ANNOUNCED_GAMES = """
CREATE TABLE IF NOT EXISTS web_fluxer_announced_games (
    id                     INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    guild_id               VARCHAR(32) NOT NULL,
    igdb_id                INT NOT NULL,
    igdb_slug              VARCHAR(255),
    steam_id               INT,
    game_name              VARCHAR(255) NOT NULL,
    release_date           BIGINT,
    genres                 TEXT,
    platforms              TEXT,
    cover_url              VARCHAR(500),
    announced_at           BIGINT NOT NULL DEFAULT 0,
    announcement_message_id VARCHAR(32),
    INDEX idx_fluxer_announced_guild (guild_id),
    INDEX idx_fluxer_announced_igdb (guild_id, igdb_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with engine.connect() as conn:
    print("Adding game discovery columns to web_fluxer_guild_settings...")
    conn.execute(text(ALTER_GUILD_SETTINGS))
    print("Creating web_fluxer_announced_games table...")
    conn.execute(text(CREATE_ANNOUNCED_GAMES))
    conn.commit()
    print("Done.")
