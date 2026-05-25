#!/usr/bin/env python3
"""Migration: create web_site_feedback table."""
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
CREATE TABLE IF NOT EXISTS web_site_feedback (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NULL,
    category    VARCHAR(30) NOT NULL DEFAULT 'general',
    subject     VARCHAR(200) NOT NULL,
    body        TEXT NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'new',
    created_at  BIGINT NOT NULL,
    INDEX idx_site_feedback_user (user_id),
    INDEX idx_site_feedback_created (created_at),
    INDEX idx_site_feedback_status (status),
    CONSTRAINT fk_site_feedback_user FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

with engine.connect() as conn:
    conn.execute(sa_text(DDL))
    conn.commit()
    print("Created web_site_feedback table.")
