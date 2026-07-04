"""
Seed: ERR Vanilla Spell Changes batch 2 - remaining incantation changes
(Erdtree, Frenzied Flame, Giants' Flame, Godskin, Golden Order, Messmer's Flame,
Servants of Rot, Spiral, Two Fingers).
Source: err.fandom.com/wiki/Vanilla_Spell_Changes, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_vanilla_spell_changes_batch2.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

CHANGES = [
    # Erdtree
    ('Aspects of the Crucible: Bloom', 'Incantation', 'Erdtree',
     "Fixed bugs related to hit registration of the beams that would cause them to fail to hit "
     "enemies."),
    ('Barrier of Gold', 'Incantation', 'Erdtree',
     "Slightly decreased duration and effectiveness (unverified). Duration is increased by 1.5x on "
     "allies."),
    ('Golden Lightning Fortification', 'Incantation', 'Erdtree',
     "Slightly decreased duration and effectiveness (unverified). Duration is increased by 1.5x on "
     "allies."),
    ('Protection of the Erdtree', 'Incantation', 'Erdtree',
     "Slightly decreased duration and effectiveness (unverified). Duration is increased by 1.5x on "
     "allies."),
    ('Black Blade', 'Incantation', 'Erdtree',
     "Greatly increased cast speed. Added minimum poise during certain parts of the cast animation."),
    ("Blessing's Boon", 'Incantation', 'Erdtree',
     "Made healing equal between caster and allies (reduction on caster, increase on allies). "
     "Increased duration on allies (unverified)."),
    ('Blessing of the Erdtree', 'Incantation', 'Erdtree',
     "Made healing equal between caster and allies. Increased duration on allies (unverified)."),
    ('Elden Stars', 'Incantation', 'Erdtree',
     "Increased duration of the main Elden Stars projectile (unverified)."),
    ('Erdtree Heal', 'Incantation', 'Erdtree',
     "Made healing equal between caster and allies (reduction on caster, increase on allies)."),
    ('Golden Vow', 'Incantation', 'Erdtree',
     "50 seconds duration (75 on allies). x0.9 All Damage taken. x1.1 All Damage dealt."),
    ('Heal from Afar', 'Incantation', 'Erdtree',
     "Projectile now affected by gravity; aim deadzone removed. Made healing equal between caster "
     "and allies."),
    ('Minor Erdtree', 'Incantation', 'Erdtree', "Massively increased the healing radius."),

    # Frenzied Flame
    ('Flame of Frenzy', 'Incantation', 'Frenzied Flame',
     "Increased damage and consistency when charged (unverified)."),
    ('Frenzied Burst', 'Incantation', 'Frenzied Flame',
     "Charging greatly increases projectile velocity and adds piercing."),
    ('Howl of Shabriri', 'Incantation', 'Frenzied Flame',
     "Duration: 40 seconds -> 30 seconds. Damage dealt: +25% -> +20%. Damage received: +30% -> "
     "+35%."),
    ('Inescapable Frenzy', 'Incantation', 'Frenzied Flame',
     "Now works on regular enemies. Will only grab enemies when held in the left hand; uses the "
     "Lifesteal Fist animations."),
    ("Midra's Flame of Frenzy", 'Incantation', 'Frenzied Flame',
     "Decreased initial FP cost from 500 to 300."),

    # Giants' Flame
    ('Catch Flame', 'Incantation', "Giants' Flame",
     "This spell is now a generator. Now also considered a Giants' Flame incantation."),
    ("Fire's Deadly Sin", 'Incantation', "Giants' Flame",
     "Lasts 20 seconds (40 when charged). Now stacks with any other buffs. Increases in "
     "effectiveness at 20, 40, 60, and 80 Faith."),
    ('Flame, Cleanse Me', 'Incantation', "Giants' Flame",
     "Significantly increased self-damage (10% HP). Now also removes all stains and swamp buildup "
     "like Soap. Grants +100 Immunity for 60 seconds."),
    ('Flame, Grant Me Strength', 'Incantation', "Giants' Flame",
     "Increased duration from 30 to 40 seconds. x1.12 Physical and Fire Damage. +40 Stamina "
     "Regen."),
    ('Flame of the Fell God', 'Incantation', "Giants' Flame",
     "Fixed an issue where the explosion would not penetrate characters or objects, meaning it "
     "could only hit one target."),
    ('Flame, Protect Me', 'Incantation', "Giants' Flame",
     "x0.6 Fire Damage taken for 50 seconds."),
    ('Flame Sling', 'Incantation', "Giants' Flame",
     "Now considered a Giants' Flame incantation."),
    ('O, Flame!', 'Incantation', "Giants' Flame", "Massively increased hitbox size."),
    ('Surge, O Flame!', 'Incantation', "Giants' Flame",
     "Each tick causes the target to take x1.02 Fire Damage for 5 seconds, stacking. Effect "
     "removed if spell casting stops."),

    # Godskin
    ('Black Flame Blade', 'Incantation', 'Godskin',
     "Increased duration from 7 to 10 seconds. Adds 1.02x+20 Fire Attack Power alongside the "
     "Black Flame DoT effect; buff affected by 100% of catalyst Faith scaling. (General Godskin "
     "change: Black Flame DoT adjusted to scale with enemy strength - less effective vs powerful "
     "bosses, significantly more effective vs weaker enemies.)"),
    ('Scouring Black Flame', 'Incantation', 'Godskin',
     "Drastically improved hitbox and angle, making it much less likely to fire into the ground or "
     "fail to hit enemies."),

    # Golden Order
    ('Discus of Light', 'Incantation', 'Golden Order',
     "Projectile now stops on enemy contact and continues spinning stationary (larger hitbox when "
     "stationary). Now immediately available to purchase from Corhyn."),
    ('Immutable Shield', 'Incantation', 'Golden Order',
     "Increases elemental damage negation by +50%. Increases True Damage negation by +50% (does "
     "not increase Strike/Pierce/Slash negation). Reduces guarding stamina consumption by 35%."),
    ('Law of Causality', 'Incantation', 'Golden Order',
     "Increased the duration between hits before count expires from 7 to 10 seconds."),
    ("Order's Blade", 'Incantation', 'Golden Order',
     "Adds 1.025x+17 Holy Attack Power; flat buff affected by 100% of catalyst Intelligence and "
     "Faith scaling. x0.8 Holy Damage taken while blocking with weapon. x1.05 Damage dealt "
     "against Undead enemies. Lasts 80 seconds."),
    ('Order Healing', 'Incantation', 'Golden Order',
     "In addition to alleviating Death Blight buildup, now also increases Vitality by 100 for 60 "
     "seconds and heals a small amount of HP."),
    ('Triple Rings of Light', 'Incantation', 'Golden Order',
     "Projectiles now stop on enemy contact and continue spinning stationary (larger hitbox when "
     "stationary)."),

    # Messmer's Flame
    ('Rain of Fire', 'Incantation', "Messmer's Flame",
     "Now tracks enemies when cast while locked on. Casting while unlocked creates a stationary "
     "rain of fire."),

    # Servants of Rot
    ('Pest Threads', 'Incantation', 'Servants of Rot', "Added Scarlet Rot buildup."),
    ('Pest-Thread Spears', 'Incantation', 'Servants of Rot', "Added Scarlet Rot buildup."),
    ('Poison Armament', 'Incantation', 'Servants of Rot',
     "Deals 100 Poison buildup on the player. Adds 25 Poison buildup and 1.008x+8 Physical Attack "
     "Power to right-hand armament; x0.8 Poison buildup taken while blocking. Flat buff affected "
     "by catalyst Faith spell scaling only. Lasts 80 seconds."),
    ('Poison Mist', 'Incantation', 'Servants of Rot',
     "Added small amount of damage to draw aggro. Slightly increased duration."),
    ('Scarlet Aeonia', 'Incantation', 'Servants of Rot',
     "Increased animation speed and added a poise multiplier during parts of the casting "
     "animation."),

    # Spiral
    ('Watchful Spirits', 'Incantation', 'Spiral',
     "The main skull now has a small hitbox that staggers weak enemies who get close to the "
     "player."),

    # Two Fingers
    ("Assassin's Approach", 'Incantation', 'Two Fingers',
     "Increased duration from 20 to 30 seconds; now casts faster while crouched. Decreases target "
     "priority by 0.1. Increases critical damage while active (unverified). Prevents landing "
     "animation from high falls."),
    ('Cure Poison', 'Incantation', 'Two Fingers',
     "Adds 50 Immunity for a moderate duration."),
    ('Darkness', 'Incantation', 'Two Fingers',
     "Increased cloud and debuff duration (unverified). Now properly conceals the player from "
     "enemy sight when the player is inside the cloud (previously required enemies to be inside "
     "the cloud)."),
    ('Divine Fortification', 'Incantation', 'Two Fingers',
     "Increased duration but decreased effectiveness (unverified)."),
    ('Flame Fortification', 'Incantation', 'Two Fingers',
     "Increased duration but decreased effectiveness (unverified)."),
    ('Lightning Fortification', 'Incantation', 'Two Fingers',
     "Increased duration but decreased effectiveness (unverified)."),
    ('Magic Fortification', 'Incantation', 'Two Fingers',
     "Increased duration but decreased effectiveness (unverified)."),
    ('Heal', 'Incantation', 'Two Fingers',
     "Made healing equal between caster and allies (reduction on caster, increase on allies)."),
    ('Great Heal', 'Incantation', 'Two Fingers',
     "Made healing equal between caster and allies."),
    ("Lord's Heal", 'Incantation', 'Two Fingers',
     "Made healing equal between caster and allies."),
    ('Urgent Heal', 'Incantation', 'Two Fingers',
     "Made healing equal between caster and allies."),
    ("Lord's Aid", 'Incantation', 'Two Fingers',
     "Adds 50 Immunity, Robustness, and Concentration for 60 seconds. Duration is doubled on "
     "allies."),
    ("Lord's Divine Fortification", 'Incantation', 'Two Fingers',
     "Duration is increased by 1.5x on allies."),
    ('Rejection', 'Incantation', 'Two Fingers',
     "Greatly increases Cast Speed for a short duration after casting (unverified)."),
]


def run():
    with engine.connect() as conn:
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
        print(f'{updated} vanilla spell changes seeded (batch 2: Erdtree-Two Fingers incantations - FINAL).')
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_vanilla_spell_changes")).scalar()
        print(f'Total vanilla spell change entries: {total}')


if __name__ == '__main__':
    run()
