"""
Migration: create web_ffxiv_characters and web_ffxiv_achievement_rewards tables.
Run: chwebsiteprj/bin/python3 create_ffxiv_tables.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()

with engine.connect() as conn:
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_characters (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            user_id         INT NOT NULL,
            lodestone_id    VARCHAR(20) NOT NULL,
            character_name  VARCHAR(100) NOT NULL,
            world           VARCHAR(50) NOT NULL,
            datacenter      VARCHAR(50) NOT NULL,
            avatar_url      VARCHAR(500),
            portrait_url    VARCHAR(500),
            title           VARCHAR(200),
            free_company    VARCHAR(200),
            fc_tag          VARCHAR(10),
            active_job      VARCHAR(50),
            -- Collection counts (refreshed from Lodestone)
            mount_count     INT DEFAULT 0,
            minion_count    INT DEFAULT 0,
            -- Raw JSON snapshots from Lodestone scrape (stored as TEXT)
            mounts_json     MEDIUMTEXT,
            minions_json    MEDIUMTEXT,
            achievements_json MEDIUMTEXT,
            -- Sync state
            last_synced_at  BIGINT,
            sync_status     VARCHAR(20) DEFAULT 'pending',  -- pending, syncing, ok, error, private
            sync_error      VARCHAR(500),
            -- Flags
            is_primary      TINYINT(1) DEFAULT 1,
            created_at      BIGINT NOT NULL,
            updated_at      BIGINT NOT NULL,
            UNIQUE KEY uq_user_character (user_id, lodestone_id),
            INDEX idx_ffxiv_user (user_id),
            INDEX idx_ffxiv_lodestone (lodestone_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print("Created web_ffxiv_characters")

    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_ffxiv_achievement_rewards (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            user_id         INT NOT NULL,
            lodestone_id    VARCHAR(20) NOT NULL,
            achievement_key VARCHAR(100) NOT NULL,
            achievement_name VARCHAR(200) NOT NULL,
            xp_awarded      INT DEFAULT 0,
            legacy_awarded  INT DEFAULT 0,
            awarded_at      BIGINT NOT NULL,
            UNIQUE KEY uq_user_achievement (user_id, achievement_key),
            INDEX idx_ffxiv_ach_user (user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print("Created web_ffxiv_achievement_rewards")

    conn.commit()

print("Done.")
