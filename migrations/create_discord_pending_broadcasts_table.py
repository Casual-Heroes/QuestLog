"""
Migration: create discord_pending_broadcasts table
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 create_discord_pending_broadcasts_table.py
"""
from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS discord_pending_broadcasts (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            guild_id     BIGINT NOT NULL,
            channel_id   BIGINT NOT NULL,
            payload      TEXT NOT NULL,
            created_at   BIGINT NOT NULL,
            KEY idx_dpb_created (created_at),
            KEY idx_dpb_guild (guild_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.commit()
    print("Done: discord_pending_broadcasts created")
