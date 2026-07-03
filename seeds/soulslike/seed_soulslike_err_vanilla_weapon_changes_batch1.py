"""
Seed: ERR Vanilla Weapon Changes - behavioral/mechanical overrides applied to existing
vanilla weapons (affinity additions, default skill changes, damage type conversions,
scaling changes, etc.) Distinct from base stat data (weight/critical/AR) which lives in
sl_weapons / sl_err_weapon_passives.
Source: err.fandom.com/wiki/Vanilla_Weapons_Changes, pasted directly by user in batches.
Updated to 1.4.9G values per the wiki page.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_vanilla_weapon_changes_batch1.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (weapon_name, weapon_class, change_text)
CHANGES = [
    ("Celebrant's Cleaver", 'Axes', "Added innate Madness buildup."),
    ("Death Knight's Twin Axes", 'Axes',
     "Added the Lightning affinity effect. Added innate Death Blight buildup. Changed damage type to "
     "Slash."),
    ('Forked-Tongued Hatchet', 'Axes',
     "Added the Fire affinity effect. Changed damage type to Pierce and Fire. Its unique skill "
     "(Dragonform Flame) is considered a breath attack."),
    ('Highland Axe', 'Axes', "x1.05 Attack Power of roar attacks."),
    ('Icerind Hatchet', 'Axes', "Added the Cold and Bolt affinity effects."),
    ('Ripple Blade', 'Axes',
     "Added the ability to use Ashes of War (still cannot be infused). Status Effects in the vicinity "
     "increase Physical Attack Power by 12% for 60 seconds."),
    ("Rosus' Axe", 'Axes',
     "Added the Sacred affinity effect. Removed Intelligence scaling and Magic Damage. Changed damage "
     "type to Slash. +100 Vitality and -2/s Death Blight buildup."),
    ('Sacrificial Axe', 'Axes', "4% Max FP+40 restoration on kill."),
    ('Smithscript Axe', 'Axes',
     "Can be buffed with greases/abilities, but the buff is lost if thrown. Smithscript weapons no "
     "longer have a restricted Ash of War selection."),
    ('Stormhawk Axe', 'Axes',
     "Added the Lightning affinity effect. x0.8 Damage taken while using skills."),

    ('Smithscript Cirque', 'Backhand Blade',
     "Can be buffed with greases/abilities, but the buff is lost if thrown. Smithscript weapons do not "
     "have a restricted Ash of War selection."),

    ("Red Bear's Claw", 'Beast Claws', "Added the Bestial affinity effect. (Hitbox size of all Beast "
     "Claw attacks increased.)"),

    ('Bloodhound Claws', 'Claws',
     "Changed upgrading path to Somber Smithing Stones. Bloodhound Step is now a Unique Skill for this "
     "weapon. x0.9 FP Cost of skills when wielded with Bloodhound's Fang."),
    ('Claws of Night', 'Claws',
     "Added the Night affinity effect. Removed Blood Loss buildup. Changed damage type to True."),
    ('Raptor Talons', 'Claws',
     "Default skill changed to Raptor of the Mists. x1.05 Attack Power of Jump Attacks. Replaced Blood "
     "Loss buildup with Frostbite buildup."),
    ('Venomous Fang', 'Claws', "Removed Deadly Poison from the game, changed to regular Poison "
     "buildup. (Hitbox size of all Claw attacks increased, same size as Fists.)"),

    ('Ancient Meteoric Ore Greatsword', 'Colossal Swords',
     "Added the Lightning and Gravitational affinity effects. Converted Magic damage portion into "
     "Lightning."),
    ("Fire Knight's Greatsword", 'Colossal Swords',
     "Removed innate Faith scaling and Fire damage. Skill use increases Fire Attack Power of Messmer "
     "Flame incantations (exact % unverified)."),
    ("Godslayer's Greatsword", 'Colossal Swords',
     "Added the Occult affinity effect. Unique skill (The Queen's Black Flame) coats the weapon with "
     "Black Flame for 10 seconds: x1.03 Fire Attack Power / +30 Fire Damage, attacks inflict Black "
     "Flame. x1.05 Attack Power of Godslayer incantations."),
    ('Grafted Blade Greatsword', 'Colossal Swords',
     "Added the Heavy affinity effect. Unique skill (Oath of Vengeance) grants x1.4 Attack Power if "
     "damaged during the active portion of the skill animation (lasts 6 seconds or one attack), plus "
     "+2 Attributes for 25 seconds."),
    ('Greatsword', 'Colossal Swords',
     "Changed two-handed light attacks to those of Dark Souls 3's Fume Ultra Greatsword."),
    ('Greatsword of Radahn', 'Colossal Swords',
     "Converted the Greatsword of Radahn (Lord) and Greatsword of Radahn (Light) into this single "
     "weapon, equipped with the unique skill Promised Consort. Added the Sacred and Gravitational "
     "affinity effects. Removed Intelligence scaling and Magic Damage - Physical Damage now scales "
     "with Faith."),
    ("Maliketh's Black Blade", 'Colossal Swords',
     "Added the Occult affinity effect. Changed damage type to True and Holy. Inflicts a small "
     "Destined Death effect on hit. Unique skill (Destined Death) coats the weapon with Destined Death "
     "for 20 seconds: x1.02 Holy Attack Power / +20 Holy Damage, attacks inflict a stronger Destined "
     "Death effect, heavy attacks release a vertical blade-like projectile."),
    ("Moonrithyll's Knight Sword", 'Colossal Swords', "Removed from the game."),
    ('Royal Greatsword', 'Colossal Swords',
     "Added the Quality affinity effect. Added innate Frostbite buildup. Changed scaling to Strength/"
     "Dexterity (both increase Magic Damage). Changed damage type to Slash."),
    ('Ruins Greatsword', 'Colossal Swords',
     "Dropped by the Leonine Misbegotten boss in War-Dead Catacombs (Caelid). Changed two-handed light "
     "attacks to those of Dark Souls 3's Fume Ultra Greatsword. Added the Gravitational affinity "
     "effect. Converted Magic damage portion into Lightning. Increased the range of projectiles "
     "created by charged heavy attacks."),
    ('Starscourge Greatsword', 'Colossal Swords',
     "Added the Gravitational affinity effect. Changed damage type to Slash. Removed innate Magic "
     "Damage - Intelligence scaling now increases Physical Damage. x1.05 Attack Power of Gravity "
     "sorceries. Unique skill (Starcaller Cry) coats the weapon with stones for 20 seconds after the "
     "follow-up attack: x1.03 Physical Attack Power, x1.09 Poise Damage, x1.15 Stamina Damage, +60 "
     "Lightning Damage."),
    ("Troll Knight's Sword", 'Colossal Swords',
     "Converted into a Weapon Catalyst capable of casting sorceries. Melee attacks and spells scale "
     "with Strength and Intelligence. Default skill changed to Carian Grandeur. x1.1 Attack Power of "
     "Carian sorceries."),
    ("Watchdog's Greatsword", 'Colossal Swords',
     "Changed heavy attacks to those of the Greatsword. Default skill changed to Stamp, due to removal "
     "of the separate Stamp (Sweep) and Stamp (Upward Cut) skills."),
    ('Zweihander', 'Colossal Swords',
     "Changed light attacks to those of Dark Souls 3's Black Knight Greataxe. (Guard boost while not "
     "deflecting increased for all Colossal Swords.)"),

    ('Anvil Hammer', 'Colossal Weapons',
     "Added the Heavy and Fire affinity effects. x1.05 Damage of weapon throwing attacks."),
    ('Axe of Godfrey', 'Colossal Weapons',
     "Added the Heavy affinity effect. Has the R1 attack chains from Raider in Nightreign. Charged R2s "
     "grant x0.85 Damage taken for 2 seconds. Duration of unique skill Regal Roar increased from 20 to "
     "25 seconds."),
    ("Bloodfiend's Arm", 'Colossal Weapons',
     "Removed innate Arcane scaling. Added innate Blood Loss buildup."),
    ("Devonia's Hammer", 'Colossal Weapons', "x1.05 Attack Power of Crucible incantations."),
    ('Dragon Greatclaw', 'Colossal Weapons',
     "Added the Bolt affinity effect. Changed damage type to Slash and Lightning (Faith scaling "
     "increases Lightning damage). x1.05 Attack Power of Dragon Cult incantations. Unique skill "
     "(Dragon Smasher) coats the weapon with red lightning for 50 seconds: x1.05 Lightning Attack "
     "Power / +50 Lightning Damage; while active, a charged skill attack releases the stored "
     "lightning, dealing x1.15 Damage versus Dragon-type enemies."),
    ('Duelist Greataxe', 'Colossal Weapons',
     "Changed light attacks to those of Dark Souls 3's Black Knight Greataxe. Default skill changed to "
     "Braggart's Roar."),
    ("Envoy's Greathorn", 'Colossal Weapons', "x1.08 FP restoration from attacking and spell casts."),
    ('Fallingstar Beast Jaw', 'Colossal Weapons',
     "Added the Gravitational affinity effect. Converted Magic damage portion into Lightning. Added "
     "innate Blood Loss buildup."),
    ('Gazing Finger', 'Colossal Weapons',
     "Changed scaling to Intelligence/Faith/Arcane. Skill now deals a mix of Magic, Holy, and Physical "
     "Damage. x1.05 Attack Power of Erdtree incantations. x1.05 Attack Power of Finger sorceries."),
    ("Ghiza's Wheel", 'Colossal Weapons',
     "Updated to a singular more powerful R2 attack instead of R2 combos. Blood Loss in vicinity "
     "greatly increases the power of spinning wheel attacks: x1.25 Attack Power of spinning wheel "
     "attacks (including R2s and the skill), lasts 15 seconds."),
    ('Giant-Crusher', 'Colossal Weapons', "Default skill changed to Determination."),
    ('Great Club', 'Colossal Weapons', "Added the ability to use Affinities and Ashes of War."),
    ('Rotten Duelist Greataxe', 'Colossal Weapons',
     "Changed light attacks to those of Dark Souls 3's Black Knight Greataxe. Default skill changed to "
     "Braggart's Roar."),
    ('Rotten Staff', 'Colossal Weapons',
     "x1.05 Attack Power of Erdtree incantations. Added Faith scaling for Physical Damage."),
    ('Shadow Sunflower Blossom', 'Colossal Weapons',
     "Added the Sacred and Occult affinity effects. x1.05 Attack Power of Thorn sorceries."),
    ('Staff of the Avatar', 'Colossal Weapons',
     "Added the Blessed affinity effect. x1.05 Attack Power of Erdtree incantations. Removed Holy "
     "damage - Faith now scales Physical Damage."),
    ("Troll's Hammer", 'Colossal Weapons',
     "Changed upgrading path to Somber Smithing Stones. Features a unique skill, 'Troll's Raging "
     "Roar' - upgraded Troll's Roar adding a fiery explosion and lingering flames that deal damage "
     "over time to the followup attack. Added the Fell affinity effect. x1.05 Attack Power of Giants' "
     "Flame incantations."),
    ("Watchdog's Staff", 'Colossal Weapons',
     "Added the Magic affinity effect. Added Intelligence scaling for Physical Damage."),

    ("Bloodhound's Fang", 'Curved Greatswords',
     "Added the Keen affinity effect. x1.05 Attack Power of jumping attacks."),
    ("Freyja's Greatsword", 'Curved Greatswords',
     "x1.05 Attack Power of Redmane skills (Flame of the Redmanes, Lion's Claw, Lion's Flame/Fury of "
     "Azash, Roaring Bash, Radahn's Rain/Lion Greatbow, Savage Lion's Claw, Firebreather, Giant Hunt, "
     "Spinning Gravity Thrust, Starcaller's Cry/Starscourge Greatsword)."),
    ("Horned Warrior's Greatsword", 'Curved Greatswords',
     "Added the Large Club R2 Heavy attacks. x1.05 Attack Power of Storm attacks."),
    ("Magma Wyrm's Scalesword", 'Curved Greatswords',
     "Now dropped by the Magma Wyrm in Volcano Manor. Added the Magma affinity effect. Fire damage "
     "scales with Arcane instead of Faith. x1.05 Attack Power of Dragon Communion incantations."),
    ("Makar's Ceremonial Cleaver", 'Curved Greatswords',
     "Added the Magma affinity effect. x1.05 Attack Power of Dragon Communion incantations."),
    ("Monk's Flameblade", 'Curved Greatswords',
     "Default skill changed to Flaming Strike. x1.05 Attack Power of Giants' Flame incantations."),
    ("Morgott's Cursed Sword", 'Curved Greatswords',
     "Added the Occult affinity effect. Changed damage type to True. x1.06 Attack Power of wraith "
     "attacks. Unique skill (Cursed-Blood Slice) coats the weapon with flame for 15 seconds: x1.05 "
     "True Attack Power / +50 Fire Damage (despite the visual effect, does not increase Blood Loss "
     "buildup)."),
    ('Omen Cleaver', 'Curved Greatswords', "Default skill changed to Lion's Claw."),
    ("Onyx Lord's Greatsword", 'Curved Greatswords',
     "Added the Gravitational affinity effect. Converted Magic damage portion into Lightning. x1.05 "
     "Attack Power of Gravity sorceries. Skill hits empower the weapon's next running attack: x1.7 "
     "Lightning Attack Power."),
    ('Zamor Curved Sword', 'Curved Greatswords',
     "Added the Cold affinity effect. x1.05 Attack Power of Cold sorceries."),
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
        print(f'{updated} vanilla weapon change entries seeded (batch 1: Axes-Curved Greatswords).')


if __name__ == '__main__':
    run()
