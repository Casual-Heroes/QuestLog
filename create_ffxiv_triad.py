"""Migration: create web_ffxiv_triad_cards and web_ffxiv_triad_decks tables."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_triad_cards (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id     INT NOT NULL,
            card_id     INT NOT NULL,
            obtained_at BIGINT NOT NULL,
            notes       VARCHAR(256),
            UNIQUE KEY uq_triad_user_card (user_id, card_id),
            KEY ix_triad_cards_user (user_id),
            FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_triad_decks (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            user_id    INT NOT NULL,
            name       VARCHAR(64) NOT NULL,
            card_ids   TEXT NOT NULL,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL,
            KEY ix_triad_decks_user (user_id),
            FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))
    conn.commit()

print("Done: web_ffxiv_triad_cards and web_ffxiv_triad_decks created.")
