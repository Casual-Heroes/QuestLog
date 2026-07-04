"""
Seed sl_session_bosses reference data as a static boss registry table.
We store all bosses per game/mode so sessions can load them at creation.

This creates a NEW reference table sl_boss_registry separate from per-session data.

Run: chwebsiteprj/bin/python3 seed_soulslike_bosses_mortality.py
"""
import django, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# Tier constants matching EldenTracker
ENEMY       = "enemy"
GREAT_ENEMY = "great_enemy"
LEGEND      = "legend"
DEMIGOD     = "demigod"
GOD         = "god"

# ── Vanilla bosses (from EldenTracker bosses_vanilla.py) ─────────────────────
VANILLA_BOSSES = [
    # LIMGRAVE
    ("Soldier of Godrick",                "Fringefolk Hero's Grave",     "Limgrave",            ENEMY),
    ("Tree Sentinel",                     "Limgrave",                    "Limgrave",            GREAT_ENEMY),
    ("Flying Dragon Agheel",              "Limgrave",                    "Limgrave",            GREAT_ENEMY),
    ("Erdtree Burial Watchdog",           "Stormfoot Catacombs",         "Limgrave",            ENEMY),
    ("Stonedigger Troll",                 "Limgrave Tunnels",            "Limgrave",            ENEMY),
    ("Beastman of Farum Azula",           "Groveside Cave",              "Limgrave",            ENEMY),
    ("Demi-Human Chiefs",                 "Coastal Cave",                "Limgrave",            ENEMY),
    ("Bell Bearing Hunter",               "Warmaster's Shack",           "Limgrave",            GREAT_ENEMY),
    ("Grave Warden Duelist",              "Murkwater Catacombs",         "Limgrave",            ENEMY),
    ("Mad Pumpkin Head",                  "Waypoint Ruins",              "Limgrave",            ENEMY),
    ("Crucible Knight",                   "Stormhill Evergaol",          "Limgrave",            GREAT_ENEMY),
    ("Bloodhound Knight Darriwil",        "Forlorn Hound Evergaol",      "Limgrave",            GREAT_ENEMY),
    ("Night's Cavalry",                   "Limgrave",                    "Limgrave",            GREAT_ENEMY),
    ("Black Knife Assassin",              "Deathtouched Catacombs",      "Limgrave",            ENEMY),
    ("Tibia Mariner",                     "Summonwater Village",         "Limgrave",            ENEMY),
    ("Margit, the Fell Omen",             "Stormveil Castle Gate",       "Limgrave",            LEGEND),
    ("Ulcerated Tree Spirit",             "Fringefolk Hero's Grave",     "Limgrave",            GREAT_ENEMY),
    ("Deathbird",                         "Limgrave",                    "Limgrave",            ENEMY),
    ("Guardian Golem",                    "Highroad Cave",               "Limgrave",            ENEMY),
    ("Patches",                           "Murkwater Cave",              "Limgrave",            ENEMY),
    # STORMVEIL CASTLE
    ("Godrick the Grafted",               "Stormveil Castle",            "Stormveil Castle",    DEMIGOD),
    ("Grafted Scion",                     "Stormveil Castle",            "Stormveil Castle",    ENEMY),
    ("Pumpkin Head",                      "Stormveil Castle",            "Stormveil Castle",    ENEMY),
    ("Leonine Misbegotten",               "Stormveil Castle",            "Stormveil Castle",    GREAT_ENEMY),
    # WEEPING PENINSULA
    ("Erdtree Avatar",                    "Weeping Peninsula",           "Weeping Peninsula",   GREAT_ENEMY),
    ("Leonine Misbegotten",               "Castle Morne",                "Weeping Peninsula",   GREAT_ENEMY),
    ("Scaly Misbegotten",                 "Morne Tunnel",                "Weeping Peninsula",   ENEMY),
    ("Tombsward Cave Miranda",            "Tombsward Cave",              "Weeping Peninsula",   ENEMY),
    ("Cemetery Shade",                    "Tombsward Catacombs",         "Weeping Peninsula",   ENEMY),
    ("Erdtree Burial Watchdog",           "Impaler's Catacombs",         "Weeping Peninsula",   ENEMY),
    ("Runebear",                          "Earthbore Cave",              "Weeping Peninsula",   GREAT_ENEMY),
    ("Deathbird",                         "Weeping Peninsula",           "Weeping Peninsula",   ENEMY),
    # LIURNIA OF THE LAKES
    ("Rennala, Queen of the Full Moon",   "Raya Lucaria Academy",        "Liurnia of the Lakes",DEMIGOD),
    ("Red Wolf of Radagon",               "Raya Lucaria Academy",        "Liurnia of the Lakes",LEGEND),
    ("Crystallian Trio",                  "Raya Lucaria Crystal Tunnel", "Liurnia of the Lakes",GREAT_ENEMY),
    ("Tibia Mariner",                     "Liurnia of the Lakes",        "Liurnia of the Lakes",ENEMY),
    ("Bols, Carian Knight",               "Cuckoo's Evergaol",           "Liurnia of the Lakes",GREAT_ENEMY),
    ("Glintstone Dragon Smarag",          "Liurnia of the Lakes",        "Liurnia of the Lakes",GREAT_ENEMY),
    ("Royal Knight Loretta",              "Caria Manor",                 "Liurnia of the Lakes",LEGEND),
    ("Black Knife Assassin",              "Black Knife Catacombs",       "Liurnia of the Lakes",ENEMY),
    ("Cemetery Shade",                    "Black Knife Catacombs",       "Liurnia of the Lakes",ENEMY),
    ("Erdtree Burial Watchdog",           "Cliffbottom Catacombs",       "Liurnia of the Lakes",ENEMY),
    ("Erdtree Avatar",                    "Liurnia of the Lakes",        "Liurnia of the Lakes",GREAT_ENEMY),
    ("Bloodhound Knight",                 "Lakeside Crystal Cave",       "Liurnia of the Lakes",ENEMY),
    ("Adan, Thief of Fire",               "Malefactor's Evergaol",       "Liurnia of the Lakes",ENEMY),
    ("Omenkiller",                        "Village of the Albinaurics",  "Liurnia of the Lakes",GREAT_ENEMY),
    ("Magma Wyrm Makar",                  "Ruin-Strewn Precipice",       "Liurnia of the Lakes",LEGEND),
    ("Night's Cavalry",                   "Liurnia of the Lakes",        "Liurnia of the Lakes",GREAT_ENEMY),
    # CAELID
    ("Starscourge Radahn",                "Redmane Castle",              "Caelid",              DEMIGOD),
    ("Crucible Knight & Misbegotten",     "Redmane Castle",              "Caelid",              LEGEND),
    ("Commander O'Neil",                  "Aeonia Swamp",                "Caelid",              LEGEND),
    ("Decaying Ekzykes",                  "Caelid",                      "Caelid",              GREAT_ENEMY),
    ("Nox Swordstress & Nox Priest",      "Sellia, Town of Sorcery",     "Caelid",              ENEMY),
    ("Erdtree Avatar",                    "Caelid",                      "Caelid",              GREAT_ENEMY),
    ("Night's Cavalry",                   "Caelid",                      "Caelid",              GREAT_ENEMY),
    ("Putrid Crystallian Trio",           "Sellia Crystal Tunnel",       "Caelid",              GREAT_ENEMY),
    ("Cleanrot Knight",                   "Abandoned Cave",              "Caelid",              ENEMY),
    ("Battlemage Hugues",                 "Caelem Ruins",                "Caelid",              ENEMY),
    ("Cemetery Shade",                    "War-Dead Catacombs",          "Caelid",              ENEMY),
    ("Putrid Tree Spirit",                "War-Dead Catacombs",          "Caelid",              GREAT_ENEMY),
    # DRAGONBARROW
    ("Flying Dragon Greyll",              "Dragonbarrow",                "Dragonbarrow",        GREAT_ENEMY),
    ("Bell Bearing Hunter",               "Dragonbarrow",                "Dragonbarrow",        GREAT_ENEMY),
    ("Beastman of Farum Azula",           "Dragonbarrow Cave",           "Dragonbarrow",        GREAT_ENEMY),
    ("Farum Azula Dragon",                "Dragonbarrow",                "Dragonbarrow",        GREAT_ENEMY),
    ("Black Blade Kindred",               "Dragonbarrow",                "Dragonbarrow",        LEGEND),
    # ALTUS PLATEAU
    ("Erdtree Avatar",                    "Altus Plateau",               "Altus Plateau",       GREAT_ENEMY),
    ("Ancient Hero of Zamor",             "Sainted Hero's Grave",        "Altus Plateau",       GREAT_ENEMY),
    ("Elemer of the Briar",               "The Shaded Castle",           "Altus Plateau",       LEGEND),
    ("Stonedigger Troll",                 "Old Altus Tunnel",            "Altus Plateau",       ENEMY),
    ("Demi-Human Queen",                  "Altus Tunnel",                "Altus Plateau",       ENEMY),
    ("Wormface",                          "Altus Plateau",               "Altus Plateau",       GREAT_ENEMY),
    ("Night's Cavalry",                   "Altus Plateau",               "Altus Plateau",       GREAT_ENEMY),
    ("Cemetery Shade",                    "Unsightly Catacombs",         "Altus Plateau",       ENEMY),
    ("Perfumer Tricia & Misbegotten Warrior", "Unsightly Catacombs",     "Altus Plateau",       ENEMY),
    ("Erdtree Burial Watchdog",           "Altus Plateau",               "Altus Plateau",       ENEMY),
    ("Black Knife Assassin",              "Sage's Cave",                 "Altus Plateau",       ENEMY),
    ("Necromancer Garris",                "Sage's Cave",                 "Altus Plateau",       ENEMY),
    # MT. GELMIR
    ("Magma Wyrm",                        "Mt. Gelmir",                  "Mt. Gelmir",          LEGEND),
    ("Full-Grown Fallingstar Beast",      "Mt. Gelmir",                  "Mt. Gelmir",          LEGEND),
    ("Demi-Human Queen",                  "Volcano Cave",                "Mt. Gelmir",          ENEMY),
    ("Ulcerated Tree Spirit",             "Volcano Manor",               "Mt. Gelmir",          GREAT_ENEMY),
    ("Godskin Noble",                     "Volcano Manor",               "Mt. Gelmir",          LEGEND),
    ("Rykard, Lord of Blasphemy",         "Volcano Manor",               "Mt. Gelmir",          DEMIGOD),
    ("Abductor Virgins",                  "Volcano Manor",               "Mt. Gelmir",          LEGEND),
    ("Bloodhound Knight",                 "Gelmir Hero's Grave",         "Mt. Gelmir",          ENEMY),
    ("Cemetery Shade",                    "Gelmir Hero's Grave",         "Mt. Gelmir",          ENEMY),
    # LEYNDELL
    ("Godfrey, First Elden Lord (Golden)", "Leyndell",                   "Leyndell",            LEGEND),
    ("Morgott, the Omen King",            "Leyndell",                    "Leyndell",            DEMIGOD),
    ("Draconic Tree Sentinel",            "Leyndell",                    "Leyndell",            LEGEND),
    ("Fell Twins",                        "Leyndell",                    "Leyndell",            LEGEND),
    ("Omen",                              "Subterranean Shunning-Grounds","Leyndell",            ENEMY),
    ("Mohg, the Omen",                    "Subterranean Shunning-Grounds","Leyndell",            LEGEND),
    # FORBIDDEN LANDS / MOUNTAINTOPS
    ("Black Blade Kindred",               "Forbidden Lands",             "Mountaintops",        LEGEND),
    ("Night's Cavalry",                   "Mountaintops of the Giants",  "Mountaintops",        GREAT_ENEMY),
    ("Borealis the Freezing Fog",         "Mountaintops of the Giants",  "Mountaintops",        LEGEND),
    ("Ancient Hero of Zamor",             "Mountaintops of the Giants",  "Mountaintops",        GREAT_ENEMY),
    ("Erdtree Avatar",                    "Mountaintops of the Giants",  "Mountaintops",        GREAT_ENEMY),
    ("Fire Giant",                        "Mountaintops of the Giants",  "Mountaintops",        DEMIGOD),
    ("Crucible Knight & Misbegotten",     "Mountaintops of the Giants",  "Mountaintops",        LEGEND),
    ("Putrid Grave Warden Duelist",       "Giants' Mountaintop Catacombs","Mountaintops",        ENEMY),
    ("Ulcerated Tree Spirit",             "Giants' Mountaintop Catacombs","Mountaintops",        GREAT_ENEMY),
    ("Erdtree Burial Watchdog",           "Giant-Conquering Hero's Grave","Mountaintops",        ENEMY),
    # SNOWFIELD / HALIGTREE
    ("Loretta, Knight of the Haligtree",  "Miquella's Haligtree",        "Haligtree",           LEGEND),
    ("Malenia, Blade of Miquella",        "Elphael, Brace of the Haligtree","Haligtree",         GOD),
    ("Ulcerated Tree Spirit",             "Haligtree",                   "Haligtree",           GREAT_ENEMY),
    ("Putrid Avatar",                     "Consecrated Snowfield",       "Snowfield",           GREAT_ENEMY),
    ("Astel, Stars of Darkness",          "Yelough Anix Tunnel",         "Snowfield",           LEGEND),
    ("Night's Cavalry",                   "Consecrated Snowfield",       "Snowfield",           GREAT_ENEMY),
    ("Erdtree Avatar",                    "Consecrated Snowfield",       "Snowfield",           GREAT_ENEMY),
    # UNDERGROUND
    ("Ancestor Spirit",                   "Siofra River",                "Underground",         LEGEND),
    ("Valiant Gargoyle (Duo)",            "Siofra Aqueduct",             "Underground",         LEGEND),
    ("Crucible Knight Siluria",           "Deeproot Depths",             "Underground",         LEGEND),
    ("Lichdragon Fortissax",              "Deeproot Depths",             "Underground",         LEGEND),
    ("Dragonkin Soldier",                 "Siofra River",                "Underground",         LEGEND),
    ("Dragonkin Soldier of Nokstella",    "Ainsel River",                "Underground",         LEGEND),
    ("Astel, Naturalborn of the Void",    "Grand Cloister",              "Underground",         LEGEND),
    ("Mohg, Lord of Blood",               "Mohgwyn Palace",              "Underground",         DEMIGOD),
    ("Bloodhound Knight",                 "Mohgwyn Palace",              "Underground",         ENEMY),
    ("Red Wolf of the Champion",          "Gelmir Hero's Grave",         "Underground",         LEGEND),
    # FARUM AZULA
    ("Godskin Duo",                       "Crumbling Farum Azula",       "Farum Azula",         LEGEND),
    ("Maliketh, the Black Blade",         "Crumbling Farum Azula",       "Farum Azula",         DEMIGOD),
    ("Dragonlord Placidusax",             "Crumbling Farum Azula",       "Farum Azula",         GOD),
    ("Beast Clergyman",                   "Crumbling Farum Azula",       "Farum Azula",         LEGEND),
    # ASHEN LEYNDELL / ELDEN THRONE
    ("Sir Gideon Ofnir, the All-Knowing", "Leyndell, Ashen Capital",     "Ashen Leyndell",      LEGEND),
    ("Godfrey, First Elden Lord",         "Leyndell, Ashen Capital",     "Ashen Leyndell",      DEMIGOD),
    ("Radagon of the Golden Order",       "Elden Throne",                "Elden Throne",        GOD),
    ("Elden Beast",                       "Elden Throne",                "Elden Throne",        GOD),
]

# ── DLC bosses (Shadow of the Erdtree) ───────────────────────────────────────
DLC_BOSSES = [
    ("Divine Beast Dancing Lion",         "Shadow Keep",                 "Shadow of the Erdtree", DEMIGOD),
    ("Rellana, Twin Moon Knight",         "Castle Ensis",                "Shadow of the Erdtree", DEMIGOD),
    ("Putrescent Knight",                 "Stone Coffin Fissure",        "Shadow of the Erdtree", LEGEND),
    ("Scadutree Avatar",                  "Shadow of the Erdtree",       "Shadow of the Erdtree", DEMIGOD),
    ("Commander Gaius",                   "Moorth Highway",              "Shadow of the Erdtree", DEMIGOD),
    ("Messmer the Impaler",               "Shadow Keep",                 "Shadow of the Erdtree", DEMIGOD),
    ("Romina, Saint of the Bud",          "Church of the Bud",           "Shadow of the Erdtree", DEMIGOD),
    ("Bayle the Dread",                   "Jagged Peak",                 "Shadow of the Erdtree", GOD),
    ("Midra, Lord of Frenzied Flame",     "Ruins of Unte",               "Shadow of the Erdtree", DEMIGOD),
    ("Metyr, Mother of Fingers",          "Shadow of the Erdtree",       "Shadow of the Erdtree", DEMIGOD),
    ("Needle Knight Leda",                "Shadow of the Erdtree",       "Shadow of the Erdtree", LEGEND),
    ("Promised Consort Radahn",           "Enir-Ilim",                   "Shadow of the Erdtree", GOD),
    ("Furnace Golem",                     "Shadow of the Erdtree",       "Shadow of the Erdtree", GREAT_ENEMY),
    ("Death Knight",                      "Shadow of the Erdtree",       "Shadow of the Erdtree", GREAT_ENEMY),
    ("Lamenter",                          "Shadow of the Erdtree",       "Shadow of the Erdtree", LEGEND),
    ("Golden Hippopotamus",               "Shadow Keep",                 "Shadow of the Erdtree", LEGEND),
    ("Ghostflame Dragon",                 "Shadow of the Erdtree",       "Shadow of the Erdtree", GREAT_ENEMY),
    ("Gloom-Eyed Queen, Marigga",         "Shadow of the Erdtree",       "Shadow of the Erdtree", LEGEND),
    ("Ralva the Great Red Bear",          "Shadow of the Erdtree",       "Shadow of the Erdtree", GREAT_ENEMY),
    ("Black Knight Edredd",               "Shadow of the Erdtree",       "Shadow of the Erdtree", GREAT_ENEMY),
    ("Jori, Elder Inquisitor",            "Shadow of the Erdtree",       "Shadow of the Erdtree", LEGEND),
    ("Demi-Human Swordmaster Onze",       "Shadow of the Erdtree",       "Shadow of the Erdtree", ENEMY),
]

# ── ERR replacements/additions ───────────────────────────────────────────────
ERR_REPLACED_KEYS = {
    "Soldier of Godrick (Fringefolk Hero's Grave)",
    "Crucible Knight & Misbegotten (Redmane Castle)",
    "Leonine Misbegotten (Castle Morne)",
    "Valiant Gargoyle (Duo) (Siofra Aqueduct)",
    "Ancient Hero of Zamor (Sainted Hero's Grave)",
    "Adan, Thief of Fire (Malefactor's Evergaol)",
}

ERR_NEW_BOSSES = [
    ("Crucible Knight Rhyacis",           "Gilded Cave of Knowledge",    "Limgrave",            GREAT_ENEMY),
    ("Fallen Cavalry",                    "Northern Limgrave",           "Limgrave",            GREAT_ENEMY),
    ("Dismounted Tree Sentinel",          "Bridge of Sacrifice",         "Weeping Peninsula",   GREAT_ENEMY),
    ("Fulminating Runebear",              "Liurnia of the Lakes",        "Liurnia of the Lakes",GREAT_ENEMY),
    ("Thief-Taker Acacio",               "Malefactor's Evergaol",       "Liurnia of the Lakes",ENEMY),
    ("Crucible Knight Hirnan",            "Four Belfries",               "Liurnia of the Lakes",LEGEND),
    ("Azash, Pride of the Redmanes",      "Redmane Castle",              "Caelid",              LEGEND),
    ("Morion, the Unbound Death",         "Farum Greatbridge",           "Dragonbarrow",        LEGEND),
    ("Flamelost Knight",                  "Serpentine Depths",           "Mt. Gelmir",          LEGEND),
    ("Fellthorn Spirit",                  "Giant's Gravepost",           "Mt. Gelmir",          GREAT_ENEMY),
    ("Royal Guardian Helicos",            "Erdtree Sanctuary",           "Leyndell",            LEGEND),
    ("Equilibrious Beast",                "Subterranean Shunning-Grounds","Leyndell",            DEMIGOD),
    ("Hallowed Avatar",                   "Erdtree (Post-Game)",         "Leyndell",            GOD),
    ("Grave Sentinel Wyngrant",           "Sainted Hero's Grave",        "Altus Plateau",       GREAT_ENEMY),
    ("Gnoster, the False Sky",            "Siofra Aqueduct",             "Underground",         LEGEND),
    ("Nox Nightmaiden",                   "Night's Sacred Ground",       "Underground",         GREAT_ENEMY),
    ("Fulghor, Champion of Rauh",         "Ancient Ruins of Rauh",       "Shadow of the Erdtree",LEGEND),
]

def make_key(name, location):
    return f"{name} ({location})"

def build_err_list():
    filtered = [b for b in VANILLA_BOSSES + DLC_BOSSES
                if make_key(b[0], b[1]) not in ERR_REPLACED_KEYS]
    return filtered + ERR_NEW_BOSSES


def seed_registry():
    with engine.begin() as conn:
        # Create registry table if not exists
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS sl_boss_registry (
                id        INT AUTO_INCREMENT PRIMARY KEY,
                game      VARCHAR(32)  NOT NULL,
                game_mode VARCHAR(32)  NOT NULL,
                boss_key  VARCHAR(200) NOT NULL,
                boss_name VARCHAR(100) NOT NULL,
                location  VARCHAR(100) NOT NULL,
                region    VARCHAR(50)  NOT NULL,
                tier      VARCHAR(20)  NOT NULL,
                sort_order INT DEFAULT 0,
                UNIQUE KEY uq_boss (game, game_mode, boss_key(190)),
                INDEX idx_game_mode (game, game_mode)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        '''))

        # Clear and reseed
        conn.execute(text('DELETE FROM sl_boss_registry WHERE game="elden_ring"'))

        # Vanilla (includes DLC)
        vanilla_all = VANILLA_BOSSES + DLC_BOSSES
        for i, (name, location, region, tier) in enumerate(vanilla_all):
            key = make_key(name, location)
            conn.execute(text('''
                INSERT INTO sl_boss_registry (game, game_mode, boss_key, boss_name, location, region, tier, sort_order)
                VALUES ("elden_ring", "vanilla", :key, :name, :loc, :region, :tier, :ord)
                ON DUPLICATE KEY UPDATE boss_name=:name, location=:loc, region=:region, tier=:tier
            '''), {'key': key, 'name': name, 'loc': location, 'region': region, 'tier': tier, 'ord': i})

        v_count = len(vanilla_all)
        print(f'Seeded {v_count} ER vanilla+DLC bosses')

        # ERR
        err_all = build_err_list()
        for i, (name, location, region, tier) in enumerate(err_all):
            key = make_key(name, location)
            conn.execute(text('''
                INSERT INTO sl_boss_registry (game, game_mode, boss_key, boss_name, location, region, tier, sort_order)
                VALUES ("elden_ring", "err", :key, :name, :loc, :region, :tier, :ord)
                ON DUPLICATE KEY UPDATE boss_name=:name, location=:loc, region=:region, tier=:tier
            '''), {'key': key, 'name': name, 'loc': location, 'region': region, 'tier': tier, 'ord': i})

        e_count = len(err_all)
        print(f'Seeded {e_count} ERR bosses')

        # Verify
        counts = conn.execute(text('SELECT game_mode, COUNT(*) FROM sl_boss_registry WHERE game="elden_ring" GROUP BY game_mode')).fetchall()
        for row in counts:
            print(f'  elden_ring/{row[0]}: {row[1]} bosses')

if __name__ == '__main__':
    seed_registry()
    print('Done')
