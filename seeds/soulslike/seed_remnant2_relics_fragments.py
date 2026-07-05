"""
Seed r2_relics, r2_relic_fragments, r2_fusion_fragments, and update r2_traits.
Data provided directly - no scraping.

Run: chwebsiteprj/bin/python3 seed_remnant2_relics_fragments.py
"""
import django, os, re, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

NOW = int(time.time())

def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

# ── Relics ───────────────────────────────────────────────────────────────────
# (name, dlc, description)
RELICS = [
    ('Bloodless Heart',  'dlc2', 'Innate 50% Use Speed bonus. On use, grants a SHIELD that prevents nearly all damage for 3s.'),
    ('Blooming Heart',   'base', 'On use, heals for 35% of Max Health over 5s. Spawns 3 Healing Orbs which grant 35% of Max Health over 5s. Orbs last 20s.'),
    ('Broken Heart',     'dlc1', 'Passively grants or removes 2 Health per sec until Health reaches 50%. On use, sets Health to 50%.'),
    ('Constrained Heart','base', 'On use, regenerates 20 Health per second for 5s and grants 2 Stacks of BULWARK while heal is active.'),
    ('Crystal Heart',    'base', 'On use, regenerates 100% of Max Health over 10s. Movement Speed reduced by 50%, incoming damage reduced by 25%. Lasts 10s.'),
    ('Decayed Heart',    'base', 'On use, causes the next 3 instances of enemy damage taken to trigger 40 Health regeneration over 3s. Lasts 30s.'),
    ('Diverting Heart',  'base', 'Does not provide standard healing. On use, reduces Skill Cooldowns by 1s per second. Lasts 15s.'),
    ('Dragon Heart',     'base', 'On use, Heals 70 Health over 0.5s.'),
    ('Enlarged Heart',   'base', 'Innate Double Use Speed. On use, heals 140 Health over 0.5s. Relic capacity is halved.'),
    ('Gossamer Heart',   'dlc3', 'Innate base Evade Window Frames increased by 1. On use, increases Evade Window Bonus Frames by 2 for 15s.'),
    ('Latent Heart',     'dlc3', 'On use, absorbs 95% incoming damage for 5s. Upon expiring, absorbed damage is applied at 10% per second for 10s.'),
    ('Lifeless Heart',   'base', 'Innate 50% Use Speed Bonus, provides no healing. Relic capacity is doubled.'),
    ('Paper Heart',      'dlc1', 'On use, heals 100% Max Health and grants 10 Stacks of PAPER HEALTH. After 10s, each Stack converts to 10% Grey Health.'),
    ('Profane Heart',    'dlc2', 'Innate 3% Lifesteal bonus. On use, increases all Lifesteal Efficacy by 50% for 15s.'),
    ('Pulsing Heart',    'base', 'On use, pulses every 3s, healing allies within 7m for 20 Health over 0.5s per pulse. Lasts 15s.'),
    ('Quilted Heart',    'base', 'On use, negates Stamina Drain and causes Evades to heal for 15 Health over 0.25s. Lasts 20s.'),
    ('Reprocessed Heart','base', 'On use, converts 5 Health as Grey Health to 40 Mod Power per second for 25s for both weapons.'),
    ('Resonating Heart', 'base', 'On use, regenerates 50% of Max Health over 5s. Overhealed Health is doubled and awarded over 20s.'),
    ('Ripened Heart',    'base', 'On use, heals 35 Health over 0.5s and an additional 70 over 5s.'),
    ('Runed Heart',      'base', 'On use, increases Health Regeneration by 5 and generates 500 Mod Power over 10s for both weapons.'),
    ('Salvaged Heart',   'base', 'Innate 25% Use Speed bonus. On use, heals 30 Health over 0.25s and restores 300% of current Grey Health.'),
    ('Shielded Heart',   'base', 'On use, grants a SHIELD for 100% of Max Health. Lasts 20s or until SHIELD is removed by damage.'),
    ('Siphon Heart',     'base', 'On use, grants 10% of base damage dealt as Lifesteal for 15s.'),
    ('Tormented Heart',  'base', 'Innate 25% Relic Use Speed bonus. On use, deals 150-450 Explosive Damage to enemies within 5m and Lifesteals 20% of damage dealt.'),
    ('Tranquil Heart',   'base', 'Passively grants 2 Health Regeneration per second. On use, doubles All Health Regeneration for 15s.'),
    ('Unsullied Heart',  'base', 'On use, heals for 100% of Current Health over 0.5s.'),
    ('Void Heart',       'base', 'On use, reduces incoming damage by 50% for 4s. When buff ends, heals 100% of missing Health over 0.75s.'),
]

# ── Relic Fragments ──────────────────────────────────────────────────────────
# (name, fragment_type, effect_value, description)
RELIC_FRAGMENTS = [
    ('Ammo Reserves',         'discipline', '25%',     'Increases Ammo Reserves by 25%.'),
    ('Armor Bonus',           'intellect',  '10%',     'Increases Armor Effectiveness by 10%.'),
    ('Base Armor',            'intellect',  '+15',     'Increases Armor by 15.'),
    ('Base Health',           'intellect',  '+10',     'Increases Health by 10.'),
    ('Base Stamina',          'intellect',  '+15',     'Increases Stamina by 15.'),
    ('Cast Speed',            'discipline', '20%',     'Increases Mod & Skill Cast Speed by 20%.'),
    ('Consumable Duration',   'discipline', '20%',     'Increases Consumable Duration by 20%.'),
    ('Critical Damage',       'power',      '10%',     'Increases Critical Damage by 10%.'),
    ('Damage Reduction',      'intellect',  '5%',      'Increases Damage Reduction by 5%.'),
    ('Evade Distance',        'intellect',  '10%',     'Increases Evade Distance by 10%.'),
    ('Evade Speed',           'intellect',  '10%',     'Increases Evade Speed by 10%.'),
    ('Explosive Damage',      'power',      '10%',     'Increases Explosive Damage by 10%.'),
    ('Firearm Charge Time',   'power',      '-10%',    'Decreases Ranged Weapon Charge Time by 10%.'),
    ('Firearm Swap Speed',    'discipline', '20%',     'Increases Firearm Swap Speed by 20%.'),
    ('Grey Health Conversion','intellect',  '15%',     'Increases Grey Health Conversion Rate by 15%.'),
    ('Healing Effectiveness', 'intellect',  '15%',     'Increases Healing Effectiveness by 15%.'),
    ('Health Bonus',          'intellect',  '10%',     'Increases Health by 10%.'),
    ('Health Regeneration',   'intellect',  '1 HP/s',  'Increases Passive Health Regeneration by 1 HP/s.'),
    ('Heat Generation',       'discipline', '-15%',    'Reduces Heat Generation by 15%.'),
    ('Melee Critical Chance', 'power',      '7.5%',    'Increases Melee Critical Chance by 7.5%.'),
    ('Melee Damage',          'power',      '10%',     'Increases Melee Damage by 10%.'),
    ('Melee Speed',           'power',      '10%',     'Increases Total Melee Attack Speed by 10%.'),
    ('Mod Critical Chance',   'power',      '7.5%',    'Increases Mod Critical Chance by 7.5%.'),
    ('Mod Damage',            'power',      '10%',     'Increases Mod Damage by 10%.'),
    ('Mod Duration',          'discipline', '15%',     'Increases Mod Duration by 15%.'),
    ('Mod Generation',        'discipline', '10%',     'Increases Mod Power Generation by 10%.'),
    ('Movement Speed',        'discipline', '10%',     'Increases Movement Speed by 10%.'),
    ('Projectile Speed',      'discipline', '15%',     'Increases Projectile Speed by 15%.'),
    ('Ranged Critical Chance','power',      '7.5%',    'Increases Ranged Critical Chance by 7.5%.'),
    ('Ranged Damage',         'power',      '10%',     'Increases Ranged Damage by 10%.'),
    ('Ranged Fire Rate',      'power',      '10%',     'Increases Ranged Fire Rate by 10%.'),
    ('Reload Speed',          'discipline', '10%',     'Increases Reload Speed by 10%.'),
    ('Revive Speed',          'intellect',  '20%',     'Increases Revive Speed by 20%.'),
    ('Shield Amount',         'intellect',  '10%',     'Increases Shield Effectiveness by 10%.'),
    ('Shield Duration',       'intellect',  '10%',     'Increases Shield Duration by 10%.'),
    ('Skill Cooldown',        'discipline', '-10%',    'Reduces Skill Cooldowns by 10%.'),
    ('Skill Critical Chance', 'power',      '7.5%',    'Increases Skill Critical Chance by 7.5%.'),
    ('Skill Damage',          'power',      '10%',     'Increases Skill Damage by 10%.'),
    ('Skill Duration',        'discipline', '15%',     'Increases Skill Duration by 15%.'),
    ('Stamina Bonus',         'intellect',  '+15',     'Increases Stamina by 15%.'),
    ('Status Damage',         'power',      '15%',     'Increases Status Effect Damage by 15%.'),
    ('Use Speed',             'discipline', '15%',     'Increases Relic and Consumable Use Speed by 15%.'),
    ('Weakspot Damage',       'power',      '15%',     'Increases Weakspot Damage by 15%.'),
    ('Weapon Ideal Range',    'discipline', '+2m',     'Increases Ideal Weapon Range by 2m.'),
    ('Weapon Spread',         'discipline', '-15%',    'Reduces Weapon Spread by 15%.'),
]

# ── Fusion Fragments ─────────────────────────────────────────────────────────
# (name, fragment1, fragment2, stat1, stat2, val1, val2)
FUSION_FRAGMENTS = [
    ('Athletic',    'Movement Speed',       'Evade Speed',          'Movement Speed',   'Evade Speed',          '10%',   '10%'),
    ('Capacitor',   'Firearm Charge Time',  'Heat Generation',      'Firearm Charge Time','Heat Generation',    '10%',   '10%'),
    ('Cleric',      'Healing Effectiveness','Use Speed',            'Healing Effectiveness','Use Speed',         '15%',   '15%'),
    ('Flash',       'Cast Speed',           'Use Speed',            'Cast Speed',       'Use Speed',            '20%',   '15%'),
    ('Grip',        'Weapon Spread',        'Firearm Swap Speed',   'Weapon Spread',    'Firearm Swap Speed',   '15%',   '20%'),
    ('Gunfighter',  'Ranged Fire Rate',     'Reload Speed',         'Ranged Fire Rate', 'Reload Speed',         '10%',   '10%'),
    ('Hulk',        'Health Bonus',         'Stamina Bonus',        'Health Bonus',     'Stamina Bonus',        '10%',   '15%'),
    ('Longevity',   'Mod Duration',         'Skill Duration',       'Mod Duration',     'Skill Duration',       '15%',   '15%'),
    ('Mage',        'Mod Damage',           'Mod Generation',       'Mod Damage',       'Mod Generation',       '10%',   '10%'),
    ('Meta',        'Weakspot Damage',      'Critical Damage',      'Weakspot Damage',  'Critical Damage',      '15%',   '10%'),
    ('Munitions',   'Ranged Critical Chance','Ammo Reserves',       'Ranged Critical Chance','Ammo Reserves',   '7.5%',  '30%'),
    ('Pirate',      'Ranged Damage',        'Melee Damage',         'Ranged Damage',    'Melee Damage',         '10%',   '10%'),
    ('Protected',   'Shield Amount',        'Base Armor',           'Shield Amount',    'Base Armor',           '10%',   '+15'),
    ('Pugilist',    'Melee Speed',          'Base Stamina',         'Melee Speed',      'Base Stamina',         '15%',   '+10'),
    ('Revitalize',  'Health Regeneration',  'Skill Cooldown',       'Health Regeneration','Skill Cooldown',     '1 HP/s','-10%'),
    ('Rogue',       'Melee Critical Chance','Evade Speed',          'Melee Critical Chance','Evade Speed',       '7.5%',  '10%'),
    ('Sapper',      'Explosive Damage',     'Damage Reduction',     'Explosive Damage', 'Damage Reduction',     '10%',   '5%'),
    ('Selfless',    'Revive Speed',         'Healing Effectiveness','Revive Speed',     'Healing Effectiveness','10%',   '5%'),
    ('Sniper',      'Ranged Damage',        'Weapon Ideal Range',   'Ranged Damage',    'Weapon Ideal Range',   '10%',   '200cm'),
    ('Tank',        'Damage Reduction',     'Armor Bonus',          'Damage Reduction', 'Armor Bonus',          '5%',    '10%'),
    ('Threshold',   'Health Bonus',         'Grey Health Conversion','Health Bonus',    'Grey Health Conversion','10%',  '15%'),
    ('Warrior',     'Melee Damage',         'Melee Speed',          'Melee Damage',     'Melee Speed',          '15%',   '15%'),
]

# ── Updated Traits ────────────────────────────────────────────────────────────
# Complete trait list with category, source, archetype link
# (name, category, max_points, dlc, source, linked_archetype)
TRAITS = [
    # Core
    ('Vigor',           'core',       10, 'base', 'Default',                          None),
    ('Endurance',       'core',       10, 'base', 'Default',                          None),
    ('Spirit',          'core',       10, 'base', 'Default',                          None),
    ('Expertise',       'core',       10, 'base', 'Default',                          None),
    # Archetype
    ('Affliction',      'archetype',  10, 'dlc1', 'Ritualist archetype',              'Ritualist'),
    ('Ammo Reserves',   'archetype',  10, 'base', 'Gunslinger archetype',             'Gunslinger'),
    ('Barrier',         'archetype',  10, 'dlc3', 'Warden archetype',                 'Warden'),
    ('Flash Caster',    'archetype',  10, 'base', 'Archon archetype',                 'Archon'),
    ('Fortify',         'archetype',  10, 'base', 'Engineer archetype',               'Engineer'),
    ('Gifted',          'archetype',  10, 'dlc2', 'Invoker archetype',                'Invoker'),
    ('Kinship',         'archetype',  10, 'base', 'Handler archetype',                'Handler'),
    ('Longshot',        'archetype',  10, 'base', 'Hunter archetype',                 'Hunter'),
    ('Potency',         'archetype',  10, 'base', 'Alchemist archetype',              'Alchemist'),
    ('Regrowth',        'archetype',  10, 'base', 'Summoner archetype',               'Summoner'),
    ('Strong Back',     'archetype',  10, 'base', 'Challenger archetype',             'Challenger'),
    ('Swiftness',       'archetype',  10, 'base', 'Explorer archetype',               'Explorer'),
    ('Triage',          'archetype',  10, 'base', 'Medic archetype',                  'Medic'),
    ('Untouchable',     'archetype',  10, 'base', 'Invader archetype',                'Invader'),
    # Unlockable
    ('Amplitude',       'unlockable', 10, 'base', 'Labyrinth (Campaign)',             None),
    ('Arcane Strike',   'unlockable', 10, 'base', 'Losomn - Harvester\'s Reach',     None),
    ('Barkskin',        'unlockable', 10, 'base', 'Yaesha - Dappled Glade',           None),
    ('Blood Bond',      'unlockable', 10, 'base', 'Yaesha - Root Nexus',              None),
    ('Bloodstream',     'unlockable', 10, 'base', 'Yaesha - Dappled Glade',           None),
    ('Chakra',          'unlockable', 10, 'base', 'Root Earth (Campaign)',             None),
    ('Dark Pact',       'unlockable', 10, 'dlc1', 'Losomn - Forlorn Coast',           None),
    ('Insight',         'unlockable', 10, 'dlc2', 'N\'Erud - The Convergence',        None),
    ('Fitness',         'unlockable', 10, 'base', 'N\'Erud - Vault of the Formless',  None),
    ('Footwork',        'unlockable', 10, 'base', 'N\'Erud - Terminus Station',       None),
    ('Glutton',         'unlockable', 10, 'base', 'Losomn - Great Hall',              None),
    ('Handling',        'unlockable', 10, 'base', 'Root Earth (Campaign)',             None),
    ('Leech',           'unlockable', 10, 'base', 'N\'Erud - Dormant N\'Erudian Facility', None),
    ('Perception',      'unlockable', 10, 'dlc3', 'N\'Erud - Stagnant Manufactory',  None),
    ('Preservation',    'unlockable', 10, 'dlc3', 'N\'Erud - The Dark Horizon',       None),
    ('Recovery',        'unlockable', 10, 'base', 'Losomn - Oracle\'s Refuge',        None),
    ('Resolute',        'unlockable', 10, 'dlc2', 'Yaesha - The Forgotten Kingdom',   None),
    ('Revivalist',      'unlockable', 10, 'base', 'Revive an ally',                   None),
    ('Rugged',          'unlockable', 10, 'base', 'Yaesha - Forgotten Field',         None),
    ('Scholar',         'unlockable', 10, 'base', 'Root Earth (Campaign)',             None),
    ('Shadeskin',       'unlockable', 10, 'base', 'Losomn - Butcher\'s Quarter',      None),
    ('Siphoner',        'unlockable', 10, 'base', 'N\'Erud - Dormant N\'Erudian Facility', None),
]


def main():
    with get_db_session() as db:
        # Relics
        existing = db.execute(text('SELECT COUNT(*) FROM r2_relics')).scalar()
        if existing > 0:
            print(f'Relics already seeded ({existing}). Skipping.')
        else:
            for (name, dlc, desc) in RELICS:
                db.execute(text("""
                    INSERT INTO r2_relics (slug, name, dlc, description, created_at)
                    VALUES (:slug, :name, :dlc, :desc, :now)
                """), {'slug': slugify(name), 'name': name, 'dlc': dlc, 'desc': desc, 'now': NOW})
            db.commit()
            print(f'Seeded {len(RELICS)} relics')

        # Relic Fragments
        existing = db.execute(text('SELECT COUNT(*) FROM r2_relic_fragments')).scalar()
        if existing > 0:
            print(f'Relic fragments already seeded ({existing}). Skipping.')
        else:
            for (name, ftype, val, desc) in RELIC_FRAGMENTS:
                db.execute(text("""
                    INSERT INTO r2_relic_fragments (slug, name, fragment_type, effect_value, description, created_at)
                    VALUES (:slug, :name, :type, :val, :desc, :now)
                """), {'slug': slugify(name), 'name': name, 'type': ftype, 'val': val, 'desc': desc, 'now': NOW})
            db.commit()
            print(f'Seeded {len(RELIC_FRAGMENTS)} relic fragments')

        # Fusion Fragments
        existing = db.execute(text('SELECT COUNT(*) FROM r2_fusion_fragments')).scalar()
        if existing > 0:
            print(f'Fusion fragments already seeded ({existing}). Skipping.')
        else:
            for (name, f1, f2, s1, s2, v1, v2) in FUSION_FRAGMENTS:
                db.execute(text("""
                    INSERT INTO r2_fusion_fragments
                        (slug, name, fragment1, fragment2, stat1, stat2, val1, val2, created_at)
                    VALUES (:slug, :name, :f1, :f2, :s1, :s2, :v1, :v2, :now)
                """), {'slug': slugify(name), 'name': name, 'f1': f1, 'f2': f2,
                       's1': s1, 's2': s2, 'v1': v1, 'v2': v2, 'now': NOW})
            db.commit()
            print(f'Seeded {len(FUSION_FRAGMENTS)} fusion fragments')

        # Traits - add category and source columns if missing, then upsert
        try:
            db.execute(text('ALTER TABLE r2_traits ADD COLUMN category VARCHAR(16) NOT NULL DEFAULT "unlockable" AFTER name'))
            db.execute(text('ALTER TABLE r2_traits ADD COLUMN source VARCHAR(200) AFTER linked_archetype_id'))
            db.commit()
            print('Added category + source columns to r2_traits')
        except Exception:
            pass  # Columns already exist

        # Load archetype IDs
        arch_rows = db.execute(text('SELECT id, name FROM r2_archetypes')).fetchall()
        arch_map = {r[1]: r[0] for r in arch_rows}

        # Clear and re-seed traits with complete data
        db.execute(text('DELETE FROM r2_traits'))
        db.commit()

        for (name, category, max_pts, dlc, source, arch_name) in TRAITS:
            arch_id = arch_map.get(arch_name) if arch_name else None
            db.execute(text("""
                INSERT INTO r2_traits
                    (slug, name, category, max_points, dlc, source, linked_archetype_id, created_at)
                VALUES (:slug, :name, :cat, :max_pts, :dlc, :source, :arch_id, :now)
            """), {'slug': slugify(name), 'name': name, 'cat': category,
                   'max_pts': max_pts, 'dlc': dlc, 'source': source,
                   'arch_id': arch_id, 'now': NOW})
        db.commit()
        total = db.execute(text('SELECT COUNT(*) FROM r2_traits')).scalar()
        print(f'Re-seeded {total} traits (core: 4, archetype: 14, unlockable: {total-18})')

        # Final summary
        print('\nFinal counts:')
        for t in ('r2_relics', 'r2_relic_fragments', 'r2_fusion_fragments', 'r2_traits'):
            c = db.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
            print(f'  {t}: {c}')


if __name__ == '__main__':
    main()
