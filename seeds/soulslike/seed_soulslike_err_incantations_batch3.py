"""
Seed: ERR new incantation detail, batch 3 (Frenzied/Golden Order + Golden Order + Miquellan +
Servants of Rot incantations).
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_incantations_batch3.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SPELLS = [
    ('Ordered Disarray', 540, 2, 27, 27, 0, 0, None,
     "Conjures a glob of alchemical gold that rains projectiles inflicting Holy damage and Madness "
     "buildup in an orderly pattern. Leaves behind twisted gold. Gathering the twisted gold slightly "
     "restores HP, drains Madness buildup, and empowers the caster.",
     "Counts as both a Frenzied Flame and Golden Order incantation.",
     "Found in the Frenzied Flame Proscription, on a corpse in a nook just before the parkour "
     "section with the coffins along the walls."),

    ('Binding Stake', 490, 2, 18, 34, 0, 0, None,
     "Ruptures the ground with a golden stake that pulls in foes and blasts them with holy energies. "
     "Inflicts Holy damage.",
     None,
     "Traded from Finger Reader Enia at Roundtable Hold in exchange for the Elden Remembrance."),

    ('Javelin of Gold', 380, 2, 14, 26, 0, 0, None,
     "Summons a holy javelin and hurls it before the caster. Inflicts Holy damage. Charging causes "
     "the javelin to explode in a burst of gold on impact, dealing a large AoE of Holy damage.",
     None,
     "Drops from the new Tree Sentinel boss found outside the Dectus Lift."),

    ('Stakes of Gold', 270, 1, 12, 22, 0, 0, None,
     "Fires five golden stakes in a cone, each dealing Holy damage upon colliding with an enemy or "
     "terrain. After a short delay, each stake explodes dealing further damage. Can be cast "
     "repeatedly.",
     None,
     "Purchasable from Miriel, Pastor of Vows for 8000 runes."),

    ('Pledged Blade', 400, 1, 0, 22, 0, 0, None,
     "Enchants the right-hand armament for 80 seconds: x1.025+25 Holy Attack Power, 0.25% Max HP+5 "
     "HP restoration on hit. Melee attacks additionally restore HP.",
     None,
     "Found north of the Highroad Cross Site of Grace (Scadu Altus), on a corpse near the "
     "patrolling Black Knight."),

    ('Scarlet Papillon', 50, 0, 0, 15, 0, 1, '1.67%+167',
     "Creates an AoE explosion on impact, inflicting True damage and causing 20 Scarlet Rot buildup "
     "on the caster and hit foes. Generates FP on hit (1.67%+167 per the overview; exact value "
     "unverified on individual page).",
     "Generator spell - costs 0 Memory Slots.",
     "Found on the Heart of Aeonia, accessible from the path outside the Church of the Plague near "
     "the Swamp Lookout Tower - visible from the tower, reached via Torrent parkour. Can also be "
     "reached directly from the Heart of Aeonia Site of Grace via Torrent parkour (very difficult, "
     "not intended path)."),

    ('Blessed Aeonia', 500, 2, 0, 31, 0, 0, None,
     "Increases Poison and Scarlet Rot buildup dealt by the caster and spirit ashes for 50 seconds: "
     "x1.15 Poison buildup dealt, x1.15 Scarlet Rot buildup dealt.",
     None,
     "Found on a corpse in the first section of the rot swamp in Elphael, Brace of the Haligtree, "
     "on top of the rock at the center (surrounded by many Rot Larva)."),

    ('Poison Bolt', 330, 1, 0, 15, 0, 0, None,
     "Releases a poisonous orb into the air that bursts into poisonous mist on impact. Deals 35 "
     "Poison buildup on the caster. Initial bolt inflicts True damage and 120 Poison buildup; the "
     "mist deals 4x 10 Poison buildup. Buildup scales with Arcane.",
     None,
     "Found on a hill near Caelid Waypoint Ruins."),
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
                    VALUES (:name, 'Incantation', 'Unknown', 1, :gen, :fp, :slots,
                            :ir, :fr, :ar, :fp_hit, :eff, :notes, :acq)
                """), {
                    'name': name, 'gen': is_gen, 'fp': fp_cost, 'slots': slots,
                    'ir': int_req, 'fr': fai_req, 'ar': arc_req,
                    'fp_hit': fp_on_hit, 'eff': effect, 'notes': notes, 'acq': acquisition,
                })
                inserted += 1
                print(f'  INSERTED: {name}')
        conn.commit()
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, incantations batch 3).')
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_spells WHERE effect IS NOT NULL")).scalar()
        print(f'Spells with full detail so far: {total}/72')


if __name__ == '__main__':
    run()
