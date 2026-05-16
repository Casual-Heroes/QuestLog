"""Migration: create web_ffxiv_dd_runs and web_ffxiv_dd_pb tables."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_dd_runs (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id     INT NOT NULL,
            dungeon     VARCHAR(8) NOT NULL,
            floor_start INT NOT NULL,
            floor_end   INT NOT NULL,
            kos         INT NOT NULL DEFAULT 0,
            job         VARCHAR(32),
            party_size  INT NOT NULL DEFAULT 1,
            is_clear    TINYINT(1) NOT NULL DEFAULT 0,
            notes       VARCHAR(256),
            run_at      BIGINT NOT NULL,
            INDEX idx_dd_runs_user (user_id),
            INDEX idx_dd_runs_dungeon (dungeon),
            CONSTRAINT fk_dd_runs_user FOREIGN KEY (user_id)
                REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_dd_pb (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id     INT NOT NULL,
            dungeon     VARCHAR(8) NOT NULL,
            floor_end   INT NOT NULL,
            kos         INT NOT NULL DEFAULT 0,
            job         VARCHAR(32),
            party_size  INT NOT NULL DEFAULT 1,
            is_clear    TINYINT(1) NOT NULL DEFAULT 0,
            run_at      BIGINT NOT NULL,
            INDEX idx_dd_pb_user (user_id),
            UNIQUE KEY uq_dd_pb (user_id, dungeon),
            CONSTRAINT fk_dd_pb_user FOREIGN KEY (user_id)
                REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.commit()

print("Done - web_ffxiv_dd_runs and web_ffxiv_dd_pb created.")
