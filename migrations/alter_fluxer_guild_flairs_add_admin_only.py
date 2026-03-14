#!/usr/bin/env python3
"""
Migration: Add admin_only column to web_fluxer_guild_flairs.

Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_fluxer_guild_flairs_add_admin_only.py
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

with engine.connect() as conn:
    print("Adding admin_only column to web_fluxer_guild_flairs...")
    conn.execute(text("""
        ALTER TABLE web_fluxer_guild_flairs
            ADD COLUMN IF NOT EXISTS admin_only TINYINT NOT NULL DEFAULT 0
    """))
    conn.commit()
    print("Done.")
