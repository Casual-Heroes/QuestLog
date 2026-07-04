"""
Seed: ERR Affinities system - reworked vanilla affinities + brand-new ERR-exclusive
affinities (Bestial, Night, Cold, Gravitational, Frenzied, Soporific, Fated), each with
its own passive/on-hit effect, scaling stat, and damage type change.
Source: err.fandom.com/wiki/Affinities, pasted directly by user. Values updated to
version 2.2.3.1.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_affinities.py
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

GENERAL_NOTE = (
    "Reforged alters the vanilla affinities and also adds several new affinities, allowing all "
    "non-somber armament to access any status effect or elemental damage type. The damage scalings of "
    "each existing affinity has been reworked, and every affinity also has an effect associated with "
    "it. Affinities no longer completely replace armament scaling, and instead modify it - this means "
    "unique combinations of scaling are possible by using different infusions based on what armament "
    "you use them on. Passive effects from affinities apply when the armament is equipped in an active "
    "hand, even when two-handing the other weapon. However, any on-hit effects (such as Magma or the "
    "active portion of Lightning) only activate when hitting with the armament that has the affinity.\n\n"
    "WHETBLADE CHANGES: A new item, the Whetblade Fragment, is available only at Merchant Kale's shop "
    "at the Church of Elleh in Limgrave. It unlocks a single affinity of choice at the start of the "
    "game without needing to find its corresponding Whetblade. Only two Whetblade Fragments can be "
    "purchased from Kale. A new whetblade, the Fated Whetblade, is available after defeating the final "
    "boss of the base game, unlocking the Fated affinity - a special affinity granting substantial "
    "changes to each weapon (cannot be unlocked via Whetblade Fragments). The Red-Hot Whetblade's "
    "location has slightly changed: now found outside its previous room in the small courtyard, "
    "guarded by an Abductor Virgin."
)

# (name, whetblade, scaling_stat, damage_type_change, effect, is_new)
AFFINITIES = [
    ('Heavy', 'Iron', 'Strength', None,
     "x1.05 Poise Damage. Passively increases Poise Damage dealt by 2.5%.", 0),
    ('Keen', 'Iron', 'Dexterity', None,
     "-5% Stamina Cost for attacks. Passively reduces the Stamina Cost of attacking and casting by "
     "2.5%.", 0),
    ('Quality', 'Iron', 'Strength and Dexterity (split equally, +10% scaling increase)', None,
     "-2.5% Stamina Cost for blocking. Slightly increases Guard Boost.", 0),
    ('Bestial', 'Iron', 'Lowers scaling for more base damage', None,
     "Each hit grants x1.04 Attack Power and x1.06 Damage Taken (stacks, each stack has its own 4 "
     "second duration). x1.05 Attack Power versus Beast-type enemies.", 1),
    ('Magic', 'Glintstone', 'Intelligence', 'Magic',
     "0.21%+1 FP Regen every 2 seconds while in combat. Increases Magic Guarded Negation.", 0),
    ('Night', 'Glintstone', 'Dexterity', 'Magic',
     "+60% Attack Power on sneak attacks. +5 Critical Damage multiplier. Increases Magic Guarded "
     "Negation.", 1),
    ('Cold', 'Glintstone', 'Intelligence', 'Magic',
     "Adds Frostbite buildup. Increases the amount of Frostbite buildup blocked. +5% Attack Power "
     "versus Stone-type enemies.", 1),
    ('Gravitational', 'Glintstone', 'Intelligence', 'Lightning and Physical',
     "-50% Weight. x1.05 Attack Power versus Void-type enemies. Greatly reduces Guard Boost.", 1),
    ('Fell', 'Red-Hot', 'Faith', 'Fire',
     "-1 Status Buildup every 2 seconds. Increases Fire Guarded Negation.", 0),
    ('Magma', 'Red-Hot', 'Intelligence', 'Fire',
     "When striking an enemy afflicted with Frostbite, deals a large amount of flat fire damage "
     "(depends on the enemy, not increased by fire buffs - verification needed) and 10 Poise Damage, "
     "but ends the Frostbite. Increases Fire Guarded Negation.", 1),
    ('Fire', 'Red-Hot', 'Strength', 'Fire',
     "Each hit applies a lingering burn dealing 0.06% Max HP+1 every second for 5 seconds (0.36% Max "
     "HP+6 total, varies x1 to x40 based on enemy type). Increases Fire Guarded Negation.", 0),
    ('Frenzied', 'Red-Hot', 'Strength, Dexterity, Intelligence, and Faith', 'Converts most damage into Fire',
     "Adds Madness buildup. Increases the amount of Madness buildup blocked.", 1),
    ('Bolt', 'Sanctified', 'Faith', 'Lightning',
     "x1.05 Attack Power versus Dragon-type enemies. Increases Lightning Guarded Negation.", 0),
    ('Sacred', 'Sanctified', 'Faith', 'Holy',
     "x1.05 Attack Power versus Undead-type enemies. Prevents undead enemies from reviving on death. "
     "Increases Holy Guarded Negation.", 0),
    ('Lightning', 'Sanctified', 'Dexterity', 'Lightning',
     "Passively increases Stamina Regen by 20. Weapon hits increase Stamina Regen by 20 for 5 seconds "
     "(stacks, each stack runs on its own independent timer). Increases Lightning Guarded Negation.", 0),
    ('Blessed', 'Sanctified', 'Strength', 'Holy',
     "0.14%+3 HP Regen every 2 seconds while in combat. Increases Holy Guarded Negation.", 0),
    ('Soporific', 'Sanctified', 'Intelligence and Faith', 'Magic and Fire',
     "Adds Sleep buildup. Increases the amount of Sleep buildup blocked.", 1),
    ('Rotten', 'Sanctified', 'Faith', None,
     "Adds Scarlet Rot buildup. Increases the amount of Scarlet Rot buildup blocked.", 0),
    ('Poison', 'Black', 'Arcane', None,
     "Adds Poison buildup. Increases the amount of Poison buildup blocked.", 0),
    ('Blood', 'Black', 'Arcane', None,
     "Adds Blood Loss buildup. Increases the amount of Blood Loss buildup blocked.", 0),
    ('Cursed', 'Black', 'Intelligence and Faith', None,
     "Adds Death Blight buildup. Increases the amount of Death Blight buildup blocked. Each hit "
     "reduces the target's Attack Power by 6% for 0.5 seconds, followed by 3% for 2.5 seconds. "
     "Consecutive hits refresh the duration of the debuff.", 0),
    ('Occult', 'Black', 'Arcane', None,
     "x1.05 Attack Power versus Divine-type enemies.", 0),
    ('Fated', 'Fated', 'Varies', 'Varies',
     "Fated applies completely custom scaling, affinities, and effects to each individual weapon in "
     "the game. Many weapons gain status effects, many change scaling entirely, and some change damage "
     "type entirely - see the Fated Whetblade article for per-weapon details.", 1),
]


def run():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_err_affinities WHERE name='__GENERAL__'"))
        conn.execute(text("""
            INSERT INTO sl_err_affinities (name, effect, created_at)
            VALUES ('__GENERAL__', :note, :ts)
        """), {'note': GENERAL_NOTE, 'ts': NOW})
        print('General/Whetblade overview seeded.')

        for name, whetblade, scaling, dmg_change, effect, is_new in AFFINITIES:
            conn.execute(text("DELETE FROM sl_err_affinities WHERE name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_affinities
                    (name, whetblade, scaling_increase_stat, damage_type_change, effect, is_new_to_err, created_at)
                VALUES (:name, :wb, :scal, :dmg, :eff, :new, :ts)
            """), {
                'name': name, 'wb': whetblade, 'scal': scaling, 'dmg': dmg_change,
                'eff': effect, 'new': is_new, 'ts': NOW,
            })
            tag = ' (NEW)' if is_new else ''
            print(f'  + {name}{tag}')
        conn.commit()

        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_affinities WHERE name != '__GENERAL__'")).scalar()
        new_count = conn.execute(text("SELECT COUNT(*) FROM sl_err_affinities WHERE is_new_to_err=1")).scalar()
        print(f'\n{total} affinities seeded ({new_count} new to ERR).')


if __name__ == '__main__':
    run()
