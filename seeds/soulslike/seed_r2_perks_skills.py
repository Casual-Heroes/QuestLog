"""
Re-seed r2_perks and r2_skills with correct data from Fextralife.
Run: chwebsiteprj/bin/python3 seed_r2_perks_skills.py
"""
import django, os, re, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

NOW = int(time.time())
PERK_TYPES = ['prime', 'damage', 'team', 'utility', 'relic']

def slugify(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

ARCHETYPE_DATA = {
    'Alchemist': {
        'perks':  ['Spirited', 'Liquid Courage', 'Panacea', 'Gold to Lead', 'Experimentalist'],
        'skills': ['Vial: Stone Mist', 'Vial: Frenzy Dust', 'Vial: Elixir of Life'],
    },
    'Archon': {
        'perks':  ['Tempest', 'Amplify', 'Power Creep', 'Spirit Within', 'Power Leak'],
        'skills': ['Reality Rune', 'Havoc Form', 'Chaos Gate'],
    },
    'Challenger': {
        'perks':  ['Die Hard', 'Close Quarters', 'Intimidating Presence', 'Powerlifter', 'Face of Danger'],
        'skills': ['War Stomp', 'Juggernaut', 'Rampage'],
    },
    'Engineer': {
        'perks':  ['High Tech', 'Metalworker', 'Magnetic Field', 'Heavy Mobility', 'Surplus'],
        'skills': ['Heavy Weapon: Vulcan', 'Heavy Weapon: Impact Cannon', 'Heavy Weapon: Flamethrower'],
    },
    'Explorer': {
        'perks':  ['Lucky', 'Scavenger', 'Metal Detector', 'Prospector', 'Self Discovery'],
        'skills': ['Plainswalker', 'Gold Digger', 'Fortune Hunter'],
    },
    'Gunslinger': {
        'perks':  ['Loaded', 'Swift Shot', 'Posse Up', 'Quick Hands', 'Sleight of Hand'],
        'skills': ['Quick Draw', 'Side Winder', 'Bullet Storm'],
    },
    'Handler': {
        'perks':  ['Bonded', 'Pack Hunter', 'Spirit of the Wolf', 'Teamwork', 'Best Friend'],
        'skills': ['Guard Dog', 'Support Dog', 'Attack Dog'],
    },
    'Hunter': {
        'perks':  ['Dead to Rights', 'Deadeye', 'Return to Sender', 'Urgency', 'Intuition'],
        'skills': ["Hunter's Mark", "Hunter's Focus", "Hunter's Shroud"],
    },
    'Invader': {
        'perks':  ['Shadow', 'S.H.A.R.K.', 'Loophole', 'Circumvent', 'Override'],
        'skills': ['Worm Hole', 'Void Cloak', 'Reboot'],
    },
    'Invoker': {
        'perks':  ['Visionary', 'Entranced', 'Communion', 'Mind and Body', 'Soothsayer'],
        'skills': ['Way of Kaeula', 'Way of Meidra', 'Way of Lydusa'],
    },
    'Medic': {
        'perks':  ['Regenerator', 'Invigorated', 'Benevolence', 'Backbone', 'Benefactor'],
        'skills': ['Wellspring', 'Healing Shield', 'Redemption'],
    },
    'Ritualist': {
        'perks':  ['Vile', 'Wrath', 'Terrify', 'Dark Blood', 'Purge'],
        'skills': ['Eruption', 'Miasma', 'Death Wish'],
    },
    'Summoner': {
        'perks':  ['Ruthless', 'Dominator', 'Residue', 'Outrage', 'Incite'],
        'skills': ['Minion: Reaver', 'Minion: Hollow', 'Minion: Flyer'],
    },
    'Warden': {
        'perks':  ['Dynamic', 'Galvanize', 'Safeguard', 'Contingency', 'Energize'],
        'skills': ['Drone: Shield', 'Drone: Heal', 'Drone: Combat'],
    },
}

def main():
    with get_db_session() as db:
        db.execute(text('DELETE FROM r2_perks'))
        db.execute(text('DELETE FROM r2_skills'))
        db.commit()

        arch_rows = db.execute(text('SELECT id, name, dlc FROM r2_archetypes')).fetchall()
        arch_map = {r[1]: (r[0], r[2]) for r in arch_rows}

        total_perks = total_skills = 0
        for arch_name, data in ARCHETYPE_DATA.items():
            if arch_name not in arch_map:
                print(f'  WARNING: {arch_name} not found in DB')
                continue
            arch_id, dlc = arch_map[arch_name]

            for i, perk_name in enumerate(data['perks']):
                ptype = PERK_TYPES[i] if i < 5 else 'utility'
                db.execute(text('''
                    INSERT INTO r2_perks (slug, name, archetype_id, perk_type, dlc, created_at)
                    VALUES (:slug, :name, :aid, :ptype, :dlc, :now)
                '''), {
                    'slug': slugify(perk_name + '-' + arch_name),
                    'name': perk_name, 'aid': arch_id,
                    'ptype': ptype, 'dlc': dlc or 'base', 'now': NOW,
                })
                total_perks += 1

            for skill_name in data['skills']:
                db.execute(text('''
                    INSERT INTO r2_skills (slug, name, archetype_id, dlc, created_at)
                    VALUES (:slug, :name, :aid, :dlc, :now)
                '''), {
                    'slug': slugify(skill_name + '-' + arch_name),
                    'name': skill_name, 'aid': arch_id,
                    'dlc': dlc or 'base', 'now': NOW,
                })
                total_skills += 1

        db.commit()
        print(f'Seeded {total_perks} perks, {total_skills} skills')
        rows = db.execute(text('SELECT perk_type, COUNT(*) FROM r2_perks GROUP BY perk_type')).fetchall()
        for r in rows:
            print(f'  {r[0]}: {r[1]}')

if __name__ == '__main__':
    main()
