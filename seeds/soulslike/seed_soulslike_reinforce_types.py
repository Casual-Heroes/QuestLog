"""
Seed reinforcement type data for max-level AR calculation.
Extracts from regulation.bin files and stores ONLY the max-level multipliers
(since the builder always shows max upgrade AR).

For ERR: attack scales with upgrades, but scaling does NOT increase with upgrades
(ERR wiki: "Upgrading an armament will no longer increase its attribute scaling").
So for ERR we store max attack multiplier but scaling multiplier = 1.0 for all stats.

Run: chwebsiteprj/bin/python3 seed_soulslike_reinforce_types.py
"""
import json, django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

ER_FILE  = '/srv/ch-webserver/regulation-vanilla-v1.14.js'
ERR_FILE = '/srv/ch-webserver/regulation-reforged-v2.2.3.4.js'


def process_regulation(filepath, game, apply_scaling_mult=True):
    with open(filepath) as f:
        data = json.load(f)

    reinforce_types = data['reinforceTypes']
    weapons = data['weapons']

    # Build: reinforceTypeId -> max level multipliers
    reinforce_max = {}
    for rid_str, levels in reinforce_types.items():
        rid = int(rid_str)
        if not levels:
            continue
        max_level = len(levels) - 1  # 0-indexed: 26 entries = levels 0-25
        max_entry = levels[max_level]
        reinforce_max[rid] = {
            'max_level': max_level,
            'attack': max_entry.get('attack', {}),
            'scaling': max_entry.get('attributeScaling', {}) if apply_scaling_mult else {},
        }

    # Build weapon -> reinforceTypeId mapping (use affinityId=0 Standard as canonical)
    weapon_reinforce = {}
    for w in weapons:
        name = w['weaponName']
        rid  = w.get('reinforceTypeId', 0)
        if name not in weapon_reinforce:
            weapon_reinforce[name] = rid

    return reinforce_max, weapon_reinforce


def seed(conn, game, reinforce_max, weapon_reinforce):
    # Seed reinforce types
    conn.execute(text('DELETE FROM sl_reinforce_types WHERE game=:g'), {'g': game})
    for rid, data in reinforce_max.items():
        conn.execute(text('''
            INSERT INTO sl_reinforce_types (id, game, max_attack_mult, max_scaling_mult, max_level)
            VALUES (:id, :g, :atk, :scl, :ml)
        '''), {
            'id': rid, 'g': game,
            'atk': json.dumps(data['attack']),
            'scl': json.dumps(data['scaling']),
            'ml':  data['max_level'],
        })
    print(f'  Seeded {len(reinforce_max)} reinforce types for {game}')

    # Update sl_weapon_ar_data with reinforce_type_id
    updated = 0
    for weapon_name, rid in weapon_reinforce.items():
        r = conn.execute(text(
            'UPDATE sl_weapon_ar_data SET reinforce_type_id=:rid WHERE weapon_name=:n AND game=:g'
        ), {'rid': rid, 'n': weapon_name, 'g': game})
        updated += r.rowcount
    print(f'  Updated reinforce_type_id on {updated} weapon AR rows for {game}')


def run():
    print('Processing ER regulation...')
    er_rt, er_wr = process_regulation(ER_FILE, 'elden_ring', apply_scaling_mult=True)

    print('Processing ERR regulation...')
    # ERR: apply_scaling_mult=False because ERR weapons don't gain scaling from upgrades
    err_rt, err_wr = process_regulation(ERR_FILE, 'err', apply_scaling_mult=False)

    with engine.begin() as conn:
        seed(conn, 'elden_ring', er_rt, er_wr)
        seed(conn, 'err', err_rt, err_wr)

        # Verify
        er_rt_count = conn.execute(text('SELECT COUNT(*) FROM sl_reinforce_types WHERE game="elden_ring"')).fetchone()[0]
        err_rt_count = conn.execute(text('SELECT COUNT(*) FROM sl_reinforce_types WHERE game="err"')).fetchone()[0]
        er_w_count = conn.execute(text('SELECT COUNT(*) FROM sl_weapon_ar_data WHERE game="elden_ring" AND reinforce_type_id IS NOT NULL')).fetchone()[0]
        err_w_count = conn.execute(text('SELECT COUNT(*) FROM sl_weapon_ar_data WHERE game="err" AND reinforce_type_id IS NOT NULL')).fetchone()[0]
        print(f'\nFinal: ER reinforce types={er_rt_count}, ER weapons updated={er_w_count}')
        print(f'       ERR reinforce types={err_rt_count}, ERR weapons updated={err_w_count}')

        # Spot check: Uchigatana +25 should be ~282 phy at base stats
        r = conn.execute(text('''
            SELECT ar.attack_json, ar.attribute_scaling_json, ar.reinforce_type_id,
                   rt.max_attack_mult, rt.max_scaling_mult
            FROM sl_weapon_ar_data ar
            JOIN sl_reinforce_types rt ON rt.id=ar.reinforce_type_id AND rt.game=ar.game
            WHERE ar.weapon_name="Uchigatana" AND ar.affinity="Standard" AND ar.game="elden_ring"
        ''')).fetchone()
        if r:
            base_atk = json.loads(r[0])
            base_scl = json.loads(r[1])
            atk_mult = json.loads(r[3])
            scl_mult = json.loads(r[4])
            max_phy = float(base_atk.get('0', 0)) * float(atk_mult.get('0', 1))
            max_dex_scl = float(base_scl.get('dex', 0)) * float(scl_mult.get('dex', 1))
            print(f'\nUchigatana Standard +25: base_phy={base_atk.get("0")} x {atk_mult.get("0")} = {max_phy:.1f}')
            print(f'  DEX scaling: {base_scl.get("dex")} x {scl_mult.get("dex")} = {max_dex_scl:.3f}')


if __name__ == '__main__':
    run()
