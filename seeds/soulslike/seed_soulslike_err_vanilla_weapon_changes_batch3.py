"""
Seed: ERR Vanilla Weapon Changes, batch 3 (Fists through Great Spears).
Source: err.fandom.com/wiki/Vanilla_Weapons_Changes, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_vanilla_weapon_changes_batch3.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

CHANGES = [
    ('Cipher Pata', 'Fists',
     "Added the Blessed affinity effect. Unique skill changed to Unblockable Piercing Blade."),
    ('Clinging Bone', 'Fists',
     "0.3% Max HP+6 restoration on hit when at <=50% Max HP. x1.15 Poise Damage when at >=35/<=65% "
     "Max HP. (Hitbox size of all Fist attacks increased.)"),
    ('Grafted Dragon', 'Fists',
     "Added the Fire and Bolt affinity effects. x0.96 Physical Damage taken while equipped."),
    ('Madding Hand', 'Fists',
     "Added the Frenzied affinity effect. x1.12 Damage for 20 seconds when Madness occurs in the "
     "vicinity."),
    ('Poisoned Hand', 'Fists',
     "Removed Deadly Poison, changed to regular Poison buildup. x1.12 Damage for 20 seconds when "
     "Poison occurs in the vicinity."),
    ("Thiollier's Hidden Needle", 'Fists',
     "Added innate Poison buildup. If Poison from this weapon occurs on enemies affected by Sleep, it "
     "inflicts additional 0.6% Max HP+1 damage for 30 seconds."),
    ('Unarmed', 'Fists',
     "Changed damage type to True. Increased base damage to 50. Increased scaling to Strength (S+) / "
     "Dexterity (S+)."),
    ("Veteran's Prosthesis", 'Fists', "Added the Lightning affinity effect."),

    ("Bastard's Stars", 'Flails',
     "Added the Gravitational affinity effect. Attacks now cause targets to explode with delayed dark "
     "stars. Converted Magic damage portion into Lightning. x1.05 Attack Power of Gravity sorceries."),
    ('Family Heads', 'Flails',
     "Added innate Frostbite buildup. Changed scaling to Dexterity/Intelligence/Faith. x1.05 Attack "
     "Power of Ghostflame sorceries."),
    ('Nightrider Flail', 'Flails', "x1.1 Attack Power while on horseback."),
    ('Serpent Flail', 'Flails',
     "Added the Fire affinity effect. Added innate Poison buildup. Added innate Arcane scaling. Deals "
     "increased burn damage to poisoned enemies."),

    ('Axe of Godrick', 'Greataxes',
     "Added the Heavy and Keen affinity effects. 8%+80 HP restoration when stance-break occurs in "
     "vicinity."),
    ('Bonny Butchering Knife', 'Greataxes',
     "Added the Keen affinity effect. Changed damage type to Slash. Changed scaling to Dexterity. "
     "0.25% Max HP+5 restoration on hit. Unique skill (Hone Blade) sharpens the weapon for 25 "
     "seconds: 0.6% Max HP+12 restoration on hit, x1.05 Slash Damage. Animation speed of Hone Blade "
     "greatly increased."),
    ('Butchering Knife', 'Greataxes',
     "Changed model to Dark Souls 3's Butcher Knife. Changed damage type to Slash. Changed scaling to "
     "Dexterity. 0.25% Max HP+5 restoration on hit."),
    ('Crescent Moon Axe', 'Greataxes', "Changed light attacks to those of Lucerne."),
    ("Death Knight's Longhaft Axe", 'Greataxes',
     "Changed light attacks to those of Lucerne. Added the Lightning affinity effect. Added innate "
     "Death Blight buildup."),
    ("Executioner's Greataxe", 'Greataxes', "Critical attacks restore 6%+60 Max FP."),
    ("Gargoyle's Black Axe", 'Greataxes',
     "Added the Occult affinity effect. Changed damage type to True. Inflicts a small Destined Death "
     "effect on hit. For 5 seconds after swapping to this weapon: x1.2 Attack Power of skills."),
    ("Gargoyle's Great Axe", 'Greataxes',
     "For 5 seconds after swapping to this weapon: x1.2 Attack Power of skills."),
    ('Great Omenkiller Cleaver', 'Greataxes',
     "Changed first heavy attack to that of Dark Souls 3's Large Club. Default skill changed to "
     "Lion's Claw."),
    ('Longhaft Axe', 'Greataxes', "Changed light attacks to those of Lucerne."),
    ('Putrescence Cleaver', 'Greataxes', "x1.05 Attack Power of Putrescent sorceries."),
    ('Winged Greathorn', 'Greataxes', "Added innate Sleep buildup."),

    ('Beastclaw Greathammer', 'Great Hammers',
     "Added the Bestial affinity effect. x1.05 Attack Power of Bestial incantations. Removed Holy "
     "damage - Faith now scales Physical Damage."),
    ('Black Steel Greathammer', 'Great Hammers', "Removed innate Faith scaling and Holy damage."),
    ("Celebrant's Skull", 'Great Hammers', "Added innate Madness buildup."),
    ('Cranial Vessel Candlestand', 'Great Hammers',
     "Added the Fell affinity effect. Added a fire visual effect to the weapon. x1.05 Attack Power of "
     "Giants' Flame incantations."),
    ("Devourer's Scepter", 'Great Hammers',
     "Added the Magma affinity effect. Fire damage scales with Intelligence. 0.25% Max HP+5 "
     "restoration on hit, 2% Max HP+20 restoration on kill."),
    ("Envoy's Long Horn", 'Great Hammers', "x1.08 FP restoration from attacking and spell casts."),
    ('Great Stars', 'Great Hammers', "0.25% Max HP+5 restoration on hit."),
    ('Large Club', 'Great Hammers', "Changed first heavy attack to that of Dark Souls 3's Large Club."),
    ('Pickaxe', 'Great Hammers',
     "x1.1 Damage versus Stone-type enemies (x1.15 with Cold affinity). Changed default skill to "
     "Overhead Stance (not normally available to Great Hammers)."),
    ('Smithscript Greathammer', 'Great Hammers',
     "Can be buffed with greases/abilities, but buff is lost if thrown. No restricted Ash of War "
     "selection."),

    ("Dragon-Hunter's Great Katana", 'Great Katanas',
     "Added the Bolt affinity effect. Added innate Arcane scaling. x1.05 Attack Power of Dragon "
     "Communion incantations."),
    ("Rakshasa's Great Katana", 'Great Katanas',
     "x1.08 Damage taken during hyperarmor frames. Each hit grants x1.04 Attack Power and x1.06 "
     "Damage taken (lasts 6 seconds each stack, similar to Bestial affinity passive but longer "
     "duration)."),

    ('Barbed Staff-Spear', 'Great Spears', "x1.05 Attack Power of Spiral incantations."),
    ('Lance', 'Great Spears', "x1.1 Attack Power while on horseback."),
    ("Mohgwyn's Sacred Spear", 'Great Spears',
     "x1.05 Attack Power of Blood Oath incantations. Changed scaling to Strength/Faith/Arcane. Unique "
     "skill (Bloodboon Ritual) coats the weapon with bloodflame for 20 seconds: x1.02 Fire Attack "
     "Power / +20 Fire Damage; attacks inflict Bloodflame applying 8 Blood Loss/0.45s for 2 seconds "
     "(40 total); duration resets when reapplied."),
    ('Serpent-Hunter', 'Great Spears',
     "Added the Bestial affinity effect. Changed damage type to True."),
    ("Siluria's Tree", 'Great Spears',
     "Changed scaling to mainly Dexterity and Faith. x1.05 Attack Power of Crucible incantations."),
    ('Spear of the Impaler', 'Great Spears',
     "Added the Fire affinity effect. Changed scaling to Dexterity/Faith/Arcane. x1.05 Attack Power "
     "of Messmer's Flame incantations."),
    ("Vyke's War Spear", 'Great Spears',
     "Changed scaling to Strength/Dexterity/Intelligence/Faith. x1.05 Attack Power of Frenzied Flame "
     "incantations."),
    ('Treespear', 'Great Spears',
     "Removed innate Faith scaling and Holy damage. Added the ability to use Affinities and Ashes of "
     "War."),
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
        print(f'{updated} vanilla weapon change entries seeded (batch 3: Fists-Great Spears).')


if __name__ == '__main__':
    run()
