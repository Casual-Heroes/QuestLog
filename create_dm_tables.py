"""
Migration: Create E2EE DM tables.
Run with: chwebsiteprj/bin/python3 create_dm_tables.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

MIGRATIONS = [
    # Add E2EE public key fields to web_users
    """
    ALTER TABLE web_users
        ADD COLUMN IF NOT EXISTS pubkey TEXT NULL COMMENT 'ECDH P-256 public key (JWK JSON, server stores only pubkey)',
        ADD COLUMN IF NOT EXISTS pubkey_encrypted TEXT NULL COMMENT 'AES-GCM encrypted private key backup (phrase-derived key)',
        ADD COLUMN IF NOT EXISTS pubkey_salt VARCHAR(64) NULL COMMENT 'Hex salt used to derive AES key from recovery phrase'
    """,

    # Conversations table - one row per unique user pair
    """
    CREATE TABLE IF NOT EXISTS web_dm_conversations (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        user_a_id       INT NOT NULL,
        user_b_id       INT NOT NULL,
        last_message_at BIGINT NOT NULL DEFAULT 0,
        created_at      BIGINT NOT NULL,
        UNIQUE KEY uq_convo (user_a_id, user_b_id),
        KEY idx_dm_convo_a (user_a_id),
        KEY idx_dm_convo_b (user_b_id),
        KEY idx_dm_convo_updated (last_message_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    # Messages table - ciphertext only, server never sees plaintext
    """
    CREATE TABLE IF NOT EXISTS web_dm_messages (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        conversation_id INT NOT NULL,
        sender_id       INT NOT NULL,
        -- AES-GCM ciphertext encrypted for recipient (base64)
        ciphertext_for_recipient TEXT NOT NULL,
        -- AES-GCM ciphertext encrypted for sender (sender's own copy)
        ciphertext_for_sender    TEXT NOT NULL,
        -- ECDH ephemeral public key used for this message (JWK JSON, base64)
        ephemeral_pubkey TEXT NOT NULL,
        -- AES-GCM IV for recipient copy (base64, 12 bytes)
        iv_recipient    VARCHAR(32) NOT NULL,
        -- AES-GCM IV for sender copy (base64, 12 bytes)
        iv_sender       VARCHAR(32) NOT NULL,
        is_deleted      TINYINT(1) NOT NULL DEFAULT 0,
        created_at      BIGINT NOT NULL,
        KEY idx_dm_msg_convo (conversation_id),
        KEY idx_dm_msg_sender (sender_id),
        KEY idx_dm_msg_created (created_at),
        CONSTRAINT fk_dm_msg_convo FOREIGN KEY (conversation_id) REFERENCES web_dm_conversations (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,

    # Unread counts - track last-read message per user per conversation
    """
    CREATE TABLE IF NOT EXISTS web_dm_read_state (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        conversation_id INT NOT NULL,
        user_id         INT NOT NULL,
        last_read_at    BIGINT NOT NULL DEFAULT 0,
        UNIQUE KEY uq_read_state (conversation_id, user_id),
        KEY idx_dm_read_user (user_id),
        CONSTRAINT fk_dm_read_convo FOREIGN KEY (conversation_id) REFERENCES web_dm_conversations (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]

with engine.connect() as conn:
    for sql in MIGRATIONS:
        try:
            conn.execute(text(sql.strip()))
            conn.commit()
            print(f"OK: {sql.strip()[:60]}...")
        except Exception as e:
            print(f"ERROR: {e}\nSQL: {sql.strip()[:80]}")

print("Done.")
