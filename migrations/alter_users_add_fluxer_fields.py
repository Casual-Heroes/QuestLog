#!/usr/bin/env python3
# alter_users_add_fluxer_fields.py
# Adds fluxer_id and fluxer_username to web_users for Fluxer OAuth account linking.
# Run once: python3 alter_users_add_fluxer_fields.py

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    # Add fluxer_id (unique, indexed - like discord_id)
    try:
        conn.execute(text(
            "ALTER TABLE web_users "
            "ADD COLUMN fluxer_id VARCHAR(50) NULL DEFAULT NULL UNIQUE AFTER discord_username"
        ))
        print("fluxer_id column added")
    except Exception as e:
        if "Duplicate column" in str(e) or "already exists" in str(e).lower():
            print("fluxer_id already exists - skipping")
        else:
            raise

    # Add fluxer_username
    try:
        conn.execute(text(
            "ALTER TABLE web_users "
            "ADD COLUMN fluxer_username VARCHAR(100) NULL DEFAULT NULL AFTER fluxer_id"
        ))
        print("fluxer_username column added")
    except Exception as e:
        if "Duplicate column" in str(e) or "already exists" in str(e).lower():
            print("fluxer_username already exists - skipping")
        else:
            raise

    # Index on fluxer_id for fast lookup
    try:
        conn.execute(text(
            "CREATE INDEX idx_web_users_fluxer_id ON web_users (fluxer_id)"
        ))
        print("fluxer_id index created")
    except Exception as e:
        if "Duplicate key name" in str(e) or "already exists" in str(e).lower():
            print("fluxer_id index already exists - skipping")
        else:
            raise

    conn.commit()
    print("Done.")
