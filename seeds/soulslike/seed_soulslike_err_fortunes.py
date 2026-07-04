"""
Seed: ERR Fortunes - overview/taxonomy pass.
Source: https://err.fandom.com/wiki/Fortunes (pasted directly by user, site blocks automated fetch)

This seeds the 28 Fortunes (3 Basic + 13 Common + 7 Rare + 5 Legendary) with name,
tier, and flavor description only. Exact buffs/drawbacks/unique_effects per Fortune
need their individual wiki pages - left NULL here, to be filled in a follow-up pass
once that detail is available.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_fortunes.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, tier, description, how_to_unlock)
FORTUNES = [
    # Basic - auto-granted with Oracle Effigy, cannot be minor
    ('Bold',         'basic', 'The aspect of an ordinary Tarnished warrior, using melee weapons to defeat foes.',
     'Automatically granted alongside the Oracle Effigy.'),
    ('Cunning',      'basic', 'The aspect of an ordinary Tarnished marksman, using ranged weapons and thrown items to defeat foes.',
     'Automatically granted alongside the Oracle Effigy.'),
    ('Wise',         'basic', 'The aspect of an ordinary Tarnished scholar, using sorceries and incantations to defeat foes.',
     'Automatically granted alongside the Oracle Effigy.'),

    # Common - unlocked with Oracle's Remedy at a Site of Grace
    ('Adherent',     'common', 'The aspect of a pious supplicant who commits to routing unbelievers with one incantation school at a time.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Apothecary',   'common', 'The aspect of a proficient craftsman who pelts their foes with consumables and crossbow bolts.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Assassin',     'common', 'The aspect of a resourceful combatant focused on breaking enemy stances with quick blows.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Barbarian',    'common', 'The aspect of a savage warrior who endures pain to satisfy their bloodlust.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Cleric',       'common', 'The aspect of a devout servant of the powers that be, ready to aid with supportive and healing incantations.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Dancer',       'common', 'The aspect of a skilled fighter who thrives when deflecting blows with precision and employing weapon skills.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Heretic',      'common', 'The aspect of an acolyte of greater powers seeking to weaken and afflict their foes.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Ranger',       'common', 'The aspect of a trained archer, able to last in strenuous circumstances.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Sage',         'common', 'The aspect of a wayward mage dealing in hidden arts, striking with unconventional spells.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Sentinel',     'common', 'The aspect of a holy warrior who invokes divine power from the safety of their heavy armor and shield.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Sorcerer',     'common', 'The aspect of a learned practitioner of the magical arts who can quickly unleash a barrage of sorceries.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Spellsword',   'common', 'The aspect of a wielder of magics and weapons who alternates between magical and physical combat.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),
    ('Veteran',      'common', 'The aspect of a seasoned old hand, employing lost battle arts to bolster their melee combat.',
     "Unlock with an Oracle's Remedy at any Site of Grace."),

    # Rare - found exploring the world or defeating powerful enemies
    ('Brave',        'rare', 'The aspect of a rough warrior from the frigid highlands who endures pain to return devastating charged attacks.',
     'Found by exploring the world or defeating a powerful enemy.'),
    ('Bulwark',      'rare', 'The aspect of a pillar of defense, standing firm as foes break themselves against their body.',
     'Found by exploring the world or defeating a powerful enemy.'),
    ('Godslayers',   'rare', 'The aspect of an avenger of the Gloam-Eyed Queen, wielding black flame with a one-handed weapon.',
     'Found by exploring the world or defeating a powerful enemy.'),
    ('Haima',        'rare', 'The aspect of a heavy magic hitter who prioritizes the breaking of enemy stances.',
     'Found by exploring the world or defeating a powerful enemy.'),
    ('Houses',       'rare', 'The aspect of a scholar of sorcerers and incantations, employing both in equal measure.',
     'Found by exploring the world or defeating a powerful enemy.'),
    ('Spiritcaller', 'rare', 'The aspect of a mystical beast deeply in touch with the spirit world, calling long-lost defenders to its side.',
     'Found by exploring the world or defeating a powerful enemy.'),
    ('Warmaster',    'rare', 'The aspect of a master of disciplines who alternates from weapon to weapon in combat.',
     'Found by exploring the world or defeating a powerful enemy.'),

    # Legendary - found exploring, NPC questlines, or defeating powerful enemies
    ('Beasts',       'legendary', 'The aspect of a hybrid incantation user who succumbs to beasthood to exchange damage negation for attack power.',
     'Found by exploring the world, completing an NPC questline, or defeating a powerful enemy.'),
    ('Crucible',     'legendary', 'The aspect of a primal warrior whose physique is empowered by Crucible incantations.',
     'Found by exploring the world, completing an NPC questline, or defeating a powerful enemy.'),
    ('Dynasts',      'legendary', 'The aspect of an aspirant of the Moghywn Dynasty who feasts on the blood of their enemies.',
     'Found by exploring the world, completing an NPC questline, or defeating a powerful enemy.'),
    ('Latenna',      'legendary', 'The aspect of a magical archer who strikes true with careful shots at the expense of mobility.',
     'Found by exploring the world, completing an NPC questline, or defeating a powerful enemy.'),
    ('Reeds',        'legendary', 'The aspect of a bloodsoaked warrior from across the sea, deftly two-handing a weapon for skilled feats of deflection.',
     'Found by exploring the world, completing an NPC questline, or defeating a powerful enemy.'),
]


def run():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_err_fortunes"))
        print(f'Seeding {len(FORTUNES)} Fortunes...')
        for name, tier, desc, unlock in FORTUNES:
            conn.execute(text("""
                INSERT INTO sl_err_fortunes (name, fortune_type, description, how_to_unlock)
                VALUES (:name, :tier, :desc, :unlock)
            """), {'name': name, 'tier': tier, 'desc': desc, 'unlock': unlock})
            print(f'  [{tier:<10}] {name}')
        conn.commit()

        counts = conn.execute(text(
            "SELECT fortune_type, COUNT(*) FROM sl_err_fortunes GROUP BY fortune_type"
        )).fetchall()
        print('\nCounts by tier:')
        for tier, count in counts:
            print(f'  {tier}: {count}')

    print('\nDone. Buffs/drawbacks/unique_effects are NULL - fill in once individual pages are reviewed.')


if __name__ == '__main__':
    run()
