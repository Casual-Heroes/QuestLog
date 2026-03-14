"""
Migration: create fluxer_channel_stat_trackers table.
Run: source chwebsiteprj/bin/activate && python3 create_fluxer_channel_stat_trackers.py
"""
from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS fluxer_channel_stat_trackers (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        VARCHAR(64) NOT NULL,
    channel_id      VARCHAR(64) NOT NULL,
    role_id         VARCHAR(64) NOT NULL,
    label           VARCHAR(100) NOT NULL,
    emoji           VARCHAR(100) DEFAULT NULL,
    game_name       VARCHAR(100) DEFAULT NULL,
    show_playing_count TINYINT(1) DEFAULT 0,
    enabled         TINYINT(1) DEFAULT 1,
    update_interval_seconds INT DEFAULT 60,
    last_updated    BIGINT DEFAULT NULL,
    last_topic      VARCHAR(500) DEFAULT NULL,
    created_at      BIGINT NOT NULL,
    created_by      VARCHAR(64) DEFAULT NULL,
    UNIQUE KEY uq_fluxer_guild_channel_tracker (guild_id, channel_id),
    KEY idx_fluxer_tracker_guild (guild_id),
    KEY idx_fluxer_tracker_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with engine.connect() as conn:
    conn.execute(text(CREATE_SQL))
    conn.commit()
    print("fluxer_channel_stat_trackers table created (or already exists).")
