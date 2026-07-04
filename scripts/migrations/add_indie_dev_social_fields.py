"""Add TikTok, Instagram, Facebook, Bluesky, Kick fields to web_indie_games."""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
cols = [
    ('dev_tiktok_url',    'VARCHAR(500)'),
    ('dev_instagram_url', 'VARCHAR(500)'),
    ('dev_facebook_url',  'VARCHAR(500)'),
    ('dev_bsky_url',      'VARCHAR(500)'),
    ('dev_kick_url',      'VARCHAR(500)'),
]

with engine.connect() as conn:
    for col, dtype in cols:
        try:
            conn.execute(text(f'ALTER TABLE web_indie_games ADD COLUMN {col} {dtype} NULL'))
            conn.commit()
            print(f'Added {col}')
        except Exception as e:
            if 'Duplicate column' in str(e):
                print(f'Already exists: {col}')
            else:
                raise

print('Done.')
