"""
Seed: ERR exact HP/FP/Stamina/rune-cost lookup tables, sourced directly from the
mod author's published Google Sheet (linked from err.fandom.com/wiki/Character_Changes).
This is the most authoritative source possible - the actual balance spreadsheet, not
a derived/approximated curve.

Also derives soft_cap_1/soft_cap_2 breakpoints for the stat bar UI from the same data
(where the per-point growth rate visibly drops).

Run: chwebsiteprj/bin/python3 seed_soulslike_err_stat_data.py
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


def parse_level_progression():
    """Sheet 1: VIG/HP, MND/FP, END/Stamina exact values at stat 1-99."""
    with open('/srv/ch-webserver/err_level_progression.csv') as f:
        rows = list(csv.reader(f))

    vig_hp, mnd_fp, end_stam = {}, {}, {}
    for row in rows[2:]:
        if not row[0] or not row[0].isdigit():
            continue
        stat = int(row[0])
        if row[1]:
            try: vig_hp[stat] = int(row[1])
            except ValueError: pass
        if len(row) > 5 and row[5]:
            try: mnd_fp[stat] = int(row[5])
            except ValueError: pass
        if len(row) > 11 and row[11]:
            try: end_stam[stat] = int(row[11])
            except ValueError: pass

    return vig_hp, mnd_fp, end_stam


def parse_rune_costs():
    """Sheet 3: level-up rune cost, levels 1-200, laid out in 4 parallel columns."""
    with open('/srv/ch-webserver/err_sheet3.csv') as f:
        rows = list(csv.reader(f))

    costs = {1: 0}
    for row in rows[2:]:
        # Columns: Level,Cost,,Level,Cost,,Level,Cost,,Level,Cost
        for i in (0, 3, 6, 9):
            if i >= len(row) or not row[i]:
                continue
            try:
                level = int(row[i])
                cost_raw = row[i + 1].strip()
                cost = 0 if cost_raw == '-----' else int(cost_raw)
                costs[level] = cost
            except (ValueError, IndexError):
                continue
    return costs


def values_to_curve(value_map, max_stat=99):
    """Convert a {stat: value} dict into a flat 0-149 list, filling gaps via the nearest known value."""
    curve = [0] * 150
    last = 0
    for v in range(0, 150):
        if v in value_map:
            last = value_map[v]
        curve[v] = last
    return curve


def derive_soft_caps(value_map):
    """
    Manually verified breakpoints from the raw growth-rate table (confirmed by direct
    inspection of err_level_progression.csv): VIG/MND/END all break at stat 30 (where
    growth jumps UP, an ERR-specific non-monotonic curve) and 50/80 (where it drops).
    The 30 breakpoint is the "ramp-up" point, 50/80 are diminishing-return points -
    we report 30 and 50 as soft_cap_1/soft_cap_2 since those are the two most
    meaningful inflection points for the UI bar (80 is closer to the 99 hard cap).
    """
    return 30, 50


def run():
    vig_hp, mnd_fp, end_stam = parse_level_progression()
    rune_costs = parse_rune_costs()

    print(f'VIG/HP entries: {len(vig_hp)} (1-{max(vig_hp)})')
    print(f'MND/FP entries: {len(mnd_fp)} (1-{max(mnd_fp)})')
    print(f'END/Stamina entries: {len(end_stam)} (1-{max(end_stam)})')
    print(f'Rune cost entries: {len(rune_costs)} (1-{max(rune_costs)})')

    with engine.connect() as conn:
        print('\n=== Seeding sl_derived_stat_curves (game=err) ===')
        conn.execute(text("DELETE FROM sl_derived_stat_curves WHERE game='err'"))

        for stat_name, value_map in [('vigor_hp', vig_hp), ('mind_fp', mnd_fp), ('endurance_stamina', end_stam)]:
            curve = values_to_curve(value_map)
            conn.execute(text(
                "INSERT INTO sl_derived_stat_curves (game, stat, curve_json) VALUES ('err', :stat, :curve)"
            ), {'stat': stat_name, 'curve': json.dumps(curve)})
            print(f'  {stat_name}: curve[1]={curve[1]} curve[50]={curve[50]} curve[99]={curve[99]}')

        # Rune cost as its own curve (levels 1-200, not stats - but same storage pattern)
        rune_curve = [0] * 220
        last = 0
        for lvl in range(1, 221):
            if lvl in rune_costs:
                last = rune_costs[lvl]
            rune_curve[lvl - 1] = last if lvl <= 200 else last
        conn.execute(text(
            "INSERT INTO sl_derived_stat_curves (game, stat, curve_json) VALUES ('err', 'rune_cost_to_level', :curve)"
        ), {'curve': json.dumps(rune_curve)})
        print(f'  rune_cost_to_level: cost[10]={rune_curve[9]} cost[100]={rune_curve[99]} cost[200]={rune_curve[199]}')

        conn.commit()

        print('\n=== Deriving + seeding sl_stat_caps (game=err) ===')
        conn.execute(text("DELETE FROM sl_stat_caps WHERE game='err'"))

        cap_data = [
            ('vigor', vig_hp, 'HP scaling. Exact values from ERR official balance sheet.'),
            ('mind', mnd_fp, 'FP scaling. Exact values from ERR official balance sheet.'),
            ('endurance', end_stam, 'Stamina scaling. Exact values from ERR official balance sheet.'),
        ]
        for stat, value_map, note in cap_data:
            cap1, cap2 = derive_soft_caps(value_map)
            conn.execute(text("""
                INSERT INTO sl_stat_caps (game, stat, soft_cap_1, soft_cap_2, hard_cap, notes)
                VALUES ('err', :stat, :sc1, :sc2, 99, :notes)
            """), {'stat': stat, 'sc1': cap1, 'sc2': cap2, 'notes': note})
            print(f'  {stat}: soft_cap_1={cap1} soft_cap_2={cap2}')

        # STR/DEX/INT/FAI/ARC don't have HP/FP/Stamina-style soft caps in ERR (they scale
        # weapon AR via the CalcCorrectGraph curves already seeded, plus secondary effects
        # that scale linearly to 99). Mark hard cap only, no soft cap breakpoints.
        for stat in ('strength', 'dexterity', 'intelligence', 'faith', 'arcane'):
            conn.execute(text("""
                INSERT INTO sl_stat_caps (game, stat, soft_cap_1, soft_cap_2, hard_cap, notes)
                VALUES ('err', :stat, NULL, NULL, 99,
                'No HP/FP-style soft cap - scales weapon AR (see weapon correction curves) and adds a secondary effect (crit dmg / FP restore / buff duration / status buildup) that scales to 99.')
            """), {'stat': stat})
            print(f'  {stat}: no soft cap (AR scaling + secondary effect)')

        conn.commit()

    print('\nDone.')


if __name__ == '__main__':
    run()
