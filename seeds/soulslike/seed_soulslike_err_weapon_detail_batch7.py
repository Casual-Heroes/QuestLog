"""
Seed: ERR per-weapon Weight + Critical fill-in, batch 7.
Source: err.fandom.com individual weapon pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch7.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, weight, critical, passive_effect, fated_effect, acquisition, description)
WEAPONS = [
    ("Makar's Ceremonial Cleaver", 14.0, 85,
     "x1.05 Attack Power to Dragon Communion incantations while equipped. Magma affinity: deals bonus "
     "damage to Frostbitten targets.",
     None,
     "Drops from Magma Wyrm Makar. (The Magma Wyrm Scalesword has been changed to drop from the Magma "
     "Wyrm in Volcano Manor instead.)",
     "Curved greatsword used in the blasphemous act of Dragon Communion. The shape resembles a "
     "dragon's head: hard scales brace its spine. Of the failed dragons cursed to slither upon the "
     "earth, Makar is the greediest, the most depraved defilement of dragonkind fueling his "
     "transformation. Unique Skill: Magma Guillotine (shared with the Magma Wyrm Scalesword) - grab "
     "the scalesword with both hands, as a wyrm would hold it in its mouth, and leap forwards, "
     "smashing it into the ground and triggering a blast of magma; follow up with an additional input "
     "for a chopping attack."),
    ('Marionette Short Sword', 2.5, 105,
     "Blood affinity: causes Blood Loss buildup.",
     None,
     "Obtained from the Sellia Gateway Ambush enemy camp in the Sellia Gateway area, along with the "
     "Avionette Scimitar.",
     "Straight sword with the crossguard bent forward. The sharp edges induce blood loss. Weapon of "
     "the Marionette Soldiers employed by sorcerers."),
    ("Mohgwyn's Sacred Seal", 1.0, 100,
     "x1.1 Attack Power to Blood Oath incantations while equipped. Blood affinity: causes Blood Loss "
     "buildup.",
     None,
     "Purchased from Finger Reader Enia in Roundtable Hold by trading in the Remembrance of the Blood "
     "Lord, acquired after defeating Mohg.",
     "A Formless sacred seal depicting the symbol of the coming dynasty. It is thought that when this "
     "seal is brandished, the great Luminary himself scourges his body to bestow the sacred mother's "
     "blessings unto the wielder. The joy of service to a Lord so selfless is truly indescribable. "
     "Added in the ERR 2.2.1.0 update."),
    ("Night's Edge", 2.0, 180,
     "Regardless of the attack performed, striking an enemy restores 0.4%+8 Stamina per hit to the "
     "user and drains 2%+10 Stamina per hit from the target - also triggers from damaging skills "
     "applied via Ash of War Enkindling, including ranged/AoE skills. Night affinity: boosts stealth "
     "attack damage.",
     None,
     "Drops from the new Nox Nightmaiden boss located near the Night's Sacred Grounds Site of Grace.",
     "Impossibly sharp dagger with a curved blade, wielded by nightmaidens of the Eternal City. Forged "
     "from the liquid metal from a Silver Tear, it is thoroughly tempered until hardened."),
    ('Nox Flowing Fist', 4.5, 100,
     "Regardless of the attack performed, striking an enemy restores 0.6%+12 Stamina per hit to the "
     "user and drains 2%+10 Stamina per hit from the target - also triggers from damaging skills "
     "applied via Ash of War Enkindling, including ranged/AoE skills. Quality affinity: blocking "
     "consumes less stamina.",
     None,
     "Drops from a miniboss added to a small new room in Nokstella.",
     "Fist weapon in the shape of a suspended dome of liquid metal wielded by monks of the Eternal "
     "City. It is said the maces of Nox monks can shift into this form, yet without their secret "
     "knowledge, this weapon remains inert."),
    ('Pumpkin Sledge', 10.0, 100,
     None, None,
     "Obtained from the Academy Blockade enemy camp in the Academy Gate Town area, along with the "
     "Chainlink Flail.",
     "A solid brass pumpkin screwed onto a rough wooden pole, wielded by Mad Pumpkin Heads. Smithed "
     "without a hint of finesse, this lopsided weapon is sure to throw its wielder off-balance."),
]


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
        print(f'\n{updated}/{len(WEAPONS)} weapons updated with weight + critical.')


if __name__ == '__main__':
    run()
