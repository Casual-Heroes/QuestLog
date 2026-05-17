import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    try:
        conn.execute(sa_text(
            "ALTER TABLE web_users ADD COLUMN share_steam_library BOOLEAN NOT NULL DEFAULT 0"
        ))
        conn.commit()
        print("OK: share_steam_library added")
    except Exception as e:
        if 'Duplicate column' in str(e):
            print("Already exists, skipping")
        else:
            raise
