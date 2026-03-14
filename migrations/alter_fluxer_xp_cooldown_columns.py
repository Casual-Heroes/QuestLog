"""Add xp_media_cooldown_secs and xp_reaction_cooldown_secs to web_fluxer_guild_settings."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    for col, default in [
        ('xp_media_cooldown_secs', 60),
        ('xp_reaction_cooldown_secs', 60),
    ]:
        try:
            conn.execute(text(
                f"ALTER TABLE web_fluxer_guild_settings "
                f"ADD COLUMN {col} INT NOT NULL DEFAULT {default}"
            ))
            conn.commit()
            print(f"Added {col}")
        except Exception as e:
            if 'Duplicate column' in str(e):
                print(f"{col} already exists")
            else:
                raise

print("Done.")
