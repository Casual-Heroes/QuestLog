#!/usr/bin/env python3
"""
Migration: Create web_fluxer_rss_articles table.

Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 create_fluxer_rss_articles_table.py
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
        CREATE TABLE IF NOT EXISTS web_fluxer_rss_articles (
            id               INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            feed_id          INT NOT NULL,
            guild_id         VARCHAR(32) NOT NULL,
            entry_guid       VARCHAR(500) NOT NULL,
            entry_link       VARCHAR(500) NULL DEFAULT NULL,
            entry_title      VARCHAR(500) NULL DEFAULT NULL,
            entry_summary    TEXT NULL DEFAULT NULL,
            entry_author     VARCHAR(256) NULL DEFAULT NULL,
            entry_thumbnail  VARCHAR(500) NULL DEFAULT NULL,
            entry_categories TEXT NULL DEFAULT NULL,
            feed_label       VARCHAR(200) NULL DEFAULT NULL,
            published_at     BIGINT NULL DEFAULT NULL,
            posted_at        BIGINT NOT NULL,
            INDEX idx_fluxer_rss_article_guild (guild_id, posted_at),
            INDEX idx_fluxer_rss_article_feed (feed_id),
            UNIQUE KEY uq_fluxer_rss_article_guid (feed_id, entry_guid(200))
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("OK: web_fluxer_rss_articles table created.")

print("Migration complete.")
