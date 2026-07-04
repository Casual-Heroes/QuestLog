"""
Seed: ERR per-weapon Weight + Critical fill-in, batch 9 (final batch of the New
Armaments list from the Weapons overview page).
Source: err.fandom.com individual weapon pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch9.py
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
    ('Suncatcher', 6.5, 110,
     "Perfect deflects restore 0.7%+7 HP and grant x1.1 Attack Power/Poise Damage/Stamina Damage and "
     "x0.9 FP Cost of skills for 5 seconds (or until hitting an enemy). Does not stack with "
     "Determination or Royal Knight's Resolve - overwrites them when triggered. Blessed affinity: "
     "slowly recovers HP while in combat.",
     None,
     "Found on the first floor of the Fortified Manor in Leyndell, on a bed next to the painting on "
     "the southern side of the manor.",
     "Cursed blade of dull gold. Once wielded by a disciplined Tarnished who fell from grace. Sealed "
     "beneath cursed wrappings lie metal forged in the Land of Reeds, its braided spirals evoking a "
     "once holy power thought to stem from the Erdtree alone. Unique Skill: Cursed Blade - performs a "
     "powerful slash with the living sword, especially potent when latent strength is unleashed after "
     "a perfect deflect; deals +160 Holy Damage and +110 Poise Damage when buffed."),
    ('Sun Realm Sword', 3.5, 100,
     "Launching a strong attack activates a parry.",
     None,
     "Obtained from the Snowswept Graveyard enemy camp in the Mountaintops of the Giants, along with "
     "the Grave Scythe. Also drops from Skeleton Knights at a low rate.",
     "An arming sword dulled by age. Provides limited protection during heavy attacks. Once, the light "
     "of the sun shone radiantly from this blade. Such glory is long past."),
    ('Twinbird Caduceus', 3.5, 0,
     "x1.1 Attack Power to ghostflame sorceries while equipped. Cold affinity: causes Frostbite "
     "buildup.",
     None,
     "Found in Liurnia of the Lakes, from a corpse in a small graveyard north of the Church of Vows.",
     "Staff crudely fashioned from human remains, with pale glintstone perched across a crude effigy. "
     "Enhances ghostflame sorceries. Though Erdtree worship once supplanted the old funeral rites, as "
     "restless remains stir to life in Death, new practitioners rise to put the dead to rest, or use "
     "them to achieve their own ends. Added in ERR 2.0."),
    ('Vulgar Militia Chain Sickle', 5.0, 105,
     "Blood affinity: causes Blood Loss buildup. Paired weapon - functions as an Axe in the right hand "
     "and a Whip in the left hand.",
     None,
     "Obtained in the Forbidden Lands, in the mouth of the giant skull near the Golden Seed tree.",
     "Paired weapon consisting of a sharpened farmer's sickle, and a cruel ball and chain. The rancid "
     "scavengers of the battlefields use the chain to catch escaping survivors at a distance, before "
     "carving their flesh with the sickle at close range. Unique Skill: Trapper's Step - skill prized "
     "by the crafty and fleet of foot; performs a quickstep maneuver allowing circling around lock-on "
     "targets, dropping a poison trap when held as an axe and a smoke bomb when held as a whip."),
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
