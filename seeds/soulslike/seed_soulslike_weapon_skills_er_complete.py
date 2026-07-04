"""
Complete ER default weapon skill seeder.
Sources: Fextralife AoW page + wiki weapon pages.

Each weapon has one default AoW. Unique-skill weapons were already seeded.
This covers all remaining ER weapons with their swappable default AoW.

Run: chwebsiteprj/bin/python3 seed_soulslike_weapon_skills_er_complete.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# weapon_name -> default skill name
# Sourced from: wiki "Default skill on X" entries + Fextralife AoW compatibility list
# Only weapons where the skill is SWAPPABLE (not locked unique skills - those already seeded)
DEFAULTS = {
    # ── Axes ─────────────────────────────────────────────────────────────────
    'Hand Axe':                     'Wild Strikes',
    'Celebrant\'s Cleaver':         'Wild Strikes',
    'Iron Cleaver':                 'Wild Strikes',
    'Jawbone Axe':                  'Wild Strikes',
    'Messmer Soldier\'s Axe':       'Wild Strikes',
    'Ripple Blade':                 'Wild Strikes',
    'Rosus\' Axe':                  'Wild Strikes',
    'Sacrificial Axe':              'War Cry',
    'Smithscript Axe':              'Wild Strikes',
    'Stormhawk Axe':                'Wild Strikes',
    'Warped Axe':                   'Wild Strikes',
    'Icerind Hatchet':              'Hoarfrost Stomp',

    # ── Backhand Blades ───────────────────────────────────────────────────────
    'Backhand Blade':               'Blind Spot',
    'Smithscript Cirque':           'Blind Spot',

    # ── Ballistae ─────────────────────────────────────────────────────────────
    'Hand Ballista':                'No Skill',
    'Jar Cannon':                   'No Skill',
    'Rabbath\'s Cannon':            'No Skill',

    # ── Beast Claws ───────────────────────────────────────────────────────────
    'Beast Claw':                   'Raging Beast',

    # ── Bows ─────────────────────────────────────────────────────────────────
    'Albinauric Bow':               'Enchanted Shot',
    'Black Bow':                    'Barrage',
    'Erdtree Bow':                  'Mighty Shot',
    'Horn Bow':                     'Mighty Shot',
    'Longbow':                      'Mighty Shot',
    'Pulley Bow':                   'Sky Shot',
    'Serpent Bow':                  'Barrage',
    'Short Bow':                    'Mighty Shot',
    'Composite Bow':                'Mighty Shot',
    'Misbegotten Shortbow':         'Barrage',

    # ── Claws ─────────────────────────────────────────────────────────────────
    'Raptor Talons':                'Quickstep',
    'Claw':                         'Quickstep',
    'Venomous Fang':                'Quickstep',

    # ── Colossal Swords ──────────────────────────────────────────────────────
    'Greatsword':                   'Stamp (Upward Cut)',
    'Fire Knight\'s Greatsword':    'Stamp (Upward Cut)',
    'Troll Knight\'s Sword':        'Stamp (Upward Cut)',
    'Troll\'s Golden Sword':        'Stamp (Upward Cut)',
    'Watchdog\'s Greatsword':       'Barbaric Roar',

    # ── Colossal Weapons ─────────────────────────────────────────────────────
    'Giant-Crusher':                'Endure',
    'Duelist Greataxe':             'Earthshaker',
    'Rotten Greataxe':              'Earthshaker',
    'Bloodfiend\'s Arm':            'Barbaric Roar',
    'Envoy\'s Greathorn':           'Endure',
    'Fallingstar Beast Jaw':        'Gravity Bolt',
    'Rotten Staff':                 'Barbaric Roar',
    'Watchdog\'s Staff':            'Barbaric Roar',
    'Staff of the Avatar':          'Scarab Shrine',
    'Great Club':                   'Golden Land',
    'Pickaxe':                      'Cragblade',
    'Envoy\'s Long Horn':           'Bubble Shower',
    'Envoy\'s Horn':                'Bubble Shower',

    # ── Crossbows ─────────────────────────────────────────────────────────────
    'Arbalest':                     'No Skill',
    'Crepus\'s Black-Key Crossbow': 'No Skill',
    'Full Moon Crossbow':           'No Skill',
    'Heavy Crossbow':               'No Skill',
    'Light Crossbow':               'No Skill',
    'Soldier\'s Crossbow':          'No Skill',

    # ── Curved Greatswords ───────────────────────────────────────────────────
    'Magma Wyrm\'s Scalesword':     'Magma Guillotine',
    'Banished Knight\'s Greatsword': 'Spinning Slash',
    'Zamor Curved Sword':           'Zamor Ice Storm',
    'Omen Cleaver':                 'Spinning Slash',
    'Rotten Gravekeeper Cloak':     'Spinning Slash',
    'Gravekeeper Cloak':            'Spinning Slash',

    # ── Curved Swords ─────────────────────────────────────────────────────────
    'Scimitar':                     'Spinning Slash',
    'Shamshir':                     'Spinning Slash',
    'Flowing Curved Sword':         'Spinning Slash',
    'Grossmesser':                  'Spinning Slash',
    'Mantis Blade':                 'Quickstep',
    'Nox Flowing Sword':            'Flowing Form',
    'Shotel':                       'Spinning Slash',
    'Eclipse Shotel':               'Death Flare',
    'Beastman\'s Curved Sword':     'Wild Strikes',
    'Forked Hatchet':               'Quickstep',
    'Bandit\'s Curved Sword':       'Spinning Slash',
    'Trefoil Kite Shield':          'Shield Bash',
    'Monk\'s Flameblade':           'Spinning Slash',
    'Smithscript Sword':            'Spinning Slash',

    # ── Daggers ───────────────────────────────────────────────────────────────
    'Dagger':                       'Quickstep',
    'Black Knife':                  'Blade of Death',
    'Crystal Knife':                'Quickstep',
    'Glintstone Kris':              'Spearcall Ritual',
    'Great Knife':                  'Quickstep',
    'Ivory Sickle':                 'Quickstep',
    'Misericorde':                  'Quickstep',
    'Parrying Dagger':              'Parry',
    'Scorpion\'s Stinger':          'Repeating Thrust',
    'Wakizashi':                    'Quickstep',
    'Blade of Calling':             'Electrify Armament',
    'Smithscript Dagger':           'Quickstep',
    'Thrusting Shield':             'Shield Crash',

    # ── Fists ─────────────────────────────────────────────────────────────────
    'Caestus':                      'Quickstep',
    'Cipher Pata':                  'Unblockable Blade',
    'Clinging Bone':                'Lifesteal Fist',
    'Grafted Dragon':               'Bear Witness!',
    'Star Fist':                    'Endure',
    'Veteran\'s Prosthesis':        'Kickback',

    # ── Flails ────────────────────────────────────────────────────────────────
    'Flail':                        'Spinning Slash',
    'Nightrider Flail':             'Spinning Slash',
    'Family Heads':                 'Familial Rancor',
    'Bastard\'s Stars':             'Nebula',

    # ── Glintstone Staves ────────────────────────────────────────────────────
    'Academy Glintstone Staff':     'No Skill',
    'Albinauric Staff':             'No Skill',
    'Astrologer\'s Staff':          'No Skill',
    'Carian Glintblade Staff':      'Spinning Weapon',
    'Carian Regal Scepter':         'Spinning Weapon',
    'Crystal Staff':                'Spinning Weapon',
    'Digger\'s Staff':              'No Skill',
    'Glintstone Staff':             'No Skill',
    'Meteorite Staff':              'No Skill',
    'Prince of Death\'s Staff':     'Gravitational Missile',
    'Rotten Crystal Staff':         'Spinning Weapon',
    'Staff of Loss':                'No Skill',
    'Lusat\'s Glintstone Staff':    'Nothing',
    'Azur\'s Glintstone Staff':     'Nothing',
    'Gelmir Glintstone Staff':      'No Skill',
    'Maternal Staff':               'No Skill',
    'Demi-Human Queen\'s Staff':    'No Skill',
    'Carian Glintblade Staff':      'Spinning Weapon',
    'Staff of the Guilty':          'No Skill',

    # ── Greataxes ─────────────────────────────────────────────────────────────
    'Forked Greatsword':            'Spinning Slash',
    'Gargoyle\'s Black Axe':        'Spinning Slash',
    'Gargoyle\'s Greataxe':         'Spinning Slash',
    'Great Omenkiller Cleaver':     'Wild Strikes',
    'Greataxe':                     'Barbaric Roar',
    'Guillotine Axe':               'Wild Strikes',
    'Winged Greathorn':             'Wild Strikes',
    'Beastman\'s Cleaver':          'Wild Strikes',

    # ── Great Hammers ─────────────────────────────────────────────────────────
    'Brick Hammer':                 'Endure',
    'Club':                         'Barbaric Roar',
    'Great Club':                   'Golden Land',
    'Celebrant\'s Skull':           'Endure',
    'Envoy\'s Long Horn':           'Bubble Shower',
    'Erdtree Greatshield':          'Golden Retaliation',
    'Hammer':                       'Endure',
    'Large Club':                   'Barbaric Roar',
    'Marika\'s Hammer':             'Gold Breaker',
    'Nox Flowing Hammer':           'Flowing Form',
    'Omen Greatshield':             'Shield Crash',
    'One-Eyed Shield':              'Flame Spit',
    'Rusted Anchor':                'Endure',
    'Smithscript Hammer':           'Endure',
    'Stone Club':                   'Endure',
    'Varre\'s Bouquet':             'Endure',
    'Greathorn Hammer':             'Endure',

    # ── Halberds ─────────────────────────────────────────────────────────────
    'Banished Knight\'s Halberd':   'Spinning Strikes',
    'Gargoyle\'s Black Halberd':    'Spinning Slash',
    'Gargoyle\'s Halberd':          'Spinning Strikes',
    'Golden Halberd':               'Golden Vow',
    'Glaive':                       'Spinning Strikes',
    'Guardian\'s Swordspear':       'Spinning Slash',
    'Halberd':                      'Spinning Strikes',
    'Ripple Crescent Halberd':      'Spinning Strikes',
    'Sunset Crystal Blade':         'Spinning Strikes',
    'Death\'s Poker':               'Ghostflame Ignition',
    'Dragon Halberd':               'Spinning Strikes',
    'Golem\'s Halberd':             'Charge Forth',
    'Commander\'s Standard':        'Rallying Standard',

    # ── Hand-to-Hand Arts ────────────────────────────────────────────────────
    'Dryleaf Arts':                 'Dryleaf Whirlwind',
    'Dane\'s Footwork':             'Dryleaf Whirlwind',

    # ── Heavy Thrusting Swords ───────────────────────────────────────────────
    'Antspur Rapier':               'Impaling Thrust',
    'Bloody Helice':                'Dynastic Sickleplay',
    'Cleanrot Knight\'s Sword':     'Charge Forth',
    'Estoc':                        'Impaling Thrust',
    'Great Epee':                   'Impaling Thrust',
    'Golem Greatarrow':             'No Skill',
    'Golem Halberd':                'Spinning Strikes',
    'Regalia of Eochaid':           'Eochaid\'s Dancing Blade',

    # ── Katanas ───────────────────────────────────────────────────────────────
    'Dragonscale Blade':            'Ice Lightning Sword',
    'Hand of Malenia':              'Waterfowl Dance',
    'Nagakiba':                     'Unsheathe',
    'Serpentbone Blade':            'Double Slash',
    'Uchigatana':                   'Unsheathe',
    'Meteoric Ore Blade':           'Gravitas',
    'Pulley Katana':                'Unsheathe',

    # ── Light Bows ────────────────────────────────────────────────────────────
    'Composite Bow':                'Mighty Shot',
    'Harp Bow':                     'Enchanted Shot',
    'Misbegotten Shortbow':         'Barrage',
    'Short Bow':                    'Mighty Shot',

    # ── Light Greatswords ────────────────────────────────────────────────────
    'Leda\'s Sword':                'Needle Piercer',
    'Milady':                       'Wing Stance',
    'Sword Lance':                  'Spinning Gravity Thrust',
    'Verdugo\'s Sharpblade':        'Wing Stance',

    # ── Reapers ───────────────────────────────────────────────────────────────
    'Death\'s Poker':               'Ghostflame Ignition',
    'Grave Scythe':                 'Spinning Slash',
    'Halo Scythe':                  'Miquella\'s Ring of Light',
    'Scythe':                       'Spinning Slash',
    'Winged Scythe':                'Angel\'s Wings',

    # ── Sacred Seals ─────────────────────────────────────────────────────────
    'Clawmark Seal':                'No Skill',
    'Dragon Communion Seal':        'No Skill',
    'Erdtree Seal':                 'No Skill',
    'Finger Seal':                  'No Skill',
    'Frenzied Flame Seal':          'No Skill',
    'Giant\'s Seal':                'No Skill',
    'Godslayer\'s Seal':            'No Skill',
    'Golden Order Seal':            'No Skill',
    'Gravel Stone Seal':            'No Skill',
    'Two Fingers Heirloom':         'No Skill',
    'Pest\'s Glaive':               'Pest\'s Assault',
    'Horned Warrior\'s Staff':      'No Skill',

    # ── Shields (Small) ──────────────────────────────────────────────────────
    'Buckler':                      'Parry',
    'Carian Knight\'s Shield':      'Carian Retaliation',
    'Eclipse Crest Heater Shield':  'Shield Bash',
    'Heater Shield':                'Parry',
    'Man-Serpent\'s Shield':        'Parry',
    'Misericorde':                  'Quickstep',
    'Spiralhorn Shield':            'Parry',
    'Rift Shield':                  'Parry',
    'Rickety Shield':               'Parry',
    'Scripture Wooden Shield':      'Parry',
    'Large Leather Shield':         'Parry',
    'Scorpion Kite Shield':         'Parry',
    'Brass Shield':                 'Parry',
    'Riveted Wooden Shield':        'Parry',

    # ── Shields (Medium) ─────────────────────────────────────────────────────
    'Blue-Gold Kite Shield':        'Parry',
    'Blue Crest Heater Shield':     'Parry',
    'Brass Shield':                 'Parry',
    'Cuckoo Kite Shield':           'Shield Bash',
    'Gilded Iron Shield':           'Shield Bash',
    'Golden Beast Crest Shield':    'Shield Bash',
    'Iron Roundshield':             'Shield Bash',
    'Kite Shield':                  'Parry',
    'Marred Leather Shield':        'Parry',
    'Marred Wooden Shield':         'Parry',
    'Pillory Shield':               'Shield Bash',
    'Red Thorn Roundshield':        'Parry',
    'Rotten Duelist Greatshield':   'Barricade Shield',
    'Scorpion Kite Shield':         'Parry',
    'Shield of the Guilty':         'Parry',
    'Silver Mirrorshield':          'Parry',
    'Spiralhorn Shield':            'Parry',
    'Stone-Sheathed Sword':         'Parry',
    'Sunflower Shield':             'Parry',
    'Wooden Greatshield':           'Shield Crash',

    # ── Shields (Greatshields) ───────────────────────────────────────────────
    'Ant\'s Skull Plate':           'Shield Bash',
    'Banished Knight\'s Shield':    'Barricade Shield',
    'Coil Shield':                  'Viper Bite',
    'Distinguished Greatshield':    'Shield Crash',
    'Eclipse Crest Greatshield':    'Shield Crash',
    'Fingerprint Stone Shield':     'Barricade Shield',
    'Formless Eld Shield':          'Shield Crash',
    'Giant\'s Prayerbook':          'Shield Crash',
    'Haligtree Crest Greatshield':  'Shield Crash',
    'Icon Shield':                  'Shield Crash',
    'Jellyfish Shield':             'Contagious Fury',
    'Lordsworn\'s Shield':          'Shield Bash',
    'Omen Greatshield':             'Shield Crash',
    'One-Eyed Shield':              'Flame Spit',
    'Redmane Greatshield':          'Shield Crash',
    'Rogier\'s Rapier':             'Glintblade Phalanx',
    'Scavenger\'s Curved Sword':    'Spinning Slash',
    'Smoldering Shield':            'Shield Crash',
    'Stone Wall':                   'Shield Crash',
    'Two Fingers Heirloom':         'No Skill',
    'Visage Shield':                'Tongue of Fire',
    'Wooden Greatshield':           'Shield Crash',

    # ── Spears ────────────────────────────────────────────────────────────────
    'Celebrant\'s Rib-Rake':        'Impaling Thrust',
    'Clayman\'s Harpoon':           'Impaling Thrust',
    'Cleanrot Spear':               'Sacred Ring of Light',
    'Cross-Naginata':               'Impaling Thrust',
    'Crystal Spear':                'Impaling Thrust',
    'Death Ritual Spear':           'Spearcall Ritual',
    'Inferno Crozier':              'Prelate\'s Charge',
    'Inquisitor\'s Girandole':      'Impaling Thrust',
    'Partisan':                     'Impaling Thrust',
    'Pike':                         'Impaling Thrust',
    'Spiked Spear':                 'Impaling Thrust',
    'Short Spear':                  'Impaling Thrust',
    'Spear':                        'Impaling Thrust',
    'Torchpole':                    'Impaling Thrust',
    'Treespear':                    'Sacred Order',
    'Vyke\'s War Spear':            'Surge of Faith',
    'Winged Spear':                 'Impaling Thrust',
    'Rotten Crystal Spear':         'Impaling Thrust',
    'Serpent Spear':                'Impaling Thrust',
    'Crafted Frostpetal':           'Impaling Thrust',

    # ── Great Spears ──────────────────────────────────────────────────────────
    'Bloodfiend\'s Sacred Spear':   'Bloodfiends\' Bloodboon',
    'Commander\'s Standard':        'Rallying Standard',
    'Hoslow\'s Petal Whip':         'Surge of Faith',
    'Siluria\'s Tree':              'Siluria\'s Woe',
    'Torrent Furled Finger':        'Giant Hunt',
    'Lance':                        'Charge Forth',
    'Dragon Communion Seal':        'No Skill',

    # ── Straight Swords ───────────────────────────────────────────────────────
    'Broadsword':                   'Square Off',
    'Lordsworn\'s Straight Sword':  'Square Off',
    'Long Sword':                   'Square Off',
    'Longsword':                    'Square Off',
    'Nobleman\'s Slender Sword':    'Square Off',
    'Ornamental Straight Sword':    'Golden Tempering',
    'Regalia of Eochaid':           'Eochaid\'s Dancing Blade',
    'Rotten Crystal Sword':         'Square Off',
    'Warhawk\'s Talon':             'Double Slash',
    'Weathered Straight Sword':     'Square Off',
    'Iron Greatsword':              'Square Off',
    'Crystal Sword':                'Square Off',
    'Coded Sword':                  'Unblockable Blade',
    'Miquellan Knight\'s Sword':    'Sacred Blade',
    'Clayman\'s Harpoon':           'Impaling Thrust',

    # ── Thrusting Swords ─────────────────────────────────────────────────────
    'Estoc':                        'Impaling Thrust',
    'Glintstone Kris':              'Spearcall Ritual',
    'Noble\'s Slender Sword':       'Impaling Thrust',
    'Rogier\'s Rapier':             'Glintblade Phalanx',
    'Rapier':                       'Impaling Thrust',
    'Spiked Caestus':               'Impaling Thrust',
    'Stormhawk Axe':                'Wild Strikes',
    'Bloody Helice':                'Dynastic Sickleplay',
    'Serpentbone Blade':            'Double Slash',

    # ── Torches ───────────────────────────────────────────────────────────────
    'Beast-Repellent Torch':        'No Skill',
    'Ghostflame Torch':             'No Skill',
    'Lantern':                      'No Skill',
    'St. Trina\'s Torch':          'No Skill',
    'Sentry\'s Torch':             'No Skill',
    'Torch':                        'No Skill',

    # ── Twinblades ────────────────────────────────────────────────────────────
    'Eleonora\'s Poleblade':        'Bloodblade Dance',
    'Godskin Peeler':               'Black Flame Tornado',
    'Twinblade':                    'Spinning Slash',
    'Gargoyle\'s Twinblade':        'Spinning Slash',
    'Gargoyle\'s Black Blades':     'Spinning Slash',
    'Naginata':                     'Impaling Thrust',
    'Twinned Knight Swords':        'Spinning Slash',

    # ── Whips ─────────────────────────────────────────────────────────────────
    'Hoslow\'s Petal Whip':         'Surge of Faith',
    'Urumi':                        'Spinning Slash',
    'Whip':                         'No Skill',
    'Thorned Whip':                 'No Skill',
    'Magma Whip Candlestick':       'No Skill',

    # ── Great Katanas ─────────────────────────────────────────────────────────
    'Rakshasa\'s Great Katana':     'Weed Cutter',
    'Dragon Hunter\'s Great Katana': 'Dragonwound Slash',

    # ── Perfume Bottles ───────────────────────────────────────────────────────
    'Deadly Poison Perfume Bottle': 'Deadly Poison Spray',
    'Frenzyflame Perfume Bottle':   'Wall of Sparks',
    'Frostbite Perfume Bottle':     'Wall of Sparks',
    'Ironjar Aromatic':             'Rolling Sparks',
    'Lightning Perfume Bottle':     'Rolling Sparks',
    'Perfumer\'s Talisman':         'Rolling Sparks',

    # ── Throwing Blades ──────────────────────────────────────────────────────
    'Kukri':                        'Piercing Throw',
    'Smithscript Cirque':           'Scattershot Throw',

    # ── Greatbows ─────────────────────────────────────────────────────────────
    'Erdtree Greatbow':             'Through and Through',
    'Golem Greatbow':               'Through and Through',
    'Greatbow':                     'Through and Through',
    'Horn Greatbow':                'Through and Through',
    'Igon\'s Greatbow':             'Igon\'s Drake Hunt',
    'Jar Cannon':                   'No Skill',
    'Lion Greatbow':                'Through and Through',
    'Pulley Bow':                   'Sky Shot',
}


def run():
    with engine.begin() as conn:
        updated_er = 0
        updated_err = 0
        not_found = []

        for weapon_name, skill_name in DEFAULTS.items():
            r = conn.execute(text(
                "UPDATE sl_weapons SET special_ability=:s WHERE name=:n AND game='elden_ring' "
                "AND (special_ability IS NULL OR special_ability='')"
            ), {'s': skill_name, 'n': weapon_name})
            if r.rowcount:
                updated_er += r.rowcount
            else:
                # Check if it exists but already has a skill (unique, already seeded)
                exists = conn.execute(text("SELECT COUNT(*) FROM sl_weapons WHERE name=:n AND game='elden_ring'"), {'n': weapon_name}).fetchone()[0]
                if not exists:
                    not_found.append(weapon_name)

            # Same default applies to ERR (same base weapons)
            r2 = conn.execute(text(
                "UPDATE sl_weapons SET special_ability=:s WHERE name=:n AND game='err' "
                "AND (special_ability IS NULL OR special_ability='')"
            ), {'s': skill_name, 'n': weapon_name})
            updated_err += r2.rowcount

    print(f'Updated: {updated_er} ER, {updated_err} ERR weapons')
    if not_found:
        print(f'Not found in DB ({len(not_found)}):')
        for n in not_found[:20]: print(f'  {n}')


if __name__ == '__main__':
    run()
