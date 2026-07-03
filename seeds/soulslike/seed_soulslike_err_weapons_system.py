"""
Seed: ERR general weapon system changes (reference text) + per-weapon Weight Rate values.
Source: err.fandom.com/wiki/Weapons, pasted directly by user.

Per-weapon AR/scaling/requirement data was already sourced separately from the
ThomasJClark/elden-ring-weapon-calculator regulation-reforged JSON dump (529 weapons,
seeded via seed_soulslike_err_weapons.py) - NOT scraped from this wiki page. This script
only adds the supplementary weaponWeightRate attribute (affects attack speed slightly,
independent of AR) since that's not present in the regulation dump, plus the general
system-level changes overview as reference text.

Note: "Immortal Coil" mentioned in the New Armaments list is not present in the
regulation-reforged-v2.2.3.4.js dump this DB was seeded from (likely added in a later
patch) - flagged as a known gap, not fixed here since exact AR data isn't available.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapons_system.py
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

GENERAL_CHANGES = {
    'overview': (
        "Reforged adds over 50 new armaments to the Lands Between while also greatly rebalancing and "
        "expanding existing weapon mechanics, scalings, and more. For a thorough overview of all "
        "vanilla and new armaments' statistics, scalings, and requirements, the community maintains the "
        "ELDEN RING Weapon Calculator (select 'ELDEN RING Reforged' as the game version)."
    ),
    'scaling': (
        "Armament attribute scaling (E to S+) no longer changes with reinforcement level - it always "
        "uses the maximum scaling regardless of reinforcement, so a weapon with A Strength scaling at "
        "+25 (or +10 somber) also has A scaling at +0. Makes it easier to evaluate a weapon for a build "
        "without guesswork. Catalysts (including weapon catalysts) still increase scaling with weapon "
        "level, since that's the only way to make them upgrade.\n\n"
        "Base damage of armaments reduced, but stat scaling greatly increased - most of an armament's "
        "damage now comes from your stats rather than smithing stones, though both remain important. "
        "For heavy bar-stat (Vigor/Mind/Endurance) investment with less in damage stats, status effects "
        "are recommended since they deal % health damage and can offset lower up-front damage. "
        "Crossbows are largely stat-agnostic. Spirit Ashes are also a strong damage asset if you have "
        "the FP to consistently Enrage them and the Mind to extend Enrage duration."
    ),
    'two_handing': (
        "The 50% Strength damage boost from two-handing was removed, replaced with a global 8% Damage "
        "increase when two-handing - lets all melee armaments benefit from two-handing. The 50% "
        "Strength boost for the purpose of MEETING minimum stat requirements still exists."
    ),
    'catalyst_attacks': (
        "Catalysts reworked to have unique projectile-based heavy attacks. All on-hit effects (affinity "
        "passives, Status Buildup) on catalysts apply via this heavy attack, not through spells. Many "
        "catalyst attacks are condensed versions of actual spells from the category the catalyst "
        "boosts, or come innately as a Mystic Ash skill, sharing properties with those spells (e.g. "
        "Albinauric Staff heavy attack receives True Damage like Night Maiden's Mist)."
    ),
    'fp_generation': (
        "Hitting enemies with any attack type restores a small amount of FP, based on Max FP, "
        "Intelligence, and whether it was a light, heavy, or critical attack. Slower-attacking armaments "
        "generally restore more FP. (See Character Changes - Mind and FP for full system.)"
    ),
    'affinities': (
        "Weapon Affinities/Infusions overhauled entirely - several new Affinities added, all existing "
        "ones rebalanced (see Affinities page for the full table). Affinities now grant passive effects "
        "alongside scaling changes (e.g. slow HP Regen from Blessed, reduced Weight from "
        "Gravitational). Affinities no longer completely override weapon scaling - they modify it, "
        "enabling unique scaling combinations depending on which weapon an infusion is applied to."
    ),
    'status_buildup': (
        "Completely rebalanced Status Buildup dealt by weapons. Arcane scaling now applies to ALL "
        "status effects regardless of a weapon's Arcane damage scaling, up to 1.5x at 99 Arcane. "
        "Weapons deal less Status Buildup per hit while Powerstancing/paired, but hitting with both "
        "weapons deals slightly more overall. Attacks that hit multiple times in very quick succession "
        "(e.g. Warhawk Talon / Serpentbone Blade special Heavy Attack) deal greatly reduced Status "
        "Buildup on the initial fast hit, but all connecting hits deal the weapon's full buildup."
    ),
    'ui': (
        "New UI elements added to show several previously-hidden weapon stats and improve the stat "
        "card's visual presentation."
    ),
    'damage_types': (
        "Changed the damage type of player gear to better reflect what it should logically deal - e.g. "
        "the Forked Hatchet now deals Pierce damage, and the Torchpole's physical damage is now Strike."
    ),
    'attack_trails': (
        "Introduced unique attack trails for most weapons - a weapon's affinity, status buildup "
        "properties, or thematic connection to a subject/material is now represented by a distinct "
        "swing trail. Several completely new trails were added to support this."
    ),
    'upgrading': (
        "Weapon upgrading reworked extensively - weapons are easier to upgrade, smithing stones are "
        "easier to obtain, and weapons scale more consistently across upgrade levels. (See Armament "
        "Upgrading article for full details.)"
    ),
    'buffing': (
        "All melee weapons can now be buffed via grease items, skills, or spells, even if somber, "
        "already affinity-infused, or innately elemental. Only a single buff can be active at a time, "
        "except buffs from Roar skills (e.g. War Cry) and the special boost from Perfect Deflecting, "
        "which do not override other weapon buffs.\n\n"
        "Buffing with an Elemental or Status Grease/Buff Skill/Spell increases that armament's blocking "
        "for that Element or Status by 20% (e.g. Poison Grease increases Poison blocked by 20%, Sacred "
        "Blade increases Holy Guarded Negation by 20%, Electrify Armament increases Lightning Guarded "
        "Negation by 20%).\n\n"
        "Since weapon buffs add flat Damage or Status Buildup, Grease/Buff effects scale with weapon "
        "class - slower weapons get a higher buff multiplier than faster ones, and very long weapons "
        "get a slight penalty. Multipliers by class: Daggers/Throwing Blades x0.8; Backhand Blades/"
        "Claws/Curved Swords/Thrusting Swords x0.85; Fists/Hand-to-Hand/Katanas/Spears/Straight Swords "
        "x0.9; Axes/Hammers/Light Greatswords/Twinblades x0.95; Beast Claws/Flails/Halberds/Heavy "
        "Thrusting Swords/Perfume Bottles/Reapers/Whips x1.0; Curved Greatswords/Great Katanas/"
        "Greatswords x1.05; Greataxes/Great Hammers/Great Spears x1.1; Colossal Swords x1.15; Colossal "
        "Weapons x1.2. Note: Throwing Blades' multiplier only applies to critical attacks or Skills with "
        "the weapon, since throwing it removes any active buff."
    ),
    'powerstancing': (
        "Powerstancing and general multi-weapon usage given vast moveset flexibility improvements (see "
        "Combat Mechanics - Multi-weapon combat). New Powerstancing-compatible class pairs: Axes with "
        "Hammers and Flails; Greataxes with Greathammers; Colossal Weapons with Colossal Swords; Curved "
        "Greatswords with Greatswords."
    ),
    'critical_attacks': (
        "Globally increased Critical Attack animation speed by 20% (wastes less time, minimal gameplay "
        "difference). Critical Attacks convert all Physical Attack Power of a weapon's damage into True "
        "Damage (crits still benefit from weapon buffs/damage increases). Critical Attacks against the "
        "player (enemy grabs, player backstabs) similarly convert all Physical damage into True Damage, "
        "piercing all armor. Critical Attacks after a parry-induced stance break deal increased damage "
        "if the enemy requires more than one parry (stacks per additional parry).\n\n"
        "Replaced Critical Attacks' special invulnerability frames with standard 'dodge' i-frames - a "
        "technical change meaning most effects (talisman accumulation, status-related on-proc tools) "
        "can still trigger during crits rather than being blocked out; does not affect invulnerability "
        "to attacks.\n\n"
        "Critical Attacks provide a large amount of attack-based FP restoration and 'Accumulation' "
        "buildup (effects like Godskin Swaddling Cloth, Storied Glintstone Amulet, the Assassin fortune "
        "stacking Poise Damage effect, etc. that build with repeated hits).\n\n"
        "Added the ability to perform Critical Attacks with the left-handed armament via Guard + Light "
        "Attack while positioned for a crit. Added Critical Attacks for additional weapon categories "
        "using Nightreign animations, with default critical modifiers: Whips 100, Light Bows 150, Bows "
        "120, Greatbows 90, Small Shields 110, Medium Shields 100, Greatshields 90."
    ),
    'shields': (
        "Status effect resistance while blocking is no longer a hidden value - it's now half of the "
        "associated damage type's Guarded Negation: Physical -> Bleed/Poison/Scarlet Rot; Magic -> "
        "Frostbite; Fire -> Madness; Lightning -> Sleep; Holy -> Death Blight. A 50% resistance shield "
        "blocks 25% of that status buildup. Affinities boost elemental AND status resistance by 25% "
        "together (e.g. Poison-infused shield gains 25% more Poison resistance without 25% more "
        "Physical Guarded Negation; Magic-infused shield gains 25% Magic Guarded Negation). Greatly "
        "increased shield damage scaling across the board, and greatly increased shield attack hitbox "
        "size for improved consistency."
    ),
    'ranged_weapons': (
        "Bows, Crossbows, and other ranged weapons extensively reworked across all facets. Each ranged "
        "weapon class given greater mechanical variety and Projectile Range for a more significant "
        "niche. All bows/crossbows now have minor Intelligence and Faith scaling, applying exclusively "
        "to Elemental Damage by default. New ammunition types added for wider elemental/status coverage; "
        "existing ammo types made generally stronger in exchange for reduced capacity. (See Ranged "
        "Weapons article for full details.)"
    ),
    'weapon_catalysts': (
        "Weapon Catalysts are weapons that can cast spells while in the right hand or two-handed via "
        "Guard + Light Attack, at the cost of very slightly reduced attack and spell power compared to "
        "dedicated weapons/catalysts. (See Weapon Catalyst article for full details.)"
    ),
    'vanilla_weapon_changes': (
        "Many vanilla weapons received significant alterations - moveset, scaling, and status buildup "
        "changes. (See Vanilla Weapons Changes article for the full per-weapon breakdown.)"
    ),
}

NEW_ARMAMENTS = [
    "Ambassador's Cudgel", "Ambassador's Greatsword", "Ambassador's Towershield", 'Avionette Pig Sticker',
    'Avionette Scimitars', 'Broken Straight Sword', 'Coilheart', 'Crude Iron Claws', 'Crystal Ringblade',
    'Dawnglow Greatbolt', "Disciple's Rotten Branch", 'Fellthorn Clutches', 'Fellthorn Stake',
    'Flamelost Greatblades', 'Flamelost War Spear', 'Flamelost War Sword', 'Fury of Azash',
    'Goldvine Branchstaff', 'Gladius of Ophidion', 'Gracebound Cane Sword', 'Gracebound Claws',
    'Gracebound Dagger', 'Gracebound Greataxe', 'Gracebound Greatshield', 'Gracebound Greatsword',
    'Gracebound Halberd', 'Gracebound Katana', 'Gracebound Longbow', 'Gracebound Mace',
    'Gracebound Round Shield', 'Gracebound Staff', 'Grave Spear', 'Immortal Coil', 'Iron Spike',
    "Lordsworn's Spear", 'Mad Sun Shield', "Makar's Ceremonial Cleaver", 'Marionette Short Sword',
    "Mohgwyn's Sacred Seal", "Night's Edge", 'Nox Flowing Fist', 'Pumpkin Sledge',
    'Putrescent Bonesmasher', "Red Wolf's Fang", 'Rotten Crystal Ringblade', 'Scepter of Serenity',
    'Snow Witch Scepter', 'Starcaller Spire', 'Suncatcher', 'Sun Realm Sword', 'Twinbird Caduceus',
    'Vulgar Militia Chain Sickle',
]

# (weapon_class, [(name, rate), ...])
WEIGHT_RATES = {
    'Axes': [('Forked-Tongue Hatchet', 1), ('Hand Axe', 0), ('Ripple Blade', 0),
              ('Vulgar Militia Chain Sickle', 0), ('Warped Axe', 1)],
    'Backhand Blades': [('Backhand Blade', 0), ("Curseblade's Cirque", 1)],
    'Beast Claws': [("Red Bear's Claw", 1)],
    'Claws': [('Crude Iron Claws', 1), ('Raptor Talons', 0)],
    'Colossal Swords': [('Flamelost Greatblades', 0), ("Godslayer's Greatsword", 1),
                         ('Grafted Blade Greatsword', 1), ('Greatsword', 1),
                         ("Maliketh's Black Blade", 1), ('Zweihander', 0)],
    'Colossal Weapons': [('Axe of Godfrey', 1), ('Duelist Greataxe', 0), ("Envoy's Greathorn", 1),
                          ('Fellthorn Stake', 0), ("Ghiza's Wheel", 0), ('Giant-Crusher', 1),
                          ('Great Club', 0), ('Rotten Duelist Greataxe', 0),
                          ('Shadow Sunflower Blossom', 0)],
    'Curved Greatswords': [("Beastman's Cleaver", 1), ("Freyja's Greatsword", 1),
                            ("Magma Wyrm's Scalesword", 1), ("Makar's Ceremonial Cleaver", 1),
                            ("Morgott's Cursed Sword", 0), ("Monk's Flameblade", 0),
                            ('Zamor Curved Sword', 0)],
    'Curved Swords': [("Bandit's Curved Sword", 1), ("Beastman's Curved Sword", 1), ('Eclipse Shotel', 0),
                       ("Horned Warrior's Sword", 1), ("Red Wolf's Fang", 0),
                       ("Serpent-God's Curved Sword", 1), ('Shamshir', 1), ('Shotel', 0),
                       ('Spirit Sword', 0), ('Wing of Astel', 0)],
    'Daggers': [('Cinquedea', 1), ('Crystal Knife', 1), ('Misericorde', 1), ("Night's Edge", 0),
                ('Parrying Dagger', 0), ('Wakizashi', 1)],
    'Fists': [('Cipher Pata', 0), ('Golem Fist', 1), ('Grafted Dragon', 1), ('Iron Ball', 1), ('Katar', 0),
              ('Pata', 1), ('Star Fist', 1), ("Thiollier's Hidden Needle", 0)],
    'Flails': [("Bastard's Stars", 0), ('Chainlink Flail', 1), ('Family Heads', 0)],
    'Greataxes': [('Axe of Godrick', 1), ('Bonny Butchering Knife', 0), ('Butchering Knife', 0),
                  ("Gargoyle's Black Axe", 0), ("Gargoyle's Great Axe", 0),
                  ('Great Omenkiller Cleaver', 1), ('Putrescence Cleaver', 1), ('Rusted Anchor', 1)],
    'Great Hammers': [('Black Steel Greathammer', 1), ('Brick Hammer', 1),
                       ('Cranial Vessel Candlestand', 1), ("Devourer's Scepter", 1), ('Large Club', 0),
                       ('Pickaxe', 0), ('Smithscript Hammer', 0)],
    'Great Katanas': [("Dragon-Hunter's Great Katana", 1)],
    'Great Spears': [('Barbed Staff-Spear', 0), ("Messmer Soldier's Spear", 0), ('Serpent-Hunter', 1),
                      ("Siluria's Tree", 1), ('Treespear', 1), ("Vyke's War Spear", 0)],
    'Greatswords': [("Death's Poker", 0), ('Iron Greatsword', 1), ("Lordsworn's Greatsword", 0),
                     ("Ordovis's Greatsword", 1)],
    'Halberds': [("Gargoyle's Black Halberd", 1), ("Gargoyle's Halberd", 1), ('Golden Halberd', 1),
                 ("Loretta's War Sickle", 0), ('Lucerne', 0), ("Pest's Glaive", 0),
                 ('Poleblade of the Bud', 1), ('Ripple Crescent Halberd', 0), ('Spirit Glaive', 0),
                 ('Starcaller Spire', 0)],
    'Hammers': [('Club', 0), ('Flowerstone Gavel', 1), ('Hammer', 1), ('Ringed Finger', 1),
                ('Stone Club', 1), ("Varré's Bouquet", 0), ('Warpick', 0)],
    'Hand-to-Hand': [("Dryleaf Seal", 1)],
    'Heavy Thrusting Swords': [("Dragon King's Cragblade", 1), ('Great Épée', 0), ('Sword Lance', 1)],
    'Katanas': [('Hand of Malenia', 0), ('Meteoric Ore Blade', 1), ('Nagakiba', 1),
                ('Serpentbone Blade', 0), ('Sword of Night', 0)],
    'Light Greatswords': [('Greatsword of Damnation', 1), ("Leda's Sword", 1)],
    'Reapers': [('Halo Scythe', 1), ('Winged Scythe', 0)],
    'Spears': [('Bolt of Gransax', 1), ("Clayman's Harpoon", 1), ('Flamelost War Spear', 1),
               ("Inquisitor's Girandole", 1), ('Pike', 1), ('Short Spear', 0), ('Swift Spear', 0),
               ('Torchpole', 0)],
    'Straight Swords': [('Broadsword', 1), ('Broken Straight Sword', 0), ('Cane Sword', 0),
                         ("Carian Knight's Sword", 1), ('Coded Sword', 0), ('Flamelost War Sword', 1),
                         ('Marionette Short Sword', 0), ('Ornamental Straight Sword', 0),
                         ('Short Sword', 0), ('Stone-Sheathed Sword', 1),
                         ('Sword of Night and Flame', 1), ("Warhawk's Talon", 0)],
    'Thrusting Swords': [('Carian Sorcery Sword', 0), ("Cleanrot Knight's Sword", 1),
                          ('Frozen Needle', 0), ('Rapier', 0)],
    'Torches': [('Torch', 0)],
    'Twinblades': [("Eleonora's Poleblade", 0), ("Gargoyle's Black Blades", 1),
                    ("Gargoyle's Twinblade", 1)],
    'Whips': [("Hoslow's Petal Whip", 1), ('Thorned Whip', 1), ('Urumi', 0)],
    'Light Bows': [('Harp Bow', 1), ('Misbegotten Shortbow', 0)],
    'Bows': [('Black Bow', 0), ('Horn Bow', 1), ('Pulley Bow', 0)],
    'Greatbows': [('Golem Greatbow', 1), ('Greatbow', 0), ("Lion's Greatbow", 1)],
    'Medium Shields': [('Mad Sun Shield', 0)],
    'Thrusting Shields': [('Carian Thrusting Shield', 1)],
}


def run():
    with engine.connect() as conn:
        # System-level reference text
        for section, content in GENERAL_CHANGES.items():
            conn.execute(text("DELETE FROM sl_err_combat_mechanics WHERE section=:s"), {'s': f'weapons_{section}'})
            conn.execute(text("""
                INSERT INTO sl_err_combat_mechanics (section, content, created_at)
                VALUES (:s, :c, :ts)
            """), {'s': f'weapons_{section}', 'c': content, 'ts': NOW})
        print(f'{len(GENERAL_CHANGES)} General Weapon Changes sections seeded (in sl_err_combat_mechanics).')

        # Weight rates - update existing sl_weapons rows by name match
        updated = 0
        not_found = []
        for weapon_class, entries in WEIGHT_RATES.items():
            for name, rate in entries:
                result = conn.execute(text("""
                    UPDATE sl_weapons SET weight_rate = :rate
                    WHERE game = 'err' AND name = :name
                """), {'rate': rate, 'name': name})
                if result.rowcount:
                    updated += 1
                else:
                    not_found.append(name)
        conn.commit()
        print(f'\n{updated} weapons updated with weight_rate.')
        if not_found:
            print(f'{len(not_found)} weapons NOT FOUND in sl_weapons (likely missing from regulation '
                  f'dump or name mismatch):')
            for n in not_found:
                print(f'  - {n}')


if __name__ == '__main__':
    run()
