"""
Migration: SoulsLike Build Planner tables
Run: chwebsiteprj/bin/python3 create_soulslike_builder_tables.py
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

TABLES = [

# ─── Vanilla ER core data ────────────────────────────────────────────────────

"""
CREATE TABLE IF NOT EXISTS sl_weapons (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    game            VARCHAR(32)  NOT NULL DEFAULT 'elden_ring',
    name            VARCHAR(200) NOT NULL,
    weapon_type     VARCHAR(64)  NOT NULL,
    physical_damage SMALLINT     DEFAULT 0,
    magic_damage    SMALLINT     DEFAULT 0,
    fire_damage     SMALLINT     DEFAULT 0,
    lightning_damage SMALLINT    DEFAULT 0,
    holy_damage     SMALLINT     DEFAULT 0,
    critical        SMALLINT     DEFAULT 100,
    weight          DECIMAL(5,1) DEFAULT 0,
    str_scaling     CHAR(1)      DEFAULT '-',
    dex_scaling     CHAR(1)      DEFAULT '-',
    int_scaling     CHAR(1)      DEFAULT '-',
    fai_scaling     CHAR(1)      DEFAULT '-',
    arc_scaling     CHAR(1)      DEFAULT '-',
    str_requirement TINYINT      DEFAULT 0,
    dex_requirement TINYINT      DEFAULT 0,
    int_requirement TINYINT      DEFAULT 0,
    fai_requirement TINYINT      DEFAULT 0,
    arc_requirement TINYINT      DEFAULT 0,
    special_ability VARCHAR(200) DEFAULT NULL,
    special_ability_fp_cost SMALLINT DEFAULT 0,
    is_somber       TINYINT(1)   DEFAULT 0,
    image_url       VARCHAR(500) DEFAULT NULL,
    location_region VARCHAR(100) DEFAULT NULL,
    location_subarea VARCHAR(200) DEFAULT NULL,
    acquisition_type VARCHAR(32) DEFAULT NULL,
    acquisition_detail TEXT       DEFAULT NULL,
    boss_required   VARCHAR(200) DEFAULT NULL,
    is_missable     TINYINT(1)   DEFAULT 0,
    ng_plus_only    TINYINT(1)   DEFAULT 0,
    spoiler_level   TINYINT      DEFAULT 3,
    created_at      BIGINT       NOT NULL,
    INDEX idx_sl_weapons_game (game),
    INDEX idx_sl_weapons_type (weapon_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_weapon_affinities (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    weapon_id       INT          NOT NULL,
    game            VARCHAR(32)  NOT NULL DEFAULT 'elden_ring',
    affinity_type   VARCHAR(32)  NOT NULL,
    physical_damage SMALLINT     DEFAULT 0,
    magic_damage    SMALLINT     DEFAULT 0,
    fire_damage     SMALLINT     DEFAULT 0,
    lightning_damage SMALLINT    DEFAULT 0,
    holy_damage     SMALLINT     DEFAULT 0,
    str_scaling     CHAR(1)      DEFAULT '-',
    dex_scaling     CHAR(1)      DEFAULT '-',
    int_scaling     CHAR(1)      DEFAULT '-',
    fai_scaling     CHAR(1)      DEFAULT '-',
    arc_scaling     CHAR(1)      DEFAULT '-',
    notes           TEXT         DEFAULT NULL,
    INDEX idx_sl_waff_weapon (weapon_id),
    INDEX idx_sl_waff_game (game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_spells (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    game            VARCHAR(32)  NOT NULL DEFAULT 'elden_ring',
    name            VARCHAR(200) NOT NULL,
    spell_type      VARCHAR(32)  NOT NULL,
    fp_cost         SMALLINT     DEFAULT 0,
    fp_cost_charged SMALLINT     DEFAULT NULL,
    slots_required  TINYINT      DEFAULT 1,
    int_requirement TINYINT      DEFAULT 0,
    fai_requirement TINYINT      DEFAULT 0,
    arc_requirement TINYINT      DEFAULT 0,
    damage_type     VARCHAR(64)  DEFAULT NULL,
    image_url       VARCHAR(500) DEFAULT NULL,
    description     TEXT         DEFAULT NULL,
    location_region VARCHAR(100) DEFAULT NULL,
    location_subarea VARCHAR(200) DEFAULT NULL,
    acquisition_type VARCHAR(32) DEFAULT NULL,
    acquisition_detail TEXT      DEFAULT NULL,
    boss_required   VARCHAR(200) DEFAULT NULL,
    is_missable     TINYINT(1)   DEFAULT 0,
    ng_plus_only    TINYINT(1)   DEFAULT 0,
    spoiler_level   TINYINT      DEFAULT 3,
    created_at      BIGINT       NOT NULL,
    INDEX idx_sl_spells_game (game),
    INDEX idx_sl_spells_type (spell_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_armor (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    game             VARCHAR(32)  NOT NULL DEFAULT 'elden_ring',
    name             VARCHAR(200) NOT NULL,
    armor_type       VARCHAR(16)  NOT NULL,
    weight           DECIMAL(5,1) DEFAULT 0,
    physical_defense DECIMAL(5,1) DEFAULT 0,
    magic_defense    DECIMAL(5,1) DEFAULT 0,
    fire_defense     DECIMAL(5,1) DEFAULT 0,
    lightning_defense DECIMAL(5,1) DEFAULT 0,
    holy_defense     DECIMAL(5,1) DEFAULT 0,
    poise            DECIMAL(5,1) DEFAULT 0,
    image_url        VARCHAR(500) DEFAULT NULL,
    location_region  VARCHAR(100) DEFAULT NULL,
    location_subarea VARCHAR(200) DEFAULT NULL,
    acquisition_type VARCHAR(32)  DEFAULT NULL,
    acquisition_detail TEXT       DEFAULT NULL,
    is_missable      TINYINT(1)   DEFAULT 0,
    ng_plus_only     TINYINT(1)   DEFAULT 0,
    spoiler_level    TINYINT      DEFAULT 3,
    created_at       BIGINT       NOT NULL,
    INDEX idx_sl_armor_game (game),
    INDEX idx_sl_armor_type (armor_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_talismans (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    game            VARCHAR(32)  NOT NULL DEFAULT 'elden_ring',
    name            VARCHAR(200) NOT NULL,
    description     TEXT         DEFAULT NULL,
    effect          TEXT         DEFAULT NULL,
    effect_value    VARCHAR(100) DEFAULT NULL,
    weight          DECIMAL(4,1) DEFAULT 0,
    image_url       VARCHAR(500) DEFAULT NULL,
    is_stackable    TINYINT(1)   DEFAULT 0,
    location_region VARCHAR(100) DEFAULT NULL,
    location_subarea VARCHAR(200) DEFAULT NULL,
    acquisition_type VARCHAR(32) DEFAULT NULL,
    acquisition_detail TEXT      DEFAULT NULL,
    boss_required   VARCHAR(200) DEFAULT NULL,
    is_missable     TINYINT(1)   DEFAULT 0,
    ng_plus_only    TINYINT(1)   DEFAULT 0,
    spoiler_level   TINYINT      DEFAULT 3,
    created_at      BIGINT       NOT NULL,
    INDEX idx_sl_talismans_game (game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_ashes_of_war (
    id                    INT AUTO_INCREMENT PRIMARY KEY,
    game                  VARCHAR(32)  NOT NULL DEFAULT 'elden_ring',
    name                  VARCHAR(200) NOT NULL,
    affinity              VARCHAR(32)  DEFAULT 'standard',
    fp_cost               SMALLINT     DEFAULT 0,
    damage_type           VARCHAR(64)  DEFAULT NULL,
    scaling_override      TEXT         DEFAULT NULL,
    compatible_weapon_types TEXT        DEFAULT NULL,
    image_url             VARCHAR(500) DEFAULT NULL,
    description           TEXT         DEFAULT NULL,
    location_region       VARCHAR(100) DEFAULT NULL,
    location_subarea      VARCHAR(200) DEFAULT NULL,
    acquisition_type      VARCHAR(32)  DEFAULT NULL,
    acquisition_detail    TEXT         DEFAULT NULL,
    is_missable           TINYINT(1)   DEFAULT 0,
    spoiler_level         TINYINT      DEFAULT 3,
    created_at            BIGINT       NOT NULL,
    INDEX idx_sl_aow_game (game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_classes (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    game            VARCHAR(32)  NOT NULL DEFAULT 'elden_ring',
    name            VARCHAR(64)  NOT NULL,
    starting_level  TINYINT      NOT NULL,
    vigor           TINYINT      DEFAULT 0,
    mind            TINYINT      DEFAULT 0,
    endurance       TINYINT      DEFAULT 0,
    strength        TINYINT      DEFAULT 0,
    dexterity       TINYINT      DEFAULT 0,
    intelligence    TINYINT      DEFAULT 0,
    faith           TINYINT      DEFAULT 0,
    arcane          TINYINT      DEFAULT 0,
    image_url       VARCHAR(500) DEFAULT NULL,
    INDEX idx_sl_classes_game (game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_stat_caps (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    game        VARCHAR(32) NOT NULL DEFAULT 'elden_ring',
    stat        VARCHAR(16) NOT NULL,
    soft_cap_1  TINYINT     DEFAULT NULL,
    soft_cap_2  TINYINT     DEFAULT NULL,
    hard_cap    TINYINT     DEFAULT 99,
    notes       TEXT        DEFAULT NULL,
    INDEX idx_sl_stat_caps_game (game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

# ─── ERR overlay tables ───────────────────────────────────────────────────────

"""
CREATE TABLE IF NOT EXISTS sl_err_weapon_overrides (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    weapon_id        INT          NOT NULL,
    physical_damage  SMALLINT     DEFAULT NULL,
    magic_damage     SMALLINT     DEFAULT NULL,
    fire_damage      SMALLINT     DEFAULT NULL,
    lightning_damage SMALLINT     DEFAULT NULL,
    holy_damage      SMALLINT     DEFAULT NULL,
    str_scaling      CHAR(1)      DEFAULT NULL,
    dex_scaling      CHAR(1)      DEFAULT NULL,
    int_scaling      CHAR(1)      DEFAULT NULL,
    fai_scaling      CHAR(1)      DEFAULT NULL,
    arc_scaling      CHAR(1)      DEFAULT NULL,
    weight           DECIMAL(5,1) DEFAULT NULL,
    special_notes    TEXT         DEFAULT NULL,
    UNIQUE KEY uq_err_weapon (weapon_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_err_enkindled_aow (
    id                 INT AUTO_INCREMENT PRIMARY KEY,
    base_aow_id        INT          NOT NULL,
    rarity             VARCHAR(16)  NOT NULL,
    affix_1            VARCHAR(200) DEFAULT NULL,
    affix_2            VARCHAR(200) DEFAULT NULL,
    affix_3            VARCHAR(200) DEFAULT NULL,
    can_apply_to_somber TINYINT(1)  DEFAULT 0,
    INDEX idx_sl_enkindled_aow (base_aow_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_err_binding_runes (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    rune_type       VARCHAR(32)  NOT NULL,
    effect          TEXT         DEFAULT NULL,
    effect_value    VARCHAR(100) DEFAULT NULL,
    conflicts_with  TEXT         DEFAULT NULL,
    synergizes_with TEXT         DEFAULT NULL,
    image_url       VARCHAR(500) DEFAULT NULL,
    description     TEXT         DEFAULT NULL,
    max_forge_level TINYINT      DEFAULT 10,
    ng_plus_only    TINYINT(1)   DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_err_fortunes (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    fortune_type    VARCHAR(16)  NOT NULL,
    buffs           TEXT         DEFAULT NULL,
    drawbacks       TEXT         DEFAULT NULL,
    unique_effects  TEXT         DEFAULT NULL,
    how_to_unlock   TEXT         DEFAULT NULL,
    image_url       VARCHAR(500) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_err_shadowed_curios (
    id                     INT AUTO_INCREMENT PRIMARY KEY,
    name                   VARCHAR(200) NOT NULL,
    trigger_condition      TEXT         DEFAULT NULL,
    effect_option_1        TEXT         DEFAULT NULL,
    effect_option_2        TEXT         DEFAULT NULL,
    effect_option_3        TEXT         DEFAULT NULL,
    max_upgrade_level      TINYINT      DEFAULT 2,
    ember_piece_cost_unlock SMALLINT    DEFAULT 50,
    ember_piece_cost_upgrade SMALLINT   DEFAULT 25,
    image_url              VARCHAR(500) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

# ─── Builds ───────────────────────────────────────────────────────────────────

"""
CREATE TABLE IF NOT EXISTS sl_er_builds (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          DEFAULT NULL,
    name            VARCHAR(200) NOT NULL,
    description     TEXT         DEFAULT NULL,
    class_id        INT          DEFAULT NULL,
    vigor           TINYINT      DEFAULT 10,
    mind            TINYINT      DEFAULT 10,
    endurance       TINYINT      DEFAULT 10,
    strength        TINYINT      DEFAULT 10,
    dexterity       TINYINT      DEFAULT 10,
    intelligence    TINYINT      DEFAULT 10,
    faith           TINYINT      DEFAULT 10,
    arcane          TINYINT      DEFAULT 10,
    total_level     SMALLINT     DEFAULT 1,
    primary_weapon_id    INT     DEFAULT NULL,
    primary_weapon_affinity VARCHAR(32) DEFAULT 'standard',
    primary_aow_id  INT          DEFAULT NULL,
    secondary_weapon_id  INT     DEFAULT NULL,
    secondary_weapon_affinity VARCHAR(32) DEFAULT 'standard',
    secondary_aow_id INT         DEFAULT NULL,
    shield_id       INT          DEFAULT NULL,
    shield_aow_id   INT          DEFAULT NULL,
    helm_id         INT          DEFAULT NULL,
    chest_id        INT          DEFAULT NULL,
    gauntlet_id     INT          DEFAULT NULL,
    leg_id          INT          DEFAULT NULL,
    talisman_1_id   INT          DEFAULT NULL,
    talisman_2_id   INT          DEFAULT NULL,
    talisman_3_id   INT          DEFAULT NULL,
    talisman_4_id   INT          DEFAULT NULL,
    spells          TEXT         DEFAULT NULL,
    playstyle_tag   VARCHAR(32)  DEFAULT 'pve',
    is_public       TINYINT(1)   DEFAULT 1,
    upvotes         INT          DEFAULT 0,
    forked_from     INT          DEFAULT NULL,
    share_token     VARCHAR(16)  DEFAULT NULL UNIQUE,
    created_at      BIGINT       NOT NULL,
    updated_at      BIGINT       NOT NULL,
    INDEX idx_sl_er_builds_user (user_id),
    INDEX idx_sl_er_builds_public (is_public),
    INDEX idx_sl_er_builds_tag (playstyle_tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_err_builds (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          DEFAULT NULL,
    name            VARCHAR(200) NOT NULL,
    description     TEXT         DEFAULT NULL,
    class_id        INT          DEFAULT NULL,
    vigor           TINYINT      DEFAULT 10,
    mind            TINYINT      DEFAULT 10,
    endurance       TINYINT      DEFAULT 10,
    strength        TINYINT      DEFAULT 10,
    dexterity       TINYINT      DEFAULT 10,
    intelligence    TINYINT      DEFAULT 10,
    faith           TINYINT      DEFAULT 10,
    arcane          TINYINT      DEFAULT 10,
    total_level     SMALLINT     DEFAULT 1,
    primary_weapon_id    INT     DEFAULT NULL,
    primary_weapon_affinity VARCHAR(32) DEFAULT 'standard',
    primary_aow_id  INT          DEFAULT NULL,
    primary_enkindling_level TINYINT DEFAULT NULL,
    secondary_weapon_id  INT     DEFAULT NULL,
    secondary_weapon_affinity VARCHAR(32) DEFAULT 'standard',
    secondary_aow_id INT         DEFAULT NULL,
    secondary_enkindling_level TINYINT DEFAULT NULL,
    shield_id       INT          DEFAULT NULL,
    shield_aow_id   INT          DEFAULT NULL,
    helm_id         INT          DEFAULT NULL,
    chest_id        INT          DEFAULT NULL,
    gauntlet_id     INT          DEFAULT NULL,
    leg_id          INT          DEFAULT NULL,
    talisman_1_id   INT          DEFAULT NULL,
    talisman_2_id   INT          DEFAULT NULL,
    talisman_3_id   INT          DEFAULT NULL,
    talisman_4_id   INT          DEFAULT NULL,
    spells          TEXT         DEFAULT NULL,
    major_fortune_id INT         DEFAULT NULL,
    minor_fortune_id INT         DEFAULT NULL,
    binding_runes   TEXT         DEFAULT NULL,
    curio_selections TEXT        DEFAULT NULL,
    playstyle_tag   VARCHAR(32)  DEFAULT 'pve',
    is_public       TINYINT(1)   DEFAULT 1,
    upvotes         INT          DEFAULT 0,
    forked_from     INT          DEFAULT NULL,
    share_token     VARCHAR(16)  DEFAULT NULL UNIQUE,
    created_at      BIGINT       NOT NULL,
    updated_at      BIGINT       NOT NULL,
    INDEX idx_sl_err_builds_user (user_id),
    INDEX idx_sl_err_builds_public (is_public)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_build_comments (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    build_id    INT          NOT NULL,
    game        VARCHAR(32)  NOT NULL,
    user_id     INT          NOT NULL,
    comment     TEXT         NOT NULL,
    created_at  BIGINT       NOT NULL,
    INDEX idx_sl_bc_build (build_id, game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_build_upvotes (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    build_id    INT          NOT NULL,
    game        VARCHAR(32)  NOT NULL,
    user_id     INT          NOT NULL,
    created_at  BIGINT       NOT NULL,
    UNIQUE KEY uq_sl_upvote (build_id, game, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_build_forks (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    original_build_id INT         NOT NULL,
    forked_build_id   INT         NOT NULL,
    game              VARCHAR(32) NOT NULL,
    user_id           INT         NOT NULL,
    created_at        BIGINT      NOT NULL,
    INDEX idx_sl_forks_original (original_build_id, game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

# ─── Build Timeline ───────────────────────────────────────────────────────────

"""
CREATE TABLE IF NOT EXISTS sl_build_timeline (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    build_id             INT          NOT NULL,
    game                 VARCHAR(32)  NOT NULL,
    phase_number         TINYINT      NOT NULL,
    phase_name           VARCHAR(32)  NOT NULL,
    target_level         SMALLINT     NOT NULL,
    key_weapons          TEXT         DEFAULT NULL,
    key_spells           TEXT         DEFAULT NULL,
    key_talismans        TEXT         DEFAULT NULL,
    key_aow              TEXT         DEFAULT NULL,
    notes                TEXT         DEFAULT NULL,
    playstyle_description TEXT        DEFAULT NULL,
    difficulty_rating    TINYINT      DEFAULT 3,
    INDEX idx_sl_timeline_build (build_id, game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

# ─── Build Collection Tracker (overlay) ──────────────────────────────────────

"""
CREATE TABLE IF NOT EXISTS sl_collection_sessions (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    build_id     INT          NOT NULL,
    game         VARCHAR(32)  NOT NULL,
    user_id      INT          DEFAULT NULL,
    spoiler_mode VARCHAR(16)  DEFAULT 'region',
    started_at   BIGINT       NOT NULL,
    ended_at     BIGINT       DEFAULT NULL,
    INDEX idx_sl_coll_build (build_id, game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_collection_item_status (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    session_id        INT          NOT NULL,
    item_type         VARCHAR(16)  NOT NULL,
    item_id           INT          NOT NULL,
    is_collected      TINYINT(1)   DEFAULT 0,
    collected_at      BIGINT       DEFAULT NULL,
    collection_method VARCHAR(16)  DEFAULT NULL,
    spoiler_level_shown TINYINT    DEFAULT NULL,
    INDEX idx_sl_cis_session (session_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

# ─── Quest Dependencies ───────────────────────────────────────────────────────

"""
CREATE TABLE IF NOT EXISTS sl_quests (
    id                     INT AUTO_INCREMENT PRIMARY KEY,
    game                   VARCHAR(32)  NOT NULL DEFAULT 'elden_ring',
    name                   VARCHAR(200) NOT NULL,
    npc_name               VARCHAR(200) DEFAULT NULL,
    starting_location_region VARCHAR(100) DEFAULT NULL,
    starting_location_detail TEXT        DEFAULT NULL,
    is_missable            TINYINT(1)   DEFAULT 0,
    point_of_no_return     TEXT         DEFAULT NULL,
    quest_type             VARCHAR(32)  DEFAULT 'npc',
    spoiler_level          TINYINT      DEFAULT 3,
    INDEX idx_sl_quests_game (game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_quest_steps (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    quest_id            INT          NOT NULL,
    step_number         TINYINT      NOT NULL,
    description         TEXT         NOT NULL,
    location_region     VARCHAR(100) DEFAULT NULL,
    location_detail     TEXT         DEFAULT NULL,
    trigger_condition   TEXT         DEFAULT NULL,
    is_missable         TINYINT(1)   DEFAULT 0,
    missable_warning    VARCHAR(500) DEFAULT NULL,
    spoiler_detail      TEXT         DEFAULT NULL,
    before_event        TEXT         DEFAULT NULL,
    after_event         TEXT         DEFAULT NULL,
    INDEX idx_sl_qs_quest (quest_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_quest_step_dependencies (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    step_id             INT          NOT NULL,
    depends_on_step_id  INT          NOT NULL,
    dependency_type     VARCHAR(32)  DEFAULT 'required',
    notes               TEXT         DEFAULT NULL,
    INDEX idx_sl_qsd_step (step_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_item_quest_dependencies (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    item_id           INT          NOT NULL,
    item_type         VARCHAR(16)  NOT NULL,
    quest_id          INT          NOT NULL,
    quest_step_id     INT          DEFAULT NULL,
    is_quest_reward   TINYINT(1)   DEFAULT 0,
    is_quest_locked   TINYINT(1)   DEFAULT 0,
    alternative_source TEXT        DEFAULT NULL,
    INDEX idx_sl_iqd_item (item_id, item_type),
    INDEX idx_sl_iqd_quest (quest_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_boss_quest_dependencies (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    quest_id        INT          NOT NULL,
    quest_step_id   INT          DEFAULT NULL,
    boss_name       VARCHAR(200) NOT NULL,
    must_be_alive   TINYINT(1)   DEFAULT 0,
    must_be_defeated TINYINT(1)  DEFAULT 0,
    notes           TEXT         DEFAULT NULL,
    INDEX idx_sl_bqd_quest (quest_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

"""
CREATE TABLE IF NOT EXISTS sl_area_quest_dependencies (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    quest_id                INT          NOT NULL,
    quest_step_id           INT          DEFAULT NULL,
    area_name               VARCHAR(200) NOT NULL,
    must_access_before_event TEXT        DEFAULT NULL,
    locked_after_event      TEXT         DEFAULT NULL,
    INDEX idx_sl_aqd_quest (quest_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

# ─── Tournament integration ───────────────────────────────────────────────────

"""
CREATE TABLE IF NOT EXISTS sl_tournament_builds (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    tournament_id   INT          NOT NULL,
    build_id        INT          NOT NULL,
    game            VARCHAR(32)  NOT NULL,
    user_id         INT          NOT NULL,
    submitted_at    BIGINT       NOT NULL,
    INDEX idx_sl_tb_tournament (tournament_id),
    INDEX idx_sl_tb_build (build_id, game)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
""",

]

def run():
    with engine.connect() as conn:
        for sql in TABLES:
            table_name = [w for w in sql.split() if w.startswith('sl_')][0]
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f'  OK  {table_name}')
            except Exception as e:
                print(f'  ERR {table_name}: {e}')

if __name__ == '__main__':
    print('Creating SoulsLike Builder tables...')
    run()
    print('Done.')
