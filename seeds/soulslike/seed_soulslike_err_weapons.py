"""
Seed: Elden Ring Reforged (ERR) weapons + AR calculator data.
Source: ThomasJClark/elden-ring-weapon-calculator's regulation-reforged-v2.2.3.4.js
- same trusted source/format as our vanilla ER data, exact game-extracted values.

ERR weapons get their own full rows (game='err') in the same tables vanilla ER uses
(sl_weapons, sl_weapon_ar_data, sl_correction_graphs, sl_attack_element_correct) -
NOT a thin override table, since ERR changes nearly every field per weapon and adds
weapons that don't exist in vanilla at all.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapons.py
"""
import json
import time
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()
NOW = int(time.time())

REGULATION_FILE = '/srv/ch-webserver/regulation-reforged-v2.2.3.4.js'


def evaluate_calc_correct_graph(points):
    """Same algorithm as the vanilla ER importer - port of evaluateCalcCorrectGraph.
    maxVal is normally an integer stat value but can rarely be a float (e.g. 97.5);
    round to the nearest int since stats only take integer values 0-99."""
    values = [0.0] * 150
    for i in range(len(points) - 1):
        left, right = points[i], points[i + 1]
        x0, x1 = round(left['maxVal']), round(right['maxVal'])
        y0, y1 = left['maxGrowVal'], right['maxGrowVal']
        adj = right['adjPt']
        for v in range(max(0, x0), min(149, x1) + 1):
            if x1 == x0:
                values[v] = y0
                continue
            ratio = (v - x0) / (x1 - x0)
            growth = ratio ** adj if adj > 0 else 1 - ((1 - ratio) ** abs(adj))
            values[v] = y0 + (y1 - y0) * growth
    last_idx = round(points[-1]['maxVal']) if points else 0
    last_val = values[min(149, last_idx)] if points else 0.0
    for v in range(last_idx, 150):
        if v < 150:
            values[v] = last_val
    return values


def derive_affinity_names(weapons):
    """Derive affinityId -> name by diffing each affinity variant's name against
    the Standard (affinityId=0) variant of the same weapon. Self-describing,
    no hardcoded mapping needed."""
    by_weapon = {}
    for w in weapons:
        by_weapon.setdefault(w['weaponName'], {})[w.get('affinityId')] = w['name']

    votes = {}
    for wname, variants in by_weapon.items():
        if 0 not in variants:
            continue
        standard_name = variants[0]
        for aid, name in variants.items():
            if aid in (0, -1):
                continue
            if name.endswith(standard_name):
                prefix = name[:-len(standard_name)].strip()
                if prefix:
                    votes.setdefault(aid, {}).setdefault(prefix, 0)
                    votes[aid][prefix] += 1

    affinity_names = {0: 'Standard'}
    for aid, prefix_counts in votes.items():
        # Pick the most common prefix for this affinity ID (handles rare outliers)
        affinity_names[aid] = max(prefix_counts.items(), key=lambda x: x[1])[0]
    return affinity_names


def run():
    print(f'Loading {REGULATION_FILE}...')
    with open(REGULATION_FILE, encoding='utf-8') as f:
        data = json.load(f)

    weapons = data['weapons']
    print(f"calcCorrectGraphs: {len(data['calcCorrectGraphs'])}")
    print(f"attackElementCorrects: {len(data['attackElementCorrects'])}")
    print(f"weapons: {len(weapons)}")

    affinity_names = derive_affinity_names(weapons)
    print(f'\nDerived {len(affinity_names)} affinity names: {affinity_names}')

    with engine.connect() as conn:
        # 1. Correction graphs
        print('\n=== Seeding ERR correction graphs ===')
        conn.execute(text("DELETE FROM sl_correction_graphs WHERE game='err'"))
        for graph_id, points in data['calcCorrectGraphs'].items():
            curve = evaluate_calc_correct_graph(points)
            conn.execute(text(
                "INSERT INTO sl_correction_graphs (id, curve_json, game) VALUES (:id, :curve, 'err')"
            ), {'id': int(graph_id), 'curve': json.dumps(curve)})
        conn.commit()
        print(f"  {len(data['calcCorrectGraphs'])} graphs seeded")

        # 2. Attack element corrects
        print('\n=== Seeding ERR attack element corrects ===')
        conn.execute(text("DELETE FROM sl_attack_element_correct WHERE game='err'"))
        for aec_id, correct_map in data['attackElementCorrects'].items():
            conn.execute(text(
                "INSERT INTO sl_attack_element_correct (id, correct_json, game) VALUES (:id, :data, 'err')"
            ), {'id': int(aec_id), 'data': json.dumps(correct_map)})
        conn.commit()
        print(f"  {len(data['attackElementCorrects'])} AEC entries seeded")

        # 3. Weapons - one row per weapon+affinity combo, full standalone data
        print('\n=== Seeding ERR weapons (sl_weapons) ===')
        conn.execute(text("DELETE FROM sl_weapons WHERE game='err'"))
        conn.execute(text("DELETE FROM sl_weapon_ar_data WHERE game='err'"))

        # Group by base weapon name so we insert each unique weapon once into sl_weapons
        # (using its Standard/affinityId=0 stats as the canonical entry), then one row per
        # affinity into sl_weapon_ar_data for AR calc purposes.
        by_weapon_name = {}
        for w in weapons:
            by_weapon_name.setdefault(w['weaponName'], []).append(w)

        weapon_id_map = {}  # weaponName -> sl_weapons.id
        inserted_weapons = 0
        inserted_ar_rows = 0

        for wname, variants in by_weapon_name.items():
            standard = next((v for v in variants if v.get('affinityId') == 0), variants[0])

            requirements = standard.get('requirements', {})
            attack = dict(standard.get('attack', []))
            scaling = dict(standard.get('attributeScaling', []))

            def scale_letter(stat_key):
                val = scaling.get(stat_key, 0)
                if not val: return '-'
                if val >= 1.5: return 'S'
                if val >= 1.1: return 'A'
                if val >= 0.7: return 'B'
                if val >= 0.4: return 'C'
                if val >= 0.15: return 'D'
                return 'E'

            weapon_type_id = standard.get('weaponType', 0)

            result = conn.execute(text("""
                INSERT INTO sl_weapons
                    (game, name, weapon_type, physical_damage, magic_damage,
                     fire_damage, lightning_damage, holy_damage, critical, weight,
                     str_scaling, dex_scaling, int_scaling, fai_scaling, arc_scaling,
                     str_requirement, dex_requirement, int_requirement,
                     fai_requirement, arc_requirement, is_somber, created_at)
                VALUES
                    ('err', :name, :wtype, :phy, :mag, :fire, :lit, :hol, 100, 0,
                     :ss, :ds, :is2, :fs, :as2,
                     :sr, :dr, :ir, :fr, :ar, 0, :ts)
            """), {
                'name': wname, 'wtype': str(weapon_type_id),
                'phy': attack.get('0', 0) or attack.get(0, 0),
                'mag': attack.get('1', 0) or attack.get(1, 0),
                'fire': attack.get('2', 0) or attack.get(2, 0),
                'lit': attack.get('3', 0) or attack.get(3, 0),
                'hol': attack.get('4', 0) or attack.get(4, 0),
                'ss': scale_letter('str'), 'ds': scale_letter('dex'),
                'is2': scale_letter('int'), 'fs': scale_letter('fai'), 'as2': scale_letter('arc'),
                'sr': requirements.get('str', 0), 'dr': requirements.get('dex', 0),
                'ir': requirements.get('int', 0), 'fr': requirements.get('fai', 0),
                'ar': requirements.get('arc', 0),
                'ts': NOW,
            })
            inserted_weapons += 1

            # AR data: one row per affinity variant
            for variant in variants:
                aid = variant.get('affinityId', 0)
                affinity = affinity_names.get(aid, f'Unknown{aid}') if aid != -1 else 'Standard'
                v_attack = dict(variant.get('attack', []))
                v_scaling = dict(variant.get('attributeScaling', []))
                v_req = variant.get('requirements', {})

                conn.execute(text("""
                    INSERT INTO sl_weapon_ar_data
                        (weapon_name, affinity, is_dlc, requirements_json, attack_json,
                         attribute_scaling_json, attack_element_correct_id, calc_correct_graph_json, game)
                    VALUES
                        (:name, :aff, 0, :req, :atk, :scal, :aecid, :ccg, 'err')
                """), {
                    'name': wname, 'aff': affinity,
                    'req': json.dumps(v_req),
                    'atk': json.dumps(v_attack),
                    'scal': json.dumps(v_scaling),
                    'aecid': variant.get('attackElementCorrectId', 10000),
                    'ccg': json.dumps(variant.get('calcCorrectGraphIds', {})),
                })
                inserted_ar_rows += 1

        conn.commit()
        print(f'  {inserted_weapons} unique ERR weapons inserted into sl_weapons')
        print(f'  {inserted_ar_rows} weapon/affinity AR rows inserted')

    print('\nDone.')


if __name__ == '__main__':
    run()
