"""
Migration: Add Fluxer, Kloak, Stoat platform types; migrate revolt → stoat
Run once: python create_platform_types_update.py
"""
import os
import sys
import django

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

with engine.connect() as conn:
    # Step 1: Expand the ENUM to include all old + new values (including revolt for safe migration)
    print("Step 1: Expanding ENUM to include new platform types...")
    conn.execute(text("""
        ALTER TABLE web_communities
        MODIFY platform ENUM(
            'discord','revolt','teamspeak','matrix','guilded','mumble','root',
            'fluxer','kloak','stoat','other'
        ) NOT NULL DEFAULT 'discord'
    """))
    conn.commit()
    print("  Done.")

    # Step 2: Migrate any existing 'revolt' records to 'stoat'
    result = conn.execute(text("SELECT COUNT(*) FROM web_communities WHERE platform = 'revolt'"))
    revolt_count = result.scalar()
    print(f"Step 2: Migrating {revolt_count} revolt communities to stoat...")
    if revolt_count:
        conn.execute(text("UPDATE web_communities SET platform = 'stoat' WHERE platform = 'revolt'"))
        conn.commit()
    print("  Done.")

    # Step 3: Remove 'revolt' from the ENUM now that it's empty
    print("Step 3: Removing 'revolt' from ENUM...")
    conn.execute(text("""
        ALTER TABLE web_communities
        MODIFY platform ENUM(
            'discord','teamspeak','matrix','guilded','mumble','root',
            'fluxer','kloak','stoat','other'
        ) NOT NULL DEFAULT 'discord'
    """))
    conn.commit()
    print("  Done.")

print("\nMigration complete.")
