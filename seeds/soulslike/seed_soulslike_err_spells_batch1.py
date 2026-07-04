"""
Seed: ERR new spell detail, batch 1.
Updates stub rows from the overview seeder with full detail, or inserts if missing.
Source: err.fandom.com individual spell pages, pasted directly by user.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_spells_batch1.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, fp_cost, slots, int_req, fai_req, arc_req, is_generator, fp_on_hit, effect, notes, acquisition)
SPELLS = [
    ('Blood Star Slicer', 400, 2, 10, 20, 0, 0, None,
     "Forms a blood star shard that splits into two projectiles which aggressively seek enemies. "
     "Inflicts Magic damage. Can be cast while in motion and charged for higher damage.",
     "Useful against blocking enemies at medium range - projectiles bend and come in from the sides.",
     "Dropped by Mad Tongue Alberich, the invader in Roundtable Hold (jump over the banister east of "
     "the grace). If already defeated before ERR, inserted into your inventory automatically."),

    ('Briars of Guilt', 670, 2, 14, 28, 0, 0, None,
     "Wounds the caster, sending a trail of flaming bloodthorns along the ground to impale enemies. "
     "Deals Fire damage and Blood Loss in a thorned explosion with lingering burn damage. Thorn trail "
     "can also damage enemies it passes through. Deals 50 Blood Loss buildup to the player, 100 on "
     "enemies (scales with Arcane). Can be charged to increase damage.",
     "Will not trigger the thorn explosion if not locked onto an enemy.",
     "Found in the Mountaintops of the Giants, from an enemy camp right after the Zamor Ruins area."),

    ('Briars of Penance', 330, 2, 16, 32, 0, 0, None,
     "Wounds the caster, causing razor-sharp blood spikes to erupt from their form and shoot "
     "projectiles in the immediate vicinity. Inflicts Pierce damage. Deals 25 Blood Loss buildup to "
     "the player, 30 buildup per thorn on enemies (scales with Arcane). Can be cast repeatedly.",
     None,
     "Obtained from the Laeidd Battleground enemy camp in Mt. Gelmir, along with Staff of the Guilty."),

    ('Briars of Resentment', 700, 3, 20, 40, 0, 0, None,
     "Wounds the caster, spreading a patch of briars across the surrounding area in a moderate "
     "circular zone centered on the player. Persists 20 seconds, dealing repeated Pierce damage and "
     "Blood Loss buildup to enemies inside. Cannot be recast until the original thorns dissipate.",
     None,
     "Found on a corpse in Altus Plateau on a hidden ledge beneath the Bridge of Iniquity. From the "
     "Second Church of Marika, head north to a spiritspring near the bridge, land on the cliff above "
     "its base, follow the cliff past a Vulgar Militiaman to a tombstone with briars."),

    ('Carian Verge', 250, 1, 21, 0, 0, 0, None,
     "Conjures a perimeter of magic short swords around the player. Swords inflict Magic damage. "
     "Grants x1.15 Attack Power of Carian sorceries and skills for up to 2 seconds after the swords "
     "disappear.",
     None,
     "Dropped by Spirit Jellyfish Pluemoon, north-east of the 'Gate Town North' site of grace in "
     "Liurnia."),

    ('Glintblade Hail', 460, 2, 35, 0, 0, 0, None,
     "Creates overhead sigils that unleash a cone of falling glintblades in front of the player. "
     "Inflicts Magic damage. Each enemy receives only one instance of damage regardless of size. "
     "Can be cast while in motion. Charging substantially increases range, area, and damage.",
     None,
     "Drops from Moongrub, a hostile NPC Carian Knight in a graveyard west of Caria Manor."),

    ('Glintstone Snowdrift', 50, 0, 11, 0, 0, 1, '1.09%+109',
     "Launches a deluge of freezing projectiles at foes. Inflicts Magic damage, 20 Frostbite buildup "
     "per projectile on enemies, 18 Frostbite buildup on player. Generates 1.09%+109 FP on hit. "
     "Can be cast repeatedly and while in motion.",
     "Generator spell - costs 0 Memory Slots.",
     "Purchasable for 2400 runes from any sorcery vendor after handing them Ranni's Scroll (awarded "
     "by finding the location depicted in the new Falling Sky painting in Redmane Castle)."),

    ('Distant Stars', 460, 2, 30, 0, 0, 0, None,
     "Fires seven homing cold shooting stars that pursue the target. Inflicts Magic damage and "
     "Frostbite buildup on enemies, plus small Frostbite buildup on the player. Projectiles travel "
     "at moderate speed with significant range. Can be cast while in motion. Homes in on nearby enemy "
     "when not locked on.",
     None,
     "Reward from Twin Lookout Encampments camp."),

    ('Flashfrost Cutter', 140, 1, 19, 0, 0, 0, None,
     "Conjures a cold magic sword and delivers a swift sweeping slash. Can be cast without delay "
     "after performing another action, roughly as fast as Carian Slicer. Inflicts Magic damage and "
     "Frostbite buildup on hit.",
     "Can be cast repeatedly without delay - similar speed to Carian Slicer.",
     "Found outside the Heretical Rise in the Mountaintops of the Giants. Instead of entering the "
     "tower, go right and under the vault; guarded by two Avionette Soldiers."),

    ('Moonchill', 420, 2, 28, 0, 0, 0, None,
     "Increases all damage negations and robustness; Frostbite and Blood Loss buildup drain faster "
     "for 80 seconds. Grants: x0.88 All Damage taken, +100 Robustness, -4 Blood Loss and Frostbite "
     "buildup every 2 seconds.",
     None,
     "Purchased from a sorcery vendor after handing them Ranni's Scroll (awarded by completing the "
     "new Falling Sky painting in Redmane Castle)."),

    ('Rime Cascade', 270, 2, 26, 0, 0, 0, None,
     "Fires a continuous stream of frozen glintstone. Inflicts Magic damage and Frostbite buildup. "
     "Charging increases potency. FP cost: 270 initial +30 per second held.",
     None,
     "Found in Cave of the Forlorn (Consecrated Snowfield), on a lying corpse in the room with two "
     "Scaly Misbegotten and a Winged Misbegotten."),
]


def run():
    with engine.connect() as conn:
        updated = 0
        inserted = 0
        for (name, fp_cost, slots, int_req, fai_req, arc_req,
             is_gen, fp_on_hit, effect, notes, acquisition) in SPELLS:
            result = conn.execute(text("""
                UPDATE sl_err_spells
                SET fp_cost = :fp, slots_used = :slots,
                    int_req = :ir, fai_req = :fr, arc_req = :ar,
                    is_generator = :gen, fp_on_hit = :fp_hit,
                    effect = :eff, notes = :notes, acquisition = :acq
                WHERE name = :name
            """), {
                'fp': fp_cost, 'slots': slots,
                'ir': int_req, 'fr': fai_req, 'ar': arc_req,
                'gen': is_gen, 'fp_hit': fp_on_hit,
                'eff': effect, 'notes': notes, 'acq': acquisition, 'name': name,
            })
            if result.rowcount:
                updated += 1
            else:
                conn.execute(text("""
                    INSERT INTO sl_err_spells
                        (name, spell_type, school, is_new_to_err, is_generator, fp_cost, slots_used,
                         int_req, fai_req, arc_req, fp_on_hit, effect, notes, acquisition)
                    VALUES (:name, 'Sorcery', 'Unknown', 1, :gen, :fp, :slots,
                            :ir, :fr, :ar, :fp_hit, :eff, :notes, :acq)
                """), {
                    'name': name, 'gen': is_gen, 'fp': fp_cost, 'slots': slots,
                    'ir': int_req, 'fr': fai_req, 'ar': arc_req,
                    'fp_hit': fp_on_hit, 'eff': effect, 'notes': notes, 'acq': acquisition,
                })
                inserted += 1
                print(f'  INSERTED (new): {name}')
        conn.commit()
        print(f'\n{updated} updated, {inserted} inserted ({len(SPELLS)} total, batch 1).')


if __name__ == '__main__':
    run()
