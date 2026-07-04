"""Add web_indie_suggestions table."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_indie_suggestions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            game_name VARCHAR(200) NOT NULL,
            steam_url VARCHAR(500) NULL,
            itch_url VARCHAR(500) NULL,
            other_url VARCHAR(500) NULL,
            note TEXT NULL,
            suggested_by INT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at BIGINT NOT NULL,
            INDEX idx_indie_suggestions_status (status),
            INDEX idx_indie_suggestions_user (suggested_by)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("Created web_indie_suggestions table")
