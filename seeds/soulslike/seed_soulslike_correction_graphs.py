"""
Seed: AR scaling correction curves, extracted directly from Elden Ring's
regulation.bin via the erdb project's pre-parsed CalcCorrectGraph.csv.
This is the EXACT, game-verified scaling curve - not an approximation.

Algorithm ported directly from erdb/src/erdb/table/correction_graph.py
Source: https://github.com/EldenRingDatabase/erdb (MIT-style license)

Run: chwebsiteprj/bin/python3 seed_soulslike_correction_graphs.py
"""
import csv
import json
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()


def calc_correction(level, threshold_left, threshold_right, coeff_left, coeff_right, adjustment):
    if threshold_right == threshold_left:
        return coeff_left
    level_ratio = (level - threshold_left) / (threshold_right - threshold_left)
    if adjustment > 0:
        growth = level_ratio ** adjustment
    else:
        growth = 1 - ((1 - level_ratio) ** abs(adjustment))
    return coeff_left + ((coeff_right - coeff_left) * growth)


def build_curve(row):
    """Returns a list of 150 floats (0-149), the scaling fraction (0.0-1.0+) at each stat value."""
    points = [0, 1, 2, 3, 4]
    ranges = []
    for left, right in zip(points, points[1:]):
        ranges.append({
            'threshold_left':  int(float(row[f'stageMaxVal{left}'])),
            'threshold_right': int(float(row[f'stageMaxVal{right}'])),
            'coeff_left':      float(row[f'stageMaxGrowVal{left}']),
            'coeff_right':     float(row[f'stageMaxGrowVal{right}']),
            'adjustment':      float(row[f'adjPt_maxGrowVal{left}']),
        })

    values = [0.0]
    for r in ranges:
        for v in range(r['threshold_left'] + 1, r['threshold_right'] + 1):
            corr = calc_correction(
                v, r['threshold_left'], r['threshold_right'],
                r['coeff_left'], r['coeff_right'], r['adjustment']
            )
            values.append(corr / 100.0)

    # Pad to 150 entries with the last known value (caps at hard cap 99 anyway)
    while len(values) < 150:
        values.append(values[-1])

    return values[:150]


def run():
    csv_path = '/srv/ch-webserver/CalcCorrectGraph.csv'
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        rows = list(reader)

    print(f'Parsing {len(rows)} correction graph rows...')

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_correction_graphs WHERE game='elden_ring'"))
        inserted = 0
        for row in rows:
            row_id = int(row['Row ID'])
            name = (row.get('Row Name') or '').strip() or None
            curve = build_curve(row)
            conn.execute(text(
                "INSERT INTO sl_correction_graphs (id, name, curve_json, game) "
                "VALUES (:id, :name, :curve, 'elden_ring')"
            ), {'id': row_id, 'name': name, 'curve': json.dumps(curve)})
            inserted += 1
            print(f'  id={row_id:>4} name={name or "(unnamed)":<40} '
                  f'curve[20]={curve[20]:.3f} curve[60]={curve[60]:.3f} curve[99]={curve[99]:.3f}')
        conn.commit()

    print(f'\nDone. {inserted} correction graphs seeded.')


if __name__ == '__main__':
    run()
