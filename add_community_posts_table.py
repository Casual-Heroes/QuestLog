"""
Migration: add web_community_posts table for Community Spaces wall feature.
Run with: chwebsiteprj/bin/python3 add_community_posts_table.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_community_posts (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            community_id  INT NOT NULL,
            author_id     INT NOT NULL,
            content       TEXT NOT NULL,
            is_pinned     TINYINT(1) NOT NULL DEFAULT 0,
            is_deleted    TINYINT(1) NOT NULL DEFAULT 0,
            like_count    INT NOT NULL DEFAULT 0,
            created_at    BIGINT NOT NULL,
            updated_at    BIGINT NOT NULL,
            INDEX idx_cp_community (community_id, is_deleted, created_at),
            INDEX idx_cp_author (author_id),
            CONSTRAINT fk_cp_community FOREIGN KEY (community_id) REFERENCES web_communities(id) ON DELETE CASCADE,
            CONSTRAINT fk_cp_author    FOREIGN KEY (author_id)    REFERENCES web_users(id)       ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_community_post_likes (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            post_id       INT NOT NULL,
            user_id       INT NOT NULL,
            created_at    BIGINT NOT NULL,
            UNIQUE KEY uq_cp_like (post_id, user_id),
            CONSTRAINT fk_cpl_post FOREIGN KEY (post_id) REFERENCES web_community_posts(id) ON DELETE CASCADE,
            CONSTRAINT fk_cpl_user FOREIGN KEY (user_id) REFERENCES web_users(id)           ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("Done - web_community_posts and web_community_post_likes created.")
