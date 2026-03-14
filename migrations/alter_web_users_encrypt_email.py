#!/usr/bin/env python3
"""
Migration: Encrypt web_users.email at rest.

Renames `email` column to `email_enc`, drops the unique index (uniqueness
is enforced by auth_user.email), and Fernet-encrypts all existing values.

Run once:
  source /srv/ch-webserver/chwebsiteprj/bin/activate
  python3 alter_web_users_encrypt_email.py
"""
import sys, os
sys.path.insert(0, '/srv/ch-webserver')
os.environ['DJANGO_SETTINGS_MODULE'] = 'casualsite.settings'
import django; django.setup()

from sqlalchemy import text
from app.db import get_engine
from app.utils.encryption import encrypt_token

engine = get_engine()

with engine.connect() as conn:
    # 1. Add the new encrypted column
    print("Step 1: Adding email_enc column...")
    conn.execute(text(
        "ALTER TABLE web_users ADD COLUMN email_enc TEXT NULL AFTER email"
    ))
    conn.commit()

    # 2. Encrypt existing values into email_enc
    print("Step 2: Encrypting existing emails...")
    rows = conn.execute(text("SELECT id, email FROM web_users WHERE email IS NOT NULL")).fetchall()
    updated = 0
    for row in rows:
        try:
            enc = encrypt_token(row.email.strip().lower())
            conn.execute(text("UPDATE web_users SET email_enc = :enc WHERE id = :id"),
                         {'enc': enc, 'id': row.id})
            updated += 1
        except Exception as e:
            print(f"  WARNING: Could not encrypt email for user id={row.id}: {e}")
    conn.commit()
    print(f"  Encrypted {updated} email(s).")

    # 3. Drop the old email column (and its unique index with it)
    print("Step 3: Dropping old plaintext email column...")
    conn.execute(text("ALTER TABLE web_users DROP COLUMN email"))
    conn.commit()

    print("\nMigration complete.")
    print("  web_users.email      -> DROPPED")
    print("  web_users.email_enc  -> Fernet-encrypted TEXT")
    print("\nReboot the web service to apply the model change.")
