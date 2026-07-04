"""
Seed: ERR Ashes of War, batch 1 - General Changes + New AoW + first chunk of full
rebalanced AoW list (alphabetical, Aspects of the Crucible: Wings through
Sacred Ring of Light).
Source: err.fandom.com/wiki/Skills, pasted directly by user in chunks.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_aow_batch1.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

GENERAL_CHANGES = (
    "Significant Action Speed increases to nearly all Skills, allowing more opportunistic use/mixups and "
    "further differentiating them from charged attacks. Skill strength generally increased but costs more "
    "FP (deters spamming, complemented by ERR's FP recovery changes). Most Ashes of War now base their "
    "effect damage on their own scaling, overriding the weapon's. Bows of all types can equip Ashes valid "
    "for 'All Armaments'. Weapon catalysts can equip Ashes valid for their moveset/original armament class. "
    "New affinities mean some skills changed default affinity (e.g. gravity-based AoW now default to the "
    "new Gravitational affinity). Certain weapons gained default skills not normally available to that "
    "class. Catalysts, weapon catalysts, shields, and all ranged weapon types have expanded AoW options.\n\n"
    "Ash of War Enkindling replaces AoW duplication at Smithing Master Hewg, using Lost Ashes; Legendary-"
    "grade Enkindled AoW can be applied to Somber armaments.\n\n"
    "Mystic Ashes are a variant of AoW allowing spells with 0 or 1 Memory Slot cost to be applied as a "
    "catalyst's skill. Most catalysts already have a Mystic Ash as their default skill. Requires the "
    "Spellsmith's Etching Tool (purchased from Smithing Master Iji, Liurnia) before Mystic Ash "
    "customization unlocks at Smithing Master Hewg; the corresponding spell must be owned first."
)

# (name, armaments, affinity, effect, scaling_note, acquisition_detail, is_new)
AOW_ENTRIES = [
    # ── New Ashes of War ──
    ('Spinning Chain', 'Flails', 'Keen',
     "Spins the striking part of a flail at high speed to attack. Follow up with a normal or strong "
     "attack to link the momentum of this skill into a successive attack.",
     None, "Dropped by the Night's Cavalry in Dragonbarrow.", 1),
    ("Lord's Stomp", 'All Armaments (Including Catalysts)', 'Heavy',
     "A skill imparted upon Crucible Knights by their lord. Stomp hard on the ground to bring forth "
     "earthen spikes.",
     "Spike damage scales with Strength.",
     "Found in a new Kaiden encampment in the Mountaintops of the Giants.", 1),

    # ── Rebalanced/existing Ashes of War (alphabetical) ──
    ('Aspects of the Crucible: Wings', 'Swords, Polearms (Thrusting) - No Colossal Armaments', 'Sacred',
     "This skill originates from the lifeforms of the Crucible. Grow a golden pair of wings and take to "
     "the air before diving down at the foe, weapon first. A spinning attack is performed when wielding "
     "a twinblade.", None, None, 0),
    ("Assassin's Gambit", 'Straight Swords (Small & Medium), Thrusting Swords', 'Night',
     "Skill that masks the user's presence at the cost of a self-inflicted wound. Grants near-invisibility "
     "to and reduces sounds produced by the user. Critical attacks are also enhanced while this skill is "
     "active.", None, None, 0),
    ('Barbaric Roar', 'Melee Armaments - No Daggers, Thrusting Swords, Whips', 'Heavy',
     "Let loose a bestial roar to rally the spirit and increase attack power. While active, strong attacks "
     "change to savage combo attacks.", "Roar damage scales with Strength.", None, 0),
    ('Barrage', 'Light Bows', None,
     "Archery skill using a bow held horizontally. Ready the bow, then fire off a rapid succession of "
     "shots faster than the eye can see.", None, None, 0),
    ('Barricade', 'All Armaments (Including Catalysts)', None,
     "Skill made famous by Sir Neidhardt. Enter a stance briefly capable of deflecting enemy attacks.",
     None, None, 0),
    ("Beast's Roar", 'All Armaments (Including Catalysts)', 'Bestial',
     "Unleash a beastly roar, rending the air as a forward-travelling projectile.",
     "Roar damage scales with Strength and Dexterity. Target priority increased during animation.",
     "Fifth reward from Gurranq.", 0),
    ('Black Flame Tornado', 'Polearms, Twinblades', 'Fell',
     "Spin armament overhead and then plunge it into the ground to summon a raging vortex of black "
     "flames. Hold to create an initial flame tornado while spinning the armament.",
     "Fire damage scales with Faith.", None, 0),
    ('Blind Spot', 'Backhand Blades', 'Keen',
     "Leap into close quarters to take advantage of the enemy's blind spot and gore them from the side. "
     "Inputs determine which side you strike from. This attack slips below the opponent's guard.",
     None, None, 0),
    ('Blinkbolt', 'Melee Armaments, Seals', 'Cursed',
     "Skill used by the golden knights who served Godwyn. From a low stance, the body is transformed "
     "into a bolt of lightning and charges straight ahead at fulgurous speed.",
     "Lightning damage scales with Faith.", None, 0),
    ('Blood Blade', 'Swords (Small & Medium)', 'Blood',
     "Wound self to coat the armament with blood, then unleash an airborne blood blade that causes "
     "hemorrhaging. Can be fired in rapid succession.",
     "Blood slash damage scales with Arcane. Also inflicts Blood Loss buildup on self.", None, 0),
    ('Blood Tax', 'Thrusting Armaments - No Colossal Armaments', 'Blood',
     "Blood Oath skill granted by the Lord of Blood. Twist to build power, then unleash a flurry of "
     "thrusts that rob the target of both their blood and their HP.", None, None, 0),
    ('Bloody Slash', 'Swords', 'Blood',
     "Blood Oath skill granted by the Lord of Blood. From a low stance, coat the blade in your own blood "
     "to unleash a rending blood slash in a wide arc.",
     "Blood slash damage scales with Arcane. Also inflicts Blood Loss buildup on self.", None, 0),
    ("Braggart's Roar", 'Melee Armaments, Catalysts - No Daggers, Thrusting Swords, Whips', 'Heavy',
     "Declare your presence with a boastful roar. Raises attack power, defense, and stamina recovery "
     "speed.", "Roar damage scales with Strength. Target priority increased during animation.", None, 0),
    ('Carian Greatsword', 'Swords, Staves - No Colossal Armaments', 'Magic',
     "Carian royal prestige embodied in a skill. Transform blade into a magical greatsword and swing it "
     "down. Can be charged to increase its power.",
     "Magic damage scales with Intelligence.",
     "Found in Caria Manor, replacing Carian Grandeur.", 0),
    ('Carian Retaliation', 'Shields (Small & Medium)', 'Magic',
     "Swing the shield to dispel incoming sorceries and incantations, transforming the magic into "
     "retaliatory glintblades. Can also be used in the same way as a regular parry.",
     "Magic damage scales with Intelligence. Costs FP even when not reflecting a spell. Has 5 active "
     "parry frames.", None, 0),
    ('Carian Sovereignty', 'Swords - No Colossal Armaments', 'Magic',
     "Skill passed down the Carian royal family. Transform blade into a magical greatsword and bring it "
     "down. Additional input follows up with a horizontal sweep. Charge either attack to enhance potency.",
     "Magic damage scales with Intelligence.", None, 0),
    ('Charge Forth', 'Polearms (Thrusting), Heavy Thrusting Swords, Twinblades', 'Quality',
     "Quickly charge forward with the armament at the hip, carrying the momentum into a thrust. Hold to "
     "cover a greater distance.", "Benefits from bonuses to running attacks.", None, 0),
    ('Chilling Mist', 'Melee Armaments - No Whips, Fists, Claws', 'Cold',
     "Coat armament in frost, and then slash, spreading frigid mist forwards. The armament retains its "
     "frost for a while.", "Mist damage scales with Dexterity and Intelligence.", None, 0),
    ('Cragblade', 'Melee Armaments - No Whips', 'Gravitational',
     "Skill that manipulates gravity. Bury the armament in the ground, pulling rocks from the earth to "
     "reinforce it. Increases attack power and makes it easier to break enemy stance.", None, None, 0),
    ('Determination', 'Melee Armaments', 'Quality',
     "A knightly skill. Hold the flat of the armament to your face and pledge your resolve, powering up "
     "your next attack.", None, None, 0),
    ('Divine Beast Frost Stomp', 'Melee Armaments, Staves', 'Cold',
     "A skill which imitates the wrath of the divine beast's dance. Lift a leg up high and stamp it down "
     "with great force, sending a powerful wave of frost straight out along the ground. Can be charged to "
     "increase power and range.", "Magic damage scales with Dexterity and Intelligence.", None, 0),
    ('Double Slash', 'Swords, Polearms (Slashing) - No Colossal Weapons', 'Keen',
     "Skill of superior swordsmen. Perform a crossing slash attack from a low stance. Repeated inputs "
     "allow for up to two follow-up attacks.", None, None, 0),
    ('Dryleaf Whirlwind', 'Melee Armaments (Small), Catalysts', None,
     "This skill represents the pinnacle of Dane's footwork-based martial artistry. Rise into the air "
     "with a series of spinning kicks before crashing down with one final strike. Imbues kicking attacks "
     "with energy, increasing their range.", "Damage scales with Strength and Dexterity.", None, 0),
    ('Earthshaker', 'Greataxes, Great Hammers, Great Spears, Colossal Weapons', 'Heavy',
     "Thrust the armament into the ground, then gather strength to unleash an earth-shaking shockwave. "
     "Follow up with a strong attack to swing the armament in a sweeping strike.",
     "AoE damage scales with Strength.", None, 0),
    ('Enchanted Shot', 'Light Bows, Longbows', None,
     "Archery skill that enlivens the arrow with spiritual essence. The resulting shot will fly faster "
     "than regular shots and change its trajectory to follow the target.", None, None, 0),
    ('Endure', 'All Armaments (Including Catalysts)', 'Heavy',
     "Assume an anchored stance to brace for incoming attacks, briefly boosting poise. Damage taken "
     "while using this skill is reduced.",
     "x0.7 damage and Status Buildup received.", None, 0),
    ('Eruption', 'Large & Colossal Swords/Axes/Hammers', 'Magma',
     "Skill of the knights who serve at Volcano Manor. Slam armament into the ground, spawning roiling "
     "lava which spouts up upon release.",
     "Fire damage scales with Intelligence. Lingering lava can stagger smaller enemies.", None, 0),
    ('Flame of the Redmanes', 'All Armaments (Including Seals)', 'Fire',
     "Skill of the Redmanes, who fought alongside General Radahn. Produce a powerful burst of flames in "
     "a wide frontward arc.", "Fire damage scales with Strength.", None, 0),
    ('Flame Skewer', 'Thrusting Armaments (Medium & Large)', 'Fell',
     "Skill of Queelign of the Fire Knights. Enwreathe armament in flame and assume a low stance before "
     "skewering the enemy in a single motion. Strong attack unleashes a follow-up flame attack.",
     "Fire damage scales with Faith and Arcane.", None, 0),
    ('Flame Spear', 'Thrusting Armaments - No Claws, Backhand Blades', 'Fell',
     "Skill of Kood, captain of the Fire Knights. Ready weapon for a thrusting attack and unleash a spear "
     "of flame straight ahead. Charge the attack to increase damage dealt and distance travelled.",
     "Fire damage scales with Faith and Arcane.", None, 0),
    ('Flaming Strike', 'Melee Armaments - No Whips, Colossal Armaments', 'Fire',
     "Skill that emits flame in a wide frontward arc. Follow up with a strong attack to perform a "
     "lunging, sweeping strike. This will also coat the armament in fire.",
     "Fire damage scales with Strength.", None, 0),
    ('Ghostflame Call', 'Swords, Spears, Staves - No Twinblades, Backhand Blades, Small Armaments', 'Cold',
     "Thrust out armament to summon ghostflame. Follow up with a normal attack to set the ground ablaze "
     "with ghostflame, or a strong attack to trigger a massive explosion.",
     "Ghostflame damage scales with Intelligence and Faith.", None, 0),
    ('Giant Hunt', 'Spears, Twinblades, Large and Colossal Thrusting Armaments', 'Quality',
     "Skill developed for confronting gigantic foes. Step forward from a low stance, carrying the "
     "momentum into a sudden upward thrust.", None, None, 0),
    ('Glintblade Phalanx', 'Swords, Polearms (Thrusting), Staves - No Colossal Armaments', 'Magic',
     "Skill used by the enchanted knights who served the Carian royal family. Form an arch of magic "
     "glintblades overhead, which will attack foes automatically. Follow up with a strong attack to "
     "chain this skill into a lunging thrust.", "Magic damage scales with Intelligence.", None, 0),
    ('Glintstone Pebble', 'Swords, Polearms (Thrusting), Staves - No Colossal Armaments', 'Magic',
     "Skill that employs glintstone sorcery of the same name. Follow up with a strong attack to chain "
     "this skill into a lunging thrust, performed while the armament is still imbued with glintstone.",
     "Magic damage scales with Intelligence.", None, 0),
    ('Golden Land', 'Greataxes, Great Hammers, Great Spears, Colossal Weapons', 'Blessed',
     "Thrust armament into the ground, then gather strength to unleash a blast of sacred energy that "
     "coalesces into golden darts. Follow up with a strong attack to swing the armament in a sweeping "
     "strike.", "Holy damage scales with Strength.", None, 0),
    ('Golden Parry', 'Shields (Small & Medium)', 'Blessed',
     "Perform an Erdtree incantation and swing the shield to deflect enemy attacks and break their "
     "stance. Effective even at a slight distance.", "Has 5 active parry frames.", None, 0),
    ('Golden Slam', 'All Armaments (Including Seals)', 'Blessed',
     "Skill of the avatars who protect Minor Erdtrees. Jump up high into the air and crash down on the "
     "ground ahead. The resulting pratfall sends golden shockwaves in all directions. Heavier equip load "
     "frames increase skill power.",
     "Holy shockwave damage scales with Strength. Skill damage scales with Equip Load frame, ranging "
     "from x0.9 at Nimble Frame to x1.15 at Massive Frame.", None, 0),
    ('Golden Vow', 'All Melee Armaments, Seals', 'Blessed',
     "Skill passed down from antiquity among the knights of the capital. Raise armament aloft and pledge "
     "to honor the Erdtree in battle, granting self and nearby allies increased attack power and defense.",
     "Grants self and allies x0.9 damage taken and x1.1 damage dealt for 30 seconds.", None, 0),
    ('Gravitas', 'Melee Armaments, Staves - No Whips, Small Armaments', 'Gravitational',
     "Skill originating from the Alabaster Lords, who had skin of stone. Thrust the armament into the "
     "ground to create a gravity well. In addition to dealing damage, this attack pulls enemies in.",
     "Gravity damage scales with Intelligence. Deals True damage.", None, 0),
    ('Ground Slam', 'All Armaments (Including Catalysts)', 'Heavy',
     "Jump up high into the air and crash down on the ground ahead. The resulting pratfall sends a "
     "powerful shockwave in all directions. Heavier equip load frames increase skill power.",
     "Shockwave damage scales with Strength. Skill damage scales with Equip Load frame, x0.9 at Nimble "
     "Frame to x1.15 at Massive Frame.", None, 0),
    ("Hoarah Loux's Earthshaker", 'Fists, Claws', 'Heavy',
     "Slam both hands onto the ground to violently shake the earth and unleash a shockwave. Follow up "
     "with an additional input to slam the ground again.",
     "AoE damage scales with Strength. Considered a Roar attack.", None, 0),
    ('Hoarfrost Stomp', 'All Armaments (Including Staves)', 'Cold',
     "Stomp hard to spread a trail of freezing mist on the ground. The mist applies the Frostbite status "
     "effect.", "Magic damage scales with Dexterity and Intelligence.", None, 0),
    ('Holy Ground', 'All Shields, Seals', 'Blessed',
     "Raise shield to create an Erdtree-consecrated area that continuously restores HP and boosts "
     "defense for self and allies inside it. Also increases poise attack power.",
     "Up to two consecrated areas may be placed at once. Areas last 50 seconds.", None, 0),
    ('Ice Spear', 'Polearms (Thrusting), Twinblades, Staves', 'Cold',
     "Skill of the warriors who served Lunar Princess Ranni. Spin armament to release cold magic, then "
     "channel it into a piercing spear of ice.",
     "Magic damage scales with Dexterity and Intelligence.", None, 0),
    ("Igon's Drake Hunt", 'Greatbows', None,
     "Skill of Igon, drake warrior. Ready the bow before unleashing a twisted shot with a great bellow "
     "that considerably enhances its power.", None, None, 0),
    ('Impaling Thrust', 'Thrusting Armaments - No Colossal Armaments', 'Keen',
     "Skill that lets piercing armaments overcome enemy shields. Build power, then lunge forward for a "
     "strong thrust that pierces an enemy's guard.", None, None, 0),
    ('Kick', 'All Armaments (Including Catalysts)', None,
     "Push an enemy back with a high kick. Effective against enemies who are guarding, and can break a "
     "foe's stance.", "Damage scales with Strength and Dexterity.", None, 0),
    ('Lifesteal Fist', 'Fists, Claws, Seals', 'Occult',
     "Skill that demonstrates mastery of the art of controlling vital energies. A slow, controlled punch "
     "with an energy-infused fist that renders foes unconscious and steals their HP. Only effective "
     "against foes of human build.", "Magic damage scales with Arcane.", None, 0),
    ('Lightning Ram', 'All Armaments (Including Seals)', 'Lightning',
     "Skill inspired by tumbling rams. Let out a bleat, then tumble forwards, clad in lightning. Tumbles "
     "can be repeated in rapid succession.", "Lightning damage scales with Dexterity.", None, 0),
    ('Lightning Slash', 'Swords, Axes, Hammers', 'Lightning',
     "Call down a bolt of lightning into armament, then swing it down to create an explosive shock. The "
     "armament retains the lightning enchantment for a while.",
     "Lightning damage scales with Dexterity.", None, 0),
    ("Lion's Claw", 'Swords, Axes, Hammers - No Thrusting Swords, Small Armaments', 'Heavy',
     "Skill of the Redmanes, who fought alongside General Radahn. Somersault forwards, striking foes "
     "with armament.", None, None, 0),
    ("Loretta's Slash", 'Polearms, Twinblades', 'Magic',
     "Skill of Loretta, the Royal Knight. Leap forward, imbuing the blade with glintstone, then descend, "
     "accelerating into a sweeping slash.", "Magic damage scales with Intelligence.", None, 0),
    ('Mighty Shot', 'Light Bows, Longbows', None,
     "Archery skill performed from an oblique stance. Ready the bow, then pull the bowstring to its "
     "limit to enhance the power of the shot, penetrating the enemy's guard.", None, None, 0),
    ('No Skill', 'All Armaments (Including Catalysts & Sombers)', None,
     "This armament has no skill. If the armament in the other hand has a skill, that skill will be "
     "used instead.", None, "Dropped by the Fallen Cavalry boss, on the bridge between Limgrave and "
     "Liurnia.", 0),
    ('Overhead Stance', 'Great Katanas', 'Keen',
     "A skill that starts with the blade held high in a ready stance. Execute a normal attack from this "
     "stance to step forward and slash downwards, or a strong attack to deliver a series of downward "
     "slashes.", None, None, 0),
    ('Palm Blast', 'Hand-to-hand, Fist, Claw', None,
     "Skill of the spiritual seekers known as the Dryleaf Sect. Imbues hand with energy before using a "
     "palm strike to unleash an explosive blast. The already formidable power and impact can be "
     "bolstered by charging the attack.", None, None, 0),
    ('Parry', 'Daggers, Curved Swords, Thrusting Swords, Fists, Claws, Shields (Small & Medium)', None,
     "Use this skill in time with a foe's melee attack to deflect it and break that foe's stance. This "
     "provides an opening to perform a critical hit.", None, None, 0),
    ('Phantom Slash', 'Polearms, Twinblades - No Great Spears', 'Quality',
     "Skill inspired by the fond remembrances of the Night's Cavalry. Creates an apparition of the "
     "knights' former instructor who guides a joint lunging upward swing. Additional input allows for a "
     "follow-up attack.", "Phantom damage scales with Strength and Dexterity.", None, 0),
    ('Piercing Fang', 'Thrusting Armaments (Medium & Large)', 'Keen',
     "Skill used by Yura, the Bloody Finger Hunter. Starting with the blade held horizontally, make a "
     "powerful thrust that cannot be blocked.", None, None, 0),
    ('Piercing Throw', 'Throwing Blades', 'Keen',
     "Throw armament with a powerful spin, causing it to bore through foes. When using this skill, the "
     "armament can be thrown further than normal and also pierce through enemies.", None, None, 0),
    ('Poison Moth Flight', 'Swords (Small and Medium) - No Twinblades', 'Poison',
     "Slash with a poison-infused blade. If the follow-up strike lands on a poisoned foe, it will deal "
     "significant damage.",
     "Follow-up strike removes only a single stack of Poison buildup. Follow-up burst damage scales "
     "with enemy strength (stronger against weaker enemies, weaker against major bosses).", None, 0),
    ('Poisonous Mist', 'Melee Armaments - No Whips, Fists, Claws', 'Poison',
     "Bathe armament in poison, and then slash, spreading toxic mist forwards. The armament retains its "
     "poison for a while.", "Mist damage scales with Arcane. Armament buff lasts 15 seconds.", None, 0),
    ('Prayerful Strike', 'Axes, Hammers', 'Sacred',
     "Raise armament aloft in prayer, then slam it into the ground. This inspired blow restores HP to "
     "the self and nearby allies if it successfully hits.", None, None, 0),
    ("Prelate's Charge", 'Large and Colossal Axes/Hammers', 'Fell',
     "Slam armament into the ground to create a surge of flames, then charge in. Hold to continue the "
     "charge.", "Fire damage scales with Faith.", None, 0),
    ('Quickstep', 'All Armaments (Including Catalysts)', 'Keen',
     "Skill prized by the crafty and fleet of foot. Perform a quickstep maneuver that allows for "
     "circling around lock-on targets.", None, None, 0),
    ('Raging Beast', 'Beast Claws', 'Keen',
     "Step with the swiftness of a beast, leap high, and slash foe from above. Initial step can be taken "
     "forward, backward, left, or right. Strong attack allows for a follow-up attack.", None, None, 0),
    ('Rain of Arrows', 'All Bows', None,
     "Archery skill performed from a low stance. Ready the bow, then fire a burst of arrows into the "
     "sky to shower the enemy with projectiles.", None, None, 0),
    ('Raptor of the Mists', 'All Melee Armaments, Catalysts', 'Keen',
     "Duck into a low stance, momentarily vanishing. If an enemy attack connects, avian wings will allow "
     "for a quick escape into the air. Half of the consumed FP will be refunded on a successful dodge.",
     None, None, 0),
    ('Repeating Thrust', 'Thrusting Armaments - No Colossal Armaments', 'Keen',
     "Twist to build power, then unleash a flurry of thrusts.", None, None, 0),
    ('Rolling Sparks', 'Perfume Bottles', None,
     "Scatter perfumed powder before you, triggering rolling explosions of deadly sparks. The properties "
     "of the sparks are determined by the perfume bottle used.", None, None, 0),
    ("Royal Knight's Resolve", 'All Melee Armaments', 'Quality',
     "Skill of the knights who once served the Elden Lord. Hold the flat of the armament to your face "
     "and pledge your resolve, greatly powering up your next attack.", None, None, 0),
    ('Sacred Blade', 'Melee Armaments - No Whips, Fists, Claws', 'Sacred',
     "Grants armament's attacks holy essence and fires off a golden blade projectile. The armament "
     "retains its holy essence for a while.", "Projectile holy damage scales with Faith.", None, 0),
    ('Sacred Order', 'All Melee Armaments', 'Sacred',
     "Skill of the Golden Order fundamentalist knights. Perform a salute and grant the armament holy "
     "essence. Highly effective against Those Who Live in Death.", None, None, 0),
    ('Sacred Ring of Light', 'Polearms, Seals - No Great Spears', 'Sacred',
     "Skill used by the commanders of the Cleanrot Knights. Gather a sacred ring of light in the "
     "armament, then fire it forwards. Can be fired in rapid succession.", None, None, 0),
]


def run():
    with engine.connect() as conn:
        # System-level General Changes note - reuse sl_err_enkindling_system table's pattern
        # by storing it as a special AoW entry name for easy lookup.
        conn.execute(text("DELETE FROM sl_err_aow_skills WHERE name='__GENERAL_CHANGES__'"))
        conn.execute(text(
            "INSERT INTO sl_err_aow_skills (name, effect) VALUES ('__GENERAL_CHANGES__', :txt)"
        ), {'txt': GENERAL_CHANGES})

        inserted = 0
        for name, armaments, affinity, effect, scaling, acquisition, is_new in AOW_ENTRIES:
            conn.execute(text("DELETE FROM sl_err_aow_skills WHERE name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_aow_skills
                    (name, armaments, affinity, effect, scaling_note, acquisition_detail, is_new_to_err)
                VALUES (:name, :arm, :aff, :eff, :scal, :acq, :new)
            """), {
                'name': name, 'arm': armaments, 'aff': affinity, 'eff': effect,
                'scal': scaling, 'acq': acquisition, 'new': is_new,
            })
            inserted += 1
        conn.commit()

        print(f'{inserted} Ashes of War seeded (batch 1).')
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_aow_skills WHERE name != '__GENERAL_CHANGES__'")).scalar()
        print(f'Total ERR AoW skills in DB so far: {total}')


if __name__ == '__main__':
    run()
