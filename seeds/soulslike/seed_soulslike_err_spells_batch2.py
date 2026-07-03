"""
Seed: ERR new spell detail, batch 2 (Crystal Volley + Death Sorceries).
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_spells_batch2.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, fp_cost, slots, int_req, fai_req, arc_req, is_gen, fp_on_hit, effect, notes, acquisition)
SPELLS = [
    ('Crystal Volley', 240, 1, 27, 0, 0, 0, None,
     "Conjures a row of six sharp crystals then sends them towards a foe after a brief delay. Can be "
     "cast while in motion. Deals Magic damage.",
     None,
     "Drops from the baby glintstone crab in the crystal area next to the poison swamp surrounding the "
     "Village of the Albinaurics."),

    ('Burgeoning Root', 510, 2, 32, 21, 0, 0, None,
     "Causes a giant root to burst from the ground in front of the caster, sending smaller root "
     "streaks outwards briefly. Both the giant and smaller streaks deal Pierce damage and cause Death "
     "Blight buildup.",
     None,
     "Found at the end of a large root on the very northern edge of Deeproot Depths."),

    ('Duskflare Barrage', 140, 1, 22, 15, 0, 0, None,
     "Fires spheres that briefly spread outwards before homing in on the locked-on target. Builds up "
     "Death Blight on the caster. Projectiles inflict Holy damage and Death Blight buildup on the "
     "target. Can be continuously channeled by holding the casting button - continuous channeling drains "
     "additional FP and Stamina, and builds up additional Death Blight on the caster. FP: 140 initial "
     "+60 per second channeled.",
     None,
     "Found on the approach to the Four Belfries, on a corpse atop a death root."),

    ('Eclipsed Blade', 400, 1, 19, 13, 0, 0, None,
     "Enchants the right-hand armament with flames of the eclipsed sun. Deals 100 Death Blight "
     "buildup on the player on cast. Adds 25 Death Blight buildup and 1.0125x+9 Holy Attack Power "
     "to the right-hand armament for 80 seconds. Flat attack power buff is affected by 100% of "
     "catalyst Intelligence and Faith spell scaling. Can be cast while in motion.",
     None,
     "Drops from the Mausoleum Knight who guards the door of the Black Knife Catacombs in Eastern "
     "Liurnia."),

    ('Eclipsed Sun', 880, 3, 54, 36, 0, 0, None,
     "Conjures a vision of the swallowed sun that appears over the area in front of the caster. After "
     "1.5 seconds the sun fires a laser directly underneath it for 4 seconds, followed by an "
     "explosion. Inflicts Death Blight on all within its light, including the caster. Standing in the "
     "sun's vicinity while it is firing boosts healing effects by 20%. The laser can deal minor Holy "
     "damage to the caster (but not to allies).",
     "Legendary sorcery. Very high stat requirements (54 Int / 36 Fai).",
     "Found after defeating Commander Niall in Castle Sol, atop the battlements after the elevator."),
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
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, batch 2).')


if __name__ == '__main__':
    run()
