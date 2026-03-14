#!/usr/bin/env python3
"""
Migration: Create web_fluxer_member_flairs table.
Tracks per-guild flair ownership and equipped state for Fluxer members.

Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 create_fluxer_member_flairs_table.py
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

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS web_fluxer_member_flairs (
    id              INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    guild_id        VARCHAR(32) NOT NULL,
    web_user_id     INT NOT NULL,
    guild_flair_id  INT NOT NULL,
    equipped        TINYINT NOT NULL DEFAULT 0,
    bought_at       BIGINT NOT NULL DEFAULT 0,
    INDEX idx_fluxer_member_flair_guild_user (guild_id, web_user_id),
    UNIQUE KEY uq_fluxer_member_flair (guild_id, web_user_id, guild_flair_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with engine.connect() as conn:
    print("Creating web_fluxer_member_flairs table...")
    conn.execute(text(CREATE_TABLE))
    conn.commit()
    print("Done.")
