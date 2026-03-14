#!/usr/bin/env python3
"""Add thread support to bridge: thread_id on relay queue, web_bridge_thread_map table."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE web_bridge_relay_queue "
        "ADD COLUMN thread_id VARCHAR(255) NULL AFTER mentions_json"
    ))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_bridge_thread_map (
            id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            bridge_id INT NOT NULL,
            discord_thread_id VARCHAR(255) NULL,
            matrix_thread_event_id VARCHAR(255) NULL,
            created_at BIGINT NOT NULL,
            INDEX idx_thread_map_discord (discord_thread_id),
            INDEX idx_thread_map_matrix (matrix_thread_event_id),
            INDEX idx_thread_map_bridge (bridge_id),
            FOREIGN KEY (bridge_id) REFERENCES web_bridge_configs(id)
        )
    """))
    conn.commit()
    print("Done - thread_id column and web_bridge_thread_map table created")
