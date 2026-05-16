"""Migration: add web_steam_achievements and web_steam_achievement_showcase tables."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_steam_achievements (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            web_user_id INT NOT NULL,
            app_id      INT NOT NULL,
            game_name   VARCHAR(200) NOT NULL,
            api_name    VARCHAR(200) NOT NULL,
            display_name VARCHAR(200) NOT NULL,
            description VARCHAR(500),
            icon_url    VARCHAR(500),
            unlocked_at BIGINT,
            synced_at   BIGINT NOT NULL,
            CONSTRAINT uq_steam_ach UNIQUE (web_user_id, app_id, api_name),
            INDEX idx_steam_ach_user (web_user_id),
            INDEX idx_steam_ach_app (web_user_id, app_id),
            FOREIGN KEY (web_user_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_steam_achievement_showcase (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            web_user_id    INT NOT NULL,
            achievement_id INT NOT NULL,
            sort_order     INT NOT NULL DEFAULT 0,
            pinned_at      BIGINT NOT NULL,
            CONSTRAINT uq_showcase_ach UNIQUE (web_user_id, achievement_id),
            INDEX idx_showcase_user (web_user_id),
            FOREIGN KEY (web_user_id) REFERENCES web_users(id) ON DELETE CASCADE,
            FOREIGN KEY (achievement_id) REFERENCES web_steam_achievements(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("Done: web_steam_achievements and web_steam_achievement_showcase tables created.")
