"""
Seed: ERR Armor - additions/location changes, individual piece passives, and armor set
passives (per-piece, stacks per set member worn).
Source: err.fandom.com/wiki/Armor, pasted directly by user. Updated to 1.4.9K values.

ERR reuses vanilla ER's armor catalog (no full re-seed of sl_armor needed per item stats -
confirmed earlier this session) - this only adds the NEW passive effect layer and the
handful of relocated/restored pieces, which is genuinely new ERR-specific data.

Run: chwebsiteprj/bin/python3 seed_soulslike_err_armor.py
"""
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

# (armor_name, change_text) - new pieces and location/acquisition changes
ARMOR_CHANGES = [
    ('Beryl Hood',
     "Found on a corpse in Dragonbarrow, directly south of the Bestial Sanctum and directly west "
     "of Farum Greatbridge Site of Grace."),
    ('Brave Armor Set',
     "Restored cut content. Found behind the statue of Godfrey at the end of the Gilded Cave of "
     "Knowledge tutorial area. Brave's Cord Circlet is obtainable as an altered version of the "
     "helm."),
    ('Chelonian Mitre',
     "Awarded by Miriel upon giving him every single scroll and prayerbook in the game."),
    ('Deathbed Smalls',
     "Restored cut content, obtainable along with Deathbed Dress."),
    ('Gravekeeper Cloak',
     "Dropped by the Grave Warden Duelist boss in Auriza Side Tomb (Capital Outskirts). No longer "
     "randomly drops from Duelists."),
    ('Kaiden', "A new altered version of the chestpiece is available."),
    ("Millicent's Set",
     "Restored cut content, obtainable at the end of her quest (whether helped or killed). "
     "Valkyrie's Prosthesis is obtainable as an altered version of the gloves."),
    ('Operatic Headdress',
     "Drops from Crowned Operatic Bats. Headpiece which slightly strengthens the attack power of "
     "elemental stones, rancorous hexes, and noxious mists. Contributed by WrenRecon."),
    ('Pilfered Mitre', "Dropped by Miriel when killed."),
    ('Ragged Set',
     "Restored cut content, obtainable as a purchase at the Altar of Anticipation."),
    ('Tree Sentinel',
     "Now dropped by the new Grave Sentinel Wyngrant boss in Sainted Hero's Grave (Altus)."),
]

# (armor_name, passive_effect)
INDIVIDUAL_PIECES = [
    ('Albinauric Mask',
     "+4 Arcane. x0.9 HP restoration of Flasks of Crimson Tears."),
    ('Ash-of-War Scarab',
     "x0.85 FP Cost of skills. x1.15 Damage taken."),
    ("Azur's Glintstone Crown",
     "x1.04 Attack Power of Azur's sorceries. x1.05 FP Cost of sorceries. Comet Azur creates a "
     "well of magic for 5 seconds when cast; while standing inside: x0.7 Stamina Cost of "
     "attacks."),
    ('Beryl Hood',
     "+1 Endurance. When enraging a Spirit Ash: x0.88 Stamina Cost of attacks for 15 seconds."),
    ('Black Dumpling',
     "When Madness is triggered in the vicinity: x1.1 Movement Speed for 20 seconds."),
    ("Blackguard's Iron Mask",
     "+10% Attack Power and +60% Poise Damage of unarmed strikes."),
    ('Cerulean Tear Scarab',
     "x1.1 FP restoration of Flasks of Cerulean Tears. x1.1 Damage taken."),
    ('Chelonian Mitre', "+1 Intelligence and Faith."),
    ('Circlet of Light',
     "+1 Intelligence, Faith and Arcane. x1.04 Attack Power of Miquellan incantations."),
    ('Crimson Hood',
     "+1 Vigor. When enraging a Spirit Ash: x1.2 HP restoration from non-flask sources for 15 "
     "seconds."),
    ('Crimson Tear Scarab',
     "x1.1 HP restoration of Flasks of Crimson Tears. x1.1 Damage taken."),
    ('Curseblade Mask',
     "+4 Dexterity. -30 Concentration. x0.9 HP restoration of Flasks of Crimson Tears."),
    ('Deathbed Dress',
     "0.2%+4 HP restoration every 2 seconds for nearby allies."),
    ('Death Mask Helm',
     "x0.95 FP Cost of summoning and enraging Spirit Ashes."),
    ("Diallos's Mask", "x0.86 Damage taken from Blood Loss."),
    ('Divine Beast Head',
     "+2 Dexterity and Strength. x1.04 Attack Power of Storm attacks. -60 Concentration. x0.9 "
     "HP restoration of Flasks of Crimson Tears."),
    ('Divine Beast Helm',
     "+2 Dexterity and Strength. x1.04 Attack Power of Storm attacks. -45 Concentration. x0.9 "
     "HP restoration of Flasks of Crimson Tears."),
    ('Divine Bird Helm',
     "+2 Dexterity and Strength. x1.04 Attack Power of Divine Bird Feathers. -45 Concentration. "
     "x0.9 HP restoration of Flasks of Crimson Tears."),
    ('Envoy Crown', "x1.06 Attack Power of Envoy Horn skills."),
    ('Glintstone Scarab', "x0.9 FP Cost of sorceries. x1.15 Damage taken."),
    ('Greathood', "+1 Intelligence and Faith. x0.95 Max HP."),
    ('Haima Glintstone Crown',
     "+1 Intelligence and Strength. x0.95 Max HP. Gavel of Haima and Cannon of Haima gain "
     "increased explosion radius."),
    ('Hierodas Glintstone Crown',
     "+1 Intelligence and Endurance. x0.95 Max HP. Ambush Shard gains improved targeting."),
    ('Horned Warrior Helm',
     "+4 Strength. -30 Concentration. x0.9 HP restoration of Flasks of Crimson Tears."),
    ('Imp Head (Bigmouth)', "+2 Mind."),
    ('Imp Head (Cat)', "+2 Endurance."),
    ('Imp Head (Corpse)', "+2 Dexterity."),
    ('Imp Head (Elder)', "+2 Faith."),
    ('Imp Head (Fanged)', "+2 Intelligence."),
    ('Imp Head (Long-Tongued)', "+2 Arcane."),
    ('Imp Head (Wolf)', "+2 Strength."),
    ('Incantation Scarab', "x0.9 FP Cost of incantations. x1.15 Damage taken."),
    ('Jar', "x1.06 Attack Power of throwing pots (x1.15 in vanilla)."),
    ('Karolos Glintstone Crown',
     "+2 Intelligence. x0.95 Max HP. Glintstone Pebble generates an additional 0.06% Max FP+6 "
     "on hit."),
    ('Greatjar',
     "x1.06 Attack Power of hefty throwing pots (x1.17 in vanilla). Does not boost pots or "
     "ritual pot."),
    ('Lazuli Glintstone Crown',
     "+1 Intelligence and Dexterity. x0.95 Max HP. Increased Cast Speed when casting Carian "
     "Slicer, Carian Greatsword, or Carian Piercer."),
    ("Lord of Blood's Robe",
     "When Blood Loss occurs in the vicinity: x1.035 Attack Power for 30 seconds."),
    ("Lusat's Glintstone Crown",
     "x1.04 Attack Power of Lusat's sorceries. x1.05 FP Cost of sorceries. Stars of Ruin "
     "projectiles create a small explosion on impact, staggering weak enemies."),
    ('Mushroom Crown', "x1.0125 Scarlet Rot buildup on enemies."),
    ('Navy Hood',
     "+1 Mind. When enraging a Spirit Ash: x0.9 FP Cost of skills, spells, and items for 15 "
     "seconds."),
    ('Okina Mask', "+2 Dexterity. -100 Concentration."),
    ('Olivinus Glintstone Crown',
     "+2 Intelligence. x0.95 Max HP. Glintstone Stars gains increased projectile lifespan."),
    ('Pilfered Mitre', "+1 Intelligence and Faith."),
    ('Silver Tear Mask',
     "+6 Arcane (+8 in vanilla). x0.95 Physical Attack Power."),
    ("St. Trina's Blossom", "x1.05 Max FP."),
    ('Twinsage Glintstone Crown',
     "+2 Intelligence. x0.95 Max HP. Crystal Burst gains an additional projectile. Shard "
     "Spiral gains increased tracking."),
    ('White Mask',
     "x1.04 Damage when Blood Loss occurs in the vicinity, for 20 seconds."),
    ('Winged Serpent Helm', "x1.04 Attack Power of Fire Knight skills."),
    ("Witch's Glintstone Crown",
     "+1 Intelligence and Arcane. x0.95 Max HP. Founding Rain of Stars gains increased radius "
     "and duration."),
]

# (set_name, passive_effect)
ARMOR_SETS = [
    ('Alberich', "x1.02 Attack Power of Aberrant sorceries."),
    ('All-Knowing', "0.05%+2 FP restoration every 2 seconds while in combat."),
    ('Ansbach', "x1.025 Attack Power of Blood Oath and dynastic skills."),
    ('Aristocrat', "+20 Item Discovery."),
    ('Astrologer', "Increases Attack Power of Sorcery Catalyst Heavy Attacks (exact value unverified)."),
    ('Azur', "x1.02 Attack Power of Azur sorceries."),
    ('Banished Knight', "x1.025 Attack Power of storm attacks."),
    ('Battlemage', "x1.015 FP restoration from attacking and spell casts."),
    ('Beast Champion', "x0.98 FP Cost of skills."),
    ('Blackflame Monk', "x1.02 Attack Power of Godslayer incantations."),
    ('Black Knife', "x1.025 Attack Power while invisible."),
    ('Black Knight',
     "x1.025 Holy Attack Power and x0.975 Stamina Cost of jump attacks and guard counters."),
    ("Blaidd's", "x0.7 Damage taken from Frostbite."),
    ('Bloodhound Knight',
     "x1.015 Action Speed for 8 seconds when Blood Loss occurs in the vicinity."),
    ('Blue Silver', "x1.02 Attack Power of projectiles while wielding a bow."),
    ('Brave', "x1.03 Attack Power of roar attacks."),
    ('Bull-Goat', "x1.1 Physical Defense."),
    ('Carian Knight', "x1.02 Attack Power of Carian sorceries."),
    ('Chainmail', "Increases Movement Distance of attacks (exact value unverified)."),
    ('Champion', "Increases Max HP (exact value unverified)."),
    ('Cleanrot', "0.1%+4 HP Restoration every 2 seconds while afflicted by Scarlet Rot."),
    ('Confessor', "Reduces Enemy Vision and Enemy Hearing (exact values unverified)."),
    ('Crucible', "x1.02 Attack Power of Aspects of the Crucible incantations and skills."),
    ('Cuckoo Knight / Raya Lucarian Soldier / Raya Lucarian Foot Soldier',
     "x1.02 Magic Attack Power while attacking with a melee weapon."),
    ('Dancer', "x1.025 Attack Power of dancing attacks."),
    ('Death Knight', "x1.0125 Death Blight buildup on enemies."),
    ('Depraved Perfumer', "x1.02 Attack Power of perfume items."),
    ('Drake Knight', "x1.02 Attack Power of Dragon Communion incantations."),
    ('Dryleaf', "x1.02 Action Speed of Dryleaf skills."),
    ('Duelist', "+0.04 Target Priority."),
    ('Eccentric',
     "Reduces Damage taken while surrounded by enemies: x0.99 at 2 enemies, x0.92 at 9 "
     "enemies (exact scaling unverified)."),
    ("Elden Lord's",
     "x1.02 Physical Attack Power and +0.005 Target Priority while under the effect of a war "
     "cry."),
    ('Exile', "x1.025 Attack Power of storm attacks."),
    ("Fia's", "x1.02 Attack Power of Death sorceries."),
    ('Fingerprint', "x1.0125 Madness buildup on enemies."),
    ('Fire Monk', "x1.02 Attack Power of Giants' Flame incantations."),
    ('Fire Prelate',
     "x0.97 Damage taken for 6 seconds after casting Giants' Flame incantations."),
    ('Fur Set', "0.6%+6 FP after killing an enemy."),
    ('Gaius', "x1.025 Attack Power of spells while on horseback."),
    ('Gelmir Knight', "0.4%+8 HP restoration after killing an enemy."),
    ('Godrick Knight / Godrick Soldier / Godrick Foot Soldier',
     "x1.01 Poise Damage while attacking with a melee weapon."),
    ('Godskin Apostle',
     "x0.94 Stamina Cost of all actions while in the presence of Black Flame."),
    ('Godskin Noble', "x0.97 Damage taken while in the presence of Black Flame."),
    ("Goldmask's", "x1.02 Attack Power of Golden Order incantations."),
    ('Gravebird', "x1.02 Attack Power of Ghostflame sorceries."),
    ('Guardian Set', "x1.02 Attack Power of Erdtree incantations."),
    ('Guide',
     "Increases Non-Flask HP Restoration for self and nearby allies (exact value unverified)."),
    ('Haligtree Knight / Haligtree Soldier / Haligtree Foot Soldier',
     "x1.02 Holy Attack Power while attacking with a melee weapon."),
    ('Iron Rivet', "x1.03 Attack Power of 'Bear Communion' incantations."),
    ('Page / High Page', "x1.02 Attack Power of projectiles while wielding a crossbow."),
    ('High Priest', "x1.02 Attack Power of Finger sorceries."),
    ('Hoslow', "x0.9 Damage taken from Blood Loss."),
    ("Igon's Set", "x1.02 Attack Power of projectiles while wielding a greatbow."),
    ('Juvenile Scholar',
     "1.2%+6 FP every 2 seconds while under the effects of Sleep (includes the Drowsy debuff)."),
    ('Kaiden', "x1.015 Max Stamina."),
    ('Leyndell Knight / Leyndell Soldier / Leyndell Foot Soldier',
     "x1.02 Lightning Attack Power while attacking with a melee weapon."),
    ("Lionel's",
     "x0.9875 Counter Damage taken (x0.9825 for Pierce)."),
    ('Lusat', "x1.02 Attack Power of Lusat sorceries."),
    ("Malenia's", "x1.04 HP restored by the effect of Malenia's Great Rune."),
    ('Malformed Dragon', "x1.02 Attack Power versus Dragon-type enemies."),
    ("Maliketh's", "x1.02 Attack Power versus Divine-type enemies."),
    ('Marais', "2.5%+50 HP restoration when Scarlet Rot occurs in the vicinity."),
    ('Marionette', "x1.08 Action Speed for 1 second after taking damage."),
    ('Mausoleum Knight / Mausoleum Soldier / Mausoleum Foot Soldier',
     "x0.976 Status Buildup received."),
    ('Messmer / Fire Knight',
     "x1.02 Attack Power of Messmerflame incantations and Fire Knight skills."),
    ('Messmer Soldier', "x1.025 Attack Power of heavy attacks."),
    ('Mushroom', "x1.0125 Scarlet Rot buildup on enemies."),
    ("Night's Cavalry", "x1.03 Attack Power of melee attacks while on horseback."),
    ('Night Set', "x0.97 Stamina Cost of attacks and dodges."),
    ("Nomadic Merchant's", "x0.75 Damage taken from Madness."),
    ('Oathseeker', "x1.025 Attack Power of dashing, rolling, and duck attacks."),
    ('Omenkiller', "x1.135 Poise for 16 seconds after using a perfume item."),
    ('Omen', "x1.03 Attack Power of Omen Bairns and Shriek of Milos."),
    ('Perfumer', "x0.97 Damage taken for 12 seconds after using a perfume item."),
    ("Perfumer Traveler's", "x0.97 FP Cost of perfume items."),
    ('Preceptor', "x1.1 Elemental Defense."),
    ('Prisoner',
     "Reduces FP Cost and Stamina Cost of spells, and reduces Max HP (exact values "
     "unverified)."),
    ('Prophet', "Increases Attack Power of Incantation Catalyst Heavy Attacks (exact value unverified)."),
    ('Queen of the Full Moon', "x1.015 Attack Power of Full Moon sorceries."),
    ("Radahn's", "x1.015 Attack Power of Gravity sorceries."),
    ('Raging Wolf', "x1.015 Physical Attack Power while attacking with a melee weapon."),
    ('Rakshasa', "x1.02 Attack Power. x1.04 Damage taken."),
    ('Raptor / Bandit', "x1.025 Attack Power of jump attacks."),
    ('Raya Lucaria Sorcerer Set / Lazuli Robe', "x1.0166 Max FP."),
    ('Redmane Knight / Redmane Soldier / Redmane Foot Soldier',
     "x1.02 Fire Attack Power while attacking with a melee weapon."),
    ('Reeds', "Increases Guard Boost when deflecting (exact value unverified)."),
    ('Rellana',
     "After casting a sorcery: x0.975 FP Cost of skills for 10 seconds. After using a skill: "
     "x0.985 FP Cost of spells for 10 seconds."),
    ('Ronin',
     "x0.91 Damage taken for 5 seconds after Madness is triggered in the vicinity."),
    ('Rotten Duelist',
     "Greaves and Helmet: +0.03 Target Priority. Chestpiece: +0.04 Target Priority."),
    ('Royal Knight', "+30 Cast Speed for 2 seconds after casting a spell."),
    ('Royal Remains', "0.2%+4 HP restoration every 2 seconds while under 50% Max HP."),
    ("Sage's", "x1.02 Attack Power of Servant of Rot incantations."),
    ('Sanguine Noble', "x1.0125 Blood Loss buildup on enemies."),
    ('Shadow Militia', "x1.0125 Poison buildup on enemies."),
    ('Snow Witch', "x1.02 Attack Power of Cold sorceries."),
    ('Spellblade', "x1.025 Magic Attack Power of skills."),
    ('Thiollier', "x1.0125 Sleep buildup on enemies."),
    ('Tree Sentinel', "x0.985 FP Cost of area healing and support incantations."),
    ('Twinned',
     "x1.02 Attack Power versus Undead enemies. Prevents skeletons from reviving when slain, "
     "regardless of weapon used."),
    ('Vagabond Knight',
     "Increases All Guarded Negation and status resistance of guarding (exact value "
     "unverified)."),
    ('Verdigris',
     "x0.975 Status Buildup received while blocking (only if blocking with the left hand, "
     "unverified)."),
    ("Veteran's", "x0.975 FP Cost of summoning and enraging spirits."),
    ('Vulgar Militia', "x1.02 Attack Power of Bestial incantations."),
    ('Warrior', "Increases Attack Power of guard counters (exact value unverified)."),
    ('Zamor', "x1.0125 Frostbite buildup on enemies."),
]


def run():
    with engine.connect() as conn:
        for name, change in ARMOR_CHANGES:
            conn.execute(text("DELETE FROM sl_err_armor_changes WHERE armor_name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_armor_changes (armor_name, change_text)
                VALUES (:name, :change)
            """), {'name': name, 'change': change})
        print(f'{len(ARMOR_CHANGES)} armor additions/changes seeded.')

        for name, effect in INDIVIDUAL_PIECES:
            conn.execute(text("DELETE FROM sl_err_armor_passives WHERE armor_name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_armor_passives (armor_name, passive_effect, is_set)
                VALUES (:name, :eff, 0)
            """), {'name': name, 'eff': effect})
        print(f'{len(INDIVIDUAL_PIECES)} individual armor piece passives seeded.')

        for name, effect in ARMOR_SETS:
            conn.execute(text("DELETE FROM sl_err_armor_passives WHERE armor_name=:name"), {'name': name})
            conn.execute(text("""
                INSERT INTO sl_err_armor_passives (armor_name, passive_effect, is_set)
                VALUES (:name, :eff, 1)
            """), {'name': name, 'eff': effect})
        print(f'{len(ARMOR_SETS)} armor set passives seeded (per-piece, stacks per set member worn).')

        conn.commit()
        total = conn.execute(text("SELECT COUNT(*) FROM sl_err_armor_passives")).scalar()
        print(f'\nTotal sl_err_armor_passives rows: {total}')


if __name__ == '__main__':
    run()
