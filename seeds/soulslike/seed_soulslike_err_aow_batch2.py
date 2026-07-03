"""
Seed: ERR Ashes of War, batch 2 - completes the main rebalanced AoW table
(Savage Claws through Zamor Ice Storm). Combined with batch 1, this finishes
the full alphabetical "Ashes of War" rebalance section ("FIN" confirmed by user).
Source: err.fandom.com/wiki/Skills, pasted directly by user in chunks.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_aow_batch2.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, armaments, affinity, effect, scaling_note, acquisition_detail, is_new)
AOW_ENTRIES = [
    ('Savage Claws', 'Beast Claws', 'Keen',
     "Pounce like a beast to viciously slash into foe with left and right claws.", None, None, 0),
    ("Savage Lion's Claw", 'Swords, Axes, Hammers - No Thrusting Swords, Small Armaments', 'Heavy',
     "Skill of the particularly brave, even among the Redmanes. Somersault forwards, striking foes with "
     "armament. An additional strike may be performed with an additional input.", None, None, 0),
    ('Scattershot Throw', 'Throwing Blades', 'Keen',
     "Employ smithing arts to conjure multiple copies of the armament in both hands and throw them all "
     "at once. Follow up with an additional input to throw again.", None, None, 0),
    ('Seppuku', 'Swords, Polearms (Thrusting) - No Small or Colossal Armaments', 'Blood',
     "A forbidden technique used by swordsmen from the Land of Reeds. Plunge the blade into your stomach "
     "to stain it with blood. Increases attack power and improves ability to inflict blood loss.",
     None, None, 0),
    ('Shared Order', 'All Melee Armaments, Seals', 'Sacred',
     "Skill of the Golden Order fundamentalist knights. Grant self and nearby allies an aura of holy "
     "essence. Highly effective against Those Who Live in Death.", None, None, 0),
    ('Shield Bash', 'All Shields', None,
     "Brace behind shield before using bodyweight to ram foes while maintaining guarding stance. Weaker "
     "enemies will be shoved backwards, and can even be staggered.", None, None, 0),
    ('Shield Crash', 'All Shields', None,
     "Two-hand the shield and charge forwards while maintaining guard. Weaker enemies will be shoved "
     "backwards and can even be staggered. Hold to extend the duration of the charge forwards.",
     "Benefits from bonuses to running attacks.", None, 0),
    ('Spectral Lance', 'Polearms - No Reapers', 'Occult',
     "Skill of the headless Mausoleum Knights. Hurl a phantasmic spear at foes.",
     "Projectile damage scales with Arcane. Lance pierces targets and has no projectile damage falloff.",
     None, 0),
    ('Spinning Gravity Thrust', 'Swords (Large and Colossal)', 'Gravitational',
     "A gravity skill honed by the disciples of an Alabaster Lord. Uses gravitational power to hang in "
     "the air before rotating the body and charging forward. An additional input allows for a follow-up "
     "attack.", None, None, 0),
    ('Spinning Slash', 'Swords, Axes, Polearms - No Colossal Armaments', 'Keen',
     "Skill favored by dexterous warriors. Slash foes as your body spins. Additionally input allows for "
     "a follow-up attack.", None, None, 0),
    ('Spinning Strikes', 'Polearms - No Great Spears', 'Quality',
     "Polearm skill that performs continuous spinning attacks. Hold to continue the attack. Can be "
     "followed up with a normal or strong attack. Nullifies projectiles such as arrows while spinning.",
     None, None, 0),
    ('Spinning Weapon', 'Swords (Small and Medium), Axes, Hammers, Polearms, Staves - No Great Spears',
     'Magic',
     "Defensive skill employed by Carian princesses. Lifts armament into mid-air, then makes it spin "
     "violently. Those it touches will suffer successive attacks.",
     "Has blocking frames and deflects projectiles.", None, 0),
    ('Square Off', 'Straight Swords, Greatswords', 'Quality',
     "This skill starts with the sword held level. Follow up with a normal attack to slash upwards "
     "through enemy's guard, or a strong attack to perform a running thrust.", None, None, 0),
    ('Stamp', 'Swords, Axes, Hammers - No Small or Medium Swords', 'Heavy',
     "Brace armament and step into a low stance that prevents recoil from most enemy attacks. Follow up "
     "with a normal attack for a sweeping strike, or with a strong attack for an upward strike.",
     None, None, 0),
    ('Storm Assault', 'Polearms (Thrusting), Heavy Thrusting Swords, Twinblades', 'Quality',
     "One of the skills that channel the tempests of Stormveil. Leap forward through surrounding storm "
     "winds and thrust armament downward. The attack will produce more storm winds at the point of "
     "impact.", "Storm projectile damage scales with Strength and Dexterity.", None, 0),
    ('Storm Blade', 'Swords - No Colossal Armaments, Twinblades', 'Quality',
     "Lost skill of Stormveil. Surround armament with shearing storm winds that can be fired forward. "
     "Can be fired in rapid succession.", "Storm projectile damage scales with Strength and Dexterity.",
     None, 0),
    ('Storm Stomp', 'All Armaments (Including Catalysts)', 'Quality',
     "One of the skills that channel the tempests of Stormveil. Stomp hard on the ground to kick up a "
     "momentary storm.", "Storm projectile damage scales with Strength and Dexterity.", None, 0),
    ('Storm Wall', 'Shields (Small & Medium)', 'Quality',
     "Swing the shield to create a wall of storm winds in front of you, deflecting arrows and other such "
     "physical projectiles. Can also be used in the same way as a regular parry.", None, None, 0),
    ('Stormcaller', 'Swords (Slashing), Axes, Hammers, Polearms - No Small or Colossal Armaments',
     'Quality',
     "One of the skills that channel the tempests of Stormveil. Spin armament to create surrounding "
     "storm winds. Repeated inputs allow for up to two follow-up attacks.",
     "Storm projectile damage scales with Strength and Dexterity.", None, 0),
    ('Swift Slash', 'Backhand Blades', 'Keen',
     "A skill passed down amongst hornsent swordsmen. Take a swift forward step to slice through foes. "
     "This sharp strike also fires off a shearing vacuum. Can be charged to increase the skill's power "
     "and the distance of the forward step.", None, None, 0),
    ('Sword Dance', 'Swords, Axes, Polearms (Slashing) - No Colossal Armaments, Great Spears', 'Keen',
     "Quickly close in to perform a series of spinning upward slashes. Follow up with an additional "
     "input to finish with a downward slash.", None, None, 0),
    ('The Rotten Flower Blooms Twice', 'All Armaments (Including Seals)', 'Rotten',
     "(Replaces: The Poison Flower Blooms Twice) Conjures stingers of scarlet rot from below to stab the "
     "enemy. Landing the attack on a foe already inflicted with rot deals massive damage in one fell "
     "swoop.",
     "Stinger damage scales with Dexterity and Faith. Removes only one stack of Scarlet Rot on enemies. "
     "Damage scales based on enemy strength, being more effective on weaker enemies and less effective "
     "against major bosses.", None, 0),
    ("Thops's Barrier", 'Shields (Small and Medium)', 'Magic',
     "Erect a magical forcefield while swinging the shield to deflect sorceries and incantations. Can "
     "also be used in the same way as a regular parry.",
     "Now has an FP cost, but has 5 parry frames and the projectile deflection radius has been "
     "significantly increased, making this ash more reliable.", None, 0),
    ('Through and Through', 'Greatbows', None,
     "Powerful archery skill using a greatbow held in an oblique stance. Ready the greatbow, then twist "
     "the bowstring to fire a mighty greatarrow that can penetrate through enemies.", None, None, 0),
    ('Thunderbolt', 'All Melee Armaments, Seals', 'Bolt',
     "Skill used by the capital's ancient dragon cult. Raise armament aloft to call down a bolt of "
     "lightning. Can be fired in rapid succession.",
     "Lightning damage scales with Faith. Penetrates enemy guards.", None, 0),
    ("Troll's Roar", 'Swords (Large and Colossal), Axes, Hammers', 'Heavy',
     "Look into the distance and let out an intense roar, generating a powerful shockwave that blows "
     "back surrounding foes. Follow up with a strong attack to slam the armament down.",
     "Roar damage scales with Strength.", None, 0),
    ('Unsheathe', 'Katanas', 'Keen',
     "Skill of swordsmen from the Land of Reeds. Sheathe blade, holding it at the hip in a composed "
     "stance. Follow up with a normal or strong attack to perform a swift parry or slash attack.",
     None, None, 0),
    ('Vacuum Slice', 'Swords, Axes - No Colossal Axes', 'Quality',
     "Lost skill of ancient heroes. Hold the armament aloft to surround it with a shearing vacuum, then "
     "launch it forwards as a blade-like projectile.",
     "Storm projectile damage scales with Strength and Dexterity.", None, 0),
    ('Vow of the Indomitable', 'All Shields, Seals', 'Blessed',
     "Skill of the ancient warriors of the Erdtree. Hold shield aloft to imbue yourself with golden "
     "power, granting momentary invincibility.", None, None, 0),
    ('Wall of Sparks', 'Perfume Bottles', None,
     "Scatter perfumed powder in vicinity, producing intense sparks after a brief delay. Can be charged "
     "to increase power and range. The properties of the sparks are determined by the perfume bottle "
     "used.", None, None, 0),
    ('War Cry', 'Melee Armaments - No Daggers, Thrusting Swords, Whips', 'Heavy',
     "Give a war cry to rally the spirit and increase attack power. While active, strong attacks change "
     "to charging attacks.",
     "Roar damage scales with Strength. Target priority increased during animation. Does not overwrite "
     "other weapon buffs.", None, 0),
    ('Waves of Darkness', 'Greataxes, Great Hammers, Great Spears, Colossal Weapons', 'Gravitational',
     "Plunge armament into the ground to release three waves of darkness. Follow up with a strong "
     "attack to swing the armament in a sweeping strike.",
     "Gravity wave damage scales with Intelligence. Deals True damage.", None, 0),
    ("White Shadow's Lure", 'All Armaments (Including Catalysts)', 'Occult',
     "Hold armament in a brief, silent prayer to create a white shadow. The apparition lures in foes of "
     "human build who are not in combat, drawing their aggression. Effective on demi-humans even if they "
     "are already in a combat state.", None, None, 0),
    ('Wild Strikes', 'Axes, Hammers, Curved Swords, Greatswords', 'Heavy',
     "Swing armament with wild abandon. Hold to continue swinging. Can be followed up with a normal or "
     "strong attack.", None, None, 0),
    ('Wing Stance', 'Thrusting Swords, Light Greatswords', 'Quality',
     "Calmly assume a right-sided stance. Normal attack triggers a rapid three-slash combination. Strong "
     "attack triggers a leaping thrust.", None, None, 0),
    ('Rallying Standard', "Commander's Standard", None,
     "Hoist the war banner aloft and give a rallying command. Raises attack power and defense for self "
     "and nearby allies. Storm attacks gain an even greater increase in attack power.",
     "After skill use, grants +2 Endurance when empowering an ally, increasing by +1 for each "
     "additional ally (stacks up to +10 Endurance). Additional Attack Power and Defense for self and "
     "affected allies, and additional Attack Power to storm attacks. Buff also affects sorcery and "
     "incantation damage, has a 30% increased duration when cast on allies, and stacks with other "
     "buffs.", None, 0),
    ('Rancor Shot', 'Bone Bow', None,
     "Imbue arrows with vengeful spirits, before firing off a barrage. Imbued arrows chase down foes as "
     "they cut through the air.", None, None, 0),
    ('Rancor Slash', 'Spirit Glaive, Spirit Sword', None,
     "Spin around, slashing foes while summoning vengeful spirits which chase down foes. Additional "
     "input allows for a follow-up attack.", None, None, 0),
    ('Red Bear Hunt', "Red Bear's Claw", None,
     "Slaughters prey with sharp claws in a great swipe of the arm. The attack creates a vacuum which "
     "deals continuous damage. Repeated inputs allow for up to two follow-up attacks.", None, None, 0),
    ('Reduvia Blood Blade', 'Reduvia', 'Blood',
     "Slash with the wicked dagger, transforming its never-drying bloodstains into airborne blades that "
     "cause blood loss. Can be fired in rapid succession.",
     "Blood Loss buildup increased, and inflicts a small amount of Blood Loss on the user.", None, 0),
    ('Regal Beastclaw', 'Beastclaw Greathammer', None,
     "Slam the hammer into the ground, rending the land asunder with the armament's five bestial claws.",
     None, None, 0),
    ('Regal Roar', 'Axe of Godfrey', 'Heavy',
     "Let loose a mighty war cry, raising attack power, while sending out a shockwave that cannot be "
     "guarded against by stomping the ground. While active, strong attack becomes a lunging slash.",
     "Animation speed increased. Target priority during animation increased. Range of roar and stomp "
     "area of effect increased. Buffs granted by Regal Roar last for 25 seconds.", None, 0),
    ('Repeating Fire', 'Repeating Crossbow', None,
     "This skill readies the weapon's rapid-fire mechanism. Once in ready stance, crank the handle to "
     "fire bolts in rapid succession.", None, None, 0),
    ("Revenger's Blade", 'Falx', None,
     "Dash up to an enemy and slash them open with the blades held in each hand. By holding down the "
     "button, the initial dash will be extended. Follow up with strong attack to hack the enemy to "
     "pieces.", "Followup attack tracking greatly improved.", None, 0),
    ("Romina's Purification", 'Poleblade of the Bud', None,
     "Imbues bud-blade with scarlet rot butterflies before unleashing two large sweeping slashes. This "
     "was once considered a sacred act of purification.", None, None, 0),
    ("Rosus' Summons", "Rosus' Axe", None,
     "Raise the axe aloft to summon those lost in death. Three skeletons will appear at a distance and "
     "attack in tandem before vanishing.",
     "Hitbox size of skeletons increased. Skeletons now deal Slash damage.", None, 0),
    ('Ruinous Ghostflame', 'Helphen Steeple', None,
     "Swing the sword to bathe its blade in ghostflame. The ghostflame increases magic damage, and also "
     "has a bitterly cold bite.",
     "After skill use, Helphen Steeple receives x1.5/x0.67 Physical Attack Power and +50 Frostbite for "
     "25 seconds.", None, 0),
    ('Sacred Phalanx', 'Cleanrot Spear', None,
     "Release the power of a hidden incantation to erect a palisade of golden spears forwards.",
     "Golden spears last longer, travel further, and penetrate guards.", None, 0),
    ('Sea of Magma', 'Magma Whip Candlestick', None,
     "Swing a molten whip overhead to temporarily cover the surrounding area in a sea of magma. Hold to "
     "continue swinging the lava whip.", None, None, 0),
    ('Shadow Sunflower Headbutt', 'Shadow Sunflower Blossom', None,
     "Slam down the blossom of a large shadow sunflower, sending out a shockwave that flattens foes. "
     "Additional inputs allow for repeated followup attacks, while heavy attacks will end the combo with "
     "a final attack.", None, None, 0),
    ('Shriek of Milos', 'Sword of Milos', None,
     "Lets out a horrific cursed scream that reduces all damage negation and status resistances for "
     "nearby foes. While active, strong attacks will change to a combo attack.", None, None, 0),
    ("Siluria's Woe", "Siluria's Spear", None,
     "Thrust the weapon in a spiraling motion, surrounding it in a vortex of wind. Charged attacks have "
     "the power to blow away enemies and can fire the tornado forwards.",
     "Projectile and melee hits can both hit the same enemy.", None, 0),
    ('Sleep Evermore', "Thiollier's Hidden Needle", None,
     "Pierces the enemy deeply with a poison-coated needle that deals heavy sleep buildup. If the "
     "follow-up strike lands upon a foe who is already in a state of slumber, it will deal significant "
     "damage.", None, None, 0),
    ('Smithing Art Spears', 'Anvil Hammer', None,
     "Slam the red-hot anvil into the ground, sending up countless spears as it is pulled out. The "
     "spears disappear instantly.", None, None, 0),
    ('Solitary Moon Slash', 'Greatsword of Solitude', None,
     "Sharply slash downward using the greatsword, shooting forward an arc of light. Strong attack "
     "allows for an advancing follow-up.", None, None, 0),
    ('Sorcery of the Crozier', "Watchdog's Staff", None,
     "Channel magic into the glintstone to activate an ancient sorcery, producing floating magic "
     "projectiles that chase enemies automatically.", None, None, 0),
    ('Soul Stifler', 'Winged Greathorn', None,
     "Raise the greathorn's wings to summon a soul-sapping miasma. Enemies in the affected area will "
     "temporarily suffer from reduced damage negation and constant sleep buildup.", None, None, 0),
    ('Spearcall Ritual', 'Death Ritual Spear', None,
     "Thrust the spear high, bearing prayers into the sky to summon a downpour of spectral spears.",
     "Projectile spread and hitbox size increased.", None, 0),
    ('Spinning Guillotine', 'Putrescence Cleaver', None,
     "Hold the putrid blade at both ends and arch body backwards to deliver a powerful overhead chop. "
     "Repeated inputs deliver follow-up attacks for as long as stamina allows. Strong attack performs a "
     "leap followed by a spinning attack.", None, None, 0),
    ('Spinning Staff', 'Carian Regal Scepter, Snow Witch Scepter', None,
     "Channel magic into the glintstone to suspend the scepter in mid air and cause it to spin "
     "violently. Those it touches will suffer successive magic attacks.",
     "Has blocking frames and will deflect projectiles.", None, 0),
    ('Spinning Wheel', "Ghiza's Wheel", None,
     "Strike the wheel against the ground to set it spinning at top speed. Hold to keep the wheel "
     "spinning. Can be used while walking to push the armament into enemies.", None, None, 0),
    ('Spiral Nebula', "Bastard's Star", None,
     "Imbue the Naturalborn's stars with magic to perform a sweeping strike. This attack leaves a dark "
     "cloud of stars in its wake that lingers briefly before exploding.", None, None, 0),
    ('Starcaller Cry', 'Starscourge Greatswords', None,
     "Bring the two swords together and roar into the skies, pulling in enemies with a gravitational "
     "wave. Follow up with an additional input to slam down with gravity-infused swords. The follow up "
     "attack fortifies the swords with stone, increasing attack power and making it easier to break "
     "enemy stance.",
     "After skill follow-up attack, Starscourge Greatswords receive x1.03 Physical Attack Power, x1.09 "
     "Poise Damage, x1.15 Stamina Damage, +60 Lightning Damage for 20 seconds. Skill animation speed "
     "increased.", None, 0),
    ("Surge of Faith", 'Cranial Vessel Candlestand', None,
     "Set the flames of Birac's faith ablaze in the cranial vessel, then raise it aloft to rain down "
     "fireballs in all directions. Repeated inputs will continue to raise the armament aloft, continuing "
     "the attack. Fire from this skill burns targets.",
     "Animation speed greatly increased. Fire projectiles have larger hitboxes and slightly track "
     "targets.", None, 0),
    ('Storm Kick', "Veteran's Prosthesis", None,
     "Thrust the prosthetic leg blade into the ground, creating a storm. Follow up with a strong attack "
     "to perform a lightning-infused jumping attack.", None, None, 0),
    ("Taker's Flames", 'Blasphemous Blade', None,
     "Raise the sacred sword aloft to set it ablaze with blasphemous flames, then bring it down to fire "
     "off a forward blast. The flames steal HP from those they touch.", None, None, 0),
    ("The Queen's Black Flame", 'Godslayer Greatsword', None,
     "Set the blade ablaze with god-slaying black flame before delivering a sweeping slash. Additional "
     "input allows for a follow-up attack. The black flames will persist in the spiral blade for a "
     "while.",
     "After skill use, Godslayer's Greatsword receives x1.03 Fire Attack Power / +30 Fire Damage for 10 "
     "seconds. Attacks inflict Black Flame.", None, 0),
    ("Thundercloud Form", "Dragon King's Cragblade", None,
     "Temporarily transform into a red thundercloud and fly through the air, then plunge down with a "
     "lightning-infused blade. Hold to increase the reach of the thundercloud form.",
     "I-Frames added to portions of the skill where player model is invisible.", None, 0),
    ('Thunderstorm', 'Stormhawk Axe', None,
     "Imbue the armament's wing-blade with lightning and swing it around to create a tempestuous "
     "lightning storm. Follow up with an additional input to perform up to two spinning attacks. The "
     "lightning will stay on the blade for a while.", None, None, 0),
    ('Transient Moonlight', 'Moonveil', None,
     "Sheathe blade, holding it at the hip in a composed stance. Follow up with either a normal or a "
     "strong attack to draw the blade at great speed for an instant parry or slash attack. Both attacks "
     "fire off a wave of light.",
     "Skill R1 is a parry and does not deal direct melee damage. Distance of R1 projectiles increased. "
     "Projectile damage of R1 parry and R2 attack is identical.", None, 0),
    ("Troll's Raging Roar", "Troll's Hammer", None,
     "Look into the distance and let out an intense roar, generating a powerful shockwave that blows "
     "back surrounding foes. Follow up with a strong attack to slam the armament down, unleashing the "
     "Flame of the Fell God.", None, None, 0),
    ('Unending Dance', 'Dancing Blades of Ranah', None,
     "A furious dance formed by a succession of slashing attacks. Hold the button down to sustain the "
     "dance for as long as stamina allows.", None, None, 0),
    ('Unblockable Piercing Blade', 'Cipher Pata', None,
     "Imbue the cipher blade with light, then lunge forward with a sudden piercing attack. This attack "
     "can not be blocked.", None, None, 0),
    ('Unblockable Rending Blade', 'Coded Sword', None,
     "Imbue the cipher blade with light, extending its length, then strike with a sudden sweeping "
     "attack. This attack cannot be blocked.", "Skill speed increased.", None, 0),
    ('Waterfowl Dance', 'Hand of Malenia', None,
     "Perform a series of one-footed leaps in the manner of a waterfowl to unleash a swift yet graceful "
     "slashing combo. Repeated inputs allow for up to two follow-up attacks.", None, None, 0),
    ('Wave of Destruction', 'Ruins Greatsword', None,
     "Raise the sword up high, then strike it against the ground to fire off a wave of gravitational "
     "force.", None, None, 0),
    ('Wave of Gold', 'Sacred Relic Sword', None,
     "Imbue the sword with bygone golden glory, then fire it at foes. A wide, golden wave fans out "
     "forwards, sweeping through all enemies caught in its path.", "Skill speed increased.", None, 0),
    ('Weed Cutter', "Rakshasa's Great Katana", None,
     "Performs scythe-like horizontal swings with the sword, cutting men down as if they were weeds. "
     "Additional inputs allow for the continuation of the attack for as long as stamina remains.",
     None, None, 0),
    ('White Light Charge', 'Ancient Meteoric Ore Greatsword', None,
     "Summons white light from the crevice in the weapon's ancient meteoric ore, using its power for a "
     "charging attack which pierces foes. Additional input causes the light to explode.", None, None, 0),
    ('Witching Hour Slash', 'Sword of Night', None,
     "Hold the sword level and infuse it with the dark of Night before unleashing a series of "
     "incorporeal attacks. This attack cannot be blocked. Can be charged to increase its power.",
     None, None, 0),
    ("Wolf's Assault", 'Royal Greatsword', None,
     "Infuse the greatsword with frost, then perform a forward somersault to plunge it into the ground. "
     "Then, pull it out to release a cold blast.", "Frostbite buildup increased.", None, 0),
    ('Zamor Ice Storm', 'Zamor Curved Sword', None,
     "Plunge the curved sword into the ground, building power before unleashing a freezing storm that "
     "batters the surroundings.", None, None, 0),
]


def run():
    with engine.connect() as conn:
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

        print(f'{inserted} Ashes of War seeded (batch 2).')
        total = conn.execute(text(
            "SELECT COUNT(*) FROM sl_err_aow_skills WHERE name != '__GENERAL_CHANGES__'"
        )).scalar()
        print(f'Total ERR AoW skills in DB: {total} (main rebalanced AoW table complete)')


if __name__ == '__main__':
    run()
