"""Migration: create web_ffxiv_hunt_reports table"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_hunt_reports (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            hunt_key     VARCHAR(64) NOT NULL,
            reported_by  INT NULL,
            dc           VARCHAR(32) NOT NULL,
            world        VARCHAR(32) NOT NULL,
            event_type   VARCHAR(16) NOT NULL DEFAULT 'kill',
            reported_at  BIGINT NOT NULL,
            notes        VARCHAR(256) NULL,
            CONSTRAINT uq_hunt_world UNIQUE (hunt_key, world),
            INDEX idx_hunt_key (hunt_key),
            INDEX idx_reported_by (reported_by),
            CONSTRAINT fk_hunt_user FOREIGN KEY (reported_by)
                REFERENCES web_users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("web_ffxiv_hunt_reports table created.")
