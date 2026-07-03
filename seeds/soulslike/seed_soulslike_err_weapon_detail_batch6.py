"""
Seed: ERR per-weapon Weight + Critical fill-in, batch 6.
Source: err.fandom.com individual weapon pages, pasted directly by user.

Special case: Immortal Coil was missing entirely from the regulation-reforged-v2.2.3.4.js
dump (confirmed absent earlier this session) - this script INSERTS it as a new row using
the full base stats from its wiki page, rather than just updating weight/critical like
the rest of this batch. Its scaling letters are taken directly from the wiki page since
there's no regulation JSON source to cross-check against. No AR variant data
(sl_weapon_ar_data) is added for it since that requires the full per-affinity
calc-correct-graph data this dump-less weapon doesn't have - it will work for base/
Standard AR display but not full affinity switching in the calculator.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch6.py
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

# (name, weight, critical, passive_effect, fated_effect, acquisition, description)
WEAPONS = [
    ('Gracebound Staff', 4.0, 100,
     "Gain x1.1 Elemental Damage dealt and x0.9 Elemental Damage received against the last elemental "
     "damage type dealt or received, while equipped.",
     None,
     "Found by a grave at the base of a large tree-like rock on the western side of the Consecrated "
     "Snowfield, south of the Apostate Derelict.",
     "Staff fashioned from the living branch of a foreign tree. Once wielded by a tender Tarnished who "
     "fell from grace. Though the guidance of grace might not sway one lost in grief and mourning, "
     "their desertion is not suffered for long. Even in distant lands, the Hold's confessors find "
     "their quarry."),
    ('Grave Spear', 5.5, 100,
     "Cold affinity: causes Frostbite buildup.",
     None,
     "Drops from Skeletal Militiamen who wield it.",
     "Spear comprised of a rusted head affixed to a crooked stick. Weapon wielded by the aged dwellers "
     "of the forgotten graveyards throughout the Lands Between. This weapon is said to have served as "
     "a charm against evil spirits in times of old."),
    ('Iron Spike', 3.0, 160,
     "x1.075 Attack Power of dashing light attacks, x1.08 Attack Power of dashing heavy attacks, "
     "x1.05 Attack Power of jumping attacks, while equipped.",
     None,
     "Obtained from the East Capital Waterfront enemy camp in Leyndell, near the existing group of "
     "Misbegotten.",
     "Hefty iron dagger, sidearm of the Winged Misbegotten. An airborne attacker would find the wide "
     "pommel of the dagger useful for bearing their whole weight as they crash down onto their foe."),
    ("Lordsworn's Spear", 4.5, 105,
     None, None,
     "Found inside the usually empty room at the entrance to Castle Morne.",
     "Well-crafted spear with an illustrious design, wielded by regulars of a lord's army. Though "
     "blackened and damaged by years of use, it appears to have otherwise been kept in a serviceable "
     "condition, despite the soldiers having long since lost their minds."),
    ('Mad Sun Shield', 7.5, 100,
     "x1.05 Attack Power of Frenzied Flame attacks while equipped. Madness in vicinity restores 5%+50 "
     "HP, or 10%+100 HP when triggered from weapon skills. Frenzied affinity: causes Madness buildup.",
     None,
     "Drops from the Flamelost Knights boss in the Buried Audience Pathway (new location added in "
     "Reforged 2.0).",
     "A chaotic image of the flame of frenzy, forged in magma by burn-scarred hands. Inflicts madness "
     "buildup. The atrocities in the hidden compound beneath the mountain could not be allowed to "
     "continue. Together, they vowed to put an end to their master's sins. Another plot, however, saw "
     "their vow unfulfilled, and their souls lost in despair. Unique Skill: Flamelost Sweep - like a "
     "cruel sun, the flame of frenzy is unceasing; sweeps foes with a frontal exhalation of maddening "
     "flames, inflicting Madness buildup on both user and struck foes."),
]

# Immortal Coil - full insert since it's missing from the regulation dump entirely.
IMMORTAL_COIL = {
    'name': 'Immortal Coil',
    'weapon_type': 'Thrusting Sword',
    'physical_damage': 0, 'magic_damage': 0, 'fire_damage': 0, 'lightning_damage': 0, 'holy_damage': 79,
    'critical': 100, 'weight': 3.0,
    'str_scaling': '-', 'dex_scaling': '-', 'int_scaling': 'D', 'fai_scaling': 'D', 'arc_scaling': '-',
    'str_requirement': 0, 'dex_requirement': 0, 'int_requirement': 27, 'fai_requirement': 27,
    'arc_requirement': 0,
    'is_somber': 1,
}
IMMORTAL_COIL_PASSIVE = (
    "Dual Weapon Catalyst capable of casting both sorceries and incantations; otherwise considered a "
    "Thrusting Sword dealing pure Holy damage. While equipped: x1.05 Attack Power to Hornsent "
    "incantations, x1.05 Attack Power to Ghostflame sorceries. Unique Skill: Empyrean Piercer - focus "
    "the crucible current and expel it forward with a motion rooted in divine calculus; hitting a foe "
    "grants x1.11 Attack Power of spells for 25 seconds."
)
IMMORTAL_COIL_ACQ = "Found at Spiral Rise in Enir-Ilim, in the Realm of Shadow (DLC)."
IMMORTAL_COIL_DESC = (
    "Ultimate treasure of the white tower, a formless blade woven from a perfect spiral. One of the "
    "legendary armaments. Binding wild and free forces from the heavens into rational harmony, this "
    "blade effortlessly channels both sorceries and incantations. Fervor tempered by discernment has "
    "ever been the mark of lords and gods, speeding them to untold heights."
)


def run():
    with engine.connect() as conn:
        updated = 0
        for name, weight, crit, passive, fated, acquisition, description in WEAPONS:
            result = conn.execute(text("""
                UPDATE sl_weapons SET weight = :weight, critical = :crit
                WHERE game = 'err' AND name = :name
            """), {'weight': weight, 'crit': crit, 'name': name})
            if result.rowcount:
                updated += 1
            else:
                print(f'  NOT FOUND in sl_weapons: {name}')

            if passive or fated or acquisition or description:
                conn.execute(text("DELETE FROM sl_err_weapon_passives WHERE weapon_name=:name"), {'name': name})
                conn.execute(text("""
                    INSERT INTO sl_err_weapon_passives
                        (weapon_name, passive_effect, fated_effect, acquisition, description)
                    VALUES (:name, :passive, :fated, :acq, :desc)
                """), {
                    'name': name, 'passive': passive, 'fated': fated,
                    'acq': acquisition, 'desc': description,
                })
        conn.commit()
        print(f'{updated}/{len(WEAPONS)} existing weapons updated with weight + critical.')

        # Insert Immortal Coil as a brand-new row
        existing = conn.execute(text(
            "SELECT id FROM sl_weapons WHERE game='err' AND name='Immortal Coil'"
        )).fetchone()
        if existing:
            print('Immortal Coil already exists, skipping insert.')
        else:
            conn.execute(text("""
                INSERT INTO sl_weapons
                    (game, name, weapon_type, physical_damage, magic_damage, fire_damage,
                     lightning_damage, holy_damage, critical, weight,
                     str_scaling, dex_scaling, int_scaling, fai_scaling, arc_scaling,
                     str_requirement, dex_requirement, int_requirement, fai_requirement, arc_requirement,
                     is_somber, created_at)
                VALUES
                    ('err', :name, :wtype, :phy, :mag, :fire, :lit, :hol, :crit, :weight,
                     :ss, :ds, :is2, :fs, :as2,
                     :sr, :dr, :ir, :fr, :ar, :somber, :ts)
            """), {
                'name': IMMORTAL_COIL['name'], 'wtype': IMMORTAL_COIL['weapon_type'],
                'phy': IMMORTAL_COIL['physical_damage'], 'mag': IMMORTAL_COIL['magic_damage'],
                'fire': IMMORTAL_COIL['fire_damage'], 'lit': IMMORTAL_COIL['lightning_damage'],
                'hol': IMMORTAL_COIL['holy_damage'], 'crit': IMMORTAL_COIL['critical'],
                'weight': IMMORTAL_COIL['weight'],
                'ss': IMMORTAL_COIL['str_scaling'], 'ds': IMMORTAL_COIL['dex_scaling'],
                'is2': IMMORTAL_COIL['int_scaling'], 'fs': IMMORTAL_COIL['fai_scaling'],
                'as2': IMMORTAL_COIL['arc_scaling'],
                'sr': IMMORTAL_COIL['str_requirement'], 'dr': IMMORTAL_COIL['dex_requirement'],
                'ir': IMMORTAL_COIL['int_requirement'], 'fr': IMMORTAL_COIL['fai_requirement'],
                'ar': IMMORTAL_COIL['arc_requirement'], 'somber': IMMORTAL_COIL['is_somber'], 'ts': NOW,
            })
            conn.execute(text("DELETE FROM sl_err_weapon_passives WHERE weapon_name='Immortal Coil'"))
            conn.execute(text("""
                INSERT INTO sl_err_weapon_passives
                    (weapon_name, passive_effect, fated_effect, acquisition, description)
                VALUES ('Immortal Coil', :passive, NULL, :acq, :desc)
            """), {
                'passive': IMMORTAL_COIL_PASSIVE, 'acq': IMMORTAL_COIL_ACQ, 'desc': IMMORTAL_COIL_DESC,
            })
            conn.commit()
            print('Immortal Coil inserted as new weapon (base AR only - no affinity variant data, '
                  'since the source dump never had it).')


if __name__ == '__main__':
    run()
