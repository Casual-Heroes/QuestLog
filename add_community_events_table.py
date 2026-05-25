"""
Migration: add community events, RSVPs, and webhook fields.
Run with: chwebsiteprj/bin/python3 add_community_events_table.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    # Webhook columns on web_communities
    for col, defn in [
        ('discord_webhook_url', 'VARCHAR(1000) NULL'),
        ('fluxer_webhook_url',  'VARCHAR(1000) NULL'),
    ]:
        try:
            conn.execute(text(f'ALTER TABLE web_communities ADD COLUMN {col} {defn}'))
            print(f'Added web_communities.{col}')
        except Exception as e:
            print(f'Skipped {col}: {e}')

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_community_events (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            community_id    INT NOT NULL,
            created_by      INT NOT NULL,
            title           VARCHAR(200) NOT NULL,
            description     TEXT NULL,
            game_tag_name   VARCHAR(200) NULL,
            game_tag_steam_id INT NULL,
            game_cover_url  VARCHAR(500) NULL,
            starts_at       BIGINT NOT NULL,
            duration_mins   INT NOT NULL DEFAULT 120,
            max_attendees   INT NULL,
            rsvp_going      INT NOT NULL DEFAULT 0,
            rsvp_maybe      INT NOT NULL DEFAULT 0,
            is_cancelled    TINYINT(1) NOT NULL DEFAULT 0,
            webhook_sent    TINYINT(1) NOT NULL DEFAULT 0,
            created_at      BIGINT NOT NULL,
            updated_at      BIGINT NOT NULL,
            INDEX idx_ce_community (community_id, is_cancelled, starts_at),
            CONSTRAINT fk_ce_community FOREIGN KEY (community_id) REFERENCES web_communities(id) ON DELETE CASCADE,
            CONSTRAINT fk_ce_creator  FOREIGN KEY (created_by)   REFERENCES web_users(id)       ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print('Created web_community_events')

    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_community_event_rsvps (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            event_id    INT NOT NULL,
            user_id     INT NOT NULL,
            status      VARCHAR(20) NOT NULL DEFAULT 'going',
            created_at  BIGINT NOT NULL,
            UNIQUE KEY uq_event_rsvp (event_id, user_id),
            CONSTRAINT fk_cer_event FOREIGN KEY (event_id) REFERENCES web_community_events(id) ON DELETE CASCADE,
            CONSTRAINT fk_cer_user  FOREIGN KEY (user_id)  REFERENCES web_users(id)            ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print('Created web_community_event_rsvps')

    conn.commit()
    print('Done.')
