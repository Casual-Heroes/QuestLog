"""
Seed: ERR Fortune mechanical detail, batch 1 of N.
Source: err.fandom.com individual Fortune pages, pasted directly by user.

Fills buffs/drawbacks/unique_effects for: Adherent, Apothecary, Assassin, Barbarian, Cleric, Dancer.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_fortunes_detail_batch1.py
"""
import json
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# Each entry: name -> { buffs: [...], drawbacks: [...], unique_effects: "full mechanic text" }
FORTUNES_DETAIL = {
    'Adherent': {
        'buffs': [
            '+2 Faith',
            '+1 Memory Slot',
        ],
        'drawbacks': [
            'x1.05 Elemental (Magic/Fire/Lightning/Holy) Attack Power taken',
            'x0.9 Poise',
        ],
        'unique_effects': (
            "Unique Mechanic - Corrupting Zeal: Repeatedly casting incantations of the same spell school "
            "builds up 'Corrupting Zeal' for that school. Progress increases based on memory slot cost, "
            "degrades over time and when casting a different school's incantations. "
            "When casting a support incantation: +75 Cast Speed for 60s, x0.95 Attack Power and Poise Damage "
            "of unboosted incantations. "
            "Corrupting Zeal (active for one spell school at a time, 3 tiers): "
            "Tier 1 x1.05 Attack Power / x1.02 Stamina+FP cost; Tier 2 x1.1 Attack Power / x1.04 cost; "
            "Tier 3 x1.2 Attack Power / x1.08 cost. "
            "At Tier 3, casting incantations of the chosen school deals feedback damage to self (scales with memory slot cost). "
            "Casting any sorcery while Corrupting Zeal is active deals maximum feedback damage to self. "
            "Minor Fortune Effect: when casting a support incantation, +75 Cast Speed for 60s only (no Zeal mechanic)."
        ),
    },
    'Apothecary': {
        'buffs': [
            '+3 Arcane',
            '+30 Projectile Range when wielding crossbows',
        ],
        'drawbacks': [
            'x0.9 FP cost of consumables (this is actually a buff/discount)',
            'x1.05 Stamina cost of attacks',
            'x1.1 Stamina cost of blocks',
            'x1.1 FP cost of skills and spells',
        ],
        'unique_effects': (
            "Unique Mechanic - Jarwight's Collection: Landing attacks with weapons, crossbows, elemental stone "
            "items, and reusable tools builds a buff (up to 3 stacks, 250 points per stack) that boosts the "
            "next pot/aromatic used. Point sources: +45 crossbow shot, +120 ballista shot, +60 elemental stone "
            "item, +60 reusable tool, weapon attacks vary by category. "
            "Consuming a pot/aromatic uses one stack: x1.3 Attack Power of pots/aromatics, x1.2 for hefty pots "
            "(boost not affected by stack count). Low-damage/status pots (Rot Pot, Poison Spraymist) do NOT "
            "consume stacks. Perfume Bottle weapons and Perfumer's Bolts do NOT count as aromatics. "
            "Minor Fortune Effect: same mechanic but single-stack only (250 points, no 3-stack storage), "
            "x1.25 Attack Power of pots/aromatics, x1.15 for hefty pots."
        ),
    },
    'Assassin': {
        'buffs': [
            '+30 Stamina Regen',
            '-0.05 Target Priority (harder for enemies to target you)',
            'x1.5 Poise Damage of consumable throwing knives (Bone/Crystal/Poisonbone Darts, Fan/Throwing Daggers, Kukris)',
            'x1.2 Poise Damage of chakrams',
            'x1.05 Poise Damage of light weapons (Axes/Backhand Blades/Beast Claws/Claws/Curved Swords/Daggers/Fists/Flails/Hammers/Hand-to-Hand/Katanas/Perfume Bottles/Spears/Straight Swords/Throwing Blades/Thrusting Swords/Twinblades/Whips)',
        ],
        'drawbacks': [
            'x0.91 Max HP',
            'x0.82 All Defense',
            'x0.75 FP restoration from flasks',
            'x1.09 Status Buildup received',
        ],
        'unique_effects': (
            "Unique Mechanic - Exploit Weakness: Successive attacks build a 4-tier buff (decays over time, "
            "rate varies by weapon category/attack type): Tier 1 x1.01 Attack Power +3 Poise Damage; "
            "Tier 2 x1.02 +4; Tier 3 x1.03 +5; Tier 4 x1.04 +6. "
            "On a critical attack: restores 3% Max HP +60, 4.5% Max FP +45, 35% Max Stamina +175. "
            "Minor Fortune Effect: critical attacks restore 2.8% Max HP +56, 4.2% Max FP +42, "
            "30% Max Stamina +150 (no Exploit Weakness buff stacking)."
        ),
    },
    'Barbarian': {
        'buffs': [
            'x1.15 Max Stamina',
            '+0.05 Target Priority',
            '+15 Poise',
        ],
        'drawbacks': [
            'x0.9 Max FP',
            'x0.84 Equip Load',
            'x0.957 Pierce Attack Power of Counterattacks (cancels their natural counter damage bonus)',
            'x1.11 damage taken from Blood Loss buildup',
            'x2 damage taken from Frostbite buildup',
            'x1.33 damage taken from Madness buildup',
            '+0.2% Max HP/s additional damage taken from Poison',
            '+0.4% Max HP/s additional damage taken from Scarlet Rot',
        ],
        'unique_effects': (
            "Unique Mechanic - Blow for Blow: Melee attacks restore HP based on hit strength (0.18% Max HP +6 "
            "up to 2.8% Max HP +44, weaker in PvP). Taking damage greatly increases HP restoration and damage "
            "negation briefly, scaling inversely with Equip Load (lower load = stronger buff). Breakpoints by "
            "Equip Load: 0%=x3.0 HP Restore/x0.78 dmg taken/3.6s duration; 25%=x2.7/x0.82/3.12s; "
            "50%=x2.25/x0.88/2.4s; 100%=x1.5/x0.98/1.2s. x0.525 HP restored from healing incantations/skills "
            "during this window (weakens Prayerful Strike/Blood Tax style healing). "
            "Nullifies most counter damage received: x0.9 (x0.95 PvP) damage taken while vulnerable to counter. "
            "Minor Fortune Effect: counter damage nullification only - x0.92 (x0.96 PvP) damage taken while "
            "vulnerable to counter, no HP restoration mechanic."
        ),
    },
    'Cleric': {
        'buffs': [
            'x1.1 Max HP',
            '+2 Memory Slot',
            'x0.95 FP cost of incantations',
            'x1.1 FP cost of skills and sorceries (more expensive)',
        ],
        'drawbacks': [
            'x0.85 Max Stamina',
            'x0.95 damage of weapons',
        ],
        'unique_effects': (
            "Unique Mechanic - Lingering Blessings: Increases HP/FP restoration from flasks for self and nearby "
            "allies (x1.1 HP, x1.05 FP). Casting healing incantations grants +1.15x Movement Speed for self and "
            "allies in 15m radius for 50s. Casting support incantations grants a damage absorption bubble for "
            "50s (or until broken): self gets x0.667 damage taken + x1.33 Poise, allies in 15m get x0.75 damage "
            "taken + x1.25 Poise. "
            "Minor Fortune Effect: flask restoration boost only - x1.08 HP, x1.04 FP for self and nearby allies, "
            "no movement speed or damage bubble mechanics."
        ),
    },
    'Dancer': {
        'buffs': [
            'x1.1 Stamina cost reduction blocking with medium shields',
            'x1.5 Stamina cost reduction blocking with greatshields',
            'x1.3 Stamina cost reduction blocking with thrusting shields',
            'x1.1 Stamina cost reduction blocking with light shields',
        ],
        'drawbacks': [
            'x0.75 FP cost of skills (this is a discount, listed here per source order)',
            'x0.95 Stamina cost of attacks (discount)',
            'x0.65 Max FP',
            'x0.95 damage of unboosted attacks',
        ],
        'unique_effects': (
            "Unique Mechanic - Ebb and Flow: Performing a deflect restores 1% +5 Stamina. Successive PERFECT "
            "deflects build a 5-tier damage buff that decays over time: Tier 1 x1.05 damage; Tier 2 x1.075; "
            "Tier 3 x1.1; Tier 4 x1.125; Tier 5 x1.15. Regular deflects and weapon attacks (scaled by hit "
            "strength) extend the buff's duration. Requires at least one perfect deflect to activate. "
            "Minor Fortune Effect: deflect restores 0.5% +3 Stamina; a perfect deflect grants x1.05 damage "
            "for 4 seconds (no stacking tiers)."
        ),
    },
}


def run():
    with engine.connect() as conn:
        updated = 0
        for name, detail in FORTUNES_DETAIL.items():
            result = conn.execute(text("""
                UPDATE sl_err_fortunes
                SET buffs = :buffs, drawbacks = :drawbacks, unique_effects = :effects
                WHERE name = :name
            """), {
                'buffs': json.dumps(detail['buffs']),
                'drawbacks': json.dumps(detail['drawbacks']),
                'effects': detail['unique_effects'],
                'name': name,
            })
            if result.rowcount:
                updated += 1
                print(f'  Updated: {name}')
            else:
                print(f'  NOT FOUND: {name}')
        conn.commit()
        print(f'\n{updated}/{len(FORTUNES_DETAIL)} Fortunes updated with full detail.')


if __name__ == '__main__':
    run()
