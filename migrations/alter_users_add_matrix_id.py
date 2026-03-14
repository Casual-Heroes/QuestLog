"""
Migration: add matrix_id and matrix_username columns to web_users
Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_users_add_matrix_id.py
"""
from sqlalchemy import text
from app.db import get_engine

engine = get_engine()
with engine.connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_users
        ADD COLUMN IF NOT EXISTS matrix_id VARCHAR(100) DEFAULT NULL,
        ADD COLUMN IF NOT EXISTS matrix_username VARCHAR(100) DEFAULT NULL
    """))
    conn.execute(text("""
        ALTER TABLE web_users
        ADD UNIQUE INDEX IF NOT EXISTS uq_web_users_matrix_id (matrix_id)
    """))
    conn.commit()
    print("Done: matrix_id and matrix_username added to web_users")
