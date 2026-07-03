"""
Seed: ERR Fortune mechanical detail, batch 3 of N.
Source: err.fandom.com individual Fortune pages, pasted directly by user.

Fills buffs/drawbacks/unique_effects/how_to_unlock for all 7 Rare Fortunes:
Brave, Bulwark, Godslayers, Haima, Houses, Spiritcaller, Warmaster.
Completes the entire Rare tier with exact acquisition locations (replacing the
generic placeholder text from the initial taxonomy seed).

Run: chwebsiteprj/bin/python3 seed_soulslike_err_fortunes_detail_batch3.py
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
    'Brave': {
        'how_to_unlock': (
            "Defeat a Kaiden Sellsword found in the Capital Outskirts, north of the Draconic Tree Sentinel. "
            "Nearest Site of Grace: Capital Rampart."
        ),
        'buffs': [
            '+2 Vigor',
            '+2 Endurance',
            'x1.05 Attack Power of roar arts and stomp attacks',
        ],
        'drawbacks': [
            'Decreases poise at higher equip loads, up to x1.49 Poise Damage Taken',
            'x0.8 Guard Boost',
            '-150 Cast Speed',
        ],
        'unique_effects': (
            "Unique Mechanic - Grit Your Teeth: Weapon attacks, roar arts, and stomp skills build the "
            "'Northern Temper' effect (progress scales with hit severity and current level). Being staggered "
            "from broken poise lowers buildup (scaled by hit severity/current level) and decreases weapon "
            "attack action speed. "
            "Special Effect - Northern Temper: increases damage negation as temper rises. While charging a "
            "heavy weapon attack or roar-skill followup: ignores stagger/knockback, triples damage negation; "
            "if struck while charging, greatly increases the charged attack's power for its duration. Effect "
            "stage lowers when struck or upon finishing a charged heavy attack. Decreases non-flask healing as "
            "temper increases. "
            "Minor Fortune Effect: while charging attacks, x0.85 damage taken and x0.85 Status Buildup "
            "received (no Northern Temper meter)."
        ),
    },
    'Bulwark': {
        'how_to_unlock': (
            "Defeat the lone Godrick Knight in a small camp at the edge of a cliff south-west of Ailing "
            "Village, Weeping Peninsula."
        ),
        'buffs': [
            '+6 Endurance',
            '+0.15 Target Priority',
            'x1.25 Guard Boost of Colossal Swords',
            'x1.225 Guard Boost of Colossal Weapons',
            'x1.45 Guard Boost of Curved Greatswords',
            'x1.35 Guard Boost of Greataxes',
            'x1.35 Guard Boost of Great Hammers',
            'x1.375 Guard Boost of Great Katanas',
            'x1.05 Guard Boost of Greatshields',
            'x1.375 Guard Boost of Great Spears',
            'x1.425 Guard Boost of Greatswords',
            'x1.15 Guard Boost of Thrusting Shields',
            'x1.45 Guard Boost of Halberds',
            'x1.5 Guard Boost of Heavy Thrusting Swords',
        ],
        'drawbacks': [
            'Always locked at Massive Frame equip load tier',
            'x0.92 Damage dealt',
            'x1.25 FP Cost of spells',
        ],
        'unique_effects': (
            "Unique Mechanic - Indomitability (when wielding greatshields, great weapons, or colossal "
            "weapons): performing a deflect grants immunity to being flung backward and x0.9 Stamina Damage "
            "to foes ahead for 6s (stacks). After guarding an attack or during a running attack: x1.12 Poise "
            "Damage (guarding) / x1.18 Poise Damage (running attack), and attacks decrease enemy Action Speed "
            "for 1s by tier: x0.755 Bosses/Minibosses (x0.825 co-op), x0.72 Elite (x0.8 co-op), x0.685 Major "
            "(x0.775 co-op), x0.65 Minor (x0.75 co-op). "
            "Minor Fortune Effect: x0.85 Stamina Cost of blocks when NOT deflecting (no deflect/guard counter "
            "mechanics)."
        ),
    },
    'Godslayers': {
        'how_to_unlock': "Defeat the Godskin Noble of the Divine Tower of Liurnia.",
        'buffs': [
            'x0.9 FP Cost of skills (discount)',
            '+2 Dexterity',
        ],
        'drawbacks': [
            'x0.75 HP restoration from flasks (disabled entirely for next Crimson Flask if near an enemy '
            'afflicted with Black Flame for 6s)',
            'x0.93 Attack Power of two-handed attacks',
            'x0.87 Attack Power of powerstanced attacks',
            'x1.05 damage taken while not in the presence of Black Flame',
        ],
        'unique_effects': (
            "Unique Mechanic - Black Flame Eulogy: +1.6s duration of Black Flame effects applied by "
            "incantations (extends Black Flame Blade to 8.5s instead of 8s). In the presence of Black Flame "
            "(regardless of source - player, ally, or enemy): +75 Cast Speed, x0.75 Stamina Cost, x0.867 "
            "damage taken, x0.85 FP Cost of incantations. "
            "Minor Fortune Effect: +0.6s duration of Black Flame effects, x0.85 damage taken in the presence "
            "of Black Flame (no cast speed/stamina/FP bonuses)."
        ),
    },
    'Haima': {
        'how_to_unlock': "Defeat Battlemage Hugues in the Sellia Evergaol.",
        'buffs': [
            'x1.05 Strike Attack Power of weapons',
        ],
        'drawbacks': [
            'x0.8 FP Cost of sorceries (this is actually a discount)',
            'x0.8 Max FP',
            'x0.8 Critical Damage',
            '-30 FP restoration from generator spells',
        ],
        'unique_effects': (
            "Unique Mechanic - Academy Justice: x1.25 Poise Damage / x0.8 Attack Power of Academy sorceries "
            "(Cannon of Haima, Comet, Crystal Barrage, Crystal Burst, Gavel of Haima, Glintstone Arc, "
            "Glintstone Cometshard, Glintstone Pebble, Glintstone Stars, Great Glintstone Shard, Rock Blaster, "
            "Shard Spiral, Shatter Earth, Star Shower, Swift Glintstone Shard, plus Decree of Haima skill). "
            "Stance-breaking a foe restores 10%+100 FP and 20%+100 Stamina. Stance-breaking after casting an "
            "Academy sorcery overrides to x1.25 Attack Power / x0.75 Poise Damage of Academy sorceries for 9s, "
            "plus immunity to weak staggers for 9s. "
            "Minor Fortune Effect: stance-breaking restores 5%+50 FP / 10%+50 Stamina; stance-breaking after "
            "casting ANY spell grants x1.1 Attack Power of spells for 6s (not limited to Academy sorceries)."
        ),
    },
    'Houses': {
        'how_to_unlock': "Defeat the Bell Bearing Hunter at the Church of Vows.",
        'buffs': [
            '+2 Memory Slot',
            '+2 Intelligence',
            '+2 Faith',
            'x1.25 FP Cost of unboosted spells (discount)',
        ],
        'drawbacks': [
            '-3 Strength',
            '-3 Dexterity',
        ],
        'unique_effects': (
            "Unique Mechanic - Royal Marriage: Casting any spell grants +50 Cast Speed and x0.75 Stamina Cost "
            "for 20s. After casting an incantation/sorcery, the OPPOSITE spell type gets x1.08 Attack Power "
            "and x0.92 FP Cost for 20s (only applies to the next spell of that type, then swaps back). Chaining "
            "6 boosted spells in succession (alternating types) grants the 7th spell x0.25 FP Cost and x0.444 "
            "Stamina Cost. "
            "Minor Fortune Effect: after casting an incantation/sorcery, opposite type gets x1.04 Attack Power "
            "/ x0.92 FP Cost for 10s only (no 6-chain bonus)."
        ),
    },
    'Spiritcaller': {
        'how_to_unlock': "Defeat the Spiritcaller Snail boss in the Road's End Catacombs.",
        'buffs': [
            'Increases movement speed',
        ],
        'drawbacks': [
            'Decreases max HP, Stamina, Attack Power, and Status Buildup while a Spirit Ash is summoned',
            'Vastly decreases max FP when no Spirit Ash is summoned',
        ],
        'unique_effects': (
            "Unique Mechanic - Spirit Bond: Summoning a Spirit Ash enables the 'Spirit Ring' - having passive "
            "Spirit Ashes in range increases the Ring's effectiveness over time. Passive Spirit Ashes in range "
            "gain increased target priority + damage negation, and restore the summoner's HP/FP. Enraged "
            "Spirit Ashes in range gain increased action speed + damage negation and restore the summoner's "
            "Stamina. Spirit Ashes lose HP if not enraged for extended periods. "
            "Minor Fortune Effect: nearby Spirit Ashes take decreased damage (no HP/FP/Stamina restoration to "
            "the summoner)."
        ),
    },
    'Warmaster': {
        'how_to_unlock': "Defeat the Bell Bearing Hunter in Warmaster's Shack, Limgrave.",
        'buffs': [
            '+1 Strength',
            '+1 Dexterity',
            'x1.1 Stamina Cost discount',
        ],
        'drawbacks': [
            '-5 Arcane',
            'x0.8 damage of spells',
            '-125 Cast Speed',
            'x0.8 damage of unfavored weapons',
            'Cannot swap equipment (armor, quick items, arrows/bolts, talismans) while in combat',
        ],
        'unique_effects': (
            "Unique Mechanic - Luck of the Draw: Every 62.5 seconds, designates a 'favored' weapon arsenal "
            "from 6 categories (Bladed: Colossal Swords/Daggers/Greatswords/Light Greatswords/Straight "
            "Swords/Throwing Blades; Hefty: Axes/Colossal Weapons/Flails/Greataxes/Great Hammers/Hammers; "
            "Exotic: Backhand Blades/Curved Greatswords/Curved Swords/Great Katanas/Katanas/Twinblades; "
            "Finesse: Great Spears/Halberds/Heavy Thrusting Swords/Reapers/Spears/Thrusting Swords; "
            "Savage: Beast Claws/Claws/Fists/Hand-to-Hand/Whips; Auxiliary: Ballistas/Bows/Crossbows/Great "
            "Bows/Greatshields/Light Bows/Medium Shields/Small Shields/Thrusting Shields/Torches). Successful "
            "attacks accelerate the next designation by ~0.6s, being hit slows it by ~0.3s; the same arsenal "
            "can't repeat twice in a row. Wielding a favored weapon grants x1.25 (x1.2 PvP) Attack Power for "
            "the first 15s, then x1.125 (x1.1 PvP) until designation expires - this fully disables the x0.8 "
            "unfavored-weapon penalty while active - plus x0.9 FP Cost of skills. "
            "Minor Fortune Effect: same favored-arsenal rotation mechanic, but flat x1.1 Attack Power / x0.9 "
            "FP Cost of skills (no 15s ramp-up tier), and does NOT lock equipment swapping in combat."
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
        print(f'\n{updated}/{len(FORTUNES_DETAIL)} Rare Fortunes updated with full detail.')

        total_filled = conn.execute(text(
            "SELECT COUNT(*) FROM sl_err_fortunes WHERE buffs IS NOT NULL"
        )).scalar()
        print(f'Total Fortunes with full detail so far: {total_filled}/28')


if __name__ == '__main__':
    run()
