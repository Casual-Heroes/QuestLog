"""Create web_ffxiv_housing_worlds_cache table."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_housing_worlds_cache (
            id INT NOT NULL DEFAULT 1,
            payload_json MEDIUMTEXT NOT NULL,
            cached_at BIGINT NOT NULL,
            PRIMARY KEY (id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("Created web_ffxiv_housing_worlds_cache table.")
