"""
Seed: ERR new spell detail, batch 5 (Primeval + Redmane + Untyped sorceries - final sorcery batch).
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_spells_batch5.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SPELLS = [
    ('Cerulean Sea', 500, 2, 56, 0, 0, 0, None,
     "Creates a stationary pool that persists on the ground. While within the radius, caster and "
     "allies regenerate 0.3%+24 FP every 2 seconds in combat (0.1%+8 for allies), but take x1.1 "
     "Elemental Damage. Enemies in the pool also take x1.1 Elemental Damage. Up to three pools can "
     "be present at once, but FP regeneration and elemental negation reduction effects do not stack.",
     "Affects allies and foes alike.",
     "Rewarded for clearing the Sunken Rise puzzle in Cerulean Coast, near the hole leading to Stone "
     "Coffin Fissure. Go north of the rise to the center of the stern of the big sunken ship; spot "
     "bubbles in the ocean and jump into them (not on Torrent). You spawn in a cave with 1 HP/FP/Stamina "
     "- touch three bubble pools guarded by Crystalians without getting hit. Upon clearing, teleport "
     "to the top of the rise."),

    ('Blazing Wall', 440, 2, 30, 0, 0, 0, None,
     "Unleashes a wave of flame that leaves lingering fire pillars in its wake. Inflicts Fire damage "
     "and causes a lingering burn effect. Charging increases the duration of the pillars.",
     None,
     "Found in a crow's nest guarded by a pilfering crow on a ledge above the Shack of the Rotting."),

    ('Fist of the Heavens', 660, 3, 45, 0, 0, 0, None,
     "Conjures a fiery meteor to smite foes, crashing into the target location after some delay. "
     "Inflicts Fire damage and leaves a lingering burn effect. Can be charged for variable amounts "
     "of time - the meteor's power gradually increases while charging.",
     "Charging continuously enhances potency up until release.",
     "Found in a crow's nest guarded by a pilfering crow on a ledge above the Shack of the Rotting."),

    ('Ancient Tracer', 550, 2, 41, 0, 0, 0, None,
     "Summons an initial circular Magic blast centered on the player, then summons magical spheres "
     "out of the ground. Each sphere fires a continuous beam of Magic at a locked-on enemy. Beams "
     "cannot be redirected once established, and only fire at locked-on enemies (beams fire into the "
     "sky if cast without lock-on). Uncharged: 1 sphere. Charged: 3 spheres.",
     "Works best on slow/stationary targets like Erdtree Avatars. Inflicts Magic damage.",
     "Drops from the unique magic guardian golem on a ledge beneath Fort Faroth. From the Fort Faroth "
     "Site of Grace, head north-east toward the Minor Erdtree and descend via spiritspring, then "
     "head south-east toward a large pot by the cliffside, drop down the gap between the pillar's "
     "corner and cliffside onto a root, and descend down roots and pillars to fight the golem."),

    ('Scornful Gaze', 290, 1, 15, 0, 0, 0, None,
     "Pelts a targeted foe with a focused beam of light. Inflicts True damage.",
     None,
     "Found inside Stone Coffin Fissure, near the minefield of exploding Sentry Stones near the "
     "Fissure Waypoint grace."),

    ('Transmigration Call', 480, 2, 44, 11, 0, 0, None,
     "Rebirths a nearby soul to crash down upon foes as a spirit tombstone. Deals pure Holy damage. "
     "When the tombstone hits the enemy, applies for 20 seconds: damage per second (varies by enemy "
     "type - weaker enemies take more, bosses less; resets on recast, does not stack), x0.75 HP "
     "restoration from flasks and non-flask sources, x0.9 Poise Damage dealt.",
     None,
     "Traded from Finger Reader Enia at Roundtable Hold in exchange for the Remembrance of the Full "
     "Moon Queen."),
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
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, batch 5 - sorceries COMPLETE).')
        total_detailed = conn.execute(text(
            "SELECT COUNT(*) FROM sl_err_spells WHERE effect IS NOT NULL"
        )).scalar()
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_spells")).scalar()
        print(f'Spells with full detail: {total_detailed}/{total}')


if __name__ == '__main__':
    run()
