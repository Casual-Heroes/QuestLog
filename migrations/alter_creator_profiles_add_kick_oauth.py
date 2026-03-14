#!/usr/bin/env python3
# alter_creator_profiles_add_kick_oauth.py
# Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_creator_profiles_add_kick_oauth.py

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

columns = [
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_user_id VARCHAR(100) NULL", "kick_user_id"),
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_display_name VARCHAR(100) NULL", "kick_display_name"),
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_access_token TEXT NULL", "kick_access_token"),
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_refresh_token TEXT NULL", "kick_refresh_token"),
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_token_expires BIGINT NULL", "kick_token_expires"),
]

with engine.connect() as conn:
    for sql, col in columns:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"  Added column: {col}")
        except Exception as e:
            if '1060' in str(e):
                print(f"  Already exists, skipping: {col}")
            else:
                print(f"  ERROR: {e}")
                raise

print("Done.")
