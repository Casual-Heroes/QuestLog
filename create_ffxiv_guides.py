"""Migration: create FFXIV guide tables."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS web_ffxiv_guides (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        author_id       INT NOT NULL,
        job_key         VARCHAR(10) NOT NULL,
        title           VARCHAR(150) NOT NULL,
        slug            VARCHAR(180) NOT NULL UNIQUE,
        summary         VARCHAR(300) NULL,
        tags            TEXT NULL,
        patch_version   VARCHAR(20) NULL,
        blocks          LONGTEXT NULL,
        is_published    TINYINT(1) NOT NULL DEFAULT 1,
        is_hidden       TINYINT(1) NOT NULL DEFAULT 0,
        is_pinned       TINYINT(1) NOT NULL DEFAULT 0,
        view_count      INT NOT NULL DEFAULT 0,
        like_count      INT NOT NULL DEFAULT 0,
        comment_count   INT NOT NULL DEFAULT 0,
        created_at      BIGINT NOT NULL,
        updated_at      BIGINT NOT NULL,
        INDEX ix_ffxiv_guides_job      (job_key),
        INDEX ix_ffxiv_guides_author   (author_id),
        INDEX ix_ffxiv_guides_job_pub  (job_key, is_published, is_hidden),
        INDEX ix_ffxiv_guides_pinned   (is_pinned),
        CONSTRAINT fk_ffxiv_guides_author FOREIGN KEY (author_id) REFERENCES web_users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS web_ffxiv_guide_likes (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        guide_id   INT NOT NULL,
        user_id    INT NOT NULL,
        created_at BIGINT NOT NULL,
        INDEX ix_ffxiv_guide_likes_guide (guide_id),
        UNIQUE KEY uq_ffxiv_guide_like (guide_id, user_id),
        CONSTRAINT fk_ffxiv_guide_likes_guide FOREIGN KEY (guide_id) REFERENCES web_ffxiv_guides(id) ON DELETE CASCADE,
        CONSTRAINT fk_ffxiv_guide_likes_user  FOREIGN KEY (user_id)  REFERENCES web_users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS web_ffxiv_guide_comments (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        guide_id   INT NOT NULL,
        author_id  INT NOT NULL,
        parent_id  INT NULL,
        body       TEXT NOT NULL,
        is_deleted TINYINT(1) NOT NULL DEFAULT 0,
        like_count INT NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        INDEX ix_ffxiv_guide_comments_guide  (guide_id),
        INDEX ix_ffxiv_guide_comments_author (author_id),
        CONSTRAINT fk_ffxiv_guide_comments_guide  FOREIGN KEY (guide_id)  REFERENCES web_ffxiv_guides(id) ON DELETE CASCADE,
        CONSTRAINT fk_ffxiv_guide_comments_author FOREIGN KEY (author_id) REFERENCES web_users(id),
        CONSTRAINT fk_ffxiv_guide_comments_parent FOREIGN KEY (parent_id) REFERENCES web_ffxiv_guide_comments(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS web_ffxiv_guide_comment_likes (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        comment_id INT NOT NULL,
        user_id    INT NOT NULL,
        created_at BIGINT NOT NULL,
        INDEX ix_ffxiv_gcl_comment (comment_id),
        UNIQUE KEY uq_ffxiv_guide_comment_like (comment_id, user_id),
        CONSTRAINT fk_ffxiv_gcl_comment FOREIGN KEY (comment_id) REFERENCES web_ffxiv_guide_comments(id) ON DELETE CASCADE,
        CONSTRAINT fk_ffxiv_gcl_user    FOREIGN KEY (user_id)    REFERENCES web_users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

with engine.connect() as conn:
    for sql in TABLES:
        conn.execute(text(sql))
        conn.commit()
    print("All FFXIV guide tables created.")
