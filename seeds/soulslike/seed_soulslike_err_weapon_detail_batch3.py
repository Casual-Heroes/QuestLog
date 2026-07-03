"""
Seed: ERR per-weapon Weight + Critical fill-in, batch 3.
Source: err.fandom.com individual weapon pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch3.py
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
    ('Fellthorn Stake', 17.0, 90,
     "Blood affinity: causes Blood Loss buildup. Fell affinity: wielding this weapon drains status "
     "effect buildup.",
     None,
     "Drops from the new Fellthorn Spirit boss found in Mountaintops of the Giants, located "
     "north-east of the 'Foot of the Forge' grace, near the Golden Seed tree.",
     "An image of a colossal, thorned stake. Licks of tortured flame have charred the twirled roots. "
     "By the decree of Queen Marika, the Fire Giants were impaled upon such stakes. With their burning "
     "blood, their resentment and their passion for their Fell God has seeped into the wood. Unique "
     "Skill: Fell Flame Flare - let the Fell God gaze upon your foes, and slam the stake down with his "
     "might, causing a fiery detonation; smaller nearby explosions follow the main blast."),
    ('Flamelost Greatblades', 25.0, 0,
     "Madness in vicinity restores 5%+50 HP, or 10%+100 HP when triggered from weapon skills. Frenzied "
     "affinity: causes Madness buildup.",
     None,
     "Drops from a Flamelost Knight spirit located after the Flamelost Knights boss in the Buried "
     "Audience Pathway (new location added in the Reforged 2.0 update).",
     "Twin greatswords of past glory, half-melted into slag by the flame of frenzy. Inflicts madness "
     "buildup. With unnatural strength, one may be wielded in each hand. As a paired weapon, both "
     "swords are held in each hand when two-handing - may not benefit from the Two-Handed Sword "
     "Talisman (unverified). Unique Skill: Flamelost Upheaval - cross the twin flamelost greatswords "
     "to ignite a short-lived flame; a blazing upward heave burns the air and transitions into a "
     "normal or strong followup attack."),
    ('Flamelost War Sword', 6.0, 100,
     "Madness in vicinity restores 5%+50 HP, or 10%+100 HP when triggered from weapon skills. Frenzied "
     "affinity: causes Madness buildup.",
     None,
     "Drops from a Flamelost Knight spirit located after the Flamelost Knight boss in the Buried "
     "Audience Pathway (new location added in the Reforged 2.0 update).",
     "Sleek blade of past glory, etched with the mark of the flame of frenzy. Inflicts madness "
     "buildup. Once granted as a favor to the praetor's most trusted knights, weapons such as this one "
     "are now dripping with the resentment of those left abandoned in his wake. Unique Skill: "
     "Flamelost Stance - stand ready with the ceremonial blade as it loses its storied luster and "
     "ignites a short-lived flame, transitioning into normal or strong attacks."),
    ('Fury of Azash', 12.5, 85,
     "Final hit of a light attack chain leaves lingering fire (exact damage unverified). Fire "
     "affinity: causes a burn effect on hit.",
     None,
     "Dropped by Azash, Pride of the Redmanes, in Redmane Castle.",
     "Rough, hastily sharpened wedge of gilded metal. Shard of the heavy blades carried by Azash, "
     "Pride of the Redmanes. The red beast of the Starscourge often breaks its blades upon its enemies "
     "in unabated bloodlust, enough to overwhelm any smith. Unique Skill: Lion's Flame - skill of "
     "Azash, who fought alongside General Radahn; launch forwards in a burning somersault, striking "
     "foes with the armament and coating it with fire, burning away any lingering rot."),
    ('Goldvine Branchstaff', 5.5, 0,
     "Boosts Attack Power and Stamina Damage when surrounded by enemies - 5 tiers, x1.04 to x1.32 "
     "depending on number of nearby foes.",
     None,
     "Obtained in Sainted Hero's Grave. After falling through the collapsed floor, jump on the first "
     "guillotine to reach an elevated hallway on the left; use a Stonesword Key to proceed and find "
     "the weapon at the end of the path.",
     "Solid wood staff wrapped in a pattern of golden vines. Warrior monks traveled the Lands Between "
     "before their homeland fell into a bloody madness. A sect of the Golden Order was founded upon "
     "their martial principles."),
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
