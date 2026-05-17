"""Migration: create web_ffxiv_applications table."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_applications (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            web_user_id      INT NULL,
            character_name   VARCHAR(100) NOT NULL,
            home_world       VARCHAR(50)  NOT NULL,
            main_job         VARCHAR(50)  NOT NULL,
            alt_jobs         TEXT NULL,
            experience_level VARCHAR(50)  NOT NULL,
            content_interests TEXT NULL,
            availability     TEXT NULL,
            why_join         TEXT NOT NULL,
            about_me         TEXT NULL,
            referral         VARCHAR(100) NULL,
            status           VARCHAR(20)  NOT NULL DEFAULT 'pending',
            admin_notes      TEXT NULL,
            submitted_at     BIGINT NOT NULL,
            reviewed_at      BIGINT NULL,
            reviewed_by      INT NULL,
            INDEX idx_ffxiv_app_user   (web_user_id),
            INDEX idx_ffxiv_app_status (status),
            CONSTRAINT fk_ffxiv_app_user FOREIGN KEY (web_user_id)
                REFERENCES web_users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("web_ffxiv_applications created (or already exists)")
