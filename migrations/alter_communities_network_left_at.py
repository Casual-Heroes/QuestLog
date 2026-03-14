#!/usr/bin/env python3
# alter_communities_network_left_at.py
# Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_communities_network_left_at.py

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE web_communities ADD COLUMN network_left_at BIGINT NULL"))
        conn.commit()
        print("Added network_left_at column.")
    except Exception as e:
        if '1060' in str(e):  # Duplicate column
            print("Column already exists, skipping.")
        else:
            raise
