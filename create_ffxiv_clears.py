"""Migration: create web_ffxiv_clears table."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

CREATE = """
CREATE TABLE IF NOT EXISTS web_ffxiv_clears (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    content_key VARCHAR(32) NOT NULL,
    cleared_at  BIGINT NOT NULL,
    UNIQUE KEY uq_ffxiv_clear (user_id, content_key),
    KEY idx_ffxiv_clears_user (user_id),
    CONSTRAINT fk_ffxiv_clears_user FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

with get_engine().connect() as conn:
    conn.execute(sa_text(CREATE))
    conn.commit()
    print("web_ffxiv_clears table created.")
