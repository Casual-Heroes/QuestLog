"""
Seed: ERR "New Unique Skills" + "Unique Skills" sections - weapon-specific skills tied
to a single unique weapon, distinct from the general rebalanced AoW table (batches 1+2).
Source: err.fandom.com/wiki/Skills, pasted directly by user in chunks.

Entries that duplicated names already seeded in batch1/batch2 (same skill listed twice
on the wiki page, once generically and once under Unique Skills) are skipped here to
avoid overwriting the generic version with a duplicate/weapon-specific one.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_aow_unique_skills.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (name, unique_weapon_name, effect, scaling_note)
NEW_UNIQUE_SKILLS = [
    ('Cursed Blade', 'Suncatcher',
     "Performs a powerful slash with the living sword. Especially potent when latent strength is "
     "unleashed after a perfect deflect.", None),
    ('Dawnblade', 'Dawnglow Greatbolt',
     "Extends the weapon with phantasmal blades to perform a spinning slash. The weapon remains imbued "
     "with holy power, which is especially effective when two-handing.", None),
    ('Dragon Smasher', 'Dragon Greatclaw',
     "Press to swing the claw and launch a wave of lightning straight forward, imbuing the claw with "
     "its power. Hold to perform a charged attack and release the stored lightning in a terrifying "
     "storm that rends even the flesh of dragons.", None),
    ('Dragonbolt', 'Dragonclaw Shield',
     "Skill used by the elite sentinels of the capital's ancient dragon cult. Raise armament aloft to "
     "call down a bolt of ancient dragon lightning.", None),
    ('Empyrean Piercer', 'Immortal Coil',
     "Focus the crucible current and expel it forward with a motion rooted in divine calculus. Striking "
     "a foe in this way boosts spell power for a duration.", None),
    ('Fell Flame Flare', 'Fellthorn Stake',
     "Let the Fell God gaze upon your foes, and slam the stake down with his might, causing a fiery "
     "detonation. Smaller nearby explosions occur following the main blast.", None),
    ('Fell Flame Lariat', 'Fellthorn Clutches',
     "Imbue your fists with the flames of tortured spirits and spin as you move forward, spewing flames "
     "and clotheslining nearby foes. Follow up with a strong attack to cause a fiery detonation.", None),
    ('Flamelost Ignition', 'Flamelost War Spear',
     "Thrust the ceremonial spear and watch it lose its storied luster and ignite a short-lived flame, "
     "whose maddening aftermath will carry on. Repeated inputs allow up to two follow-up attacks, with "
     "each attack increasing the intensity of the flame.", None),
    ('Flamelost Stance', 'Flamelost War Sword',
     "Stand ready with the ceremonial blade as it loses its storied luster and ignites a short-lived "
     "flame. From this stance transition to normal or strong attacks.", None),
    ('Flamelost Sweep', 'Mad Sun Shield',
     "Like a cruel sun, the flame of frenzy is unceasing, and use of this skill sweeps foes with a "
     "frontal exhalation of its maddening flames.", None),
    ('Flamelost Upheaval', 'Flamelost Greatblades',
     "Cross the twin flamelost greatswords to ignite a short-lived flame. A blazing upward heave burns "
     "the very air, and transitions into either a normal or strong followup attack.", None),
    ("Lion's Flame", 'Fury of Azash',
     "Skill of Azash, who fought alongside General Radahn. Launch forwards in a burning somersault, "
     "striking foes with the armament and coating it with fire. The flame of the Redmanes burns away "
     "any lingering rot.", None),
    ("Miquella's Sacred Light", "Miquellan Knight's Sword",
     "Imbue sword with sacred light, and release the light with a great thrust of the sword. The "
     "armament retains its holy essence for a while.", None),
    ('Pulverize', 'Putrescent Bonesmasher',
     "Hold the giant blade with both hands and smash repeatedly at foe's feet. Follow up with a strong "
     "attack to perform a mid-air slam.", None),
    ("Red Wolf's Gambol", "Red Wolf's Fang",
     "Skill of the ferocious Red Wolf. Jump backwards, leaving sigils that create enemy-seeking "
     "glintblades in your wake. Follow up with an additional input to perform a devastating slash "
     "attack.", None),
    ('Starsplitter Stance', 'Meteoric Ore Blade',
     "Sheathe blade, slowing perceived time while it is held at the hip. Follow up with a normal or "
     "strong attack to perform a swift parry or a flurry of dazzling slashes. Additional input causes "
     "an explosive star collapse.", None),
    ("Trapper's Step", 'Vulgar Militia Chain Sickle',
     "Skill prized by the crafty and fleet of foot. Perform a quickstep maneuver that allows for "
     "circling around lock-on targets. Drops a poison trap when held as an axe, and a smoke bomb when "
     "held as a whip.", None),
    ("Troll's Raging Roar (Unique)", "Troll's Hammer",
     "Upgraded Troll's Roar that adds a fiery explosion and lingering flames that do damage over time "
     "to the followup attack, similar to attacks the boss does.", None),
    ('Viper Stance', 'Coilheart',
     "While in stance, use normal attack to thrust forward with shield up, and strong attack to lash "
     "out and bite with the shield's bronze viper. If the thrust attack lands on a poisoned foe, it "
     "will deal significant damage.", None),
]

UNIQUE_SKILLS = [
    ('Alabaster Lord\'s Pull', "Alabaster Lord's Sword",
     "Thrust the armament into the ground to create a gravity well. In addition to dealing damage, this "
     "attack pulls enemies in. Has a greater area of effect than Gravitas.",
     "Skill speed increased and hyperarmor added."),
    ('Ancient Lightning Spear', 'Bolt of Gransax',
     "Imbue the armament with the ancient dragons' red lightning, then throw it as a spear. Can be "
     "charged to increase its power.", None),
    ("Angel's Wings", 'Winged Scythe',
     "Jump and imbue the wing-blade of the armament with light, then deliver a slashing attack on the "
     "enemy. The white wings heal nearby Spirit Ashes, while impeding recovery using flasks of tears "
     "for targets.",
     "Minor damage over time added to hit effect; scaling depends on hit enemy, much stronger against "
     "weaker targets. Heals nearby Spirit Ashes by 10% of Max HP + 50 on hit."),
    ('Bear Witness!', 'Grafted Dragon',
     "Grant the small dragon a fleeting glimpse of life and thrust it skyward, spewing flames over a "
     "wide frontward area.", None),
    ("Beast's Step", 'Cinquedea',
     "Skill prized by the ever restless beasts. Perform a quickstep maneuver that allows for circling "
     "around lock-on targets. Bestial incantations cast immediately after using this skill have "
     "increased attack power, lasting as long as the casting of bestial incantations persists.", None),
    ('Blade of Death', 'Black Knife',
     "Unleash the power of the Rune of Death to fire off a blade-like projectile. In addition to "
     "dealing immediate damage, the blade reduces the enemy's maximum HP and continues to wear down HP "
     "for a while.",
     "After skill use, Black Knife receives x1.01 Holy Attack Power / +10 Holy Damage for 8 seconds. "
     "Attacks inflict a Minor Destined Death effect on hit."),
    ('Blade of Gold', 'Blade of Calling',
     "Leap into the air, charging the armament with golden flames that are then shot at the enemy as a "
     "single, blade-like projectile. Inflicts holy damage.",
     "Deals increased Poise Damage and knockback, especially compared to the Black Knife's Blade of "
     "Death skill."),
    ('Blinkbolt: Long-hafted Axe', "Death Knight's Longhaft Axe",
     "From a low stance, the body is transformed into a bolt of lightning and charges straight ahead at "
     "fulgurous speed. Strong attack performs a lightning-charged leaping slash.", None),
    ('Blinkbolt: Twinaxe', "Death Knight's Twin Axes",
     "From a low stance, the body is transformed into a bolt of lightning and charges straight ahead at "
     "fulgurous speed. Strong attack performs a lightning-charged spinning slash.", None),
    ('Bloodblade Dance', "Eleonora's Poleblade",
     "Leap at foe to perform a flurry of tornado-like attacks. Follow up with an additional input to "
     "perform an attack that ends in an evasive maneuver. After dealing damage, bloodflame continues to "
     "build up onset of blood loss for a short time.",
     "Inflicts the Bloodflame Bleed (Blood Loss) over time effect on hit."),
    ('Bloodboon Ritual', "Mohgwyn's Sacred Spear",
     "Raise the sacred spear and pierce the body of the Formless Mother. Stab up to three times, "
     "creating explosions of blood with each thrust that heal the caster. This skill will coat the "
     "armament with bloodflame for a while.",
     "After skill use, Mohgwyn's Sacred Spear receives x1.02 Fire Attack Power / +20 Fire Damage for 20 "
     "seconds. Attacks inflict Bloodflame for 2 seconds, applying 8 Blood Loss every 0.45 seconds (40 "
     "total). Duration resets when reapplied."),
    ("Bloodfiends' Bloodboon", "Bloodfiend's Sacred Spear",
     "Raise the sacred spear and pierce the body of the mother of truth, creating an explosion of "
     "bloodflame in the area surrounding the target. Additional input allows for up to three follow-up "
     "attacks.", None),
    ('Bloodhound Step', "Bloodhound's Claws",
     "Skill that allows the user to become temporarily invisible while dodging at high speed. Moves "
     "faster and travels farther than a regular quickstep. This skill can be used to circle around "
     "lock-on targets.",
     "Exclusive to Bloodhound's Claws. I-Frames decreased from 20 to 16. Properly circles around "
     "enemies as intended."),
    ("Bloodhound's Finesse", "Bloodhound's Fang",
     "Slash upwards with the Bloodhound's Fang, using the momentum of the strike to perform a backwards "
     "somersault and gain some distance from foes. Follow up with a strong attack to perform the "
     "Bloodhound's Step attack.", None),
    ('Bubble Shower', "Envoy's Long Horn",
     "Blow on the horn to release a spume of magic bubbles. The bubbles float gently before raining "
     "down on the target.", None),
    ('Carian Grandeur', "Carian Knight's Sword, Troll Knight's Sword",
     "Carian royal prestige embodied in a skill. Transform blade into a magical greatsword and swing it "
     "down. Can be charged to increase its power by up to two levels. A magic-empowering sigil is "
     "released at full charge.",
     "Exclusive to Carian Knight's Sword and Troll Knight's Sword. Spawns a Terra Magica sigil and "
     "buffs weapon with Magic damage on successful full charge."),
    ('Claw Flick', 'Ringed Finger',
     "Cause the finger to swell, then flex to build up strength before giving enemies an almighty "
     "flick.", None),
    ('Corpse Piler', 'Rivers of Blood',
     "Forms a blade of cursed blood for repeated, interweaving successive attacks. Follow up with an "
     "additional input for further successive attacks. After dealing damage, bloodflame continues to "
     "build up onset of blood loss for a short time.",
     "Inflicts bloodflame's Bleed (Blood Loss) over time effect on hit."),
    ('Corpse Wax Cutter', "Gargoyle's Blackblade",
     "Lost skill of ancient heroes. Lift the sword up high to release the power of corpse wax and "
     "launch it forwards as a blade-like projectile.", "Skill speed increased."),
    ('Cursed-Blood Slice', "Morgott's Cursed Sword",
     "Brace, then charge forward to deliver a downward diagonal slice. The bloody trail of the blade is "
     "followed by a burst of flame. Additional input allows for a follow-up attack.",
     "After skill use, Morgott's Cursed Sword receives x1.05 True Attack Power / +50 Fire Damage for 15 "
     "seconds. This buff does not increase Blood Loss despite the visual effect."),
    ('Darkness', 'Sword of Darkness',
     "Raise the sword aloft and cleave surroundings with darkness. Deals magic damage and temporarily "
     "reduces magic damage negation.", None),
    ('Deadly Dance', "Curseblade's Cirques",
     "An aggressive spinning skill that tears into foes using the circular blades held in each hand. "
     "Additional input allows for a sharp axe-kick follow-up.", None),
    ('Death Flare', 'Eclipse Shotel',
     "Set the lusterless sun ablaze with the Prince of Death's flames, inflicting the death ailment "
     "upon foes. Follow up with an additional input to bring down the armament, triggering an "
     "explosion.", "Skill speed increased."),
    ('Destined Death', "Maliketh's Black Blade",
     "Set free the remnants of Destined Death, plunging the greatsword into the ground to summon a "
     "myriad of blades. This attack will cover the blade in flames of Death for a short time. While the "
     "blade is imbued with Death, use charge attacks to release explosive projectiles.",
     "After skill use, Maliketh's Black Blade receives x1.02 Holy Attack Power / +20 Holy Damage for 20 "
     "seconds. Attacks inflict a Destined Death effect on hit. Heavy attacks release a vertical "
     "blade-like projectile."),
    ("Devonia's Vortex", "Devonia's Hammer",
     "Using the power of the Crucible vortex, violently spin the hammer around and slam the ground, "
     "causing a shockwave. This skill can be charged to increase its power.", None),
    ('Devourer of Worlds', "Devourer's Scepter",
     "Charge the scepter with magic and strike it against the ground to steal the HP of all nearby "
     "enemies.", None),
    ('Dragonform Flame', 'Forked-Tongue Hatchet',
     "Spew fire from a dragon-form maw, sweeping in a frontward arc. The flames on the ground will "
     "continue to burn for a short time.", "Skill considered a Breath attack."),
    ('Dragonwound Slash', "Dragon-Hunter's Great Katana",
     "Designed to hunt colossal dragons, this skill cloaks the armament with a jagged gravel-stone aura "
     "before performing a high leaping slash. Charge the attack to increase the power of the slash.",
     None),
    ('Dynastic Sickleplay', 'Obsidian Lamina',
     "A finessed evasive skill that creates space to maneuver. Inputs dictate direction of the "
     "backstep. Follow up with strong attack to perform an advancing upward slash. Press strong attack "
     "again to bring the weapon back down.", None),
    ("Dynast's Finesse", 'Bloody Helice',
     "Nimbly avoid an attack, securing some distance from foes. Follow up with strong attack to perform "
     "a sudden lunge, and press strong attack again to perform a sweeping slice.", None),
    ("Eochaid's Dancing Blade", "Regalia of Eochaid, Marais Executioner's Sword",
     "Infuse the sword with energy, then fling it forwards in a corkscrew attack. The sword "
     "continuously deals damage while violently spinning. Charge the attack to increase reach and "
     "duration of the spin.", None),
    ('Erdtree Slam', 'Staff of the Avatar, Rotten Staff',
     "Jump up high into the air and crash down on the ground ahead. The resulting pratfall sends golden "
     "shockwaves in all directions. This is the most powerful of all the Ground Slam skills. Heavier "
     "equip load frames increase skill power.",
     "Skill damage scales off Equip Load frame, from x0.9 at Nimble Frame to x1.15 at Massive Frame."),
    ('Establish Order', 'Golden Order Greatsword',
     "Raise the armament in a salute, releasing a golden explosion. Repeated inputs send out waves of "
     "golden light.", None),
    ('Euporia Vortex', 'Euporia',
     "Using the power of the vortex, violently twirl the armament, dealing multiple slashes directly "
     "ahead. The greater the restored luster of the blades, the greater the power of this skill. "
     "However, use of this skill will fully consume the blades' luster.", None),
    ('Familial Rancor', 'Family Heads',
     "Gently rattle the copper heads to summon vengeful spirits that chase down foes. The anguish of a "
     "spouse and children invites accursed wrath.", None),
    ('Fan Shot', "Ansbach's Longbow, Gracebound Longbow",
     "This skill uses the bow held horizontally. Readies five arrows at once, firing them in a "
     "fan-shaped arc.", None),
    ('Firebreather', 'Steel-Wire Torch',
     "Blow into torch flame, spreading flames in a wide frontward arc. The flames on the ground will "
     "continue to burn for a short time.", "Increased duration of fire surfaces produced by the skill."),
    ('Fires of Slumber', "St. Trina's Torch",
     "Blow into the candlestick's flame, creating a stream of hazy purple fire to cover the ground "
     "ahead. The intoxicating flames inflict the sleep ailment upon foes.",
     "Increased duration of fire surfaces produced by the skill."),
    ('Flame Dance', "Giant's Red Braid",
     "Imbue the red braid with the Giants' Flame and lash out in a wide range with a series of agile "
     "swings. The weapon will continue to release flames when swung for a moderate duration after using "
     "this skill. Fire from this skill burns targets.",
     "After skill use, Giant's Red Braid receives an additional Fire damage over time effect for a "
     "short time."),
    ('Flare, O Serpent', 'Serpent Flail',
     "Ignites a flame inside the snakes, temporarily empowering flame attacks. Once ignited, strong "
     "attacks and other moves that strike the ground will cause an explosion.", None),
    ('Flower Dragonbolt', 'Flowerstone Gavel',
     "Calls down the red lightning of the ancient dragons to strike a target. Deals lightning damage "
     "and also temporarily reduces the target's lightning damage negation. Can be charged to increase "
     "its power.",
     "Enemies struck receive an additional x1.12 (Uncharged) to x1.16 (Charged) Lightning Damage for 50 "
     "seconds."),
    ('Flowing Form (Hammer)', 'Nox Flowing Hammer, Nox Flowing Sword',
     "Temporarily transforms the armament into its liquid form. Swing the armament like a whip to "
     "strike surroundings before slamming its teardrop-shaped head down.", None),
    ('Flowing Form (Sword)', 'Nox Flowing Sword',
     "Temporarily transforms the armament into its liquid form. Swing the armament like a whip to "
     "perform a sweeping slice over a wide area.", "Speed increased."),
    ('Frenzyflame Thrust', "Vyke's War Spear",
     "Imbue the spear with the flame of frenzy and leap forwards, plunging it into the ground and "
     "setting off a maddening explosion. The skill inflicts both the enemy and the user with madness.",
     "Increased Madness buildup."),
    ('Ghostflame Ignition', "Death's Poker",
     "Thrust out the barbed rod and set its tip alight with ghostflame. Follow up with a normal attack "
     "to set the ground ablaze with ghostflame, or a strong attack to trigger a massive explosion.",
     "Increased skill speed."),
    ('Gold Breaker', "Marika's Hammer",
     "Leap up high and, while suspended in midair, imbue the rune shard with light before smashing it "
     "down hard onto the ground. The heroic Radagon's signature attack.", "Modified visual effects."),
    ('Golden Crux', 'Greatsword of Damnation',
     "Leap up and skewer foe from overhead. If successful, the weapon's barbs unfold to excruciate from "
     "within; else, additional input releases barbs in the area. There is something of the Golden Order "
     "in the sight of those fixed upon this crux.",
     "Reliability and damage of followup attack greatly increased."),
    ('Golden Tempering', 'Ornamental Straight Sword',
     "Cross the two swords to grant their attacks holy essence. While in effect, strong attack performs "
     "a dual-wielding combo attack.", "Slightly increased weapon buff duration and damage."),
    ('Gravity Bolt', 'Fallingstar Beast Jaw',
     "Imbue the jaw of the fallingstar beast with gravitational lightning, sending a bolt crashing down "
     "a short distance away. Can be fired in rapid succession.", None),
    ('Great Oracular Bubble', "Envoy's Greathorn",
     "Blow on the horn to release a massive magic bubble. The bubble floats gently through the air "
     "towards its target.",
     "Fires three bubbles which spread out and explode. Single-target damage still limited to one "
     "bubble."),
    ('Great Serpent Hunt', 'Serpent Hunter',
     "Perform a powerful forward lunge and follow up with an upward thrust via additional input. When "
     "fighting a great serpent, a long blade of light will appear, revealing the armament's true power.",
     "Amount of hyperarmor frames increased. Second hit's melee hitbox damage increased."),
    ('Hone Blade', 'Bonny Butchering Knife',
     "Perform a stroking action to sharpen the blade, honing its cutting edge and increasing amount of "
     "HP recovered. The greater potentates treasure the tools of their practice.",
     "Animation speed greatly increased. After skill use, Bonny Butchering Knife receives 0.6% Max HP + "
     "12 restoration on hit and x1.05 Slash Damage for 25 seconds."),
    ('Horn Calling: Storm', "Horned Warrior's Greatsword",
     "Invokes tangled horns to cover the weapon's blade. Call a storm into the horns, then mow through "
     "enemies. Additional inputs allow for up to two follow-up attacks.", None),
    ('Horned Calling', "Horned Warrior's Swords",
     "Invokes tangled horns to cover the weapon's blade. Drive the weapon into the ground, calling up a "
     "cluster of piercing horns.", None),
    ('I Command Thee, Kneel!', 'Axe of Godrick',
     "Repeatedly smash the Axe of Godrick into the ground, unleashing two earth-shaking shockwaves. "
     "Follow up with an additional input to produce a third shockwave.", None),
    ('Ice Lightning Slash', 'Dragon Halberd',
     "Slash foes as your body spins. Additional input allows for a follow-up attack that calls down a "
     "bolt of ice lightning. The ice lightning effect will persist for a while.",
     "After skill use, Dragon Halberd receives x1.07 Lightning Attack Power / +70 Lightning Damage and "
     "+30 Frostbite for 20 seconds."),
    ('Ice Lightning Sword', 'Dragonscale Blade',
     "Call down a bolt of ice lightning into the blade and bring it down upon a foe. The ice lightning "
     "effect will persist for a while.",
     "After skill use, Dragonscale Blade receives x1.07 Lightning Attack Power / +70 Lightning Damage "
     "and +30 Frostbite for 20 seconds."),
    ("Igon's Drake Hunt (Greatbow)", "Igon's Greatbow",
     "Skill of Igon, drake warrior. Ready the bow before unleashing a twisted volley with a great "
     "bellow that considerably enhances its power.", "Fires a vertical spread of 7 arrows."),
    ("Jori's Inquisition", 'Barbed Staff-Spear',
     "Thrust the greatstaff into the air, firing off a succession of golden barb-like arcs. Holding the "
     "button down extends the barrage for a short duration.",
     "FP cost of holding the skill for full duration decreased. Skill's damage increased."),
    ('Knowledge Above All', 'Scepter of the All-Knowing',
     "Raise the scepter to manifest the realm of the All-Knowing. Magic and holy damage negation will "
     "be reduced for all within the area, including the caster.",
     "After skill use, caster and targets in the area take x1.15 Magic damage and x1.15 Holy damage for "
     "30 seconds."),
    ("Kowtower's Resentment", 'Gazing Finger',
     "Skill performed as a violent bow using a finger's foremost protrusion. Resentment builds as it is "
     "forced to bow, making it explode with anger. Hold button down to further increase resentment.",
     None),
    ('Last Rites', 'Golden Epitaph',
     "Raise the epitaph to grant the effect of Shared Order to yourself and allies in the vicinity. "
     "Particularly effective at laying to rest Those Who Live in Death.",
     "Buff duration increased and now stacks with other buffs."),
    ('Light', 'Sword of Light',
     "Unleashes the light carved in the armament's blade. Send the sword aloft to let loose a blinding "
     "light whose many rays sweep through the surrounding area. Also temporarily boosts one's own holy "
     "attacks.", None),
    ("Loretta's Enchanted Slash", "Loretta's War Sickle",
     "Skill of Loretta, Knight of the Haligtree. Leap forward, imbuing the blade with glintstone, then "
     "descend, accelerating into a sweeping slash. This will also coat the blade in magic, boosting the "
     "power and cast speed of sorceries as well.",
     "Version of Loretta's Slash exclusive to Loretta's War Sickle. Skill use buffs the weapon with "
     "Magic damage, and increases Magic spell damage and Cast Speed."),
    ('Madding Spear-Hand Strike', 'Madding Hand',
     "Makes hand into the shape of a spear before unleashing a plunging stab that penetrates the body "
     "of the enemy. Afflicts foe with a large dose of madness.", None),
    ('Magma Guillotine', "Magma Wyrm's Scalesword, Makar's Ceremonial Cleaver",
     "Grab the scalesword with both hands, as a wyrm would hold it in its mouth, and leap forwards, "
     "smashing it into the ground and triggering a blast of magma. Follow up with an additional input "
     "to perform a chopping attack.", None),
    ('Magma Shower', 'Magma Blade',
     "Slash at foes in a twirling motion while scattering magma all around. Additional input allows for "
     "a follow-up attack.", "Skill speed and magma pool duration increased."),
    ("Messmer's Assault", 'Spear of the Impaler',
     "A fierce succession of attacks using a flame-coated spear tip. Repeated inputs allow up to two "
     "follow-up attacks. The final move thrusts the spear into the ground, causing countless spears to "
     "form in the surrounding area.", None),
    ("Miquella's Rings of Light", 'Halo Scythe',
     "Summon Miquella's shining halo and fire it forwards. Can be fired in rapid succession.",
     "Projectiles pierce targets."),
    ('Mists of Eternal Sleep', 'Velvet Sword of St. Trina',
     "Releases a velvety purple mist that spreads across a wide frontal area. Afflicts foes with a "
     "heavy buildup of sleep.", None),
    ('Mists of Slumber', 'Sword of St. Trina',
     "Releases a faint purple mist that spreads across a wide frontwards area. The mist inflicts the "
     "sleep ailment upon foes.", "Increased duration of lingering effect surfaces."),
    ('Moon-and-Fire Stance', "Rellana's Twin Blades",
     "Assume ready stance, swords imbued with magic. Follow up with normal attack to cast glintstone "
     "light waves, or strong attack to perform a spinning attack that bathes the area with flame. Light "
     "waves can have up to two follow-up casts with additional inputs.", None),
    ('Moonlight Greatsword', 'Dark Moon Greatsword',
     "Raise the sword aloft, bathing it in the light of the dark moon. Temporarily increases magic "
     "attack power and imbues blade with frost. Charged attacks release blasts of moonlight.",
     "After skill use, Dark Moon Greatsword receives x1.03 Magic Attack Power / +30 Magic Damage and "
     "+40 Frostbite for 35 seconds. Speeds up charge attacks, and charged projectiles travel further."),
    ('Nebula', 'Wing of Astel',
     "Imbue the Naturalborn's wings with magic to send forth a dark cloud of stars that lingers briefly "
     "before exploding.", "Skill speed increased."),
    ('Needle Piercer', "Leda's Sword",
     "Skill of Needle Knight Leda. Generates ten gold needles which pierce their target all at once. "
     "Those pierced are purged of all ailments and special effects alike.",
     "Needles deal pure Holy damage with 100 Faith scaling."),
    ('Night-and-Flame Stance', 'Sword of Night and Flame',
     "Hold the sword level and prepare to cast a sorcery. Follow up with a normal attack to cast a "
     "glintstone stream, or a strong attack to sweep forward with a burst of flames.",
     "Magic portion of the stance is considered Carian."),
    ('Oath of Vengeance', 'Grafted Blade Greatsword',
     "Swear an oath upon the greatsword to avenge the clan, temporarily raising all attributes for a "
     "certain duration. Damage taken while using this skill is reduced, and taking damage will power up "
     "your next attack.",
     "During skill animation: x0.7 Damage Taken, x0.7 Status Buildup, x1.4 Attack Power for 6 seconds "
     "or one attack if damage is taken. After skill use, grants +2 Attributes for 25 seconds."),
    ("Onyx Lord's Repulsion", "Onyx Lord's Greatsword",
     "Thrust the armament into the ground to create a gravity well. In addition to dealing damage, this "
     "attack sends enemies flying away.", None),
    ("Onze's Line of Stars", 'Star-Lined Sword',
     "This skill, named after a demi-human swordmaster, imbues sorcerous energy into lined glintstones "
     "and executes a slash attack. Repeated inputs allow for up to two follow-up attacks, each dealing "
     "greater damage than the last.", None),
    ('Oracular Bubble', "Envoy's Horn",
     "Blow on the horn to release a magic bubble. The bubble floats gently through the air towards its "
     "target.", None),
    ("Ordovis's Vortex", "Ordovis's Greatsword",
     "Channel the power of the crucible to spin the entire sword in midair, building momentum before "
     "slamming the blade down onto the ground. This skill can be charged to increase its power.",
     "Skill speed increased."),
    ('Painful Strike', 'Tooth Whip',
     "A chastening whip strike, honed to maximize pain. Temporarily reduces the action speed of the "
     "target's attack recoveries, and decreases their stamina regeneration. Thus does the pain "
     "encourage obedience.",
     "Action Speed and Stamina Regen debuffs last for 25 seconds on the target."),
    ('Poison Spear-Hand Strike', 'Poisoned Hand',
     "Makes hand into the shape of a spear before unleashing a plunging stab that penetrates the body "
     "of the enemy. Afflicts foe with a large dose of deadly poison.", None),
    ('Prayerful Strike (Halberd)', 'Golden Halberd',
     "Raise armament aloft in prayer, then slam it into the ground. This inspired blow restores HP to "
     "the self and nearby allies if it successfully hits.", None),
    ('Promised Consort', 'Greatswords of Radahn',
     "Imbue the two greatswords with the light of Miquella, then deliver a slashing attack accompanied "
     "by columns of light. Additional input allows for up to two follow-up attacks.", None),
    ("Radahn's Rain", 'Lion Greatbow',
     "Archery skill performed from a low stance. Ready the bow and fire a sudden flurry of arrows up "
     "into the sky. The arrows will pour on foes like rain.", None),
]


def run():
    with engine.connect() as conn:
        inserted = 0
        for name, weapon, effect, scaling in NEW_UNIQUE_SKILLS:
            conn.execute(text("DELETE FROM sl_err_aow_skills WHERE name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_aow_skills
                    (name, effect, scaling_note, is_unique_skill, unique_weapon_name, is_new_to_err)
                VALUES (:name, :eff, :scal, 1, :weapon, 1)
            """), {'name': name, 'eff': effect, 'scal': scaling, 'weapon': weapon})
            inserted += 1
        print(f'{inserted} New Unique Skills seeded.')

        inserted2 = 0
        for name, weapon, effect, scaling in UNIQUE_SKILLS:
            conn.execute(text("DELETE FROM sl_err_aow_skills WHERE name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_aow_skills
                    (name, effect, scaling_note, is_unique_skill, unique_weapon_name, is_new_to_err)
                VALUES (:name, :eff, :scal, 1, :weapon, 0)
            """), {'name': name, 'eff': effect, 'scal': scaling, 'weapon': weapon})
            inserted2 += 1
        conn.commit()
        print(f'{inserted2} Unique Skills seeded.')

        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_aow_skills")).scalar()
        print(f'\nTotal sl_err_aow_skills rows: {total}')


if __name__ == '__main__':
    run()
