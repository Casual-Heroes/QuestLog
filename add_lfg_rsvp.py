"""
Migration: add rsvp_going/rsvp_maybe to web_lfg_groups + create web_lfg_group_rsvps table
Run: chwebsiteprj/bin/python3 add_lfg_rsvp.py
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
sys.path.insert(0, '/srv/ch-webserver')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()
with engine.connect() as conn:
    # Add rsvp columns to web_lfg_groups
    for col, definition in [
        ('rsvp_going', 'INT NOT NULL DEFAULT 0'),
        ('rsvp_maybe', 'INT NOT NULL DEFAULT 0'),
    ]:
        try:
            conn.execute(sa_text(f"ALTER TABLE web_lfg_groups ADD COLUMN {col} {definition}"))
            conn.commit()
            print(f"Added {col} column.")
        except Exception as e:
            if 'Duplicate column' in str(e):
                print(f"{col} already exists, skipping.")
            else:
                raise

    # Create web_lfg_group_rsvps table
    try:
        conn.execute(sa_text("""
            CREATE TABLE web_lfg_group_rsvps (
                id INT AUTO_INCREMENT PRIMARY KEY,
                group_id INT NOT NULL,
                user_id INT NOT NULL,
                status VARCHAR(20) NOT NULL,
                created_at BIGINT NOT NULL,
                UNIQUE KEY uq_lfg_group_rsvp (group_id, user_id),
                KEY idx_lfg_rsvp_group (group_id),
                CONSTRAINT fk_lfg_rsvp_group FOREIGN KEY (group_id)
                    REFERENCES web_lfg_groups(id) ON DELETE CASCADE,
                CONSTRAINT fk_lfg_rsvp_user FOREIGN KEY (user_id)
                    REFERENCES web_users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """))
        conn.commit()
        print("Created web_lfg_group_rsvps table.")
    except Exception as e:
        if "already exists" in str(e):
            print("web_lfg_group_rsvps already exists, skipping.")
        else:
            raise

print("Done.")
