"""Add dev submission fields to web_indie_games."""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
cols = [
    ('submission_status', 'VARCHAR(20) NULL'),
    ('submission_pitch',  'TEXT NULL'),
    ('submission_link',   'VARCHAR(500) NULL'),
    ('submission_note',   'TEXT NULL'),
    ('submitted_by',      'INT NULL'),
]

with engine.connect() as conn:
    for col, dtype in cols:
        try:
            conn.execute(text(f'ALTER TABLE web_indie_games ADD COLUMN {col} {dtype}'))
            conn.commit()
            print(f'Added {col}')
        except Exception as e:
            if 'Duplicate column' in str(e):
                print(f'Already exists: {col}')
            else:
                raise

print('Done.')
