#!/usr/bin/env python3
"""
Migration: Add winners_announced column to raffles table
"""
import os
import sys

# Add project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
import django
django.setup()

from app.db import get_engine
from sqlalchemy import text

def add_winners_announced_column():
    """Add winners_announced column to raffles table."""
    engine = get_engine()

    print("Adding winners_announced column to raffles table...")

    try:
        with engine.connect() as conn:
            # Check if column already exists
            result = conn.execute(text("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE table_name = 'raffles'
                AND column_name = 'winners_announced'
                AND table_schema = DATABASE()
            """))
            exists = result.scalar() > 0

            if exists:
                print("✓ Column 'winners_announced' already exists")
                return True

            # Add the column
            conn.execute(text("""
                ALTER TABLE raffles
                ADD COLUMN winners_announced TINYINT(1) DEFAULT 0 AFTER winners
            """))
            conn.commit()

            print("✓ Column 'winners_announced' added successfully")
            return True

    except Exception as e:
        print(f"✗ Error adding column: {e}")
        return False

if __name__ == "__main__":
    print("="*60)
    print("Raffle Winners Announced Column Migration")
    print("="*60)

    success = add_winners_announced_column()

    if success:
        print("\n✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Restart the web server")
        print("2. Restart the Discord bot")
    else:
        print("\n⚠️  Migration failed!")
        sys.exit(1)
