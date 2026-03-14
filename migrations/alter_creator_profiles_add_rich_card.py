"""
Migration: Add rich card columns to web_creator_profiles.
Adds latest YouTube video, latest stream snapshot, and Steam opt-in flag.
Run: chwebsiteprj/bin/python3 alter_creator_profiles_add_rich_card.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

COLUMNS = [
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS latest_youtube_video_id VARCHAR(50) DEFAULT NULL",
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS latest_youtube_video_title VARCHAR(300) DEFAULT NULL",
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS latest_youtube_thumbnail_url VARCHAR(500) DEFAULT NULL",
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS latest_youtube_video_published_at BIGINT DEFAULT NULL",
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS latest_stream_title VARCHAR(300) DEFAULT NULL",
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS latest_stream_thumbnail_url VARCHAR(500) DEFAULT NULL",
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS latest_stream_platform VARCHAR(20) DEFAULT NULL",
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS latest_stream_ended_at BIGINT DEFAULT NULL",
    "ALTER TABLE web_creator_profiles ADD COLUMN IF NOT EXISTS show_steam_on_profile TINYINT(1) NOT NULL DEFAULT 0",
]

with engine.connect() as conn:
    for sql in COLUMNS:
        try:
            conn.execute(text(sql))
            print(f"OK: {sql[:80]}")
        except Exception as e:
            print(f"SKIP (may already exist): {e}")
    conn.commit()

print("Done.")
