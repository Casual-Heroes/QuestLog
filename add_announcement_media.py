import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()
from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    cols = conn.execute(text("SHOW COLUMNS FROM web_site_announcements")).fetchall()
    col_names = [c[0] for c in cols]
    if 'media_url' not in col_names:
        conn.execute(text("ALTER TABLE web_site_announcements ADD COLUMN media_url VARCHAR(500) NULL"))
        print("Added media_url")
    if 'media_type' not in col_names:
        conn.execute(text("ALTER TABLE web_site_announcements ADD COLUMN media_type VARCHAR(20) NULL"))
        print("Added media_type")
    if 'game_tag_name' not in col_names:
        conn.execute(text("ALTER TABLE web_site_announcements ADD COLUMN game_tag_name VARCHAR(200) NULL"))
        print("Added game_tag_name")
    if 'game_tag_steam_id' not in col_names:
        conn.execute(text("ALTER TABLE web_site_announcements ADD COLUMN game_tag_steam_id INT NULL"))
        print("Added game_tag_steam_id")
    conn.commit()
    print("Done")
