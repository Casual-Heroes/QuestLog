"""
Migration: create web_post_broadcast_messages table.
Tracks which Fluxer/Discord message corresponds to each QuestLog post broadcast,
so edits and deletes can update/remove the same message rather than posting new ones.
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_post_broadcast_messages (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            post_id       INT          NOT NULL,
            platform      VARCHAR(16)  NOT NULL,   -- 'fluxer' or 'discord'
            channel_id    VARCHAR(32)  NOT NULL,
            message_id    VARCHAR(32)  NOT NULL,
            webhook_url   VARCHAR(500) NULL,        -- for discord webhook edits/deletes
            created_at    BIGINT       NOT NULL,
            INDEX idx_pbm_post (post_id),
            UNIQUE KEY uq_pbm_post_platform (post_id, platform)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("web_post_broadcast_messages created (or already exists)")
