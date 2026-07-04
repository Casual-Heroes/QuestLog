"""
Seed: ERR Vanilla Weapon Changes, batch 2 (Curved Swords through Dual Catalysts).
Source: err.fandom.com/wiki/Vanilla_Weapons_Changes, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_vanilla_weapon_changes_batch2.py
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
    ("Beastman's Curved Sword", 'Curved Swords', "Default skill changed to Wild Strikes."),
    ('Dancing Blade of Ranah', 'Curved Swords',
     "Added the Fire affinity effect. Changed damage type to Slash and Fire (Dexterity scaling "
     "increases Fire damage). Continuous perfect actions build a stacking fire damage increase as "
     "long as perfect actions persist (unverified)."),
    ('Eclipse Shotel', 'Curved Swords',
     "Added the Cursed affinity effect. Added innate Death Blight buildup. Scales with Intelligence "
     "and Faith. Unique skill (Death Flare) coats the weapon with death flames for 20 seconds: "
     "x1.04+40 Holy Attack Power, +25 Death Blight buildup."),
    ('Falchion', 'Curved Swords', "Default skill changed to Sword Dance."),
    ('Flowing Curved Sword', 'Curved Swords',
     "Changed light attacks to those of Shamshir, increased heavy attack speed. -2 Scarlet Rot "
     "buildup when landing a hit."),
    ('Grossmesser', 'Curved Swords', "Changed heavy attacks to those of Spiked Club."),
    ("Horned Warrior's Sword", 'Curved Swords', "x1.05 Attack Power of Storm attacks."),
    ('Magma Blade', 'Curved Swords',
     "Added the Magma affinity effect. Fire damage scales with Intelligence. x1.05 Attack Power of "
     "Magma sorceries."),
    ('Mantis Blade', 'Curved Swords',
     "Added innate Death Blight buildup. Slightly increased cancel speed of charged heavy attacks. No "
     "longer a guaranteed drop from the shade in Gelmir Hero's Grave (enemy respawns indefinitely)."),
    ('Nox Flowing Sword', 'Curved Swords',
     "Added the Quality affinity effect. Restores 0.8%+16 Stamina per hit to the user, drains 2%+10 "
     "Stamina per hit from the target."),
    ('Scimitar', 'Curved Swords', "Changed light attacks to those of Shamshir."),
    ("Serpent-God's Curved Sword", 'Curved Swords', "2% Max HP+20 restoration on kill."),
    ('Spirit Sword', 'Curved Swords',
     "Added innate Frostbite buildup. Changed scaling to Dexterity/Intelligence/Faith. x1.1 (unverified) "
     "Action Speed when at <=25% Max HP. Unique skill (Rancor Slash) buffs the weapon with ghostflame "
     "for 15 seconds: 40+4% Magic Attack Power, +40 Frostbite."),
    ('Wing of Astel', 'Curved Swords',
     "Added the Gravitational and Night affinity effects. Converted Magic damage portion into "
     "Lightning. Increased speed of charged heavy attacks."),

    ('Black Knife', 'Daggers',
     "Added the Night and Occult affinity effects. Critical hits apply Destined Death. Ash of War adds "
     "a short (8 second) buff: x1.01 Holy Attack Power / +10 Holy Damage, attacks inflict a Minor "
     "Destined Death effect."),
    ('Blade of Calling', 'Daggers', "Added the Occult affinity effect."),
    ("Celebrant's Sickle", 'Daggers', "Added innate Madness buildup."),
    ('Cinquedea', 'Daggers',
     "Added the Bestial affinity effect. x1.05 Attack Power of Bestial incantations; x1.16 if cast "
     "within 3 seconds after using the unique skill (Beast's Step) - lasts as long as Bestial "
     "incantation casting persists."),
    ('Crystal Knife', 'Daggers',
     "Changed upgrading path to Somber Smithing Stones. Added the Cold affinity effect. Added innate "
     "Frostbite buildup. Innate skill changed to Chilling Mist."),
    ('Erdsteel Dagger', 'Daggers',
     "Renamed to Brass Dagger (consistency with Brass Shield and original localization). Removed "
     "innate Faith scaling."),
    ("Fire Knight's Shortsword", 'Daggers',
     "Removed innate Faith scaling and Fire damage. Skill use increases Fire Attack Power of Messmer "
     "Flame incantations (exact % unverified)."),
    ('Glintstone Kris', 'Daggers',
     "Added the Magic and Blessed affinity effects. Converted into a Weapon Catalyst capable of "
     "casting sorceries and incantations. Melee attacks and spells scale with Dexterity/Intelligence/"
     "Faith."),
    ('Ivory Sickle', 'Daggers',
     "Changed upgrading path to Somber Smithing Stones. Added the Magic affinity effect. Changed "
     "scaling to Dexterity/Intelligence/Arcane."),
    ('Main-Gauche', 'Daggers',
     "Added thrusting R1 light attacks, using a mix of Dagger and Thrusting Sword animations."),
    ('Parrying Dagger', 'Daggers',
     "Added thrusting R1 light attacks, using a mix of Dagger and Thrusting Sword animations."),
    ('Reduvia', 'Daggers',
     "Added the ability to throw the weapon (like Smithscript Dagger) while held in the left hand, "
     "using Guard + Light Attack."),
    ('Scorpion Stinger', 'Daggers',
     "Added innate Poison buildup. Innate skill changed to The Rotten Flower Blooms Twice. Critical "
     "attacks now have massively increased status buildup (x3)."),
    ('Wakizashi', 'Daggers',
     "Can be powerstanced in the right hand with left-hand katanas (not just the inverse "
     "configuration), with significantly increased damage while powerstancing with a katana. When "
     "wielded with a katana, both weapons additionally receive x1.025 Attack Power / x1.02 Poise "
     "Damage / x1.02 Stamina Damage, applying even if attacking with only one weapon."),

    ('Scepter of the All-Knowing', 'Dual Catalysts',
     "Previously belonged to Hammers. Changed scaling to Intelligence/Faith. +25 Cast Speed."),
    ('Staff of the Great Beyond', 'Dual Catalysts',
     "Changed scaling to Intelligence/Faith/Arcane. +25 Cast Speed."),
    ('Staff of the Guilty', 'Dual Catalysts',
     "Previously belonged to Staves. Changed scaling to Intelligence/Faith."),
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
        print(f'{updated} vanilla weapon change entries seeded (batch 2: Curved Swords-Dual Catalysts).')


if __name__ == '__main__':
    run()
