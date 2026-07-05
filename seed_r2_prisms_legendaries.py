"""
Seed r2_prisms and r2_legendary_bonuses from Fextralife data.
Run: chwebsiteprj/bin/python3 seed_r2_prisms_legendaries.py
"""
import django, os, re, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

NOW = int(time.time())

def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

# 7 Prisms - all DLC3
PRISMS = [
    ('Prism of Lethargy',  'Buy from Dwell in Ward 13 for 1,000 Relic Dust.'),
    ('Prism of Greed',     'Occasionally sold by Cass for 250,000 Scrap.'),
    ('Prism of Voracity',  'Defeat any World Boss.'),
    ('Prism of Jealousy',  'Craft at Wallace using 3 Prismatic Stones + 1 Simulacrum. Prismatic Stones found by charged shovel attack in specific locations.'),
    ('Prism of Hatred',    'Complete 50 Boss Rush runs.'),
    ('Prism of Passion',   'Complete 200 Boss Rush runs.'),
    ('Prism of Pride',     'Complete 500 Boss Rush runs.'),
]

# 42 Legendary Bonuses
LEGENDARIES = [
    ('Allegiance',       'Cannot Kill or Be Killed by Friendly Fire Damage.'),
    ('Altruistic',       'Lifesteal applies 50% of Stolen Health to Allies.'),
    ('Artful Dodger',    'All Dodges trigger Perfect Dodge Mechanics. Cooldown of 3 seconds.'),
    ('Bodyguard',        'Cannot be One-Shot while at Max Health Capacity.'),
    ('Boundless Energy', 'Grants Infinite N\'Erudian Energy.'),
    ('Brutality',        'All Damage Dealt and Received is increased by 100%.'),
    ('Critical Situation','Grants 35% All Critical Chance within the LIGHT Weight Class.'),
    ('Dark Omen',        'Dodges become Mist Step, costing Health instead of Stamina.'),
    ('Defense Measures', 'Increases SHIELD Maximum by 100%.'),
    ('Exhausted',        'Increases Heat Decay Rate by 250%.'),
    ('Fleet Footed',     'Increases Dodge Weight Threshold by 100.'),
    ('Full Hearted',     'Increases Relic Charges by 100%.'),
    ('Gigantic',         'Grants 50 Health and Stamina.'),
    ('God Tear',         'Reduces Cheat Death Cooldowns by 50%.'),
    ('Heavy Drinker',    'Increases Concoction Limit by 5.'),
    ('Hyperactive',      'Increases HASTE Effectiveness by 100%.'),
    ('Immovable',        'Cannot be Staggered while BULWARK is active.'),
    ('Impervious',       'Reduces All Incoming Damage by 30%.'),
    ('Insult to Injury', 'Applying any Negative Status Effect applies EXPOSED.'),
    ('Jack of all Trades','Increases All Damage by 40%.'),
    ('Luck of the Devil','Grants EXTREME Luck.'),
    ('Master Killer',    'Multiplies Weakspot Damage by 1.35x.'),
    ('Outlaw',           'Reloading Reloads both Weapons.'),
    ('Overpowered',      'Increases Mod Generation by 50%.'),
    ('Peak Conditioning','Grants Infinite Stamina.'),
    ('Physician',        'Increases Healing Effectiveness by 100%.'),
    ('Power Fantasy',    'Increases Explosive Critical Chance and Critical Damage by 30%.'),
    ('Power Trip',       'Doubles Mod Charges.'),
    ('Prime Time',       'Enables Prime Perk for Secondary Archetype.'),
    ('Reverberation',    'Increases Stamina Recovery by 200 per second.'),
    ('Sadistic',         'Status Effect Damage has a 50% chance to deal 2x more damage per tick.'),
    ('Sharpshooter',     'Increases Ranged Damage by 60%.'),
    ('Size Matters',     'Doubles Magazine Size for non Single Shot Weapons.'),
    ('Soulmate',         'Increases Summon Limit by 1.'),
    ('Spectrum',         'Gain Bonuses Based on Color of Fragments within the Prism.'),
    ('Speed Demon',      'Grants Maximum Movement Speed Bonuses.'),
    ('Steel Plating',    'Increases Armor by 150.'),
    ('Traitor',          'Maxes out Core Traits Vigor, Endurance, Spirit and Expertise.'),
    ('Unbreakable',      'Grey Health cannot be removed.'),
    ('Unbridled',        'Reduces all Skill Cooldowns by Half.'),
    ('Vaccinated',       'Immune to Negative Status Effects.'),
    ('Wrecking Ball',    'Increases Explosive Critical Chance by 100%.'),
]

def main():
    with get_db_session() as db:
        # Prisms
        existing = db.execute(text('SELECT COUNT(*) FROM r2_prisms')).scalar()
        if existing:
            print(f'Prisms already seeded ({existing}). Skipping.')
        else:
            for (name, how) in PRISMS:
                db.execute(text('''
                    INSERT INTO r2_prisms (slug, name, how_to_get, dlc, created_at)
                    VALUES (:slug, :name, :how, 'dlc3', :now)
                '''), {'slug': slugify(name), 'name': name, 'how': how, 'now': NOW})
            db.commit()
            print(f'Seeded {len(PRISMS)} prisms')

        # Legendary Bonuses
        existing = db.execute(text('SELECT COUNT(*) FROM r2_legendary_bonuses')).scalar()
        if existing:
            print(f'Legendary bonuses already seeded ({existing}). Skipping.')
        else:
            for (name, desc) in LEGENDARIES:
                db.execute(text('''
                    INSERT INTO r2_legendary_bonuses (slug, name, description, created_at)
                    VALUES (:slug, :name, :desc, :now)
                '''), {'slug': slugify(name), 'name': name, 'desc': desc, 'now': NOW})
            db.commit()
            print(f'Seeded {len(LEGENDARIES)} legendary bonuses')

        print(f'\nFinal: {db.execute(text("SELECT COUNT(*) FROM r2_prisms")).scalar()} prisms, '
              f'{db.execute(text("SELECT COUNT(*) FROM r2_legendary_bonuses")).scalar()} legendaries')

if __name__ == '__main__':
    main()
