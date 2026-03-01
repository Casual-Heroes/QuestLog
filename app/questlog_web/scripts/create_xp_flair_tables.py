"""
Migration: XP Events, Flairs, User Flairs, Rank Titles
Run once: python create_xp_flair_tables.py
"""
import os
import sys
import time
import django

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from sqlalchemy import text
from app.db import get_engine

engine = get_engine()

with engine.connect() as conn:

    # --- web_xp_events ---
    print("Creating web_xp_events...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_xp_events (
            id          INT AUTO_INCREMENT PRIMARY KEY,
            user_id     INT NOT NULL,
            action_type VARCHAR(50) NOT NULL,
            xp          INT NOT NULL,
            source      VARCHAR(20) NOT NULL DEFAULT 'web',
            ref_id      VARCHAR(100),
            created_at  BIGINT NOT NULL,
            INDEX idx_xp_user_action_date (user_id, action_type, created_at),
            FOREIGN KEY (user_id) REFERENCES web_users(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

    # --- web_flairs ---
    print("Creating web_flairs...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_flairs (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            name         VARCHAR(100) NOT NULL,
            emoji        VARCHAR(20)  NOT NULL DEFAULT '',
            description  VARCHAR(300),
            flair_type   ENUM('normal','seasonal','exclusive') NOT NULL DEFAULT 'normal',
            hp_cost      INT NOT NULL DEFAULT 0,
            enabled      TINYINT(1) NOT NULL DEFAULT 1,
            display_order INT NOT NULL DEFAULT 0,
            created_at   BIGINT NOT NULL,
            updated_at   BIGINT NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

    # --- web_user_flairs ---
    print("Creating web_user_flairs...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_user_flairs (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            user_id      INT NOT NULL,
            flair_id     INT NOT NULL,
            is_equipped  TINYINT(1) NOT NULL DEFAULT 0,
            purchased_at BIGINT NOT NULL,
            INDEX idx_uf_user (user_id),
            UNIQUE KEY uq_uf_user_flair (user_id, flair_id),
            FOREIGN KEY (user_id)  REFERENCES web_users(id)  ON DELETE CASCADE,
            FOREIGN KEY (flair_id) REFERENCES web_flairs(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

    # --- web_rank_titles ---
    print("Creating web_rank_titles...")
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS web_rank_titles (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            level        INT NOT NULL UNIQUE,
            title        VARCHAR(100) NOT NULL,
            icon         VARCHAR(50)  NOT NULL DEFAULT '',
            created_at   BIGINT NOT NULL,
            updated_at   BIGINT NOT NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """))
    conn.commit()
    print("  Done.")

    # --- Seed default ARPG/soulslike rank titles ---
    now = int(time.time())
    default_titles = [
        (1,  'Hollow Wanderer',    'fas fa-user'),
        (5,  'Ember Knight',       'fas fa-shield-alt'),
        (10, 'Cursed Champion',    'fas fa-skull'),
        (15, 'Soul Bearer',        'fas fa-fire'),
        (20, 'Phantom Blade',      'fas fa-sword'),
        (30, 'Ashen Lord',         'fas fa-dragon'),
        (40, 'Sovereign of Cinder','fas fa-crown'),
        (50, 'Elden Seeker',       'fas fa-gem'),
        (65, 'Undying Sovereign',  'fas fa-infinity'),
        (80, 'Mythic Wraith',      'fas fa-bolt'),
        (99, 'The Fated One',      'fas fa-star'),
    ]
    existing = conn.execute(text("SELECT COUNT(*) FROM web_rank_titles")).scalar()
    if existing == 0:
        print("Seeding default rank titles...")
        for level, title, icon in default_titles:
            conn.execute(text("""
                INSERT IGNORE INTO web_rank_titles (level, title, icon, created_at, updated_at)
                VALUES (:level, :title, :icon, :now, :now)
            """), {'level': level, 'title': title, 'icon': icon, 'now': now})
        conn.commit()
        print(f"  Inserted {len(default_titles)} rank titles.")
    else:
        print(f"  Rank titles already seeded ({existing} rows), skipping.")

    # --- web_users: add active_flair_id column if not present ---
    print("Adding active_flair_id to web_users (if not present)...")
    try:
        conn.execute(text(
            "ALTER TABLE web_users ADD COLUMN active_flair_id INT NULL"
        ))
        conn.commit()
        print("  Done.")
    except Exception as e:
        if 'Duplicate column' in str(e) or 'already exists' in str(e).lower():
            print("  Already exists, skipping.")
        else:
            raise

print("\nMigration complete.")
