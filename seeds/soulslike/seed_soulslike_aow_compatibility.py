"""
Seed compatible_weapon_types for ER AoW table.
Source: Fextralife AoW page + ER wiki.

Format: comma-separated weapon type names matching sl_weapons.weapon_type values.
Special values: ALL = works on all melee, ALL_MELEE = same, SHIELDS = shields only.

Run: chwebsiteprj/bin/python3 seed_soulslike_aow_compatibility.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# AoW name -> compatible weapon types string
# Using the EXACT weapon type values from sl_weapons.weapon_type
# Special tokens used in filtering:
#   ALL_MELEE = all melee weapons
#   ALL = literally everything including catalysts/shields
#   NO_SMALL = excludes small weapons (daggers, small swords)
#   NO_COLOSSAL = excludes colossal weapons
AOW_COMPAT = {
    # Standard / no affinity
    'Mighty Shot':              'Bow,Light Bow',
    'Barrage':                  'Light Bow',
    'Sky Shot':                 'Bow,Light Bow',
    'Enchanted Shot':           'Bow,Light Bow',
    'Through and Through':      'Greatbow',
    'Rain of Arrows':           'Bow,Light Bow,Greatbow',
    "Igon's Drake Hunt":        'Greatbow',
    'Parry':                    'Dagger,Curved Sword,Thrusting Sword,Fist,Claw,Small Shield,Medium Shield',
    'Storm Wall':               'Small Shield,Medium Shield',
    'Shield Bash':              'Small Shield,Medium Shield,Greatshield',
    'Shield Crash':             'Small Shield,Medium Shield,Greatshield',
    'Barricade Shield':         'Small Shield,Medium Shield,Greatshield',
    'Shield Strike':            'Small Shield,Medium Shield,Greatshield',
    'No Skill':                 'Small Shield,Medium Shield,Greatshield,Torch',
    'Dryleaf Whirlwind':        'Hand-to-Hand Art',
    'Palm Blast':               'Hand-to-Hand Art,Fist,Claw',
    'Rolling Sparks':           'Perfume Bottle',
    'Wall of Sparks':           'Perfume Bottle',
    'Piercing Throw':           'Throwing Blade',
    'Scattershot Throw':        'Throwing Blade',
    'Raging Beast':             'Beast Claw',
    'Savage Claws':             'Beast Claw',
    'Blind Spot':               'Backhand Blade',
    'Swift Slash':              'Backhand Blade',
    'Overhead Stance':          'Great Katana',
    'Wing Stance':              'Light Greatsword,Thrusting Sword',
    'Aspects of the Crucible: Wings': 'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Light Greatsword,Great Katana,Spear,Great Spear,Halberd',

    # Heavy affinity
    'Stamp (Upward Cut)':       'Straight Sword,Greatsword,Colossal Sword,Axe,Greataxe,Hammer,Great Hammer,Colossal Weapon',
    'Stamp (Sweep)':            'Straight Sword,Greatsword,Colossal Sword,Axe,Greataxe,Hammer,Great Hammer,Colossal Weapon',
    'Wild Strikes':             'Axe,Greataxe,Hammer,Great Hammer,Curved Sword,Greatsword',
    "Lion's Claw":              'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Hammer,Great Hammer,Spear,Great Spear,Halberd',
    'Savage Lion\'s Claw':      'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Hammer,Great Hammer,Spear,Great Spear,Halberd',
    'Cragblade':                'Dagger,Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Light Greatsword,Great Katana,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Fist,Claw,Beast Claw,Backhand Blade,Throwing Blade',
    'Earthshaker':              'Greataxe,Great Hammer,Colossal Weapon,Great Spear',
    'Spinning Gravity Thrust':  'Greatsword,Colossal Sword',
    'War Cry':                  'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Fist,Claw,Beast Claw,Backhand Blade,Light Greatsword,Great Katana,Colossal Weapon',
    'Barbaric Roar':            'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Fist,Claw,Beast Claw,Backhand Blade,Light Greatsword,Great Katana,Colossal Weapon',
    "Braggart's Roar":          'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Fist,Claw,Beast Claw,Backhand Blade,Light Greatsword,Great Katana,Colossal Weapon',
    "Troll's Roar":             'Greatsword,Colossal Sword,Axe,Greataxe,Hammer,Great Hammer,Colossal Weapon',
    'Hoarah Loux\'s Earthshaker': 'Fist,Claw,Beast Claw,Backhand Blade,Dagger,Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Light Greatsword,Great Katana,Colossal Weapon',
    'Ground Slam':              'ALL_MELEE',
    'Endure':                   'ALL_MELEE',
    'Kick':                     'ALL_MELEE',
    "Lord's Stomp":             'ALL',

    # Keen affinity
    'Spinning Slash':           'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Spear,Great Spear,Halberd,Light Greatsword,Great Katana',
    'Impaling Thrust':          'Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd,Twinblade',
    'Piercing Fang':            'Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd',
    'Repeating Thrust':         'Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd,Twinblade',
    'Double Slash':             'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Spear,Great Spear,Halberd,Light Greatsword,Great Katana',
    'Sword Dance':              'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Spear,Great Spear,Halberd,Light Greatsword,Great Katana',
    'Unsheathe':                'Katana',
    'Spinning Chain':           'Flail',
    'Quickstep':                'ALL_MELEE',
    "Bloodhound's Step":        'ALL_MELEE',
    'Raptor of the Mists':      'ALL_MELEE',
    "Beast's Roar":             'ALL_MELEE',
    'Overhead Stance':          'Great Katana',
    'Piercing Throw':           'Throwing Blade',
    'Scattershot Throw':        'Throwing Blade',
    'Raging Beast':             'Beast Claw',
    'Savage Claws':             'Beast Claw',
    'Blind Spot':               'Backhand Blade',
    'Swift Slash':              'Backhand Blade',

    # Quality affinity
    'Square Off':               'Straight Sword,Greatsword',
    'Charge Forth':             'Thrusting Sword,Heavy Thrusting Sword,Twinblade,Spear,Great Spear,Halberd',
    'Giant Hunt':               'Spear,Great Spear,Halberd,Twinblade,Greatsword,Colossal Sword,Colossal Weapon',
    'Storm Blade':              'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Thrusting Sword,Heavy Thrusting Sword,Axe,Greataxe,Spear,Great Spear,Halberd,Reaper,Light Greatsword,Great Katana',
    'Storm Assault':            'Thrusting Sword,Heavy Thrusting Sword,Twinblade,Spear,Great Spear,Halberd',
    'Stormcaller':              'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Axe,Greataxe,Hammer,Great Hammer,Spear,Great Spear,Halberd,Light Greatsword,Great Katana',
    'Spinning Strikes':         'Spear,Great Spear,Halberd,Twinblade',
    'Phantom Slash':            'Spear,Great Spear,Halberd,Twinblade',
    'Vacuum Slice':             'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Axe,Light Greatsword,Great Katana',
    'Wing Stance':              'Light Greatsword,Thrusting Sword',
    'Storm Stomp':              'ALL_MELEE',
    'Determination':            'ALL_MELEE',
    "Royal Knight's Resolve":   'ALL_MELEE',

    # Magic affinity
    'Glintstone Pebble':        'Straight Sword,Greatsword,Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd,Glintstone Staff',
    'Glintblade Phalanx':       'Straight Sword,Greatsword,Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd,Glintstone Staff',
    'Carian Greatsword':        'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Spear,Great Spear,Halberd,Light Greatsword,Great Katana,Glintstone Staff',
    'Carian Grandeur':          'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Spear,Great Spear,Halberd,Light Greatsword,Great Katana',
    'Carian Sovereignty':       'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Spear,Great Spear,Halberd,Light Greatsword,Great Katana',
    'Spinning Weapon':          'Straight Sword,Greatsword,Axe,Greataxe,Hammer,Great Hammer,Spear,Great Spear,Halberd,Glintstone Staff',
    "Loretta's Slash":          'Spear,Great Spear,Halberd,Twinblade',
    'Gravitas':                 'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Light Greatsword,Great Katana,Colossal Weapon,Colossal Sword,Glintstone Staff',
    'Waves of Darkness':        'Greataxe,Great Hammer,Great Spear,Colossal Weapon',
    "Thops's Barrier":          'Small Shield,Medium Shield',
    'Carian Retaliation':       'Small Shield,Medium Shield',

    # Fire affinity
    'Flaming Strike':           'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Fist,Claw,Beast Claw,Backhand Blade,Dagger,Light Greatsword,Great Katana',
    'Eruption':                 'Greatsword,Colossal Sword,Axe,Greataxe,Hammer,Great Hammer,Heavy Thrusting Sword,Colossal Weapon',
    'Flame of the Redmanes':    'ALL_MELEE',

    # Flame Art affinity
    "Prelate's Charge":         'Greataxe,Great Hammer,Colossal Weapon',
    'Black Flame Tornado':      'Spear,Great Spear,Halberd,Twinblade',
    'Flame Skewer':             'Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd',
    'Flame Spear':              'Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd',

    # Lightning affinity
    'Lightning Slash':          'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Axe,Greataxe,Hammer,Great Hammer,Light Greatsword,Great Katana',
    'Blinkbolt':                'ALL_MELEE',
    'Lightning Ram':            'ALL_MELEE',
    'Thunderbolt':              'ALL_MELEE',

    # Sacred affinity
    'Sacred Blade':             'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Light Greatsword,Great Katana,Colossal Weapon',
    'Prayerful Strike':         'Axe,Greataxe,Hammer,Great Hammer',
    'Sacred Ring of Light':     'Spear,Great Spear,Halberd,Sacred Seal',
    'Sacred Order':             'ALL_MELEE',
    'Shared Order':             'ALL_MELEE',
    'Golden Land':              'Greataxe,Great Hammer,Great Spear,Colossal Weapon',
    'Golden Slam':              'ALL_MELEE',
    'Golden Vow':               'ALL_MELEE',
    'Golden Parry':             'Small Shield,Medium Shield',
    'Vow of the Indomitable':   'Small Shield,Medium Shield,Greatshield',
    'Holy Ground':              'Small Shield,Medium Shield,Greatshield',
    'Aspects of the Crucible: Wings': 'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Light Greatsword,Great Katana,Spear,Great Spear,Halberd',

    # Poison affinity
    'Poisonous Mist':           'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Light Greatsword,Great Katana,Colossal Weapon',
    'Poison Moth Flight':       'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Thrusting Sword,Heavy Thrusting Sword,Light Greatsword,Great Katana',

    # Blood affinity
    'Bloody Slash':             'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Axe,Greataxe,Spear,Great Spear,Halberd,Light Greatsword,Great Katana',
    'Blood Blade':              'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Thrusting Sword,Light Greatsword,Great Katana',
    'Blood Tax':                'Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd',
    'Seppuku':                  'Straight Sword,Greatsword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Spear,Great Spear,Halberd,Light Greatsword,Great Katana',

    # Cold affinity
    'Chilling Mist':            'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Twinblade,Thrusting Sword,Heavy Thrusting Sword,Axe,Greataxe,Hammer,Great Hammer,Flail,Spear,Great Spear,Halberd,Reaper,Light Greatsword,Great Katana,Colossal Weapon',
    'Ice Spear':                'Spear,Great Spear,Halberd,Twinblade,Glintstone Staff',
    'Hoarfrost Stomp':          'ALL_MELEE',
    'Ghostflame Call':          'Straight Sword,Greatsword,Colossal Sword,Curved Sword,Curved Greatsword,Katana,Spear,Great Spear,Halberd,Glintstone Staff',
    'Divine Beast Frost Stomp': 'ALL_MELEE',

    # Occult affinity
    'Spectral Lance':           'Spear,Great Spear,Halberd,Twinblade',
    'Lifesteal Fist':           'Fist,Claw,Beast Claw,Backhand Blade',
    "White Shadow's Lure":      'ALL_MELEE',
    "Assassin's Gambit":        'Straight Sword,Thrusting Sword',
    'Shriek of Sorrow':         'ALL_MELEE',
    'The Poison Flower Blooms Twice': 'ALL_MELEE',
    "The Rotten Flower Blooms Twice": 'ALL_MELEE',
}


def run():
    with engine.begin() as conn:
        updated = 0
        not_found = []
        for name, compat in AOW_COMPAT.items():
            # Strip "Ash of War: " prefix variations if present in DB
            r = conn.execute(text(
                "UPDATE sl_ashes_of_war SET compatible_weapon_types=:c WHERE game='elden_ring' AND name=:n"
            ), {'c': compat, 'n': name})
            if r.rowcount:
                updated += r.rowcount
            else:
                # Try with "Ash of War: " prefix
                r2 = conn.execute(text(
                    "UPDATE sl_ashes_of_war SET compatible_weapon_types=:c WHERE game='elden_ring' AND name=:n"
                ), {'c': compat, 'n': f'Ash of War: {name}'})
                if r2.rowcount:
                    updated += r2.rowcount
                else:
                    not_found.append(name)

        print(f'Updated {updated} ER AoW compatibility entries')
        if not_found:
            print(f'Not found ({len(not_found)}):')
            for n in not_found[:20]: print(f'  {n}')


if __name__ == '__main__':
    run()
