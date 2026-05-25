"""Migration: add media_url, media_type, admin_note to web_site_feedback."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.begin() as conn:
    for col, defn in [
        ('media_url',  "VARCHAR(500) NULL"),
        ('media_type', "VARCHAR(20) NULL"),
        ('admin_note', "TEXT NULL"),
    ]:
        try:
            conn.execute(text(f"ALTER TABLE web_site_feedback ADD COLUMN {col} {defn}"))
            print(f"Added {col}")
        except Exception as e:
            if 'Duplicate column' in str(e):
                print(f"{col} already exists")
            else:
                raise
print("Done.")
