#!/usr/bin/env python3
"""
Migration: Add max_age_days column to web_fluxer_rss_feeds.

NULL = no age limit (post everything)
0    = same as NULL
N    = skip articles older than N days (based on published_at / posted_at)

Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_fluxer_rss_feeds_max_age.py
"""
import os, sys
sys.path.insert(0, '/srv/ch-webserver')
os.environ['DJANGO_SETTINGS_MODULE'] = 'casualsite.settings'
import django; django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_fluxer_rss_feeds
        ADD COLUMN max_age_days INT NULL DEFAULT NULL
        COMMENT 'Skip articles older than this many days. NULL = no limit.'
        AFTER poll_interval_minutes
    """))
    conn.commit()
    print("OK: max_age_days column added to web_fluxer_rss_feeds.")

print("Migration complete.")
