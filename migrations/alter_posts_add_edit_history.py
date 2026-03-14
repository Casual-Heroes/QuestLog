"""
Migration: add edit history to posts.
- Adds web_post_edits table (id, post_id, content_before, edited_at)
- Adds edited_at and edit_count columns to web_posts
Run with: chwebsiteprj/bin/python3 alter_posts_add_edit_history.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_post_edits (
            id INT AUTO_INCREMENT PRIMARY KEY,
            post_id INT NOT NULL,
            content_before TEXT NOT NULL,
            edited_at BIGINT NOT NULL,
            INDEX idx_post_edit_post (post_id, edited_at),
            CONSTRAINT fk_post_edit_post FOREIGN KEY (post_id)
                REFERENCES web_posts(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.execute(text("""
        ALTER TABLE web_posts
        ADD COLUMN IF NOT EXISTS edited_at BIGINT NULL DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS edit_count INT NOT NULL DEFAULT 0
    """))
    conn.commit()
    print("Done: created web_post_edits, added edited_at + edit_count to web_posts")
