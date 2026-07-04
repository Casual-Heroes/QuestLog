"""
Seed: per-weapon, per-affinity AR scaling data extracted directly from
EquipParamWeapon.csv and AttackElementCorrectParam.csv (erdb project,
sourced from the game's own regulation.bin - exact, not approximated).

Run: chwebsiteprj/bin/python3 seed_soulslike_weapon_ar_data.py
"""
import csv
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

WEAPON_CSV = '/srv/ch-webserver/EquipParamWeapon.csv'
AEC_CSV = '/srv/ch-webserver/AttackElementCorrectParam.csv'

# Affinity name as it appears in the bracket suffix -> our canonical affinity name
AFFINITY_SUFFIXES = {
    '': 'Standard',
    'Heavy': 'Heavy',
    'Keen': 'Keen',
    'Quality': 'Quality',
    'Fire': 'Fire',
    'Flame Art': 'Flame Art',
    'Lightning': 'Lightning',
    'Sacred': 'Sacred',
    'Magic': 'Magic',
    'Cold': 'Cold',
    'Poison': 'Poison',
    'Blood': 'Blood',
    'Occult': 'Occult',
}


def parse_weapon_name(row_name):
    """'Uchigatana [Heavy]' -> ('Uchigatana', 'Heavy'). 'Uchigatana' -> ('Uchigatana', 'Standard')."""
    row_name = row_name.strip()
    if row_name.endswith(']') and '[' in row_name:
        base, _, bracket = row_name.rpartition('[')
        base = base.strip()
        affinity_raw = bracket.rstrip(']').strip()
        affinity = AFFINITY_SUFFIXES.get(affinity_raw, affinity_raw)
        return base, affinity
    return row_name, 'Standard'


def seed_attack_element_correct():
    print('=== Seeding sl_attack_element_correct ===')
    with open(AEC_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        rows = list(reader)

    damage_types = [
        ('byPhysics', 'physical'),
        ('byMagic', 'magic'),
        ('byFire', 'fire'),
        ('byThunder', 'lightning'),
        ('byDark', 'holy'),
    ]

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_attack_element_correct WHERE game='elden_ring'"))
        inserted = 0
        for row in rows:
            row_id = row['Row ID']
            if not row_id.isdigit():
                continue
            for suffix, dmg_type in damage_types:
                try:
                    str_en = int(row.get(f'isStrengthCorrect_{suffix}', 0) or 0)
                    dex_en = int(row.get(f'isDexterityCorrect_{suffix}', 0) or 0)
                    int_en = int(row.get(f'isMagicCorrect_{suffix}', 0) or 0)
                    fai_en = int(row.get(f'isFaithCorrect_{suffix}', 0) or 0)
                    arc_en = int(row.get(f'isLuckCorrect_{suffix}', 0) or 0)
                    str_ra = int(float(row.get(f'InfluenceStrengthCorrectRate_{suffix}', 100) or 100))
                    dex_ra = int(float(row.get(f'InfluenceDexterityCorrectRate_{suffix}', 100) or 100))
                    int_ra = int(float(row.get(f'InfluenceMagicCorrectRate_{suffix}', 100) or 100))
                    fai_ra = int(float(row.get(f'InfluenceFaithCorrectRate_{suffix}', 100) or 100))
                    arc_ra = int(float(row.get(f'InfluenceLuckCorrectRate_{suffix}', 100) or 100))
                except (ValueError, TypeError):
                    continue

                composite_id = int(row_id) * 10 + damage_types.index((suffix, dmg_type))
                conn.execute(text("""
                    INSERT INTO sl_attack_element_correct
                        (id, damage_type, str_enabled, dex_enabled, int_enabled, fai_enabled, arc_enabled,
                         str_ratio, dex_ratio, int_ratio, fai_ratio, arc_ratio, game)
                    VALUES (:id, :dmg, :se, :de, :ie, :fe, :ae, :sr, :dr, :ir, :fr, :ar, 'elden_ring')
                """), {
                    'id': composite_id, 'dmg': dmg_type,
                    'se': str_en, 'de': dex_en, 'ie': int_en, 'fe': fai_en, 'ae': arc_en,
                    'sr': str_ra, 'dr': dex_ra, 'ir': int_ra, 'fr': fai_ra, 'ar': arc_ra,
                })
                inserted += 1
        conn.commit()
    print(f'  {inserted} AEC entries seeded')


def seed_weapon_ar_data():
    print('=== Seeding sl_weapon_ar_data ===')
    with open(WEAPON_CSV, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        all_rows = [r for r in reader if r.get('Row Name', '').strip()]

    print(f'  Total named weapon rows in CSV: {len(all_rows)}')

    # Get the set of weapon names we actually have in our DB
    with engine.connect() as conn:
        our_weapons = {r[0] for r in conn.execute(text(
            "SELECT DISTINCT name FROM sl_weapons WHERE game='elden_ring'"
        )).fetchall()}

    print(f'  Weapons in our DB: {len(our_weapons)}')

    inserted = 0
    skipped_no_match = 0

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM sl_weapon_ar_data WHERE game='elden_ring'"))
        for row in all_rows:
            base_name, affinity = parse_weapon_name(row['Row Name'])
            if base_name not in our_weapons:
                skipped_no_match += 1
                continue

            try:
                conn.execute(text("""
                    INSERT INTO sl_weapon_ar_data
                        (weapon_name, affinity, base_phy, base_mag, base_fire, base_lit, base_hol,
                         correct_type_phy, correct_type_mag, correct_type_fire, correct_type_lit, correct_type_hol,
                         correct_str, correct_dex, correct_int, correct_fai, correct_arc,
                         attack_element_correct_id, game)
                    VALUES
                        (:name, :aff, :phy, :mag, :fire, :lit, :hol,
                         :ctp, :ctm, :ctf, :ctl, :cth,
                         :cstr, :cdex, :cint, :cfai, :carc,
                         :aec, 'elden_ring')
                """), {
                    'name': base_name, 'aff': affinity,
                    'phy': int(float(row['attackBasePhysics'] or 0)),
                    'mag': int(float(row['attackBaseMagic'] or 0)),
                    'fire': int(float(row['attackBaseFire'] or 0)),
                    'lit': int(float(row['attackBaseThunder'] or 0)),
                    'hol': int(float(row.get('attackBaseDark', 0) or 0)),
                    'ctp': int(float(row['correctType_Physics'] or 0)),
                    'ctm': int(float(row.get('correctType_Magic', -1) or -1)),
                    'ctf': int(float(row.get('correctType_Fire', -1) or -1)),
                    'ctl': int(float(row.get('correctType_Thunder', -1) or -1)),
                    'cth': int(float(row.get('correctType_Dark', -1) or -1)),
                    'cstr': int(float(row['correctStrength'] or 0)),
                    'cdex': int(float(row['correctAgility'] or 0)),
                    'cint': int(float(row.get('correctMagic', 0) or 0)),
                    'cfai': int(float(row['correctFaith'] or 0)),
                    'carc': int(float(row.get('correctLuck', 0) or 0)),
                    'aec': int(float(row.get('attackElementCorrectId', 10000) or 10000)),
                })
                inserted += 1
            except Exception as e:
                print(f'  ! Error on {row["Row Name"]}: {e}')
                continue
        conn.commit()

    print(f'  {inserted} weapon/affinity rows inserted, {skipped_no_match} CSV rows had no DB match')


if __name__ == '__main__':
    seed_attack_element_correct()
    seed_weapon_ar_data()
    print('\nDone.')
