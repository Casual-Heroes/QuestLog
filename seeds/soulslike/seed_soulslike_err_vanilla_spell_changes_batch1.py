"""
Seed: ERR Vanilla Spell Changes batch 1 - all sorcery changes + partial incantation changes
(Bestial, Blood Oath, Dragon Communion, Dragon Cult up to Vyke's Dragonbolt).
Source: err.fandom.com/wiki/Vanilla_Spell_Changes, pasted directly by user.

General rules (not stored per-spell): All spells received general rebalancing. Many have
increased animation speed, improved hitboxes, and projectile tracking - small differences
not listed. Status-inflicting spells now inflict small self-buildup to discourage spam.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_vanilla_spell_changes_batch1.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# General system note - stored as a special row
SYSTEM_NOTE = (
    "All spells received general rebalancing. Many feature increased animation speed, improved "
    "hitboxes, and projectile tracking - small differences not listed. Status-inflicting spells now "
    "inflict a small amount of self-buildup to discourage spamming and encourage use of status "
    "resisting items and armors. Carian sword sorceries and Carian Glintblade sorceries have been "
    "merged into one category. All Finger sorceries now have Arcane requirements. All standard Dragon "
    "Communion breath spells: drastically improved consistency with number of hits and hitboxes "
    "(now always hit twice uncharged, four times charged), greatly increased animation speed, "
    "decreased initial FP cost by 10%."
)

# (spell_name, spell_type, school, change_text)
CHANGES = [
    # Sorceries - Carian
    ('Carian Phalanx', 'Sorcery', 'Carian',
     "Grants 341 FP restoration over 20 seconds. Recasting refreshes the buff."),
    ('Carian Retaliation', 'Sorcery', 'Carian',
     "Glintblade damage increases at 20, 40, 60, and 80 Intelligence."),
    ('Carian Slicer', 'Sorcery', 'Carian',
     "This spell is now a generator. Royal House Scroll position swapped with Academy Scroll."),
    ('Glintblade Phalanx', 'Sorcery', 'Carian',
     "Grants 242 FP restoration over 20 seconds. Recasting refreshes the buff. Royal House Scroll "
     "position swapped with Academy Scroll."),
    ('Greatblade Phalanx', 'Sorcery', 'Carian',
     "Grants 275 FP restoration over 20 seconds. Recasting refreshes the buff."),
    ("Loretta's Greatbow", 'Sorcery', 'Carian', "Now considered a Carian sorcery."),
    ("Loretta's Mastery", 'Sorcery', 'Carian', "Now considered a Carian sorcery."),
    ('Lucidity', 'Sorcery', 'Carian',
     "In addition to vanilla effect, grants a buff for 20 seconds: x0.9 FP Cost of sorceries, "
     "+100 Concentration."),
    ('Magic Downpour', 'Sorcery', 'Carian',
     "Increased number of projectiles and projectile tracking. Projectiles now pierce targets. "
     "Now considered a Carian sorcery."),
    ("Miriam's Vanishing", 'Sorcery', 'Carian',
     "Greatly increased cast speed for easier use as a dodge. Light attacks upon exiting the spell "
     "perform a duck attack."),

    # Sorceries - Claymen
    ('Great Oracular Bubble', 'Sorcery', 'Claymen',
     "Charging increases projectile tracking. Bubble lowers enemy damage output for a moderate "
     "duration (unverified). Increased poise damage and explosion size."),
    ('Oracle Bubbles', 'Sorcery', 'Claymen',
     "Charging increases number of bubbles and projectile tracking. Bubbles lower enemy damage "
     "output for a short duration (unverified)."),

    # Sorceries - Cold
    ('Freezing Mist', 'Sorcery', 'Cold',
     "Added small amount of damage to draw enemy aggro and prevent stealth boss kills. Increased "
     "frost buildup speed when charged."),
    ('Frozen Armament', 'Sorcery', 'Cold',
     "Deals 100 Frostbite buildup on the player. Adds 25 Frostbite buildup and 1.0125x+12 Magic "
     "Attack Power to right-hand armament; x0.8 Frostbite buildup taken while blocking with "
     "weapon. Flat buff affected by 100% of catalyst Intelligence scaling. Lasts 80 seconds."),

    # Sorceries - Crystalian
    ('Crystal Release', 'Sorcery', 'Crystalian',
     "Increased number of projectiles and damage tick rate. Added large main explosion on initial "
     "release (single tick of high damage and poise damage). Channeling grants a 2-second buff: "
     "x0.7 Damage taken, +40 Poise."),
    ('Shattering Crystal', 'Sorcery', 'Crystalian',
     "Staggers enemies for longer. Reduced close-range effectiveness, increased long-range "
     "effectiveness."),

    # Sorceries - Death
    ('Ancient Death Rancor', 'Sorcery', 'Death',
     "Added Frostbite buildup. Charging increases number of projectiles and projectile velocity."),
    ('Explosive Ghostflame', 'Sorcery', 'Death',
     "Increased lingering fire duration and damage tick speed."),
    ("Fia's Mist", 'Sorcery', 'Death',
     "Added small amount of damage to draw aggro. Increased Death Blight buildup speed when "
     "charged."),
    ('Mass of Putrescence', 'Sorcery', 'Death',
     "Added Sleep buildup. Requirements: 14 Int / 7 Fai / 28 Arc."),
    ('Rancorcall', 'Sorcery', 'Death',
     "Added Frostbite buildup. Charging increases number of projectiles and projectile velocity."),
    ("Tibia's Summons", 'Sorcery', 'Death',
     "Summoned skeletons now deal Slash damage instead of Magic - the only Slash damage Sorcery."),
    ('Vortex of Putrescence', 'Sorcery', 'Death',
     "Added Sleep buildup. Requirements: 12 Int / 6 Fai / 24 Arc."),

    # Sorceries - Finger
    ('Cherishing Fingers', 'Sorcery', 'Finger',
     "Hitting at least one enemy restores 6%+60 HP (9%+90 if charged). All Finger sorceries now "
     "have Arcane requirements."),
    ('Fleeting Microcosm', 'Sorcery', 'Finger',
     "Charged version conjures two additional microcosms behind the player."),

    # Sorceries - Full Moon
    ("Ranni's Dark Moon", 'Sorcery', 'Full Moon',
     "Added i-frames during player-invisible portions. Debuff lasts 30 seconds and causes target "
     "to take x1.1 Magic Damage."),
    ("Rellana's Twin Moons", 'Sorcery', 'Full Moon',
     "Added i-frames during player-invisible portions. Now also part of the Carian sorcery "
     "category."),
    ("Rennala's Full Moon", 'Sorcery', 'Full Moon',
     "Added i-frames during player-invisible portions. Debuff lasts 60 seconds and causes target "
     "to take x1.1 Magic Damage. Now also part of the Carian sorcery category."),

    # Sorceries - Glintstone
    ('Crystal Barrage', 'Sorcery', 'Glintstone',
     "Added small stagger to hits. Improved consistency by decreasing bullet spread. Decreased FP "
     "cost of channeling."),
    ('Crystal Burst', 'Sorcery', 'Glintstone',
     "Decreased spread; charged variant has increased spread and more projectiles."),
    ('Gavel of Haima', 'Sorcery', 'Glintstone', "Shockwave now knocks enemies away on hit."),
    ('Glintstone Pebble', 'Sorcery', 'Glintstone',
     "This spell is now a generator."),
    ('Glintstone Stars', 'Sorcery', 'Glintstone',
     "Charged variant gains increased tracking. Each successive hit does more damage."),
    ('Great Glintstone Shard', 'Sorcery', 'Glintstone',
     "Added a weakening effect that makes targets take x1.1 Magic Damage for 6 seconds. Academy "
     "Scroll position swapped with Royal House Scroll."),
    ('Rock Blaster', 'Sorcery', 'Glintstone', "Now knocks enemies away on hit."),
    ("Scholar's Armament", 'Sorcery', 'Glintstone',
     "Adds 1.025x+25 Magic Attack Power to right-hand armament; x0.8 Magic Damage taken while "
     "blocking with weapon. Melee attacks restore additional FP (exact % unverified). Flat buff "
     "affected by 100% of catalyst Intelligence scaling. Lasts 80 seconds."),
    ("Scholar's Shield", 'Sorcery', 'Glintstone',
     "x0.5 Physical Damage taken when guarding (was x0.7). x0.75 Magic/Fire/Lightning/Holy Damage "
     "taken when guarding (was x0.3 for Magic, x0.7 for others). x0.8 Stamina Cost of blocks (was "
     "x0.65). Lasts 50 seconds."),
    ('Shard Spiral', 'Sorcery', 'Glintstone', "Now penetrates enemy guard."),
    ('Shatter Earth', 'Sorcery', 'Glintstone', "Now knocks enemies away on hit."),
    ('Starlight', 'Sorcery', 'Glintstone',
     "Now grants increased FP regeneration for 60 seconds after cast (to refund cast cost - not a "
     "sustained FP regen spell). Base: 3 FP/second. Intelligence thresholds: 20=3 FP/0.95s, "
     "40=3 FP/0.9s, 60=3 FP/0.85s, 80=3 FP/0.8s. Also increases target priority by 0.1."),
    ('Star Shower', 'Sorcery', 'Glintstone',
     "Charged variant gains increased tracking. Each successive hit does more damage."),
    ('Swift Glintstone Shard', 'Sorcery', 'Glintstone',
     "Added a weakening effect making targets more vulnerable to Magic damage for a short time "
     "(exact value unverified). Academy Scroll position swapped with Royal House Scroll."),
    ('Terra Magica', 'Sorcery', 'Glintstone',
     "Increased sigil duration from 30 to 90 seconds, but lowered damage multiplier from x1.35 to "
     "x1.15. Up to three sigils can now be placed at once; their effects do not stack."),
    ("Thop's Barrier", 'Sorcery', 'Glintstone',
     "Increased effect duration and size. Greatly increases Cast Speed for a short duration after "
     "casting."),

    # Sorceries - Gravity
    ('Blades of Stone', 'Sorcery', 'Gravity',
     "Now deals a mix of Lightning and Pierce damage."),
    ('Collapsing Stars', 'Sorcery', 'Gravity',
     "Increased level of stagger. Charging increases number of projectiles. Now deals True damage "
     "instead of Magic."),
    ('Gravitational Missile', 'Sorcery', 'Gravity',
     "Now deals Lightning damage instead of Magic."),
    ('Gravity Well', 'Sorcery', 'Gravity',
     "Increased level of stagger. Increased projectile speed and tracking. Now deals True damage "
     "instead of Magic."),
    ('Meteorite', 'Sorcery', 'Gravity',
     "Now fires a single homing meteorite. Meteorites damage targets at a consistent rate. Now "
     "deals a mix of Lightning and Strike damage."),
    ('Meteorite of Astel', 'Sorcery', 'Gravity',
     "Now fires three homing meteorites. Meteorites damage targets at a consistent rate. Now deals "
     "a mix of Lightning and Strike damage."),
    ('Rock Sling', 'Sorcery', 'Gravity',
     "Now deals a mix of Lightning and Strike damage."),

    # Sorceries - Magma
    ("Gelmir's Fury", 'Sorcery', 'Magma',
     "Increased number of projectiles. Increased magma pool duration and damage tick speed. Added "
     "slight Frostbite buildup decrease on cast."),
    ('Magma Shot', 'Sorcery', 'Magma',
     "Charging now increases magma pool duration. Added slight Frostbite buildup decrease on cast."),
    ('Roiling Magma', 'Sorcery', 'Magma',
     "Charging now increases magma pool duration. Added slight Frostbite buildup decrease on cast."),
    ("Rykard's Rancor", 'Sorcery', 'Magma',
     "Greatly increased projectile duration and homing angle. Added slight Frostbite buildup "
     "decrease on cast."),

    # Sorceries - Night
    ('Ambush Shard', 'Sorcery', 'Night', "This spell is now a generator."),
    ('Eternal Darkness', 'Sorcery', 'Night',
     "Increased size and duration of the absorbing projectile. Slows down enemies in the vicinity "
     "(unverified)."),
    ("Night Maiden's Mist", 'Sorcery', 'Night',
     "Decreased percentage and flat damage, but increased the damage that scales with the "
     "catalyst's Spell Boost."),
    ('Unseen Blade', 'Sorcery', 'Night',
     "Also obscures weapon trails and visual hit attributes. Adds 1.02x+20 Physical Attack Power "
     "to right-hand armament; flat buff affected by 100% of catalyst Intelligence scaling. "
     "-0.1 Target Priority. x0.8 Physical Damage taken while blocking with weapon. Lasts 80 "
     "seconds."),
    ('Unseen Form', 'Sorcery', 'Night',
     "Increased duration to 60 seconds (from 30). Slightly decreased enemy sight reduction to "
     "x0.65 (from x0.4). -0.3 Target Priority. x1.10 Attack Power of critical attacks. x1.12 "
     "Damage of Night sorceries. x0.85 True Damage taken."),

    # Sorceries - Primeval
    ('Founding Rain of Stars', 'Sorcery', 'Primeval',
     "Increased duration to 17 seconds uncharged, 20 seconds charged. Enemies remaining in the "
     "rain suffer decreased elemental negation, up to -10% if they stay for 10 seconds."),
    ('Stars of Ruin', 'Sorcery', 'Primeval',
     "Charged variant gains increased tracking. Each successive hit does more damage."),

    # Sorceries - Thorn
    ('Briars of Punishment', 'Sorcery', 'Thorn',
     "Relocated from a corpse in the Mountaintops of the Giants to a second caster Guilty in "
     "Liurnia, in the lake near the southern Thief-Taker Encampment."),
    ('Mantle of Thorns', 'Sorcery', 'Thorn',
     "Added a physical damage negation increase (unverified) to the effect. Doubled the duration. "
     "Roll damage now scales with Faith."),

    # Incantations - Bestial
    ('Beast Claw', 'Incantation', 'Bestial', "Now deals Slash damage."),
    ('Bestial Sling', 'Incantation', 'Bestial', "This spell is now a generator."),
    ('Bestial Vitality', 'Incantation', 'Bestial',
     "Now also restores a small amount of Stamina over time (unverified), in addition to HP."),
    ('Stone of Gurranq', 'Incantation', 'Bestial', "Now deals Strike damage."),

    # Incantations - Blood Oath
    ('Bloodflame Blade', 'Incantation', 'Blood Oath',
     "Applies 6 Blood Loss buildup on caster every 0.11 seconds over 1 second (60 total). "
     "Right-hand armament applies 8 Blood Loss buildup on hit targets every 0.45 seconds over 2 "
     "seconds (40 total); duration resets when reapplied. Also adds 1.015x+15 Fire Attack Power; "
     "flat buff affected by 100% of catalyst Faith scaling. x0.8 Blood Loss buildup taken while "
     "blocking with weapon. Lasts 80 seconds."),

    # Incantations - Dragon Communion (general change stored, no specific per-spell changes listed)

    # Incantations - Dragon Cult
    ("Ancient Dragon's Lightning Strike", 'Incantation', 'Dragon Cult',
     "Lightning from above ignores guards."),
    ('Dragonbolt Blessing', 'Incantation', 'Dragon Cult',
     "Increased duration from 70 to 90 seconds. Increased Status Resistance from +30 to +100. "
     "Replaced attack deflection effect with x1.42 Poise buff. Reduced Lightning Damage increase "
     "from x1.35 to x1.1. Adds stagger resistance to small stagger animations/weak hits. Can now "
     "stack with other body buffs."),
    ('Electrify Armament', 'Incantation', 'Dragon Cult',
     "Adds 1.025x+17 Lightning Attack Power to right-hand armament; flat buff affected by 100% of "
     "catalyst Faith and Dexterity scaling. x0.8 Lightning Damage taken while blocking with "
     "weapon. x0.94 Stamina Cost of attacks. Lasts 80 seconds."),
    ('Electrocharge', 'Incantation', 'Dragon Cult',
     "Lasts 40 seconds. +40 Stamina Regen. Lingering AoE damage now scales with Dexterity "
     "(breakpoints at 20, 40, 60, and 80 Dexterity)."),
    ('Frozen Lightning Spear', 'Incantation', 'Dragon Cult',
     "Now does 180 Frostbite buildup on initial hit (up from 90), and 60 on followup hits (down "
     "from 90)."),
    ("Fortissax's Lightning Spear", 'Incantation', 'Dragon Cult',
     "Increased cast and recovery speed. Greatly increased hitbox size."),
    ('Honed Bolt', 'Incantation', 'Dragon Cult', "This spell is now a generator."),
    ("Knight's Lightning Spear", 'Incantation', 'Dragon Cult',
     "Added Death Blight effects and buildup."),
    ('Lightning Spear', 'Incantation', 'Dragon Cult',
     "Charging increases projectile velocity."),
    ('Lightning Strike', 'Incantation', 'Dragon Cult',
     "Lightning from above ignores guards."),
    ("Vyke's Dragonbolt", 'Incantation', 'Dragon Cult',
     "80 seconds duration. Adds 1.025x+25 Lightning Attack Power to right-hand armament; attack "
     "power buff affected by 100% of catalyst Faith scaling. x1.15 Equip Load. x1.1 Lightning "
     "Damage taken."),
]


def run():
    with engine.connect() as conn:
        # System note
        conn.execute(text(
            "DELETE FROM sl_err_vanilla_spell_changes WHERE spell_name='__SYSTEM__'"
        ))
        conn.execute(text("""
            INSERT INTO sl_err_vanilla_spell_changes (spell_name, spell_type, school, change_text)
            VALUES ('__SYSTEM__', 'System', 'General', :note)
        """), {'note': SYSTEM_NOTE})

        updated = 0
        for name, stype, school, change in CHANGES:
            conn.execute(text(
                "DELETE FROM sl_err_vanilla_spell_changes WHERE spell_name=:name"
            ), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_vanilla_spell_changes (spell_name, spell_type, school, change_text)
                VALUES (:name, :type, :school, :change)
            """), {'name': name, 'type': stype, 'school': school, 'change': change})
            updated += 1
        conn.commit()
        print(f'{updated} vanilla spell changes seeded (batch 1: all Sorceries + Bestial/Blood Oath/'
              f'Dragon Cult incantations).')


if __name__ == '__main__':
    run()
