"""
Migration: create web_fluxer_guild_templates table
Run: chwebsiteprj/bin/python3 create_fluxer_templates_table.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS web_fluxer_guild_templates (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            guild_id        VARCHAR(32) NOT NULL,
            template_type   VARCHAR(10) NOT NULL,
            name            VARCHAR(100) NOT NULL,
            description     VARCHAR(500) DEFAULT NULL,
            template_data   LONGTEXT NOT NULL,
            use_count       INT NOT NULL DEFAULT 0,
            created_by      INT DEFAULT NULL,
            created_at      BIGINT NOT NULL,
            updated_at      BIGINT NOT NULL,
            INDEX idx_fluxer_template_guild (guild_id),
            INDEX idx_fluxer_template_type  (guild_id, template_type)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("Created web_fluxer_guild_templates table.")
