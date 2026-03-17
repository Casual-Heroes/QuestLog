#!/usr/bin/env python3
"""
Add role_schema column to web_lfg_groups.
Run with: chwebsiteprj/bin/python3 alter_lfg_groups_add_role_schema.py
"""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE web_lfg_groups ADD COLUMN role_schema TEXT NULL AFTER support_needed"
    ))
    conn.commit()
    print("Done: role_schema column added to web_lfg_groups.")
