"""
Seed: ERR Tools and Consumables - Aromatics, Greases, Pots, Throwables, Buffs/Misc,
Flasks, and Tools.
Source: err.fandom.com/wiki/Tools_and_Consumables, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_tools_consumables.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SYSTEM_SECTIONS = {
    'overview': (
        "Reforged reworks consumables and adds many new ones, including aromatics, pots, throwables, "
        "greases, and buff items. Aromatics and greases in particular have been substantially added "
        "to and redesigned, making them more practical mid-combat and granting them new effects. "
        "Tools have also been reworked to be more effective, with multiple new tools added."
    ),
    'crafting_summary': (
        "Reforged introduces a complete rework of crafting, converting collected materials down into "
        "base materials (e.g. all Fire-related materials craft into 'Blazing Amalgam') so consumables "
        "cost shared base materials instead of direct ingredients. Drastically reduces crafting tedium "
        "and means passive material collection while exploring is almost always useful. (Full crafting "
        "system detail is in a separate Crafting page/table.)"
    ),
    'rune_arcs': (
        "Rune Arcs significantly expanded: in addition to activating your Great Rune, they now also "
        "put you into a multiplayer-capable state, replacing Furlcalling Finger Remedies. Defeating a "
        "boss immediately applies a Rune Arc to you; if you already have one active, you instead "
        "receive one as an item."
    ),
    'aromatics_overview': (
        "Maximum aromatics carried at once tripled, from 10 to 30. Bottle pickups now give 3 instead "
        "of 1. Usage speed increased and damage hitboxes improved for consistency. Damaging perfumes "
        "had their damage output and scaling increased significantly to reflect their cost. Three new "
        "perfume cookbooks added, two old ones updated: Perfumer's Cookbook [3] (same vanilla location, "
        "Auriza Side Tomb - Galvanizing Elixir, Ironjar Elixir), [4] (same vanilla location, Ainsel "
        "River merchant - Rimed Spraymist, Acid Spraymist), [5] (new - walls of Sellia after Sellia "
        "Backstreets grace - Stardust Elixir, Concealing Aromatic), [6] (new - large dark pit in "
        "Subterranean Shunning-Grounds with a Royal Revenant, first pipe maze section - Wraithflame "
        "Spraymist, Afflicting Aromatic), [7] (new - Mt. Gelmir merchant - Feverish Aromatic, "
        "Rupturing Aromatic)."
    ),
    'greases_overview': (
        "Greases significantly reworked. All greases last 40 seconds (Shield Grease lasts 60). Regular "
        "grease uses the Drawstring Grease animation; Drawstring greases removed from the game. "
        "Greases now coat both weapons simultaneously (except Shield Grease), benefiting multi-weapon "
        "setups. Greases increase how effectively a weapon can block their respective Element/Status "
        "by 20% (Dragonwound/Communion grease blocks Physical damage). If the weapon's Attack Power on "
        "a damage type is zero, the multiplier does not apply to that type. The multiplier is applied "
        "before the flat bonus."
    ),
    'pots_overview': (
        "Base damage and Poise Damage of all thrown pots increased. Roped pots removed; Hefty Pot "
        "explosion size increased. All pot consumables given Arcane damage scaling in addition to "
        "their normal scaling stats - pots with no other damage scaling have very high Arcane scaling "
        "(Poison pots + Hefty, Fetid pots + Hefty, Sleep pots + Eternal/Hefty, Swarm Pots + Hefty)."
    ),
    'flasks_overview': (
        "Reforged doubles HP values game-wide, so Crimson Flask restoration is also approximately "
        "doubled. FP values are multiplied by 10 game-wide, so Cerulean Flask restoration is increased "
        "to match. Added flask sharing on co-op difficulties - using a Flask of Crimson/Cerulean Tears "
        "near an ally restores their HP/FP respectively.\n\n"
        "Crimson Flask Tier -> HP Restored: +0=600, +1=690, +2=780, +3=870, +4=960, +5=1050, +6=1122, "
        "+7=1194, +8=1266, +9=1338, +10=1392, +11=1446, +12=1500.\n\n"
        "Cerulean Flask Tier -> FP Restored: +0=600, +1=660, +2=720, +3=760, +4=800, +5=840, +6=880, "
        "+7=900, +8=920, +9=940, +10=960, +11=980, +12=1000."
    ),
}

# Greases - (name, attack_power_multiplier, flat_bonus, extra_effect)
GREASES = [
    ('Magic/Fire/Lightning/Holy Grease', 'x1.04 Elemental', '+40 Elemental', None),
    ('Royal Magic/Messmerfire/Dragonbolt/Golden Grease', 'x1.05 Elemental', '+50 Elemental', None),
    ('Blighted Grease', 'x1.02 Holy', '+20 Holy', '+25 Death Blight buildup'),
    ('Blood Grease', 'x1.01 Physical', '+10 Physical', '+25 Blood Loss buildup'),
    ('Dragon Communion Grease', 'x1.025 Physical', '+25 Physical', 'x1.05 Damage against Dragon enemies'),
    ('Dragonwound Grease', 'x1.02 Physical', '+20 Physical', 'x1.05 Damage against Dragon enemies'),
    ('Eternal Sleep Grease', 'x1.015 Magic, x1.015 Fire', '+15 Magic, +15 Fire',
     '+30 Sleep buildup, +15 Sleep buildup per second on self'),
    ('Festive Grease', 'x1.04 Holy', '+40 Holy', 'x1.05 Rune Gain'),
    ('Freezing Grease', 'x1.02 Magic', '+20 Magic', '+25 Frostbite buildup'),
    ('Frenzyflame Grease', 'x1.02 Fire', '+20 Fire', '+25 Madness buildup'),
    ('Poison Grease', 'x1.01 Physical', '+10 Physical', '+25 Poison buildup'),
    ('Rot Grease', 'x1.01 Physical', '+10 Physical', '+25 Scarlet Rot buildup'),
    ('Shield Grease', None, None, 'x0.8 Stamina Cost of blocks'),
    ('Soporific Grease', 'x1.01 Magic, x1.01 Fire', '+10 Magic, +10 Fire', '+25 Sleep buildup'),
]

# (category, name, effect, duration, is_new, acquisition)
CONSUMABLES = [
    # New Aromatics
    ('Aromatic', 'Afflicting Aromatic',
     "Releases spores that repeatedly sprout into Deathroots, inflicting Death Blight.",
     None, 1, "Perfumer's Cookbook [6]: large dark pit in Subterranean Shunning-Grounds with a "
     "Royal Revenant, first pipe maze section."),
    ('Aromatic', 'Concealing Aromatic',
     "Turns self and nearby allies invisible, reducing target priority and providing some "
     "resistance to True/Standard damage.",
     None, 1, "Perfumer's Cookbook [5]: walls of Sellia, after the Sellia Backstreets Site of "
     "Grace."),
    ('Aromatic', 'Feverish Aromatic',
     "Launches a burst of explosive spores, inflicting Madness and Fire damage. Spores linger "
     "briefly, inflicting additional Madness.",
     None, 1, "Perfumer's Cookbook [7]: purchase from the Mt. Gelmir merchant."),
    ('Aromatic', 'Galvanizing Elixir',
     "Bolsters the body with lightning, improving Movement Speed and Stamina Regen.",
     None, 1, "Perfumer's Cookbook [3]: Auriza Side Tomb in Altus Plateau."),
    ('Aromatic', 'Rimed Spraymist',
     "Releases a cold mist from the user's mouth, inflicting Frostbite and Magic damage. Similar "
     "to Hoarfrost Stomp, but stronger.",
     None, 1, "Perfumer's Cookbook [4]: purchase from the Ainsel River merchant."),
    ('Aromatic', 'Rupturing Aromatic',
     "Scatters flies over a wide area that rupture into pools of blood, inflicting Blood Loss and "
     "Fire damage.",
     None, 1, "Perfumer's Cookbook [7]: purchase from the Mt. Gelmir merchant."),
    ('Aromatic', 'Stardust Elixir',
     "Lightens oneself with gravitational forces, increasing Equip Load and reducing Dodge "
     "Stamina Cost.",
     None, 1, "Perfumer's Cookbook [5]: walls of Sellia, after the Sellia Backstreets Site of "
     "Grace."),
    ('Aromatic', 'Wraithflame Spraymist',
     "Releases accursed flames from the user's mouth, inflicting Holy damage.",
     None, 1, "Perfumer's Cookbook [6]: large dark pit in Subterranean Shunning-Grounds with a "
     "Royal Revenant, first pipe maze section."),

    # Vanilla Aromatic Changes
    ('Aromatic', 'Acid Spraymist',
     "Decreased duration, increased effectiveness. Duration: 40s. Enemy Physical Damage: x0.85. "
     "Enemy Poise Damage: x0.9. Enemy Stamina Damage: x0.9. Acid debuff now stacks with other "
     "debuffs of the same type.",
     '40', 0, None),
    ('Aromatic', 'Bloodboil Aromatic',
     "Decreased duration and Attack Power boost; now greatly increases Max Stamina and Stamina "
     "Regen. Also increases Attack Power of perfume weapons/items even without physical damage. "
     "Duration: 30s. Damage taken: x1.333. x1.2 Physical and Attack Power of perfumes. Stamina "
     "Regen: +60/s. Max Stamina: x1.2. Less effective at melting enemies overall, but now "
     "drastically increases stamina and works with more damage sources.",
     '30', 0, None),
    ('Aromatic', 'Ironjar Aromatic',
     "Decreased duration, increased damage negation, drastically increased usage animation speed. "
     "Duration: 10s. Physical Damage Negation: x0.5. Magic/Fire/Holy Damage Negation: x0.65. "
     "Lightning Damage Negation: x1.5. Poise multiplier: x2. Status Resistance: +100. More useful "
     "for dealing with specific high-threat attacks.",
     '10', 0, None),
    ('Aromatic', 'Poison Spraymist', "Poison buildup: 30/tick.", None, 0, None),
    ('Aromatic', 'Spark Aromatic',
     "Now scales off Arcane instead of Dexterity. Using it near an enemy or wall now releases "
     "sparks in a half circle pattern instead of straight forward.",
     None, 0, None),
    ('Aromatic', 'Uplifting Aromatic',
     "Attack buff is now tied to the shield it provides, removed when the shield is removed. "
     "Duration: 30s. x1.1 Physical and Attack Power of perfumes. Shield All Damage Negation: "
     "x0.5. Shield Poise boost: x1.333.",
     '30', 0, None),

    # New Pots
    ('Pot', 'Death Lightning Pot',
     "Ritual pot dealing 160 Lightning damage, 60 Poise Damage, 600 Stamina Damage, and 120 "
     "Death Blight buildup in the explosion radius. 200% (A) Faith/Arcane scaling. Replaces the "
     "Red Lightning Pot.",
     None, 1, None),
    ('Pot', 'Hefty Frenzied Flame Pot',
     "Hefty pot dealing 160 Fire damage, 60 Poise Damage, 600 Stamina Damage, and 280 Madness "
     "buildup in the explosion radius. 80% (D) scaling on all five attributes.",
     None, 1, None),
    ('Pot', 'Hefty Holy Water Pot',
     "Hefty pot dealing 300 Holy damage, 120 Poise Damage, 1200 Stamina Damage in the explosion "
     "radius. 10% extra damage to Undead enemies. 200% (A) Faith/Arcane scaling. Recipe found on "
     "a corpse in the Finger Ruins of Dheo, north, near spirit eels.",
     None, 1, None),
    ('Pot', 'Rock Pot',
     "Pot full of rocks. Deals 160 Strike damage, 70 Poise Damage, 700 Stamina Damage. 300% (S+) "
     "Strength and 100% (C) Arcane scaling. Recipe in Nomadic Warrior's Cookbook [5].",
     None, 1, None),
    ('Pot', 'Hefty Sleep Pot',
     "Hefty pot dealing 150 Strike damage, 50 Poise Damage, 500 Stamina Damage, and 70 Sleep "
     "buildup; applies 70 Sleep buildup per second within the effect radius for 4 seconds. 400% "
     "(S+) Arcane scaling.",
     None, 1, None),
    ('Pot', 'Hefty Ancient Dragonbolt Pot',
     "Hefty pot dealing 300 Lightning damage, 120 Poise Damage, 1200 Stamina Damage in the "
     "explosion radius. 200% (A) Faith/Arcane scaling.",
     None, 1, None),

    # Vanilla Pot Changes
    ('Pot', 'Cursed-Blood Pot',
     "x0.9 Status Resistance on the marked enemy for 60 seconds.", '60', 0, None),
    ('Pot', 'Fetid Pot',
     "Self poison duration now matches other poison sources (unverified). Self poison buildup: "
     "200 -> 300 (unverified).",
     None, 0, None),
    ('Pot', 'Redmane Fire Pot / Hefty Fire Pot', "Removed Dexterity scaling.", None, 0, None),
    ('Pot', 'Volcano Pot / Hefty Volcano Pot',
     "Added Intelligence scaling. Removed Strength and Dexterity scaling.", None, 0, None),
    ('Pot', 'Ancient Dragonbolt Pot',
     "Reskinned and repurposed as a Red Lightning pot. Scales with Faith/Arcane.", None, 0, None),
    ('Pot', 'Red Lightning Pot', "Replaced with Death Lightning Pot.", None, 0, None),
    ('Pot', 'Sleep Pot', "Sleep buildup: 29 -> 50.", None, 0, None),
    ('Pot', 'Magic Pot / Academy Magic Pot', "Increased Intelligence scaling.", None, 0, None),
    ('Pot', 'Hefty Magic Pot', "Reduced Intelligence scaling.", None, 0, None),
    ('Pot', 'Hefty Rock Pot',
     "Increased Strength scaling, removed Dexterity scaling. Scales primarily with Strength, low "
     "Arcane scaling.",
     None, 0, None),
    ('Pot', 'Hefty Furnace Pot',
     "Increased Faith scaling, removed Strength and Dexterity scaling. Has the highest Arcane "
     "scaling of all non-status-inducing pots.",
     None, 0, None),
    ('Pot', 'Lightning Pot / Hefty Lightning Pot',
     "Increased Dexterity scaling, removed Strength scaling.", None, 0, None),
    ('Pot', 'Fire Pot', "Removed Dexterity scaling.", None, 0, None),
    ('Pot', 'Giants Flame Pot', "Increased Faith scaling.", None, 0, None),
    ('Pot', 'Hefty Fire Pot / Redmane Fire Pot',
     "Increased Strength scaling, removed Dexterity scaling.", None, 0, None),
    ('Pot', 'Sacred Order Pot', "Scales with Intelligence and Faith.", None, 0, None),

    # Throwables
    ('Throwable', 'Azula Chakram',
     "Chakram thrown by Farum Azula Beastmen. Scales with Dexterity and primarily Strength. "
     "Recipe from Ancient Dragon Apostle's Cookbook [5], sold by the Dragonbarrow Isolated "
     "Merchant.",
     None, 1, None),
    ('Throwable', 'Azula Lightning Chakram',
     "Chakram thrown by Farum Azula Beastmen. Scales with Strength and primarily Faith. Recipe "
     "from Ancient Dragon Apostle's Cookbook [5], sold by the Dragonbarrow Isolated Merchant.",
     None, 1, None),
    ('Throwable', 'Call of Tibia',
     "Fixed placement issues so the skeleton more consistently faces the enemy; increased "
     "stagger and knockback dealt.",
     None, 0, None),
    ('Throwable', 'Crystalian Chakram',
     "Chakram thrown by Crystalians. Scales with Dexterity, Strength, and primarily "
     "Intelligence. Recipe from Glintstone Craftsman's Cookbook [9], sold by Iji the Blacksmith.",
     None, 1, None),
    ('Throwable', 'Putrid Crystalian Chakram',
     "Chakram thrown by Crystalians. Applies Scarlet Rot buildup (exact value unverified). "
     "Recipe from Glintstone Craftsman's Cookbook [9], sold by Iji the Blacksmith.",
     None, 1, None),
    ('Throwable', 'Sanctified Stone',
     "Weighty Stones that deal Holy damage instead. Crafted in batches of 5 from a single "
     "Sanctified Stone. Obtained from Nomadic Warrior's Cookbook [2]. Scales primarily with "
     "Strength.",
     None, 1, None),
    ('Throwable', 'Surging Frenzied Flame',
     "Greatly improved hitbox consistency by increasing size and adding a new hitbox to the main "
     "flame itself.",
     None, 0, None),
    ('Throwable', 'Weighty Stone',
     "Replaces the removed ability to throw Ruin Fragments. Crafted in batches of 5 from a "
     "single Ruin Fragment; recipe available by default. Scales primarily with Strength.",
     None, 1, None),

    # Buffs / Misc
    ('Buff/Misc', 'Boiled Crab',
     "Physical Damage Taken: x0.85. No longer overrides other body buffs when used.", '100', 0, None),
    ('Buff/Misc', 'Boiled Prawn',
     "Physical Damage Taken: x0.9. No longer overrides other body buffs when used.", '150', 0, None),
    ('Buff/Misc', 'Dragon Communion Flesh',
     "+6 Vigor/Endurance/Strength/Dexterity. No longer overrides other body buffs when used.",
     '100', 0, None),
    ('Buff/Misc', 'Exalted Flesh',
     "Physical Attack Power: x1.1. No longer overrides other body buffs when used.", '60', 0, None),
    ('Buff/Misc', 'Fingerprint Nostrum',
     "+6 Mind/Intelligence/Faith/Arcane. No longer overrides other body buffs when used.",
     '100', 0, None),
    ('Buff/Misc', 'Glass Shards',
     "Can be consumed, dealing 80% of your HP - can be used to set up Branchsword Talisman "
     "strategies easily.", None, 0, None),
    ('Buff/Misc', 'Gold-Pickled Fowl Feet',
     "Rune Gain: x1.15. Removed on grace rest.", '300', 0, None),
    ('Buff/Misc', 'Pickled Turtle Neck', "Stamina Regen: +50.", '120', 0, None),
    ('Buff/Misc', 'Silver-Pickled Fowl Feet',
     "Item Discovery: +100. Removed on grace rest.", '300', 0, None),
    ('Buff/Misc', 'Warming Stone / Frenzy Stone',
     "Added a small amount of percentage-based regeneration on top of flat regeneration, but the "
     "% healing is much weaker on enemies - better heals Spirit Ashes (typically multiple times "
     "more HP than the player), with a small benefit to extremely high-HP players (unverified).",
     None, 0, None),
    ('Buff/Misc', 'Well-Pickled Turtle Neck', "Stamina Regen: +70.", '60', 0, None),
    ('Buff/Misc', 'Withered Twig',
     "Afflicts you with Death Blight, but also grants the Sacrificial Twig effect, preventing "
     "rune loss. Essentially the Homeward Bone from previous games - safely returns to your most "
     "recent Site of Grace even when warping is not allowed. Acquired from Nomadic Warrior's "
     "Cookbook [25], found in Stormveil Castle shortly past the Rampart Tower Site of Grace.",
     None, 1, None),
    ('Buff/Misc', 'Regular Cured Meats',
     "Status Resistance: +250. No longer have any innate status buildup upon use.", '100', 0, None),
    ('Buff/Misc', 'White Cured Meats',
     "Status Resistance: +150. No longer have any innate status buildup upon use.", '200', 0, None),
    ('Buff/Misc', 'Revitalizing Cured Meat',
     "Vitality: +250. Recipe from Nomadic Warrior's Cookbook [25], found in Stormveil Castle - "
     "from Rampart Tower Site of Grace, head through the North door then turn immediately right.",
     '100', 1, None),
    ('Buff/Misc', 'Revitalizing White Cured Meat',
     "Vitality: +150. Recipe from Nomadic Warrior's Cookbook [26], located above and east of "
     "Woodfolk Ruins (small set of lone ruins on a cliff).",
     '200', 1, None),
    ('Buff/Misc', 'Erdbark Raisins',
     "Torrent Movement Speed and Torrent+Rider All Damage Negation buffs (exact values "
     "unverified). Recipe from Stable-Master's Cookbook [1], dropped by a Haligtree Knight "
     "wandering the path through the Mistwood.",
     None, 1, None),
    ('Buff/Misc', 'Stormhoof Raisins',
     "Torrent Movement Speed and Torrent+Rider All Damage Negation buffs (exact values "
     "unverified). Recipe from Stable-Master's Cookbook [1], dropped by a Haligtree Knight "
     "wandering the path through the Mistwood.",
     None, 1, None),
    ('Buff/Misc', 'Spirit Raisins', None, '180', 0, None),
]

# (name, effect, is_new, acquisition)
TOOLS = [
    ("Ancestral Infant's Head", "Added Sleep buildup on hit.", 0, None),
    ("Baldachin's Blessing",
     "Held in inventory: x1.1 Equip Load, x0.9 Max HP. When used: 15 second duration, x1.25 "
     "Physical Damage Negation, x1.5 Poise, FP Cost change unverified.", 0, None),
    ('Decree of Haima',
     "Reusable tool that throws a magic hammer directly ahead, affected by gravity. Bounces off "
     "and sticks into the first object it hits after striking an enemy. Cannot be thrown again "
     "until a long cooldown ends (exact seconds unverified) - cooldown can be skipped by picking "
     "the hammer back up. Considered an Academy Sorcery for the Haima Fortune, and a Throwing "
     "Weapon attack for the Smithscript Talisman. Scales with Strength and Intelligence equally.",
     1, "Found in Liurnia, on the cliffs above Stillwater Cave."),
    ("Lamenter's Mask",
     "S+ Strength scaling, +8 Arcane. x0.95 Damage taken (x0.8 from Holy). +60 Immunity/"
     "Robustness/Vitality.", 0, None),
    ("Margit's Shackle / Mohg's Shackle",
     "Both shackles now have the same range of 100 meters. Mohg no longer takes 20% extra "
     "damage when shackled.", 0, None),
    ('Perfumed Oil of Ranah',
     "Now considered a 'Dancing Attack' for Dancing Attack specific buffs.", 0, None),
    ('Priestess Heart',
     "x0.93 Damage taken and +140 Status Resistance. When used again while in dragon form: "
     "x1.15 Attack Power of Dragon Cult incantations for 100 seconds (duration cannot be "
     "extended by Common Buff Duration increases).", 0, None),
    ("Radiant Baldachin's Blessing",
     "Held in inventory: no longer reduces Max HP, no longer increases Equip Load by 10% like "
     "the regular version. Now infinitely reusable; when used, provides the same effect as the "
     "regular Baldachin's Blessing. FP Cost unverified.", 0, None),
    ('Rock Heart',
     "x0.9 Damage taken and +100 Status Resistance. When used again while in dragon form: "
     "x1.15 Attack Power of Dragon Communion incantations for 100 seconds (duration cannot be "
     "extended by Common Buff Duration increases).", 0, None),
    ('Wraith-Calling Bell', "Increased animation speed (unverified).", 0, None),
]


def run():
    with engine.connect() as conn:
        for section, content in SYSTEM_SECTIONS.items():
            conn.execute(text("DELETE FROM sl_err_consumables_system WHERE section=:s"), {'s': section})
            conn.execute(text(
                "INSERT INTO sl_err_consumables_system (section, content) VALUES (:s, :c)"
            ), {'s': section, 'c': content})
        print(f'{len(SYSTEM_SECTIONS)} system overview sections seeded.')

        for name, mult, flat, extra in GREASES:
            effect_parts = []
            if mult:
                effect_parts.append(f"Attack Power Multiplier: {mult}")
            if flat:
                effect_parts.append(f"Flat Damage Bonus: {flat}")
            if extra:
                effect_parts.append(extra)
            effect = '. '.join(effect_parts) + '.'
            conn.execute(text("DELETE FROM sl_err_consumables WHERE category='Grease' AND name=:n"), {'n': name})
            conn.execute(text("""
                INSERT INTO sl_err_consumables (category, name, effect, duration_sec)
                VALUES ('Grease', :name, :eff, '40')
            """), {'name': name, 'eff': effect})
        print(f'{len(GREASES)} greases seeded.')

        inserted = 0
        for category, name, effect, duration, is_new, acquisition in CONSUMABLES:
            conn.execute(text(
                "DELETE FROM sl_err_consumables WHERE category=:cat AND name=:name"
            ), {'cat': category, 'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_consumables (category, name, effect, duration_sec, is_new_to_err, acquisition)
                VALUES (:cat, :name, :eff, :dur, :new, :acq)
            """), {
                'cat': category, 'name': name, 'eff': effect, 'dur': duration,
                'new': is_new, 'acq': acquisition,
            })
            inserted += 1
        print(f'{inserted} consumables seeded (Aromatics, Pots, Throwables, Buffs/Misc).')

        for name, effect, is_new, acquisition in TOOLS:
            conn.execute(text("DELETE FROM sl_err_consumables WHERE category='Tool' AND name=:n"), {'n': name})
            conn.execute(text("""
                INSERT INTO sl_err_consumables (category, name, effect, is_new_to_err, acquisition)
                VALUES ('Tool', :name, :eff, :new, :acq)
            """), {'name': name, 'eff': effect, 'new': is_new, 'acq': acquisition})
        print(f'{len(TOOLS)} tools seeded.')

        conn.commit()
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_consumables")).scalar()
        print(f'\nTotal sl_err_consumables rows: {total}')


if __name__ == '__main__':
    run()
