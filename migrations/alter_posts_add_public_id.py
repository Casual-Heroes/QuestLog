#!/usr/bin/env python3
"""
Add public_id column to web_posts for non-sequential public URLs.

Run: chwebsiteprj/bin/python3 migrations/alter_posts_add_public_id.py
"""
import os
import sys
import django

sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

import secrets
from sqlalchemy import text
from app.db import get_engine

CHARS = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

def gen_id():
    return ''.join(secrets.choice(CHARS) for _ in range(8))

engine = get_engine()
with engine.connect() as conn:
    # Add column if missing
    conn.execute(text("""
        ALTER TABLE web_posts
        ADD COLUMN IF NOT EXISTS public_id VARCHAR(12) NULL UNIQUE
    """))
    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_web_posts_public_id ON web_posts (public_id)"))
    conn.commit()
    print("Column added.")

    # Backfill existing posts
    rows = conn.execute(text("SELECT id FROM web_posts WHERE public_id IS NULL")).fetchall()
    print(f"Backfilling {len(rows)} posts...")
    for row in rows:
        while True:
            pid = gen_id()
            exists = conn.execute(text("SELECT 1 FROM web_posts WHERE public_id = :p"), {'p': pid}).fetchone()
            if not exists:
                break
        conn.execute(text("UPDATE web_posts SET public_id = :p WHERE id = :id"), {'p': pid, 'id': row[0]})
    conn.commit()
    print("Done.")
