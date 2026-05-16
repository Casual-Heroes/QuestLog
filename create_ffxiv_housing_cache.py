"""Create web_ffxiv_housing_cache table."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_housing_cache (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            world_id   INT NOT NULL UNIQUE,
            world_name VARCHAR(64) NOT NULL DEFAULT '',
            payload_json MEDIUMTEXT NOT NULL,
            cached_at  BIGINT NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("Created web_ffxiv_housing_cache table.")
