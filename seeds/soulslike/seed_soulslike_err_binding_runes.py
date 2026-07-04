"""
Seed: ERR individual Binding Runes for all 7 Great Rune categories + Ascended Runes.
Source: err.fandom.com/wiki/Runeforging, pasted directly by user.

Effect text format: "base value (max forged value) effect description" - matches the
wiki's "x1 forge" vs "max forges" column convention. Max forge count is 4 for Grafted
Runes, 10 for the other 6 Great Rune categories, 100 for Ascended Runes (see category
stubs in sl_err_runeforging for the forge counts/costs).

Run: chwebsiteprj/bin/python3 seed_soulslike_err_binding_runes.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (rune_category_name, [(name, effect_text), ...])
BINDING_RUNES = {
    'Grafted Runes': [
        ('Grafted Vigor', '+1 (+4) Vigor'),
        ('Grafted Mind', '+1 (+4) Mind'),
        ('Grafted Endurance', '+1 (+4) Endurance'),
        ('Grafted Strength', '+1 (+4) Strength'),
        ('Grafted Dexterity', '+1 (+4) Dexterity'),
        ('Grafted Intelligence', '+1 (+4) Intelligence'),
        ('Grafted Faith', '+1 (+4) Faith'),
        ('Grafted Arcane', '+1 (+4) Arcane'),
    ],
    'Cradled Runes': [
        ('Cradled Focus', 'x1.007 (x1.07) Max FP'),
        ('Cradled Starlight', '0.01%+1 (0.1%+4) FP Regen every 2 seconds (in combat)'),
        ('Cradled Consumption', 'x0.996 (x0.96) FP Cost of spells'),
        ('Cradled Night', 'x0.988 (x0.88) Enemy Vision / Enemy Hearing'),
    ],
    'Leonine Runes': [
        ('Leonine Stamina', 'x1.008 (x1.08) Max Stamina'),
        ('Leonine Consumption', 'x0.993 (x0.93) FP Cost of skills'),
        ('Leonine Weight', 'x1.004 (x1.04) Equip Load'),
        ('Leonine Reach', 'x1.006 (x1.06) Attack Range, +3 (+30) Projectile Range'),
    ],
    'Covetous Runes': [
        ('Covetous Gold', 'x1.005 (x1.05) Rune Gain, x1.004 (x1.04) HP Restoration'),
        ('Covetous Silver', '+8 (+80) Item Discovery, FP restoration from attacks (exact value '
                              'unverified)'),
        ('Covetous Age', 'x1.015 (x1.15) Common Buff Duration'),
        ('Covetous Immunity', '+8 (+80) Immunity'),
    ],
    'Cursed Runes': [
        ('Cursed Health', 'x1.006 (x1.06) Max HP'),
        ('Cursed Vitality', '+8 (+80) Vitality'),
        ('Cursed Determination', 'x0.995 (x0.95) Stamina Cost'),
        ('Cursed Resolve', 'x1.01 (x1.11) Poise'),
    ],
    'Tainted Runes': [
        ('Tainted Resistance', 'x0.995 (x0.95) Status Buildup received'),
        ('Tainted Robustness', '+8 (+80) Robustness'),
        ('Tainted Consumption', 'x0.990 (x0.9) FP Cost of consumables'),
        ('Tainted Projection', '+5 (+50) Cast Speed'),
    ],
    'Scarlet Runes': [
        ('Scarlet Concentration', '+8 (+80) Concentration'),
        ('Scarlet Swiftness', 'x1.006 (x1.06) Movement Speed'),
        ('Scarlet Stability', 'x0.992 (x0.92) Stamina Cost of blocks'),
        ('Scarlet Persistence', '+2 (+20) Stamina Regen'),
    ],
    'Ascended Binding Runes': [
        ('Ascended Power', 'x1.001 (x1.1) Attack Power'),
        ('Ascended Negation', 'x0.999 (x0.9) Damage Taken'),
    ],
}

ASCENDED_NOTE = (
    "Starting in NG+, an Ascended selection of Binding Runes becomes available. Each Ascended Rune can "
    "be forged up to a maximum of 100 times."
)


MAX_FORGES = {
    'Grafted Runes': 4,
    'Ascended Binding Runes': 100,
}


def run():
    with engine.connect() as conn:
        # Update the Ascended category stub with its max_forges + note now that we know it
        conn.execute(text("""
            UPDATE sl_err_runeforging
            SET max_forges = 100, content = :note
            WHERE section = 'category' AND rune_category_name = 'Ascended Binding Runes'
        """), {'note': ASCENDED_NOTE})

        total = 0
        for category, runes in BINDING_RUNES.items():
            max_forge = MAX_FORGES.get(category, 10)
            ng_plus_only = 1 if category == 'Ascended Binding Runes' else 0
            for name, effect in runes:
                conn.execute(text(
                    "DELETE FROM sl_err_binding_runes WHERE name=:name AND rune_type=:cat"
                ), {'name': name, 'cat': category})
                conn.execute(text("""
                    INSERT INTO sl_err_binding_runes
                        (name, rune_type, effect, max_forge_level, ng_plus_only)
                    VALUES (:name, :cat, :effect, :max_forge, :ng_plus)
                """), {
                    'name': name, 'cat': category, 'effect': effect,
                    'max_forge': max_forge, 'ng_plus': ng_plus_only,
                })
                total += 1
            print(f'  + {category}: {len(runes)} Binding Runes')
        conn.commit()

        print(f'\n{total} Binding Runes seeded across {len(BINDING_RUNES)} categories.')


if __name__ == '__main__':
    run()
