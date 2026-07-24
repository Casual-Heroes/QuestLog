#!/usr/bin/env python3
"""Build the ERR builder's factual calculation data from an unpacked regulation.bin.

The reference calculator JSON supplies only the public weapon and affinity names
used by QuestLog. Every numeric weapon, class, and derived-stat value in the
output is read from the supplied ERR regulation XML files. This script never
connects to or modifies the database.
"""

import argparse
import json
import math
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


DAMAGE_FIELDS = {
    "0": "attackBasePhysics",
    "1": "attackBaseMagic",
    "2": "attackBaseFire",
    "3": "attackBaseThunder",
    "4": "attackBaseDark",
}
GRAPH_FIELDS = {
    "0": "correctType_Physics",
    "1": "correctType_Magic",
    "2": "correctType_Fire",
    "3": "correctType_Thunder",
    "4": "correctType_Dark",
}
REQUIREMENT_FIELDS = {
    "str": "properStrength",
    "dex": "properAgility",
    "int": "properMagic",
    "fai": "properFaith",
    "arc": "properLuck",
}
SCALING_FIELDS = {
    "str": "correctStrength",
    "dex": "correctAgility",
    "int": "correctMagic",
    "fai": "correctFaith",
    "arc": "correctLuck",
}
REINFORCE_ATTACK_FIELDS = {
    "0": "physicsAtkRate",
    "1": "magicAtkRate",
    "2": "fireAtkRate",
    "3": "thunderAtkRate",
    "4": "darkAtkRate",
}
REINFORCE_SCALING_FIELDS = {
    "str": "correctStrengthRate",
    "dex": "correctAgilityRate",
    "int": "correctMagicRate",
    "fai": "correctFaithRate",
    "arc": "correctLuckRate",
}
AFFINITY_NAMES = {
    -1: "Standard",
    0: "Standard",
    1: "Heavy",
    2: "Keen",
    3: "Quality",
    4: "Fire",
    5: "Fell",
    6: "Lightning",
    7: "Sacred",
    8: "Magic",
    9: "Cold",
    10: "Poison",
    11: "Blood",
    12: "Occult",
    13: "Bolt",
    14: "Soporific",
    15: "Frenzied",
    16: "Magma",
    17: "Rotten",
    18: "Cursed",
    19: "Night",
    20: "Gravitational",
    21: "Blessed",
    22: "Bestial",
    23: "Fated",
}

CLASS_NAMES = {
    3000: "Vagabond",
    3001: "Warrior",
    3002: "Hero",
    3003: "Bandit",
    3004: "Astrologer",
    3005: "Prophet",
    3006: "Confessor",
    3007: "Samurai",
    3008: "Prisoner",
    3009: "Wretch",
    3010: "Perfumer",
    3011: "Scout",
    3012: "Gladiator",
    3013: "Guide",
}

CLASS_STAT_FIELDS = {
    "vigor": "baseVit",
    "mind": "baseWil",
    "endurance": "baseEnd",
    "strength": "baseStr",
    "dexterity": "baseDex",
    "intelligence": "baseMag",
    "faith": "baseFai",
    "arcane": "baseLuc",
}

ARMOR_SLOTS = {0: "helm", 1: "chest", 2: "gauntlet", 3: "leg"}
PLACEHOLDER_ARMOR_NAMES = {"Head", "Body", "Arms", "Legs"}
FORTUNE_SPEFFECT_IDS = {
    "Barbarian": 9010000,
    "Sentinel": 9018000,
    "Dynasts": 9027000,
    "Bulwark": 9033000,
}

# ERR-added and renamed weapons do not have public names in Paramdex. Their IDs
# are stable EquipParamWeapon row IDs, verified against type, requirements,
# damage, scaling, AEC, reinforcement profile, and neighboring named rows.
WEAPON_ID_ALIASES = {
    "Ambassador's Cudgel": 11160000,
    "Ambassador's Greatsword": 4120000,
    "Ambassador's Towershield": 32310000,
    "Avionette Pig Sticker": 18120000,
    "Avionette Scimitars": 7160000,
    "Backhand Blades": 64500000,
    "Brass Dagger": 1150000,
    "Broken Straight Sword": 2120000,
    "Coilheart": 2280000,
    "Crude Iron Claws": 22040000,
    "Crystal Ringblade": 64530000,
    "Curseblade's Cirques": 64520000,
    "Dancing Blades of Ranah": 7520000,
    "Dark Glintstone Staff": 33210000,
    "Dawnglow Greatbolt": 10110000,
    "Disciple's Rotten Branch": 16100000,
    "Dragonscale Halberd": 18140000,
    "Fellthorn Clutches": 21140000,
    "Fellthorn Stake": 23090000,
    "Flamelost Greatblades": 4090000,
    "Flamelost War Spear": 16190000,
    "Flamelost War Sword": 2130000,
    "Fury of Azash": 8090000,
    "Gladius of Ophidion": 2270000,
    "Goldvine Branchstaff": 10100000,
    "Gracebound Cane Sword": 5070000,
    "Gracebound Claws": 22050000,
    "Gracebound Dagger": 1210000,
    "Gracebound Greataxe": 23160000,
    "Gracebound Greatshield": 32320000,
    "Gracebound Greatsword": 3240000,
    "Gracebound Halberd": 18180000,
    "Gracebound Katana": 9090000,
    "Gracebound Longbow": 41080000,
    "Gracebound Mace": 11180000,
    "Gracebound Round Shield": 30210000,
    "Gracebound Staff": 33330000,
    "Grave Spear": 16170000,
    "Greatswords of Radahn": 4530000,
    "Horned Warrior's Swords": 7530000,
    "Iron Spike": 1120000,
    "Lordsworn's Spear": 16180000,
    "Mad Sun Shield": 31200000,
    "Makar's Ceremonial Cleaver": 8110000,
    "Marionette Short Sword": 2100000,
    "Marionette Spiked Spear": 16140000,
    "Mohgwyn's Sacred Seal": 34100000,
    "Night's Edge": 1170000,
    "Nox Flowing Fists": 21050000,
    "Ornamental Straight Swords": 2060000,
    "Poison Perfume Bottle": 61540000,
    "Pumpkin Sledge": 12030000,
    "Putrescent Bonesmasher": 8120000,
    "Red Wolf's Fang": 7130000,
    "Rotten Crystal Ringblade": 64540000,
    "Rotten Duelist Greataxe": 23150000,
    "Scepter of Serenity": 12270000,
    "Smithscript Cirques": 64510000,
    "Snow Witch Scepter": 33300000,
    "Starcaller Spire": 18170000,
    "Starscourge Greatswords": 4050000,
    "Sun Realm Sword": 2030000,
    "Suncatcher": 9100000,
    "Twinbird Caduceus": 33310000,
    "Vulgar Militia Chain Sickle": 14070000,
}


def number(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return value
    return int(parsed) if parsed.is_integer() else parsed


def normalized(value):
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(
        character for character in value if not unicodedata.combining(character)
    ).casefold().replace("’", "'").strip()


def load_param(path):
    root = ET.parse(path).getroot()
    defaults = {
        field.attrib["name"]: number(field.attrib.get("defaultValue"))
        for field in root.find("fields")
    }
    rows = {}
    for element in root.find("rows"):
        values = defaults.copy()
        values.update({key: number(value) for key, value in element.attrib.items()})
        values["paramdexName"] = element.attrib.get("paramdexName", "")
        rows[int(element.attrib["id"])] = values
    return rows


def evaluate_curve(row):
    stages = [
        {
            "max": float(row[f"stageMaxVal{index}"]),
            "grow": float(row[f"stageMaxGrowVal{index}"]) / 100,
            "adjust": float(row[f"adjPt_maxGrowVal{index}"]),
        }
        for index in range(5)
    ]
    values = [0.0] * 150
    for index in range(1, len(stages)):
        previous = stages[index - 1]
        stage = stages[index]
        minimum = 1 if index == 1 else math.floor(previous["max"]) + 1
        maximum = 149 if index == len(stages) - 1 else math.floor(stage["max"])
        for attribute in range(minimum, maximum + 1):
            denominator = stage["max"] - previous["max"]
            ratio = 1 if denominator == 0 else (attribute - previous["max"]) / denominator
            ratio = max(0, min(1, ratio))
            if previous["adjust"] > 0:
                ratio **= previous["adjust"]
            elif previous["adjust"] < 0:
                ratio = 1 - (1 - ratio) ** -previous["adjust"]
            values[attribute] = previous["grow"] + (stage["grow"] - previous["grow"]) * ratio
    return values


def evaluate_derived_curve(row):
    """Evaluate a CalcCorrectGraph row whose growth values are final stats.

    Weapon correction graphs store percentages and therefore use
    ``evaluate_curve``'s /100 conversion. ERR's HP, FP, and stamina rows store
    the displayed values directly. The game truncates the interpolated result.
    """
    stages = [
        {
            "max": float(row[f"stageMaxVal{index}"]),
            "grow": float(row[f"stageMaxGrowVal{index}"]),
            "adjust": float(row[f"adjPt_maxGrowVal{index}"]),
        }
        for index in range(5)
    ]
    values = [0] * 150
    for index in range(1, len(stages)):
        previous = stages[index - 1]
        stage = stages[index]
        minimum = 1 if index == 1 else math.floor(previous["max"]) + 1
        maximum = 149 if index == len(stages) - 1 else math.floor(stage["max"])
        for attribute in range(minimum, maximum + 1):
            denominator = stage["max"] - previous["max"]
            ratio = 1 if denominator == 0 else (attribute - previous["max"]) / denominator
            ratio = max(0, min(1, ratio))
            if previous["adjust"] > 0:
                ratio **= previous["adjust"]
            elif previous["adjust"] < 0:
                ratio = 1 - (1 - ratio) ** -previous["adjust"]
            values[attribute] = math.floor(
                previous["grow"] + (stage["grow"] - previous["grow"]) * ratio
            )
    return values


def reinforce_row_base(profile_id):
    # ERR's EquipParamWeapon values point directly at the mod's appended
    # ReinforceParamWeapon row groups (for example, 12000..12025).
    return profile_id


def build_armor_export(armor_rows):
    return dict(sorted({
        row["paramdexName"]: {
            "regulation_id": row_id,
            "type": ARMOR_SLOTS[int(row["protectorCategory"])],
            "weight": row.get("weight", 0),
            # ERR stores displayed poise as a per-piece correction rate.
            "poise": round(float(row.get("toughnessCorrectRate", 0)) * 1000, 3),
        }
        for row_id, row in armor_rows.items()
        if row.get("paramdexName")
        and row["paramdexName"] not in PLACEHOLDER_ARMOR_NAMES
        and int(row.get("protectorCategory", 4)) in ARMOR_SLOTS
    }.items()))


def build_talisman_export(accessory_rows, sp_effect_rows):
    talismans = {}
    for row_id, row in accessory_rows.items():
        name = row.get("paramdexName")
        if not name:
            continue
        effect = sp_effect_rows.get(int(row.get("refId", -1)), {})
        talismans[name] = {
            "regulation_id": row_id,
            "weight": row.get("weight", 0),
            "equip_load_mult": effect.get("equipWeightChangeRate", 1),
        }
    return dict(sorted(talismans.items()))


def build_weight_source_export(sp_effect_rows):
    return {
        "fortunes": {
            name: sp_effect_rows[row_id].get("equipWeightChangeRate", 1)
            for name, row_id in FORTUNE_SPEFFECT_IDS.items()
        },
        "crystal_tears": {
            "Winged Crystal Tear": sp_effect_rows[511012].get(
                "equipWeightChangeRate", 1
            ),
        },
    }


def build_dataset(reference, regulation_dir, version):
    reference_data = json.loads(Path(reference).read_text(encoding="utf-8"))
    weapon_rows = load_param(regulation_dir / "EquipParamWeapon.param.xml")
    reinforce_rows = load_param(regulation_dir / "ReinforceParamWeapon.param.xml")
    curve_rows = load_param(regulation_dir / "CalcCorrectGraph.param.xml")
    aec_rows = load_param(regulation_dir / "AttackElementCorrectParam.param.xml")
    class_rows = load_param(regulation_dir / "CharaInitParam.param.xml")
    armor_rows = load_param(regulation_dir / "EquipParamProtector.param.xml")
    accessory_rows = load_param(regulation_dir / "EquipParamAccessory.param.xml")
    sp_effect_rows = load_param(regulation_dir / "SpEffectParam.param.xml")

    base_ids_by_name = defaultdict(list)
    for row_id, row in weapon_rows.items():
        if row_id % 10000 == 0 and row.get("paramdexName"):
            base_ids_by_name[normalized(row["paramdexName"])].append(row_id)

    weapons = defaultdict(dict)
    missing = set()
    used_reinforce = set()
    used_curves = {0}
    used_aec = set()

    for reference_weapon in reference_data["weapons"]:
        weapon_name = reference_weapon["weaponName"]
        if weapon_name == "Unarmed":
            continue
        candidates = base_ids_by_name.get(normalized(weapon_name), [])
        base_id = WEAPON_ID_ALIASES.get(weapon_name)
        if base_id is None and len(candidates) == 1:
            base_id = candidates[0]
        if base_id is None:
            missing.add(weapon_name)
            continue

        affinity_id = int(reference_weapon["affinityId"])
        row_id = base_id if affinity_id < 0 else base_id + affinity_id * 100
        row = weapon_rows.get(row_id)
        if row is None:
            missing.add(f"{weapon_name} (affinity {affinity_id})")
            continue

        affinity = AFFINITY_NAMES[affinity_id]
        graphs = {
            damage: int(row[field])
            for damage, field in GRAPH_FIELDS.items()
            if int(row.get(field, 0)) != 0
        }
        used_curves.update(graphs.values())
        used_reinforce.add(int(row["reinforceTypeId"]))
        used_aec.add(int(row["attackElementCorrectId"]))
        weapons[weapon_name][affinity] = {
            "requirements": {
                stat: row[field]
                for stat, field in REQUIREMENT_FIELDS.items()
                if row.get(field, 0)
            },
            "attack": {
                damage: row[field]
                for damage, field in DAMAGE_FIELDS.items()
                if row.get(field, 0)
            },
            "scaling": {
                stat: row[field] / 100
                for stat, field in SCALING_FIELDS.items()
                if row.get(field, 0)
            },
            "aec_id": int(row["attackElementCorrectId"]),
            "calc_correct_graph_ids": graphs,
            "reinforce_type_id": int(row["reinforceTypeId"]),
            "max_upgrade": 10 if int(row["reinforceTypeId"]) >= 19000 else 25,
            "weight": row.get("weight", 0),
            "sorcery_tool": bool(row.get("enableMagic") or row.get("enableSorcery")),
            "incantation_tool": bool(row.get("enableMiracle")),
        }

    if missing:
        raise RuntimeError("Unmapped ERR weapons: " + ", ".join(sorted(missing)))

    reinforce = {}
    for profile_id in sorted(used_reinforce):
        base = reinforce_row_base(profile_id)
        levels = []
        for upgrade in range(26):
            row = reinforce_rows.get(base + upgrade)
            if row is None:
                break
            levels.append({
                "attack": {
                    damage: row[field]
                    for damage, field in REINFORCE_ATTACK_FIELDS.items()
                },
                "scaling": {
                    stat: row[field]
                    for stat, field in REINFORCE_SCALING_FIELDS.items()
                },
            })
            if upgrade >= 10 and profile_id >= 19000:
                break
        if not levels:
            raise RuntimeError(
                f"No ReinforceParamWeapon rows for profile {profile_id} "
                f"(expected base row {base})"
            )
        reinforce[str(profile_id)] = {
            "levels": levels,
            "max_level": len(levels) - 1,
            "attack": levels[-1]["attack"],
            "scaling": levels[-1]["scaling"],
        }

    damage_names = {
        "0": "Physics", "1": "Magic", "2": "Fire", "3": "Thunder", "4": "Dark"
    }
    stat_names = {
        "str": "Strength", "dex": "Dexterity", "int": "Magic", "fai": "Faith", "arc": "Luck"
    }
    aec = {}
    for aec_id in sorted(used_aec):
        row = aec_rows[aec_id]
        damage_values = {}
        for damage, damage_name in damage_names.items():
            attributes = {}
            for stat, stat_name in stat_names.items():
                if not row.get(f"is{stat_name}Correct_by{damage_name}"):
                    continue
                overwrite = row.get(f"overwrite{stat_name}CorrectRate_by{damage_name}", -1)
                attributes[stat] = True if overwrite == -1 else overwrite / 100
            if attributes:
                damage_values[damage] = attributes
        aec[str(aec_id)] = damage_values

    curves = {
        str(curve_id): evaluate_curve(curve_rows[curve_id])
        for curve_id in sorted(used_curves)
    }
    classes = []
    for row_id, class_name in CLASS_NAMES.items():
        row = class_rows[row_id]
        classes.append({
            "regulation_id": row_id,
            "name": class_name,
            "level": int(row["soulLv"]),
            **{
                stat: int(row[field])
                for stat, field in CLASS_STAT_FIELDS.items()
            },
        })

    derived_curves = {
        "vigor_hp": evaluate_derived_curve(curve_rows[100]),
        "mind_fp": evaluate_derived_curve(curve_rows[101]),
        "endurance_stamina": evaluate_derived_curve(curve_rows[104]),
    }
    return {
        "game": "err",
        "regulation_version": version,
        "classes": classes,
        "derived_curves": derived_curves,
        "armor": build_armor_export(armor_rows),
        "talismans": build_talisman_export(accessory_rows, sp_effect_rows),
        "weight_sources": build_weight_source_export(sp_effect_rows),
        "weapons": dict(sorted((name, dict(variants)) for name, variants in weapons.items())),
        "curves": curves,
        "aec": aec,
        "reinforce": reinforce,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path)
    parser.add_argument(
        "--existing-dataset",
        type=Path,
        help="Refresh regulation-only sections of an existing generated dataset",
    )
    parser.add_argument("--regulation-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", default="2.2.9.5")
    args = parser.parse_args()
    if args.existing_dataset:
        dataset = json.loads(args.existing_dataset.read_text(encoding="utf-8"))
        armor_rows = load_param(args.regulation_dir / "EquipParamProtector.param.xml")
        accessory_rows = load_param(args.regulation_dir / "EquipParamAccessory.param.xml")
        sp_effect_rows = load_param(args.regulation_dir / "SpEffectParam.param.xml")
        dataset["armor"] = build_armor_export(armor_rows)
        dataset["talismans"] = build_talisman_export(
            accessory_rows, sp_effect_rows
        )
        dataset["weight_sources"] = build_weight_source_export(sp_effect_rows)
        dataset["regulation_version"] = args.version
    else:
        if not args.reference:
            parser.error("--reference is required unless --existing-dataset is used")
        dataset = build_dataset(args.reference, args.regulation_dir, args.version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {len(dataset['weapons'])} weapons, "
        f"{sum(len(value) for value in dataset['weapons'].values())} variants, "
        f"{len(dataset.get('armor', {}))} armor pieces, "
        f"{len(dataset.get('talismans', {}))} talismans to {args.output}"
    )


if __name__ == "__main__":
    main()
