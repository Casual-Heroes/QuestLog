"""Migration: create web_ffxiv_field_ops table."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_field_ops (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            user_id          INT NOT NULL,
            zone             VARCHAR(24) NOT NULL,
            elemental_level  INT,
            logos_actions    INT,
            resistance_rank  INT,
            mettle           BIGINT,
            ces_completed    INT,
            knowledge_level  INT,
            phantom_unlocked INT,
            phantom_mastered INT,
            forked_clears    INT,
            relic_stage      VARCHAR(64),
            updated_at       BIGINT NOT NULL,
            INDEX idx_fo_user (user_id),
            UNIQUE KEY uq_field_ops (user_id, zone),
            CONSTRAINT fk_fo_user FOREIGN KEY (user_id)
                REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.commit()

print("Done - web_ffxiv_field_ops created.")
