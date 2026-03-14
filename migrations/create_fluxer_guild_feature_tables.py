#!/usr/bin/env python3
"""
Migration: create all Fluxer guild feature tables.

Tables created:
  - web_fluxer_lfg_games          (per-guild LFG game configs)
  - web_fluxer_lfg_groups         (active LFG groups)
  - web_fluxer_lfg_members        (LFG group membership)
  - web_fluxer_welcome_config     (welcome/goodbye message config)
  - web_fluxer_reaction_roles     (reaction role menus)
  - web_fluxer_raffles            (guild raffles)
  - web_fluxer_raffle_entries     (raffle entries/tickets)
  - web_fluxer_mod_warnings       (moderation warnings)
  - web_fluxer_verification_config (verification settings)
  - web_fluxer_rss_feeds          (guild RSS feed subscriptions)

Run from project root:
    python create_fluxer_guild_feature_tables.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_db_session
from sqlalchemy import text

TABLES = [
    (
        'web_fluxer_lfg_games',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_lfg_games (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            guild_id        VARCHAR(32) NOT NULL,
            name            VARCHAR(100) NOT NULL,
            emoji           VARCHAR(100) DEFAULT NULL,
            cover_url       VARCHAR(500) DEFAULT NULL,
            max_group_size  INT NOT NULL DEFAULT 5,
            has_roles       INT NOT NULL DEFAULT 0,
            tank_slots      INT NOT NULL DEFAULT 0,
            healer_slots    INT NOT NULL DEFAULT 0,
            dps_slots       INT NOT NULL DEFAULT 0,
            support_slots   INT NOT NULL DEFAULT 0,
            options_json    TEXT DEFAULT NULL,
            is_active       INT NOT NULL DEFAULT 1,
            created_at      BIGINT NOT NULL DEFAULT 0,
            INDEX idx_fluxer_lfg_game_guild (guild_id, is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_lfg_groups',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_lfg_groups (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            guild_id            VARCHAR(32) NOT NULL,
            game_id             INT DEFAULT NULL,
            game_name           VARCHAR(100) NOT NULL,
            title               VARCHAR(200) DEFAULT NULL,
            description         TEXT DEFAULT NULL,
            max_size            INT NOT NULL DEFAULT 5,
            current_size        INT NOT NULL DEFAULT 1,
            creator_fluxer_id   VARCHAR(32) DEFAULT NULL,
            creator_web_user_id INT DEFAULT NULL,
            creator_name        VARCHAR(100) DEFAULT NULL,
            scheduled_time      BIGINT DEFAULT NULL,
            discord_message_id  VARCHAR(32) DEFAULT NULL,
            channel_id          VARCHAR(32) DEFAULT NULL,
            status              VARCHAR(20) NOT NULL DEFAULT 'open',
            created_at          BIGINT NOT NULL DEFAULT 0,
            closed_at           BIGINT DEFAULT NULL,
            INDEX idx_fluxer_lfg_group_guild_status (guild_id, status),
            INDEX idx_fluxer_lfg_group_created (guild_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_lfg_members',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_lfg_members (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            group_id        INT NOT NULL,
            fluxer_user_id  VARCHAR(32) DEFAULT NULL,
            web_user_id     INT DEFAULT NULL,
            username        VARCHAR(100) DEFAULT NULL,
            role            VARCHAR(20) DEFAULT NULL,
            selections_json TEXT DEFAULT NULL,
            is_creator      INT NOT NULL DEFAULT 0,
            joined_at       BIGINT NOT NULL DEFAULT 0,
            left_at         BIGINT DEFAULT NULL,
            INDEX idx_fluxer_lfg_member_group (group_id),
            INDEX idx_fluxer_lfg_member_user (fluxer_user_id),
            INDEX idx_fluxer_lfg_member_web (web_user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_welcome_config',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_welcome_config (
            id                      INT AUTO_INCREMENT PRIMARY KEY,
            guild_id                VARCHAR(32) NOT NULL,
            enabled                 INT NOT NULL DEFAULT 0,
            welcome_channel_id      VARCHAR(32) DEFAULT NULL,
            welcome_message         TEXT DEFAULT NULL,
            welcome_embed_enabled   INT NOT NULL DEFAULT 0,
            welcome_embed_title     VARCHAR(200) DEFAULT NULL,
            welcome_embed_color     VARCHAR(10) DEFAULT NULL,
            welcome_embed_footer    VARCHAR(300) DEFAULT NULL,
            welcome_embed_thumbnail INT NOT NULL DEFAULT 0,
            dm_enabled              INT NOT NULL DEFAULT 0,
            dm_message              TEXT DEFAULT NULL,
            goodbye_enabled         INT NOT NULL DEFAULT 0,
            goodbye_channel_id      VARCHAR(32) DEFAULT NULL,
            goodbye_message         TEXT DEFAULT NULL,
            auto_role_id            VARCHAR(32) DEFAULT NULL,
            updated_at              BIGINT NOT NULL DEFAULT 0,
            UNIQUE KEY uq_fluxer_welcome_guild (guild_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_reaction_roles',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_reaction_roles (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            guild_id      VARCHAR(32) NOT NULL,
            channel_id    VARCHAR(32) NOT NULL,
            message_id    VARCHAR(32) DEFAULT NULL,
            title         VARCHAR(200) DEFAULT NULL,
            description   TEXT DEFAULT NULL,
            mappings_json TEXT DEFAULT NULL,
            is_exclusive  INT NOT NULL DEFAULT 0,
            created_at    BIGINT NOT NULL DEFAULT 0,
            updated_at    BIGINT NOT NULL DEFAULT 0,
            INDEX idx_fluxer_react_role_guild (guild_id),
            INDEX idx_fluxer_react_role_msg (message_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_raffles',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_raffles (
            id                   INT AUTO_INCREMENT PRIMARY KEY,
            guild_id             VARCHAR(32) NOT NULL,
            title                VARCHAR(200) NOT NULL,
            description          TEXT DEFAULT NULL,
            prize                VARCHAR(300) DEFAULT NULL,
            channel_id           VARCHAR(32) DEFAULT NULL,
            message_id           VARCHAR(32) DEFAULT NULL,
            max_winners          INT NOT NULL DEFAULT 1,
            ticket_cost_hp       INT NOT NULL DEFAULT 0,
            max_entries_per_user INT NOT NULL DEFAULT 1,
            winners_json         TEXT DEFAULT NULL,
            status               VARCHAR(20) NOT NULL DEFAULT 'pending',
            starts_at            BIGINT DEFAULT NULL,
            ends_at              BIGINT DEFAULT NULL,
            created_by           INT DEFAULT NULL,
            created_at           BIGINT NOT NULL DEFAULT 0,
            INDEX idx_fluxer_raffle_guild_status (guild_id, status)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_raffle_entries',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_raffle_entries (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            raffle_id       INT NOT NULL,
            web_user_id     INT DEFAULT NULL,
            fluxer_user_id  VARCHAR(32) DEFAULT NULL,
            username        VARCHAR(100) DEFAULT NULL,
            ticket_count    INT NOT NULL DEFAULT 1,
            entered_at      BIGINT NOT NULL DEFAULT 0,
            INDEX idx_fluxer_raffle_entry_raffle (raffle_id),
            INDEX idx_fluxer_raffle_entry_user (raffle_id, web_user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_mod_warnings',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_mod_warnings (
            id                  INT AUTO_INCREMENT PRIMARY KEY,
            guild_id            VARCHAR(32) NOT NULL,
            target_user_id      VARCHAR(32) NOT NULL,
            target_username     VARCHAR(100) DEFAULT NULL,
            moderator_user_id   VARCHAR(32) DEFAULT NULL,
            moderator_username  VARCHAR(100) DEFAULT NULL,
            reason              TEXT DEFAULT NULL,
            severity            INT NOT NULL DEFAULT 1,
            is_active           INT NOT NULL DEFAULT 1,
            pardoned_at         BIGINT DEFAULT NULL,
            created_at          BIGINT NOT NULL DEFAULT 0,
            INDEX idx_fluxer_mod_warn_guild_user (guild_id, target_user_id),
            INDEX idx_fluxer_mod_warn_guild_active (guild_id, is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_verification_config',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_verification_config (
            id                      INT AUTO_INCREMENT PRIMARY KEY,
            guild_id                VARCHAR(32) NOT NULL,
            verification_type       VARCHAR(20) NOT NULL DEFAULT 'none',
            verification_channel_id VARCHAR(32) DEFAULT NULL,
            verified_role_id        VARCHAR(32) DEFAULT NULL,
            account_age_days        INT NOT NULL DEFAULT 7,
            verified_message        TEXT DEFAULT NULL,
            failed_message          TEXT DEFAULT NULL,
            updated_at              BIGINT NOT NULL DEFAULT 0,
            UNIQUE KEY uq_fluxer_verification_guild (guild_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
    (
        'web_fluxer_rss_feeds',
        """
        CREATE TABLE IF NOT EXISTS web_fluxer_rss_feeds (
            id              INT AUTO_INCREMENT PRIMARY KEY,
            guild_id        VARCHAR(32) NOT NULL,
            url             VARCHAR(500) NOT NULL,
            label           VARCHAR(200) DEFAULT NULL,
            channel_id      VARCHAR(32) NOT NULL,
            channel_name    VARCHAR(100) DEFAULT NULL,
            last_checked_at BIGINT DEFAULT NULL,
            last_entry_id   VARCHAR(200) DEFAULT NULL,
            is_active       INT NOT NULL DEFAULT 1,
            created_at      BIGINT NOT NULL DEFAULT 0,
            INDEX idx_fluxer_rss_guild_active (guild_id, is_active)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """,
    ),
]


def run():
    with get_db_session() as db:
        for table_name, sql in TABLES:
            try:
                db.execute(text(sql))
                db.commit()
                print(f"OK: CREATE TABLE IF NOT EXISTS {table_name}")
            except Exception as e:
                print(f"ERROR creating {table_name}: {e}")
                db.rollback()


if __name__ == '__main__':
    run()
    print("\nDone.")
