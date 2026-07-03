"""
Seed: ERR Vanilla Weapon Changes, batch 6 (Straight Swords through Whips).
Source: err.fandom.com/wiki/Vanilla_Weapons_Changes, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_vanilla_weapon_changes_batch6.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

CHANGES = [
    ('Cane Sword', 'Straight Swords',
     "Default Skill changed from Square Off to Sword Dance."),
    ("Carian Knight's Sword", 'Straight Swords',
     "Converted into a Weapon Catalyst capable of casting sorceries. Scales spells and melee attacks "
     "with Dexterity and Intelligence. x1.1 Attack Power of Carian sorceries. Added the ability to "
     "perform a Deflect during heavy attacks (visualized by the deflect icon in status effects)."),
    ('Coded Sword', 'Straight Swords', "Added the Blessed affinity effect."),
    ('Crystal Sword', 'Straight Swords',
     "Added the Magic affinity effect. x1.05 Attack Power of Crystalian sorceries. Grants Crystal "
     "Armor during skill usage (x0.8 Damage taken, +40 Poise) - also applies to regular Ashes of War "
     "via Ash of War Enkindling."),
    ('Golden Epitaph', 'Straight Swords',
     "Added the Sacred affinity effect. Now scales off Intelligence as well as Faith."),
    ('Lazuli Glintstone Sword', 'Straight Swords',
     "Added the Magic affinity effect. Converted into a Weapon Catalyst capable of casting sorceries. "
     "Scales spells and melee attacks with a mix of Strength, Dexterity, and mostly Intelligence. "
     "Default Skill changed from Glintstone Pebble to Carian Greatsword. Added the ability to perform "
     "a Deflect during heavy attacks."),
    ("Miquellan Knight's Sword", 'Straight Swords',
     "Added the Blessed affinity effect. Converted into a Weapon Catalyst capable of casting "
     "incantations. Scales spells and melee attacks with a mix of Strength, Dexterity, and mostly "
     "Faith. Has a new skill called Miquella's Sacred Light. x1.1 Attack Power of Miquella "
     "incantations."),
    ('Ornamental Straight Sword', 'Straight Swords', "Added the Quality affinity effect."),
    ('Regalia of Eochaid', 'Straight Swords',
     "Changed heavy attacks to those of Broadsword. Charged attacks empower main-hand weapon for 2 "
     "seconds: x1.2 Magic Damage."),
    ('Rotten Crystal Sword', 'Straight Swords',
     "Added the Magic affinity effect. Default Skill changed from Spinning Slash to Double Slash. "
     "x1.05 Attack Power of Crystalian sorceries."),
    ('Stone-Sheathed Sword', 'Straight Swords', "Added the Heavy affinity effect."),
    ('Sword of Darkness', 'Straight Swords',
     "Added the Occult and Magic affinity effects. Changed heavy attacks to those of the Warhawk's "
     "Talon. Now deals True damage and Magic damage, but still scales with Faith."),
    ('Sword of Light', 'Straight Swords',
     "Added the Sacred and Blessed affinity effects. Changed heavy attacks to those of the Shortsword. "
     "Now scales with Intelligence (still deals Holy damage). Now deals True damage."),
    ('Sword of Night and Flame', 'Straight Swords',
     "Added the Night and Fell affinity effects. During the day: x1.15 Fire Attack Power of armaments "
     "and x1.1 Fire Attack Power of spells. During the night: x1.15 Magic Attack Power of armaments "
     "and x1.1 Magic Attack Power of spells."),
    ('Velvet Sword of St. Trina', 'Straight Swords',
     "Is now a Thrusting Sword with Light Greatsword Heavy and Guard Counter attacks."),
    ("Warhawk's Talon", 'Straight Swords',
     "Slightly increases jump attack Action Speed."),

    ('Smithscript Dagger', 'Throwing Blade',
     "Can be buffed with greases/abilities, but buff is lost if thrown. No restricted Ash of War "
     "selection."),

    ('Carian Thrusting Shield', 'Thrusting Shields',
     "Changed upgrading path to Somber Smithing Stones. Added the Magic affinity effect. Default Skill "
     "changed from Shield Strike to Tremendous Phalanx."),
    ('Dueling Shield', 'Thrusting Shields',
     "Default skill changed from Shield Strike to Impaling Thrust."),

    ("Cleanrot Knight's Sword", 'Thrusting Swords',
     "Default Skill changed from Impaling Thrust to Sword Dance. x0.9 FP Cost of skills when wielded "
     "with the Cleanrot Spear or Halo Scythe. While holding the Cleanrot Spear in the left hand and "
     "the Cleanrot Knight's Sword in the right hand: grants a unique blocking animation with increased "
     "guard boost, a unique guard counter, and the Spear's Sacred Phalanx skill overrides any Ash of "
     "War on the Sword. (Critical value of all Thrusting Swords increased by 10 points, Rapier by 15.)"),
    ('Carian Sorcery Sword', 'Thrusting Swords',
     "Is now a Weapon Catalyst scaling mostly with Intelligence and Dexterity. x1.1 Attack Power of "
     "Carian sorceries."),
    ('Frozen Needle', 'Thrusting Swords',
     "Added the Cold affinity effect. Default Skill changed from Impaling Thrust to Ice Spear."),
    ("Rogier's Rapier", 'Thrusting Swords', "Increased charge attack speed."),

    ('Beast-Repellent Torch', 'Torches',
     "Added the Bestial affinity effect. (Torches: light intensity slightly reduced, all torches can "
     "now Deflect but not block normally.)"),
    ('Ghostflame Torch', 'Torches',
     "x1.1 Attack Power of Rancor attacks (most Ghostflame sorceries excluding Tibia's Summons and "
     "Rings of Spectral Light, Ghostflame Breath, Rykard's Rancor, Rancor Slash/Spirit Sword/Spirit "
     "Glaive, Ghostflame Ignition/Death's Poker, Twinbird Caduceus heavy attack, Spearcall Ritual, "
     "Rancor Pots, Rancor Shot). Default skill changed to Ghostflame Call."),
    ('Sentry\'s Torch', 'Torches', "Added the Sacred affinity effect."),
    ("St. Trina's Torch", 'Torches',
     "Successive attacks lower resistance to sleep by X% (exact value unverified)."),
    ('Steel-Wire Torch', 'Torches', "Added the Fire affinity effect."),
    ('Torch', 'Torches', "Added the Fire affinity effect."),

    ('Black Steel Twinblade', 'Twinblades',
     "Removed innate Faith scaling and Holy damage. Jumping Heavy Attacks cause a Holy damage "
     "explosion."),
    ("Eleonora's Poleblade", 'Twinblades',
     "Now inflicts a small amount of self Blood Loss buildup on hit. Activating Blood Loss on yourself "
     "with this weapon briefly increases Fire Attack Power."),
    ('Euporia', 'Twinblades', "Decreases damage against Undead enemies by 10%."),
    ("Gargoyle's Black Blades", 'Twinblades',
     "Added the Occult affinity effect. Default Skill changed from Spinning Slash to Spinning Strikes. "
     "Now deals True damage. Inflicts a small Destined Death effect on hit. For 5 seconds after "
     "swapping to this weapon: x1.2 Attack Power of skills."),
    ("Gargoyle's Twinblade", 'Twinblades',
     "Default Skill changed from Spinning Slash to Spinning Strikes. For 5 seconds after swapping to "
     "this weapon: x1.2 Attack Power of skills."),
    ('Godskin Peeler', 'Twinblades',
     "Added the Occult affinity effect. When infused with Fated affinity, the Fire trails acquire a "
     "Black Flame visual effect."),

    ("Giant's Red Braid", 'Whips',
     "Added the Fell affinity effect. x1.05 Attack Power of Giants' Flame incantations."),
    ("Hoslow's Whip", 'Whips', "Changed damage type to Slash."),
    ('Magma Whip Candlestick', 'Whips',
     "Added the Magma affinity effect. x1.05 Attack Power of Magma sorceries."),
    ('Thorned Whip', 'Whips',
     "Changed damage type to Slash. x1.05 Attack Power of Thorn sorceries."),
    ('Tooth Whip', 'Whips',
     "Unique skill (Painful Strike) now also decreases the Action Speed of enemy attack recovery "
     "animations in addition to the original Stamina Regen debuff. Increased debuff duration to 25 "
     "seconds. Deals bonus Strike damage to targets afflicted with slowing effects (including Painful "
     "Strike's effect)."),
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
        print(f'{updated} vanilla weapon change entries seeded (batch 6: Straight Swords-Whips - FINAL).')


if __name__ == '__main__':
    run()
