"""
Migration: Add source, claim_status, claim_user_id, claim_note to web_indie_games.
Run: chwebsiteprj/bin/python3 add_indie_claim_columns.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine

engine = get_engine()

with engine.connect() as conn:
    try:
        conn.execute(conn.connection.cursor().__class__.__mro__[0].__new__(conn.connection.cursor().__class__))
    except Exception:
        pass

    from sqlalchemy import text

    statements = [
        "ALTER TABLE web_indie_games ADD COLUMN source VARCHAR(20) NULL DEFAULT 'ch_spotlight' AFTER submission_note",
        "ALTER TABLE web_indie_games ADD COLUMN claim_status VARCHAR(20) NULL AFTER source",
        "ALTER TABLE web_indie_games ADD COLUMN claim_user_id INT NULL AFTER claim_status",
        "ALTER TABLE web_indie_games ADD COLUMN claim_note TEXT NULL AFTER claim_user_id",
    ]

    for sql in statements:
        try:
            conn.execute(text(sql))
            print(f"OK: {sql[:80]}")
        except Exception as e:
            if 'Duplicate column name' in str(e):
                print(f"SKIP (already exists): {sql[:80]}")
            else:
                print(f"ERROR: {e}")
                raise

    conn.commit()
    print("Done.")
