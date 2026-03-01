"""
Migration: VIP User System
- Adds is_vip column to web_users
- Seeds the "Early Tester" VIP flair into web_flairs

Run once: python create_vip_column.py
"""
import os
import sys
import time
import django

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

with engine.connect() as conn:

    # 1. Add is_vip column to web_users
    print("Adding is_vip column to web_users...")
    try:
        conn.execute(text("""
            ALTER TABLE web_users
            ADD COLUMN is_vip TINYINT(1) NOT NULL DEFAULT 0
            AFTER is_disabled
        """))
        conn.commit()
        print("  Done.")
    except Exception as e:
        if 'Duplicate column' in str(e) or 'already exists' in str(e).lower():
            print("  Column already exists, skipping.")
        else:
            raise

    # 2. Seed the Early Tester VIP flair (idempotent — check by name)
    print("Seeding Early Tester VIP flair...")
    existing = conn.execute(text(
        "SELECT id FROM web_flairs WHERE name = 'Early Tester' LIMIT 1"
    )).fetchone()

    if existing:
        print(f"  Flair already exists (id={existing[0]}), skipping.")
    else:
        now = int(time.time())
        conn.execute(text("""
            INSERT INTO web_flairs
                (name, emoji, description, flair_type, hp_cost, enabled, display_order, created_at, updated_at)
            VALUES
                ('Early Tester', '⭐', 'Awarded to early testers who helped shape QuestLog.',
                 'exclusive', 0, 1, 0, :now, :now)
        """), {'now': now})
        conn.commit()
        row = conn.execute(text(
            "SELECT id FROM web_flairs WHERE name = 'Early Tester' LIMIT 1"
        )).fetchone()
        print(f"  Created Early Tester flair (id={row[0]}).")

print("\nMigration complete.")
