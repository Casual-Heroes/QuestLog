"""
Migration: Add Champion subscription perks columns to web_users.

  active_flair2_id  INT NULL  - second equipped flair slot (Champions only)
  show_as_champion  TINYINT(1) NOT NULL DEFAULT 0  - opt-in public Champions listing

Run with:
  chwebsiteprj/bin/python3 alter_users_champion_fields.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
with engine.connect() as conn:
    # Check if columns exist before adding
    cols = {row[0] for row in conn.execute(text("DESCRIBE web_users")).fetchall()}

    if 'active_flair2_id' not in cols:
        conn.execute(text(
            "ALTER TABLE web_users ADD COLUMN active_flair2_id INT NULL AFTER active_flair_id"
        ))
        print("Added active_flair2_id")
    else:
        print("active_flair2_id already exists - skipped")

    if 'show_as_champion' not in cols:
        conn.execute(text(
            "ALTER TABLE web_users ADD COLUMN show_as_champion TINYINT(1) NOT NULL DEFAULT 0 AFTER stripe_subscription_id"
        ))
        print("Added show_as_champion")
    else:
        print("show_as_champion already exists - skipped")

    conn.commit()

print("Done.")
