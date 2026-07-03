"""
Seed: ERR Fortune mechanical detail, batch 4 (FINAL) of N.
Source: err.fandom.com individual Fortune pages, pasted directly by user.

Fills buffs/drawbacks/unique_effects/how_to_unlock for all 5 Legendary Fortunes
(Beasts, Crucible, Dynasts, Latenna, Reeds) and all 3 Basic Fortunes
(Bold, Cunning, Wise). This completes all 28 ERR Fortunes.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_fortunes_detail_batch4.py
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
    # ─── Legendary ──────────────────────────────────────────────────────────
    'Beasts': {
        'how_to_unlock': "Give Gurranq all nine Deathroot.",
        'buffs': [
            'x1.1 Movement Speed (unverified exact value on wiki)',
            '+50 Cast Speed',
            'x1.5 FP Cost of consumables (discount)',
        ],
        'drawbacks': [
            '-20 Poise',
            'x0.8 HP restoration at zero Beasthood',
        ],
        'unique_effects': (
            "Unique Mechanic - Beasthood: a resource meter that drains at 230/s (105/s minor), built from: "
            "Bestial affinity active effect +50/s (does not stack), Bestial Vitality +50/s, Bestial "
            "Constitution +4625 (only if no Beasthood tier currently active), Bestial Sling +125, Beast Claw "
            "+625, Gurranq's Beast Claw +2000, Stone of Gurranq +1000, any Bestial incantation +125 during "
            "Beast's Step boost, Beast's Roar skill +750, Regal Beastclaw skill +1500, any weapon hit "
            "+10 to +100 depending on hit type. "
            "10 escalating tiers (Beasthood required: 249/1499/2249/2999/3749/4499/5249/5999/6749/7499): "
            "Physical Damage x1.05 to x1.5; Magic/Fire/Lightning Damage x1.025 to x1.25; Holy Damage x1.0375 "
            "to x1.375; Stamina Regen +4 to +40; Damage Taken x1.09 to x1.9; Status Buildup Taken x1.045 to "
            "x1.45; Target Priority +0.025 to +0.25 (linear scaling across the 10 tiers). "
            "Minor Fortune Effect: single flat 50-Beasthood tier only (not the full 10-tier ramp) - x1.1 "
            "Physical, x1.05 Magic/Fire/Lightning, x1.075 Holy, x1.15 Damage Taken, +0.025 Target Priority. "
            "Beasthood sources scaled down proportionally (e.g. Bestial Vitality still +50/s, Beast Claw +500, "
            "Gurranq's Beast Claw +1625, etc - see minor source list)."
        ),
    },
    'Crucible': {
        'how_to_unlock': "Defeat Crucible Knight Hirnan, on the other side of the Nokron waygate at the Four Belfries.",
        'buffs': [
            '+50 Cast Speed',
            'x1.08 All Defense',
        ],
        'drawbacks': [
            '-5 Arcane',
            '-50 Stamina Regen',
            'x0.9 Magic Damage',
            'x0.9 Fire Damage (excluding Aspect of the Crucible: Breath)',
            'x0.9 Lightning Damage',
            'x0.67 Duration of non-Aspect buffs',
        ],
        'unique_effects': (
            "Unique Mechanic - Aspect Empowerment: each Aspect of the Crucible spell restores 2%+40 HP and "
            "grants a 50s buff specific to that Aspect. Tail: x1.06 Physical Attack Power of weapons/skills, "
            "x1.06 Holy Attack Power of weapons/skills. Breath: +100 Stamina Regen, +2/s Status Buildup drain. "
            "Horn: x0.88 (x0.92 PvP) damage taken, x1.5 Poise. Bloom: 0.1%+1 HP restoration every 2s, x2 "
            "healing received when casting any Aspect spell. Thorn: 8% increased Action Speed, 1 additional "
            "i-frame while dodging. x0.96 (x0.99 PvP) damage taken baseline. "
            "Minor Fortune Effect: casting an Aspect of the Crucible incantation restores 2%+40 HP and grants "
            "a flat 25s buff: x1.03 Attack Power, x0.92 damage taken, +30 Stamina Regen (no per-Aspect unique "
            "effects, just one generic buff regardless of which Aspect was cast)."
        ),
    },
    'Dynasts': {
        'how_to_unlock': (
            "Defeat Sanguine Noble Annalise, a new invading NPC found in a red-lit cave under the waterfall "
            "west of the Below the Well Site of Grace, Siofra River."
        ),
        'buffs': [
            '+60 Blood Loss resistance',
            '+60 Frostbite resistance',
            'x1.05 Pierce Attack Power',
        ],
        'drawbacks': [
            'x0.85 Equip Load',
            'x0.9 Magic Attack Power',
            'x0.9 Lightning Attack Power',
            'x0.9 Holy Attack Power',
            'x0.8 HP restoration from flasks when outside the sanguine pool',
        ],
        'unique_effects': (
            "Unique Mechanic - Sanguine Pool: in the presence of Blood Loss, forms a pool for 25s. Lingering "
            "in it grants +70 Stamina Regen, x1.2 Movement Speed, 2/s HP Regen, plus melee-attack HP "
            "restoration scaled by a 4-tier buff built while standing in the pool (Tier 1: 0.5-1.5%+5-15 HP; "
            "Tier 2: 2-3%+20-30; Tier 3: 3.5-4.5%+35-45; Tier 4: 5%+50). Allies in the pool get reduced "
            "benefits (+50 Stamina Regen, 2/s HP Regen, x1.1 flask HP restoration). Foes standing in the pool "
            "take x1.08 Blood Loss buildup plus 0.12%+1 HP damage and 2 Blood Loss buildup per second. "
            "Minor Fortune Effect: same pool mechanic but weaker - +50 Stamina Regen, 1/s HP Regen, no melee "
            "HP-restoration tier system; allies get +30 Stamina Regen/1/s HP Regen; foes take x1.06 Blood "
            "Loss buildup plus 0.08%+1 HP damage and 1 Blood Loss buildup per second."
        ),
    },
    'Latenna': {
        'how_to_unlock': "Reward for giving the first half of the Haligtree Medallion to Latenna, past the Lakeside Crystal Cave.",
        'buffs': [
            'x1.1 Max FP',
            'x1.05 Attack Power of bows',
            '+20 Magic Damage of bows',
            '+30 Projectile Range of bows',
            '0.1%+1 FP Regen every 2 seconds',
        ],
        'drawbacks': [
            '-150 Stamina Regen while dashing',
            '+10 Stamina Cost of dashing',
            'Jumping costs 100 Stamina + 10% Max Stamina',
            'x0.9 Attack Power of spells',
        ],
        'unique_effects': (
            "Unique Mechanic - Child of Silver: when wielding a medium-sized bow, holding an arrow while "
            "stationary charges the shot through 3 tiers (visual/audio cue per tier). Tier 1: x1.35 Attack "
            "Power, x1.175 Stamina Damage, x1.175 Poise Damage, +10 Magic Damage, +10 Projectile Range, "
            "+0.025 Target Priority. Tier 2: x1.65 Attack Power, x1.325 Stamina/Poise Damage, +15 Magic "
            "Damage, +20 Projectile Range, +0.05 Target Priority. Tier 3: x2 Attack Power, x1.5 Stamina/Poise "
            "Damage, +20 Magic Damage, +30 Projectile Range, +0.075 Target Priority. "
            "Minor Fortune Effect: single flat charge tier (no 3-tier ramp) - x1.3 Attack Power, x1.15 "
            "Stamina/Poise Damage, +10 Magic Damage, +30 Projectile Range, +0.025 Target Priority."
        ),
    },
    'Reeds': {
        'how_to_unlock': "Defeat the Bell Bearing Hunter of the Isolated Merchant's Shack in Dragonbarrow.",
        'buffs': [
            'x0.9 Stamina Cost of blocks (discount)',
        ],
        'drawbacks': [
            'x0 Stamina Cost of raising your guard (no cost reduction benefit noted beyond this)',
            'x1.1 damage taken',
            '-2 I-Frames while dodging (does not apply in Shura Mode)',
            'x0.5 Poise Damage dealt',
            'x1.333 Stamina Cost of blocks with shields',
        ],
        'unique_effects': (
            "Unique Mechanic - Snow, Moon, and Flowers: applies when two-handing a 'light sword' (Curved "
            "Sword/Katana/Light Greatsword/Straight Sword/Thrusting Sword) or Great Katana. Grants x1.13 "
            "damage of uncharged heavy attacks, x1.33 of charged heavy attacks, x1.35 of guard counters, "
            "x1.1 of weapon skills, plus bonus Stamina Regen while guarding. Performing a deflect inflicts "
            "30-45 Poise Damage on foes ahead (scaled by deflected hit strength), x3.25 during a perfect "
            "deflect (boosted further by Hammer Talisman). Tradeoff: while two-handing a light sword/Great "
            "Katana, you're unable to move while guarding, and heavy/charged/guard-counter attacks have their "
            "natural Poise Damage bonus nullified (x0.5/x0.25/x0.33 respectively). "
            "Minor Fortune Effect: a perfect deflect inflicts only 0.1 Poise Damage on foes ahead - "
            "functionally negligible damage but interrupts enemy poise regeneration."
        ),
    },

    # ─── Basic ──────────────────────────────────────────────────────────────
    'Bold': {
        'how_to_unlock': "Automatically granted upon picking up the Oracle Effigy.",
        'buffs': [
            'x1.05 Max HP',
            'x1.025 Attack Power of melee attacks',
            'x0.975 Stamina Cost of blocks (discount)',
        ],
        'drawbacks': [
            'x0.94 Max FP',
        ],
        'unique_effects': (
            "No unique mechanic - Basic Fortunes provide simple generalist bonuses, weaker than any "
            "comparable specialized Fortune in the melee category, and intentionally so. Favors melee "
            "builds. Cannot be used as a Minor Fortune (Basic tier is excluded from the Minor Fortune system "
            "entirely)."
        ),
    },
    'Cunning': {
        'how_to_unlock': "Automatically granted upon picking up the Oracle Effigy.",
        'buffs': [
            'x1.12 Max Stamina',
            'x1.035 Attack Power of arrows, bolts, and consumable items',
            'x1.1 Common Buff Duration',
        ],
        'drawbacks': [
            'x0.95 Max HP',
        ],
        'unique_effects': (
            "No unique mechanic, but uniquely among the Basic Fortunes it has one effect not found anywhere "
            "else: a flat damage buff to ALL consumables (spell tools, throwing knives, chakrams, and any "
            "other offensive consumable item). All other effects are weaker than comparable Fortunes in the "
            "ranged/throwing category. Favors ranged and throwing-item builds. Cannot be used as a Minor "
            "Fortune."
        ),
    },
    'Wise': {
        'how_to_unlock': "Automatically granted upon picking up the Oracle Effigy.",
        'buffs': [
            'x1.085 Max FP',
            'x1.03 Attack Power of spells and catalyst heavy attacks',
            '+1 Memory Slot',
        ],
        'drawbacks': [
            'x0.93 Max Stamina',
        ],
        'unique_effects': (
            "No unique mechanic - generalist caster bonuses, weaker than any specialized casting Fortune. "
            "Favors sorcery and incantation builds, including hybrid sorcery+incantation builds or sorcery-"
            "focused builds with secondary buff usage. Cannot be used as a Minor Fortune."
        ),
    },
}


def run():
    with engine.connect() as conn:
        updated = 0
        for name, detail in FORTUNES_DETAIL.items():
            result = conn.execute(text("""
                UPDATE sl_err_fortunes
                SET buffs = :buffs, drawbacks = :drawbacks, unique_effects = :effects, how_to_unlock = :unlock
                WHERE name = :name
            """), {
                'buffs': json.dumps(detail['buffs']),
                'drawbacks': json.dumps(detail['drawbacks']),
                'effects': detail['unique_effects'],
                'unlock': detail['how_to_unlock'],
                'name': name,
            })
            if result.rowcount:
                updated += 1
                print(f'  Updated: {name}')
            else:
                print(f'  NOT FOUND: {name}')
        conn.commit()
        print(f'\n{updated}/{len(FORTUNES_DETAIL)} Fortunes updated with full detail (final batch).')

        total_filled = conn.execute(text(
            "SELECT COUNT(*) FROM sl_err_fortunes WHERE buffs IS NOT NULL"
        )).scalar()
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_fortunes")).scalar()
        print(f'\n=== FINAL: {total_filled}/{total} Fortunes fully detailed ===')


if __name__ == '__main__':
    run()
