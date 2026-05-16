"""Migration: create web_testimonials table."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '.')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_testimonials (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            member_name VARCHAR(100) NOT NULL,
            handle      VARCHAR(100) NULL,
            avatar_url  VARCHAR(500) NULL,
            quote       TEXT NOT NULL,
            game_tag    VARCHAR(100) NULL,
            sort_order  INT NOT NULL DEFAULT 0,
            is_active   TINYINT(1) NOT NULL DEFAULT 1,
            created_at  BIGINT NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.commit()
    print("web_testimonials table created.")
