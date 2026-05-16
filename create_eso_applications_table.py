#!/usr/bin/env python3
"""Create web_eso_applications table."""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_eso_applications (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            web_user_id      INT NULL,
            character_name   VARCHAR(100) NOT NULL,
            main_class       VARCHAR(50) NOT NULL,
            subclass         VARCHAR(50) NOT NULL,
            role             VARCHAR(100) NOT NULL,
            experience_level VARCHAR(200) NOT NULL,
            content_interests TEXT NULL,
            availability     TEXT NULL,
            why_join         TEXT NOT NULL,
            about_me         TEXT NULL,
            referral         VARCHAR(100) NULL,
            status           VARCHAR(20) NOT NULL DEFAULT 'pending',
            admin_notes      TEXT NULL,
            submitted_at     BIGINT NOT NULL,
            reviewed_at      BIGINT NULL,
            reviewed_by      INT NULL,
            CONSTRAINT fk_eso_app_user FOREIGN KEY (web_user_id)
                REFERENCES web_users(id) ON DELETE SET NULL,
            INDEX idx_eso_app_user (web_user_id),
            INDEX idx_eso_app_status (status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))
    conn.commit()
    print("Created web_eso_applications table.")
