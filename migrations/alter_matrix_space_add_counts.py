#!/usr/bin/env python3
"""Add room_count and member_count columns to web_matrix_space_settings."""
import sys
import os
sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()  # triggers settings.py which loads /etc/casual-heroes/secrets.env via dotenv

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    for col, definition in [
        ('room_count',   'INT NOT NULL DEFAULT 0'),
        ('member_count', 'INT NOT NULL DEFAULT 0'),
    ]:
        try:
            conn.execute(text(
                f"ALTER TABLE web_matrix_space_settings ADD COLUMN {col} {definition}"
            ))
            conn.commit()
            print(f"Added {col}")
        except Exception as e:
            if '1060' in str(e) or 'Duplicate column' in str(e):
                print(f"{col} already exists - skipping")
            else:
                print(f"ERROR adding {col}: {e}")
                sys.exit(1)

print("Done.")
