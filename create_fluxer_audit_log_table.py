#!/usr/bin/env python3
"""
Create web_fluxer_audit_log table for the Fluxer bot audit system.
Run with: chwebsiteprj/bin/python3 create_fluxer_audit_log_table.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_fluxer_audit_log (
            id              BIGINT AUTO_INCREMENT PRIMARY KEY,
            guild_id        VARCHAR(32)  NOT NULL,
            action          VARCHAR(64)  NOT NULL,
            action_category VARCHAR(32)  NOT NULL DEFAULT 'member',
            actor_id        VARCHAR(32)  NULL,
            actor_name      VARCHAR(128) NULL,
            target_id       VARCHAR(32)  NULL,
            target_name     VARCHAR(128) NULL,
            target_type     VARCHAR(32)  NULL,
            reason          TEXT         NULL,
            details         TEXT         NULL,
            created_at      BIGINT       NOT NULL,
            INDEX idx_guild_created (guild_id, created_at),
            INDEX idx_guild_action  (guild_id, action)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """))
    conn.commit()
    print("web_fluxer_audit_log table created (or already existed).")
