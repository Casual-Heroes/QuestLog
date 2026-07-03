"""
Seed: ERR Runeforging system overview + the 7 Binding Rune category stubs.
Source: err.fandom.com/wiki/Runeforging, pasted directly by user.

Individual Binding Rune lists (Grafted/Cradled/Leonine/Covetous/Cursed/Tainted/Scarlet
Runes + Ascended Binding Runes) to follow in a separate seed pass once the user
provides each section.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_runeforging_overview.py
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

SYSTEM_OVERVIEW = (
    "Runeforging is a new progression system introduced in ELDEN RING Reforged. It enables the "
    "creation of Binding Runes, a new category of items that grant passive boosts while held in the "
    "inventory.\n\n"
    "To unlock the Runeforging system, a Great Rune must be acquired (even not restored) and 20 Rune "
    "Pieces must be presented to Finger Reader Enia in the Roundtable Hold. Unlocking the system gives "
    "you the Fractured Great Rune key item - depositing it in the storage chest disables the effects of "
    "all your Binding Runes. Having this item also allows you to manage Binding Runes at any Site of "
    "Grace.\n\n"
    "RUNE PIECES & RUNIC TRACES: Rune Pieces are collectible items scattered throughout the Lands "
    "Between, generally found in obscure and hidden corners of the world. Bosses also drop them, with "
    "additional Pieces dropped in NG+ cycles. Runic Traces simply track the total number of Rune Pieces "
    "collected from world pick-ups so far (other methods, like killing bosses, don't grant Traces). "
    "Reaching the level cap in NG+ replaces the level up menu at Sites of Grace with the option to "
    "purchase Rune Pieces, Ember Pieces, and Lost Ashes for 500,000 runes each.\n\n"
    "Rune Pieces are found in the open world, dungeons (caves, catacombs, Hero's Graves), castles "
    "(Morne, Sol), and Legacy Dungeons - every dungeon has at least one Piece, larger ones have two or "
    "more. Four general location types: (1) scattered on non-descript cliff edges, ponds, and roofs - "
    "easiest to find; (2) obscure dungeon corners/outcrops requiring attention to ledges, cliffs, "
    "bushes, and grass; (3) inside breakable objects (vases, boxes, barrels) where the orange glow is "
    "only intermittently visible; (4) requiring difficult platforming/parkour on foot or via Torrent - "
    "rare, for the most adventurous players. Over 1000 Rune Pieces exist total in the Lands Between.\n\n"
    "BINDING RUNES: Range from attribute increases to improvements in FP Cost, Poise Damage, or "
    "Movement Speed. Each Binding Rune is forged from 10 Rune Pieces (25 for Grafted Runes) and can be "
    "consumed in the inventory at any time to retrieve the spent Pieces. Each Binding Rune can be forged "
    "up to a maximum of 10 times (4 times for Grafted Runes). Each Great Rune unlocks the forging of new "
    "Binding Runes, themed in accordance with the Demigod whose power binds them. Binding Runes are "
    "available for purchase at any Site of Grace, or at Finger Reader Enia."
)

# (great_rune_name, rune_category_name, cost_pieces, max_forges)
RUNE_CATEGORIES = [
    ("Godrick's Great Rune", 'Grafted Runes', 25, 4),
    ('Great Rune of the Unborn', 'Cradled Runes', 10, 10),
    ("Radahn's Great Rune", 'Leonine Runes', 10, 10),
    ("Rykard's Great Rune", 'Covetous Runes', 10, 10),
    ("Morgott's Great Rune", 'Cursed Runes', 10, 10),
    ("Mohg's Great Rune", 'Tainted Runes', 10, 10),
    ("Malenia's Great Rune", 'Scarlet Runes', 10, 10),
]


def run():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_err_runeforging WHERE section='system'"))
        conn.execute(text("""
            INSERT INTO sl_err_runeforging (section, content, created_at)
            VALUES ('system', :content, :ts)
        """), {'content': SYSTEM_OVERVIEW, 'ts': NOW})
        print('System overview seeded.')

        for great_rune, category, cost, forges in RUNE_CATEGORIES:
            conn.execute(text(
                "DELETE FROM sl_err_runeforging WHERE section='category' AND rune_category_name=:cat"
            ), {'cat': category})
            conn.execute(text("""
                INSERT INTO sl_err_runeforging
                    (section, great_rune_name, rune_category_name, cost_pieces, max_forges, created_at)
                VALUES ('category', :gr, :cat, :cost, :forges, :ts)
            """), {'gr': great_rune, 'cat': category, 'cost': cost, 'forges': forges, 'ts': NOW})
            print(f'  + (stub) {category} ({great_rune}) - {cost} pieces/forge, max {forges} forges')

        # Ascended Binding Runes - separate stub, no Great Rune tie-in
        conn.execute(text(
            "DELETE FROM sl_err_runeforging WHERE section='category' AND rune_category_name='Ascended Binding Runes'"
        ))
        conn.execute(text("""
            INSERT INTO sl_err_runeforging (section, rune_category_name, created_at)
            VALUES ('category', 'Ascended Binding Runes', :ts)
        """), {'ts': NOW})
        print('  + (stub) Ascended Binding Runes')

        conn.commit()
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_runeforging WHERE section='category'")).scalar()
        print(f'\n{total}/8 Runeforging category stubs seeded, awaiting individual Binding Rune lists.')


if __name__ == '__main__':
    run()
