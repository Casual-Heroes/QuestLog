#!/usr/bin/env python3
"""
Migration: add publish_to_network column to web_fluxer_lfg_config.
Run once: python3 alter_lfg_config_add_publish_to_network.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
import django; django.setup()

from sqlalchemy import text
from app.db import get_db_session

with get_db_session() as db:
    db.execute(text("""
        ALTER TABLE web_fluxer_lfg_config
        ADD COLUMN IF NOT EXISTS publish_to_network TINYINT NOT NULL DEFAULT 0
    """))
    db.commit()
    print("Migration complete: publish_to_network added to web_fluxer_lfg_config")
