"""
Seed: ERR per-weapon Weight + Critical fill-in, batch 2.
Source: err.fandom.com individual weapon pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch2.py
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
    ('Coilheart', 5.0, 100,
     "Enhances guard point during attacks (exact value unverified). Increases Immunity by 80 and "
     "drains Poison buildup. Poison affinity: causes Poison buildup.",
     None,
     "Must first acquire the Gladius of Ophidion, the Coil Shield, and the Ringmaster Ophidion Spirit "
     "Ashes. Equip Coil Shield in the left hand and Gladius of Ophidion in the right hand, then summon "
     "Ringmaster Ophidion and have him perform his gesture (either by performing the Rallying Cry "
     "gesture near him at any spirit monument area, or by summoning him in the Gilded Court where he "
     "auto-performs the gesture upon aggroing). Upon obtaining Coilheart, the Gladius of Ophidion and "
     "Coil Shield are permanently lost - requires NG+ or Starlight Tokens to get them again.",
     "Weapon once wielded by a gladiator in a past age. A paired set consisting of a broadsword and a "
     "serpentine shield. Inflicts poison buildup. A forked tongue tainted his will, coercing him to "
     "embrace cruelties he once rejected, in service to one he once thought just. The serpent's cinch "
     "is inescapable. Unique Skill: Viper Stance - while in stance, normal attack thrusts forward with "
     "shield up, strong attack lashes out and bites with the shield's bronze viper; the thrust deals "
     "significant damage against poisoned foes."),
    ('Crude Iron Claws', 3.5, 125,
     "Blood affinity: causes Blood Loss buildup.",
     None,
     "Obtained from the Craven's Advance camp in Leyndell, alongside the Pumpkin Helm.",
     "Roughly hewn fist weapon, dull blades of iron fused to a simple frame. Weapon wielded by the Mad "
     "Pumpkin Heads. Not one thought was spared to the comfort of holding this rough weapon. Its "
     "intended wielder must be despised indeed."),
    ('Crystal Ringblade', 6.0, 95,
     "x1.05 Attack Power of Crystalian sorceries. Crystal Armor during skill usage (x0.8 Damage Taken, "
     "+40 Poise) - triggers using any skill, including those applied via Ash of War Enkindling. Magic "
     "affinity: slowly recovers FP while in combat.",
     None,
     "Defeat the Crystalian Duo boss encounter in the Altus Tunnel.",
     "Ringblade fashioned from pure crystal; a deed impossible for a human. Enwreathed with powerful "
     "magic. The inscrutable Crystalians have but one clear purpose: to safeguard their crystals unto "
     "the end. One theory posits that they yearn for the return of their creator who will carve for "
     "them new brethren."),
    ('Dawnglow Greatbolt', 10.0, 90,
     "Increases added Holy attack power (exact value unverified). Wielding this weapon drains status "
     "effect buildup (exact value unverified).",
     None,
     "Defeat Fulghor, Champion of Rauh, accessed from the belfry warp gate just outside the exit from "
     "Castle Ensis.",
     "A giant blade of solid brass, its shape reminiscent of a bolt of lightning. Etched upon its "
     "gleaming surface are ancient patterns, crossed in a likeness of thorns. None who would have liked "
     "to reveal their secrets ever survived approaching the weapon's wielder. Unique Skill: Dawnblade - "
     "extends the weapon with phantasmal blades to perform a spinning slash; the weapon remains imbued "
     "with holy power, especially effective when two-handing."),
    ("Disciple's Rotten Branch", 4.0, 100,
     "x1.1 Attack Power of Servant of Rot incantations while equipped. Rotten affinity: causes Scarlet "
     "Rot buildup.",
     None,
     "Found in Tombsward Cave, Weeping Peninsula. Low chance to drop from Disciples of Rot.",
     "A gnarled old treebranch covered in toxic mushrooms and slime. Tool of the overgrown disciples of "
     "rot. The weapon's stench is almost unbearable. Wounds inflicted by it are sure to spread the "
     "scarlet rot. Functions as a Weapon Catalyst capable of casting incantations, otherwise considered "
     "a Spear."),
    ('Fellthorn Clutches', 4.0, 100,
     "x1.075 Fire Attack Power of incantations while equipped. Fell affinity: wielding this weapon "
     "drains status effect buildup.",
     None,
     "Drops from the new Fellthorn Spirit boss in Leyndell, Ashen Capital, located next to the "
     "Erdtree's Favor +2 talisman, replacing the previous three Ulcerated Tree Spirits.",
     "Thorned, gnarled roots that wind themselves around one's arms. Fist weapons come in pairs, and "
     "two-handing this weapon equips it to both hands. The burning of the Erdtree is the cardinal sin. "
     "Its protective spirits are tortured by flame, lashing out in unspeakable pain. Functions as a "
     "Weapon Catalyst capable of casting incantations, otherwise considered a Fist weapon. Unique "
     "Skill: Fell Flame Lariat - imbue fists with the flames of tortured spirits and spin while moving "
     "forward, spewing flames and clotheslining nearby foes; strong attack follow-up causes a fiery "
     "detonation."),
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
