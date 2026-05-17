"""
Migration: add guild_game and guild_game_name to web_communities
Run: chwebsiteprj/bin/python3 add_community_guild_fields.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

with get_engine().connect() as conn:
    conn.execute(sa_text(
        "ALTER TABLE web_communities "
        "ADD COLUMN guild_game VARCHAR(50) NULL DEFAULT NULL, "
        "ADD COLUMN guild_game_name VARCHAR(200) NULL DEFAULT NULL"
    ))
    conn.commit()
    print("Done: guild_game and guild_game_name added to web_communities")
