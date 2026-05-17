#!/usr/bin/env python3
"""Create web_ticker_events table for game library play_together events."""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_ticker_events (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            user_id      INT NOT NULL,
            event_type   VARCHAR(30) NOT NULL DEFAULT 'game_added',
            game_name    VARCHAR(200) NOT NULL,
            steam_app_id INT NULL,
            created_at   BIGINT NOT NULL,
            INDEX idx_te_user (user_id),
            INDEX idx_te_created (created_at),
            CONSTRAINT fk_te_user FOREIGN KEY (user_id)
                REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))
    conn.commit()
    print("Created web_ticker_events table.")
