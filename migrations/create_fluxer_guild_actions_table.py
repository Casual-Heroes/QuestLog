#!/usr/bin/env python3
# create_fluxer_guild_actions_table.py
# Creates web_fluxer_guild_actions table for dashboard-initiated bot actions.
# Run once: python3 create_fluxer_guild_actions_table.py

import os
import sys

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from sqlalchemy import text
from app.db import get_engine

DDL = """
CREATE TABLE IF NOT EXISTS web_fluxer_guild_actions (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    guild_id      VARCHAR(25)  NOT NULL,
    action_type   VARCHAR(30)  NOT NULL,
    payload_json  TEXT         NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'pending',
    created_at    BIGINT       NOT NULL,
    processed_at  BIGINT       NULL,
    result_json   TEXT         NULL,
    INDEX idx_guild_action_pending (guild_id, status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with get_engine().connect() as conn:
    conn.execute(text(DDL))
    conn.commit()

print("Done: created web_fluxer_guild_actions table")
