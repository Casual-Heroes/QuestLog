"""
Seed: ERR per-weapon Weight + Critical fill-in, batch 4.
Source: err.fandom.com individual weapon pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch4.py
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
    ('Gladius of Ophidion', 3.5, 100,
     "Poison affinity: causes Poison buildup. Despite having a standard moveset and generic weapon "
     "skill, this is a somber weapon and cannot be infused.",
     None,
     "Located in the Serpentine Depths (new location added in Reforged 2.0). After defeating the "
     "Crazed Duelist, snakes continue to spawn in the arena - after defeating enough, a unique snail "
     "spawns and drops the Gladius of Ophidion on defeat.",
     "A nimble broadsword of aged bronze, ideal for stabbing at vulnerable points. Inflicts poison "
     "buildup. Bronze was a favored metal for the arming of gladiators. A copper alloy that would fade "
     "over time, it would symbolically blemish its primordial hue with the green scales of the reviled "
     "serpent. Required to acquire Coilheart."),
    ('Gracebound Cane Sword', 3.0, 130,
     "Lowers attack of and deals bonus damage to marked targets (exact values unverified).",
     None,
     "Found in Elphael, just beyond the Elphael Inner Wall site of grace. Proceed down the hallway from "
     "the Rotten Crystalians, then instead of continuing to the small rot swamp, keep going south and "
     "look behind the large ornate chalice.",
     "Walking cane wrought from silver, with deadly function. Once wielded by a bookish Tarnished who "
     "fell from grace. They honeyed words of a kindly deity sway even the most resolute of hearts. What "
     "hope, then, is there for one who strives for the betterment of his people?"),
    ('Gracebound Claws', 3.0, 100,
     "Weapon hits empower nearby allies (exact value unverified). Cold affinity: causes Frostbite "
     "buildup and a ghostflame burn on hit. Despite being a claw weapon, compatible with Whip Ashes of "
     "War instead of Claw Ashes.",
     None,
     "Found at the base of a grave in the Mountaintops graveyard with the Giant Skeletal Phantoms.",
     "Silver accessories of fine make, attached to one's fingers. Once wielded by a dour Tarnished who "
     "fell from grace. Imbued with a resentful hex, these claws now slash with an otherworldly edge, "
     "drawn from the ire of their former master as she contends with her beloathed family in the "
     "spirit realm."),
    ('Gracebound Dagger', 2.5, 150,
     "Final hit of a light attack chain stores damage the enemy took over the previous 4 seconds and "
     "reprises 35% of it (unverified exact %) back onto them over the next 4 seconds. While a reprise "
     "is active, damage taken during that window isn't recorded toward another reprise (unverified).",
     None,
     "Found on a flower-adorned grave in the Gilded Court, on the way to Warrior's Rest.",
     "Filigreed dagger bearing traces of magic. Once wielded by a refined Tarnished who fell from "
     "grace. The guidance of grace demands complete devotion, such that even familial bonds are "
     "abandoned in pursuit of lordship. The graves of the Gilded Court tell of how such fervor is "
     "rewarded."),
    ('Gracebound Greataxe', 19.0, 90,
     "Taking damage during a skill grants x1.15 Poise Damage, x1.15 Damage, x1.15 Stamina Damage for "
     "the duration of the skill.",
     None,
     "Found inside the Caelid Colosseum, accessed from behind the Great Jar - walk through the "
     "hallways to find it up against an altar.",
     "Colossal axe carved from a ship's figurehead. Once wielded by a mighty Tarnished who fell from "
     "grace. Once dispersed across the Sea of Fog, some Tarnished would remain to plunder its waters, "
     "up until the call of grace brought them home to fight forevermore."),
    ('Gracebound Greatshield', 17.0, 90,
     "Guarding slowly heals self and nearby allies by 0.15% Max HP + 3 every 2 seconds.",
     None,
     "Found after teleporting to the Crumbling Lands through the Four Belfries in Liurnia, on a "
     "slanted pillar in the area with the two Beastmen of Farum Azula.",
     "Artifact of a lost people, once wielded by a proud Tarnished who fell from grace. With the fall "
     "of the Storm King, a secretive people beholden to him is said to have left this realm. Though "
     "their storm arts persist upon the battlefield, few know their origins."),
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
