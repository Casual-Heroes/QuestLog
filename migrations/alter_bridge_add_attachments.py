#!/usr/bin/env python3
# alter_bridge_add_attachments.py
# Adds attachments_json column to web_bridge_relay_queue for media relay support.
# Run once: python alter_bridge_add_attachments.py

import os
import sys

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from sqlalchemy import text
from app.db import get_engine

with get_engine().connect() as conn:
    conn.execute(text(
        "ALTER TABLE web_bridge_relay_queue "
        "ADD COLUMN attachments_json TEXT NULL AFTER reply_quote"
    ))
    conn.commit()

print("Done: added attachments_json to web_bridge_relay_queue")
