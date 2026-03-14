"""
Migration: add origin_guild_id and origin_guild_name columns to web_lfg_groups
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_lfg_add_origin_guild.py
"""
from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_lfg_groups
        ADD COLUMN IF NOT EXISTS origin_guild_id VARCHAR(64) DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS origin_guild_name VARCHAR(200) DEFAULT NULL
    """))
    conn.commit()
    print("Done: origin_guild_id and origin_guild_name added to web_lfg_groups")
