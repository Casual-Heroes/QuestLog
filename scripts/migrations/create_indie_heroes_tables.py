"""
Migration: Create web_indie_games table and add indie_game_id to web_community_posts.
Run: chwebsiteprj/bin/python3 create_indie_heroes_tables.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text as sa_text

engine = get_engine()

with engine.begin() as conn:
    conn.execute(sa_text("""
        CREATE TABLE IF NOT EXISTS `web_indie_games` (
            `id`              INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            `slug`            VARCHAR(220) NOT NULL UNIQUE,
            `name`            VARCHAR(500) NOT NULL,
            `steam_app_id`    INT NULL UNIQUE,
            `steam_url`       VARCHAR(500) NULL,
            `igdb_id`         INT NULL,
            `igdb_url`        VARCHAR(500) NULL,
            `cover_url`       VARCHAR(500) NULL,
            `banner_url`      VARCHAR(500) NULL,
            `platforms`       TEXT NOT NULL DEFAULT '[]',
            `genres`          TEXT NOT NULL DEFAULT '[]',
            `steam_tags`      TEXT NOT NULL DEFAULT '[]',
            `spotlight_text`  TEXT NULL,
            `spotlight_quote` VARCHAR(500) NULL,
            `dev_bio`         TEXT NULL,
            `dev_devlog`      TEXT NULL,
            `dev_website`     VARCHAR(500) NULL,
            `dev_twitter`     VARCHAR(200) NULL,
            `dev_discord_url` VARCHAR(500) NULL,
            `dev_fluxer_url`  VARCHAR(500) NULL,
            `dev_steam_url`   VARCHAR(500) NULL,
            `dev_itch_url`    VARCHAR(500) NULL,
            `dev_youtube_url` VARCHAR(500) NULL,
            `dev_twitch_url`  VARCHAR(500) NULL,
            `community_id`    INT NULL,
            `release_date`    VARCHAR(100) NULL,
            `price`           VARCHAR(50) NULL,
            `review_score`    INT NULL,
            `status`          VARCHAR(20) NOT NULL DEFAULT 'featured',
            `is_published`    TINYINT(1) NOT NULL DEFAULT 0,
            `is_featured`     TINYINT(1) NOT NULL DEFAULT 0,
            `added_by`        INT NOT NULL,
            `dev_user_id`     INT NULL,
            `dev_edited_at`   BIGINT NULL,
            `post_count`      INT NOT NULL DEFAULT 0,
            `created_at`      BIGINT NOT NULL,
            `updated_at`      BIGINT NOT NULL,
            INDEX `ix_web_indie_games_published` (`is_published`, `is_featured`, `created_at`),
            INDEX `ix_web_indie_games_status` (`status`, `is_published`),
            INDEX `ix_web_indie_games_dev` (`dev_user_id`),
            CONSTRAINT `fk_indie_added_by` FOREIGN KEY (`added_by`) REFERENCES `web_users`(`id`),
            CONSTRAINT `fk_indie_dev_user` FOREIGN KEY (`dev_user_id`) REFERENCES `web_users`(`id`) ON DELETE SET NULL,
            CONSTRAINT `fk_indie_community` FOREIGN KEY (`community_id`) REFERENCES `web_communities`(`id`) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))
    print("Created web_indie_games table")

    # Add indie_game_id to web_community_posts if not already there
    result = conn.execute(sa_text("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = 'web_community_posts'
          AND COLUMN_NAME = 'indie_game_id'
    """))
    if result.scalar() == 0:
        conn.execute(sa_text("""
            ALTER TABLE `web_community_posts`
            ADD COLUMN `indie_game_id` INT NULL AFTER `lfg_group_id`,
            ADD INDEX `idx_cp_indie_game` (`indie_game_id`, `is_deleted`, `created_at`),
            ADD CONSTRAINT `fk_cp_indie_game`
                FOREIGN KEY (`indie_game_id`) REFERENCES `web_indie_games`(`id`) ON DELETE CASCADE
        """))
        print("Added indie_game_id to web_community_posts")
    else:
        print("indie_game_id already exists on web_community_posts - skipped")

print("Migration complete.")
