"""
Migration: Create site_activity_fluxer_roles table
Run: chwebsiteprj/bin/python3 create_site_activity_fluxer_roles.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS site_activity_fluxer_roles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            game_id INT NOT NULL,
            guild_id VARCHAR(100) NOT NULL,
            role_id VARCHAR(100) NOT NULL,
            guild_name VARCHAR(255) DEFAULT NULL,
            role_name VARCHAR(255) DEFAULT NULL,
            is_active TINYINT(1) NOT NULL DEFAULT 1,
            CONSTRAINT fk_fluxer_role_game FOREIGN KEY (game_id)
                REFERENCES site_activity_games(id) ON DELETE CASCADE,
            UNIQUE KEY uq_fluxer_game_guild_role (game_id, guild_id, role_id),
            KEY idx_site_activity_fluxer_role_game (game_id),
            KEY idx_site_activity_fluxer_role_guild (guild_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))
    conn.commit()
    print("Created site_activity_fluxer_roles table.")
