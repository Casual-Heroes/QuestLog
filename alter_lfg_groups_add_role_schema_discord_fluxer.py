"""
Migration: add role_schema to lfg_groups (Discord) and
role_schema + tanks/healers/dps/support to web_fluxer_lfg_groups (Fluxer).
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    # ── Discord lfg_groups ────────────────────────────────────────────────────
    row = conn.execute(text(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='lfg_groups' AND COLUMN_NAME='role_schema'"
    )).scalar()
    if row == 0:
        conn.execute(text(
            "ALTER TABLE lfg_groups ADD COLUMN role_schema TEXT NULL AFTER support_needed"
        ))
        print("Added role_schema to lfg_groups")
    else:
        print("lfg_groups.role_schema already exists")

    # ── Fluxer web_fluxer_lfg_groups ─────────────────────────────────────────
    for col, defn in [
        ('tanks_needed',   'INT NOT NULL DEFAULT 0'),
        ('healers_needed', 'INT NOT NULL DEFAULT 0'),
        ('dps_needed',     'INT NOT NULL DEFAULT 0'),
        ('support_needed', 'INT NOT NULL DEFAULT 0'),
        ('role_schema',    'TEXT NULL'),
        ('enforce_role_limits', 'TINYINT(1) NOT NULL DEFAULT 1'),
    ]:
        exists = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='web_fluxer_lfg_groups' AND COLUMN_NAME=:c"
        ), {'c': col}).scalar()
        if exists == 0:
            conn.execute(text(f"ALTER TABLE web_fluxer_lfg_groups ADD COLUMN {col} {defn}"))
            print(f"Added {col} to web_fluxer_lfg_groups")
        else:
            print(f"web_fluxer_lfg_groups.{col} already exists")

    conn.commit()

print("Done.")
