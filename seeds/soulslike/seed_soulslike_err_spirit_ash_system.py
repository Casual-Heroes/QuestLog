"""
Seed: ERR Spirit Ash system overview + stub rows for new/changed ashes.
Source: err.fandom.com/wiki/Spirit_Ashes, pasted directly by user.

This seeds:
1. A system-level table for general mechanics (Spirit Fury, Passive/Enraged states,
   Depleted Ashes fix) - stored as a special row since it's not per-ash data.
2. Stub rows for the 8 brand-new ERR Spirit Ashes (name only, awaiting individual
   page detail).
3. The 6 vanilla Spirit Ashes with confirmed behavioral changes, with that exact
   change text already filled in.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_spirit_ash_system.py
"""
import time
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
NOW = int(time.time())

SYSTEM_OVERVIEW = (
    "GENERAL CHANGES: Initial summon FP costs greatly reduced. Spirit Ashes now scale with NG+ cycles. "
    "Spiritcalling Bell use is faster and can be done while moving. Spirit summons are now vulnerable to "
    "status effects (matching whatever the normal version of that enemy is vulnerable to). Early reinforcement "
    "levels strengthened, removing the power spike previously gained at later levels - reinforcement is now "
    "a steadier upgrade curve. Some early high-level Gloveworts replaced with lower-level ones.\n\n"
    "DEPLETED SPIRIT ASHES: item changes from vanilla to Reforged may cause existing Spirit Ashes to show as "
    "'depleted' (outdated versions). Fix: at a Site of Grace, open Reforged options > Compatibility > "
    "'Restore depleted spirit ashes', then fast travel. If depleted ashes are only in quick item slots (not "
    "inventory), simply re-assign those slots to the new versions.\n\n"
    "SPIRIT FURY: Spirit Ashes are Passive by default when summoned - very low damage, very high damage "
    "reduction, reduced status buildup, cannot stagger/flatten enemies, and are ignored by enemies unless no "
    "other target exists. Using the Spirit Ash again while already summoned 'Enrages' it for 2x the initial "
    "FP cost: vastly increased damage (5x Passive, roughly 2x vanilla values), normal damage reduction, vastly "
    "increased target priority (some ashes like Latenna get a smaller priority boost by design, since they're "
    "meant to be fragile/low-aggro), and heals the ash for 10% of its Max HP every time Enrage triggers. "
    "Enraged state is time-limited then reverts to Passive; can be re-triggered indefinitely with enough FP. "
    "Mind scales Spirit Fury duration: 30s base at 1 Mind, up to 40s at 99 Mind. Some ashes behave "
    "differently Passive vs Enraged (more aggressive/direct when Enraged), use powerful buffs/debuffs less "
    "often while Passive, or perform a specific attack immediately upon being Enraged."
)

NEW_SPIRIT_ASHES = [
    'Blaidd',
    'Glintstone Miner Ashes',
    'Lazuli Sorcerer',
    'Grand Inquisitor Eli',
    'Latenna and Lobo',
    'Ringmaster Ophidion',
    'Starcaller Ashes',
    'Zamor Knight Lyedna',
]

VANILLA_CHANGES = {
    'Avionette Soldiers': "Can now perform 'breakdown' animations when attacked while Enraged.",
    'Blackflame Monk Amon': "Uses Black Flame attacks much less frequently while Passive.",
    'Black Knife Tiche': "Uses her Destined Death attack much less frequently while Passive.",
    'Kaiden Sellsword': (
        "Performs War Cry immediately upon being Enraged and attacks aggressively. The War Cry animation "
        "grants greatly increased damage resistance during itself and prevents stagger."
    ),
    'Marionette Soldiers': "Can now perform 'breakdown' animations when attacked while Enraged.",
    'Skeletal Militiamen': "Now apply Frostbite status to enemies.",
}


def run():
    with engine.connect() as conn:
        # System overview - stored as a special named row (id lookup by name='__SYSTEM__')
        conn.execute(text("DELETE FROM sl_spirit_ashes WHERE name='__SYSTEM__' AND game='err'"))
        conn.execute(text("""
            INSERT INTO sl_spirit_ashes (game, name, description, created_at)
            VALUES ('err', '__SYSTEM__', :desc, :ts)
        """), {'desc': SYSTEM_OVERVIEW, 'ts': NOW})
        print('System overview seeded.')

        # New ERR-exclusive Spirit Ashes (stubs, awaiting individual page detail)
        for name in NEW_SPIRIT_ASHES:
            conn.execute(text("DELETE FROM sl_spirit_ashes WHERE name=:name AND game='err'"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_spirit_ashes (game, name, is_new_to_err, created_at)
                VALUES ('err', :name, 1, :ts)
            """), {'name': name, 'ts': NOW})
            print(f'  + (stub) {name}')

        # Vanilla ashes with confirmed ERR behavioral changes
        for name, change_text in VANILLA_CHANGES.items():
            conn.execute(text("DELETE FROM sl_spirit_ashes WHERE name=:name AND game='err'"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_spirit_ashes (game, name, is_new_to_err, vanilla_changes, created_at)
                VALUES ('err', :name, 0, :changes, :ts)
            """), {'name': name, 'changes': change_text, 'ts': NOW})
            print(f'  + (vanilla, changed) {name}')

        conn.commit()
        total = conn.execute(text("SELECT COUNT(*) FROM sl_spirit_ashes WHERE game='err'")).scalar()
        print(f'\nTotal sl_spirit_ashes rows for ERR: {total} (1 system overview + '
              f'{len(NEW_SPIRIT_ASHES)} new stubs + {len(VANILLA_CHANGES)} vanilla changes)')


if __name__ == '__main__':
    run()
