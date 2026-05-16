#!/usr/bin/env python3
"""Create web_user_games table."""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_user_games (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            web_user_id     INT NOT NULL,
            -- Game identity
            igdb_id         INT NULL,
            steam_app_id    INT NULL,
            name            VARCHAR(200) NOT NULL,
            cover_url       VARCHAR(500) NULL,
            -- Status: playing, played, backlog, play_together
            status          VARCHAR(20) NOT NULL DEFAULT 'playing',
            -- Optional metadata
            playtime_hours  FLOAT NULL,
            platform        VARCHAR(50) NULL,
            -- Timestamps
            added_at        BIGINT NOT NULL,
            updated_at      BIGINT NOT NULL,
            CONSTRAINT fk_ug_user FOREIGN KEY (web_user_id)
                REFERENCES web_users(id) ON DELETE CASCADE,
            INDEX idx_ug_user (web_user_id),
            INDEX idx_ug_status (status),
            INDEX idx_ug_steam (steam_app_id),
            INDEX idx_ug_igdb (igdb_id),
            UNIQUE KEY uq_ug_user_game (web_user_id, igdb_id, steam_app_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))
    conn.commit()
    print("Created web_user_games table.")
