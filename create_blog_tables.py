"""
Migration: create blog tables + is_contributor flag on web_users.

Run with:
    chwebsiteprj/bin/python3 create_blog_tables.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()

STATEMENTS = [
    # -------------------------------------------------------------------------
    # 1. is_contributor flag on web_users
    # -------------------------------------------------------------------------
    """
    ALTER TABLE web_users
    ADD COLUMN IF NOT EXISTS is_contributor TINYINT(1) NOT NULL DEFAULT 0
    AFTER is_ffxiv_member
    """,

    # -------------------------------------------------------------------------
    # 2. web_articles
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_articles (
        id            INT NOT NULL AUTO_INCREMENT,
        author_id     INT NOT NULL,
        title         VARCHAR(200) NOT NULL,
        slug          VARCHAR(220) NOT NULL,
        summary       VARCHAR(500),
        category      VARCHAR(20) NOT NULL DEFAULT 'article',
        game_tag_id   INT,
        game_tag_name VARCHAR(500),
        cover_url     VARCHAR(500),
        body_md       LONGTEXT NOT NULL,
        is_published  TINYINT(1) NOT NULL DEFAULT 0,
        is_hidden     TINYINT(1) NOT NULL DEFAULT 0,
        is_pinned     TINYINT(1) NOT NULL DEFAULT 0,
        comment_count INT NOT NULL DEFAULT 0,
        view_count    INT NOT NULL DEFAULT 0,
        edited_at     BIGINT,
        edit_count    INT NOT NULL DEFAULT 0,
        created_at    BIGINT NOT NULL,
        updated_at    BIGINT NOT NULL,
        published_at  BIGINT,
        PRIMARY KEY (id),
        UNIQUE KEY uq_articles_slug (slug),
        KEY ix_web_articles_listing (is_published, is_hidden, category, published_at),
        KEY ix_web_articles_author (author_id),
        KEY ix_web_articles_pinned (is_pinned),
        CONSTRAINT fk_articles_author FOREIGN KEY (author_id) REFERENCES web_users (id),
        CONSTRAINT fk_articles_game   FOREIGN KEY (game_tag_id) REFERENCES web_found_games (id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # -------------------------------------------------------------------------
    # 3. web_article_comments
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_article_comments (
        id          INT NOT NULL AUTO_INCREMENT,
        article_id  INT NOT NULL,
        author_id   INT NOT NULL,
        parent_id   INT,
        content     TEXT NOT NULL,
        is_deleted  TINYINT(1) NOT NULL DEFAULT 0,
        like_count  INT NOT NULL DEFAULT 0,
        created_at  BIGINT NOT NULL,
        updated_at  BIGINT NOT NULL,
        PRIMARY KEY (id),
        KEY ix_web_article_comments_article (article_id, is_deleted),
        KEY ix_web_article_comments_author (author_id),
        CONSTRAINT fk_artcmt_article FOREIGN KEY (article_id) REFERENCES web_articles (id) ON DELETE CASCADE,
        CONSTRAINT fk_artcmt_author  FOREIGN KEY (author_id)  REFERENCES web_users (id),
        CONSTRAINT fk_artcmt_parent  FOREIGN KEY (parent_id)  REFERENCES web_article_comments (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # -------------------------------------------------------------------------
    # 4. web_article_comment_likes
    # -------------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_article_comment_likes (
        id          INT NOT NULL AUTO_INCREMENT,
        comment_id  INT NOT NULL,
        user_id     INT NOT NULL,
        created_at  BIGINT NOT NULL,
        PRIMARY KEY (id),
        UNIQUE KEY uq_article_comment_like (comment_id, user_id),
        KEY ix_artcmtlike_comment (comment_id),
        CONSTRAINT fk_artcmtlike_comment FOREIGN KEY (comment_id) REFERENCES web_article_comments (id) ON DELETE CASCADE,
        CONSTRAINT fk_artcmtlike_user    FOREIGN KEY (user_id)    REFERENCES web_users (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

with engine.connect() as conn:
    for sql in STATEMENTS:
        stmt = sql.strip()
        # Extract first line for display
        first_line = stmt.split('\n')[0]
        print(f"Running: {first_line[:80]}...")
        conn.execute(sa_text(stmt))
        conn.commit()
        print("  OK")

print("\nAll blog migration statements completed successfully.")
