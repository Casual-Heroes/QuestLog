#!/usr/bin/env python3
"""
Migration: Create web_unified_leaderboard table.

Run once:
  source /srv/ch-webserver/chwebsiteprj/bin/activate
  python3 create_unified_leaderboard_table.py
"""
import sys, os
sys.path.insert(0, '/srv/ch-webserver')
os.environ['DJANGO_SETTINGS_MODULE'] = 'casualsite.settings'
import django; django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

with engine.connect() as conn:
    print("Creating web_unified_leaderboard table...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_unified_leaderboard (
            id           INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            user_id      INT NOT NULL,
            guild_id     VARCHAR(32) NOT NULL,
            platform     VARCHAR(20) NOT NULL,
            messages     INT NOT NULL DEFAULT 0,
            voice_mins   INT NOT NULL DEFAULT 0,
            reactions    INT NOT NULL DEFAULT 0,
            media_count  INT NOT NULL DEFAULT 0,
            xp_total     INT NOT NULL DEFAULT 0,
            last_active  BIGINT NULL,
            updated_at   BIGINT NOT NULL DEFAULT 0,
            CONSTRAINT uq_unified_lb_user_guild_platform UNIQUE (user_id, guild_id, platform),
            INDEX idx_unified_lb_guild_platform (guild_id, platform),
            INDEX idx_unified_lb_xp (guild_id, platform, xp_total),
            CONSTRAINT fk_unified_lb_user FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.commit()
    print("Done. web_unified_leaderboard created.")
