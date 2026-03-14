#!/usr/bin/env python3
"""
Migration: Expand web_fluxer_rss_feeds with WardenBot-parity fields.

Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_fluxer_rss_feeds_expand.py
"""
import os, sys
sys.path.insert(0, '/srv/ch-webserver')
os.environ['DJANGO_SETTINGS_MODULE'] = 'casualsite.settings'
import django; django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    for col_sql in [
        "ALTER TABLE web_fluxer_rss_feeds ADD COLUMN ping_role_id VARCHAR(32) NULL DEFAULT NULL",
        "ALTER TABLE web_fluxer_rss_feeds ADD COLUMN poll_interval_minutes INT NOT NULL DEFAULT 15",
        "ALTER TABLE web_fluxer_rss_feeds ADD COLUMN category_filter_mode VARCHAR(20) NOT NULL DEFAULT 'none'",
        "ALTER TABLE web_fluxer_rss_feeds ADD COLUMN category_filters TEXT NULL DEFAULT NULL",
        "ALTER TABLE web_fluxer_rss_feeds ADD COLUMN embed_config TEXT NULL DEFAULT NULL",
        "ALTER TABLE web_fluxer_rss_feeds ADD COLUMN consecutive_failures INT NOT NULL DEFAULT 0",
        "ALTER TABLE web_fluxer_rss_feeds ADD COLUMN last_error VARCHAR(500) NULL DEFAULT NULL",
    ]:
        try:
            conn.execute(text(col_sql))
            print(f"OK: {col_sql[:80]}")
        except Exception as e:
            if 'Duplicate column' in str(e):
                print(f"SKIP (exists): {col_sql[:80]}")
            else:
                print(f"ERROR: {e}")
    conn.commit()

print("Migration complete.")
