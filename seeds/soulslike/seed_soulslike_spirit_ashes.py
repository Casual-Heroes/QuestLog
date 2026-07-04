"""
Seed sl_spirit_ashes for both elden_ring and err.
ER: full list from wiki (base + DLC).
ERR: all ER ashes carry over + 8 new ERR-exclusive ashes.

Run: chwebsiteprj/bin/python3 seed_soulslike_spirit_ashes.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text
import time

engine = get_engine()

# ER spirit ashes - inventory_order, name, description, fp_cost, summon_type, acquisition
# summon_type: 'grave' = Grave Gloveworts, 'ghost' = Ghost Gloveworts
ER_ASHES = [
    (1,  'Wandering Noble Ashes',            'Summons five zombies that engage enemies in melee combat', 28,   'grave', 'Base game'),
    (2,  'Noble Sorcerer Ashes',             'Summons noble sorcerer spirit',                            11,   'grave', 'Base game'),
    (3,  'Nomad Ashes',                      'Summons nomad spirit',                                     61,   'grave', 'Base game'),
    (4,  'Putrid Corpse Ashes',              'Summons four putrid corpse spirits',                       40,   'grave', 'Base game'),
    (5,  'Skeletal Militiaman Ashes',        'Summons two skeletal militiaman spirits',                  44,   'grave', 'Base game'),
    (6,  'Skeletal Bandit Ashes',            'Summons skeletal bandit spirit',                           22,   'grave', 'Base game'),
    (7,  'Albinauric Ashes',                 'Summons two Albinauric spirits',                           53,   'grave', 'Base game'),
    (8,  'Winged Misbegotten Ashes',         'Summons winged misbegotten spirit',                        37,   'grave', 'Base game'),
    (9,  'Demi-Human Ashes',                 'Summons five demi-human spirits',                          69,   'grave', 'Base game'),
    (10, 'Clayman Ashes',                    'Summons two clayman spirits',                              77,   'grave', 'Base game'),
    (11, 'Oracle Envoy Ashes',               'Summons four Oracle Envoy spirits',                        72,   'grave', 'Base game'),
    (12, 'Man-Fly Ashes',                    'Summons three man-fly spirits',                            29,   'grave', 'Shadow of the Erdtree DLC'),
    (13, 'Lone Wolf Ashes',                  'Summons three lone wolf spirits',                          55,   'grave', 'Base game'),
    (14, 'Rotten Stray Ashes',               'Summons rotten stray spirit',                              35,   'grave', 'Base game'),
    (15, 'Giant Rat Ashes',                  'Summons three giant rat spirits',                          0,    'grave', 'Base game'),
    (16, 'Warhawk Ashes',                    'Summons warhawk spirit',                                   52,   'grave', 'Base game'),
    (17, 'Land Squirt Ashes',                'Summon three land squirts',                                240,  'grave', 'Base game'),
    (18, 'Spirit Jellyfish Ashes',           'Summons spirit jellyfish',                                 31,   'grave', 'Base game'),
    (19, 'Miranda Sprout Ashes',             'Summon five miranda sprout spirits',                       185,  'grave', 'Base game'),
    (20, 'Spider Scorpion Ashes',            'Summons spider scorpion spirit',                           41,   'grave', 'Shadow of the Erdtree DLC'),
    (21, 'Fingercreeper Ashes',              'Summons Fingercreeper spirit',                             80,   'grave', 'Shadow of the Erdtree DLC'),
    (22, 'Fanged Imp Ashes',                 'Summons two fanged imp spirits',                           50,   'grave', 'Base game'),
    (23, 'Bigmouth Imp Ashes',               'Summons bigmouth imp spirit',                              50,   'grave', 'Shadow of the Erdtree DLC'),
    (24, 'Gravebird Ashes',                  'Summons Gravebird spirit',                                 52,   'grave', 'Shadow of the Erdtree DLC'),
    (25, 'Soldjars of Fortune Ashes',        'Summons three little living jar spirits',                  135,  'grave', 'Base game'),
    (26, 'Archer Ashes',                     'Summons three archer spirits',                             57,   'grave', 'Base game'),
    (27, 'Greatshield Soldier Ashes',        'Summons five greatshield soldier spirits',                 74,   'grave', 'Base game'),
    (28, 'Page Ashes',                       'Summons page spirit',                                      81,   'grave', 'Base game'),
    (29, 'Vulgar Militia Ashes',             'Summons three vulgar militia spirits',                     70,   'grave', 'Base game'),
    (30, 'Marionette Soldier Ashes',         'Summons two marionette soldier spirits',                   67,   'grave', 'Base game'),
    (31, 'Avionette Soldier Ashes',          'Summon the spirits of two avionette soldiers',             67,   'grave', 'Base game'),
    (32, 'Kaiden Sellsword Ashes',           'Summons Kaiden sellsword spirit',                          88,   'grave', 'Base game'),
    (33, 'Mad Pumpkin Head Ashes',           'Summon the spirit of a mad pumpkin head',                  110,  'grave', 'Base game'),
    (34, 'Fire Monk Ashes',                  'Summons Fire Monk spirit',                                 85,   'grave', 'Base game'),
    (35, 'Ancestral Follower Ashes',         'Summons ancestral follower spirit',                        63,   'grave', 'Base game'),
    (36, 'Horned Warrior Ashes',             'Summons horned warrior spirit',                            112,  'grave', 'Shadow of the Erdtree DLC'),
    (37, 'Azula Beastman Ashes',             'Summons two Azula beastman spirits',                       102,  'grave', 'Base game'),
    (38, 'Man-Serpent Ashes',                'Summons man-serpent spirit',                               62,   'grave', 'Base game'),
    (39, 'Crystalian Ashes',                 'Summons Crystalian spirit',                                101,  'grave', 'Base game'),
    (40, 'Kindred of Rot Ashes',             'Summons Kindred of Rot spirit',                            73,   'grave', 'Base game'),
    (41, 'Bloodfiend Hexer\'s Ashes',        'Summons bloodfiend hexer spirit',                          500,  'grave', 'Shadow of the Erdtree DLC'),
    (42, 'Glintstone Sorcerer Ashes',        'Summons glintstone sorcerer spirit',                       49,   'grave', 'Base game'),
    (43, 'Twinsage Sorcerer Ashes',          'Summons Twinsage sorcerer spirit',                         89,   'grave', 'Base game'),
    (44, 'Inquisitor Ashes',                 'Summons two inquisitor spirits',                           93,   'grave', 'Shadow of the Erdtree DLC'),
    (45, 'Godrick Soldier Ashes',            'Summons two Godrick soldier spirits',                      54,   'grave', 'Base game'),
    (46, 'Raya Lucaria Soldier Ashes',       'Summons three Raya Lucaria soldier spirits',               59,   'grave', 'Base game'),
    (47, 'Leyndell Soldier Ashes',           'Summons two Leyndell soldier spirits',                     64,   'grave', 'Base game'),
    (48, 'Radahn Soldier Ashes',             'Summons two Radahn Soldier spirits',                       71,   'grave', 'Base game'),
    (49, 'Haligtree Soldier Ashes',          'Summons four Haligtree soldier spirits',                   66,   'grave', 'Base game'),
    (50, 'Mausoleum Soldier Ashes',          'Summons five mausoleum soldier spirits',                   75,   'grave', 'Base game'),
    (51, 'Messmer Soldier Ashes',            'Summons two Messmer soldier spirits',                      72,   'grave', 'Shadow of the Erdtree DLC'),
    (52, 'Stormhawk Deenh',                  'Summons spirit of Stormhawk Deenh',                        47,   'ghost', 'Base game'),
    (53, 'Banished Knight Oleg Ashes',       'Summons spirit of Banished Knight Oleg',                   100,  'ghost', 'Base game'),
    (54, 'Banished Knight Engvall Ashes',    'Summons spirit of Banished Knight Engvall',                100,  'ghost', 'Base game'),
    (55, 'Bloodhound Knight Floh',           'Summons spirit of Bloodhound Knight Floh',                 95,   'ghost', 'Base game'),
    (56, 'Black Knight Captain Huw',         'Summons spirit of Black Knight Captain Huw',               106,  'ghost', 'Shadow of the Erdtree DLC'),
    (57, 'Black Knight Commander Andreas',   'Summons spirit of Black Knight Commander Andreas',         111,  'ghost', 'Shadow of the Erdtree DLC'),
    (58, 'Fire Knight Hilde',                'Summons spirit of Fire Knight Hilde',                      116,  'ghost', 'Shadow of the Erdtree DLC'),
    (59, 'Fire Knight Queelign',             'Summons spirit of Fire Knight Queelign',                   123,  'ghost', 'Shadow of the Erdtree DLC'),
    (60, 'Swordhand of Night Jolán',         'Summons spirit of Swordhand of Night Jolán',               86,   'ghost', 'Shadow of the Erdtree DLC'),
    (61, 'Jolán and Anna',                   'Summons spirits of Jolán and Anna',                        144,  'ghost', 'Shadow of the Erdtree DLC'),
    (62, 'Battlemage Hugues Ashes',          'Summons spirit of Battlemage Hugues',                      122,  'ghost', 'Base game'),
    (63, 'Latenna the Albinauric',           'Summons spirit of Latenna the Albinauric',                 74,   'ghost', 'Base game'),
    (64, 'Perfumer Tricia',                  'Summons spirit of Perfumer Tricia',                        78,   'ghost', 'Base game'),
    (65, 'Depraved Perfumer Carmaan Ashes',  'Summons spirit of Depraved Perfumer Carmaan',              124,  'ghost', 'Base game'),
    (66, 'Omenkiller Rollo',                 'Summons the spirit of Omenkiller Rollo',                   113,  'ghost', 'Base game'),
    (67, 'Blackflame Monk Amon Ashes',       'Summons spirit of Blackflame Monk Amon',                   115,  'ghost', 'Base game'),
    (68, 'Curseblade Meera',                 'Summons spirit of Curseblade Meera',                       91,   'ghost', 'Shadow of the Erdtree DLC'),
    (69, 'Demi-Human Swordsman Yosh',        'Summons spirit of Demi-Human Swordsman Yosh',              129,  'ghost', 'Shadow of the Erdtree DLC'),
    (70, 'Ancient Dragon Knight Kristoff Ashes', 'Summons spirit of Ancient Dragon Knight Kristoff',     108,  'ghost', 'Base game'),
    (71, 'Redmane Knight Ogha Ashes',        'Summons spirit of Redmane Knight Ogha',                    106,  'ghost', 'Base game'),
    (72, 'Lhutel the Headless',              'Summons spirit of Lhutel the Headless',                    104,  'ghost', 'Base game'),
    (73, 'Cleanrot Knight Finlay Ashes',     'Summons spirit of Cleanrot Knight Finlay',                 127,  'ghost', 'Base game'),
    (74, 'Black Knife Tiche',                'Summons spirit of Black Knife Tiche',                      132,  'ghost', 'Base game'),
    (75, 'Divine Bird Warrior Ornis',        'Summons spirit of Divine Bird Warrior Ornis',              131,  'ghost', 'Shadow of the Erdtree DLC'),
    (76, 'Taylew the Golem Smith',           'Summons spirit of Taylew the Golem Smith',                 138,  'ghost', 'Shadow of the Erdtree DLC'),
    (77, 'Ancient Dragon Florissax',         'Summons spirit of Ancient Dragon Florissax',               85,   'ghost', 'Shadow of the Erdtree DLC'),
    (78, 'Mimic Tear Ashes',                 'Summons mimic tear spirit',                                660,  'ghost', 'Base game'),
    (79, 'Finger Maiden Therolina Puppet',   'Summons spirit of Finger Maiden Therolina',               82,   'ghost', 'Base game'),
    (80, 'Jarwight Puppet',                  'Summons Jarwight spirit',                                  60,   'ghost', 'Base game'),
    (81, 'Dolores the Sleeping Arrow Puppet','Summons spirit of Dolores the Sleeping Arrow',             87,   'ghost', 'Base game'),
    (82, 'Nepheli Loux Puppet',              'Summons spirit of Nepheli Loux',                           90,   'ghost', 'Base game'),
    (83, 'Dung Eater Puppet',                'Summons spirit of the Dung Eater',                         118,  'ghost', 'Base game'),
    (84, 'Nightmaiden & Swordstress Puppets','Summons nightmaiden & swordstress spirits',                97,   'ghost', 'Base game'),
]

# ERR-exclusive new spirit ashes
ERR_NEW_ASHES = [
    ('Blaidd',                'Summons spirit of Blaidd the Half-Wolf. Two Crimson Flasks, inflicts frostbite.',    740,  'ghost', 'Complete Blaidd\'s questline - top of Ranni\'s Rise', 1480),
    ('Glintstone Miner Ashes','Summons two glintstone miner spirits. One uses Rock Blaster, other casts sorceries.',520, 'grave', 'Found inside the Altus Tunnel', 1040),
    ('Grand Inquisitor Eli',  'Summons Grand Inquisitor Eli and four hornsent inquisitors.',                        980,  'ghost', 'Trade Elder Inquisitor Jori\'s Remembrance with Enia', 1960),
    ('Latenna and Lobo',      'Summons spirits of Latenna and Lobo. Latenna as magic archer, Lobo as wolf mount.',  770,  'ghost', 'End of Latenna\'s questline at Apostate Derelict', 1540),
    ('Lazuli Sorcerer',       'Summons Lazuli sorcerer spirit.',                                                    None, 'grave', 'Unknown', None),
    ('Ringmaster Ophidion',   'Summons spirit of Ringmaster Ophidion.',                                             630,  'ghost', 'Serpentine Depths, guarded by Colossal Fingercreeper', 1260),
    ('Starcaller Ashes',      'Summons two starcaller spirits. One melee, one gravity ranged.',                     340,  'grave', 'Found in Starcaller area', 680),
]


def run():
    now = int(time.time())
    with engine.begin() as conn:
        # Clear existing
        conn.execute(text('DELETE FROM sl_spirit_ashes WHERE game IN ("elden_ring","err")'))

        # Seed ER ashes
        for inv_order, name, desc, fp, summon_type, acq in ER_ASHES:
            conn.execute(text("""
                INSERT INTO sl_spirit_ashes
                    (game, name, description, fp_cost, summon_type, acquisition_detail, is_new_to_err, created_at)
                VALUES ('elden_ring', :name, :desc, :fp, :stype, :acq, 0, :ts)
            """), {'name': name, 'desc': desc, 'fp': fp or 0, 'stype': summon_type, 'acq': acq, 'ts': now})

        print(f'Seeded {len(ER_ASHES)} ER spirit ashes')

        # Seed ERR: all ER ashes carry over + new ones
        for inv_order, name, desc, fp, summon_type, acq in ER_ASHES:
            conn.execute(text("""
                INSERT INTO sl_spirit_ashes
                    (game, name, description, fp_cost, summon_type, acquisition_detail, is_new_to_err, created_at)
                VALUES ('err', :name, :desc, :fp, :stype, :acq, 0, :ts)
            """), {'name': name, 'desc': desc, 'fp': fp or 0, 'stype': summon_type, 'acq': acq, 'ts': now})

        # ERR-exclusive new ashes
        for name, desc, fp, summon_type, acq, enrage_fp in ERR_NEW_ASHES:
            conn.execute(text("""
                INSERT INTO sl_spirit_ashes
                    (game, name, description, fp_cost, enrage_fp_cost, summon_type, acquisition_detail, is_new_to_err, created_at)
                VALUES ('err', :name, :desc, :fp, :efp, :stype, :acq, 1, :ts)
            """), {'name': name, 'desc': desc, 'fp': fp or 0, 'efp': enrage_fp,
                   'stype': summon_type, 'acq': acq, 'ts': now})

        print(f'Seeded {len(ER_ASHES) + len(ERR_NEW_ASHES)} ERR spirit ashes ({len(ERR_NEW_ASHES)} new)')

        # Verify
        er = conn.execute(text('SELECT COUNT(*) FROM sl_spirit_ashes WHERE game="elden_ring"')).fetchone()[0]
        err = conn.execute(text('SELECT COUNT(*) FROM sl_spirit_ashes WHERE game="err"')).fetchone()[0]
        print(f'Final: ER={er}, ERR={err}')


if __name__ == '__main__':
    run()
