"""
Migration: change guild_game from VARCHAR(50) to TEXT (JSON array support)
Run: chwebsiteprj/bin/python3 alter_community_guild_game.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

with get_engine().connect() as conn:
    conn.execute(sa_text(
        "ALTER TABLE web_communities MODIFY COLUMN guild_game TEXT NULL DEFAULT NULL"
    ))
    conn.commit()
    print("Done: guild_game changed to TEXT")
