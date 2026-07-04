"""
Seed: ERR Vanilla Weapon Changes, batch 4 (Greatswords through Perfume Bottles).
Source: err.fandom.com/wiki/Vanilla_Weapons_Changes, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_vanilla_weapon_changes_batch4.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

CHANGES = [
    ("Alabaster Lord's Sword", 'Greatswords',
     "Changed light attacks to Bloodborne's Holy Moonlight Sword. Changed heavy attacks to those of "
     "Claymore. Added the Gravitational affinity effect. Converted Magic damage portion into "
     "Lightning. x1.05 Attack Power of Gravity sorceries. Skill hits empower the weapon's next heavy "
     "attack: x1.4 Lightning Attack Power."),
    ("Banished Knight's Greatsword", 'Greatswords', "Default skill changed to Stormcaller."),
    ('Bastard Sword', 'Greatswords',
     "Changed light attacks to Bloodborne's Holy Moonlight Sword. Changed one-handed heavy attacks "
     "to those of Flamberge."),
    ('Blasphemous Blade', 'Greatswords',
     "Added the Magma and Occult affinity effects. Fire damage scales with Intelligence. 2% Max HP+20 "
     "restoration on kill."),
    ('Dark Moon Greatsword', 'Greatswords',
     "Changed light attacks to Bloodborne's Holy Moonlight Sword. x1.05 Attack Power of Cold "
     "sorceries. Unique skill (Moonlight Greatsword) coats the weapon with frost for 35 seconds: "
     "x1.03 Magic Attack Power / +30 Magic Damage, +40 Frostbite."),
    ("Death's Poker", 'Greatswords',
     "Changed scaling to Dexterity/Intelligence/Faith. Changed damage type to Strike and Magic. "
     "x1.05 Attack Power of Ghostflame sorceries."),
    ('Flamberge', 'Greatswords',
     "Changed two-handed light attacks to those of Knight's Greatsword."),
    ("Gargoyle's Blackblade", 'Greatswords',
     "Added the Occult affinity effect. Changed damage type to True. Inflicts a small Destined Death "
     "effect on hit. For 5 seconds after swapping to this weapon: x1.2 Attack Power of skills."),
    ("Gargoyle's Greatsword", 'Greatswords',
     "For 5 seconds after swapping to this weapon: x1.2 Attack Power of skills."),
    ('Golden Order Greatsword', 'Greatswords',
     "Changed light attacks to Bloodborne's Holy Moonlight Sword. Added the Sacred affinity effect. "
     "Changed scaling to Dexterity/Intelligence/Faith. x1.05 Attack Power of Fundamentalist "
     "incantations."),
    ('Greatsword of Damnation', 'Greatswords',
     "Is now a Light Greatsword. Added innate Madness buildup. Changed scaling to Strength/Dexterity/"
     "Intelligence/Faith. Charged heavy attacks extend the weapon's barbs with a burst of holy "
     "energy: +200 Holy Damage, +12 Poise Damage (120 per weapon card), +600 Stamina Damage; unverified "
     "Action Speed increase of charged heavies for 20 seconds when Madness occurs in the vicinity."),
    ('Greatsword of Solitude', 'Greatswords',
     "Added the Quality affinity effect. x0.85 Stamina Cost of blocks while a summoned spirit is "
     "alive. x1.1 Damage dealt for 30 seconds after summoned spirit dies."),
    ("Helphen's Steeple", 'Greatswords',
     "Changed light attacks to Bloodborne's Holy Moonlight Sword. Changed heavy attacks to those of "
     "Claymore. Added innate Frostbite buildup. Changed scaling to Strength/Intelligence/Faith. Unique "
     "skill (Ruinous Ghostflame) coats the weapon with ghostflame for 25 seconds: x1.5 Magic Attack "
     "Power / x0.67 Physical Attack Power, +50 Frostbite."),
    ('Inseparable Sword', 'Greatswords',
     "Added the Sacred affinity effect. Added innate Arcane scaling and requirement. Applying a Holy "
     "buff to the weapon grants a Determination effect: x1.3 Attack Power for one hit."),
    ('Iron Greatsword', 'Greatswords',
     "Changed two-handed jump heavy attacks to those of Omen Cleaver. Changed one-handed heavy attacks "
     "to those of Flamberge. x1.075 Attack Power of dashing light attacks, x1.08 of dashing heavy "
     "attacks, x1.05 of jumping attacks."),
    ("Knight's Greatsword", 'Greatswords',
     "Changed first heavy attack to that of Claymore."),
    ('Lizard Greatsword', 'Greatswords',
     "Added innate Poison buildup. Default skill changed to Stamp (due to removal of Stamp (Sweep) "
     "and Stamp (Upward Cut) skills)."),
    ("Lordsworn's Greatsword", 'Greatswords', "Default skill changed to Charge Forth."),
    ("Marais Executioner's Greatsword", 'Greatswords',
     "Changed light attacks to Bloodborne's Holy Moonlight Sword. Changed heavy attacks to those of "
     "Flamberge. Charged attacks empower main-hand weapon for 2 seconds: x1.2 Magic Damage."),
    ("Ordovis's Greatsword", 'Greatswords',
     "Changed heavy attacks to those of Death's Poker. x1.05 Attack Power of Crucible incantations."),
    ('Sacred Relic Sword', 'Greatswords',
     "Added the Sacred affinity effect. Changed damage type to True. x1.05 Damage dealt / x0.95 "
     "Damage taken when at >=95% Max HP; x1.1 Damage dealt / x0.9 Damage taken when at <=25% Max HP."),
    ('Sword of Milos', 'Greatswords',
     "4% Max FP+40 restoration on kill. Unique skill (Shriek of Milos) grants for 20 seconds: x1.1 "
     "Damage taken and x1.11 Status Buildup of enemies, x1.1 Physical Attack Power."),

    ('Banished Knight\'s Halberd', 'Halberds', "Default skill changed to Storm Assault."),
    ("Commander's Standard", 'Halberds',
     "Added the Quality affinity effect. x1.05 Attack Power of Storm attacks. +2 Endurance when "
     "empowering an ally, increased by +1 per additional ally (stacks up to +10). (All halberds can "
     "now guard attack - 'shield poking'.)"),
    ('Dragon Halberd', 'Halberds',
     "Renamed to Dragonscale Halberd. Added the Bolt affinity effect. Added innate Frostbite buildup. "
     "Frostbite in the vicinity grants a buff for 20 seconds: x0.85 Damage taken, x0.85 Status "
     "Buildup. Unique skill (Ice Lightning Sword) coats the weapon with ice lightning for 20 seconds: "
     "x1.07 Lightning Attack Power / +70 Lightning Damage, +30 Frostbite."),
    ("Gargoyle's Black Halberd", 'Halberds',
     "Added the Occult affinity effect. Changed damage type to True. Inflicts a small Destined Death "
     "effect on hit. For 5 seconds after swapping to this weapon: x1.2 Attack Power of skills."),
    ("Gargoyle's Halberd", 'Halberds',
     "For 5 seconds after swapping to this weapon: x1.2 Attack Power of skills."),
    ('Golden Halberd', 'Halberds',
     "Added the Blessed affinity effect. Default skill changed to Prayerful Strike. x1.05 Attack "
     "Power of Erdtree incantations. Skill hits grant a Golden Vow effect for 20 seconds: x1.1 Damage "
     "dealt, x0.9 Damage taken."),
    ("Loretta's War Sickle", 'Halberds',
     "Added the Blessed affinity effect. Converted into a Weapon Catalyst capable of casting "
     "sorceries. Melee attacks and spells scale with Strength/Dexterity/Intelligence. x1.1 Attack "
     "Power of Loretta's sorceries. Unique skill buffs the weapon for 25 seconds: x1.1 Magic Attack "
     "Power (also affects all sorceries cast), +100 Cast Speed."),
    ('Lucerne', 'Halberds',
     "Flipped the model (weapon hits with the hammer part). Changed damage type to Strike and Pierce."),
    ('Nightrider Glaive', 'Halberds', "x1.1 Attack Power while on horseback."),
    ("Pest's Glaive", 'Halberds',
     "Changed heavy attacks to those of Short Spear. x0.96 Elemental Damage taken."),
    ('Poleblade of the Bud', 'Halberds',
     "x1.05 Attack Power of Servant of Rot incantations. Arcane scaling changed to Faith. Generates "
     "rotten butterflies on hit after a short delay that deal True Damage, Scarlet Rot buildup, and "
     "10 Poise Damage as a single explosion (exact values unverified)."),
    ('Ripple Crescent Halberd', 'Halberds',
     "Added the ability to use Ashes of War (cannot be infused). Status Effects in the vicinity "
     "increase Physical Attack Power by 12% for 60 seconds."),
    ('Spirit Glaive', 'Halberds',
     "Added innate Frostbite buildup. Changed scaling to Strength/Dexterity/Intelligence/Faith. x1.1 "
     "(unverified) Action Speed when at <=25% Max HP. Unique skill (Rancor Slash) buffs the weapon "
     "with ghostflame for 15 seconds: 40+4% Magic Attack Power, +40 Frostbite."),
    ('Vulgar Militia Shotel', 'Halberds', "Converted into a Reaper."),

    ("Envoy's Horn", 'Hammers', "x1.08 FP restoration from attacking and spell casts."),
    ('Flowerstone Gavel', 'Hammers',
     "Changed light roll, duck, and heavy running attacks to those of the Morning Star. Added the Bolt "
     "affinity effect. Added innate Blood Loss buildup. Changed scaling to Strength/Dexterity/Faith/"
     "Arcane. x1.05 Attack Power of Dragon Cult AND Dragon Communion incantations."),
    ("Marika's Hammer", 'Hammers',
     "Changed light roll, duck, and heavy running attacks to those of the Morning Star. Added "
     "explosive AoE effects to R2 attacks. Changed scaling to Strength/Dexterity/Intelligence/Faith. "
     "x1.05 Attack Power of Fundamentalist incantations."),
    ("Monk's Flamemace", 'Hammers',
     "Default skill changed to Flaming Strike. x1.05 Attack Power of Giants' Flame incantations."),
    ('Nox Flowing Hammer', 'Hammers',
     "Added the Quality affinity effect. Restores 1%+20 Stamina per hit to the user, drains 2%+10 "
     "Stamina per hit from the target."),
    ('Ringed Finger', 'Hammers', "Added the Heavy affinity effect."),
    ("Varré's Bouquet", 'Hammers',
     "Converted into a Weapon Catalyst capable of casting incantations. Melee attacks and spells "
     "scale with Dexterity/Faith/Arcane. x1.1 Attack Power of Blood Oath incantations."),
    ('Warpick', 'Hammers',
     "x1.1 Damage versus Stone-type enemies (x1.15 with Cold affinity)."),

    ("Dragon King's Cragblade", 'Heavy Thrusting Swords',
     "Added the Bolt affinity effect. Changed scaling to Dexterity/Faith (Faith increases Lightning "
     "damage). x1.05 Attack Power of Dragon Cult incantations."),
    ('Godskin Stitcher', 'Heavy Thrusting Swords',
     "Added the Occult affinity effect. When infused with Fated affinity, the Fire trails acquire a "
     "Black Flame visual effect."),
    ('Great Épée', 'Heavy Thrusting Swords', "Default skill changed to Repeating Thrust."),
    ("Queelign's Greatsword", 'Heavy Thrusting Swords',
     "Removed innate Faith scaling and Fire damage."),
    ('Sword Lance', 'Heavy Thrusting Swords',
     "Default skill changed to Spinning Gravity Thrust. x1.1 Attack Power while on horseback."),

    ('Dragonscale Blade', 'Katanas',
     "Added the Bolt affinity effect. Added innate Frostbite buildup. Frostbite in the vicinity "
     "grants a buff for 20 seconds: x0.85 Damage taken, x0.85 Status Buildup. Unique skill (Ice "
     "Lightning Sword) coats the weapon with ice lightning for 20 seconds: x1.07 Lightning Attack "
     "Power / +70 Lightning Damage, +30 Frostbite."),
    ('Hand of Malenia', 'Katanas',
     "Replaced innate Blood Loss buildup with Scarlet Rot buildup. Changed duck/backstep attack to "
     "that of Bloodborne's Chikage. Added 0.25% Max HP+5 restoration on hit."),
    ('Meteoric Ore Blade', 'Katanas',
     "Added the Gravitational affinity effect. Converted Magic damage portion into Lightning. Heavy "
     "attacks deal Strike damage with a purple lightning/stone visual effect. Unique skill: "
     "Starsplitter Stance."),
    ('Moonveil', 'Katanas', "Added the Night affinity effect."),
    ('Nagakiba', 'Katanas', "Default skill changed to Piercing Fang."),
    ('Rivers of Blood', 'Katanas',
     "Inflicts a small amount of self Blood Loss buildup on hit. Activating Blood Loss on yourself "
     "with this weapon briefly increases Fire Attack Power."),
    ('Serpentbone Blade', 'Katanas',
     "Added the ability to use Affinities and Ashes of War. Removed Deadly Poison, changed to regular "
     "Poison buildup."),
    ('Star-Lined Sword', 'Katanas',
     "Added the Magic affinity effect. Replaced innate Blood Loss buildup with Frostbite buildup. "
     "Changed scaling to Dexterity/Intelligence."),
    ('Sword of Night', 'Katanas',
     "Added the Night affinity effect. Removed innate Blood Loss buildup. Changed damage type to "
     "True."),

    ("Leda's Sword", 'Light Greatswords',
     "Added the Keen affinity effect. x1.05 Attack Power of Miquella incantations."),
    ("Rellana's Twin Blades", 'Light Greatswords',
     "Added the Fire and Magic affinity effects. Converted into a Weapon Catalyst capable of casting "
     "sorceries. Scales spells and melee attacks with Faith/Strength/Dexterity/Intelligence/Arcane. "
     "When used with Rellana's Cameo equipped and skill is used while the talisman's effect is active, "
     "the blades receive a corresponding fire and magic buff for 25 seconds (10%+20 Fire/Magic Damage)."),

    ('Chilling Perfume Bottle', 'Perfume Bottles',
     "Added the Cold affinity effect. (All Perfume Bottles now scale primarily off Arcane instead of "
     "Dexterity.)"),
    ('Firespark Perfume Bottle', 'Perfume Bottles', "Added the Fire affinity effect."),
    ('Lightning Perfume Bottle', 'Perfume Bottles', "Added the Lightning affinity effect."),
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
        print(f'{updated} vanilla weapon change entries seeded (batch 4: Greatswords-Perfume Bottles).')


if __name__ == '__main__':
    run()
