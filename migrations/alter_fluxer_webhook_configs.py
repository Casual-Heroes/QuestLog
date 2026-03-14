#!/usr/bin/env python3
# alter_fluxer_webhook_configs.py
# Run once: chwebsiteprj/bin/python3 alter_fluxer_webhook_configs.py

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    # Add guild_id, channel_id, channel_name, embed_color to web_fluxer_webhook_configs
    # Each ALTER is wrapped so partial runs don't fail the whole script
    alters = [
        ("guild_id",    "ALTER TABLE web_fluxer_webhook_configs ADD COLUMN guild_id VARCHAR(32) DEFAULT NULL AFTER is_enabled"),
        ("channel_id",  "ALTER TABLE web_fluxer_webhook_configs ADD COLUMN channel_id VARCHAR(32) DEFAULT NULL AFTER guild_id"),
        ("channel_name","ALTER TABLE web_fluxer_webhook_configs ADD COLUMN channel_name VARCHAR(200) DEFAULT NULL AFTER channel_id"),
        ("embed_color", "ALTER TABLE web_fluxer_webhook_configs ADD COLUMN embed_color VARCHAR(7) DEFAULT NULL AFTER channel_name"),
    ]
    for col, sql in alters:
        try:
            conn.execute(text(sql))
            print(f"  + Added column: {col}")
        except Exception as e:
            if "Duplicate column name" in str(e):
                print(f"  - Column already exists: {col}")
            else:
                raise
    conn.commit()
    print("web_fluxer_webhook_configs - OK")
