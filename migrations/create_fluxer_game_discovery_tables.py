#!/usr/bin/env python3
"""
Migration: create web_fluxer_game_search_configs and web_fluxer_found_games tables.
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 create_fluxer_game_discovery_tables.py
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

CREATE_SEARCH_CONFIGS = """
CREATE TABLE IF NOT EXISTS web_fluxer_game_search_configs (
    id            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    guild_id      VARCHAR(32) NOT NULL,
    name          VARCHAR(100) NOT NULL,
    enabled       INT NOT NULL DEFAULT 1,
    genres        TEXT,
    themes        TEXT,
    keywords      TEXT,
    game_modes    TEXT,
    platforms     TEXT,
    min_hype      INT,
    min_rating    FLOAT,
    days_ahead    INT NOT NULL DEFAULT 30,
    show_on_website INT NOT NULL DEFAULT 1,
    created_at    BIGINT NOT NULL DEFAULT 0,
    updated_at    BIGINT NOT NULL DEFAULT 0,
    INDEX idx_fluxer_game_search_guild (guild_id),
    INDEX idx_fluxer_game_search_enabled (guild_id, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

CREATE_FOUND_GAMES = """
CREATE TABLE IF NOT EXISTS web_fluxer_found_games (
    id                 INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    guild_id           VARCHAR(32) NOT NULL,
    igdb_id            INT NOT NULL,
    igdb_slug          VARCHAR(255),
    game_name          VARCHAR(255) NOT NULL,
    release_date       BIGINT,
    summary            TEXT,
    genres             TEXT,
    themes             TEXT,
    keywords           TEXT,
    game_modes         TEXT,
    platforms_json     TEXT,
    cover_url          VARCHAR(500),
    igdb_url           VARCHAR(500),
    steam_url          VARCHAR(500),
    hypes              INT,
    rating             FLOAT,
    search_config_id   INT,
    search_config_name VARCHAR(100),
    found_at           BIGINT NOT NULL DEFAULT 0,
    check_id           VARCHAR(50),
    INDEX idx_fluxer_found_game_guild (guild_id),
    INDEX idx_fluxer_found_game_igdb (guild_id, igdb_id),
    INDEX idx_fluxer_found_game_search (guild_id, search_config_id),
    INDEX idx_fluxer_found_game_check (guild_id, check_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with engine.connect() as conn:
    print("Creating web_fluxer_game_search_configs...")
    conn.execute(text(CREATE_SEARCH_CONFIGS))
    print("Creating web_fluxer_found_games...")
    conn.execute(text(CREATE_FOUND_GAMES))
    conn.commit()
    print("Done.")
