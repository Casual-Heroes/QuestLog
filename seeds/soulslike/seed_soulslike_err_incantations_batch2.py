"""
Seed: ERR new incantation detail, batch 2 (Erdtree + Frenzied Flame/Golden Order).
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_incantations_batch2.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SPELLS = [
    ('Golden Star', 50, 0, 0, 12, 0, 1, '1.53%+153',
     "Creates a golden shooting star that homes in on targets. Inflicts Holy damage and generates FP "
     "on hit (1.53%+153 per the overview; exact value unverified on individual page). Can be cast "
     "while in motion or crouching.",
     "Generator spell - costs 0 Memory Slots.",
     "Found at the south-most part of the map, beyond the Morne Moangrave Site of Grace."),

    ('Kindling Spirit', 240, 1, 0, 25, 0, 0, None,
     "Conjures a golden flame that lights up dark areas and increases HP Restoration by x1.12 for "
     "caster and nearby allies. The flame deals minor Holy damage to nearby enemies (x0.2 Incant "
     "Scaling every 3 seconds). When cast while locked on, the Spirit follows the target for 30 "
     "seconds; up to 3 can be attached to a target at once. When cast with no target, the Spirit "
     "floats forward a short distance, stopping on collision with any enemy or object, lasting 60 "
     "seconds (only one untargeted spirit can be active at a time).",
     None,
     "Given to the player upon collecting five kindling spirits around the Mistwood in eastern "
     "Limgrave, all collected without dying or warping. Locations: (1) small pool south of Mistwood "
     "Outskirts Site of Grace, floating surrounded by Runebears - double-jump with Torrent to reach; "
     "(2) behind the well leading to Siofra River, on the ground; (3) on top of the hill south of "
     "the Minor Erdtree; (4) north of the Miranda Blossoms at the upper section edge near the "
     "graveyard; (5) inside the center column at the highest part of Mistwood Ruins, requiring "
     "parkour with Torrent."),

    ('Projection of Gold', 310, 1, 0, 23, 0, 0, None,
     "Projects a sphere of golden light to smite foes. Inflicts Holy damage.",
     None,
     "Drops from the dismounted Tree Sentinel found on the Bridge of Sacrifice between Limgrave and "
     "Weeping Peninsula."),

    ('Contorting Frenzy', 300, 1, 0, 23, 0, 0, None,
     "Inflicts 60 Madness buildup on the caster and shoots a large madness projectile. If the "
     "projectile hits an enemy: caster receives +0.5 Target Priority, x1.5 Enemy Hearing and x1.5 "
     "Enemy Vision for 5 seconds (nearly guaranteeing the enemy changes target to the caster). The "
     "enemy receives 60 Madness buildup, increased alertness (+0.1 Target Priority), x1.15 All "
     "Damage taken, and slightly increased action speed after attacks for 30 seconds. Projectile: 50 "
     "base Fire damage, 400 Stamina Damage, 25 Poise Damage. Cannot be charged.",
     "The debuffs on the enemy make it attack faster and deal more damage - a high-risk debuff "
     "spell best used when you need the enemy to focus on you.",
     "Acquired after giving the Three Fingers' Scrawl prayerbook to an incantation teacher. The "
     "prayerbook is found in the Serpentine Depths in Mt. Gelmir."),

    ('Frenzyflame Armament', 400, 1, 0, 19, 0, 0, None,
     "Engulfs the right-hand armament with the Flame of Frenzy for 80 seconds. Deals 100 Madness "
     "buildup on the player on cast. Adds 25 Madness buildup and 1.0125x+5 Fire Attack Power to "
     "the right-hand armament. Flat buff is affected by 100% of catalyst Strength, Dexterity, "
     "Intelligence, and Faith spell scaling. Can be cast while in motion.",
     None,
     "Acquired after giving the Three Fingers' Scrawl prayerbook to an incantation teacher. "
     "Prayerbook found in the Serpentine Depths in Mt. Gelmir."),

    ('Frenzyspore Mist', 380, 1, 0, 18, 0, 0, None,
     "Releases a maddening mist before the caster. Inflicts Fire damage and causes Madness buildup. "
     "Charging enhances range and duration of the mist.",
     None,
     "Found by defeating a Black Miranda Blossom south of the Church of Inhibition in northeastern "
     "Liurnia."),

    ('Glyph of Suppression', 270, 1, 17, 17, 0, 0, None,
     "Conjures a forward-facing glyph that emits projectiles inflicting Holy damage and Madness "
     "buildup. Leaves behind twisted gold upon expiration. Gathering the twisted gold slightly "
     "restores HP, drains Madness buildup, and empowers the caster.",
     "Counts as both a Frenzied Flame and Golden Order incantation for damage-boosting effects.",
     "After defeating the Equilibrious Beast at the end of the Subterranean Shunning-Grounds, "
     "continue to the Frenzied Flame Proscription. In the very first corridor, pick up the "
     "incantation from a corpse."),

    ('Mark of the Beast', 810, 3, 37, 37, 0, 0, None,
     "Conjures an ordered glyph beneath a foe that detonates after a delay. Inflicts Holy damage "
     "and causes Madness buildup. Leaves behind twisted gold. Gathering the twisted gold slightly "
     "restores HP, drains Madness buildup, and empowers the caster.",
     "Counts as both a Frenzied Flame and Golden Order incantation. Very high stat requirements "
     "(37 Int / 37 Fai).",
     "Found in the Frenzied Flame Proscription. Descend to the bottom of the wall coffin parkour "
     "section but don't plunge the central shaft - instead reach the coffin that accesses the level "
     "with the Fingerprint Stone Shield; the incantation is on that level."),
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
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, incantations batch 2).')


if __name__ == '__main__':
    run()
