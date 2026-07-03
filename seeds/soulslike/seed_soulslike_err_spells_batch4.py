"""
Seed: ERR new spell detail, batch 4 (Magma + Night sorceries).
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_spells_batch4.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SPELLS = [
    ('Blasphemous Spark', 50, 0, 18, 0, 0, 1, '1.76%+176',
     "Sparks a stream of blasphemous flame to scorch foes. Inflicts Fire damage. Generates 1.76%+176 "
     "FP on hit.",
     "Generator spell - costs 0 Memory Slots.",
     "Purchasable for 6500 runes from any sorcery vendor after handing them the Gelmirian Scroll. "
     "The scroll is found in the Serpentine Depths: in the area near the Tibia Mariner, go to the "
     "room with falling blades and use two Stonesword Keys, then follow the path to a lava-covered "
     "corridor with the scroll on the body at the end."),

    ('Molten Armament', 400, 1, 16, 5, 0, 0, None,
     "Enchants the right-hand armament with magma for 80 seconds (60 if Blasphemous Crest is "
     "equipped). Leaves small magma puddles on the ground on cast. Reduces Frostbite buildup on the "
     "player by 15 when cast. Adds 1.025x+25 Fire Attack Power to the right-hand armament (1.027x+27 "
     "with Blasphemous Crest). Flat buff is affected by 100% of catalyst Intelligence scaling. "
     "Affected by Blasphemous Crest (further increases damage and grants the Magma affinity effect). "
     "Can be cast while in motion.",
     None,
     "Found from a new enemy camp in Volcano Manor near the Rykard teleporter - jump down from the "
     "balcony to find the chest."),

    ('Serpentine Blaze', 310, 1, 30, 10, 0, 0, None,
     "Summons a snaking flame that zig-zags in front of the player before darting directly at the "
     "target, piercing them and dealing Fire damage, while restoring HP equal to 50+5% of Max HP. "
     "Charging increases the projectile's speed. Can get stuck on geometry and destroy itself due to "
     "its winding path.",
     None,
     "Purchasable with the Gelmirian Scroll found in the Serpentine Depths (same location as "
     "Blasphemous Spark - Stonesword Key corridor in the area near the Tibia Mariner)."),

    ('Unstable Fissure', 550, 2, 24, 8, 0, 0, None,
     "Prepares an explosive trap that erupts after some time or when a foe approaches. The expelled "
     "rock comes crashing back down, leaving hazardous magma behind. Inflicts Fire and Strike damage.",
     None,
     "Found on a corpse south of Seethewater Cave entrance, Mt. Gelmir."),

    ('Volcanic Storm', 480, 2, 34, 11, 0, 0, None,
     "Creates an AoE of roiling magma and fiery winds centered on the player, inflicting Fire damage "
     "to foes within. Can be continuously channeled by holding the casting button; additional FP "
     "drained at +120/s while channeling.",
     None,
     "Found next to Alexander when he visits Mt. Gelmir - step into the lava to grab it (using "
     "Torrent recommended)."),

    ('False Constellation', 630, 2, 38, 0, 0, 0, None,
     "Creates a fleeting star field high in the air. After some delay, the stars crash down upon "
     "foes. Inflicts Magic damage.",
     None,
     "Defeat the Gnoster, the False Sky boss encounter at the Siofra Aqueduct."),

    ('False Heavens', 410, 1, 27, 0, 0, 0, None,
     "Sends forward a wave of lights that leaves stifling stars in its wake, damaging foes within "
     "and inflicting Sleep and Poison buildup. Inflicts Magic damage.",
     None,
     "Found after defeating Gnoster, the False Sky."),

    ('Silver Attunement', 500, 2, 24, 0, 24, 0, None,
     "Attunes self with secret knowledge for 50 seconds: x1.12 Status Buildup dealt, x0.9 Status "
     "Buildup taken.",
     None,
     "Found at the beginning of Nokstella, Eternal City, in a breakable statue north of the first "
     "grace. To break the statue, lure the Giant Silver Tear down into it using a hole in the "
     "railing in the upper section of the area."),
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
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, batch 4).')


if __name__ == '__main__':
    run()
