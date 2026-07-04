"""
Seed: ERR per-weapon Weight + Critical multiplier fill-in (batch 1 of ~50 pages), plus
passive effect / Fated effect / acquisition text where provided.
Source: err.fandom.com individual weapon pages, pasted directly by user.

The regulation-reforged-v2.2.3.4.js dump used to originally seed sl_weapons does NOT
contain Weight or per-weapon Critical multiplier data (confirmed by inspecting the raw
JSON - only name/affinityId/weaponType/requirements/attack/attributeScaling/
reinforceTypeId/attackElementCorrectId/calcCorrectGraphIds are present). Both fields
were hardcoded (weight=0, critical=100) in the original ERR weapon seeder. This batch
fills in the real values as the user provides them page by page.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch1.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, weight, critical, passive_effect, fated_effect, acquisition, description)
WEAPONS = [
    ("Ambassador's Cudgel", 7.0, 95,
     "Deals bonus magic damage to marked targets once.",
     None,
     "Found as a random drop from Roundtable Ambassadors who wield these hammers.",
     "Solid iron bludgeon with an elongated striking end, wielded by field agents of the All-Knowing. "
     "Their gaze obscured by metal helms, Sir Gideon's pawns leave it to the lavish eye etchings atop "
     "their clubs to bear witness to their victims' final moments."),
    ("Ambassador's Greatsword", 20.5, 90,
     "Deals bonus magic damage to marked targets once.", None, None, None),
    ("Ambassador's Towershield", 15.0, 90,
     "Deals bonus magic damage to marked targets once.", None, None, None),
    ('Avionette Pig Sticker', 6.5, 95,
     "Causes Blood Loss buildup (Blood affinity).", None, None, None),
    ('Avionette Scimitars', 5.5, 90,
     "Causes Blood Loss buildup (Blood affinity).", None, None, None),
    ('Broken Straight Sword', 1.0, 100,
     None,
     "+1 Courage. Does nothing.",
     'Found next to the new "Gilded Cave of Knowledge" Site of Grace.',
     "Straight sword with its blade broken near in half. A weapon with no exceptional qualities. "
     "Nearly useless in battle, but \"nearly useless\" trumps \"empty-handed\". Functions as a normal "
     "Straight Sword, albeit with very poor damage and range. Given as part of the tutorial to "
     "guarantee players have a weapon capable of completing it. Ironically, in some specific cases "
     "your bare fists may actually deal higher DPS."),
]


def run():
    with engine.connect() as conn:
        updated = 0
        for name, weight, crit, passive, fated, acquisition, description in WEAPONS:
            result = conn.execute(text("""
                UPDATE sl_weapons SET weight = :weight, critical = :crit
                WHERE game = 'err' AND name = :name
            """), {'weight': weight, 'crit': crit, 'name': name})
            if result.rowcount:
                updated += 1
            else:
                print(f'  NOT FOUND in sl_weapons: {name}')

            if passive or fated or acquisition or description:
                conn.execute(text("DELETE FROM sl_err_weapon_passives WHERE weapon_name=:name"), {'name': name})
                conn.execute(text("""
                    INSERT INTO sl_err_weapon_passives
                        (weapon_name, passive_effect, fated_effect, acquisition, description)
                    VALUES (:name, :passive, :fated, :acq, :desc)
                """), {
                    'name': name, 'passive': passive, 'fated': fated,
                    'acq': acquisition, 'desc': description,
                })
        conn.commit()
        print(f'\n{updated}/{len(WEAPONS)} weapons updated with weight + critical.')


if __name__ == '__main__':
    run()
