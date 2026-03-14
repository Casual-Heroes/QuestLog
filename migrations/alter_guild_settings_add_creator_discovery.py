#!/usr/bin/env python3
"""Migration: add creator_discovery_json column to web_fluxer_guild_settings."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from sqlalchemy import text
from app.db import get_engine

SQL = "ALTER TABLE web_fluxer_guild_settings ADD COLUMN creator_discovery_json TEXT DEFAULT NULL"

engine = get_engine()
with engine.connect() as conn:
    try:
        conn.execute(text(SQL))
        conn.commit()
        print("Migration complete: creator_discovery_json added.")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("Column already exists, skipping.")
        else:
            print(f"Error: {e}")
            raise
