"""
Migration: add origin_platform and origin_group_id columns to web_lfg_groups
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_lfg_add_origin_columns.py
"""
from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_lfg_groups
        ADD COLUMN IF NOT EXISTS origin_platform VARCHAR(20) DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS origin_group_id INT DEFAULT NULL
    """))
    conn.commit()
    print("Done: origin_platform and origin_group_id added to web_lfg_groups")
