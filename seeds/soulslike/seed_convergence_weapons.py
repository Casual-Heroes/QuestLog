"""
Seed Convergence mod weapons into sl_weapons (game='convergence').
Uses convergence_weapons.json - 583 unique base weapons.
Run: chwebsiteprj/bin/python3 seed_convergence_weapons.py
"""
import json
import os
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

import django
django.setup()

from app.db import get_db_session
from sqlalchemy import text

JSON_FILE = '/home/fulldata/EldenTracker/convergence_weapons.json'

# Numeric scaling coefficient -> letter grade (matches ER wiki conventions)
def to_grade(val):
    if not val or val <= 0:
        return '-'
    if val < 0.2:
        return 'E'
    if val < 0.5:
        return 'D'
    if val < 0.7:
        return 'C'
    if val < 1.0:
        return 'B'
    if val < 1.5:
        return 'A'
    return 'S'

# somber = unique weapons (reinforced with somber smithing stones in base ER)
# In Convergence, unique-affinity weapons are somber
def is_somber(weapon):
    return weapon.get('affinity') == 'Unique'

def main():
    with open(JSON_FILE) as f:
        weapons = json.load(f)

    print(f'Loaded {len(weapons)} weapons from JSON')

    with get_db_session() as db:
        existing = db.execute(
            text("SELECT COUNT(*) FROM sl_weapons WHERE game='convergence'")
        ).scalar()
        if existing > 0:
            print(f'WARNING: {existing} convergence weapons already exist. Skipping (delete first if re-seeding).')
            return

        now = int(time.time())
        inserted = 0
        skipped = 0

        for w in weapons:
            name = w.get('name', '').strip()
            if not name:
                skipped += 1
                continue

            weapon_type = w.get('weapon_type', 'Unknown')
            attack = w.get('attack', {})
            scaling = w.get('scaling', {})
            reqs = w.get('requirements', {})

            physical_damage = int(attack.get('physical', 0) or 0)
            magic_damage    = int(attack.get('magic', 0) or 0)
            fire_damage     = int(attack.get('fire', 0) or 0)
            lightning_damage = int(attack.get('lightning', 0) or 0)
            holy_damage     = int(attack.get('holy', 0) or 0)

            str_scaling = to_grade(scaling.get('strength', 0))
            dex_scaling = to_grade(scaling.get('dexterity', 0))
            int_scaling = to_grade(scaling.get('intelligence', 0))
            fai_scaling = to_grade(scaling.get('faith', 0))
            arc_scaling = to_grade(scaling.get('arcane', 0))

            str_req = int(reqs.get('strength', 0) or 0)
            dex_req = int(reqs.get('dexterity', 0) or 0)
            int_req = int(reqs.get('intelligence', 0) or 0)
            fai_req = int(reqs.get('faith', 0) or 0)
            arc_req = int(reqs.get('arcane', 0) or 0)

            somber = 1 if is_somber(w) else 0

            db.execute(text("""
                INSERT INTO sl_weapons (
                    game, name, weapon_type,
                    physical_damage, magic_damage, fire_damage, lightning_damage, holy_damage,
                    critical, weight,
                    str_scaling, dex_scaling, int_scaling, fai_scaling, arc_scaling,
                    str_requirement, dex_requirement, int_requirement, fai_requirement, arc_requirement,
                    is_somber, spoiler_level, created_at
                ) VALUES (
                    'convergence', :name, :weapon_type,
                    :phys, :magic, :fire, :lightning, :holy,
                    100, 0.0,
                    :str_s, :dex_s, :int_s, :fai_s, :arc_s,
                    :str_r, :dex_r, :int_r, :fai_r, :arc_r,
                    :somber, 3, :now
                )
            """), {
                'name': name, 'weapon_type': weapon_type,
                'phys': physical_damage, 'magic': magic_damage,
                'fire': fire_damage, 'lightning': lightning_damage, 'holy': holy_damage,
                'str_s': str_scaling, 'dex_s': dex_scaling,
                'int_s': int_scaling, 'fai_s': fai_scaling, 'arc_s': arc_scaling,
                'str_r': str_req, 'dex_r': dex_req,
                'int_r': int_req, 'fai_r': fai_req, 'arc_r': arc_req,
                'somber': somber, 'now': now,
            })
            inserted += 1

        db.commit()
        print(f'Inserted: {inserted}  Skipped: {skipped}')
        total = db.execute(
            text("SELECT COUNT(*) FROM sl_weapons WHERE game='convergence'")
        ).scalar()
        print(f'Convergence weapons in DB: {total}')

if __name__ == '__main__':
    main()
