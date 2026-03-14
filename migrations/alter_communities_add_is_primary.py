#!/usr/bin/env python3
# alter_communities_add_is_primary.py
# Run: source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 alter_communities_add_is_primary.py

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    for sql, col in [
        ("ALTER TABLE web_communities ADD COLUMN is_primary TINYINT(1) NOT NULL DEFAULT 0", "is_primary"),
    ]:
        try:
            conn.execute(text(sql))
            conn.commit()
            print(f"  Added column: {col}")
        except Exception as e:
            if '1060' in str(e):
                print(f"  Already exists, skipping: {col}")
            else:
                print(f"  ERROR: {e}")
                raise

print("Done.")
