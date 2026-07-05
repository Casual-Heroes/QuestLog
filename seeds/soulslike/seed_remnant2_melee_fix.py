"""
Fix truncated melee weapon names (apostrophe broke the regex parser)
and add missing melee weapons from wiki data.

Run: chwebsiteprj/bin/python3 seed_remnant2_melee_fix.py
"""
import django, os, re, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

NOW = int(time.time())

def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

# Fix truncated names: (broken_name, correct_name)
NAME_FIXES = [
    ('Assassin',    "Assassin's Dagger"),
    ('Hero',        "Hero's Sword"),
    ('World',       "World's Edge"),
]

# Melee weapons from wiki that are missing from the toolkit seed
# (name, moveset/subtype, damage_base, crit, weakspot, stagger, mod_name)
# damage is base (pre-upgrade), crit/weakspot/stagger as int percentage
MISSING_MELEE = [
    # These appear in wiki list but weren't in toolkit TS
    # toolkit had 46, wiki has more - adding the gaps
]

# Full corrected melee weapon list with stats from wiki
# Format: (name, weapon_subtype, damage, crit_pct, weakspot_pct, stagger_pct)
# We update existing ones with correct stats from wiki, add missing ones
MELEE_STATS = [
    ("Abyssal Hook",        'hammer',       101, 6,   85,   80),
    ("Assassin's Dagger",   'sword',         35, -3,  110, -15),
    ("Atom Smasher",        'hammer',        72,  5,   95,  11),
    ("Atom Splitter",       'greatsword',   100,  6,   95,   7),
    ("Black Greatsword",    'greatsword',   120, 15,  110,  25),
    ("Blade of Gul",        'sword',         57,  4,  100,   6),
    ("Bone Chopper",        'hatchet',       58,  7,  105,  -3),
    ("Crystal Staff",       'staff',         42,  5,   95,   3),
    ("Dark Matter Gauntlets",'fists',        50,  5,  110,   5),
    ("Decayed Claws",       'claws',         49, 16,  110,  -4),
    ("Dreamcatcher",        'staff',         58,  5,   95,   3),
    ("Edge of the Forest",  'katana',        59, 11,  105, -15),
    ("Feral Judgement",     'claws',         53, 13,  110, -15),
    ("Gas Giant",           'hammer',        74,  3,   95,   8),
    ("Godsplitter",         'sword',         38,  2,   50, -20),
    ("Harvester Scythe",    'scythe',        65, 12,  100, -33),
    ("Hero's Sword",        'sword',         51,  5,   90, -10),
    ("Huntress Spear",      'spear',         63,  5,  110,  -5),
    ("Iron Greatsword",     'greatsword',   105,  5,   95,  13),
    ("Knuckle Dusters",     'fists',         43,  5,  110,   5),
    ("Krell Axe",           'hatchet',       54,  3,   85, -10),
    ("Labyrinth Staff",     'staff',         64,  8,   95,   5),
    ("Mirage",              'flail',         48,  3,  100, -10),
    ("Nightshade",          'claws',         47, 18,  110, -20),
    ("Ornate Blade",        'sword',         52, 11,  105,  -5),
    ("Ornate Flail",        'flail',         63, 11,  100,  -3),
    ("Rebellion Spear",     'spear',         60, 13,  110,   2),
    ("Red Doe Staff",       'staff',         62,  3,   95,   8),
    ("Ritualist Scythe",    'scythe',        51,  5,  100, -19),
    ("Royal Broadsword",    'greatsword',   102,  7,   95,  11),
    ("Rusted Claws",        'claws',         51, 14,  110,  -9),
    ("Scrap Hammer",        'hammer',        83,  8,   95,   9),
    ("Scrap Hatchet",       'hatchet',       57,  6,  105,   1),
    ("Scrap Staff",         'staff',         65,  6,   95,   8),
    ("Shovel",              'hammer',        55, 15,  100,   0),
    ("Smolder",             'sword',         46,  4,   95,   1),
    ("Spectral Blade",      'katana',        53,  8,  105, -25),
    ("Steel Flail",         'flail',         69,  4,  100,   6),
    ("Steel Katana",        'katana',        56, 13,  105, -10),
    ("Steel Scythe",        'scythe',        55, 10,  100, -15),
    ("Steel Spear",         'spear',         61,  9,  110,  -4),
    ("Steel Sword",         'sword',         56,  7,  100,   2),
    ("Stonebreaker",        'greatsword',   103,  4,   95,   5),
    ("Vice Grips",          'claws',         55,  6,  110, -18),
    ("World's Edge",        'greatsword',    96,  3,   85, -20),
    ("Wrathbringer",        'hammer',       101,  6,   85,  80),
]


def main():
    with get_db_session() as db:
        # Step 1: Fix truncated names
        for broken, correct in NAME_FIXES:
            existing = db.execute(text(
                "SELECT id FROM r2_weapons WHERE name=:n AND weapon_type='melee'"
            ), {'n': broken}).scalar()
            if existing:
                new_slug = slugify(correct)
                db.execute(text(
                    "UPDATE r2_weapons SET name=:name, slug=:slug WHERE id=:id"
                ), {'name': correct, 'slug': new_slug, 'id': existing})
                print(f'  Fixed: {broken!r} -> {correct!r}')
            else:
                print(f'  Not found (already fixed?): {broken!r}')
        db.commit()

        # Step 2: Update all melee weapons with correct stats from wiki
        updated = 0
        inserted = 0
        for (name, subtype, damage, crit, weakspot, stagger) in MELEE_STATS:
            existing_id = db.execute(text(
                "SELECT id FROM r2_weapons WHERE name=:n AND weapon_type='melee'"
            ), {'n': name}).scalar()

            if existing_id:
                db.execute(text("""
                    UPDATE r2_weapons SET
                        physical_damage=:dmg, crit_chance=:crit,
                        weakspot_bonus=:ws, stagger=:stagger
                    WHERE id=:id
                """), {'dmg': damage, 'crit': crit, 'ws': weakspot,
                       'stagger': stagger, 'id': existing_id})
                updated += 1
            else:
                # Insert missing weapon
                db.execute(text("""
                    INSERT INTO r2_weapons
                        (slug, name, weapon_type, physical_damage, crit_chance,
                         weakspot_bonus, stagger, dlc, created_at)
                    VALUES (:slug, :name, 'melee', :dmg, :crit, :ws, :stagger, 'base', :now)
                """), {'slug': slugify(name), 'name': name, 'dmg': damage,
                       'crit': crit, 'ws': weakspot, 'stagger': stagger, 'now': NOW})
                print(f'  Added missing: {name}')
                inserted += 1

        db.commit()
        total = db.execute(text("SELECT COUNT(*) FROM r2_weapons WHERE weapon_type='melee'")).scalar()
        print(f'\nUpdated: {updated}  Inserted: {inserted}  Total melee: {total}')


if __name__ == '__main__':
    main()
