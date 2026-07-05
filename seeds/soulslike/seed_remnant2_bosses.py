"""
Seed r2_bosses with all Remnant 2 bosses, world bosses, and aberrations.
Data sourced from: https://remnant2.wiki.gg/wiki/Bestiary

boss_type values:
  'boss'       - optional dungeon boss
  'world_boss' - mandatory world boss
  'aberration' - empowered enemy variant

Run: chwebsiteprj/bin/python3 seed_remnant2_bosses.py
"""
import django, os, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

NOW = int(time.time())

# (name, boss_type, world, zone, is_optional, dlc, drop_notes)
BOSSES = [

    # ── Optional Dungeon Bosses ──────────────────────────────────────────────

    # N'Erud
    ('The Astropath',       'boss', 'N\'Erud',    'Astropath\'s Respite',     1, 'base',  'Seeker Residue (Helix Mod)'),
    ('Abomination',         'boss', 'N\'Erud',    'The Putrid Domain',        1, 'base',  'Mutated Growth (Bore Mod)'),
    ('Custodian\'s Eye',    'boss', 'N\'Erud',    'Spectrum Nexus',           1, 'base',  'Sentry\'s Old Iris (Prismatic Driver Mod)'),
    ('Primogenitor',        'boss', 'N\'Erud',    'The Hatchery',             1, 'base',  'Cracked Shell (Space Crabs Mod)'),
    ('N\'Erudian Reaper',   'boss', 'N\'Erud',    'Detritus Foundry',         1, 'dlc3',  'Replication Pod (Harvester Bots Mod)'),
    ('The Amalgam Duo',     'boss', 'N\'Erud',    'Mucid Terrarium',          1, 'dlc3',  None),

    # Yaesha
    ('Kaeula\'s Shadow',    'boss', 'Yaesha',     'Kaeula\'s Rest',           1, 'base',  'Twilight Dactylus (Rootlash Mod)'),
    ('Legion',              'boss', 'Yaesha',     'The Twisted Chantry',      1, 'base',  'Agnosia Driftwood (Fargazer Mod)'),
    ('Mother Mind',         'boss', 'Yaesha',     'The Nameless Nest',        1, 'base',  'Cordyceps Gland (Tremor Mod)'),
    ('Shrewd',              'boss', 'Yaesha',     'The Expanding Glade',      1, 'base',  'Soul Sliver (Rotted Arrow Mod)'),
    ('Cinderclad Forge',    'boss', 'Yaesha',     'Deserted Atelier',         1, 'dlc2',  'Forge Ember (Heatwave Mod)'),
    ('The Stonewarden',     'boss', 'Yaesha',     'Earthen Coliseum',         1, 'dlc2',  'Pallid Lodestone (Abrasive Rounds Mod)'),

    # Losomn
    ('Bloat King',          'boss', 'Losomn',     'The Great Sewers',         1, 'base',  'Bone Sap (Voltaic Rondure Mod)'),
    ('Gwendil: The Unburnt','boss', 'Losomn',     'Cotton\'s Kiln',           1, 'base',  'Alkahest Powder (Witchfire Mod)'),
    ('The Huntress',        'boss', 'Losomn',     'Briella\'s Garden',        1, 'base',  'Venerated Spearhead (Huntress Spear), Sacred Hunt Feather (Familiar Mod)'),
    ('The Red Prince',      'boss', 'Losomn',     'Gilded Chambers',          1, 'base',  'Forlorn Fragment (Firestorm Mod), Bloody Steel Splinter (Blood Draw Mod), Crown of the Red Prince'),
    ('Magister Dullain',    'boss', 'Losomn',     'Shattered Gallery',        1, 'base',  'Tainted Ichor (Corrosive Rounds Mod)'),
    ('Bruin, Blade of the King', 'boss', 'Losomn','Glistering Cloister',     1, 'dlc1',  'Wretched Skull (Ring of Spears Mod)'),
    ('The Sunken Witch',    'boss', 'Losomn',     'Sunken Haunt',             1, 'dlc1',  'Hex Wreath (Creeping Mist Mod)'),

    # Root Earth
    ('Cancer',              'boss', 'Root Earth', 'Ashen Wasteland',          1, 'base',  None),
    ('Venom',               'boss', 'Root Earth', 'Corrupted Harbor',         1, 'base',  'Dread Core (Skewer 2.0 Mod)'),

    # ── World Bosses (mandatory) ─────────────────────────────────────────────

    # N'Erud
    ('Sha\'Hala',           'world_boss', 'N\'Erud',   'Sentinel\'s Keep',    0, 'base',  'Eidolon Shard (Spectral Blade), Void Cinder (Aphelion), Void Heart, Embrace of Sha\'Hala'),
    ('Tal\'Ratha',          'world_boss', 'N\'Erud',   'Tal\'Ratha\'s Refuge',0, 'base',  'Spiced Bile (Nebula), Shining Essence Echo (Void Idol), Acidic Jawbone (Gas Giant)'),
    ('Alepsis-Taura',       'world_boss', 'N\'Erud',   'Alepsis-Taura',       0, 'dlc3',  None),

    # Yaesha
    ('Corrupted Ravager',   'world_boss', 'Yaesha',    'Ravager\'s Lair',     0, 'base',  'Ravager\'s Maw (Feral Judgement), Doe\'s Antler (Red Doe Staff), Crimson Membrane (Merciless), Ravager\'s Mark'),
    ('Corruptor',           'world_boss', 'Yaesha',    'The Great Bole',      0, 'base',  'Twisted Lazurite (Twisted Arbalest), Hollow Heart (Stonebreaker)'),
    ('Lydusa',              'world_boss', 'Yaesha',    'Luminous Vale',       0, 'dlc2',  'Eye of Lydusa (Monolith), Blossoming Core (Mirage), Tear of Lydusa'),

    # Losomn
    ('The Nightweaver',     'world_boss', 'Losomn',    'Tormented Asylum',    0, 'base',  'Nightfall, Nightshade'),
    ('Faelin / Faerin',     'world_boss', 'Losomn',    'Beatific/Malefic Gallery', 0, 'base', 'Imposter\'s Heart (Deceit), Melded Hilt (Godsplitter), Faerin\'s Sigil, Faelin\'s Sigil'),
    ('The One True King',   'world_boss', 'Losomn',    'Palace of the One True King', 0, 'dlc1', None),

    # Root Earth
    ('Annihilation',        'world_boss', 'Root Earth','Blackened Citadel',   0, 'base',  'Forgotten Memory (Alpha/Omega), Broken Compass (Golden Compass), Scholar trait'),

    # Labyrinth
    ('Labyrinth Sentinel',  'world_boss', 'Labyrinth', 'Labyrinth',           0, 'base',  'Conflux Prism (Cube Gun)'),

    # ── Aberrations ──────────────────────────────────────────────────────────

    # Standard aberrations
    ('Astral Harvester',    'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('Atrophy',             'aberration', 'Yaesha',    None, 1, 'base', None),
    ('Bane',                'aberration', 'Root Earth',None, 1, 'base', None),
    ('Barghest the Vile',   'aberration', 'Losomn',    None, 1, 'base', None),
    ('Bastion',             'aberration', 'Labyrinth', None, 1, 'base', None),
    ('Charred Sentry',      'aberration', 'Yaesha',    None, 1, 'base', None),
    ('Cursed Wretch',       'aberration', 'Losomn',    None, 1, 'base', None),
    ('Defiler',             'aberration', 'Yaesha',    None, 1, 'base', None),
    ('Dire Fiend',          'aberration', 'Losomn',    None, 1, 'base', None),
    ('E.D. Alpha',          'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('Fester',              'aberration', 'Yaesha',    None, 1, 'base', None),
    ('Fetid Corpse',        'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('Firth: The Oathkeeper','aberration','Losomn',    None, 1, 'base', None),
    ('Gorecarver',          'aberration', 'Losomn',    None, 1, 'base', None),
    ('Gorge',               'aberration', 'Losomn',    None, 1, 'base', None),
    ('Inverted Shambler',   'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('Little Gorge',        'aberration', 'Losomn',    None, 1, 'base', None),

    # Roaming aberrations
    ('Abyssal Dreadnought', 'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('Arcanum Diviner',     'aberration', 'Losomn',    None, 1, 'base', None),
    ('Befouled Larva',      'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('Blightspawn',         'aberration', 'Losomn',    None, 1, 'base', None),
    ('C.E. Sigma',          'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('C.E. Theta',          'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('Deathsower',          'aberration', 'Yaesha',    None, 1, 'base', None),
    ('Deceitful Augur',     'aberration', 'Yaesha',    None, 1, 'base', None),
    ('Desolate Stalker',    'aberration', 'Yaesha',    None, 1, 'base', None),
    ('E.D.V.A',             'aberration', 'N\'Erud',   None, 1, 'base', None),
    ('Emberkeeper',         'aberration', 'Losomn',    None, 1, 'base', None),
    ('Emberwatcher',        'aberration', 'Losomn',    None, 1, 'base', None),
    ('Flintblade Marauder', 'aberration', 'Losomn',    None, 1, 'base', None),
    ('Flintblade Prowler',  'aberration', 'Losomn',    None, 1, 'base', None),
    ('Goreglut',            'aberration', 'Yaesha',    None, 1, 'base', None),
    ('Grimshot',            'aberration', 'Losomn',    None, 1, 'base', None),
    ('Highborn Stalker',    'aberration', 'Losomn',    None, 1, 'base', None),
    ('Lichwing',            'aberration', 'Yaesha',    None, 1, 'base', None),
]


def main():
    with get_db_session() as db:
        existing = db.execute(text('SELECT COUNT(*) FROM r2_bosses')).scalar()
        if existing > 0:
            print(f'WARNING: {existing} bosses already exist. Delete first to re-seed.')
            return

        inserted = 0
        for (name, boss_type, world, zone, is_optional, dlc, drop_notes) in BOSSES:
            db.execute(text("""
                INSERT INTO r2_bosses
                    (name, boss_type, world, zone, is_optional, dlc, drop_notes, created_at)
                VALUES
                    (:name, :boss_type, :world, :zone, :is_optional, :dlc, :drop_notes, :now)
            """), {
                'name': name, 'boss_type': boss_type, 'world': world,
                'zone': zone, 'is_optional': is_optional, 'dlc': dlc,
                'drop_notes': drop_notes, 'now': NOW,
            })
            inserted += 1

        db.commit()
        print(f'Inserted {inserted} bosses.')

        # Summary
        for bt in ('boss', 'world_boss', 'aberration'):
            c = db.execute(text("SELECT COUNT(*) FROM r2_bosses WHERE boss_type=:t"), {'t': bt}).scalar()
            print(f'  {bt}: {c}')


if __name__ == '__main__':
    main()
