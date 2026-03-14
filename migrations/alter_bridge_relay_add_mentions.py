#!/usr/bin/env python3
"""Add mentions_json column to web_bridge_relay_queue."""
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
        "ADD COLUMN mentions_json TEXT NULL AFTER attachments_json"
    ))
    conn.commit()
    print("Done - mentions_json column added")
