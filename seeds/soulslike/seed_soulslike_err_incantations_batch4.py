"""
Seed: ERR new incantation detail, batch 4 (final batch - Servants of Rot + Untyped).
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_incantations_batch4.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SPELLS = [
    ('Poison Moth Flight', 520, 2, 0, 27, 0, 0, None,
     "Releases five butterflies (four smaller, one larger) that hover in the air before flying "
     "towards the enemy. The smaller moths poison enemies; the larger moth consumes the poison to "
     "deal additional damage. Butterflies pierce the target and then circle around before slowly "
     "disappearing. The final moth moves towards the target after the smaller ones.",
     None,
     "Found on a body next to a tree in Liurnia of the Lakes, northwest of the Village of the "
     "Albinaurics Site of Grace."),

    ('Putrid Mist', 0, 1, 0, 0, 0, 0, None,
     "Releases a mist of scarlet rot before the caster. Inflicts True damage and causes Scarlet Rot "
     "buildup. Can be cast while in motion.",
     "FP cost unspecified on individual page (not listed); likely low given it was sold from Gowry "
     "in vanilla.",
     "Sold by Gowry in Caelid."),

    ('Rotten Armament', 400, 1, 0, 20, 0, 0, None,
     "Enchants the right-hand armament with rot for 80 seconds. Deals 100 Scarlet Rot buildup on "
     "the player on cast. Adds 25 Scarlet Rot buildup and 1.00625x+6 Physical Attack Power to the "
     "right-hand armament. Flat buff is affected by 100% of catalyst Faith spell scaling. Can be "
     "cast while in motion.",
     None,
     "Purchased from Gowry after progressing Millicent's quest - available at the same time as Pest "
     "Threads (after giving Millicent the Valkyrie's Prosthesis)."),

    ('Grasp of Eochaid', 5, 1, 0, 10, 21, 0, None,
     "Shoots a small red line towards an enemy, inflicting Magic damage and draining their vital "
     "energies while restoring HP (exact HP restored unverified). Hold the button to continue "
     "draining.",
     "Extremely low FP cost (5). Can be held to continuously drain.",
     "Drops from the Bell Bearing Hunter inside the Hermit Merchant's Shack in Altus Plateau at "
     "night."),
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
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, incantations batch 4 - FINAL).')
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_spells WHERE effect IS NOT NULL")).scalar()
        grand_total = conn.execute(text("SELECT COUNT(*) FROM sl_err_spells")).scalar()
        print(f'All spells with full detail: {total}/{grand_total} - {"COMPLETE" if total == grand_total else "remaining gaps"}')


if __name__ == '__main__':
    run()
