#!/usr/bin/env python3
"""
Migration: Add enabled column to web_fluxer_rss_feeds.

1 = enabled (default), 0 = disabled (paused, not deleted)

Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_fluxer_rss_feeds_add_enabled.py
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
        ADD COLUMN enabled TINYINT NOT NULL DEFAULT 1
        COMMENT '1=enabled, 0=paused'
        AFTER last_error
    """))
    conn.commit()
    print("OK: enabled column added to web_fluxer_rss_feeds.")

print("Migration complete.")
