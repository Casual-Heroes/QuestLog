"""
Seed: Elden Ring starting classes and stat caps
Run: chwebsiteprj/bin/python3 seed_soulslike_classes_caps.py
Source: Fextralife Elden Ring wiki (verified)
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

CLASSES = [
    # name,           level, vig, mnd, end, str, dex, int, fai, arc
    ('Hero',          7,  14,  9, 12, 16,  9,  7,  8, 11),
    ('Vagabond',      9,  15, 10, 11, 14, 13,  9,  9,  7),
    ('Warrior',       8,  11, 12, 11, 10, 16, 10,  8,  9),
    ('Prisoner',      9,  11, 12, 11, 11, 14, 14,  6,  9),
    ('Astrologer',    6,   9, 15,  9,  8, 12, 16,  7,  9),
    ('Prophet',       7,  10, 14,  8, 11, 10,  7, 16, 10),
    ('Confessor',    10,  10, 13, 10, 12, 12,  9, 14,  9),
    ('Wretch',        1,  10, 10, 10, 10, 10, 10, 10, 10),
    ('Bandit',        5,  10, 11, 10,  9, 13,  9,  8, 14),
    ('Samurai',       9,  12, 11, 13, 12, 15,  9,  8,  8),
]

# Stat caps - multiple soft caps stored as soft_cap_1 and soft_cap_2 (primary breakpoints)
# notes column captures the full picture including secondary effects
STAT_CAPS = [
    # stat, soft_cap_1, soft_cap_2, hard_cap, notes
    ('vigor',        40, 60, 99, 'HP scaling: major gain to 40, diminishing 40-60, minimal 60-99'),
    ('mind',         50, 60, 99, 'FP scaling: major gain to 50, diminishing 50-60, minimal 60-99'),
    ('endurance',    15, 30, 99, 'Stamina: caps at 15/30/50. Equip load: caps at 25/60. Hard cap 99'),
    ('strength',     20, 80, 99, 'AR scaling breakpoints: 18/20 early, 50 mid, 80 soft cap. 99 hard cap'),
    ('dexterity',    20, 80, 99, 'AR scaling breakpoints: 18/20 early, 50 mid, 80 soft cap. 99 hard cap'),
    ('intelligence', 20, 80, 99, 'AR/Spellbuff breakpoints: 20/50/60 scaling, 80 soft cap. 99 hard cap'),
    ('faith',        20, 80, 99, 'AR/Spellbuff breakpoints: 20/50/60 scaling, 80 soft cap. 99 hard cap'),
    ('arcane',       20, 60, 99, 'AR scaling: 18/20 early, 40/45 mid, 60 soft cap, 80 secondary. 99 hard cap'),
]


def run():
    with engine.connect() as conn:
        # Classes
        print('Seeding classes...')
        conn.execute(text("DELETE FROM sl_classes WHERE game = 'elden_ring'"))
        for row in CLASSES:
            name, level, vig, mnd, end_, str_, dex, int_, fai, arc = row
            conn.execute(text("""
                INSERT INTO sl_classes
                    (game, name, starting_level, vigor, mind, endurance,
                     strength, dexterity, intelligence, faith, arcane)
                VALUES
                    ('elden_ring', :name, :lvl, :vig, :mnd, :end,
                     :str, :dex, :int, :fai, :arc)
            """), {
                'name': name, 'lvl': level, 'vig': vig, 'mnd': mnd,
                'end': end_, 'str': str_, 'dex': dex, 'int': int_,
                'fai': fai, 'arc': arc,
            })
            print(f'  {name} (Lv{level}): VIG{vig} MND{mnd} END{end_} STR{str_} DEX{dex} INT{int_} FAI{fai} ARC{arc}')

        # Stat caps
        print('\nSeeding stat caps...')
        conn.execute(text("DELETE FROM sl_stat_caps WHERE game = 'elden_ring'"))
        for stat, sc1, sc2, hc, notes in STAT_CAPS:
            conn.execute(text("""
                INSERT INTO sl_stat_caps (game, stat, soft_cap_1, soft_cap_2, hard_cap, notes)
                VALUES ('elden_ring', :stat, :sc1, :sc2, :hc, :notes)
            """), {'stat': stat, 'sc1': sc1, 'sc2': sc2, 'hc': hc, 'notes': notes})
            print(f'  {stat}: soft {sc1}/{sc2} hard {hc}')

        conn.commit()
        print('\nDone.')


if __name__ == '__main__':
    run()
