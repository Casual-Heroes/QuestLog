#!/usr/bin/env python3
# alter_creator_profiles_add_kick_instagram_facebook.py
# Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_creator_profiles_add_kick_instagram_facebook.py

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

columns = [
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_url VARCHAR(500) NULL", "kick_url"),
    ("ALTER TABLE web_creator_profiles ADD COLUMN facebook_url VARCHAR(500) NULL", "facebook_url"),
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_slug VARCHAR(100) NULL", "kick_slug"),
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_follower_count INT NOT NULL DEFAULT 0", "kick_follower_count"),
    ("ALTER TABLE web_creator_profiles ADD COLUMN kick_last_synced BIGINT NULL", "kick_last_synced"),
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
