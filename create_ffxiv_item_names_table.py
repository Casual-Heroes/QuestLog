"""Create web_ffxiv_item_names table for caching Lodestone mount/minion name lookups."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_item_names (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tooltip_hash VARCHAR(64) NOT NULL UNIQUE,
            item_type VARCHAR(10) NOT NULL COMMENT 'mount or minion',
            item_name VARCHAR(255) NOT NULL,
            lodestone_url VARCHAR(512),
            created_at BIGINT NOT NULL DEFAULT 0
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))
    conn.commit()
    print("Created web_ffxiv_item_names table.")
