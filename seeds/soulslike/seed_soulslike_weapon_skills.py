"""
Seed default weapon skills into sl_weapons.special_ability
Source: Elden Ring wiki skill table + ERR wiki unique skills list.

Unique skills = the weapon has a locked skill that cannot be changed.
Regular skills = the weapon comes with this AoW by default but it CAN be replaced.

Both ER and ERR share the same base weapon set. ERR unique skill weapons
are identified separately via sl_weapon_ar_data affinity count.

Run: chwebsiteprj/bin/python3 seed_soulslike_weapon_skills.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# weapon_name -> (skill_name, is_unique)
# is_unique=True  = locked skill, cannot replace with AoW
# is_unique=False = default AoW, player can swap it
WEAPON_SKILLS = {
    # ── Unique skills (cannot be changed) ────────────────────────────────────
    'Ruins Greatsword':                 ('Wave of Destruction', True),
    'Royal Greatsword':                 ('Wolf\'s Assault', True),
    'Starscourge Greatsword':           ('Starcaller Cry', True),
    'Grafted Blade Greatsword':         ('Oath of Vengeance', True),
    'Maliketh\'s Black Blade':          ('Destined Death', True),
    'Blasphemous Blade':                ('Taker\'s Flames', True),
    'Godslayer\'s Greatsword':          ('Queen\'s Black Flame', True),
    'Sacred Relic Sword':               ('Wave of Gold', True),
    'Greatsword of Radahn (Lord)':      ('Promised Consort', True),
    'Greatsword of Radahn (Light)':     ('Lightspeed Slash', True),
    'Greatsword of Damnation':          ('Golden Crux', True),
    'Greatsword of Solitude':           ('Solitary Moon Slash', True),
    'Watchdog\'s Greatsword':           ('Barbaric Roar', True),
    'Gargoyle\'s Greatsword':           ('Vacuum Slice', True),
    'Gargoyle\'s Black Greatsword':     ('Vacuum Slice', True),
    'Carian Knight\'s Sword':           ('Carian Grandeur', True),
    'Sword of Night and Flame':         ('Night-and-Flame Stance', True),
    'Sword of Night':                   ('Witching Hour Slash', True),
    'Sword of Light':                   ('Light', True),
    'Sword of Darkness':                ('Darkness', True),
    'Star-Lined Sword':                 ('Onze\'s Line of Stars', True),
    'Leda\'s Sword':                    ('Needle Piercer', True),
    'Miquellan Knight\'s Sword':        ('Sacred Blade', True),
    'Inseparable Sword':                ('Sacred Blade', True),
    'Rellana\'s Twinblade':             ('Moon-and-Fire Stance', True),
    'Euporia':                          ('Euporia Vortex', True),
    'Moonveil':                         ('Transient Moonlight', True),
    'Meteoric Ore Blade':               ('Gravitas', True),
    'Ancient Meteoric Ore Greatsword':  ('White Light Charge', True),
    'Obsidian Lamina':                  ('Dynastic Sickleplay', True),
    'Falx':                             ('Revenger\'s Blade', True),
    'Dancing Blade of Ranah':           ('Unending Dance', True),
    'Curseblade\'s Cirque':             ('Deadly Dance', True),
    'Claws of Night':                   ('Scattershot (Claws)', True),
    'Red Bear\'s Claw':                 ('Red Bear Hunt', True),
    'Poisoned Hand':                    ('Poison Spear-Hand Strike', True),
    'Madding Hand':                     ('Madding Spear-Hand Strike', True),
    'Dryleaf Arts':                     ('Dryleaf Whirlwind', True),
    'Death Knight\'s Twin Axes':        ('Blinkbolt: Twinaxe', True),
    'Death Knight\'s Longhaft Axe':     ('Blinkbolt: Long-hafted Axe', True),
    'Axe of Godfrey':                   ('I Command Thee, Kneel!', True),
    'Axe of Godrick':                   ('I Command Thee, Kneel!', True),
    'Devonia\'s Hammer':                ('Devonia\'s Vortex', True),
    'Flowerstone Gavel':                ('Flower Dragonbolt', True),
    'Anvil Hammer':                     ('Smithing Art Spears', True),
    'Tooth Whip':                       ('Painful Strike', True),
    'Serpent Flail':                    ('Flare, O Serpent', True),
    'Spear of the Impaler':             ('Messmer\'s Assault', True),
    'Barbed Staff-Spear':               ('Jori\'s Inquisition', True),
    'Bloodfiend\'s Sacred Spear':       ('Bloodfiends\' Bloodboon', True),
    'Spirit Glaive':                    ('Rancor Slash', True),
    'Spirit Sword':                     ('Rancor Slash', True),
    'Poleblade of the Bud':             ('Romina\'s Purification', True),
    'Rakshasa\'s Great Katana':         ('Weed Cutter', True),
    'Dragon Hunter\'s Great Katana':    ('Dragonwound Slash', True),
    'Shadow Sunflower Blossom':         ('Shadow Sunflower Headbutt', True),
    'Gazing Finger':                    ('Kowtower\'s Resentment', True),
    'Lamenting Visage':                 ('Blindfold of Happiness', True),
    'Horned Warrior\'s Sword':          ('Horn Calling', True),
    'Horned Warrior\'s Greatsword':     ('Horn Calling: Storm', True),
    'Moonrithyll\'s Knights Sword':     ('Tremendous Phalanx', True),
    'Verdigris Greatshield':            ('Moore\'s Charge', True),
    'Golden Lion Shield':               ('Roaring Bash', True),
    'Shield of Night':                  ('Revenge of the Night', True),
    'Smithscript Shield':               ('Discus Hurl', True),
    'Ansbach\'s Longbow':               ('Fan Shot', True),
    'Bone Bow':                         ('Rancor Shot', True),
    'Repeating Crossbow':               ('Repeating Fire', True),
    'Nanaya\'s Torch':                  ('Feeble Lord\'s Frenzied Flame', True),
    'Velvet Sword of St Trina':         ('Mists of Eternal Sleep', True),
    'Putrescence Cleaver':              ('Spinning Guillotine', True),
    'Thiollier\'s Hidden Needle':       ('Sleep Evermore', True),
    'Forked-Tongue Hatchet':            ('Dragonform Flame', True),
    'Deadly Poison Perfume Bottle':     ('Deadly Poison Spray', True),
    'Bonny Butchering Knife':           ('Hone Blade', True),
    'Bloodhound\'s Fang':              ('Bloodhound\'s Finesse', True),
    'Sword of Milos':                   ('Shriek of Milos', True),
    'Magma Wyrm\'s Scalesword':        ('Magma Guillotine', True),
    'Marika\'s Hammer':                 ('Gold Breaker', True),
    'Bolt of Gransax':                  ('Ancient Lightning Spear', True),
    'Dragon King\'s Cragblade':         ('Thundercloud Form', True),
    'Vyke\'s War Spear':                ('Surge of Faith', True),
    'Mohgwyn\'s Sacred Spear':          ('Bloodboon Ritual', True),
    'Morgott\'s Cursed Sword':          ('Cursed-Blood Slice', True),
    'Loretta\'s War Sickle':            ('Loretta\'s Slash', True),
    'Winged Scythe':                    ('Angel\'s Wings', True),
    'Eclipse Shotel':                   ('Death Flare', True),
    'Rivers of Blood':                  ('Corpse Piler', True),
    'Marais Executioner\'s Sword':      ('Eochaid\'s Dancing Blade', True),
    'Eleonora\'s Poleblade':            ('Bloodblade Dance', True),
    'Godskin Peeler':                   ('Black Flame Tornado', True),
    'Godskin Stitcher':                 ('Taker\'s Flames', True),
    'Ghiza\'s Wheel':                   ('Spinning Wheel', True),
    'Nox Flowing Sword':                ('Flowing Form', True),
    'Nox Flowing Hammer':               ('Flowing Form', True),
    'Cinquedea':                        ('Quickstep', True),
    'Reduvia':                          ('Reduvia Blood Blade', True),
    'Hookclaws':                        ('Quickstep', True),
    'Venomous Fang':                    ('Quickstep', True),
    'Bloodhound Claws':                 ('Bloodhound\'s Step', True),
    'Carian Glintstone Staff':          ('Spinning Weapon', True),
    'Carian Regal Scepter':             ('Spinning Weapon', True),
    'Rotten Crystal Staff':             ('Spinning Weapon', True),
    'Staff of the Avatar':              ('Scarab Shrine', True),
    'Crystal Staff':                    ('Spinning Weapon', True),
    'Lusat\'s Glintstone Staff':        ('Nothing', True),
    'Azur\'s Glintstone Staff':         ('Nothing', True),
    'Prince of Death\'s Staff':         ('Gravitational Missile', True),
    'Graven-Mass Talisman':             ('Nothing', True),
    'Dragon Communion Seal':            ('Nothing', True),
    'Frenzied Flame Seal':              ('Nothing', True),
    'Giant\'s Seal':                    ('Nothing', True),
    'Godslayer\'s Seal':                ('Nothing', True),
    'Golden Order Seal':                ('Nothing', True),
    'Gravel Stone Seal':                ('Nothing', True),
    'Erdtree Seal':                     ('Nothing', True),
    'Clawmark Seal':                    ('Nothing', True),
    'Fingerprint Stone Shield':         ('Barricade Shield', True),
    'Ant\'s Skull Plate':               ('Shield Bash', True),
    'Eclipse Crest Greatshield':        ('Shield Crash', True),
    'One-Eyed Shield':                  ('Flame Spit', True),
    'Coil Shield':                      ('Viper Bite', True),
    'Jellyfish Shield':                 ('Contagious Fury', True),
    # ── Default AoW (can be replaced) ────────────────────────────────────────
    'Zweihänder':                       ('Stamp (Upward Cut)', False),
    'Zweihander':                       ('Stamp (Upward Cut)', False),
    'Claymore':                         ('Lion\'s Claw', False),
    'Battle Axe':                       ('Wild Strikes', False),
    'Highland Axe':                     ('War Cry', False),
    'Club':                             ('Barbaric Roar', False),
    'Battle Hammer':                    ('Braggart\'s Roar', False),
    'Troll\'s Hammer':                  ('Troll\'s Roar', False),
    'Dragon Greatclaw':                 ('Endure', False),
    'Scimitar':                         ('Spinning Slash', False),
    'Twinblade':                        ('Spinning Slash', False),
    'Gargoyle\'s Black Halberd':        ('Spinning Slash', False),
    'Short Spear':                      ('Impaling Thrust', False),
    'Partisan':                         ('Impaling Thrust', False),
    'Estoc':                            ('Impaling Thrust', False),
    'Katar':                            ('Impaling Thrust', False),
    'Longsword':                        ('Square Off', False),
    'Lance':                            ('Charge Forth', False),
    'Golem\'s Halberd':                 ('Charge Forth', False),
    'Great Knife':                      ('Quickstep', False),
    'Forked Hatchet':                   ('Quickstep', False),
    'Prelate\'s Inferno Crozier':       ('Prelate\'s Charge', False),
    'Treespear':                        ('Sacred Order', False),
    'Great Club':                       ('Golden Land', False),
    'Golden Halberd':                   ('Golden Vow', False),
    'Carian Knight\'s Shield':          ('Carian Retaliation', False),
    'Gargoyle\'s Greatsword':           ('Vacuum Slice', False),
}


def run():
    with engine.begin() as conn:
        updated_er = 0
        updated_err = 0
        not_found = []

        for weapon_name, (skill_name, is_unique) in WEAPON_SKILLS.items():
            # Update ER
            result = conn.execute(text(
                "UPDATE sl_weapons SET special_ability = :skill "
                "WHERE name = :name AND game = 'elden_ring'"
            ), {'skill': skill_name, 'name': weapon_name})
            if result.rowcount > 0:
                updated_er += result.rowcount
            else:
                not_found.append(f'ER:{weapon_name}')

            # Update ERR (same weapons, same default skills apply)
            result2 = conn.execute(text(
                "UPDATE sl_weapons SET special_ability = :skill "
                "WHERE name = :name AND game = 'err'"
            ), {'skill': skill_name, 'name': weapon_name})
            if result2.rowcount > 0:
                updated_err += result2.rowcount

    print(f'Updated {updated_er} ER weapons, {updated_err} ERR weapons')
    if not_found:
        print(f'Not found in ER ({len(not_found)}):')
        for n in not_found[:30]:
            print(f'  {n}')


if __name__ == '__main__':
    run()
