"""
Seed: ERR Shadowed Curios system overview + the 9 Curio name/trigger stubs.
Source: err.fandom.com/wiki/Shadowed_Curios, pasted directly by user.
Updated to version 2.1.2.2.

Individual Curio detail (the 3 selectable effects + rank-upgrade text per Curio)
to follow in a separate seed pass once the user provides each page.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_curios_overview.py
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
    "Shadowed Curios are a new, permanent progression system found in the Realm of Shadow that allow "
    "you to upgrade very specific, active portions of your build (unlike the passive boosts of Binding "
    "Runes) and typically provide some moderately sized temporary buff upon performing a specific "
    "action.\n\n"
    "Each Curio lets you choose and strengthen one of three unique effects that occur upon the trigger "
    "condition. Curios function both inside and outside the Shadow Realm, unlike Scadutree Blessing. "
    "Curios can be re-sealed at any Site of Grace - this disables their effect and refunds all spent "
    "Ember Pieces.\n\n"
    "Shadowed Curios must be found throughout the Shadow Realm. Some are found as item pickups, while "
    "for others you must defeat certain enemies.\n\n"
    "EMBER PIECES: Each Shadowed Curio is unlocked at the cost of 50 Ember Pieces, glowing red "
    "collectables found throughout the Shadow Realm in similarly obscure locations as Rune Pieces in "
    "the Lands Between. Also obtainable by defeating bosses. To unlock a Curio, go to the Strengthen "
    "Character menu at a Site of Grace and select Shadowed Curios, then choose between three effect "
    "options for that Curio. Each effect can be further strengthened by two ranks, each costing a "
    "further 25 Ember Pieces - a fully upgraded Curio costs 100 Ember Pieces total. It is possible to "
    "fully upgrade all nine Curios (one effect each), but not in a single NG cycle due to the limited "
    "Ember Piece supply (~250 ground pickups exist in the Realm of Shadow)."
)

# (name, trigger_condition)
CURIOS = [
    ('Academy', 'Triggers upon casting a spell'),
    ('Dragonscale', 'Triggers upon staggering'),
    ('Fanatic', 'Triggers upon defeating a foe'),
    ('Gate', 'Triggers upon successfully guarding an attack'),
    ('Knifeprint', 'Triggers upon performing a critical attack'),
    ('Physician', 'Triggers upon imbibing a flask of tears'),
    ('Poacher', 'Triggers upon crouching'),
    ('Ranah', 'Triggers upon performing a perfect action'),
    ('Scadutear', 'Triggers upon imbibing the Wondrous Physick'),
]


def run():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_err_curios WHERE section='system'"))
        conn.execute(text("""
            INSERT INTO sl_err_curios (section, content, created_at)
            VALUES ('system', :content, :ts)
        """), {'content': SYSTEM_OVERVIEW, 'ts': NOW})
        print('System overview seeded.')

        for name, trigger in CURIOS:
            conn.execute(text("DELETE FROM sl_err_curios WHERE section='curio' AND name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_curios (section, name, trigger_condition, created_at)
                VALUES ('curio', :name, :trigger, :ts)
            """), {'name': name, 'trigger': trigger, 'ts': NOW})
            print(f'  + (stub) {name} - {trigger}')
        conn.commit()

        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_curios WHERE section='curio'")).scalar()
        print(f'\n{total}/9 Curio stubs seeded, awaiting individual page detail.')


if __name__ == '__main__':
    run()
