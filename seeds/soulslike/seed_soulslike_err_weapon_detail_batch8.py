"""
Seed: ERR per-weapon Weight + Critical fill-in, batch 8.
Source: err.fandom.com individual weapon pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_weapon_detail_batch8.py
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
    ('Putrescent Bonesmasher', 12.0, 85,
     "Cold affinity: causes Frostbite buildup. Soporific affinity: causes Sleep buildup.",
     None,
     "Dropped by Putrescent Bonemass enemies in Stone Coffin Fissure, in the Realm of Shadow (DLC).",
     "Great curved sword assembled from the bones of the departed, clutching a blade of hardened "
     "putrescence. A writhing mass at its core pulses in restless vitality. Though unable to find "
     "peace in death, putrescent remains gather into great brutes to seek, and protect, the source of "
     "sweet slumber left behind at its resting grounds. Unique Skill: Pulverize - hold the giant blade "
     "with both hands and smash repeatedly at foe's feet; strong attack follow-up performs a mid-air "
     "slam. Added in ERR 2.0."),
    ("Red Wolf's Fang", 1.0, 95,
     "Magic affinity: slowly recovers FP while in combat. Due to its summoned nature, the blade "
     "inflicts purely Magic damage.",
     None,
     "Drops from the Red Wolf of the Champion found in Gelmir Hero's Grave, Mt. Gelmir.",
     "Curved red-gold sword etched with runes of power. Weapon wielded by the proud Red Wolf of the "
     "Champion. The sword's glowing color is reminiscent of the ancient lifeblood of the crucible. "
     "Unique Skill: Red Wolf's Gambol - skill of the ferocious Red Wolf; jump backwards, leaving "
     "sigils that create enemy-seeking glintblades in your wake, with an additional input for a "
     "devastating slash attack follow-up."),
    ('Rotten Crystal Ringblade', 6.0, 95,
     "x1.05 Attack Power of Crystalian sorceries while equipped. Rotten affinity: causes Scarlet Rot "
     "buildup. Magic affinity: slowly recovers FP while in combat.",
     None,
     "Complete the Elphael Inner Wall camp in Elphael by defeating the three Rotten Crystalian camp "
     "guardians.",
     "Ringblade fashioned from pure crystal; a deed impossible for a human. It festers with scarlet "
     "rot. The inscrutable Crystalians have but one clear purpose: to safeguard their crystals unto "
     "the end. One theory posits that they yearn for the return of their creator who will carve for "
     "them new brethren."),
    ('Scepter of Serenity', 11.0, 100,
     "5%+50 FP restoration when Madness is inflicted in the vicinity. If held in one hand, "
     "additionally grants x1.1 Holy Damage dealt and x1.1 Madness buildup caused. Has the same strong "
     "attack as the Axe of Godrick and Crescent Moon Axe.",
     None,
     "Defeat the Equilibrious Beast boss encounter at the bottom of the Subterranean Shunning-Grounds.",
     "A thick, ornate staff of solid metal, with a wax sculpture of furled fingers as a crown. Yearning "
     "for order, the man would cling to the symbol of his past, finding solace in the purpose it "
     "embodied. Yearning for chaos, the beast would scream and rampage through its prison, beating "
     "relentlessly against its walls."),
    ('Snow Witch Scepter', 3.0, 0,
     "x1.1 Attack Power of Cold sorceries while equipped. Frostbite from Cold sorceries cast by this "
     "staff makes enemies take an additional x1.03 Damage. Cold affinity: causes Frostbite buildup.",
     None,
     "Reward for clearing the Twin Lookout Encampments camp in Liurnia.",
     "Witch's casting implement, fashioned of a frightfully cold metal. One of the legendary "
     "armaments. Strengthens cold sorceries. Passed down to a young princess once she had learned all "
     "there was to teach. It bears the leaden weight of a dark obligation."),
    ('Starcaller Spire', 5.5, 95,
     "x1.1 Attack Power to gravity sorceries while equipped. Gravitational affinity: increases damage "
     "against Void enemies.",
     None,
     "Drops from the Fallingstar Beast in the Altus Plateau; also drops from Starcallers at a low "
     "rate.",
     "Crooked polearm tipped with a crude spike of meteoric ore, shaped by gravity magic. Heavy "
     "attacks unleash spikes of weighty magic on the ground. The most devoted of Starcallers may "
     "attract the intrigue of a lord from the stars, who will teach them the ways of his people. "
     "Functions as a Weapon Catalyst, otherwise considered a Halberd."),
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
