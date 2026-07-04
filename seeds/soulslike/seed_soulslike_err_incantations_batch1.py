"""
Seed: ERR new incantation detail, batch 1 (Blood Oath + Dragon Communion + Dragon Cult).
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_incantations_batch1.py
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
    ('Retch Gore', 50, 0, 0, 13, 12, 1, '1.71%+171',
     "Sprays a short-range cone of blood before the caster. Inflicts Fire damage and causes Blood "
     "Loss buildup on both the caster and hit foes. Generates FP on hit (exact amount unverified; "
     "overview lists 1.71%+171).",
     "Generator spell - costs 0 Memory Slots. Short range only.",
     "Found on a corpse in front of a big tombstone, directly west of Prospect Town, Gravesite Plain."),

    ('Bloodrose Mist', 380, 1, 0, 16, 15, 0, None,
     "Releases a bloody mist before the caster. Mist inflicts Slash damage and causes Blood Loss "
     "buildup. Can be cast while in motion.",
     None,
     "Found on an upper ledge behind the portal to Mohgwyn Palace in the Consecrated Snowfield. "
     "Defeat a giant blood-writhing rotmound enemy to loot the incantation (drop on it from above "
     "to reach it)."),

    ('Dragonrend', 50, 0, 0, 10, 14, 1, '1.01%+101',
     "Creates dragon claw lacerations to cleave foes. Inflicts Slash damage and generates FP on hit "
     "(1.01%+101 per the overview). Can be cast repeatedly.",
     "Generator spell - costs 0 Memory Slots.",
     "Found on a corpse at the top of the broken ruins south of Church of Dragon Communion, Limgrave."),

    ("Dragonlord's Domain", 770, 2, 0, 38, 19, 0, None,
     "Transforms the caster into the Dragonlord to trap surrounding foes beyond time. Trapped foes "
     "move at a fraction of their usual speed. The enchantment does not last long.",
     None,
     "Traded from Finger Reader Enia at Roundtable Hold in exchange for the Remembrance of the "
     "Dragonlord."),

    ("Morion's Doom", 720, 3, 0, 24, 36, 0, None,
     "Transforms caster into a dragon to spew death-infused breath from above. Inflicts Holy damage "
     "and causes a Destined Death burn. Can be charged to extend duration. Can be cast while jumping. "
     "FP: 720 initial +70 per second channeled.",
     "Like other dragon breath incantations, charging extends duration.",
     "Traded for 3 Dragon Hearts at Cathedral of Dragon Communion (Caelid) after defeating Morion, "
     "the Unbound Death."),

    ('Bolt of Gransax', 460, 2, 0, 26, 0, 0, None,
     "Creates a spear of red lightning and launches it forwards from above. On impact, the spear "
     "bursts into trails of lightning covering the area. Inflicts Lightning damage. Note: different "
     "damage values from the Ash of War of the same name.",
     None,
     "Drops from a Leyndell Knight in the Capital Outskirts area by the gate, near the Finger "
     "Reader Crone."),

    ('Frozen Dragonbolt', 620, 2, 10, 36, 0, 0, None,
     "Buffs the right-hand armament for 80 seconds: adds 25 Frostbite buildup and 1%+10 Lightning "
     "damage (flat buff affected by catalyst's Faith spell scaling). On cast, deals 132 Frostbite "
     "buildup on the player and an initial explosion dealing 120 Frostbite buildup alongside "
     "Lightning damage.",
     None,
     "Drops from the Dragonkin Soldier of Nokron, encountered in Siofra River."),

    ('Frozen Lightning Wisp', 440, 2, 7, 29, 0, 0, None,
     "Summons a wisp of ice lightning to pelt foes with frozen lightning bolts. Inflicts Lightning "
     "damage and causes Frostbite buildup.",
     None,
     "Drops from a new giant flying incantation scarab in Consecrated Snowfield, west of the Night "
     "Cavalry Duo bossfight (or south-west of 'Inner Consecrated Snowfield' grace), flying near the "
     "big frozen tree."),
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
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, incantations batch 1).')


if __name__ == '__main__':
    run()
