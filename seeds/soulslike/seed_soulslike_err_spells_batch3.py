"""
Seed: ERR new spell detail, batch 3 (Finger + Ghostflame + Gravity sorceries).
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_spells_batch3.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SPELLS = [
    ('Guiding Microcosm', 500, 2, 30, 0, 15, 0, None,
     "Conjures a microcosm that follows the player for 60 seconds, granting the caster and nearby "
     "allies x0.9 All Damage taken and x1.1 All Damage dealt. The microcosm explodes if an enemy "
     "gets too close, dealing Magic damage.",
     None,
     "Found on top of a white spherical rock halfway through the finger-shaped pathway from the Finger "
     "Ruins of Rhia Site of Grace."),

    ('Warding Microcosm', 400, 2, 28, 0, 14, 0, None,
     "Conjures a stationary microcosm for 60 seconds. Allies (including the caster) inside gain "
     "x0.8 All Damage taken and -9 Status Buildup every 2 seconds. Also repels enemies who get too "
     "close.",
     None,
     "Found on top of a white spherical rock on the northernmost area of the Finger Ruins of Dheo."),

    ('Rancor', 50, 0, 14, 10, 0, 1, '0.98%+98',
     "Casts a single homing rancor skull with moderate range and speed at an enemy. Deals Magic "
     "damage and Frostbite buildup to the player and enemies (exact buildup value unverified). "
     "Generates FP on hit (exact amount unverified; overview lists 0.98%+98). Can be cast while in "
     "motion.",
     "Generator spell - costs 0 Memory Slots.",
     "Available from the start; found as a drop or purchasable - check in-game vendor after obtaining "
     "the relevant scroll."),

    ('Creeping Rancor', 370, 2, 26, 17, 0, 0, None,
     "Fires a single homing skull that gradually tracks a locked-on enemy and explodes on proximity "
     "after a brief delay. Casting deals 40 Frostbite buildup to the player; the explosion inflicts "
     "140 Frostbite buildup to enemies and a ghostflame burn. Only one skull can exist at a time - "
     "recasting removes the previous skull.",
     None,
     "Found on a hill in the Capital Outskirts near some golden skeletons."),

    ('Raving Rancor', 560, 2, 37, 23, 0, 0, None,
     "Summons a stationary hovering rancor skull that, after a delay, fires a continuous beam of "
     "ghostflame for a moderate distance. The skull is autonomous - you can move and attack after "
     "placing it. While locked on, the skull lazily homes on the enemy. Only one skull can be active "
     "at a time. Beam lasts 6 seconds uncharged, 8 when charged (charging extends duration but not "
     "per-tick damage; Godfrey Icon increases per-tick damage). Inflicts Magic damage, Frostbite "
     "buildup (exact value unverified), and a ghostflame burn. Can be cast while moving.",
     "Charging does not increase per-tick damage but increases total damage via longer duration; "
     "Godfrey Icon talisman increases damage on each individual tick.",
     "Acquired by defeating all 4 skeleton-summoning Large Bloodbane Albinaurics in the Mohgwyn "
     "Palace outskirts."),

    ('Stone Sling', 50, 0, 16, 0, 0, 1, '1.92%+192',
     "Pulls a stone from the earth and sends it flying. Deals a mix of Lightning and Strike damage. "
     "Generates 1.92% Max FP + 192 on hit. Can be cast while in motion.",
     "Generator spell - costs 0 Memory Slots.",
     "Drops from an Alabaster Lord at Crater-pocked Glade on the north-east side of the Weeping "
     "Peninsula (boss appears only at night)."),

    ('Electromagnetic Discharge', 730, 3, 56, 0, 0, 0, None,
     "Causes a sphere of gravitational energy to rise from the floor, dealing Lightning damage to "
     "those above. The sphere then pulses periodically (4 times uncharged, 5 times charged) dealing "
     "Lightning damage in a moderate area. Each pulse arcs gravitational lightning through nearby "
     "enemies, dealing additional damage even beyond pulse range.",
     "Charging extends duration (one extra pulse) but not per-pulse damage.",
     "Reward for clearing three 'dot puzzle' challenges: from each big electrified crystal, shoot the "
     "closest crystal to transfer the current until all are lit. Must kill the Astel in the area to "
     "activate the puzzle. Puzzle locations: (1) room before Astel, Naturalborn of the Void - shoot "
     "crystals bottom to top in a straight line; (2) from 'Ainsel River Main' grace, go straight then "
     "left to the waterfall (two crystals hidden under it, use the side strips of land); (3) big "
     "cave/room before the Hermit Merchant in Ainsel River ('Ainsel River Downstream' grace), "
     "north-east section."),

    ('Singularity', 590, 2, 44, 0, 0, 0, None,
     "Fires numerous gravitational projectiles that pull the targeted foe towards a singularity while "
     "drawing in opposing sorceries and incantations. Small projectiles deal True damage; the final "
     "explosion deals Lightning damage.",
     "Can redirect enemy spells toward the singularity while active.",
     "Drops from a new Alabaster Lord boss found East of the Church of the Plague."),
]


def run():
    with engine.connect() as conn:
        updated = 0
        inserted = 0
        for (name, fp_cost, slots, int_req, fai_req, arc_req,
             is_gen, fp_on_hit, effect, notes, acquisition) in SPELLS:
            result = conn.execute(text("""
                UPDATE sl_err_spells
                SET fp_cost = :fp, slots_used = :slots,
                    int_req = :ir, fai_req = :fr, arc_req = :ar,
                    is_generator = :gen, fp_on_hit = :fp_hit,
                    effect = :eff, notes = :notes, acquisition = :acq
                WHERE name = :name
            """), {
                'fp': fp_cost, 'slots': slots, 'ir': int_req, 'fr': fai_req, 'ar': arc_req,
                'gen': is_gen, 'fp_hit': fp_on_hit, 'eff': effect, 'notes': notes,
                'acq': acquisition, 'name': name,
            })
            if result.rowcount:
                updated += 1
            else:
                conn.execute(text("""
                    INSERT INTO sl_err_spells
                        (name, spell_type, school, is_new_to_err, is_generator, fp_cost, slots_used,
                         int_req, fai_req, arc_req, fp_on_hit, effect, notes, acquisition)
                    VALUES (:name, 'Sorcery', 'Unknown', 1, :gen, :fp, :slots,
                            :ir, :fr, :ar, :fp_hit, :eff, :notes, :acq)
                """), {
                    'name': name, 'gen': is_gen, 'fp': fp_cost, 'slots': slots,
                    'ir': int_req, 'fr': fai_req, 'ar': arc_req,
                    'fp_hit': fp_on_hit, 'eff': effect, 'notes': notes, 'acq': acquisition,
                })
                inserted += 1
                print(f'  INSERTED: {name}')
        conn.commit()
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, batch 3).')


if __name__ == '__main__':
    run()
