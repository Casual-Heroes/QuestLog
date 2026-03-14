"""
Migration: add current_game_appid column to web_users
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_users_add_current_game_appid.py
"""
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(__import__('sqlalchemy').text(
        "ALTER TABLE web_users ADD COLUMN IF NOT EXISTS current_game_appid INT NULL AFTER current_game"
    ))
    conn.commit()
    print("Done: current_game_appid added to web_users")
