"""
Seed: ERR Shadowed Curios full detail - fills the 9 stub rows from the overview seed
with acquisition, and the 3 selectable effects (each with Base/+1/+2 text) per Curio.
Source: err.fandom.com individual Curio pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_curios_detail.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, acquisition_detail, effect1_name, effect1_text, effect2_name, effect2_text, effect3_name, effect3_text)
CURIOS = [
    ('Academy',
     "Found in a cave to the southwest of the Cathedral of Manus Metyr, in the same cave with Ash of "
     "War: Carian Sovereignty.",
     'Studied Academy Curio',
     "Slightly increases maximum FP for a duration. Increases Max FP based on the cast spell's Memory "
     "Slot; every buff applies separately and stacks. Base (6s): x1.0067/x1.02/x1.03/x1.04 for "
     "0/1/2/3-slot spells. +1 (7s): x1.008375/x1.025/x1.0375/x1.05. +2 (8s): x1.01/x1.03/x1.045/x1.06.",
     'Sellian Academy Curio',
     "Increases the effectiveness of dodging for a brief duration. Base: +1 I-Frame for 4 seconds. "
     "+1: +1 I-Frame for 5 seconds. +2: +1 I-Frame for 6 seconds.",
     'Lazuli Academy Curio',
     "Reduces the FP consumption of skills for a duration. Base: x0.8 FP Cost of skills for 8 seconds. "
     "+1: x0.8 FP Cost of skills for 12 seconds. +2: x0.7 FP Cost of skills for 12 seconds."),

    ('Dragonscale',
     "Found on the body of a fallen drake to the south of the Grand Altar of Dragon Communion site of "
     "grace, behind the large fallen dragon.",
     'Ancient Dragonscale Curio',
     "Vastly increases poise for a brief duration. Base: +40 Poise for 4 seconds. +1: +40 Poise for 6 "
     "seconds. +2: +60 Poise for 6 seconds.",
     'Hidden Dragonscale Curio',
     "Releases an obscuring dark mist. Base: Darkness for 1 second. +1: Darkness for 3 seconds. "
     "+2: Darkness for 5 seconds.",
     'Sharp Dragonscale Curio',
     "Releases a burst of pierce damage based on the strength of the received hit (values are a "
     "range). Base: 38-75 Pierce Damage, 5-10 Poise Damage, 200 Stamina Damage. +1: 44-88 Pierce "
     "Damage, 6.25-12.5 Poise Damage, 200 Stamina Damage. +2: 50-100 Pierce Damage, 7.5-15 Poise "
     "Damage, 200 Stamina Damage."),

    ("Fanatic",
     "Chest reward for clearing Ensis Castlefront Camp in Gravesite Plain.",
     "Zealous Fanatic's Curio",
     "Increases action speed for a duration. Base: x1.08 Action Speed for 9 seconds. +1: x1.08 Action "
     "Speed for 12 seconds. +2: x1.1 Action Speed for 12 seconds.",
     "Inexorable Fanatic's Curio",
     "Vastly boosts all negation for a brief duration. Base: x0.7 All Damage Negation for 6 seconds. "
     "+1: x0.7 All Damage Negation for 8 seconds. +2: x0.6 All Damage Negation for 8 seconds.",
     "Boundless Fanatic's Curio",
     "Greatly reduces FP consumption for a duration. Base: x0.8 FP Cost of all actions for 8 seconds. "
     "+1: x0.8 FP Cost of all actions for 12 seconds. +2: x0.7 FP Cost of all actions for 12 seconds."),

    ('Gate',
     "Found near the initially sealed gate after Divine Beast Dancing Lion.",
     'Hallowed Gate Curio',
     "Slightly restores HP if in combat. Base: 0.28% Max HP + 8 restoration over 2 seconds. "
     "+1: 0.36% Max HP + 10 restoration over 2 seconds. +2: 0.44% Max HP + 12 restoration over 2 "
     "seconds.",
     'Mystical Gate Curio',
     "Boosts cast speed for a duration. Base: +80 Cast Speed for 6 seconds. +1: +100 Cast Speed for "
     "7.5 seconds. +2: +120 Cast Speed for 9 seconds.",
     'Impervious Gate Curio',
     "Increases status resistance. Base: x1.05+1 Status Resistance and x0.99 Status Buildup taken for "
     "15 seconds. +1: x1.06+2 Status Resistance and x0.98 Status Buildup taken for 15 seconds. "
     "+2: x1.06+2 Status Resistance and x0.98 Status Buildup taken for 20 seconds."),

    ('Knifeprint',
     "Found in the Shaman Village, at the front door of the hut facing the small golden tree.",
     'Restorative Knifeprint Curio',
     "Boosts the restoration and action speed of flask of tears for a duration. Base (6s): x1.2 "
     "Crimson, x1.28 Cerulean. +1 (6s): x1.26 Crimson, x1.34 Cerulean. +2 (6s): x1.32 Crimson, x1.4 "
     "Cerulean.",
     'Concealing Knifeprint Curio',
     "Conceals wearer's presence and reduces the volume of sounds for a duration. Base: x0.65 Enemy "
     "Hearing and applies Unseen Form for 14 seconds. +1: same, 18 seconds. +2: same, 22 seconds.",
     'Viridian Knifeprint Curio',
     "Vastly decreases stamina consumption of attacks for a duration. Base: x0.55 Stamina Cost of "
     "attacks for 8 seconds. +1: x0.55 Stamina Cost of attacks for 12 seconds. +2: x0.4 Stamina Cost "
     "of attacks for 12 seconds."),

    ("Physician",
     "Found in the Specimen Storehouse. Take the elevator on the first floor to the west of the "
     "Specimen Storehouse, First Floor site of grace, and then continue to the large room with jars "
     "roaming around. The curio is on the altar.",
     "Physician's Equivalent Curio",
     "Slightly restores the other flask's resource. Base: 4% Max FP+1 (Crimson), 6% Max HP+1 "
     "(Cerulean). +1: 6% Max FP+1, 9% Max HP+1. +2: 8% Max FP+1, 12% Max HP+1.",
     "Physician's Oracle Curio",
     "Grants a protective barrier for 2 seconds based on which flask is imbibed. Base: x0.8 (x0.9 "
     "PVP) Damage Taken Crimson, x0.7 (x0.85 PVP) Damage Taken Cerulean, x1.25 Poise. +1: x0.725 "
     "(x0.8625 PVP), x0.6 (x0.8 PVP), x1.38 Poise. +2: x0.65 (x0.825 PVP), x0.5 (x0.75 PVP), x1.54 "
     "Poise.",
     "Physician's Enduring Curio",
     "Restores stamina over three seconds. Base: 22.1% Max Stamina restoration. +1: 28.05% Max "
     "Stamina restoration. +2: 34% Max Stamina restoration."),

    ("Poacher",
     "Found in the forest on the north-west of Rauh Base, on a rock formation between two Runebears.",
     "Expeditious Poacher's Curio",
     "Provides a burst of movement speed for a duration. Base: x1.4 Movement Speed for 4 seconds. "
     "+1: x1.4 Movement Speed for 5 seconds. +2: x1.6 Movement Speed for 5 seconds.",
     "Ambushing Poacher's Curio",
     "Greatly boosts the power of the next crouch attack. Base (6s): x1.75 (x1.25 PvP) Damage, x1.75 "
     "Poise Damage. +1 (9s): x1.75 (x1.25 PvP) Damage, x1.75 Poise Damage. +2 (9s): x2 (x1.33 PvP) "
     "Damage, x2 Poise Damage.",
     "Eagle-Eyed Poacher's Curio",
     "Vastly increases projectile range for a duration. Base: +90 Projectile Range for 12 seconds. "
     "+1: +105 Projectile Range for 15 seconds. +2: +120 Projectile Range for 18 seconds."),

    ('Ranah',
     "Found by defeating a Cemetery Shade, north of Cerulean Coast Cross site of grace.",
     'Daunting Curio of Ranah',
     "Slightly increases poise damage. Base: x1.04 Poise Damage. +1: x1.05 Poise Damage. +2: x1.06 "
     "Poise Damage.",
     'Starlit Curio of Ranah',
     "Slightly restores FP if in combat. Base: 0.12% Max FP+1 restoration. +1: 0.16% Max FP+2 "
     "restoration. +2: 0.2% Max FP+3 restoration.",
     'Whirling Curio of Ranah',
     "Reduces stamina consumption of dodging for a brief duration. Base: x0.76 Stamina Cost of "
     "dodging for 2 seconds. +1: x0.76 Stamina Cost of dodging for 3 seconds. +2: x0.68 Stamina Cost "
     "of dodging for 3 seconds."),

    ('Scadutear',
     "Found in the big bowl after the battle with Commander Gaius.",
     'Curative Scadutear Curio',
     "Grants full status buildup resistance for a brief duration. Base: x0 Status Buildup received "
     "for 12 seconds. +1: x0 Status Buildup received for 16 seconds. +2: x0 Status Buildup received "
     "for 20 seconds.",
     'Emboldening Scadutear Curio',
     "Slightly increases all attributes for a duration. Base: +2 Attributes for 60 seconds. +1: +2 "
     "Attributes for 90 seconds. +2: +3 Attributes for 90 seconds.",
     'Fortuitous Scadutear Curio',
     "Grants a random additional Crystal Tear effect. +1: 20% chance for a second additional effect. "
     "+2: 40% chance for a second additional effect."),
]


def run():
    with engine.connect() as conn:
        updated = 0
        for name, acq, e1n, e1t, e2n, e2t, e3n, e3t in CURIOS:
            combined = (
                f"Effect 1 - {e1n}: {e1t}\n\n"
                f"Effect 2 - {e2n}: {e2t}\n\n"
                f"Effect 3 - {e3n}: {e3t}"
            )
            result = conn.execute(text("""
                UPDATE sl_err_curios
                SET acquisition_detail = :acq,
                    effect_rank1 = :e1, effect_rank2 = :e2, effect_rank3 = :e3
                WHERE section = 'curio' AND name = :name
            """), {
                'acq': acq,
                'e1': f"{e1n}: {e1t}",
                'e2': f"{e2n}: {e2t}",
                'e3': f"{e3n}: {e3t}",
                'name': name,
            })
            if result.rowcount:
                updated += 1
                print(f'  Updated: {name}')
            else:
                print(f'  NOT FOUND: {name}')
        conn.commit()
        print(f'\n{updated}/9 Curios fully detailed.')


if __name__ == '__main__':
    run()
