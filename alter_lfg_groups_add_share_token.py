#!/usr/bin/env python3
"""
Add share_token column to web_lfg_groups and backfill existing rows.
Run with: chwebsiteprj/bin/python3 alter_lfg_groups_add_share_token.py
"""
import os
import sys
import secrets
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text

_CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

def generate_token():
    return ''.join(secrets.choice(_CHARS) for _ in range(8))

engine = get_engine()
with engine.connect() as conn:
    # Add the column (ignore if already exists)
    try:
        conn.execute(text(
            "ALTER TABLE web_lfg_groups ADD COLUMN share_token VARCHAR(8) NULL UNIQUE AFTER completed_at"
        ))
        conn.commit()
        print("Column share_token added.")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("Column share_token already exists, skipping ALTER.")
        else:
            raise

    # Backfill existing rows that have no token
    rows = conn.execute(text("SELECT id FROM web_lfg_groups WHERE share_token IS NULL")).fetchall()
    print(f"Backfilling {len(rows)} rows...")
    for (row_id,) in rows:
        while True:
            token = generate_token()
            exists = conn.execute(text("SELECT 1 FROM web_lfg_groups WHERE share_token=:t LIMIT 1"), {"t": token}).fetchone()
            if not exists:
                break
        conn.execute(text("UPDATE web_lfg_groups SET share_token=:t WHERE id=:id"), {"t": token, "id": row_id})
    conn.commit()
    print(f"Done: {len(rows)} rows backfilled with share tokens.")
