"""
Seed: ERR per-weapon Weight + Critical fill-in, batch 5.
Source: err.fandom.com individual weapon pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch5.py
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
    ('Gracebound Greatsword', 9.0, 100,
     "Skill use coats the armament in flame, dealing damage over time (exact values unverified).",
     None,
     "Found at the edge of a cliff at the Church of Vengeance.",
     "Eroded greatsword with a dulled edge. Once wielded by a knightly Tarnished who fell from grace. "
     "Its blade is worn away by years of strife. Without its wielder's bloody work, there would be "
     "scores more adversaries for the Roundtable to face today."),
    ('Gracebound Halberd', 10.5, 95,
     "Creates a damaging whirlwind while charging attacks (exact values unverified).",
     None,
     "Found after teleporting to the Crumbling Lands through the Four Belfries in Liurnia, on a "
     "slanted pillar in the area with the two Beastmen of Farum Azula.",
     "Weathered halberd, hollowed like a bird's bones. Once wielded by a proud Tarnished who fell from "
     "grace. The gales that swept around this halberd have worn away much of the fine metalwork that "
     "celebrates its heritage."),
    ('Gracebound Katana', 5.5, 100,
     "Blood affinity: causes Blood Loss buildup.",
     None,
     "Found in the Outer Wall Battleground, Altus Plateau, in one of the small craters with enormous "
     "arrows sticking out, a little southeast of the Outer Wall Battleground site of grace.",
     "Blood-crusted sword from the Land of Reeds. Once wielded by a disciplined Tarnished who fell "
     "from grace. The old blade bears the stains of a shameful suicide. Bad luck is sure to befall one "
     "who chooses to return this weapon to battle."),
    ('Gracebound Longbow', 4.0, 135,
     "x1.15 Counter Damage to arrows while equipped.",
     None,
     "Found at the edge of the cliff just beyond the Abductor Virgin Duo in Volcano Manor, just before "
     "the drop down to the slanted rock leading to Wyndham Ruins.",
     "Old oaken bow, wrapped with leather strips. Once wielded by a somber Tarnished who fell from "
     "grace. The arrows loosed by this bow once felled the marks of a secretive order, rarely aligned "
     "with the Roundtable Hold. Such dual allegiances draw unwanted ire if not concealed."),
    ('Gracebound Mace', 8.0, 100,
     "Final hit of a light attack chain provides x1.12 Attack Power.",
     None,
     "Found at a grave northwest of Charo's Hidden Grave, north of the Furnace Golem's location.",
     "Flanged mace wrought of black iron. Once wielded by a waifish Tarnished who fell from grace. "
     "With a reputation for unsubtle bloodshed, one confessor soon lost the favor of the Two Fingers. "
     "In search for a cure to her compulsions, she followed the kindest of the demigods as long as she "
     "could."),
    ('Gracebound Round Shield', 2.0, 100,
     "Extends slide distance while equipped (exact value unverified).",
     None,
     "Found at the edge of a cliff at the Church of Vengeance.",
     "Old wooden shield with flaking paint. Once wielded by a knightly Tarnished who fell from grace. "
     "The white emblem upon a blue field reflects the culture of its wielder's distant origins. Its "
     "legacy persists despite his obscure demise."),
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
