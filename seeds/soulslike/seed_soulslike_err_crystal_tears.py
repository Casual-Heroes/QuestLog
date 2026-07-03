"""
Seed: ERR Wondrous Physick Crystal Tears - 2 new tears + 30 changed/renamed vanilla tears.
Source: err.fandom.com/wiki/Wondrous_Physick, pasted directly by user. Values updated to 2.1.2.3.

Note: Tear duration is NOT increased by Common Buff Duration effects (e.g. OldLordTalisman).

Run: chwebsiteprj/bin/python3 seed_soulslike_err_crystal_tears.py
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

# (name, effect, location, duration, is_new)
TEARS = [
    ('Arcane-knot Crystal Tear', "+8 Arcane", "Found at the Rose Church in Liurnia", '540', 1),
    ('Ceruleanspill Crystal Tear', "x1.14 Max FP",
     'Dropped by Blighted Avatar boss in Deeproot Depths, near the "Great Waterfall Crest" site of '
     'grace', '180', 1),

    ('Bloodsucking Cracked Tear',
     "x1.2 Damage dealt. 0.35%+35 HP drained per second.", None, '180', 0),
    ('Cerulean Hidden Tear',
     "x0.35 FP Cost of all actions (x0.7 when used alongside Viridian Hidden Tear).", None, '15', 0),
    ('Cerulean-Sapping Cracked Tear',
     "1%+1 Max FP restoration when landing a melee attack (2 second cooldown between activations).",
     None, '180', 0),
    ('Cerulean Crystal Tear', "50%+1 Max FP restoration.", None, '-', 0),
    ('Crimsonburst Crystal Tear', "0.75%+1 HP Regen every 2 seconds.", None, '180', 0),
    ('Crimsonburst Dried Tear', "0.75%+1 HP Regen for nearby allies every 2 seconds.", None, '180', 0),
    ('Crimson-Sapping Cracked Tear',
     "1%+1 Max HP restoration when landing a melee attack (2 second cooldown between activations).",
     None, '180', 0),
    ('Crimsonspill Crystal Tear', "x1.12 Max HP.", None, '180', 0),
    ('Crimsonwhorl Crystal Tear',
     "x0.01 Elemental Damage taken. 5% Max HP restoration when hit by an Elemental attack.",
     None, '15', 0),
    ('Crimson Bubbletear',
     "One-time 30% Max HP restoration when below 21% Max HP.", None, '180', 0),
    ('Crimson Crystal Tear', "50%+1 Max HP restoration.", None, '-', 0),
    ('Deflecting Hardtear',
     "When performing regular deflects: x0.9 Stamina Cost of blocking, x0.8 Damage taken, x0.8 "
     "Status Buildup taken.", None, '180', 0),
    ('Dexterity-knot Crystal Tear', "+8 Dexterity.", None, '540', 0),
    ('Faith-knot Crystal Tear', "+8 Faith.", None, '540', 0),
    ('Flame-Shrouding Cracked Tear', "x1.12 Fire Damage dealt.", None, '180', 0),
    ('Glovewort Crystal Tear', "x1.1 Damage dealt by Spirit Ashes.", None, '180', 0),
    ('Holy-Shrouding Cracked Tear', "x1.12 Holy Damage dealt.", None, '180', 0),
    ('Intelligence-knot Crystal Tear', "+8 Intelligence.", None, '540', 0),
    ('Leaden Hardtear',
     "+20 Poise. Stagger immunity to Push, Minimal, Small and Medium staggers.", None, '15', 0),
    ('Lightning-Shrouding Cracked Tear', "x1.12 Lightning Damage dealt.", None, '180', 0),
    ('Magic-Shrouding Cracked Tear', "x1.12 Magic Damage dealt.", None, '180', 0),
    ('Oil-Soaked Tear', "x1.2 Fire Damage taken by oil-soaked entities.", None, '180', 0),
    ('Opaline Bubbletear',
     "x0.05 Damage taken from next attack. +40 Poise until next attack.", None, '60', 0),
    ('Opaline Hardtear', "x0.9 Damage taken.", None, '180', 0),
    ('Purifying Crystal Tear', "Same effect as vanilla.", None, 'Forever', 0),
    ('Ruptured Crystal Tear',
     "The explosion of a single Tear deals 400 Holy Damage (scales with weapon level, up to x5 at "
     "max level), 180 Poise Damage, 3000 Stamina Damage, and 15% Max HP+500 damage to self. Range "
     "of explosion: 2.5 meters (5 with two Tears).", None, '-', 0),
    ('Speckled Hardtear',
     "+100 Status Resistance. x0.9 Status Buildup received. Cures all Status Buildup on use.",
     None, '180', 0),
    ('Spiked Cracked Tear', "x1.12 Attack Power of heavy attacks.", None, '180', 0),
    ('Stonebarb Cracked Tear', "x1.12 Poise Damage dealt.", None, '60', 0),
    ('Strength-knot Crystal Tear', "+8 Strength.", None, '540', 0),
    ('Thorny Cracked Tear',
     "Increases Damage with successive attacks - builds up as more attacks land and decays over "
     "time, divided into 4 tiers: x1.045 / x1.09 / x1.135 / x1.18.", None, '180', 0),
    ('Twiggy Cracked Tear',
     "Prevents rune loss upon death. Dying from Death Blight while active leaves all runes on the "
     "ground to be picked up. Effect shared with the Sacrificial Twig.", None, '180', 0),
    ('Viridianburst Crystal Tear',
     "New name of Greenburst Crystal Tear. +80 Stamina Regen.", None, '180', 0),
    ('Viridian Hidden Tear',
     "x0.65 Stamina Cost of melee attacks and spells (x0.825 when used alongside Cerulean Hidden "
     "Tear).", None, '30', 0),
    ('Viridianspill Crystal Tear',
     "New name of Greenspill Crystal Tear. x1.16 Max Stamina.", None, '180', 0),
    ('Windy Cracked Tear',
     "+2 I-Frame while dodging (only +1 for rolls if Crucible Feather Talisman is equipped, and "
     "for ducking/sliding if Fine Crucible Feather Talisman is equipped). x1.2 Damage taken. x1.18 "
     "travelled distance while dodging.", None, '180', 0),
    ('Winged Crystal Tear', "x1.2 Equip Load.", None, '180', 0),
]


def run():
    with engine.connect() as conn:
        inserted = 0
        for name, effect, location, duration, is_new in TEARS:
            conn.execute(text("DELETE FROM sl_err_crystal_tears WHERE name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_crystal_tears (name, effect, location, duration_sec, is_new_to_err, created_at)
                VALUES (:name, :eff, :loc, :dur, :new, :ts)
            """), {
                'name': name, 'eff': effect, 'loc': location, 'dur': duration,
                'new': is_new, 'ts': NOW,
            })
            inserted += 1
        conn.commit()
        print(f'{inserted} Crystal Tears seeded.')
        new_count = conn.execute(text(
            "SELECT COUNT(*) FROM sl_err_crystal_tears WHERE is_new_to_err=1"
        )).scalar()
        print(f'  {new_count} new to ERR, {inserted - new_count} changed/renamed vanilla.')


if __name__ == '__main__':
    run()
