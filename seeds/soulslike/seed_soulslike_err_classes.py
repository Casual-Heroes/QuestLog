"""
Seed: Elden Ring Reforged (ERR) starting classes.
Source: err.fandom.com/wiki/Character_Changes - "Starting Classes" section.
ERR rebalances all classes to a flat 89 total stat points at level 10
(except Wretch, who stays level 1 / all 10s / total 80, same as vanilla).
Adds 5 new classes not in vanilla ER: Perfumer, Scout, Gladiator, Guide
(Wretch is shared with vanilla naming but stats match vanilla exactly).

Run: chwebsiteprj/bin/python3 seed_soulslike_err_classes.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

CLASSES = [
    # name,         level, vig, mnd, end, str, dex, int, fai, arc
    ('Vagabond',    10, 16, 10, 11, 14, 13,  9,  9,  7),
    ('Warrior',     10, 13, 12, 11, 10, 16, 10,  8,  9),
    ('Hero',        10, 15,  9, 13, 16, 10,  7,  9, 10),
    ('Bandit',      10, 11, 11, 13,  9, 14,  9,  8, 14),
    ('Astrologer',  10, 11, 16, 10,  8, 12, 16,  7,  9),
    ('Prophet',     10, 11, 15,  9, 11, 10,  7, 16, 10),
    ('Confessor',   10, 12, 13, 10, 12, 12,  8, 14,  8),
    ('Samurai',     10, 12, 11, 14, 12, 15,  9,  8,  8),
    ('Prisoner',    10, 12, 13, 11, 10, 14, 14,  6,  9),
    ('Wretch',       1, 10, 10, 10, 10, 10, 10, 10, 10),
    ('Perfumer',    10, 10, 12, 11,  9, 14, 10,  7, 16),
    ('Scout',       10, 12, 12, 12, 11, 11, 10, 10, 11),
    ('Gladiator',   10, 12,  9, 13, 14, 14,  9,  6, 12),
    ('Guide',       10, 13, 15, 11,  9, 11, 10, 14,  6),
]


def run():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_classes WHERE game = 'err'"))
        print('Seeding ERR classes...')
        for row in CLASSES:
            name, level, vig, mnd, end_, str_, dex, int_, fai, arc = row
            total = vig + mnd + end_ + str_ + dex + int_ + fai + arc
            conn.execute(text("""
                INSERT INTO sl_classes
                    (game, name, starting_level, vigor, mind, endurance,
                     strength, dexterity, intelligence, faith, arcane)
                VALUES
                    ('err', :name, :lvl, :vig, :mnd, :end,
                     :str, :dex, :int, :fai, :arc)
            """), {
                'name': name, 'lvl': level, 'vig': vig, 'mnd': mnd,
                'end': end_, 'str': str_, 'dex': dex, 'int': int_,
                'fai': fai, 'arc': arc,
            })
            print(f'  {name} (Lv{level}, total={total}): VIG{vig} MND{mnd} END{end_} STR{str_} DEX{dex} INT{int_} FAI{fai} ARC{arc}')
        conn.commit()
        print('\nDone.')


if __name__ == '__main__':
    run()
