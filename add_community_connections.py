"""
Migration: add web_community_connections table (Connected Spaces feature).
Run with: chwebsiteprj/bin/python3 add_community_connections.py
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_community_connections (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            requester_id    INT NOT NULL,
            recipient_id    INT NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending',
            requested_by    INT NOT NULL,
            created_at      BIGINT NOT NULL,
            updated_at      BIGINT NOT NULL,
            UNIQUE KEY uq_community_connection (requester_id, recipient_id),
            INDEX idx_conn_requester (requester_id, status),
            INDEX idx_conn_recipient (recipient_id, status),
            CONSTRAINT fk_conn_requester FOREIGN KEY (requester_id) REFERENCES web_communities(id) ON DELETE CASCADE,
            CONSTRAINT fk_conn_recipient FOREIGN KEY (recipient_id) REFERENCES web_communities(id) ON DELETE CASCADE,
            CONSTRAINT fk_conn_user FOREIGN KEY (requested_by) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    print('Created web_community_connections')
    conn.commit()
    print('Done.')
