#!/usr/bin/env python3
# alter_add_go_live_webhook.py
# Run once: chwebsiteprj/bin/python3 alter_add_go_live_webhook.py

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
    now = int(time.time())
    conn.execute(text("""
        INSERT IGNORE INTO web_fluxer_webhook_configs
            (event_type, label, webhook_url, is_enabled, created_at, updated_at)
        VALUES ('go_live', 'Go Live', NULL, 0, :now, :now)
    """), {"now": now})
    conn.commit()
    print("web_fluxer_webhook_configs - go_live row seeded OK")
