"""
Seed: ERR Fortune mechanical detail, batch 2 of N.
Source: err.fandom.com individual Fortune pages, pasted directly by user.

Fills buffs/drawbacks/unique_effects for: Heretic, Ranger, Sage, Sentinel, Sorcerer,
Spellsword, Veteran. This completes all 13 Common Fortunes.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_fortunes_detail_batch2.py
"""
import json
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

FORTUNES_DETAIL = {
    'Heretic': {
        'buffs': [
            'x1.05 Status Buildup dealt',
            '+1 Memory Slot',
        ],
        'drawbacks': [
            '-3 Vigor',
            'x0.8 Innate Status Resistance',
            'x0.95 Rune Gain',
        ],
        'unique_effects': (
            "Unique Mechanic - Vector of Infection: While under any status effect (applied separately per "
            "status type, self-inflicted statuses count, e.g. Bleed from Seppuku): x0.95 FP Cost of all "
            "actions, +30 Stamina Regen (diminishing returns), +2 Arcane, lasting 120s per status. "
            "While under TWO OR MORE statuses simultaneously: +0.2% +3 HP Regen every 2s, +0.3% +4 FP Regen "
            "every 2s (does not stack further past 2 statuses, but Stamina Regen does keep stacking per status). "
            "Minor Fortune Effect: +30 Stamina Regen per active status type (90s duration), no FP discount, "
            "no HP/FP regen tier."
        ),
    },
    'Ranger': {
        'buffs': [
            '+40 Item Discovery',
            'x1.15 Common Buff Duration',
            'x1.1 Movement Speed when wielding bows',
        ],
        'drawbacks': [
            'x0.94 Status Buildup received (this is a resistance buff worded as a multiplier)',
            'x0.9 HP restoration from flasks',
            'x0.9 FP restoration from flasks',
            'x0.9 Poise Damage dealt',
        ],
        'unique_effects': (
            "Unique Mechanic - Eagle Eye: Landing weapon/bow attacks grants a 5s stamina-cost-reduction buff "
            "(x0.99 to x0.9 Stamina Cost of successive attacks based on hit strength) - stacks with itself and "
            "other tiers. While the stamina buff is active, a separate 10-tier buff builds over time (keeps "
            "building even without landing attacks, expires when the stamina buff expires): "
            "tiers 1-2=+5/+10 Projectile Range x1.005/x1.01 dmg; tiers 3-4=+15/+20 range x1.015/x1.02; "
            "tiers 5-6=+25/+30 range x1.025/x1.03; tiers 7-8=+35/+40 range x1.035/x1.04; "
            "tiers 9-10=+45/+50 range x1.045/x1.05. "
            "Minor Fortune Effect: stamina-cost-reduction buff only (x0.995 to x0.95, 5s duration, stacks), "
            "no projectile range/damage tier system."
        ),
    },
    'Sage': {
        'buffs': [
            'x1.1 Max FP',
            '+2 Memory Slot',
        ],
        'drawbacks': [
            '-1 Vigor',
            'x1.12 Physical Damage taken',
            'x1.1 FP Cost of skills and consumables',
            'x0.9 Physical Attack Power of weapons',
        ],
        'unique_effects': (
            "Unique Mechanic - Devoted Studies: Casting a spell grants bonus FP and Stamina restoration based "
            "on memory slot cost (0-slot: +7 FP/+7%+0.7% Stamina; 1-slot: +7+0.238% FP/+7+1.4% Stamina; "
            "2-slot: +7+0.7% FP/+7+2.8% Stamina; 3-slot: +7+1.169% FP/+7+5.6% Stamina). "
            "Casting spells of DIFFERENT memory slot costs builds a stacking damage buff (up to 3 tiers): "
            "Tier 1 x1.025, Tier 2 x1.05, Tier 3 x1.1 spell Attack Power. Each slot-cost boost has its own "
            "duration (0-slot 10s, 1-slot 15s, 2-slot 20s, 3-slot 25s) and the number of simultaneous active "
            "boosts determines the tier. "
            "Minor Fortune Effect: same FP/Stamina restoration on cast but exactly half values "
            "(0-slot: 0/0; 1-slot: +7+0.14% FP/+7+0.7% Stamina; 2-slot: +7+0.35%/+7+2.1%; "
            "3-slot: +7+0.7%/+7+4.2%), no stacking damage buff tiers."
        ),
    },
    'Sentinel': {
        'buffs': [
            'x1.08 Equip Load',
            'x1.1 +10 Elemental (Magic/Fire/Lightning/Holy) Defense',
            'x1.05 Attack Power of incantations',
            'x1.05 Poise',
            'x0.9 Stamina Cost of blocks with shields (discount)',
        ],
        'drawbacks': [
            '-3 Arcane',
            '-20 Stamina Regen',
            'x0.9 Movement Speed while in combat',
        ],
        'unique_effects': (
            "Unique Mechanic - Shield of Faith: Blocking an attack restores 0.4% Max FP +4 (deflects count as "
            "blocks). Taking damage restores 0.8% Max FP +8. "
            "At or below 50% Max HP: +0.2%+4 HP Regen every 2s, +100 Cast Speed, x0.9 FP Cost of incantations. "
            "Minor Fortune Effect: block restores 0.3% Max FP +3, taking damage restores 0.6% Max FP +6 "
            "(deflects count as blocks); no low-HP cast speed/FP discount tier."
        ),
    },
    'Sorcerer': {
        'buffs': [
            'x0.9 FP Cost of sorceries (discount)',
            '+1 Memory Slot',
        ],
        'drawbacks': [
            'x0.83 Poise',
            'x0.95 Max Stamina',
            'x0.8 Common Buff Duration',
        ],
        'unique_effects': (
            "Unique Mechanic - Academy Brilliance: Casting a sorcery grants a stackable 6s buff: +20 Cast "
            "Speed, x0.975 FP Cost of sorceries. After casting 9 sorceries in succession (Generator spells "
            "don't consume this), the next cast sorcery deals x1.5 Attack Power. "
            "Minor Fortune Effect: same stackable +20 Cast Speed / x0.975 FP Cost buff but 5s duration "
            "instead of 6s, no 9-cast damage bonus mechanic."
        ),
    },
    'Spellsword': {
        'buffs': [
            '+6 Mind',
            '+50 Cast Speed',
        ],
        'drawbacks': [
            'x0.65 HP restoration from non-flask sources',
            'x1.1 Status Buildup received',
            'x0.92 Attack Power of unboosted attacks',
        ],
        'unique_effects': (
            "Unique Mechanic - Sword and Scroll: Two independent 3-tier buffs that build from alternating "
            "melee/caster actions, each starts at Tier 1 by default and decays 15s after the relevant action "
            "(duration cannot be refreshed, but tier can still increase from the opposite attack type). "
            "Casting-spells buff (boosts melee + cheapens skills): Tier 1 x1.06 melee dmg/x0.98 skill FP cost; "
            "Tier 2 x1.12/x0.96; Tier 3 x1.18/x0.94. Higher memory-slot spells build this faster; Generator "
            "spells don't build it. "
            "Landing-melee buff (boosts spells + cheapens them): Tier 1 x1.06 spell dmg/x0.99 spell FP cost; "
            "Tier 2 x1.12/x0.98; Tier 3 x1.18/x0.97. Stronger attacks (weapon-category dependent) build this "
            "faster; Generator spells neither consume nor benefit from it. "
            "Minor Fortune Effect: flat (non-tiered) versions - casting spells grants x1.08 melee Attack Power "
            "/ x0.96 skill FP Cost; landing melee grants x1.08 spell Attack Power / x0.98 spell FP Cost; both "
            "expire 12s after the triggering action, Generators excluded both ways."
        ),
    },
    'Veteran': {
        'buffs': [
            'x1.02 Max HP',
            'x1.04 Max Stamina',
            'x1.03 Max FP',
            'x0.9 Stamina Cost of attacks when varying weapon attack types (discount)',
            'x1.08 FP Cost discount of spells, items and skills',
        ],
        'drawbacks': [
            'x0.8 damage dealt with backstabs',
            'x0.9 Status Buildup dealt',
        ],
        'unique_effects': (
            "Unique Mechanic - Honed Technique: Weapon attacks build a 'Decisive Strike' meter to 500 "
            "accumulation (e.g. dagger R1 = 30, colossal charged R2 = 90). Using a VARIETY of different attack "
            "types (not repeating the same type as either of the previous two attacks) grants x2.5 buildup. "
            "Casting a spell lowers buildup; leaving combat clears it entirely. "
            "At max charge (Decisive Strike active): x1.2 Poise Damage, x1.2 Attack Power, x1.2 Stamina Damage "
            "on the next weapon skill use. Being hit while charged: x0.8 damage taken, x0.9 Status Buildup "
            "received, but resets the counter to 0. Landing a guard counter while charged restores FP equal "
            "to 6x the base guard-counter restoration (e.g. 1.92%+60 FP for dagger, 4.08%+120 for colossal), "
            "not boosted by other FP-restoration effects. Using the weapon skill, guard counter, or getting "
            "staggered all consume/remove the charge. "
            "Minor Fortune Effect: flat x1.06 Attack Power of weapon skills, no Decisive Strike meter."
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

        # Progress check
        total_filled = conn.execute(text(
            "SELECT COUNT(*) FROM sl_err_fortunes WHERE buffs IS NOT NULL"
        )).scalar()
        print(f'Total Fortunes with full detail so far: {total_filled}/28')


if __name__ == '__main__':
    run()
