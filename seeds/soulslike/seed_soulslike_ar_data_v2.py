"""
Seed: AR (Attack Rating) calculator data from ThomasJClark/elden-ring-weapon-calculator's
regulation-vanilla-v1.14.js - post-Shadow of the Erdtree DLC, 480 weapons / 3216 affinity
variants, exact data extracted from the game's own regulation.bin.

This REPLACES the earlier erdb-based seed (which predated the DLC and only had 305/402
base game weapons). Source: https://github.com/ThomasJClark/elden-ring-weapon-calculator

Run: chwebsiteprj/bin/python3 seed_soulslike_ar_data_v2.py
"""
import json
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

REGULATION_FILE = '/srv/ch-webserver/regulation-vanilla-v1.14.js'

# Affinity ID -> name (from ThomasJClark calculator's weaponTypes / affinity mapping,
# matches the bracket-suffix names we already use elsewhere in our DB)
AFFINITY_NAMES = {
    0:  'Standard', 1: 'Heavy', 2: 'Keen', 3: 'Quality', 4: 'Fire',
    5:  'Flame Art', 6: 'Lightning', 7: 'Sacred', 8: 'Magic', 9: 'Cold',
    10: 'Poison', 11: 'Blood', 12: 'Occult', 14: 'Unique',
}


def evaluate_calc_correct_graph(points):
    """
    Port of evaluateCalcCorrectGraph from regulationData.ts.
    points: list of {maxVal, maxGrowVal, adjPt} dicts (5 stages).
    Returns a 150-entry list of scaling fractions indexed by stat value (0-149).
    """
    values = [0.0] * 150
    for i in range(len(points) - 1):
        left, right = points[i], points[i + 1]
        x0, x1 = left['maxVal'], right['maxVal']
        y0, y1 = left['maxGrowVal'], right['maxGrowVal']
        adj = right['adjPt']

        for v in range(max(0, x0), min(149, x1) + 1):
            if x1 == x0:
                values[v] = y0
                continue
            ratio = (v - x0) / (x1 - x0)
            if adj > 0:
                growth = ratio ** adj
            else:
                growth = 1 - ((1 - ratio) ** abs(adj))
            values[v] = y0 + (y1 - y0) * growth

    # Fill any remaining tail with the last computed value
    last_val = values[min(149, points[-1]['maxVal'])] if points else 0.0
    for v in range(points[-1]['maxVal'] if points else 0, 150):
        if v < 150:
            values[v] = last_val

    return values


def run():
    print(f'Loading {REGULATION_FILE}...')
    with open(REGULATION_FILE, encoding='utf-8') as f:
        data = json.load(f)

    print(f"calcCorrectGraphs: {len(data['calcCorrectGraphs'])}")
    print(f"attackElementCorrects: {len(data['attackElementCorrects'])}")
    print(f"reinforceTypes: {len(data['reinforceTypes'])}")
    print(f"weapons: {len(data['weapons'])}")

    with engine.connect() as conn:
        # 1. Correction graphs - evaluate each into a 150-entry curve
        print('\n=== Seeding correction graphs ===')
        conn.execute(text("DELETE FROM sl_correction_graphs WHERE game='elden_ring'"))
        for graph_id, points in data['calcCorrectGraphs'].items():
            curve = evaluate_calc_correct_graph(points)
            conn.execute(text(
                "INSERT INTO sl_correction_graphs (id, curve_json, game) VALUES (:id, :curve, 'elden_ring')"
            ), {'id': int(graph_id), 'curve': json.dumps(curve)})
        conn.commit()
        print(f"  {len(data['calcCorrectGraphs'])} graphs seeded")

        # 2. Attack element corrects - store raw structure (damage_type_idx -> {stat: true/ratio})
        print('\n=== Seeding attack element corrects ===')
        conn.execute(text("DELETE FROM sl_attack_element_correct WHERE game='elden_ring'"))
        for aec_id, correct_map in data['attackElementCorrects'].items():
            conn.execute(text(
                "INSERT INTO sl_attack_element_correct (id, correct_json, game) "
                "VALUES (:id, :data, 'elden_ring')"
            ), {'id': int(aec_id), 'data': json.dumps(correct_map)})
        conn.commit()
        print(f"  {len(data['attackElementCorrects'])} AEC entries seeded")

        # 3. Weapons - base (unupgraded) attack + scaling per affinity variant
        print('\n=== Seeding weapon AR data ===')
        conn.execute(text("DELETE FROM sl_weapon_ar_data WHERE game='elden_ring'"))

        # Match against our existing sl_weapons table by name
        our_weapons = {r[0] for r in conn.execute(text(
            "SELECT DISTINCT name FROM sl_weapons WHERE game='elden_ring'"
        )).fetchall()}
        print(f'  Weapons already in our DB: {len(our_weapons)}')

        inserted = 0
        no_match = 0
        new_weapon_names = set()

        for w in data['weapons']:
            base_name = w['weaponName']
            affinity_id = w.get('affinityId', 0)
            # -1 = unique/legendary weapons that can't be infused with an affinity at all
            # (e.g. Moonveil, Rivers of Blood) - treat as "Standard" since it's the only variant.
            affinity = 'Standard' if affinity_id == -1 else AFFINITY_NAMES.get(affinity_id, f'Unknown{affinity_id}')

            if base_name not in our_weapons:
                no_match += 1
                new_weapon_names.add(base_name)
                continue

            requirements = w.get('requirements', {})
            attack = dict(w.get('attack', []))             # [[dmgTypeIdx, value], ...] -> {idx: value}
            attribute_scaling = dict(w.get('attributeScaling', []))  # [[stat, value], ...] -> {stat: value}

            conn.execute(text("""
                INSERT INTO sl_weapon_ar_data
                    (weapon_name, affinity, is_dlc, requirements_json, attack_json,
                     attribute_scaling_json, attack_element_correct_id, calc_correct_graph_json, game)
                VALUES
                    (:name, :aff, :dlc, :req, :atk, :scal, :aecid, :ccg, 'elden_ring')
            """), {
                'name': base_name, 'aff': affinity,
                'dlc': 1 if w.get('dlc') else 0,
                'req': json.dumps(requirements),
                'atk': json.dumps(attack),
                'scal': json.dumps(attribute_scaling),
                'aecid': w.get('attackElementCorrectId', 10000),
                'ccg': json.dumps(w.get('calcCorrectGraphIds', {})),
            })
            inserted += 1

        conn.commit()
        print(f'  {inserted} weapon/affinity rows inserted')
        print(f'  {no_match} CSV rows had no DB match ({len(new_weapon_names)} unique unmatched names)')
        if new_weapon_names:
            print(f'  Sample unmatched: {list(new_weapon_names)[:15]}')

    print('\nDone.')


if __name__ == '__main__':
    run()
