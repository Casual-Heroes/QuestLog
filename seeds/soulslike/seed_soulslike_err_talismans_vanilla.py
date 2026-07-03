"""
Seed: ERR vanilla talisman rebalance (game='err' rows in sl_talismans).
Source: err.fandom.com/wiki/Talismans, "Vanilla Talisman Changes" table, updated to
patch 2.2.6.0, pasted directly by user.

ERR removes weight from ALL talismans and rebalances effects (simple stat tweaks to
entirely new mechanics). This seeds ERR-tagged rows for each vanilla talisman with
its new effect text. Talismans with no listed change in the source table keep their
vanilla effect text copied over (their numbers may differ slightly in-game but no
delta was published).

Run: chwebsiteprj/bin/python3 seed_soulslike_err_talismans_vanilla.py
"""
import time
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
NOW = int(time.time())

# (name, new ERR effect text) - only talismans explicitly listed in the source table.
# Some entries cover both base + upgrade tiers (+1/+2/+3) and Great-Jar's/Greatshield
# variants where applicable, captured as one combined effect description.
TALISMAN_REBALANCE = {
    "Aged One's Exultation": (
        "When Madness is triggered in the vicinity: 30%+60 Stamina restoration, "
        "2%+4 Stamina Regen every 2 seconds. Duration: 20 seconds."
    ),
    "Ailment Talisman": (
        "When a status effect is triggered in the vicinity, grants +200 Status Resistance and x0.9 Status "
        "Buildup received to the same effect. Duration: 360s for Poison/Scarlet Rot, 240s for "
        "Frostbite/Sleep, 120s for Blood Loss/Madness, 60s for Death Blight."
    ),
    "Ancestral Spirit's Horn": (
        "3%+30 FP restoration on kill. x1.06 FP restoration from attacking and spell casts."
    ),
    "Arrow's Reach Talisman": "+65 Projectile Range.",
    "Arrow's Soaring Sting Talisman": (
        "x1.1 Attack Power of arrows and bolts, +35 Projectile Range. Incompatible with Arrow's Sting Talisman."
    ),
    "Arrow's Sting Talisman": (
        "x1.12 Attack Power of arrows and bolts. Incompatible with Arrow's Soaring Sting Talisman."
    ),
    'Arsenal Charm': "Base: x1.1 Equip Load. +1: x1.125 Equip Load. Great-Jar's: x1.15 Equip Load.",
    "Assassin's Cerulean Dagger": (
        "On critical attack: 12%+120 FP restoration, then +10 FP every 2s for 50s "
        "(does not stack with Starlight Shard)."
    ),
    "Assassin's Crimson Dagger": (
        "On critical attack: 9%+90 HP restoration, x0.9 Physical Damage taken for 50s "
        "(does not stack with Boiled Prawn or Boiled Crab)."
    ),
    'Axe Talisman': "x1.2 Charge Speed of charged heavy attacks, x1.1 Attack Power of heavy attacks.",
    'Beloved Stardust': "x1.18 Action Speed of heavy attacks of catalysts.",
    'Blade of Mercy': "For 20s after a critical hit: +8 Arcane, x1.18 Damage.",
    'Blessed Blue Dew Talisman': "0.32%+3 FP Regen every 2 seconds.",
    'Blessed Dew Talisman': "0.28%+5 HP Regen every 2 seconds.",
    'Blue Dancer Charm': (
        "Increases Physical Attack Power with lower Equip Load. Breakpoints: <=10 EL=x1.12, 15=x1.107, "
        "20=x1.097, 25=x1.087, 30=x1.077, 35=x1.067, 40=x1.051, 45=x1.021, >=50=x1.0 (linear between points)."
    ),
    'Blue-Feathered Branchsword': "x0.5 (x0.75 PvP) damage taken when at <=25% Max HP.",
    'Boltdrake Talisman': (
        "Base: x0.825 (x0.866 PvP) Lightning Damage taken. +1: x0.8 (x0.84 PvP). "
        "+2: x0.775 (x0.814 PvP). Greatshield: x0.75 (x0.788 PvP)."
    ),
    "Bull-Goat's Talisman": "+15 Poise, x1.2 All Defense.",
    'Carian Filigreed Crest': "x0.9 FP Cost of skills, x0.9 Stamina Cost of skills.",
    'Cerulean Amber Medallion': (
        "Base: +3 Mind, x1.01 Max FP. +1: +2 Mind, x1.055 Max FP. +2: +1 Mind, x1.10 Max FP "
        "(moved to Moonfolk Ruins/Moonlight Altar). +3: +1 Mind, x1.12 Max FP."
    ),
    'Cerulean Seed Talisman': "Base: x1.2 FP restoration of Flask of Cerulean Tears. +1: x1.25 FP restoration.",
    'Clarifying Horn Charm': (
        "Base: +100 Concentration, -2 Sleep/Madness buildup every 2s. "
        "+1: +110 Concentration, -3 Sleep/Madness buildup every 2s. "
        "+2: +120 Concentration, -3 Sleep/Madness buildup every 2s."
    ),
    'Claw Talisman': "x1.16 Attack Power of jump attacks, +10 Poise while performing jump attacks.",
    'Companion Jar': "x1.15 Attack Power of pots, x1.1 Attack Power of hefty pots.",
    'Concealing Veil': (
        "Conceals presence from foes, especially while crouching: x0.9 Enemy Vision (x0.75 crouching). "
        "Reduces sound: x0.8 Enemy Hearing (x0.5 crouching)."
    ),
    "Crepus's Vial": (
        "Crouching while stationary obscures wearer in dark mist (like Darkness spell). "
        "x1.5 Attack Power while crouching for over 4s, x1.52 Attack Power of bolts. "
        "Persists 1.5s after moving or standing."
    ),
    'Crimson Amber Medallion': (
        "Base: +3 Vigor, x1.01 Max HP. +1: +2 Vigor, x1.05 Max HP. "
        "+2: +1 Vigor, x1.1 Max HP. +3: +1 Vigor, x1.11 Max HP."
    ),
    'Crimson Seed Talisman': "Base: x1.16 HP restoration of Flask of Crimson Tears. +1: x1.2 HP restoration.",
    'Crucible Feather Talisman': (
        "+2 I-Frames while dodging, x1.1 travelled distance while dodging, x1.25 damage taken."
    ),
    'Crucible Knot Talisman': "x0.875 Counter Damage taken.",
    'Crucible Scale Talisman': "x0.65 Critical Damage taken.",
    'Crusade Insignia': "For 20s after killing an enemy: +8 Endurance, x1.18 Damage.",
    'Curved Sword Talisman': (
        "x1.18 Attack Power of guard counters, x1.16 Attack Power of feint attacks, "
        "x0.91 damage taken while performing guard counters or feint attacks."
    ),
    "Daedicar's Woe": "x2 damage taken.",
    'Dagger Talisman': "x1.24 Attack Power of critical attacks, x0.1 Stamina Cost of critical attacks.",
    'Dragoncrest Shield Talisman': (
        "Base: x0.925 (x0.948 PvP) Physical Damage taken (moved to Sainted Hero's Grave/Altus). "
        "+1: x0.9 (x0.923 PvP) (moved to bottom of Bestial Sanctum/Dragonbarrow). "
        "+2: x0.875 (x0.897 PvP). Greatshield: x0.85 (x0.871 PvP)."
    ),
    "Dreaming Saint's Exultation": (
        "Renamed from St. Trina's Smile. When Sleep is triggered nearby: 2%+20 FP restoration for self and "
        "allies upon attacking drowsy foes (2s cooldown). Duration: 15 seconds."
    ),
    'Dried Bouquet': (
        "When a summoned spirit dies: x1.1 Damage, x0.9 damage taken. Duration: 300 seconds."
    ),
    'Enraged Divine Beast': "x1.12 Damage of storm attacks, x1.08 Poise Damage of storm attacks.",
    "Erdtree's Favor": (
        "Base: x1.03 Max HP, x1.06 Max Stamina, x1.03 Equip Load. "
        "+1: x1.04 Max HP, x1.08 Max Stamina, x1.04 Equip Load. "
        "+2: x1.05 Max HP, x1.1 Max Stamina, x1.05 Equip Load."
    ),
    "Faithful's Canvas Talisman": (
        "x1.04 Attack Power of incantations, +25 Cast Speed of incantations. "
        "Incompatible with Flock's Canvas Talisman."
    ),
    'Fine Crucible Feather Talisman': (
        "+2 I-Frames while ducking (no effect in Shura Mode), extended duration of ducking, "
        "x1.10 damage taken."
    ),
    'Fire Scorpion Charm': (
        "x1.15 Fire Damage. For 20s after a critical hit: x1.1 Fire Damage. x1.15 non-Fire damage taken."
    ),
    'Flamedrake Talisman': (
        "Base: x0.825 (x0.866 PvP) Fire Damage taken. +1: x0.8 (x0.84 PvP). "
        "+2: x0.775 (x0.814 PvP). Greatshield: x0.75 (x0.788 PvP)."
    ),
    "Flock's Canvas Talisman": (
        "x1.06 Attack Power of incantations, +50 Cast Speed of incantations. "
        "Incompatible with Faithful's Canvas Talisman."
    ),
    'Godfrey Icon': "x1.15 Attack Power of charged skills, x1.12 Attack Power of charged spells.",
    'Godskin Swaddling Cloth': "3%+30 HP restoration on successive attacks.",
    'Gold Scarab': "x1.1 Rune Gain on kill. Moved to Hidden Path to the Haligtree.",
    'Graven-Mass Talisman': (
        "x1.06 Attack Power of sorceries, +50 Cast Speed of sorceries. "
        "Incompatible with Graven-School Talisman."
    ),
    'Graven-School Talisman': (
        "x1.04 Attack Power of sorceries, +25 Cast Speed of sorceries. "
        "Incompatible with Graven-Mass Talisman."
    ),
    'Greatshield Talisman': (
        "x0.85 Stamina Cost of blocks, +30 Stamina Regen while blocking "
        "(reduces the Stamina Regen penalty of holding block)."
    ),
    'Green Turtle Talisman': "Green: +40 Stamina Regen. Two-Headed: +50 Stamina Regen.",
    'Haligdrake Talisman': (
        "Base: x0.825 (x0.866 PvP) Holy Damage taken. +1: x0.8 (x0.84 PvP). +2: x0.775 (x0.814 PvP). "
        "Golden Braid: x0.75 (x0.788 PvP), guarantees Black Knife is replaced by Mimic Tear Melina in the "
        "Nox Nightmaiden boss fight."
    ),
    'Hammer Talisman': (
        "x1.1 Poise Damage, x1.2 Stamina Damage. If already joined Volcano Manor, found on the corpse "
        "holding Eye Surcoat armor in the Rykard, Lord of Blasphemy arena."
    ),
    'Immunizing Horn Charm': (
        "Base: +100 Immunity, -2 Poison/Scarlet Rot buildup every 2s. "
        "+1: +110 Immunity, -3 Poison/Scarlet Rot buildup every 2s. "
        "+2: +120 Immunity, -3 Poison/Scarlet Rot buildup every 2s."
    ),
    "Kindred of Rot's Exultation": (
        "0.25%+15 HP Regen every 2s when Scarlet Rot occurs nearby. Duration: 40 seconds."
    ),
    'Lacerating Crossed-Tree': (
        "x1.15 Damage of dash light attacks, x1.16 Damage of dash heavy attacks, "
        "x1.08 Action Speed of dash attacks."
    ),
    'Lance Talisman': (
        "x1.16 Attack Power of melee attacks on horseback, x1.08 Attack Power of spells/projectiles on "
        "horseback, x1.2 attack movement distance."
    ),
    'Lightning Scorpion Charm': (
        "x1.15 Lightning Damage. For 20s after a critical hit: x1.1 Lightning Damage. "
        "x1.15 non-Lightning damage taken."
    ),
    'Longtail Cat Talisman': (
        "Nullifies fall damage (does not prevent death from a high fall), prevents landings from impeding "
        "movement, retains combo chain after a roll/duck (loses unique roll/duck attacks in exchange)."
    ),
    "Lord of Blood's Exultation": "x1.15 Damage when Blood Loss occurs nearby. Duration: 30 seconds.",
    'Magic Scorpion Charm': (
        "x1.15 Magic Damage. For 20s after a critical hit: x1.1 Magic Damage. x1.15 non-Magic damage taken."
    ),
    "Marika's Scarseal": (
        "+2 Mind/Intelligence/Faith/Arcane, x1.03 (x1.045 PvP) damage taken."
    ),
    "Marika's Soreseal": (
        "+4 Mind/Intelligence/Faith/Arcane, x1.06 (x1.09 PvP) damage taken."
    ),
    "Millicent's Prosthesis": (
        "+3 Dexterity. Successive attacks build a 4-tier damage buff that decays over time: "
        "x1.03/x1.06/x1.09/x1.12. Incompatible with Winged Sword Insignia and Rotten Winged Sword Insignia."
    ),
    'Moon of Nokstella': "+14 Memory Slot (effectively max slots), x1.12 Attack Power of Night attacks.",
    'Mottled Necklace': (
        "Base: x0.9 Status Buildup received. +1: x0.875. +2: x0.85."
    ),
    "Old Lord's Talisman": (
        "x1.3 Common Buff Duration - applies to spells and most buffs (consumables, Ashes of War) but not "
        "Fortunes effects or Crystal Tears."
    ),
    'Outer God Heirloom': "+6 Arcane.",
    'Pearldrake Talisman': (
        "Base: x0.9 (x0.923 PvP) Elemental Damage taken. +1: x0.875 (x0.897 PvP). "
        "+2: x0.85 (x0.871 PvP). Greatshield: x0.825 (x0.846 PvP)."
    ),
    'Pearl Shield Talisman': "x0.75 Elemental Damage taken while blocking, x0.75 Status Buildup received while blocking.",
    "Perfumer's Talisman": "x1.15 Attack Power of perfume items, x1.1 Attack Power of Perfume Bottle weapons.",
    'Primal Glintstone Blade': "x0.85 FP Cost of spells, x0.85 Stamina Cost of spells, x0.75 Max HP.",
    "Prince of Death's Pustule": "+100 Vitality, -2 Death Blight buildup every 2s.",
    "Prince of Death's Cyst": "+110 Vitality, -3 Death Blight buildup every 2s.",
    "Prosthesis-Wearer Heirloom": "+6 Dexterity.",
    'Radagon Icon': "+100 Cast Speed.",
    "Radagon's Scarseal": "+2 Vigor/Endurance/Strength/Dexterity, x1.05 (x1.075 PvP) damage taken.",
    "Radagon's Soreseal": "+4 Vigor/Endurance/Strength/Dexterity, x1.1 (x1.15 PvP) damage taken.",
    'Red-Feathered Branchsword': "x1.2 Damage when at <=25% Max HP.",
    "Rellana's Cameo": (
        "After maintaining the same stance for 1s: x1.36 Damage of skills, x1.18 FP Cost discount of skills. "
        "Using Moon-and-Fire Stance (Rellana's Twin Blades) grants: left sword x1.1 Fire Attack + 20 Fire "
        "Damage, right sword x1.1 Magic Attack + 20 Magic Damage. Duration: 30 seconds."
    ),
    'Retaliatory Crossed-Tree': (
        "x1.16 Damage of rolling attacks, x1.17 Damage of ducking attacks, x1.05 Action Speed of "
        "rolling/ducking attacks."
    ),
    'Ritual Shield Talisman': "x0.7 damage taken when at >=95% Max HP.",
    'Ritual Sword Talisman': "x1.1 Damage when at >=95% Max HP.",
    'Roar Medallion': (
        "x1.15 Attack Power of roar attacks, x1.12 Damage of breath attacks. Roaring grants x1.05 Max "
        "Stamina for 20s (stacks with itself)."
    ),
    'Rotten Winged Sword Insignia': (
        "Successive attacks build a 4-tier damage buff that decays over time: x1.035/x1.065/x1.1/x1.135. "
        "Incompatible with Winged Sword Insignia and Millicent's Prosthesis."
    ),
    'Sacred Scorpion Charm': (
        "x1.15 Holy Damage. For 20s after a critical hit: x1.1 Holy Damage. x1.15 non-Holy damage taken."
    ),
    'Sacrificial Twig': (
        "Prevents rune loss on death (consumed in exchange). Dying from Death Blight while equipped leaves "
        "runes on the ground without consuming the talisman."
    ),
    "Shabriri's Woe": "+0.2 Target Priority.",
    'Shard of Alexander': "x1.16 Attack Power of skills.",
    'Sharpshot Talisman': "x1.16 Attack Power of precision-aimed shots, x1.8 Running Speed while aiming.",
    'Shattered Stone Talisman': "x1.15 Damage of kicking and stomping attacks.",
    'Silver Scarab': "+40 Item Discovery. Moved to Abandoned Cave, Dragonbarrow.",
    'Smithing Talisman': (
        "x1.12 Damage of weapon-throwing attacks. Upon being thrown and caught, increases weapon's Physical "
        "Attack Power by 1.02x +20 (not applied on the throw itself)."
    ),
    'Spear Talisman': (
        "x1.12 Physical Counter Damage, x1.24 Physical Counter Damage during guarding attacks "
        "(buffs do not stack together)."
    ),
    'Spelldrake Talisman': (
        "Base: x0.825 (x0.866 PvP) Magic Damage taken. +1: x0.8 (x0.84 PvP). "
        "+2: x0.775 (x0.814 PvP). Greatshield: x0.75 (x0.788 PvP)."
    ),
    'Stalwart Horn Charm': (
        "Base: +100 Robustness, -2 Blood Loss/Frostbite buildup every 2s. "
        "+1: +110 Robustness, -3 buildup every 2s. +2: +120 Robustness, -3 buildup every 2s."
    ),
    'Stargazer Heirloom': "+6 Intelligence.",
    'Starscourge Heirloom': "+6 Strength.",
    "Taker's Cameo": "2.5%+25 HP restoration on kill, x1.08 HP restoration from non-flask sources.",
    'Talisman of All Crucibles': (
        "x0.65 Critical Damage taken, x0.88 Counter Damage taken, +2 I-Frames while dodging and ducking, "
        "x1.1 travelled distance while dodging (stacks with Windy Cracked Tear for x1.25 total), "
        "x1.375 damage taken."
    ),
    "Talisman of Lord's Bestowal": (
        "+30 Poise for 10s after using a Flask of Tears, x1.06 action speed of using a Flask of Tears."
    ),
    'Talisman of the Dread': (
        "x1.08 Damage of Dragon Communion incantations, grants single-hit stagger immunity when casting "
        "Dragon Communion spells. (Vanilla effect now belongs to Blasphemous Crest.)"
    ),
    'Twinblade Talisman': (
        "Increases damage of each hit in a light attack combo: x1.04/x1.08/x1.12/x1.16/x1.2/x1.16."
    ),
    "Two Fingers Heirloom": "+6 Faith.",
    'Two-Handed Sword Talisman': (
        "Renamed to 'Curved Greatsword Talisman'. x1.4 (x1.5 two-handing) Damage of the final hit of a light "
        "attack chain (vanilla Twinblade Talisman's original effect)."
    ),
    'Verdigris Discus': (
        "x0.91 (x0.94 PvP) damage taken at Solid Frame, x0.82 (x0.88 PvP) damage taken at Massive Frame."
    ),
    'Viridian Amber Medallion': (
        "Base: +3 Endurance, x1.01 Max Stamina. +1: +2 Endurance, x1.09 Max Stamina. "
        "+2: +1 Endurance, x1.18 Max Stamina. +3: +1 Endurance, x1.2 Max Stamina."
    ),
    'Warrior Jar Shard': (
        "x1.12 Attack Power of skills. Can now be obtained peacefully by defeating Starscourge Radahn with "
        "Iron Fist Alexander's help, then speaking to him after."
    ),
    'Winged Sword Insignia': (
        "Successive attacks build a 4-tier damage buff that decays over time: x1.025/x1.05/x1.075/x1.1. "
        "Incompatible with Rotten Winged Sword Insignia and Millicent's Prosthesis."
    ),
}


def run():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_talismans WHERE game='err'"))

        # Pull all vanilla talisman names to copy over (those not explicitly rebalanced
        # keep vanilla flavor text, since no ERR delta was published for them).
        vanilla = conn.execute(text(
            "SELECT name, description, effect, image_url FROM sl_talismans WHERE game='elden_ring'"
        )).fetchall()

        inserted = 0
        rebalanced = 0
        for name, desc, vanilla_effect, image_url in vanilla:
            new_effect = TALISMAN_REBALANCE.get(name)
            if new_effect:
                rebalanced += 1
            else:
                new_effect = vanilla_effect  # no published delta - carry over vanilla text

            conn.execute(text("""
                INSERT INTO sl_talismans
                    (game, name, description, effect, weight, image_url, created_at)
                VALUES
                    ('err', :name, :desc, :effect, 0, :image, :ts)
            """), {
                'name': name, 'desc': desc, 'effect': new_effect,
                'image': image_url, 'ts': NOW,
            })
            inserted += 1

        conn.commit()
        print(f'Inserted {inserted} ERR talismans ({rebalanced} with explicit rebalanced text, '
              f'{inserted - rebalanced} carried over from vanilla - no published delta).')
        print('All ERR talismans seeded with weight=0 (ERR removes talisman weight entirely).')


if __name__ == '__main__':
    run()
