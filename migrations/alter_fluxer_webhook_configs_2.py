#!/usr/bin/env python3
# alter_fluxer_webhook_configs_2.py
# Run once: chwebsiteprj/bin/python3 alter_fluxer_webhook_configs_2.py

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    alters = [
        ("message_template", "ALTER TABLE web_fluxer_webhook_configs ADD COLUMN message_template TEXT DEFAULT NULL AFTER embed_color"),
        ("embed_title",      "ALTER TABLE web_fluxer_webhook_configs ADD COLUMN embed_title VARCHAR(255) DEFAULT NULL AFTER message_template"),
        ("embed_footer",     "ALTER TABLE web_fluxer_webhook_configs ADD COLUMN embed_footer VARCHAR(255) DEFAULT NULL AFTER embed_title"),
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

    # Seed lfg_announce row if not already present
    now = int(time.time())
    conn.execute(text("""
        INSERT IGNORE INTO web_fluxer_webhook_configs
            (event_type, label, is_enabled, created_at, updated_at)
        VALUES ('lfg_announce', 'LFG Posted', 0, :now, :now)
    """), {"now": now})

    conn.commit()
    print("web_fluxer_webhook_configs - OK")
    print("Seeded: lfg_announce")
