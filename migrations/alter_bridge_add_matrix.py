"""
Migration: Add Matrix columns to bridge tables and widen ID columns for Matrix IDs.

Run with:
  source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_bridge_add_matrix.py
"""
import sys
import os
sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

MIGRATIONS = [
    # WebBridgeConfig: add Matrix columns, make discord/fluxer columns nullable
    "ALTER TABLE web_bridge_configs ADD COLUMN IF NOT EXISTS matrix_space_id VARCHAR(255) NULL AFTER fluxer_channel_id",
    "ALTER TABLE web_bridge_configs ADD COLUMN IF NOT EXISTS matrix_room_id VARCHAR(255) NULL AFTER matrix_space_id",
    "ALTER TABLE web_bridge_configs ADD COLUMN IF NOT EXISTS relay_matrix_outbound TINYINT NOT NULL DEFAULT 1 AFTER relay_fluxer_to_discord",
    "ALTER TABLE web_bridge_configs ADD COLUMN IF NOT EXISTS relay_matrix_inbound TINYINT NOT NULL DEFAULT 1 AFTER relay_matrix_outbound",
    "ALTER TABLE web_bridge_configs MODIFY COLUMN discord_guild_id VARCHAR(20) NULL",
    "ALTER TABLE web_bridge_configs MODIFY COLUMN discord_channel_id VARCHAR(20) NULL",
    "ALTER TABLE web_bridge_configs MODIFY COLUMN fluxer_guild_id VARCHAR(20) NULL",
    "ALTER TABLE web_bridge_configs MODIFY COLUMN fluxer_channel_id VARCHAR(20) NULL",
    # Add index on matrix_room_id
    "ALTER TABLE web_bridge_configs ADD INDEX idx_bridge_matrix_room (matrix_room_id)",
    # WebBridgeRelayQueue: widen source_message_id and target_channel_id for Matrix IDs
    "ALTER TABLE web_bridge_relay_queue MODIFY COLUMN source_message_id VARCHAR(255) NULL",
    "ALTER TABLE web_bridge_relay_queue MODIFY COLUMN target_channel_id VARCHAR(255) NOT NULL",
    # WebBridgeMessageMap: widen message_id and channel_id
    "ALTER TABLE web_bridge_message_map MODIFY COLUMN message_id VARCHAR(255) NOT NULL",
    "ALTER TABLE web_bridge_message_map MODIFY COLUMN channel_id VARCHAR(255) NOT NULL",
    # WebBridgePendingReaction: widen target IDs
    "ALTER TABLE web_bridge_pending_reactions MODIFY COLUMN target_message_id VARCHAR(255) NOT NULL",
    "ALTER TABLE web_bridge_pending_reactions MODIFY COLUMN target_channel_id VARCHAR(255) NOT NULL",
    # WebBridgePendingDeletion: widen target IDs
    "ALTER TABLE web_bridge_pending_deletions MODIFY COLUMN target_message_id VARCHAR(255) NOT NULL",
    "ALTER TABLE web_bridge_pending_deletions MODIFY COLUMN target_channel_id VARCHAR(255) NOT NULL",
]

with engine.connect() as conn:
    for sql in MIGRATIONS:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"OK: {sql[:80]}")
        except Exception as e:
            if 'Duplicate key name' in str(e) or 'Duplicate column name' in str(e):
                print(f"SKIP (already exists): {sql[:80]}")
            else:
                print(f"ERROR: {e}")
                print(f"  SQL: {sql}")

print("Migration complete.")
