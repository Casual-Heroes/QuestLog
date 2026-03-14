#!/usr/bin/env python3
"""
create_matrix_tables.py - Create all web_matrix_* tables for QuestLogMatrix bot.

Run with:
  source /srv/ch-webserver/chwebsiteprj/bin/activate && python3 create_matrix_tables.py
"""

import sys
import os
sys.path.insert(0, '/srv/ch-webserver')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

TABLES = [
    # ---------------------------------------------------------------
    # Space settings (guild equivalent)
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_space_settings (
        id                      INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id                VARCHAR(255)  NOT NULL,
        space_name              VARCHAR(200)  NULL,
        space_avatar_url        VARCHAR(500)  NULL,
        owner_matrix_id         VARCHAR(100)  NULL,
        bot_present             SMALLINT      NOT NULL DEFAULT 1,
        joined_at               BIGINT        NULL,
        left_at                 BIGINT        NULL,
        -- XP
        xp_enabled              SMALLINT      NOT NULL DEFAULT 1,
        xp_per_message          INTEGER       NOT NULL DEFAULT 2,
        xp_cooldown_secs        INTEGER       NOT NULL DEFAULT 60,
        xp_ignored_rooms        TEXT          NULL,
        level_up_enabled        SMALLINT      NOT NULL DEFAULT 0,
        level_up_room_id        VARCHAR(255)  NULL,
        level_up_message        TEXT          NULL,
        -- Moderation
        mod_log_room_id         VARCHAR(255)  NULL,
        warn_threshold          INTEGER       NOT NULL DEFAULT 3,
        auto_ban_after_warns    SMALLINT      NOT NULL DEFAULT 0,
        -- Welcome
        welcome_room_id         VARCHAR(255)  NULL,
        welcome_message         TEXT          NULL,
        goodbye_room_id         VARCHAR(255)  NULL,
        goodbye_message         TEXT          NULL,
        -- Admin access
        admin_power_level       INTEGER       NOT NULL DEFAULT 50,
        admin_matrix_ids        TEXT          NULL,
        -- General
        bot_prefix              VARCHAR(10)   NOT NULL DEFAULT '!',
        language                VARCHAR(10)   NOT NULL DEFAULT 'en',
        timezone                VARCHAR(50)   NOT NULL DEFAULT 'UTC',
        -- Discovery
        discovery_enabled       SMALLINT      NOT NULL DEFAULT 0,
        discovery_room_id       VARCHAR(255)  NULL,
        discovery_ping_matrix_id VARCHAR(100) NULL,
        -- Timestamps
        created_at              BIGINT        NOT NULL DEFAULT 0,
        updated_at              BIGINT        NOT NULL DEFAULT 0,
        UNIQUE KEY uq_matrix_space_id (space_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Rooms (channel equivalent)
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_rooms (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id            VARCHAR(255)  NOT NULL,
        room_id             VARCHAR(255)  NOT NULL,
        room_name           VARCHAR(200)  NULL,
        room_alias          VARCHAR(200)  NULL,
        topic               TEXT          NULL,
        is_encrypted        SMALLINT      NOT NULL DEFAULT 0,
        is_space            SMALLINT      NOT NULL DEFAULT 0,
        member_count        INTEGER       NOT NULL DEFAULT 0,
        power_levels_json   TEXT          NULL,
        last_synced_at      BIGINT        NULL,
        created_at          BIGINT        NOT NULL DEFAULT 0,
        UNIQUE KEY uq_matrix_room (space_id, room_id),
        INDEX idx_matrix_rooms_space (space_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Members
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_members (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id            VARCHAR(255)  NOT NULL,
        matrix_id           VARCHAR(100)  NOT NULL,
        display_name        VARCHAR(200)  NULL,
        avatar_url          VARCHAR(500)  NULL,
        power_level         INTEGER       NOT NULL DEFAULT 0,
        web_user_id         INTEGER       NULL,
        joined_at           BIGINT        NULL,
        left_at             BIGINT        NULL,
        last_seen           BIGINT        NULL,
        synced_at           BIGINT        NOT NULL DEFAULT 0,
        UNIQUE KEY uq_matrix_member (space_id, matrix_id),
        INDEX idx_matrix_members_space (space_id),
        INDEX idx_matrix_members_mid (matrix_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # XP per member per space
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_xp_events (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id            VARCHAR(255)  NOT NULL,
        matrix_id           VARCHAR(100)  NOT NULL,
        xp                  INTEGER       NOT NULL DEFAULT 0,
        level               INTEGER       NOT NULL DEFAULT 1,
        last_message_at     BIGINT        NULL,
        UNIQUE KEY uq_matrix_xp (space_id, matrix_id),
        INDEX idx_matrix_xp_space (space_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Mod warnings
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_mod_warnings (
        id                      INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id                VARCHAR(255)  NOT NULL,
        target_matrix_id        VARCHAR(100)  NOT NULL,
        moderator_matrix_id     VARCHAR(100)  NOT NULL,
        reason                  TEXT          NOT NULL,
        room_id                 VARCHAR(255)  NULL,
        is_active               SMALLINT      NOT NULL DEFAULT 1,
        pardoned_by             VARCHAR(100)  NULL,
        pardoned_at             BIGINT        NULL,
        created_at              BIGINT        NOT NULL DEFAULT 0,
        INDEX idx_matrix_warn_space (space_id),
        INDEX idx_matrix_warn_target (space_id, target_matrix_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Welcome config
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_welcome_config (
        id                      INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id                VARCHAR(255)  NOT NULL,
        enabled                 SMALLINT      NOT NULL DEFAULT 0,
        welcome_room_id         VARCHAR(255)  NULL,
        welcome_message         TEXT          NULL,
        welcome_embed_enabled   SMALLINT      NOT NULL DEFAULT 0,
        welcome_embed_title     VARCHAR(200)  NULL,
        welcome_embed_color     VARCHAR(10)   NULL,
        dm_enabled              SMALLINT      NOT NULL DEFAULT 0,
        dm_message              TEXT          NULL,
        goodbye_enabled         SMALLINT      NOT NULL DEFAULT 0,
        goodbye_room_id         VARCHAR(255)  NULL,
        goodbye_message         TEXT          NULL,
        auto_invite_room_ids    TEXT          NULL,
        updated_at              BIGINT        NOT NULL DEFAULT 0,
        UNIQUE KEY uq_matrix_welcome (space_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # RSS feeds
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_rss_feeds (
        id                      INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id                VARCHAR(255)  NOT NULL,
        url                     VARCHAR(500)  NOT NULL,
        label                   VARCHAR(200)  NULL,
        room_id                 VARCHAR(255)  NOT NULL,
        room_name               VARCHAR(100)  NULL,
        ping_matrix_id          VARCHAR(100)  NULL,
        poll_interval_minutes   INTEGER       NOT NULL DEFAULT 15,
        max_age_days            INTEGER       NULL,
        last_checked_at         BIGINT        NULL,
        last_entry_id           VARCHAR(200)  NULL,
        consecutive_failures    INTEGER       NOT NULL DEFAULT 0,
        last_error              VARCHAR(500)  NULL,
        enabled                 INTEGER       NOT NULL DEFAULT 1,
        created_at              BIGINT        NOT NULL DEFAULT 0,
        INDEX idx_matrix_rss_space (space_id, enabled)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # RSS articles (deduplication)
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_rss_articles (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        feed_id             INTEGER       NOT NULL,
        space_id            VARCHAR(255)  NOT NULL,
        entry_guid          VARCHAR(500)  NOT NULL,
        entry_link          VARCHAR(500)  NULL,
        entry_title         VARCHAR(500)  NULL,
        entry_summary       TEXT          NULL,
        entry_author        VARCHAR(256)  NULL,
        entry_thumbnail     VARCHAR(500)  NULL,
        published_at        BIGINT        NULL,
        posted_at           BIGINT        NOT NULL DEFAULT 0,
        UNIQUE KEY uq_matrix_rss_article (feed_id, entry_guid(191)),
        INDEX idx_matrix_rss_article_space (space_id, posted_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Action queue (web -> bot)
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_guild_actions (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id            VARCHAR(255)  NOT NULL,
        action_type         VARCHAR(50)   NOT NULL,
        payload_json        TEXT          NOT NULL,
        status              VARCHAR(20)   NOT NULL DEFAULT 'pending',
        created_at          BIGINT        NOT NULL DEFAULT 0,
        processed_at        BIGINT        NULL,
        result_json         TEXT          NULL,
        INDEX idx_matrix_action_queue (space_id, status, created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Pending DMs (account linking verification)
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_pending_dms (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        matrix_id           VARCHAR(100)  NOT NULL,
        message             TEXT          NOT NULL,
        status              VARCHAR(20)   NOT NULL DEFAULT 'pending',
        created_at          BIGINT        NOT NULL DEFAULT 0,
        sent_at             BIGINT        NULL,
        INDEX idx_matrix_pending_dms_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Ban lists (Draupnir-style policy lists)
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_ban_lists (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id            VARCHAR(255)  NOT NULL,
        name                VARCHAR(200)  NOT NULL,
        description         TEXT          NULL,
        is_subscribed       SMALLINT      NOT NULL DEFAULT 0,
        source_room_id      VARCHAR(255)  NULL,
        last_synced_at      BIGINT        NULL,
        created_at          BIGINT        NOT NULL DEFAULT 0,
        INDEX idx_matrix_ban_lists_space (space_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Ban list entries
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_ban_list_entries (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        list_id             INTEGER       NOT NULL,
        target_matrix_id    VARCHAR(100)  NOT NULL,
        reason              TEXT          NULL,
        added_by            VARCHAR(100)  NULL,
        created_at          BIGINT        NOT NULL DEFAULT 0,
        UNIQUE KEY uq_matrix_ban_entry (list_id, target_matrix_id),
        INDEX idx_matrix_ban_entry_list (list_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # Level roles (auto-assign role at level threshold)
    # (stored as power level assignments in Matrix)
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_level_roles (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id            VARCHAR(255)  NOT NULL,
        level               INTEGER       NOT NULL,
        power_level         INTEGER       NOT NULL DEFAULT 0,
        label               VARCHAR(100)  NULL,
        created_at          BIGINT        NOT NULL DEFAULT 0,
        UNIQUE KEY uq_matrix_level_role (space_id, level),
        INDEX idx_matrix_level_roles_space (space_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,

    # ---------------------------------------------------------------
    # XP boost events
    # ---------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS web_matrix_xp_boosts (
        id                  INTEGER       NOT NULL AUTO_INCREMENT PRIMARY KEY,
        space_id            VARCHAR(255)  NOT NULL,
        label               VARCHAR(100)  NOT NULL,
        multiplier          FLOAT         NOT NULL DEFAULT 2.0,
        starts_at           BIGINT        NOT NULL DEFAULT 0,
        ends_at             BIGINT        NOT NULL DEFAULT 0,
        created_at          BIGINT        NOT NULL DEFAULT 0,
        INDEX idx_matrix_xp_boost_space (space_id, ends_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def run():
    print("Creating Matrix tables...")
    with engine.connect() as conn:
        for sql in TABLES:
            table_name = [w for w in sql.split() if w.startswith('web_matrix_')][0]
            try:
                conn.execute(text(sql.strip()))
                conn.commit()
                print(f"  OK: {table_name}")
            except Exception as e:
                print(f"  ERROR {table_name}: {e}")
                raise
    print("Done.")


if __name__ == '__main__':
    run()
