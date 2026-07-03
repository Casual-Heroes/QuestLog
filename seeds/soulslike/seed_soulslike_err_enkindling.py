"""
Seed: ERR Ash of War Enkindling system - mechanics overview + full affix table.
Source: err.fandom.com/wiki/Ash_of_War_Enkindling, pasted directly by user.
Affix effects table updated to game patch 2.2.1.1.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_enkindling.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SYSTEM_SECTIONS = {
    'basic_mechanics': (
        "Ash of War Enkindling replaces the Ash of War duplication menu at Smithing Master Hewg, using the "
        "Lost Ashes currency. When an Ash of War is enkindled, you're granted an extra copy with a random "
        "rarity: Common (1 star), Rare (2 stars), or Legendary (3 stars), plus a random Affix granting "
        "powerful benefits. 3-star (Legendary) Enkindled Ashes can be equipped on Somber weapons of the "
        "appropriate class, enabling more varied builds. 'No Skill' can always go on Somber weapons even "
        "without Enkindling. Weapon Catalysts count as weapons for Enkindled Ash compatibility. Unwanted "
        "Enkindled Ashes can be sold for runes (1000/4000/16000 for Common/Rare/Legendary). Each purchase "
        "also produces a Residual Ashes item - 100 Residual Ashes can be traded for a guaranteed 3-star "
        "Enkindled Ash of War."
    ),
    'lost_ashes_availability': (
        "Lost Ashes replace many generic crafting ingredients / corpse loot pickups in the world, upgraded "
        "to Legendary rarity drop visibility to stand out. Guaranteed chest reward for each cleared Camp. "
        "Purchasable in bulk from Smithing Master Iji (20), Blacksmith Sfyrix (30), Forsaken Merchant (50), "
        "and a few other world merchants. New Game Plus unlocks an infinite shop at every Site of Grace "
        "(500,000 runes each). Very small (item-discovery-unaffected) chance to drop from powerful enemies. "
        "Reward for defeating at least 2 bosses in the Trial of Recollection (scales with difficulty/boss "
        "count) - unlocked after defeating Elden Beast or in NG+, infinitely repeatable, one of the best "
        "end-game sources."
    ),
    'affixes_overview': (
        "Affixes grant effects ranging from passive stat boosts to trigger-based buffs to active "
        "event-triggered effects. Every Ash of War has a different available Affix pool - from generic ones "
        "like Mundane (available to all Ashes) to character-specific ones themed after NPCs who use a "
        "similar skill or attack. Some Enkindled Ashes grant affinities not normally available on that "
        "weapon. Passive buffs (stat increases) are active as long as the weapon is equipped and show in "
        "the icon bar. Active buffs (weapon hit effects) only work on the weapon with the Ash equipped and "
        "only appear in the icon bar when conditions are met (some have no visible icon). Common/Rare/"
        "Legendary Enkindled Ashes grant 1/2/3 bonus effects from their Affix respectively. Identical "
        "passive effects do not stack (e.g. two Mundane Ashes' stat boosts don't add together)."
    ),
}

# (affix_name, affinity, 1-star effect, 2-star effect, 3-star effect)
AFFIXES = [
    ('Enduring', 'Standard', 'x1.03 Equip Load', 'x0.95 Stamina Cost of blocks',
     '+60 Stamina Regen when at <=50% Max HP'),
    ('Hearty', 'Standard', 'x1.04 Max HP', 'Weapon hits deal bonus Strike Damage',
     '0.25%+10 HP Regen every 2 seconds when in combat and at >=90% Max HP'),
    ('Lively', 'Standard', 'x1.06 Max Stamina', 'Weapon hits deal bonus Slash Damage',
     'Taking damage restores 6%+60 Stamina (5 second cooldown)'),
    ('Mundane', 'Standard', '+1 Vigor', '+2 Mind', '+3 Endurance'),
    ('Soaring', 'Standard', '+30 Projectile Range',
     'Projectile hits grant x1.12 dodge distance for 6 seconds',
     'x1.08 Attack Power of projectile skills'),
    ('Striking', 'Standard', 'x1.045 Counter Damage',
     'Taking damage grants x1.1 Action Speed for 1 second',
     'Weapon hits grant x0.84 Stamina Cost of dodging for 2 seconds'),
    ('Turtled', 'Standard', '+20 Stamina Regen',
     'Replaces the Movement Speed penalty while blocking with a 2.5% increase',
     'Pickled Turtle Necks grant x1.06 Attack Power (includes Assassin\'s Viridian Dagger\'s additional effect)'),
    ('Rampaging', 'Heavy', 'x1.08 Running Speed while sprinting', '+2 Strength',
     'x1.12 Poise Damage of dash attacks'),
    ('Resolute', 'Heavy', '+6 Poise', 'x0.88 damage taken while using skills',
     'x0.82 damage taken from critical hits'),
    ('Sovereign', 'Heavy', '+4 Poise, x1.025 Equip Load',
     'Successful skill hits grant x1.1 Action Speed during recovery',
     'x1.05 Attack Power of Redmane skills'),
    ('Acrobatic', 'Keen', 'x1.08 travelled distance while dodging', '+2 Dexterity',
     'x1.06 Action Speed of roll or duck attacks'),
    ('Clever', 'Keen', 'x1.05 Max FP', 'Weapon hits deal bonus Pierce Damage',
     'Skill hits grant 0.3%+3 FP Regen every 2s for 10s (1.5%+15 total)'),
    ('Gifted', 'Quality', 'x0.94 Stamina Cost of attacks', '+1 Dexterity, +1 Strength',
     'x0.96 Stamina Cost / x1.02 Attack Power of perfect attacks, x0.98 FP Cost of perfect spells'),
    ('Turbulent', 'Quality', 'x1.035 Poise Damage',
     'Weapon hits grant bonus Poise for 4 seconds',
     'Stance breaks nearby grant x1.13 Attack Power of storm attacks for 8 seconds'),
    ('Astral', 'Magic', 'x1.035 Magic Damage',
     'Weapon hits grant x0.94 FP Cost of spells / x0.92 FP Cost of skills+items for 8s',
     'Skill hits cause target to take x1.065 Magic Damage for 6 seconds'),
    ('Enchanted', 'Magic', 'x1.035 Attack Power of spells',
     'x0.88 FP Cost of skills for 10s after casting a spell',
     'Skill use grants 0.1%+1 FP Regen every 2s for 12s (0.7%+7 total)'),
    ('Godslayer', 'Fell', 'x1.05 Attack Power against Divine enemies',
     'x0.92 Fire Damage taken / x0.92 Holy Damage taken',
     'x1.1 Attack Power of skills in the presence of black flame'),
    ('Ruinous', 'Fell', 'x1.035 Fire Damage', 'Weapon hits grant -2 Status Buildup',
     'Skill hits grant flame enhancement for 8s: x1.05 Physical Damage, x1.05 Fire Damage, +20 Stamina Regen'),
    ('Scaled', 'Bolt', 'x1.05 Attack Power against Dragon enemies',
     'Weapon hits grant x0.91 damage taken for 6 seconds',
     'Skill use grants x1.08 Lightning Damage for 6 seconds'),
    ('Smiting', 'Sacred', 'x1.05 Attack Power against Undead enemies',
     'Weapon hits deal bonus Holy Damage',
     'Skill use grants x1.065 Attack Power of spells for 10 seconds'),
    ('Sneaking', 'Night', 'x1.08 Attack Power of critical attacks',
     'While crouching: x0.9 Enemy Vision+Hearing, +90 Stamina Regen',
     'x1.12 Poise Damage for 12s after a critical attack'),
    ('Smoldering', 'Fire', 'x1.02 Max HP, x1.03 Max FP, x1.04 Max Stamina',
     'Weapon hits grant +4 Strength for 6 seconds',
     'Skills deal bonus Fire Damage to burning targets'),
    ('Augmenting', 'Lightning', 'x1.1 Common Buff Duration',
     'x1.12 FP restoration of Flask of Cerulean Tears',
     'Weapon hits extend buff duration'),
    ('Voltaic', 'Lightning', 'x1.035 Lightning Damage',
     'Weapon hits grant x1.25 Movement Speed for 2.5 seconds',
     'Skill hits bolster self with lightning for 6s: x1.05 Lightning Damage, +50 Status Resistance, '
     'stagger resistance to weak hits'),
    ('Golden', 'Blessed', '+2 Faith',
     'Skill use grants x1.06 HP Recovery from all sources / x1.1 Rune Gain for 12 seconds',
     'Taking damage grants x1.1 Elemental Damage for 18 seconds'),
    ('Venomous', 'Poison', '+2 Arcane',
     '-2 Poison buildup every 2s, increases status application',
     'Skills deal +20 Poison buildup'),
    ('Sanguine', 'Blood', '+1 Faith, +1 Arcane',
     'Weapon hits deal bonus Fire Damage',
     'Status Bleed (Blood Loss) from skills deals x1.15 damage'),
    ('Serrated', 'Blood', 'x1.035 Slash Attack Power',
     'Blood Loss nearby grants 7%+70 Stamina restoration',
     'Weapon hits grant x1.2 Action Speed for 0.1 seconds'),
    ('Resourceful', 'Occult', 'x1.04 Attack Power of items and tools',
     'x1.1 HP restoration of Flask of Crimson Tears',
     'Item/tool attacks grant x0.88 FP Cost of skills for 16 seconds'),
    ('Silver', 'Occult', '+1 Intelligence, +1 Arcane',
     'Skill use grants increased FP Recovery from all sources and +50 Item Discovery for 12 seconds',
     'Taking damage grants x1.1 Physical Attack Power for 18 seconds'),
    ('Barbaric', 'Bestial', 'x0.95 Counter Damage taken',
     'Taking damage grants x1.08 Poise Damage for 8 seconds',
     'Skills deal bonus Slash Damage to stance-broken targets'),
    ('Magnetic', 'Gravitational', 'x1.1 attack movement distance',
     'Weapon hits deal bonus Lightning Damage',
     'Skill hits cause target to take x1.065 Lightning Damage for 6 seconds'),
    ('Suspended', 'Gravitational', 'x0.92 Stamina Cost of dodging',
     'x0.65 Status Buildup received while airborne or using a skill',
     'x1.06 Action Speed of jump attacks'),
    ('Decaying', 'Rotten', '16%+16 Immunity',
     'Weapon hits deal 10 Scarlet Rot buildup to poisoned targets',
     'Skills deal bonus True Damage to rotted targets'),
    ('Eclipsed', 'Cursed', '+1 Faith, +1 Intelligence',
     'Weapon hits deal 0.5 Poise Damage to blighted targets',
     'Skills deal +20 Death Blight buildup'),
    ('Freezing', 'Cold', '-2 Frostbite buildup every 2s, raises magic damage negation',
     'Weapon hits make frostbitten targets take an additional x1.03 damage',
     'Skills deal 3.5 Poise Damage to frostbitten targets'),
    ('Twinbird', 'Cold', '16%+16 Blood Loss+Death Blight Resistance, 8%+8 Frostbite Resistance',
     'x0.80 FP Cost of skills/items/spells when at <=25% Max HP',
     'Skills deal bonus Magic Damage to full-health targets'),
    ('Gentle', 'Soporific', '16%+16 Concentration',
     'Weapon hits deal bonus Magic Damage to drowsy targets',
     'Sleep nearby grants 4%+40 FP restoration'),
    ('Chaotic', 'Frenzied', 'x1.04 Fire Damage of spells and skills',
     '+1 Strength, +1 Dexterity, +1 Faith, +1 Intelligence',
     'Madness nearby grants x1.1 Action Speed of skills for 12 seconds'),
]


def run():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_err_enkindling_system"))
        for section, content in SYSTEM_SECTIONS.items():
            conn.execute(text(
                "INSERT INTO sl_err_enkindling_system (section, content) VALUES (:s, :c)"
            ), {'s': section, 'c': content})
        print(f'{len(SYSTEM_SECTIONS)} system overview sections seeded.')

        conn.execute(text("DELETE FROM sl_err_enkindling_affixes"))
        for name, affinity, e1, e2, e3 in AFFIXES:
            conn.execute(text("""
                INSERT INTO sl_err_enkindling_affixes (name, affinity, effect_1_star, effect_2_star, effect_3_star)
                VALUES (:name, :aff, :e1, :e2, :e3)
            """), {'name': name, 'aff': affinity, 'e1': e1, 'e2': e2, 'e3': e3})
            print(f'  + {name} ({affinity})')
        conn.commit()

        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_enkindling_affixes")).scalar()
        print(f'\n{total} affixes seeded across all affinities.')


if __name__ == '__main__':
    run()
