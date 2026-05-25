#!/usr/bin/env python3
"""Migration: create web_site_announcements table."""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()

DDL = """
CREATE TABLE IF NOT EXISTS web_site_announcements (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    author_id   INT NOT NULL,
    title       VARCHAR(200) NOT NULL,
    body_md     MEDIUMTEXT NOT NULL,
    category    VARCHAR(20) NOT NULL DEFAULT 'update',
    is_pinned   TINYINT(1) NOT NULL DEFAULT 0,
    created_at  BIGINT NOT NULL,
    updated_at  BIGINT NOT NULL,
    INDEX idx_site_ann_author (author_id),
    INDEX idx_site_ann_created (created_at),
    CONSTRAINT fk_site_ann_author FOREIGN KEY (author_id) REFERENCES web_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

with engine.connect() as conn:
    conn.execute(sa_text(DDL))
    conn.commit()
    print("Created web_site_announcements table.")
