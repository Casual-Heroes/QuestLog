#!/usr/bin/env python3
"""Migration: add stream_schedule and stream_timezone to web_creator_profiles."""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    try:
        conn.execute(sa_text(
            "ALTER TABLE web_creator_profiles ADD COLUMN stream_schedule MEDIUMTEXT NULL AFTER show_steam_on_profile"
        ))
        print("Added stream_schedule column.")
    except Exception as e:
        print(f"stream_schedule: {e}")
    try:
        conn.execute(sa_text(
            "ALTER TABLE web_creator_profiles ADD COLUMN stream_timezone VARCHAR(50) NULL AFTER stream_schedule"
        ))
        print("Added stream_timezone column.")
    except Exception as e:
        print(f"stream_timezone: {e}")
    conn.commit()
print("Done.")
