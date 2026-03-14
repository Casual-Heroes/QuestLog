#!/usr/bin/env python3
# alter_fluxer_guild_channels.py
# Run once: chwebsiteprj/bin/python3 alter_fluxer_guild_channels.py

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
    try:
        conn.execute(text(
            "ALTER TABLE web_fluxer_guild_channels "
            "ADD COLUMN guild_name VARCHAR(200) NOT NULL DEFAULT '' AFTER guild_id"
        ))
        print("  + Added column: guild_name")
    except Exception as e:
        if "Duplicate column name" in str(e):
            print("  - Column already exists: guild_name")
        else:
            raise
    conn.commit()
    print("web_fluxer_guild_channels - OK")
