"""
Seed r2_mutators from wiki data (manually provided).
Run: chwebsiteprj/bin/python3 seed_remnant2_mutators.py
"""
import django, os, re, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

NOW = int(time.time())

def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

# (name, mutator_type, dlc)
MUTATORS = [
    ('Bandit',          'ranged',   'base'),
    ('Battery',         'ranged',   'base'),
    ('Battle Mage',     'melee',    'base'),
    ('Bottom Heavy',    'ranged',   'base'),
    ('Bulletweaver',    'ranged',   'base'),
    ('Charged Wounds',  'ranged',   'dlc3'),
    ('Deadly Calm',     'ranged',   'base'),
    ('Dervish',         'melee',    'base'),
    ('Detonator',       'ranged',   'dlc3'),
    ('Disengage',       'melee',    'base'),
    ('Dreadful',        'ranged',   'dlc1'),
    ('Edgelord',        'melee',    'base'),
    ('Executor',        'melee',    'dlc1'),
    ('Extender',        'ranged',   'base'),
    ('Failsafe',        'ranged',   'base'),
    ('Far-Sighted',     'ranged',   'dlc2'),
    ('Feedback',        'ranged',   'base'),
    ('Fetid Wounds',    'ranged',   'base'),
    ('Ghost Shell',     'ranged',   'base'),
    ('Gladiator',       'melee',    'dlc2'),
    ('Guts',            'melee',    'dlc1'),
    ('Harmonizer',      'ranged',   'base'),
    ('Hidden Power',    'ranged',   'base'),
    ('Hyper Charger',   'melee',    'dlc3'),
    ('Ingenuity',       'ranged',   'base'),
    ('Insulator',       'ranged',   'dlc3'),
    ('Kill Switch',     'ranged',   'base'),
    ('Latency',         'melee',    'base'),
    ('Lithely',         'ranged',   'base'),
    ('Maelstrom',       'ranged',   'dlc1'),
    ('Misfortune',      'melee',    'base'),
    ('Momentum',        'ranged',   'base'),
    ('Near-Sighted',    'ranged',   'dlc2'),
    ('Opportunist',     'melee',    'base'),
    ('Overdrive',       'melee',    'base'),
    ('Pressure Point',  'ranged',   'dlc2'),
    ('Prophecy',        'ranged',   'dlc1'),
    ('Refunder',        'ranged',   'base'),
    ('Reinvigorate',    'melee',    'base'),
    ('Repercussion',    'ranged',   'dlc3'),
    ('Resentment',      'melee',    'base'),
    ('Searing Wounds',  'ranged',   'dlc2'),
    ('Sequenced Shot',  'ranged',   'base'),
    ('Shielded Strike', 'melee',    'base'),
    ('Shocker',         'melee',    'base'),
    ('Slayer',          'ranged',   'base'),
    ('Sleeper',         'ranged',   'dlc1'),
    ('Spellweaver',     'ranged',   'base'),
    ('Spirit Feeder',   'ranged',   'base'),
    ('Spirit Healer',   'ranged',   'base'),
    ('Steadfast',       'melee',    'base'),
    ('Stormbringer',    'melee',    'base'),
    ('Striker',         'melee',    'base'),
    ('Supercharger',    'ranged',   'base'),
    ('Superheated',     'ranged',   'dlc3'),
    ('Tainted Blade',   'melee',    'base'),
    ('Thousand Cuts',   'ranged',   'dlc2'),
    ('Timewave',        'ranged',   'base'),
    ('Top Heavy',       'ranged',   'base'),
    ('Transference',    'melee',    'base'),
    ('Transpose',       'ranged',   'base'),
    ('Twisting Wounds', 'ranged',   'base'),
    ('Vampire Blade',   'melee',    'base'),
    ('Vengeful Strike', 'melee',    'base'),
    ('Volatile Strike', 'melee',    'base'),
    ('Weaponlord',      'melee',    'base'),
]

def main():
    with get_db_session() as db:
        existing = db.execute(text('SELECT COUNT(*) FROM r2_mutators')).scalar()
        if existing > 0:
            print(f'WARNING: {existing} mutators already exist. Delete first to re-seed.')
            return

        for (name, mtype, dlc) in MUTATORS:
            db.execute(text("""
                INSERT INTO r2_mutators (slug, name, mutator_type, dlc, created_at)
                VALUES (:slug, :name, :type, :dlc, :now)
            """), {'slug': slugify(name), 'name': name, 'type': mtype, 'dlc': dlc, 'now': NOW})

        db.commit()
        total = db.execute(text('SELECT COUNT(*) FROM r2_mutators')).scalar()
        print(f'Inserted {total} mutators')

        for mtype in ('ranged', 'melee'):
            c = db.execute(text("SELECT COUNT(*) FROM r2_mutators WHERE mutator_type=:t"), {'t': mtype}).scalar()
            print(f'  {mtype}: {c}')

if __name__ == '__main__':
    main()
