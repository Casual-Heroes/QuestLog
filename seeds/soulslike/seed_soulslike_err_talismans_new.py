"""
Seed: 11 brand-new ERR-exclusive talismans (no vanilla equivalent).
Source: err.fandom.com individual talisman pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_talismans_new.py
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

# (name, description, effect, acquisition_detail)
NEW_TALISMANS = [
    (
        "Assassin's Viridian Dagger",
        "An assassin's dagger, misshapen and stained in viridian. Modelled after the darkly gleaming "
        "blades used in the Night of Black Knives, those which gave the demigods their first taste of Death.",
        "When a critical attack is executed: 50%+500 Stamina restoration, +30 Stamina Regen for 50s "
        "(does not stack with Pickled Turtle Neck or Well-Pickled Turtle Neck).",
        "Defeat the invisible Black Knife Assassin waiting just outside the Queen's Bedchamber Site of "
        "Grace in Leyndell, Royal Capital.",
    ),
    (
        'Blasphemous Crest',
        "A red insignia bestowed to a knight of Praetor Rykard, its image revealing blasphemous "
        "machinations. The followers of Volcano Manor toil for one purpose: their liege lord's usurpation "
        "of the Erdtree.",
        "x1.12 Damage of magma spells and skills. Grants the Magma affinity passive effect to magma "
        "spells and skills. Boosts the effect of Molten Armament but reduces its base duration by 20 "
        "seconds. (This effect used to belong to Talisman of the Dread, which now has a different effect.)",
        "Join the Volcano Manor family. If already joined in your playthrough, automatically added to inventory.",
    ),
    (
        "Dancer's Castanets",
        "Castanets used by dancers from foreign lands. Received from Patches, and rejected by Tanith. "
        "The passionate dance comprises no seductiveness, but only a dignified beauty.",
        "x1.1 Attack Power of dancing attacks. x1.1 Stamina Damage and x1.1 Poise Damage of dancing "
        "attacks while in the Perfect Action window. Dancing attacks: Bloodblade Dance (Eleonora's "
        "Poleblade), Dancing Blade of Ranah (heavy attacks only), Eochaid's Dancing Blade (Marais "
        "Executioner's Greatsword / Regalia of Eochaid), Flame Dance (Giant's Red Braid), Flowing Curved "
        "Sword (heavy attacks only), Perfumed Oil of Ranah, Sword Dance, Unending Dance (Dancing Blade of "
        "Ranah), Waterfowl Dance (Hand of Malenia).",
        "After killing Rykard, Lord of Blasphemy, talk to Patches in Volcano Manor. Then find Patches in "
        "Shaded Castle (sitting before Elemer of the Briar boss room) and talk to him for a key item. "
        "Finally talk to Tanith in Rykard's arena and offer her the key item - she refuses it and the "
        "talisman is added to your inventory. If the key item was already given to her, the talisman "
        "appears automatically.",
    ),
    (
        "Death-Prince's Exultation",
        "A talisman depicting the favored prince of the capital, Godwyn the Golden. \"You who left us far "
        "too early, let your gentle spirit rest among the roots and wait for us within the golden boughs.\"",
        "Death Blight in the vicinity grants a protective barrier that fully resists the next staggering blow.",
        "Found in the Darklight Catacomb. Proceed through to the first elevator descent, into the large "
        "dark room with railings. North of the elevator is an edge missing its stone railing with a small "
        "ledge below - drop down, go up the nearby ladder (watch for the catacomb sorcerer), then jump "
        "across to the ledge with the chest containing the talisman.",
    ),
    (
        'Erdhewn Medallion',
        "A wooden trinket depicting the Erdtree. Though carved with simple means, the countless rings "
        "permeating the wood speak of the Erdtree's long vigil, once thought to last forever.",
        "Boosts non-flask healing with lower equip load, also affects nearby allies (15m radius). "
        "Nimble Frame: x1.16 self / x1.12 allies. Balanced Frame: x1.08 self / x1.06 allies.",
        "Found on a corpse behind the Minor Erdtree in Weeping Peninsula, guarded by two Guardians.",
    ),
    (
        "Execrable Serpent's Exultation",
        "A talisman depicting coils of snakes tangled around a gladiator's helmet. Duelists who acted the "
        "part of the treacherous snake were stung by this enfeebling trinket before combat.",
        "x0.88 Status Resistance of enemies when Poison occurs in the vicinity, for 25 seconds.",
        "Rewarded for clearing the Leyndell Colosseum enemy camp in Leyndell, Royal Capital.",
    ),
    (
        'Heavenly Brew Talisman',
        "A talisman depicting the reclusive monk Rhico as he enjoys a delectable drink. Though the world "
        "may be at a precipice, there is no reason not to enjoy the remaining pleasures as best one can.",
        "x1.6 HP restoration of Flask of Crimson Tears on successive use, at the cost of 90 Sleep buildup. "
        "x1.75 FP restoration of Flask of Cerulean Tears on successive use, at the cost of 90 Sleep buildup.",
        "Acquired from an NPC at the Shack of the Reeling, Liurnia of the Lakes.",
    ),
    (
        "Lunar Princess' Exultation",
        "A doll resembling the lunar princess Ranni. \"Our Lady's fate once again stirs. Upon the dark "
        "path of the Empyrean, let destiny be rended, and herald the dawn of the dark moon.\"",
        "x0.825 damage taken when Frostbite occurs in the vicinity, for 40 seconds.",
        "Requires the Miniature Ranni key item and all 13 Starlight Shards collected from Stone Astrolabes "
        "across the map (Limgrave x2, Weeping Peninsula, Liurnia, Caelid x2, Altus Plateau, Mt. Gelmir x2, "
        "Mountaintops of the Giants x2, Moonlight Altar, Dragonbarrow). Once collected, reach the large "
        "Stone Astrolabe atop the stairs in the Royal Knight Loretta boss arena, Caria Manor, to claim it.",
    ),
    (
        'Prodigious Crown Pendant',
        "A stone pendant depicting a glintstone crown in the likeness of Sorcerer Thops, fondly worn as a "
        "secret keepsake. Though Thops was derided as bluntstone at the Academy, one student held onto her "
        "belief in his hidden genius.",
        "Increases Elemental Attack Power with lower Equip Load. Breakpoints (linear scaling between "
        "10-30 and 30-50 Equip Load): <=10 EL=x1.12, 15=x1.107, 20=x1.097, 25=x1.087, 30=x1.077, "
        "35=x1.067, 40=x1.051, 45=x1.021, >=50=x1.0.",
        "Defeat the Graven-School found at the bottommost room of Lenne's Rise in Dragonbarrow.",
    ),
    (
        'Storied Glintstone Amulet',
        "A small chunk of purple glintstone, once part of a well-worn necklace. In days of old, wondrous "
        "colors of glintstone were fashioned into the glintstone crowns of past Academy conspectuses.",
        "3.5%+35 FP restoration on successive attacks.",
        "Found in a crashed carriage northeast of Bower of Bounty Site of Grace, at the end of the "
        "collapsed bridge.",
    ),
    (
        'Thunderous Beast Charm',
        "A talisman depicting a great bear with a hide of stone, its gem-inlaid eyes sparking with bouts "
        "of lightning. Mythical beasts of lightning, said to command storms at will, find reverence even "
        "beyond the Lands Between.",
        "Increases Running Speed based on Equip Load (Nimble x1.04, Balanced x1.06, Solid x1.08, Massive "
        "x1.1 baseline). Continuous dashing builds a lightning current that further boosts running speed "
        "(Nimble x1.08, Balanced x1.12, Solid x1.16, Massive x1.2 with current) and, on the next running "
        "attack, inflicts 120-600 Lightning Damage (scales with weapon upgrade level), 60 Poise Damage, "
        "and 600 Stamina Damage in a 5m radius, plus a half-damage Lightning AoE. Ending the dash depletes "
        "the current.",
        "Defeat the Fulminating Runebear, northeast of Tetsu's Rise in Liurnia.",
    ),
    (
        'Whirling Blades Charm',
        "A talisman depicting two hands grasping ornate swords, locked in a dance of death. The arts of "
        "combat and those of dancing are intimately entwined.",
        "x1.06 Damage and x1.04 Action Speed when alternating between right and left hand attacks "
        "(one-handed attacks only, does not apply while powerstancing).",
        "Dropped by a Cemetery Shade in the Cerulean Coast, Realm of Shadow - roaming under a large tree "
        "on the west coast, directly above the hole leading to Southern Nameless Mausoleum.",
    ),
]


def run():
    with engine.connect() as conn:
        for name, desc, effect, acquisition in NEW_TALISMANS:
            conn.execute(text(
                "DELETE FROM sl_talismans WHERE game='err' AND name=:name"
            ), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_talismans
                    (game, name, description, effect, weight, acquisition_detail, created_at)
                VALUES
                    ('err', :name, :desc, :effect, 0, :acq, :ts)
            """), {
                'name': name, 'desc': desc, 'effect': effect,
                'acq': acquisition, 'ts': NOW,
            })
            print(f'  + {name}')
        conn.commit()

        total = conn.execute(text("SELECT COUNT(*) FROM sl_talismans WHERE game='err'")).scalar()
        print(f'\n{len(NEW_TALISMANS)} new ERR-exclusive talismans seeded.')
        print(f'Total ERR talismans now: {total} (150 vanilla-rebalanced + {len(NEW_TALISMANS)} new)')


if __name__ == '__main__':
    run()
