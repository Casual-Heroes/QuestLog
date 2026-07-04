"""Add web_spotlight_slots table."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_spotlight_slots (
            id INT AUTO_INCREMENT PRIMARY KEY,
            category VARCHAR(20) NOT NULL,
            slot_type VARCHAR(20) NOT NULL,
            ref_id INT NOT NULL,
            starts_at BIGINT NOT NULL,
            expires_at BIGINT NULL,
            set_by INT NOT NULL,
            created_at BIGINT NOT NULL,
            INDEX idx_spotlight_category_type (category, slot_type),
            INDEX idx_spotlight_expires (expires_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("Created web_spotlight_slots table")
