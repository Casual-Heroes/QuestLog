"""
Migration: Server Rotation Voting Polls
Creates: web_server_polls, web_server_poll_options, web_server_poll_votes

Run once: python create_server_poll_tables.py
"""
import os
import sys
import django

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

with engine.connect() as conn:

    # --- web_server_polls ---
    print("Creating web_server_polls...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_server_polls (
            id                      INT AUTO_INCREMENT PRIMARY KEY,
            title                   VARCHAR(300) NOT NULL,
            description             TEXT,
            is_active               TINYINT(1) NOT NULL DEFAULT 0,
            is_ended                TINYINT(1) NOT NULL DEFAULT 0,
            show_results_before_end TINYINT(1) NOT NULL DEFAULT 1,
            ends_at                 BIGINT NULL,
            winner_option_id        INT NULL,
            created_by_id           INT NULL,
            created_at              BIGINT NOT NULL,
            updated_at              BIGINT NOT NULL,
            INDEX idx_polls_active (is_active, is_ended)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

    # --- web_server_poll_options ---
    print("Creating web_server_poll_options...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_server_poll_options (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            poll_id     INT NOT NULL,
            game_name   VARCHAR(300) NOT NULL,
            description TEXT,
            image_url   VARCHAR(500),
            steam_appid VARCHAR(50),
            sort_order  INT NOT NULL DEFAULT 0,
            vote_count  INT NOT NULL DEFAULT 0,
            created_at  BIGINT NOT NULL,
            INDEX idx_poll_options_poll (poll_id),
            FOREIGN KEY (poll_id) REFERENCES web_server_polls(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

    # --- web_server_poll_votes ---
    print("Creating web_server_poll_votes...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_server_poll_votes (
            id        INT AUTO_INCREMENT PRIMARY KEY,
            poll_id   INT NOT NULL,
            option_id INT NOT NULL,
            user_id   INT NOT NULL,
            created_at BIGINT NOT NULL,
            UNIQUE KEY uq_poll_user (poll_id, user_id),
            INDEX idx_poll_votes_option (option_id),
            FOREIGN KEY (poll_id)   REFERENCES web_server_polls(id)        ON DELETE CASCADE,
            FOREIGN KEY (option_id) REFERENCES web_server_poll_options(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id)   REFERENCES web_users(id)               ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

    # Add FK for winner_option_id now that options table exists
    print("Adding winner_option_id FK to web_server_polls...")
    try:
        conn.execute(text("""
            ALTER TABLE web_server_polls
            ADD CONSTRAINT fk_poll_winner
            FOREIGN KEY (winner_option_id) REFERENCES web_server_poll_options(id) ON DELETE SET NULL
        """))
        conn.commit()
        print("  Done.")
    except Exception as e:
        if 'Duplicate' in str(e) or 'already exists' in str(e).lower():
            print("  Already exists, skipping.")
        else:
            raise

print("\nMigration complete. Run: python manage.py run_server to apply.")
