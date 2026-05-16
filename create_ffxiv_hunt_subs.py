"""Migration: create web_ffxiv_hunt_subs and seed ffxiv_hunt webhook config row."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

import time
from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_hunt_subs (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            user_id       INT NOT NULL,
            watch_key     VARCHAR(128) NOT NULL,
            worlds        VARCHAR(512),
            notify_site   TINYINT(1) NOT NULL DEFAULT 1,
            notify_fluxer TINYINT(1) NOT NULL DEFAULT 0,
            created_at    BIGINT NOT NULL,
            UNIQUE KEY uq_hunt_sub_user_key (user_id, watch_key),
            KEY ix_hunt_subs_user (user_id),
            FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """))

    # Seed webhook config row for ffxiv_hunt if not present
    now = int(time.time())
    conn.execute(text("""
        INSERT IGNORE INTO web_fluxer_webhook_configs
            (event_type, label, is_enabled, created_at, updated_at)
        VALUES
            ('ffxiv_hunt', 'FFXIV Hunt / Event Alerts', 0, :now, :now)
    """), {'now': now})

    conn.commit()

print("Done: web_ffxiv_hunt_subs created, ffxiv_hunt webhook config seeded.")
