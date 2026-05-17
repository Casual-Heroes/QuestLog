"""Add discord_access_token_enc, discord_refresh_token_enc, discord_token_expires_at to web_users."""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_users
        ADD COLUMN IF NOT EXISTS discord_access_token_enc TEXT NULL AFTER fluxer_token_expires_at,
        ADD COLUMN IF NOT EXISTS discord_refresh_token_enc TEXT NULL AFTER discord_access_token_enc,
        ADD COLUMN IF NOT EXISTS discord_token_expires_at BIGINT NULL AFTER discord_refresh_token_enc
    """))
    conn.commit()
    print("Done - discord token columns added")
