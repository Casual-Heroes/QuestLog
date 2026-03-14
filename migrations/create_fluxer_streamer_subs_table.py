"""
Migration: create web_fluxer_streamer_subs table
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 create_fluxer_streamer_subs_table.py
"""
from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_fluxer_streamer_subs (
            id                   INT AUTO_INCREMENT PRIMARY KEY,
            guild_id             VARCHAR(25) NOT NULL,
            streamer_platform    VARCHAR(20) NOT NULL,
            streamer_handle      VARCHAR(100) NOT NULL,
            streamer_display_name VARCHAR(100) NULL,
            notify_channel_id    VARCHAR(25) NOT NULL,
            custom_message       VARCHAR(500) NULL,
            is_active            SMALLINT NOT NULL DEFAULT 1,
            is_currently_live    SMALLINT NOT NULL DEFAULT 0,
            last_notified_at     BIGINT NULL,
            created_at           BIGINT NOT NULL,
            updated_at           BIGINT NOT NULL,
            UNIQUE KEY uq_fluxer_streamer_sub (guild_id, streamer_platform, streamer_handle),
            KEY idx_fluxer_streamer_sub_guild (guild_id),
            KEY idx_fluxer_streamer_sub_active (is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.commit()
    print("Done: web_fluxer_streamer_subs created")
