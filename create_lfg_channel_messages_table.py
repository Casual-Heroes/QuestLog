"""
Migration: create web_lfg_channel_messages table.

Stores the bot message ID for each LFG embed posted to a guild channel.
Used to delete-and-repost the embed when a member joins, keeping the
channel tidy instead of sending a separate "New Member Joined" message.

Run with:
    chwebsiteprj/bin/python3 create_lfg_channel_messages_table.py
"""

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS web_lfg_channel_messages (
    id            INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    group_id      INT          NOT NULL,
    group_platform VARCHAR(16) NOT NULL DEFAULT 'web',
    platform      VARCHAR(16)  NOT NULL,
    guild_id      VARCHAR(32)  NOT NULL,
    channel_id    VARCHAR(32)  NOT NULL,
    message_id    VARCHAR(32)  NOT NULL,
    created_at    BIGINT       NOT NULL,
    INDEX idx_lfg_msg_group (group_id, group_platform),
    INDEX idx_lfg_msg_platform_guild (platform, guild_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text(CREATE_SQL))
    conn.commit()
    print("Created web_lfg_channel_messages table (or already existed).")
