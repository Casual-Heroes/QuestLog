"""
Seed: ERR Spells overview - system changes, new spell names list, generator spells with
FP-on-hit values, and Mystic Ash default assignments per catalyst.
Source: err.fandom.com/wiki/Spells, pasted directly by user.

Individual spell stats (damage, requirements, memory slots) are not in this paste -
that data is linked to an external spreadsheet. This seeds the structural/system info.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_spells_overview.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

SYSTEM_SECTIONS = {
    'overview': (
        "Reforged introduces many changes to how spellcasting functions mechanically, adds over 60 new "
        "spells, and alters many base game spells.\n\n"
        "Generator spells are a new type of spell which cost no Memory Slots to equip and directly "
        "recover FP. Additionally, each Catalyst has a unique heavy attack that generates FP on hit "
        "while costing no FP. These additions augment the general FP Regen changes and reduce reliance "
        "on Cerulean Flasks for spell gameplay.\n\n"
        "Mystic Ashes are a new Ash of War variant, allowing spells with no or 1 Memory Slot cost to be "
        "equipped as a Catalyst's skill. Many Catalysts have had their default skill changed to a Mystic "
        "Ash spell."
    ),
    'general_spellcasting': (
        "Every spell has received rebalancing for Damage, Stamina Cost, Memory Slot cost, and FP Cost. "
        "Characters start with one extra Memory Slot, for a maximum of 14 (engine maximum; Moon of "
        "Nokstella talisman now grants maximum Memory Slots). Range of support incantations increased "
        "for more consistent ally targeting.\n\n"
        "Each spell cast initially consumes FP based on Max FP, then regenerates some FP over one second "
        "based on Memory Slot count: 0-slot (Generator): 0.2% Max FP penalty then 0.5% Max FP+4 "
        "restore; 1-slot: 0.8% penalty then 1% Max FP+12; 2-slot: 2.4% penalty then 1.5% Max FP+20; "
        "3-slot: 4.8% penalty then 2% Max FP+28.\n\n"
        "Casting a spell now very slightly increases the damage of other spells for an extended time "
        "(not visible as a buff) - incentivizes using varied spells in a loadout. Boosts to specific "
        "spell schools from weapon effects cannot stack if both are the same potency (e.g. two "
        "Beastclaw Seals would not stack; Cinquedea + Clawmark Seal can stack). Common Buff Duration "
        "effects do not affect HP Regen effects, including from spells."
    ),
    'cast_speed': (
        "Greatly increased the speed of most spell casting animations. Casting animations can generally "
        "be cancelled in the first few frames before FP is spent, and cancelled more quickly after "
        "firing. Certain spells have had range adjustments to account for these safer cast animations.\n\n"
        "Cast Speed now improves how quickly spells transition into weapon skills and attacks, benefiting "
        "hybrid melee+spell builds more from Cast Speed.\n\n"
        "Cast Speed stat now works on a scale from 1 to 250 instead of 10 to 70. Mind now governs Cast "
        "Speed instead of Dexterity, up to +125 at 99 Mind. Players start with 50 Cast Speed.\n\n"
        "Catalyst Cast Speed bonuses/penalties: Academy Glintstone Staff +25, Azur's Glintstone Staff "
        "+50, Clawmark Seal +25, Dryleaf Seal +25, Staff of the Great Beyond +25, Scepter of the "
        "All-Knowing +25, Giant's Seal -25, Lusat's Glintstone Staff -25, Rotten Crystal Staff -25. "
        "Radagon Icon talisman: +100. Faithful/Flock Canvas Talisman: +25/+50. Tainted Projection rune: "
        "up to +50."
    ),
    'generators': (
        "Generator spells cost no Memory Slots to equip and generate FP on hit. Recognized by a blue "
        "drop in the bottom right corner of their spell icon. Each catalyst has a built-in generator "
        "spell via heavy attack (costs zero FP). Generators restore both flat FP and a percentage of "
        "Max FP on hit; exact restoration varies per spell depending on attack speed.\n\n"
        "Generator Sorceries (name - school - FP on hit): Ambush Shard Night 1.02%+102; Blasphemous "
        "Spark (new) Magma 1.76%+176; Carian Slicer Carian 0.95%+95; Glintstone Pebble Glintstone "
        "0.94%+94; Glintstone Snowdrift (new) Cold 1.12%+112; Rancor (new) Ghostflame 0.98%+98; Stone "
        "Sling (new) Gravity 1.92%+192.\n\n"
        "Generator Incantations (name - school - FP on hit): Bestial Sling Bestial 0.96%+96; Catch "
        "Flame Giants'/Godslayer(Godslayer's Seal) 1.06%+106; Dragonrend (new) Dragon Communion "
        "1.01%+101; Golden Star (new) Erdtree 1.53%+153; Honed Bolt Dragon Cult 1.14%+114; Retch Gore "
        "(new) Blood Oath 1.71%+171; Scarlet Papillon (new) Servants of Rot 1.67%+167."
    ),
    'mystic_ashes': (
        "Mystic Ashes are a new type of Ash of War that allow you to cast any spell costing 1 Memory "
        "Slot or less with the Weapon Skill input, for easy access without cycling through the spell "
        "list. Available for purchase for 5 Lost Ashes each at Smithing Master Hewg after purchasing "
        "the Spellsmith's Etching Tool at Smithing Master Iji in Liurnia. Cannot be Enkindled. Must own "
        "the corresponding spell first.\n\n"
        "Default Mystic Ash assignments per catalyst: Academy Glintstone Staff=Starlight, Dark "
        "Glintstone Staff=Flashfrost Cutter, Gelmir Glintstone Staff=Magma Shot, Staff of Loss=Night "
        "Shard, Digger's Staff=Shatter Earth, Carian Glintblade Staff=Glintblade Phalanx, Albinauric "
        "Staff=Night Maiden's Mist, Maternal Staff=Cherishing Fingers, Meteorite Staff=Collapsing "
        "Stars, Spiraltree Seal=Spira, Giant's Seal=Flame Cleanse Me, Clawmark Seal=Bestial Vitality, "
        "Gravel Stone Seal=Lightning Spear, Godslayer's Seal=Catch Flame, Fire Knight's Seal=Fire "
        "Serpent, Staff of the Guilty=Briars of Punishment.\n\n"
        "Unique multi-slot Mystic Ashes (exclusive to specific catalysts): Crystal Staff=Crystal "
        "Release, Rotten Crystal Staff=Crystal Torrent, Azur's Glintstone Staff=Comet, Lusat's "
        "Glintstone Staff=Star Shower, Prince of Death's Staff=Creeping Rancor, Staff of the Great "
        "Beyond=Guiding Microcosm, Golden Order Seal=Law of Regression, Erdtree Seal=Great Heal, "
        "Dragon Communion Seal=Dragonmaw, Frenzied Flame Seal=Howl of Shabriri."
    ),
    'catalyst_changes': (
        "Each catalyst now has a unique short-range Heavy Attack (no FP cost) doing significant Poise "
        "Damage with decent FP recovery, further boostable by the overhauled Beloved Stardust talisman. "
        "Expanded list of Dual Catalysts. Added Weapon Catalysts - armaments capable of attacking, "
        "blocking, and casting. (See individual Staves and Seals pages for per-catalyst changes.)"
    ),
}

# (name, type, school, is_new, is_generator, effect)
NEW_SORCERIES = [
    ('Blood Star Slicer', 'Sorcery', 'Aberrant', 1, 0, None),
    ('Briars of Guilt', 'Sorcery', 'Aberrant', 1, 0, None),
    ('Briars of Penance', 'Sorcery', 'Aberrant', 1, 0, None),
    ('Briars of Resentment', 'Sorcery', 'Aberrant', 1, 0, None),
    ('Carian Verge', 'Sorcery', 'Carian', 1, 0, None),
    ('Glintblade Hail', 'Sorcery', 'Carian', 1, 0, None),
    ('Glintstone Snowdrift', 'Sorcery', 'Cold', 1, 1,
     "Launches a deluge of freezing projectiles at foes. FP on hit: 1.12%+112."),
    ('Distant Stars', 'Sorcery', 'Cold', 1, 0, None),
    ('Flashfrost Cutter', 'Sorcery', 'Carian/Cold', 1, 0, None),
    ('Moonchill', 'Sorcery', 'Cold', 1, 0, None),
    ('Rime Cascade', 'Sorcery', 'Cold', 1, 0, None),
    ('Crystal Volley', 'Sorcery', 'Crystalian', 1, 0, None),
    ('Burgeoning Root', 'Sorcery', 'Death', 1, 0, None),
    ('Duskflare Barrage', 'Sorcery', 'Death', 1, 0, None),
    ('Eclipsed Blade', 'Sorcery', 'Death', 1, 0, None),
    ('Eclipsed Sun', 'Sorcery', 'Death', 1, 0, None),
    ('Guiding Microcosm', 'Sorcery', 'Finger', 1, 0, None),
    ('Warding Microcosm', 'Sorcery', 'Finger', 1, 0, None),
    ('Rancor', 'Sorcery', 'Ghostflame', 1, 1,
     "Summons a vengeful spirit that chases down foes. FP on hit: 0.98%+98."),
    ('Creeping Rancor', 'Sorcery', 'Ghostflame', 1, 0, None),
    ('Raving Rancor', 'Sorcery', 'Ghostflame', 1, 0, None),
    ('Stone Sling', 'Sorcery', 'Gravity', 1, 1,
     "Pulls a stone from the earth and sends it flying. FP on hit: 1.92%+192."),
    ('Electromagnetic Discharge', 'Sorcery', 'Gravity', 1, 0, None),
    ('Singularity', 'Sorcery', 'Gravity', 1, 0, None),
    ('Blasphemous Spark', 'Sorcery', 'Magma', 1, 1,
     "Sparks a stream of blasphemous flame to scorch foes. FP on hit: 1.76%+176."),
    ('Molten Armament', 'Sorcery', 'Magma', 1, 0, None),
    ('Serpentine Blaze', 'Sorcery', 'Magma', 1, 0, None),
    ('Unstable Fissure', 'Sorcery', 'Magma', 1, 0, None),
    ('Volcanic Storm', 'Sorcery', 'Magma', 1, 0, None),
    ('False Constellation', 'Sorcery', 'Night', 1, 0, None),
    ('False Heavens', 'Sorcery', 'Night', 1, 0, None),
    ('Silver Attunement', 'Sorcery', 'Night', 1, 0, None),
    ('Cerulean Sea', 'Sorcery', 'Primeval', 1, 0, None),
    ('Blazing Wall', 'Sorcery', 'Redmane', 1, 0, None),
    ('Fist of the Heavens', 'Sorcery', 'Redmane', 1, 0, None),
    ('Ancient Tracer', 'Sorcery', 'Untyped', 1, 0, None),
    ('Scornful Gaze', 'Sorcery', 'Untyped', 1, 0, None),
    ('Transmigration Call', 'Sorcery', 'Untyped', 1, 0, None),
]

NEW_INCANTATIONS = [
    ('Retch Gore', 'Incantation', 'Blood Oath', 1, 1,
     "Ejects a cone of vile blood from the caster's mouth. FP on hit: 1.71%+171."),
    ('Bloodrose Mist', 'Incantation', 'Blood Oath', 1, 0, None),
    ('Dragonrend', 'Incantation', 'Dragon Communion', 1, 1,
     "Creates dragon claw lacerations to cleave foes. FP on hit: 1.01%+101."),
    ("Dragonlord's Domain", 'Incantation', 'Dragon Communion', 1, 0, None),
    ("Morion's Doom", 'Incantation', 'Dragon Communion', 1, 0, None),
    ('Bolt of Gransax', 'Incantation', 'Dragon Cult', 1, 0, None),
    ('Frozen Dragonbolt', 'Incantation', 'Dragon Cult', 1, 0, None),
    ('Frozen Lightning Wisp', 'Incantation', 'Dragon Cult', 1, 0, None),
    ('Golden Star', 'Incantation', 'Erdtree', 1, 1,
     "Creates a golden shooting star that homes in on targets. FP on hit: 1.53%+153."),
    ('Kindling Spirit', 'Incantation', 'Erdtree', 1, 0, None),
    ('Projection of Gold', 'Incantation', 'Erdtree', 1, 0, None),
    ('Contorting Frenzy', 'Incantation', 'Frenzied Flame', 1, 0, None),
    ('Frenzyflame Armament', 'Incantation', 'Frenzied Flame', 1, 0, None),
    ('Frenzyspore Mist', 'Incantation', 'Frenzied Flame', 1, 0, None),
    ('Glyph of Suppression', 'Incantation', 'Frenzied Flame/Golden Order', 1, 0, None),
    ('Mark of the Beast', 'Incantation', 'Frenzied Flame/Golden Order', 1, 0, None),
    ('Ordered Disarray', 'Incantation', 'Frenzied Flame/Golden Order', 1, 0, None),
    ('Binding Stake', 'Incantation', 'Golden Order', 1, 0, None),
    ('Javelin of Gold', 'Incantation', 'Golden Order', 1, 0, None),
    ('Stakes of Gold', 'Incantation', 'Golden Order', 1, 0, None),
    ('Pledged Blade', 'Incantation', 'Miquellan', 1, 0, None),
    ('Scarlet Papillon', 'Incantation', 'Servants of Rot', 1, 1,
     "Brings forth a swarm of scarlet butterflies that descend nearby, inflicting minor Scarlet Rot "
     "buildup. FP on hit: 1.67%+167."),
    ('Blessed Aeonia', 'Incantation', 'Servants of Rot', 1, 0, None),
    ('Poison Bolt', 'Incantation', 'Servants of Rot', 1, 0, None),
    ('Poison Moth Flight', 'Incantation', 'Servants of Rot', 1, 0, None),
    ('Putrid Mist', 'Incantation', 'Servants of Rot', 1, 0, None),
    ('Rotten Armament', 'Incantation', 'Servants of Rot', 1, 0, None),
    ('Grasp of Eochaid', 'Incantation', 'Untyped', 1, 0, None),
]

# Generator spells from vanilla that are now generators in ERR
GENERATOR_VANILLA = [
    ('Ambush Shard', 'Sorcery', 'Night', 0, 1,
     "Launches a projectile from a distance removed from the caster, striking the enemy from behind. "
     "FP on hit: 1.02%+102."),
    ('Carian Slicer', 'Sorcery', 'Carian', 0, 1,
     "Conjures a magic sword and delivers a swift sweeping slash. FP on hit: 0.95%+95."),
    ('Glintstone Pebble', 'Sorcery', 'Glintstone', 0, 1,
     "Launches magical projectiles at foes. FP on hit: 0.94%+94."),
    ('Bestial Sling', 'Incantation', 'Bestial', 0, 1,
     "Swiftly flings a number of sharp rock shards. FP on hit: 0.96%+96."),
    ('Catch Flame', 'Incantation', "Giants' Flame / Godslayer", 0, 1,
     "Momentarily sparks flame from the caster's hand. FP on hit: 1.06%+106. Cast with Godslayer's "
     "Seal is considered a Godslayer incantation."),
    ('Honed Bolt', 'Incantation', 'Dragon Cult', 0, 1,
     "Summons a bolt of lightning to strike foes from above. FP on hit: 1.14%+114."),
]


def run():
    with engine.connect() as conn:
        for section, content in SYSTEM_SECTIONS.items():
            conn.execute(text("DELETE FROM sl_err_spell_system WHERE section=:s"), {'s': section})
            conn.execute(text(
                "INSERT INTO sl_err_spell_system (section, content) VALUES (:s, :c)"
            ), {'s': section, 'c': content})
        print(f'{len(SYSTEM_SECTIONS)} spell system sections seeded.')

        inserted = 0
        for entries in [NEW_SORCERIES, NEW_INCANTATIONS, GENERATOR_VANILLA]:
            for name, spell_type, school, is_new, is_gen, effect in entries:
                conn.execute(text("DELETE FROM sl_err_spells WHERE name=:name"), {'name': name})
                fp_on_hit = None
                if effect and 'FP on hit:' in effect:
                    fp_on_hit = effect.split('FP on hit:')[1].strip().rstrip('.')
                conn.execute(text("""
                    INSERT INTO sl_err_spells
                        (name, spell_type, school, is_new_to_err, is_generator, fp_on_hit, effect)
                    VALUES (:name, :type, :school, :new, :gen, :fp, :eff)
                """), {
                    'name': name, 'type': spell_type, 'school': school,
                    'new': is_new, 'gen': is_gen, 'fp': fp_on_hit, 'eff': effect,
                })
                inserted += 1
        conn.commit()
        print(f'{inserted} spells seeded ({len(NEW_SORCERIES)} new sorceries, '
              f'{len(NEW_INCANTATIONS)} new incantations, {len(GENERATOR_VANILLA)} generator-vanilla).')
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_spells")).scalar()
        print(f'Total sl_err_spells rows: {total}')


if __name__ == '__main__':
    run()
