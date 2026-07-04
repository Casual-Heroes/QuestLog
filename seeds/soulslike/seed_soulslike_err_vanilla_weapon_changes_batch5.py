"""
Seed: ERR Vanilla Weapon Changes, batch 5 (Reapers through Staves).
Source: err.fandom.com/wiki/Vanilla_Weapons_Changes, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_vanilla_weapon_changes_batch5.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

CHANGES = [
    ('Grave Scythe', 'Reapers', "Replaced innate Blood Loss buildup with Frostbite buildup."),
    ('Halo Scythe', 'Reapers',
     "Uses the unique two-handed light attacks from Bloodborne's Burial Blade."),
    ('Obsidian Lamina', 'Reapers',
     "Added the Keen affinity effect. Light attacks from the Halo Scythe."),
    ('Vulgar Militia Shotel', 'Reapers', "Previously belonged to Halberds."),
    ('Winged Scythe', 'Reapers',
     "Attacks have x1.05 Action Speed when Spirit Ashes are summoned. Unique skill (Angel's Wings) "
     "heals nearby Spirit Ashes by 10% Max HP+50 on hit and deals minor scaling damage over time. "
     "Replaced innate Blood Loss buildup with Sleep buildup."),

    ('Clawmark Seal', 'Seals',
     "+25 Cast Speed. x1.1 Attack Power of Bestial incantations. (Each seal now has a unique Heavy "
     "Attack that can be used while in the right hand or two-handing - costs no FP, does heavy poise "
     "damage.)"),
    ('Dryleaf Seal', 'Seals',
     "Converted into a Hand-to-hand Weapon Catalyst. Scales with Faith, Strength, and Dexterity. "
     "+25 Cast Speed. x1.1 Attack Power of Miquella incantations."),
    ('Erdtree Seal', 'Seals', "x1.1 Attack Power of Erdtree incantations."),
    ("Fire Knight's Seal", 'Seals',
     "Scales with Faith and Arcane. x1.1 Attack Power of Messmer's incantations."),
    ("Giant's Seal", 'Seals',
     "Added the Fell affinity effect. -25 Cast Speed. x1.1 Attack Power of Giants' Flame "
     "incantations."),
    ("Godslayer's Seal", 'Seals',
     "Added the Occult affinity effect. Casting Catch Flame with this seal emits Blackflame particles "
     "(doesn't deal Blackflame DoT but is considered a Godslayer incantation for damage boost "
     "purposes). x1.1 Attack Power of Godslayer incantations."),
    ('Gravel Stone Seal', 'Seals',
     "Added the Bolt affinity effect. Scales with Dexterity and Faith. x1.1 Attack Power of Dragon "
     "Cult incantations."),
    ('Spiral Seal', 'Seals',
     "Scales minorly with Strength and Dexterity, primarily with Faith. x1.1 Attack Power of Hornsent "
     "incantations."),

    ('Albinauric Shield', 'Shields',
     "Status effects in the vicinity grant x0.92 Stamina Cost of blocks for 60 seconds."),
    ("Ant's Skull Plate", 'Shields',
     "Default Skill changed from Shield Bash to Shield Crash. Grants +80 Immunity and -2 Scarlet Rot "
     "buildup every 2 seconds."),
    ("Banished Knight's Shield", 'Shields',
     "Default skill changed to Storm Wall. x1.05 Attack Power of Storm attacks."),
    ("Beastman's Jar Shield", 'Shields', "x1.08 Attack Power of throwing chakrams."),
    ('Black Steel Greatshield', 'Shields', "x1.06 Attack Power of Guard Counters."),
    ('Blue-Gold Kite Shield', 'Shields', "x1.08 HP Restoration."),
    ("Carian Knight's Shield", 'Shields',
     "Changed upgrading path to Somber Smithing Stones. Added the Magic affinity effect. x1.05 Attack "
     "Power of Carian skills and sorceries. Default Skill changed from No Skill to Carian Retaliation."),
    ('Crossed-Tree Towershield', 'Shields',
     "x1.085 Attack Power of rolling attacks, x1.08 of ducking attacks, x1.075 of dashing light "
     "attacks, x1.08 of dashing heavy attacks."),
    ('Crucible Hornshield', 'Shields',
     "Damage changed from Strike to Pierce. x1.05 Attack Power of Crucible incantations. Added Faith "
     "scaling and Holy damage."),
    ('Cuckoo Greatshield', 'Shields', "x1.05 Magic Attack Power."),
    ('Dragonclaw Shield', 'Shields',
     "Default Skill changed from Shield Bash to a unique variant of Thunderbolt. Added the Bolt "
     "affinity effect. Lightning damage now scales off Faith instead of Dexterity. x1.05 Attack Power "
     "of Dragon Cult incantations. While blocking with this shield in the offhand, performing light "
     "attacks now does lightning-imbued slashing attacks."),
    ('Erdtree Greatshield', 'Shields',
     "Added the Blessed affinity effect. x1.05 Attack Power of Erdtree incantations. While blocking "
     "with this shield in the offhand, performing light attacks now does forward shield thrusts (with "
     "guard frames) based on the Dismounted Tree Sentinel moveset. While Golden Vow is active: x0.9 "
     "Stamina Cost of blocks."),
    ('Fingerprint Stone Shield', 'Shields', "+0.1 Target Priority while blocking."),
    ('Gilded Greatshield', 'Shields', "x1.05 Poise Damage."),
    ('Golden Greatshield', 'Shields', "x1.05 Lightning Attack Power."),
    ('Golden Lion Shield', 'Shields',
     "x1.05 Attack Power of Redmane skills. Roaring Bash increases power of your next attack after a "
     "direct hit: x1.25 Attack Power for 4 seconds or one attack."),
    ('Great Turtle Shell', 'Shields',
     "x0.975 Physical Damage taken when held on the back. +15 Stamina Regen."),
    ('Haligtree Crest Greatshield', 'Shields', "x1.05 Holy Attack Power."),
    ('Hawk Crest Wooden Shield', 'Shields', "+50 Projectile Range."),
    ('Icon Shield', 'Shields',
     "Innate HP Regen replaced with the Blessed affinity effect. Grants x1.15 HP Restoration from "
     "non-flask sources while guarding."),
    ('Jellyfish Shield', 'Shields',
     "Added Arcane scaling and requirement. Added innate Poison buildup. Now deals True damage. Unique "
     "skill grants x1.15 Attack Power for 40 seconds."),
    ('Marred Wooden Shield', 'Shields', "Default Skill changed from No Skill to Shield Bash."),
    ('Messmer Soldier Shield', 'Shields', "x1.06 Attack Power of Heavy Attacks."),
    ('One-Eyed Shield', 'Shields',
     "Added the Fell affinity effect. x1.05 Attack Power of Giants' Flame incantations. Added Faith "
     "scaling and Fire damage."),
    ("Perfumer's Shield", 'Shields',
     "x1.06 Attack Power of perfume items, x1.04 Attack Power of perfume weapons."),
    ('Redmane Greatshield', 'Shields', "x1.05 Fire Attack Power."),
    ('Scorpion Kite Shield', 'Shields', "x1.16 Attack Power of critical attacks."),
    ('Serpent Crest Shield', 'Shields', "x1.05 Attack Power of Messmer's Flame incantations."),
    ('Shield of Night', 'Shields',
     "Added the Night affinity effect. Skill now tagged as a Guard Counter attack for damage boosting "
     "effects."),
    ('Shield of the Guilty', 'Shields',
     "+80 Concentration, -2 Sleep and Madness buildup every 2 seconds."),
    ('Silver Mirrorshield', 'Shields',
     "Added the Blessed affinity effect. Default Skill changed from No Skill to Carian Retaliation. "
     "x0.95 FP Cost of sorceries when used with Loretta's War Sickle."),
    ('Smoldering Shield', 'Shields', "Added the Magma affinity effect."),
    ('Spiked Palisade Shield', 'Shields', "Damage changed from Strike to Pierce."),
    ('Verdigris Greatshield', 'Shields', "Added the Heavy affinity effect."),
    ('Visage Shield', 'Shields',
     "Added the Fire and Fell affinity effects. Granted Fire damage scaling with Strength."),
    ('Wolf Crest Shield', 'Shields', "x1.05 Attack Power of Carian sorceries."),

    ('Bolt of Gransax', 'Spears',
     "Added the Bolt affinity effect. x1.05 Attack Power of Dragon Cult incantations. Lightning "
     "damage now scales off Faith instead of Dexterity."),
    ("Bloodfiend's Fork", 'Spears', "Removed innate Arcane scaling."),
    ("Celebrant's Rib Rake", 'Spears',
     "Added innate Madness buildup. Damage type changed from Pierce to Slash."),
    ("Clayman's Harpoon", 'Spears', "No longer has innate Magic Damage."),
    ("Cleanrot Knight's Spear", 'Spears',
     "Grants +100 Immunity and -2 Scarlet Rot buildup every second. While holding the Cleanrot Spear "
     "in the left hand and the Cleanrot Knight's Sword in the right hand: grants a unique blocking "
     "animation with increased guard boost, a unique guard counter (similar to the holy-infused attack "
     "the enemy does), and the Spear's Sacred Phalanx skill overrides any Ash of War on the Sword."),
    ('Cross-Naginata', 'Spears', "Default Skill changed from Impaling Thrust to Double Slash."),
    ('Crystal Spear', 'Spears',
     "Added the Magic affinity effect. Default Skill changed from Impaling Thrust to Glintstone "
     "Pebble. x1.05 Attack Power of Crystalian sorceries. Grants Crystal Armor during skill usage "
     "(x0.8 Damage taken, +40 Poise) - also applies to regular Ashes of War applied via Ash of War "
     "Enkindling. Location changed to the Raya Lucaria Crystal Cave boss fight."),
    ('Death Ritual Spear', 'Spears',
     "Added innate Frostbite buildup. Now scales off Faith as well as Intelligence. x1.05 Attack "
     "Power of Ghostflame sorceries."),
    ("Inquisitor's Girandole", 'Spears',
     "Added the Magma affinity effect. Default Skill changed from Impaling Thrust to Eruption. Against "
     "enemies recently afflicted with Blood Loss: applies the same DoT as the Fire Affinity and deals "
     "an extra 0.2% Max HP+1/s for 5 seconds (1.2% Max HP+6 total, varies x0.05 to x2 by enemy type)."),
    ('Rotten Crystal Spear', 'Spears',
     "Added the Magic affinity effect. x1.05 Attack Power of Crystalian sorceries."),
    ('Smithscript Spear', 'Spears',
     "Can be buffed with greases/abilities, but buff is lost if thrown. No restricted Ash of War "
     "selection."),
    ('Spiked Spear', 'Spears',
     "Renamed to the Marionette's Spiked Spear. Default Skill changed from Impaling Thrust to "
     "Repeating Thrust. Now deals Strike damage on non-thrusting attacks instead of Slash."),
    ('Swift Spear', 'Spears', "Thrusting heavy attacks from the Short Spear."),
    ('Torchpole', 'Spears',
     "Added the Fire affinity effect. Now uses the heavy sweeping attacks from the Partisan."),

    ('Academy Glintstone Staff', 'Staves', "+25 Cast Speed."),
    ("Azur's Glintstone Staff", 'Staves',
     "+50 Cast Speed. x1.125 FP Cost of sorceries. x1.05 Attack Power of Azur's sorceries."),
    ('Carian Glintblade Staff', 'Staves',
     "Now scales off Dexterity and Intelligence. x1.10 Attack Power of Carian sorceries (combines "
     "Carian Sword and Glintblade sorceries, merging the Glintstone and Glintblade staves)."),
    ('Carian Glintstone Staff', 'Staves',
     "Now called the Dark Glintstone Staff. Now scales off Dexterity and Intelligence. x1.10 Attack "
     "Power of Cold sorceries. Found north-west of the Eastern Liurnia Lake Shore site of grace, in "
     "a wooded location with crystal snake snails and glintstone crystals (drops from a new phantom "
     "enemy, a shiny Blue Miranda Blossom)."),
    ('Crystal Staff', 'Staves',
     "x1.10 Attack Power of Crystalian sorceries. Grants Crystal Armor during skill usage (x0.8 "
     "Damage taken, +40 Poise) - also applies to regular Ashes of War via Ash of War Enkindling."),
    ('Demi-Human Queen\'s Staff', 'Staves',
     "Now scales off Strength, Dexterity, and Intelligence. x1.08 FP restoration from attacking and "
     "spell casts."),
    ("Digger's Staff", 'Staves',
     "Now scales off Strength and Intelligence. x1.1 Attack Power of Stonedigger sorceries."),
    ("Gelmir's Glintstone Staff", 'Staves',
     "Added the Magma affinity effect. Now scales purely off Intelligence. Now has a guaranteed drop "
     "from the Heart of the Mountain camp. x1.1 Attack Power of Magma sorceries."),
    ("Lusat's Glintstone Staff", 'Staves',
     "x1.05 Attack Power of Lusat's sorceries. -25 Cast Speed. x1.25 FP Cost of sorceries."),
    ('Meteorite Staff', 'Staves',
     "Can now be upgraded using Somber Smithing Stones and scales like a normal staff. Added the "
     "Gravitational affinity effect. x1.1 Attack Power of Gravity sorceries."),
    ('Rotten Crystal Staff', 'Staves',
     "Changes the visuals of Crystalian sorceries to those used by the Putrid Crystalians. Adds "
     "Scarlet Rot buildup to Crystalian sorceries. -25 Cast Speed."),
    ('Staff of the Guilty', 'Staves',
     "Now a Dual Catalyst scaling off Intelligence and Faith. x1.1 Attack Power of Thorn sorceries. "
     "Now has a guaranteed drop from the Laeidd Battleground camp chest."),
]


def run():
    with engine.connect() as conn:
        updated = 0
        for name, wclass, change in CHANGES:
            conn.execute(text("DELETE FROM sl_err_vanilla_weapon_changes WHERE weapon_name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_vanilla_weapon_changes (weapon_name, weapon_class, change_text)
                VALUES (:name, :wclass, :change)
            """), {'name': name, 'wclass': wclass, 'change': change})
            updated += 1
        conn.commit()
        print(f'{updated} vanilla weapon change entries seeded (batch 5: Reapers-Staves).')


if __name__ == '__main__':
    run()
