"""
Create sl_guides, sl_guide_likes, sl_guide_comments tables.
Run: chwebsiteprj/bin/python3 create_sl_guides.py
"""
import django, os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

TABLES = [
    """
    CREATE TABLE IF NOT EXISTS sl_guides (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        author_id       INT NOT NULL,
        title           VARCHAR(200) NOT NULL,
        slug            VARCHAR(230) NOT NULL UNIQUE,
        summary         VARCHAR(400) NULL,
        body            LONGTEXT NULL,
        game            VARCHAR(100) NOT NULL DEFAULT 'elden_ring',
        game_mode       VARCHAR(32)  NULL,
        game_tag_name   VARCHAR(200) NULL,
        game_tag_steam_id INT        NULL,
        guide_type      VARCHAR(30)  NOT NULL DEFAULT 'general',
        is_published    TINYINT(1)   NOT NULL DEFAULT 1,
        is_hidden       TINYINT(1)   NOT NULL DEFAULT 0,
        is_pinned       TINYINT(1)   NOT NULL DEFAULT 0,
        view_count      INT          NOT NULL DEFAULT 0,
        like_count      INT          NOT NULL DEFAULT 0,
        comment_count   INT          NOT NULL DEFAULT 0,
        created_at      BIGINT       NOT NULL,
        updated_at      BIGINT       NOT NULL,
        INDEX idx_sl_guides_game     (game, is_published, is_hidden),
        INDEX idx_sl_guides_author   (author_id),
        INDEX idx_sl_guides_type     (guide_type),
        INDEX idx_sl_guides_pinned   (is_pinned)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS sl_guide_likes (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        guide_id   INT NOT NULL,
        user_id    INT NOT NULL,
        created_at BIGINT NOT NULL,
        UNIQUE KEY uq_sl_guide_like (guide_id, user_id),
        INDEX idx_sl_guide_likes_guide (guide_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS sl_guide_comments (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        guide_id   INT NOT NULL,
        author_id  INT NOT NULL,
        body       TEXT NOT NULL,
        is_deleted TINYINT(1) NOT NULL DEFAULT 0,
        like_count INT NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        INDEX idx_sl_guide_comments_guide  (guide_id),
        INDEX idx_sl_guide_comments_author (author_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]

with get_db_session() as db:
    for sql in TABLES:
        db.execute(text(sql.strip()))
    db.commit()

print("sl_guides, sl_guide_likes, sl_guide_comments created.")
