"""Migration: create ESO build system tables."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()

tables = [
    """
    CREATE TABLE IF NOT EXISTS web_eso_builds (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        author_id       INT NOT NULL,
        title           VARCHAR(120) NOT NULL,
        slug            VARCHAR(140) NOT NULL UNIQUE,
        tagline         VARCHAR(200),
        patch_version   VARCHAR(20),
        eso_class       VARCHAR(40) NOT NULL,
        role            VARCHAR(20) NOT NULL,
        resource        VARCHAR(20),
        stat_health     INT,
        stat_magicka    INT,
        stat_stamina    INT,
        stat_dps        INT,
        stat_hps        INT,
        difficulty      TINYINT,
        how_it_works    LONGTEXT,
        pros            TEXT,
        cons            TEXT,
        champion_points LONGTEXT,
        rotation        LONGTEXT,
        gear            LONGTEXT,
        skills          LONGTEXT,
        mundus          VARCHAR(80),
        buff_food       VARCHAR(120),
        is_meta         TINYINT(1) NOT NULL DEFAULT 0,
        is_published    TINYINT(1) NOT NULL DEFAULT 1,
        view_count      INT NOT NULL DEFAULT 0,
        upvotes         INT NOT NULL DEFAULT 0,
        downvotes       INT NOT NULL DEFAULT 0,
        comment_count   INT NOT NULL DEFAULT 0,
        created_at      BIGINT NOT NULL,
        updated_at      BIGINT NOT NULL,
        INDEX ix_eso_builds_class_role (eso_class, role),
        INDEX ix_eso_builds_author (author_id),
        INDEX ix_eso_builds_meta (is_meta),
        FOREIGN KEY (author_id) REFERENCES web_users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS web_eso_build_votes (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        build_id   INT NOT NULL,
        user_id    INT NOT NULL,
        vote       TINYINT NOT NULL,
        created_at BIGINT NOT NULL,
        UNIQUE KEY uq_eso_build_vote (build_id, user_id),
        INDEX (build_id),
        FOREIGN KEY (build_id) REFERENCES web_eso_builds(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id)  REFERENCES web_users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS web_eso_build_comments (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        build_id   INT NOT NULL,
        author_id  INT NOT NULL,
        body       TEXT NOT NULL,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        INDEX (build_id),
        INDEX (author_id),
        FOREIGN KEY (build_id)  REFERENCES web_eso_builds(id) ON DELETE CASCADE,
        FOREIGN KEY (author_id) REFERENCES web_users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS web_eso_build_bookmarks (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        build_id   INT NOT NULL,
        user_id    INT NOT NULL,
        created_at BIGINT NOT NULL,
        UNIQUE KEY uq_eso_build_bookmark (build_id, user_id),
        INDEX (build_id),
        FOREIGN KEY (build_id) REFERENCES web_eso_builds(id) ON DELETE CASCADE,
        FOREIGN KEY (user_id)  REFERENCES web_users(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]

with engine.connect() as conn:
    for sql in tables:
        conn.execute(sa_text(sql))
        conn.commit()
    print("ESO build tables created successfully.")
