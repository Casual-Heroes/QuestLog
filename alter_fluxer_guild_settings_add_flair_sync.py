"""Add flair_sync_enabled to web_fluxer_guild_settings (opt-in, default 0)."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE web_fluxer_guild_settings "
        "ADD COLUMN flair_sync_enabled SMALLINT NOT NULL DEFAULT 0"
    ))
    conn.commit()
    print("Done: flair_sync_enabled added (default 0 = opt-in required)")
