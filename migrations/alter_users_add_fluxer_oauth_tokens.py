"""
Migration: Add Fluxer OAuth token storage + custom status sync opt-in to web_users.
Run: chwebsiteprj/bin/python3 alter_users_add_fluxer_oauth_tokens.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    for sql in [
        "ALTER TABLE web_users ADD COLUMN IF NOT EXISTS fluxer_sync_custom_status TINYINT(1) NOT NULL DEFAULT 0",
        "ALTER TABLE web_users ADD COLUMN IF NOT EXISTS fluxer_access_token_enc TEXT DEFAULT NULL",
        "ALTER TABLE web_users ADD COLUMN IF NOT EXISTS fluxer_refresh_token_enc TEXT DEFAULT NULL",
        "ALTER TABLE web_users ADD COLUMN IF NOT EXISTS fluxer_token_expires_at BIGINT DEFAULT NULL",
    ]:
        try:
            conn.execute(text(sql))
            print(f"OK: {sql[:80]}")
        except Exception as e:
            print(f"SKIP: {e}")
    conn.commit()
print("Done.")
