"""
Migration: add ticker opt-out columns to web_users
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_users_add_ticker_prefs.py
"""
from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    for col, default in [
        ('ticker_show_live',    1),
        ('ticker_show_playing', 1),
        ('ticker_show_posts',   1),
        ('ticker_show_follows', 1),
        ('ticker_show_lfg',     1),
    ]:
        conn.execute(text(
            f"ALTER TABLE web_users ADD COLUMN IF NOT EXISTS {col} TINYINT(1) NOT NULL DEFAULT {default}"
        ))
    conn.commit()
    print("Done: ticker opt-out columns added to web_users")
