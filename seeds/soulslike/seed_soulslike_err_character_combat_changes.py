"""
Seed: ERR Character Changes + Combat Changes reference pages.
Source: err.fandom.com/wiki/Character_Changes and /wiki/Combat_Changes, pasted directly
by user. Stored as readable reference sections (not wired into calculator logic yet -
that is a separate follow-up task to update computeAR/equip-load/poise math in
soulslike_builder.html using the exact thresholds captured here).

Run: chwebsiteprj/bin/python3 seed_soulslike_err_character_combat_changes.py
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

CHARACTER_CHANGES = {
    'universal': (
        "Increased default Talisman and Spell slots by 1 (Godfrey no longer drops a Talisman pouch; no "
        "memory stones removed, this is the engine-level max spell slots). Almost all non-weapon buffs "
        "can now stack with each other (very few overwrite each other) - this reduces guesswork around "
        "buff combos, but all buffs were rebalanced with lower individual effects and stacking similar "
        "buffs has diminishing returns (2nd buff ~72% value, 3rd ~50% value). Weapon buffs still "
        "overwrite each other to prevent absurd stacking. All buffs are removed when resting at a Site "
        "of Grace.\n\n"
        "Increased healing from HP Regen effects; almost all regen-over-time now has both flat healing "
        "and a % of Max HP, scaling with Max HP. HP Regen effects can now stack (in vanilla nearly all "
        "overwrite each other) - balanced via diminishing returns on stacking. Spell/Skill active HP "
        "Regen (Blessing's Boon, Holy Ground, Bestial Vitality) can also stack. Warning (unverified): "
        "many HP Regen effects active can reduce effectiveness of active recovery like Crimson Dagger "
        "Talisman or Godskin Swaddling Cloth.\n\n"
        "Changed fall impact thresholds: 'medium' landing now occurs above 12m (was 4m), 'heavy' "
        "landing above 16m (was 8m) - much less slowdown from falls. Fall damage (starting at 16m) and "
        "lethal fall threshold are unchanged."
    ),
    'torrent': (
        "Removed the confirmation prompt to consume a flask when re-summoning Torrent via whistle after "
        "death - a flask is now used automatically. Greatly increased Torrent's movement speed while "
        "decreasing his health and increasing player vulnerability while riding. New Raisin items "
        "customize Torrent's abilities, craftable after acquiring Stable-Master's Cookbook [1] (dropped "
        "by a new Haligtree Knight roaming Mistwood, Limgrave). Added Max HP scaling to Torrent based on "
        "player level - up to 2x HP at level 200, +5% HP every 10 levels. Fixed a bug where Torrent "
        "wouldn't heal between loading screens or at Sites of Grace. Torrent is no longer immune to "
        "swamp status buildup and will take damage there; Raisins now cure status in addition to "
        "healing. Improved controls: stopping animation can cancel Torrent's gallop state (easier to "
        "slow down), and Torrent slides much less when landing with no direction held. Torrent can now "
        "be dyed using Body Hues in the Gilded Court. Combat with a Camp Leader disables Torrent until "
        "the leader(s) is defeated."
    ),
    'fp_stamina_scaling': (
        "FP and Stamina changed to a base-100 scale rather than base-10 (what was 50 FP in vanilla is "
        "now 500 FP). Creates more distinct granularity, lets regen effects have more impact at low "
        "amounts, and allows finer-precision balancing."
    ),
    'level_cap_scaling': (
        "Level cap is now 200. Vigor, Mind, and Endurance give more Max HP/FP/Stamina beyond the "
        "original softcap of 60 - scaling reworked to give slightly more early, less in mid levels, "
        "vastly more at high levels (see ERR Level Progression spreadsheet). Weapons benefit much more "
        "from higher stat investment; split-scaling weapons/catalysts updated to require similar "
        "investment as single-stat gear. Rule of thumb: A/S scaling in a stat benefits from going to "
        "80-99 of that stat; B or lower scaling benefits less from a single stat but scales effectively "
        "across multiple stats (affinities can improve scaling further - see ERR Weapon Calculator for "
        "exact values). Reduced Defense and Status Resistance gained from leveling. Enemy rune drops "
        "increased to make higher levels realistically achievable in a single NG playthrough."
    ),
    'vigor_hp': (
        "HP values adjusted to roughly 2.3x vanilla at 99 Vigor (2100 vanilla -> 4800 Reforged). Enemy "
        "damage widely rebalanced/adjusted to partially scale with this increase, with many "
        "attack-specific raises/lowers based on attack nature and enemy type. Increasing Vigor also "
        "slightly increases Status Buildup Drain Speed, from a minimum of 3/sec up to a maximum of "
        "4/sec at 99 Vigor."
    ),
    'endurance_stamina': (
        "Endurance no longer increases Equip Load, which is now locked at a flat 100 base and only "
        "raised/lowered by gear or conditional effects (see Combat Changes / Equip Load section). "
        "Stamina values adjusted to roughly 13x vanilla at 99 Endurance (170 vanilla -> 2200 Reforged) - "
        "stamina costs for all actions adjusted mutually, so the effective stamina increase from "
        "vanilla to Reforged is not a flat 13x. Stamina Regen speed now scales with Endurance, up to a "
        "40% increase at 99 Endurance. Completely depleting stamina now applies a brief 'Out of "
        "Stamina' penalty that considerably reduces Stamina Regen for a few seconds (more intense "
        "visual effect in PvP)."
    ),
    'mind_fp': (
        "FP values adjusted to roughly 8x vanilla at 99 Mind (450 vanilla -> 3500 Reforged) - FP costs "
        "adjusted mutually, so the effective increase is not a flat 8x. Added a slight passive FP Regen "
        "while in combat (0.1% Max FP + 1 every 2 seconds). Added the ability to restore FP by "
        "attacking enemies, scaling with weapon speed, attack type, Intelligence, and Max FP. Added FP "
        "regeneration via 'Generator' spells on hit (restore both a flat amount and a % of max FP). "
        "Mind now scales Cast Speed instead of Dexterity. Mind also scales Spirit Fury duration "
        "(Spirit Ash mechanic) - base 25 seconds at 1 Mind, scaling up to 50 seconds at 99 Mind "
        "(unverified exact figures, though build planner uses 30s-40s elsewhere - check in-game)."
    ),
    'damage_attributes': (
        "Strength increases Poise Damage up to +25% max, and increases Physical Defense somewhat more "
        "than other stats. Dexterity increases Critical Damage up to +50% max, and reduces Stamina Cost "
        "of melee attacks/spells by up to 10%. Intelligence increases FP Regen from attacks/spells up "
        "to +40% max (catalyst heavy attacks and generator spells benefit at 25% efficacy), and "
        "increases Elemental Defense somewhat more than other stats. Faith increases Common Buff "
        "Duration (spells, AoW, consumables, Enkindled Ashes, Armor Passives) up to +60% max, and "
        "increases Poise up to +10%. Arcane increases Status Buildup dealt by all status effects up to "
        "+50% max, and increases Item Discovery. All these effects scale all the way to 99 in a stat - "
        "see the ERR Level Progression spreadsheet for exact per-level values."
    ),
    'scadutree_revered_ash': (
        "Adjusted Scadutree Blessing values and added/moved Scadutree Fragments so the world total "
        "exceeds the requirement for max Blessing level. Scadutree Blessing table (v2.1.2.3), levels "
        "1-20: Damage Dealt from x1.025 (lvl 1) up to x1.5 (lvl 20) in +0.025 steps; Damage Taken from "
        "x0.968 (lvl 1) down to x0.667 (lvl 20).\n\n"
        "Adjusted Revered Spirit Ash values (v2.1.2.3), levels 1-10: Spirit Ash Max HP x1.025 to x1.25; "
        "Spirit Ash Attack Power x1.05 to x1.5; Spirit Ash Damage Taken x0.976 down to x0.8; Torrent "
        "Damage Taken x0.939 down to x0.667."
    ),
    'starting_classes_note': (
        "All starting classes are level 10 with equal total stats (89), except Wretch who starts at "
        "level 1 with all stats at 10 (total 80). Each class starts with a talisman, and some receive "
        "bonus spells. Full per-class equipment/talisman/spell/stat data already seeded in sl_classes "
        "(game='err') - confirmed matching this source exactly."
    ),
}

COMBAT_CHANGES = {
    'damage_types_defense': (
        "'Standard Damage' generally removed for both player and enemies - now called True Damage, "
        "dealt exclusively by attacks that logically ignore armor (liquid/gas attacks, Physical damage "
        "of Critical Attacks like grabs/ripostes). Specific partially-incorporeal weapons (e.g. "
        "Morgott's Cursed Sword) also deal True Damage both when player- and enemy-wielded. True Damage "
        "is almost never resisted, but enemies are also never weak to it. Armor and Dragoncrest Shield "
        "talismans grant no True Damage Negation, but conditional All Damage Negation boosts (Golden "
        "Vow, Ritual Shield Talisman) DO grant True negation.\n\n"
        "Greatly improved consistency of enemy elemental damage types - enemies visually using an "
        "elemental attack now consistently deal that type; enemies using elemental weapons deal a "
        "consistent mix of Physical + Elemental damage (e.g. Crucible Knights now deal substantial Holy "
        "damage with weapon attacks alongside reduced Physical), encouraging varied defenses over "
        "stacking pure Physical negation.\n\n"
        "Generally reduced both enemy and player Defense (benefits low-damage weapons like Daggers and "
        "split-damage weapons, since passing through Defense twice is less punishing). Exact enemy "
        "defense values viewable in the Codex of the All-Knowing. Slightly reworked the Defense Formula "
        "so Attack Power isn't impacted when trivial - in cases where incoming damage greatly exceeds "
        "defense, attacks now deal 1.0x instead of capping at 0.9x, making displayed Attack Power more "
        "accurate."
    ),
    'movement_animations': (
        "Delayed roll input buffer on most player stagger animations (now begins 3-30 frames after "
        "stagger starts depending on animation length) - greatly reduces accidental roll inputs. "
        "Significantly improved sprinting pivot animation: cancellable on the first possible frame, "
        "faster, transitions into dashing attacks instead of stationary light/heavy attacks, and grants "
        "a brief Movement Speed and attack movement distance increase after pivoting. Weapon/stance "
        "swap animations now cancellable on the first possible frame - instant action after swapping. "
        "Decreased jump animation startup and removed the 'reset to base running speed' on jump while "
        "sprinting (removes need to 'bunny hop' via block-tapping). Decreased recovery time of most "
        "attacks (less ending lag, move sooner after an action). Sped up many abnormally slow player "
        "attacks, especially Weapon Skills."
    ),
    'equip_load': (
        "Equip Load states renamed (cosmetic only): Light Load -> Nimble Frame, Medium Load -> Balanced "
        "Frame, Heavy Load -> Solid Frame, Overloaded -> Massive Frame.\n\n"
        "New thresholds: Nimble Frame 0-33.3%, Balanced Frame 33.3-66.6%, Solid Frame 66.6-99.9%, "
        "Massive Frame 100%+. Each frame now has an identical-sized range, making Nimble Frame slightly "
        "less restrictive than vanilla.\n\n"
        "Equip Load now only accounts for the heaviest armament in EACH hand (right + left), ignoring "
        "the other four equipment slots entirely - may not be accurately reflected in the in-game "
        "preview UI while equipping.\n\n"
        "Equip Load is no longer increased by leveling Endurance. It now starts at a flat 100 base, "
        "raised/lowered only by gear or conditional effects (talismans, fortunes, buffs, debuffs). "
        "Armor weight/effectiveness increased to compensate, and Solid Frame + Massive Frame "
        "effectiveness vastly buffed: Solid Frame no longer uses heavy walk/run animations; Massive "
        "Frame no longer removes sprinting or jumping. Goal: give each Equip Load state its own "
        "identity tied to armor worn, rather than something you out-level via Endurance.\n\n"
        "NOTE: the equipment list below needs re-verification per the wiki - Equip Load buff values "
        "were significantly changed in a recent patch.\n\n"
        "Equip Load INCREASE sources: Winged Crystal Tear (x1.2, 180s), Stardust Elixir (x1.15, 50s), "
        "Vyke's Dragonbolt (x1.15, 80s), Arsenal talismans (x1.1/x1.125/x1.15), Fortune of the Sentinel "
        "(x1.1), Baldachin's Blessing (x1.1, but x0.9 Max HP), Binding Rune of Leonine Weight (x1.004 "
        "per rune, max x1.04 at 10 forges), Erdtree's Favor talismans (x1.03/x1.04/x1.05), 'Enduring' "
        "Enkindled AoW affix (x1.03), 'Sovereign' Enkindled AoW affix (x1.02).\n\n"
        "Equip Load DECREASE sources: Fortune of the Barbarian (x0.8), Fortune of the Bulwark (always "
        "at Massive Frame), Fortune of the Dynasts (x0.85).\n\n"
        "GRANULARITY: Equip Load now affects certain stats via a smooth curve based on Equip Load % (up "
        "to Massive Frame, no further penalty past 100%): Stamina Regen (+30 at 0% Equip Load, -30 at "
        "100%+), Stamina Cost of dodging and jumping, Non-Flask HP Restoration (x1.05 at 0%, x0.95 at "
        "100%+ - does NOT affect Flask of Crimson Tears but DOES affect Flask of Wondrous Physick since "
        "that's non-flask restoration), Movement Speed (x1.1 at 0%, x0.9 at 100%+, does not affect jump "
        "distance), Guard Boost (unverified exact multiplier range, lower at 0% Equip Load, higher at "
        "100%+)."
    ),
    'dodging': (
        "Rebalanced all roll tiers (i-frame values at 30 FPS): Nimble Roll - 13 i-frames, acts out 2 "
        "frames faster than Medium Roll, travels further, uses Bloodborne's light-load dodge animation "
        "with improved tracking. Balanced Roll - 12 i-frames, acts out 2 frames faster than Heavy Roll. "
        "Solid Roll - 11 i-frames, faster/further-reaching animation, screenshake removed. Massive Roll "
        "- unchanged (uses vanilla heavy roll).\n\n"
        "Dodge-like Skills (e.g. Quickstep): holding the Dash input now unlocks movement from any "
        "locked-on target, fixing a vanilla issue where the player stops and re-faces the target "
        "mid-Quickstep.\n\n"
        "Fixed various vanilla 'backjump'/'reverse roll' issues involving locking onto a target while "
        "performing an evasive action.\n\n"
        "Removed the unique 'crouch rolling' state - rolling while crouching now performs a regular "
        "roll and stands you up (the old stealth roll was rarely useful and caused awkward post-roll "
        "states)."
    ),
    'ducking_sliding': (
        "DUCKING: Replaced the backstep animation with a duck animation. Ducking has a small amount of "
        "i-frames and very low Stamina Cost, greatly lowers your hitbox (dodges high attacks even "
        "without i-frames), and cancels into an attack nearly instantly (cannot chain into itself or "
        "dodges). Nimble Duck: 8 i-frames, 10% faster than Medium Duck. Balanced Duck: 7 i-frames, 10% "
        "faster than Heavy Duck. Solid Duck: 6 i-frames. Massive Duck: unverified.\n\n"
        "SLIDING: New dodge option via Crouch/Stealth input while sprinting. Retains current Movement "
        "Speed, has a small number of i-frames like ducking, low-profiles attacks like ducking, small "
        "Stamina Cost, and retains more movement control than rolling (can circle around attacking "
        "enemies). Attacking during a slide immediately cancels into a crouch attack."
    ),
    'counterattack_damage_level': (
        "COUNTERATTACK: Counter Damage no longer only boosts Pierce Damage by 30% - now boosts Pierce "
        "by 15% and all other damage types by 10%. Enemies take 10% more Poise Damage during their "
        "counterattack windows. Counter damage window extended to cover the end of the attack animation "
        "(applies to both player and enemies).\n\n"
        "DAMAGE LEVEL (determines stagger/knockback/launch behavior on hit): increased damage level of "
        "Light Attack combo finishers, fully charged Heavy Attacks (especially the 2nd Heavy Attack), "
        "and some charged spell variants that didn't already increase it. Reworked enemy damage level "
        "resistances - large impact on mob/enemy stagger behavior. Some bosses (e.g. Bell Bearing "
        "Hunters) had resistances adjusted to allow brief staggers from powerful attacks; some powerful "
        "enemies may be harder to stagger with small weapons. Intent: more meaningful choices in how "
        "attacks stagger enemies."
    ),
    'blocking_deflection': (
        "BLOCKING: Adjusted block-recovery animation cancel timings for quicker post-block actions. "
        "Added a movement speed reduction while walking and blocking (applies to all weapons/shields "
        "except Torches). Raising guard now consumes a very small amount of Stamina, increasing if the "
        "guard button is pressed multiple times in quick succession. Status effect resistance while "
        "blocking is no longer a hidden value - it's now half of the associated damage type's Guarded "
        "Negation: Physical Guarded Negation -> Bleed/Poison/Scarlet Rot; Magic Guarded Negation -> "
        "Frostbite; Fire Guarded Negation -> Madness; Lightning Guarded Negation -> Sleep; Holy Guarded "
        "Negation -> Death Blight. Example: a 50% Physical Negation shield blocks 25% of bleed/poison/"
        "rot buildup. Affinities boost both elemental resistance and status resistance by 25% together "
        "- e.g. a Poison-infused shield gains 25% more Poison resistance without 25% more Physical "
        "Guarded Negation, and a Magic-infused shield gains 25% Magic Guarded Negation.\n\n"
        "DEFLECTION: Blocking within the first few frames of a weapon/shield's block animation performs "
        "a Deflect; stricter timing performs a Perfect Deflect. Deflects increase All Guarded Negation, "
        "reduce Status Buildup taken, and increase Guard Boost. Perfect Deflects entirely negate "
        "damage/status buildup, tremendously increase Guard Boost, and grant a brief attack buff; some "
        "enemy attacks recoil off a Perfect Deflect, opening an easy retaliation.\n\n"
        "HARDNESS: Removed Hardness variability (a hidden armament stat controlling which enemy attacks "
        "recoil when blocked) - all armaments now share the same Hardness, generally only recoiling "
        "weak attacks from minor enemies. Perfect Deflects greatly increase Hardness, recoiling almost "
        "all enemy combo finishers and many weak-enemy attacks entirely.\n\n"
        "GUARD COUNTERS: If the right-hand armament can't Guard Counter, performing the Guard Counter "
        "input now uses the left-hand armament if it's capable (e.g. catalyst right hand + weapon/"
        "shield left hand). Can be set to always prefer left-hand Guard Counters in the Reforged "
        "Controls menu.\n\n"
        "GUARDBREAK: Being guardbroken now deals 15-25% of Max HP as damage (cannot drop you below 1% "
        "HP, so it can't kill you). Stamina Regen is slowed while guardbroken. The guardbreak animation "
        "can now be almost instantly cancelled by rolling - if hit by another attack before cancelling, "
        "the extra damage penalty is not applied."
    ),
    'multi_weapon_combat': (
        "Extensive changes/improvements to multi-weapon combat (Powerstancing and non-Powerstancing), "
        "aimed at increasing moveset flexibility and viable weapon combinations. Many elements can be "
        "disabled in Control Settings if the increased input complexity is overwhelming.\n\n"
        "New Powerstancing-compatible weapon class pairs: Axes with Hammers and Flails; Greataxes with "
        "Greathammers; Colossal Weapons with Colossal Swords; Curved Greatswords with Greatswords.\n\n"
        "LEFT-HAND BLOCK: Pressing Guard with a weapon in the left hand now blocks instead of attacking "
        "- enables Deflects with left-handed weapons (major part of the multi-weapon overhaul). Applies "
        "both to Powerstancing/Paired Weapons and wielding different weapons in each hand.\n\n"
        "GUARD + LIGHT ATTACK unlocks new moves depending on wielded armaments: LH medium/great shield "
        "+ RH poking armament (Great Spears/Halberds/Heavy Thrusting Swords/Spears/Thrusting Swords) = "
        "RH thrust while guarding ('shield poke' - disabled for small shields due to low Guard Boost/"
        "defense). Powerstancing armaments (including paired weapons like Avionette Scimitars) = RH "
        "light attack. Non-Powerstancing armaments = LH light attack (also works for running/dash, roll "
        "and duck attacks). LH armament capable of critical attacks vs near-poise-broken/back-turned "
        "enemy = LH critical attack. LH or RH Weapon Catalyst = cast spell (if both hands hold "
        "catalysts, RH casts). LH Reduvia one-handed = Throwing Blade one-handed moveset (works while "
        "powerstancing too; running/dash/roll/duck inputs still perform normal attacks). LH Cleanrot "
        "Spear + RH Cleanrot Knight's Sword = unique guarding stance (spear stats used for guard, bonus "
        "x1.55 Guard Boost and x0.1 Physical Damage taken) plus a unique Guard Counter; the spear's "
        "Sacred Phalanx skill overrides any RH weapon skill. Note: left-handed Weapon Skills remain "
        "unavailable since most skills lack left-handed versions.\n\n"
        "GUARD + HEAVY ATTACK: LH armament + RH armament = LH heavy attack (also works for charged "
        "heavy, running/dash, roll, duck attacks, and while powerstancing). LH Reduvia one-handed = "
        "Reduvia heavy attack (unlike light attack, this does NOT throw the weapon - easy access to "
        "melee attacks)."
    ),
    'parrying': (
        "Increased parry hitbox size and moved it slightly forward, reducing whiffed parries with "
        "correct timing. Adjusted parry animation frames/timing: all FP-consuming parries have a 5 "
        "frame duration with source-dependent startup. Dagger: 4 frame duration, 4 frame startup. Small "
        "Shield: 4 frame duration, 5 frame startup. Buckler Parry: 4 frame duration, 4 frame startup. "
        "Curved Sword/Thrusting Sword: 3 frame duration, 4 frame startup. Medium Shield: 3 frame "
        "duration, 5 frame startup. Exact parry frames shown via the shield icon on the buff bar.\n\n"
        "Enemies requiring multiple parries to be stance-broken now take more riposte damage per parry "
        "required once stance-broken (only applies if stance-broken specifically by parries) - greatly "
        "increases parry effectiveness against multi-parry bosses."
    ),
    'perfect_actions': (
        "Perfect Actions ('Just Actions') grant a bonus to the next action when performed with precise "
        "timing after a prior action - does not stack or progress. Can be performed after almost all "
        "combat actions except blocking/deflecting: Light/Heavy attacks, Dodging, Jump attacks, "
        "Horseback attacks, all spellcasting animations, Weapon Skills (including multi-input skills), "
        "Parrying, Using an item. Indicated by a faint flash on the weapon or player model, with a "
        "brighter flash + sound on success (toggleable in Settings).\n\n"
        "Benefits (Weapon Skills on melee weapons count as melee attacks; Catalyst Heavy Attacks count "
        "as Spells per the Spells page; Mystic Ashes count as spells): Perfect Attack (Melee) - x0.8 "
        "Stamina Cost, x1.08 Action Speed, x1.04 Attack Power. Perfect Attack (Magic) - x0.8 Stamina "
        "Cost, x1.08 Action Speed, x0.96 FP Cost. Perfect Attack (Ranged) - x0.8 Stamina Cost, x1.08 "
        "Action Speed, +30 Projectile Range. Perfect Dodge - x0.8 Stamina Cost, x1.08 Action Speed, +1 "
        "I-Frame. Perfect Item - x0.8 Stamina Cost, x1.08 Action Speed, x1.04 HP/FP restored (Flask "
        "only)."
    ),
    'plunging_attacks': (
        "Re-implemented plunging attacks (no boss-specific special attacks like Asylum/Taurus Demon, "
        "just a universal plunging attack). Attacking while falling beyond a certain distance greatly "
        "increases Attack Power and Poise Damage, indicated by a white flash and buff icon. Applies to "
        "both Light and Heavy airborne attacks, and can hit multiple enemies. The fall distance required "
        "is longer than in prior Souls games to compensate for jumping; landing before the enemy voids "
        "the bonus."
    ),
    'poise': (
        "Enemy Poise Damage lowered across the board - many more enemy attacks can now be poised "
        "through. Vanilla enemy Poise Damage values were round numbers (10, 50, 100, 150, 200...); "
        "Reforged uses 9, 19, 39, 59, 79, 99, 119, 139, 159, 179, 199, etc. - meaning you no longer need "
        "breakpoint+1 Poise, just breakpoint Poise exactly (e.g. vanilla needed 51 or 101 Poise; "
        "Reforged needs only 40 to beat a 39 Poise Damage attack).\n\n"
        "Player Poise recovery now begins 12 seconds after last being hit (was 30 seconds). Player Poise "
        "Damage values altered: now visible on a weapon's stat card, weapons have a wider Poise Damage "
        "range within their class (lets specific weapons stand out), most attacks/spells deal more "
        "Poise Damage than vanilla (especially high-commitment options and combo enders), with a small "
        "number of outliers slightly reduced."
    ),
    'stamina_consumption': (
        "Diversified weapon Stamina Cost to be more unique per weapon (small, mostly unnoticeable "
        "changes for individual weapon identity). Lower-reinforcement weapons (+0) consume 20% less "
        "Stamina than max-reinforcement weapons of the same type (also applies to catalysts) - reduces "
        "pressure to rush Endurance leveling early while keeping the final build's Endurance requirement "
        "the same."
    ),
    'stealth': (
        "Increased stealth attack damage bonus from 20% to 25%. Running/Rolling/Jumping now count as "
        "'important' sound sources - most enemies walk toward an important sound's origin (non-important "
        "sounds only make enemies look toward the source). Slightly adjusted radius of some player "
        "sound sources. Improved state management so short falls and some other actions automatically "
        "return you to sneaking (jumping and attacking still exit stealth). Removed the 'Crouch Roll' "
        "state - rolling while crouching now performs a normal roll and stands you up (the old stealth "
        "roll was rarely useful since the only reason to roll while sneaking is to dodge an attack "
        "anyway)."
    ),
}


def run():
    with engine.connect() as conn:
        for section, content in CHARACTER_CHANGES.items():
            conn.execute(text("DELETE FROM sl_err_character_changes WHERE section=:s"), {'s': section})
            conn.execute(text("""
                INSERT INTO sl_err_character_changes (section, content, created_at)
                VALUES (:s, :c, :ts)
            """), {'s': section, 'c': content, 'ts': NOW})
        print(f'{len(CHARACTER_CHANGES)} Character Changes sections seeded.')

        for section, content in COMBAT_CHANGES.items():
            conn.execute(text("DELETE FROM sl_err_combat_mechanics WHERE section=:s"), {'s': section})
            conn.execute(text("""
                INSERT INTO sl_err_combat_mechanics (section, content, created_at)
                VALUES (:s, :c, :ts)
            """), {'s': section, 'c': content, 'ts': NOW})
        print(f'{len(COMBAT_CHANGES)} Combat Changes sections seeded.')
        conn.commit()


if __name__ == '__main__':
    run()
