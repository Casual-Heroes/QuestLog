"""
ERR-specific weapon default skill seeder.
Updates ERR weapons where the default skill differs from ER vanilla,
and seeds Mystic Ash defaults for ERR catalysts.

Source: ERR wiki AoW page (all 3 batches).
DO NOT update elden_ring entries - ERR only.

Run: chwebsiteprj/bin/python3 seed_soulslike_weapon_skills_err.py
"""
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# ERR Mystic Ash defaults for catalysts - these REPLACE the old "No Skill"/"Nothing" entries
# Source: ERR wiki Mystic Ashes section
ERR_CATALYST_SKILLS = {
    'Academy Glintstone Staff':  'Starlight',
    'Albinauric Staff':          'Night Maiden\'s Mist',
    'Azur\'s Glintstone Staff':  'Comet',
    'Carian Glintblade Staff':   'Glintblade Phalanx',
    'Clawmark Seal':             'Bestial Vitality',
    'Crystal Staff':             'Crystal Release',
    'Dark Glintstone Staff':     'Flashfrost Cutter',
    'Digger\'s Staff':           'Shatter Earth',
    'Dragon Communion Seal':     'Dragonmaw',
    'Erdtree Seal':              'Great Heal',
    'Fire Knight\'s Seal':       'Fire Serpent',
    'Frenzied Flame Seal':       'Howl of Shabriri',
    'Gelmir Glintstone Staff':   'Magma Shot',
    'Giant\'s Seal':             'Flame, Cleanse Me',
    'Godslayer\'s Seal':         'Catch Flame',
    'Golden Order Seal':         'Law of Regression',
    'Gravel Stone Seal':         'Lightning Spear',
    'Lusat\'s Glintstone Staff': 'Star Shower',
    'Maternal Staff':            'Cherishing Fingers',
    'Meteorite Staff':           'Collapsing Stars',
    'Prince of Death\'s Staff':  'Creeping Rancor',
    'Rotten Crystal Staff':      'Crystal Torrent',
    'Spiraltree Seal':           'Spira',
    'Staff of Loss':             'Night Shard',
    'Staff of the Great Beyond': 'Guiding Microcosm',
    'Staff of the Guilty':       'Briars of Punishment',
}

# ERR weapons whose default skill changed from ER vanilla
# Source: ERR wiki AoW page + unique skill list
ERR_SKILL_CHANGES = {
    # AoW affinity/skill changes that affect weapon defaults
    # Flails now get Spinning Chain (new ERR AoW)
    'Flail':              'Spinning Chain',
    'Nightrider Flail':   'Spinning Chain',
    'Chainlink Flail':    'Spinning Chain',
    'Family Heads':       'Familial Rancor',

    # ERR new unique skills for weapons
    'Coilheart':                 'Viper Stance',
    'Fury of Azash':             'Lion\'s Flame',
    'Flamelost War Sword':       'Flamelost Stance',
    'Flamelost War Spear':       'Flamelost Ignition',
    'Flamelost Greatblades':     'Flamelost Upheaval',
    'Mad Sun Shield':            'Flamelost Sweep',
    'Fellthorn Stake':           'Fell Flame Flare',
    'Fellthorn Clutches':        'Fell Flame Lariat',
    'Vulgar Militia Chain Sickle': 'Trapper\'s Step',
    'Immortal Coil':             'Empyrean Piercer',
    'Meteoric Ore Blade':        'Starsplitter Stance',
    'Red Wolf\'s Fang':          'Red Wolf\'s Gambol',
    'Putrescent Bonesmasher':    'Pulverize',
    'Troll\'s Hammer':           'Troll\'s Raging Roar',
    'Miquellan Knight\'s Sword': 'Miquella\'s Sacred Light',
    'Dragon Greatclaw':          'Dragon Smasher',
    'Dragonclaw Shield':         'Dragonbolt',
    'Suncatcher':                'Cursed Blade',
    'Dawnglow Greatbolt':        'Dawnblade',

    # ERR unique skills from batches 4-6 (weapons that differ from ER or are ERR-only)
    'Cinquedea':                 'Beast\'s Step',        # changed from Quickstep
    'Blade of Calling':          'Blade of Gold',        # changed from Electrify Armament
    'Cipher Pata':               'Unblockabled Piercing Blade',
    'Coded Sword':               'Unblockable Rending Blade',
    'Cranial Vessel Candlestand': 'Surge of Faith',
    'Dancing Blades of Ranah':   'Unending Dance',
    'Dark Moon Greatsword':      'Moonlight Greatsword',
    'Devourer\'s Scepter':       'Devourer of Worlds',
    'Dragon Halberd':            'Ice Lightning Slash',
    'Dragon King\'s Cragblade':  'Thundercloud Form',
    'Dragonscale Blade':         'Ice Lightning Sword',
    'Envoy\'s Greathorn':        'Great Oracular Bubble',
    'Envoy\'s Horn':             'Oracular Bubble',
    'Envoy\'s Long Horn':        'Bubble Shower',
    'Family Heads':              'Familial Rancor',
    'Giant\'s Red Braid':        'Flame Dance',
    'Ghiza\'s Wheel':            'Spinning Wheel',
    'Gladiator Greatsword':      'Square Off',
    'Godslayer\'s Greatsword':   'The Queen\'s Black Flame',
    'Golden Epitaph':            'Last Rites',
    'Golden Halberd':            'Prayerful Strike',     # changed from Golden Vow
    'Golden Order Greatsword':   'Establish Order',
    'Grafted Blade Greatsword':  'Oath of Vengeance',
    'Grafted Dragon':            'Bear Witness!',
    'Halo Scythe':               'Miquella\'s Rings of Light',
    'Hand of Malenia':           'Waterfowl Dance',
    'Helphen\'s Steeple':        'Ruinous Ghostflame',
    'Lion Greatbow':             'Radahn\'s Rain',
    'Loretta\'s War Sickle':     'Loretta\'s Enchanted Slash',
    'Magma Blade':               'Magma Shower',
    'Magma Whip Candlestick':    'Sea of Magma',
    'Magma Wyrm\'s Scalesword':  'Magma Guillotine',
    'Makar\'s Ceremonial Cleaver': 'Magma Guillotine',
    'Marais Executioner\'s Sword': 'Eochaid\'s Dancing Blade',
    'Mohgwyn\'s Sacred Spear':   'Bloodboon Ritual',
    'Moonveil':                  'Transient Moonlight',
    'Morgott\'s Cursed Sword':   'Cursed-Blood Slice',
    'Onyx Lord\'s Greatsword':   'Onyx Lord\'s Repulsion',
    'Ordovis\'s Greatsword':     'Ordovis\'s Vortex',
    'Ornamental Straight Sword': 'Golden Tempering',
    'Regalia of Eochaid':        'Eochaid\'s Dancing Blade',
    'Ringed Finger':             'Claw Flick',
    'Rivers of Blood':           'Corpse Piler',
    'Rosus\' Axe':               'Rosus\' Summons',
    'Rotten Staff':              'Erdtree Slam',
    'Sacred Relic Sword':        'Wave of Gold',
    'Scepter of the All-Knowing': 'Knowledge Above All',
    'Serpent Hunter':            'Great Serpent Hunt',
    'Siluria\'s Tree':           'Siluria\'s Woe',
    'Star-Lined Sword':          'Onze\'s Line of Stars',
    'Stormhawk Axe':             'Thunderstorm',
    'Sword of Milos':            'Shriek of Milos',
    'Sword of St. Trina':        'Mists of Slumber',
    'Staff of the Avatar':       'Erdtree Slam',
    'Steel-Wire Torch':          'Firebreather',
    'St. Trina\'s Torch':        'Fires of Slumber',
    'Veteran\'s Prosthesis':     'Storm Kick',
    'Watchdog\'s Staff':         'Sorcery of the Crozier',
    'Winged Greathorn':          'Soul Stifler',
    'Winged Scythe':             'Angel\'s Wings',
    'Wing of Astel':             'Nebula',
    'Zamor Curved Sword':        'Zamor Ice Storm',
    'Beastclaw Greathammer':     'Regal Beastclaw',
    'Axe of Godfrey':            'Regal Roar',
    'Cleanrot Spear':            'Sacred Phalanx',
    'Commander\'s Standard':     'Rallying Standard',

    # ERR Gracebound weapons (new ERR weapons) - default skills
    'Gracebound Greatsword':     'Square Off',
    'Gracebound Cane Sword':     'Square Off',
    'Gracebound Katana':         'Unsheathe',
    'Gracebound Mace':           'Endure',
    'Gracebound Halberd':        'Spinning Strikes',
    'Gracebound Claws':          'Quickstep',
    'Gracebound Greataxe':       'Earthshaker',
    'Gracebound Round Shield':   'Parry',
    'Gracebound Greatshield':    'Shield Crash',
    'Gracebound Staff':          'No Skill',
    'Gracebound Longbow':        'Fan Shot',
    'Gracebound Dagger':         'Quickstep',

    # Other ERR new weapons
    'Ambassador\'s Cudgel':      'Endure',
    'Ambassador\'s Greatsword':  'Square Off',
    'Ambassador\'s Towershield': 'Shield Crash',
    'Avionette Pig Sticker':     'Impaling Thrust',
    'Avionette Scimitars':       'Spinning Slash',
    'Broken Straight Sword':     'Square Off',
    'Crystal Ringblade':         'Spinning Slash',
    'Rotten Crystal Ringblade':  'Spinning Slash',
    'Crude Iron Claws':          'Quickstep',
    'Goldvine Branchstaff':      'No Skill',
    'Gladius of Ophidion':       'Quickstep',
    'Grave Spear':               'Impaling Thrust',
    'Iron Spike':                'Endure',
    'Lordsworn\'s Spear':        'Impaling Thrust',
    'Makar\'s Ceremonial Cleaver': 'Wild Strikes',
    'Marionette Short Sword':    'Square Off',
    'Mohgwyn\'s Sacred Seal':    'No Skill',
    'Night\'s Edge':             'Spinning Slash',
    'Nox Flowing Fist':          'Quickstep',
    'Pumpkin Sledge':            'Endure',
    'Starcaller Spire':          'No Skill',
    'Twinbird Caduceus':         'No Skill',
    'Snow Witch Scepter':        'No Skill',
    'Scepter of Serenity':       'No Skill',
    'Sun Realm Sword':           'Square Off',
    'Disciple\'s Rotten Branch': 'No Skill',
    'Dawnglow Greatbolt':        'Dawnblade',
}


def run():
    with engine.begin() as conn:
        updated_catalysts = 0
        updated_changes = 0
        not_found = []

        # Update ERR catalysts with Mystic Ash defaults (overwrite existing)
        for name, skill in ERR_CATALYST_SKILLS.items():
            r = conn.execute(text(
                "UPDATE sl_weapons SET special_ability=:s WHERE name=:n AND game='err'"
            ), {'s': skill, 'n': name})
            if r.rowcount:
                updated_catalysts += r.rowcount
            else:
                not_found.append(f'catalyst: {name}')

        # Update ERR weapons with changed/new skills (only if not already a unique skill)
        for name, skill in ERR_SKILL_CHANGES.items():
            r = conn.execute(text(
                "UPDATE sl_weapons SET special_ability=:s WHERE name=:n AND game='err'"
            ), {'s': skill, 'n': name})
            if r.rowcount:
                updated_changes += r.rowcount
            else:
                not_found.append(f'weapon: {name}')

    print(f'Updated {updated_catalysts} ERR catalysts, {updated_changes} ERR weapon changes')
    if not_found:
        print(f'Not found ({len(not_found)}):')
        for n in not_found[:20]: print(f'  {n}')


if __name__ == '__main__':
    run()
