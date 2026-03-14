"""Migration: create web_custom_emoji table for site-wide custom emoji and stickers."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_custom_emoji (
            id INT AUTO_INCREMENT PRIMARY KEY,
            shortcode VARCHAR(50) NOT NULL UNIQUE,
            image_url VARCHAR(500) NOT NULL,
            is_animated TINYINT(1) NOT NULL DEFAULT 0,
            is_sticker TINYINT(1) NOT NULL DEFAULT 0,
            created_at BIGINT NOT NULL,
            created_by INT NULL,
            INDEX idx_custom_emoji_shortcode (shortcode),
            CONSTRAINT fk_custom_emoji_creator FOREIGN KEY (created_by) REFERENCES web_users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("web_custom_emoji table created.")
