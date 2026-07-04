"""Add admin_only column to web_flairs."""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    try:
        conn.execute(text('ALTER TABLE web_flairs ADD COLUMN admin_only TINYINT NOT NULL DEFAULT 0'))
        conn.commit()
        print('Added admin_only to web_flairs')
    except Exception as e:
        if 'Duplicate column' in str(e):
            print('Already exists: admin_only')
        else:
            raise

print('Done.')
