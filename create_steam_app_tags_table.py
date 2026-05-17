#!/usr/bin/env python3
"""Creates web_steam_app_tags table for SteamQuest genre/theme filtering."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_steam_app_tags (
            id        INT AUTO_INCREMENT PRIMARY KEY,
            app_id    INT NOT NULL,
            tag_name  VARCHAR(128) NOT NULL,
            synced_at BIGINT NOT NULL,
            UNIQUE KEY uq_steam_app_tag (app_id, tag_name),
            INDEX ix_steam_app_tags_app (app_id),
            INDEX ix_steam_app_tags_tag (tag_name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("web_steam_app_tags table created (or already exists).")
