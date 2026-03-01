"""
Migration: Steam Search Console + Schedule Columns
Adds fetch_interval, include_consoles to web_steam_search_configs
and igdb_id, igdb_url, console_platforms to web_found_games.
Run once: python create_steam_search_console_columns.py
"""
import os
import sys
import django

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

changes = [
    ('web_steam_search_configs', 'fetch_interval',    'INT NOT NULL DEFAULT 1440'),
    ('web_steam_search_configs', 'include_consoles',  'BOOLEAN NOT NULL DEFAULT FALSE'),
    ('web_found_games',          'igdb_id',           'INT NULL'),
    ('web_found_games',          'igdb_url',          'VARCHAR(500) NULL'),
    ('web_found_games',          'console_platforms', "TEXT NOT NULL DEFAULT '[]'"),
]

with engine.connect() as conn:
    for table, col, col_def in changes:
        try:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
            print(f"  + {table}.{col}")
        except Exception as e:
            if 'Duplicate column' in str(e) or 'already exists' in str(e).lower():
                print(f"  ~ {table}.{col} already exists, skipping")
            else:
                raise
    conn.execute(text("COMMIT"))

print("Done.")
