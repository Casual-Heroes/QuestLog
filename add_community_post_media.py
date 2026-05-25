"""
Migration: add media_url, media_type, game_tag_name, game_tag_steam_id to web_community_posts.
Also relax content to nullable (posts can be media-only).
Run with: chwebsiteprj/bin/python3 add_community_post_media.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    for col, defn in [
        ('media_url',          'VARCHAR(500) NULL'),
        ('media_type',         'VARCHAR(20) NULL'),
        ('game_tag_name',      'VARCHAR(200) NULL'),
        ('game_tag_steam_id',  'INT NULL'),
    ]:
        try:
            conn.execute(text(f'ALTER TABLE web_community_posts ADD COLUMN {col} {defn}'))
            print(f'Added web_community_posts.{col}')
        except Exception as e:
            print(f'Skipped {col}: {e}')

    # Allow content to be nullable (media-only posts)
    try:
        conn.execute(text('ALTER TABLE web_community_posts MODIFY COLUMN content TEXT NULL'))
        print('Made content nullable')
    except Exception as e:
        print(f'Skipped content nullable: {e}')

    conn.commit()
    print('Done.')
