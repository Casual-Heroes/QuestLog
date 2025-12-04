#!/usr/bin/env python3
"""
Migration script to add guild_modules table for modular pricing system.
Run this to create the new table in the database.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine, get_db_session
from app.models import Base, GuildModule
from sqlalchemy import text


def create_guild_modules_table():
    """Create the guild_modules table."""
    print("Creating guild_modules table...")

    try:
        # Get the database engine
        engine = get_engine()

        # Create the table using SQLAlchemy
        GuildModule.__table__.create(engine, checkfirst=True)
        print("✓ guild_modules table created successfully!")
        return True
    except Exception as e:
        print(f"✗ Error creating table: {e}")
        return False


def verify_table():
    """Verify the table was created correctly."""
    print("\nVerifying table structure...")

    try:
        with get_db_session() as db:
            # Try to query the table
            result = db.execute(text("SELECT COUNT(*) FROM guild_modules")).scalar()
            print(f"✓ Table verified! Current row count: {result}")

            # Show table structure (MySQL syntax)
            columns = db.execute(text("SHOW COLUMNS FROM guild_modules")).fetchall()
            print("\nTable columns:")
            for col in columns:
                # MySQL returns: (Field, Type, Null, Key, Default, Extra)
                print(f"  - {col[0]} ({col[1]})")

            return True
    except Exception as e:
        print(f"✗ Error verifying table: {e}")
        return False


def grant_free_modules_to_existing_guilds():
    """Grant basic free modules to all existing guilds."""
    print("\nGranting free tier modules to existing guilds...")

    try:
        from app.models import Guild
        import time

        free_modules = ['reaction_roles', 'xp', 'templates']  # Free tier gets limited versions

        with get_db_session() as db:
            guilds = db.query(Guild).all()
            print(f"Found {len(guilds)} guilds")

            for guild in guilds:
                # Skip if already has modules
                existing = db.query(GuildModule).filter_by(guild_id=guild.guild_id).count()
                if existing > 0:
                    print(f"  - Guild {guild.guild_id} already has modules, skipping")
                    continue

                # Grant free modules
                for module_name in free_modules:
                    module = GuildModule(
                        guild_id=guild.guild_id,
                        module_name=module_name,
                        enabled=True,
                        expires_at=None,  # Free tier doesn't expire
                        activated_at=int(time.time())
                    )
                    db.add(module)

                print(f"  ✓ Granted free modules to guild {guild.guild_id}")

            db.commit()
            print(f"\n✓ Free modules granted to {len(guilds)} guilds!")
            return True
    except Exception as e:
        print(f"✗ Error granting free modules: {e}")
        return False


def main():
    """Main migration function."""
    print("=" * 60)
    print("Warden Bot - Guild Modules Table Migration")
    print("=" * 60)
    print()

    # Step 1: Create table
    if not create_guild_modules_table():
        print("\n❌ Migration failed at table creation!")
        sys.exit(1)

    # Step 2: Verify table
    if not verify_table():
        print("\n⚠️  Table created but verification failed!")
        sys.exit(1)

    # Step 3: Grant free modules to existing guilds
    print("\nDo you want to grant free tier modules to existing guilds? (y/n): ", end='')
    response = input().strip().lower()

    if response == 'y':
        if not grant_free_modules_to_existing_guilds():
            print("\n⚠️  Failed to grant free modules, but table is ready!")
        else:
            print("\n✅ Migration completed successfully!")
    else:
        print("\nSkipping free module grants.")
        print("\n✅ Migration completed successfully!")

    print()
    print("=" * 60)
    print("Next steps:")
    print("1. Restart your Django/Gunicorn server")
    print("2. Set up Stripe integration")
    print("3. Create billing page")
    print("=" * 60)


if __name__ == "__main__":
    main()
