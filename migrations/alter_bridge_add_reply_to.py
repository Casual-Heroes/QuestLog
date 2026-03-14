import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()
from app.db import get_engine
from sqlalchemy import text

with get_engine().connect() as conn:
    conn.execute(text("""
        ALTER TABLE web_bridge_relay_queue
        ADD COLUMN reply_to_source_message_id VARCHAR(255) NULL DEFAULT NULL
        AFTER reply_quote
    """))
    conn.commit()
    print("Done - added reply_to_source_message_id to web_bridge_relay_queue")
