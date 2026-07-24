from pathlib import Path

from django.test import SimpleTestCase


TEMPLATE = (
    Path(__file__).parent
    / "questlog_web/templates/questlog_web/soulslike_builder.html"
)


class SoulslikeBuilderAffinityUiTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = TEMPLATE.read_text(encoding="utf-8")

    def test_locked_err_affinity_uses_existing_affinity_row(self):
        self.assertIn("function renderWeaponAffinityRow(slot, weapon)", self.source)
        self.assertIn("weapon.equippedAffinity = fixedAffinities[0]", self.source)
        self.assertIn("nameEl.textContent = fixedAffinities.join(' / ')", self.source)

    def test_fixed_affinity_row_is_read_only(self):
        self.assertIn("row.onclick = null", self.source)
        self.assertIn(
            "row.title = 'Fixed Elden Ring Reforged affinity'", self.source
        )

    def test_saved_build_restore_prefers_fixed_affinity(self):
        self.assertIn(
            "const affinity = fixedAffinities[0] || d.weapons?.[slot + '_affinity']",
            self.source,
        )

    def test_weapon_picker_and_summary_show_multi_affinity_label(self):
        self.assertIn("${lockedBadge}${infusableBadge}${affinityBadge}", self.source)
        self.assertIn(
            "affinityLabel: fixedAffinities.join(' / ') || equippedAffinity",
            self.source,
        )

    def test_err_and_vanilla_use_separate_unmet_requirement_penalties(self):
        self.assertIn(
            "BUILD.game === 'err' ? 0.5 : 0.4",
            self.source,
        )

    def test_numeric_attack_element_corrections_use_reference_branch(self):
        self.assertIn("const attributeCorrect = scalingAttrs[statKey]", self.source)
        self.assertIn("attributeCorrect === true", self.source)
        self.assertIn(
            "(attributeCorrect * upgradedScaling) / baseScaling",
            self.source,
        )
        self.assertIn(
            "totalScaling = 1 - ineffectiveAttributePenalty",
            self.source,
        )

    def test_weapon_upgrade_level_uses_regulation_profile(self):
        self.assertIn('id="upgrade-{{ wslot }}"', self.source)
        self.assertIn("function setWeaponUpgradeLevel(slot, value)", self.source)
        self.assertIn("reinforce?.levels?.[upgradeLevel] || reinforce", self.source)
        self.assertIn("computeAR(variant, statsForAR, weapon.upgradeLevel)", self.source)

    def test_casting_tools_show_spell_scaling(self):
        self.assertIn("function getSpellScalingLabel(variant, result)", self.source)
        self.assertIn("variant.sorcery_tool", self.source)
        self.assertIn("variant.incantation_tool", self.source)

    def test_actual_level_override_is_separate_from_minimum_level(self):
        self.assertIn('id="level-override"', self.source)
        self.assertIn('readonly oninput="onLevelOverride(this.value)"', self.source)
        self.assertIn('id="level-override-toggle"', self.source)
        self.assertIn(">Override</button>", self.source)
        self.assertNotIn("onclick=\"clearLevelOverride()\"", self.source)
        self.assertIn("const minimumLevel = Math.min(levelCap", self.source)
        self.assertIn(
            "BUILD.level_override < minimumLevel",
            self.source,
        )
        self.assertIn("BUILD.level_override = minimumLevel", self.source)
        self.assertIn(
            "Number.isFinite(BUILD.level_override) ? BUILD.level_override : minimumLevel",
            self.source,
        )
        self.assertIn("parseInt(d.total_level ?? d.level, 10)", self.source)
        self.assertIn("BUILD.level_override = Number.isFinite(savedLevel)", self.source)

    def test_err_talismans_feed_stats_resources_and_ar(self):
        self.assertIn("const ERR_TALISMAN_MODIFIERS", self.source)
        self.assertIn("'Viridian Amber Medallion +3'", self.source)
        self.assertIn("'Viridian Amber Medallion +3': { stamina: 1.13 }", self.source)
        self.assertIn("function calcTalismanModifiers()", self.source)
        self.assertIn("(talismanMods.statFlat[k] || 0)", self.source)
        self.assertIn("talismanMods.stamina", self.source)
        self.assertIn("talismanMods.eqload", self.source)
        self.assertIn("const talismanAttack = calcTalismanModifiers().attack", self.source)

    def test_vanilla_talismans_use_regulation_modifiers(self):
        talisman_function = self.source.split(
            "function calcTalismanModifiers()", 1
        )[1].split("function calcFortuneStatBonuses()", 1)[0]
        self.assertIn("const supplied = equipped?.modifiers || {};", self.source)
        self.assertNotIn(
            "if (BUILD.game !== 'err') return result;",
            talisman_function,
        )
        self.assertIn("modifier.statFlat || {}", self.source)
        self.assertIn("modifier.attack || {}", self.source)

    def test_vanilla_sheet_skips_conditional_buffs(self):
        self.assertIn(
            "deterministic equipped effects",
            self.source,
        )
        self.assertIn(
            "modifier.attackPve || modifier.attack || {}",
            self.source,
        )
        self.assertIn(
            "modifier.attackPvp || modifier.attack || {}",
            self.source,
        )

    def test_vanilla_blue_dancer_uses_equipped_weight_without_toggle(self):
        self.assertIn(
            "function vanillaBlueDancerMultiplier(weight)",
            self.source,
        )
        self.assertIn(
            "[[0,1.15],[8,1.135],[16,1.09],[20,1.0375],[30,1.0]]",
            self.source,
        )
        self.assertIn(
            "modifier.physicalEquipScaling === 'vanilla_blue_dancer'",
            self.source,
        )
        self.assertIn(
            "talismanWeight += BUILD.slots[slot]?.weight || 0",
            self.source,
        )

    def test_selected_vanilla_tears_feed_simple_sheet_calculations(self):
        self.assertIn("function calcPhysickModifiers()", self.source)
        self.assertIn(
            "if (BUILD.game !== 'elden_ring') return result;",
            self.source,
        )
        self.assertIn(
            "(physickMods.statFlat[k] || 0)",
            self.source,
        )
        self.assertIn(
            "* physickMods.stamina",
            self.source,
        )
        self.assertIn(
            "* (physickAttack[damageType] || 1)",
            self.source,
        )

    def test_vanilla_derived_values_prefer_regulation_curves(self):
        self.assertIn("if (DERIVED_CURVES.vigor_hp)", self.source)
        self.assertIn("if (DERIVED_CURVES.mind_fp)", self.source)
        self.assertIn("if (DERIVED_CURVES.endurance_stamina)", self.source)
        self.assertIn(
            "if (DERIVED_CURVES.endurance_equip_load)", self.source
        )

    def test_talisman_slot_changes_refresh_all_calculations(self):
        self.assertIn("if (category === 'talisman')", self.source)
        self.assertIn("if (SLOT_CATEGORY[slot] === 'talisman')", self.source)
        self.assertIn("updateAllStatBars();", self.source)
        self.assertIn("updateAllWeaponARs();", self.source)

    def test_stat_input_matches_in_game_display_without_changing_allocated_level(self):
        self.assertNotIn('id="effective-{{ stat }}"', self.source)
        preview = self.source.split(
            "function onStatPreview(stat)", 1
        )[1].split("function onStatChange(stat)", 1)[0]
        commit = self.source.split(
            "function onStatChange(stat)", 1
        )[1].split("function updateAllStatBars()", 1)[0]
        render = self.source.split(
            "function updateStatBar(stat)", 1
        )[1].split("// Rune cost to level up", 1)[0]
        self.assertIn(
            "displayedVal - bonus",
            preview,
        )
        self.assertIn("displayedVal - bonus", commit)
        self.assertIn("input.value = val;", render)
        self.assertIn("Base: ${base} | Displayed: ${val}", render)
        self.assertNotIn("effective.textContent", render)

    def test_legacy_stats_below_class_minimum_are_normalized_on_load(self):
        loader = self.source.split(
            "function loadBuildData(d)", 1
        )[1].split("const weaponSlots", 1)[0]
        self.assertIn(
            "Math.max(classMinimum, Number(d.stats[k]) || classMinimum)",
            loader,
        )

    def test_binding_runes_select_regulation_copy_tier_without_compounding(self):
        calculator = self.source.split(
            "const RUNE_DERIVED_MULTS", 1
        )[1].split("function updateDerivedStats()", 1)[0]
        self.assertIn("byCopies:", calculator)
        self.assertIn("result[m.resource] *= m.byCopies[copies]", calculator)
        self.assertNotIn("Math.pow", calculator)
        self.assertIn("1.0160000324249268", calculator)

    def test_minor_fortune_applies_current_deterministic_resource_bonus(self):
        calculator = self.source.split(
            "function calcFortuneDerivedMults()", 1
        )[1].split("// Rune multiplicative effects", 1)[0]
        self.assertIn("BUILD.minor_fortune.minor_modifiers?.hp || 1.01", calculator)
        self.assertIn(
            "BUILD.minor_fortune.minor_modifiers?.stamina || 1.01",
            calculator,
        )
        self.assertIn("hp: (m.hp || 1) * minorHp", calculator)
        self.assertIn("stamina: (m.stamina || 1) * minorStamina", calculator)

    def test_empty_err_api_modifiers_do_not_suppress_talisman_fallback(self):
        calculator = self.source.split(
            "function calcTalismanModifiers()", 1
        )[1].split("function calcPhysickModifiers()", 1)[0]
        self.assertIn("const fallback = BUILD.game === 'err'", calculator)
        self.assertIn("const supplied = equipped?.modifiers || {};", calculator)
        self.assertIn("...(fallback.statFlat || {})", calculator)
        self.assertIn("...(supplied.statFlat || {})", calculator)
        self.assertIn(
            "'Viridian Amber Medallion':    { statFlat: { endurance: 3 }, stamina: 1.01 }",
            self.source,
        )

    def test_err_equipped_weight_uses_selected_regulation_affinity(self):
        self.assertIn("function effectiveWeaponWeight(slot)", self.source)
        self.assertIn(
            "const selected = variants.find(variant => variant.affinity === affinity)",
            self.source,
        )
        self.assertIn("if (selected?.weight != null)", self.source)
        self.assertIn(
            "['rh1','rh2','rh3'].map(effectiveWeaponWeight)",
            self.source,
        )
        self.assertIn(
            "['lh1','lh2','lh3'].map(effectiveWeaponWeight)",
            self.source,
        )

    def test_fixed_gravitational_affinity_has_weight_fallback(self):
        self.assertIn(
            "getFixedWeaponAffinities(weapon).includes('Gravitational')",
            self.source,
        )
        self.assertIn("baseWeight * 0.5", self.source)

    def test_err_armor_loader_requests_regulation_overlay(self):
        self.assertIn(
            "fetch('/api/soulslike/armor/?game=' + requestedGame",
            self.source,
        )

    def test_err_equip_load_sources_use_regulation_payload(self):
        self.assertIn("let ERR_WEIGHT_SOURCES = {};", self.source)
        self.assertIn("ERR_WEIGHT_SOURCES = d.weight_sources || {};", self.source)
        self.assertIn("equipped?.equip_load_mult", self.source)
        self.assertIn("function calcPhysickEquipLoadMult()", self.source)
        self.assertIn("'Winged Crystal Tear': 1.10", self.source)
        self.assertIn("'Sentinel':  1.04", self.source)
        self.assertIn("'Dynasts':   0.86", self.source)
        self.assertIn("'Bulwark':   0.001", self.source)
        self.assertIn(
            "overlaying ERR regulation",
            self.source,
        )

    def test_rune_cost_stops_at_each_games_level_cap(self):
        self.assertIn("const maxLevel = BUILD.game === 'err' ? 200 : 713", self.source)
        self.assertIn("if (level >= maxLevel) return 0", self.source)

    def test_err_rune_cost_uses_current_regulation_formula(self):
        self.assertIn("const adjustedLevel = level + 81", self.source)
        self.assertIn("(adjustedLevel - 91) * 0.015", self.source)
        self.assertIn("(growth + 0.34) * adjustedLevel * adjustedLevel - 1886", self.source)
        self.assertIn("yields 59,175 at current level 105", self.source)

    def test_async_derived_curve_load_refreshes_initial_values(self):
        self.assertIn("DERIVED_CURVES = d.curves || {};", self.source)
        self.assertIn(
            "// The request is asynchronous; refresh immediately", self.source
        )
        self.assertIn("updateDerivedStats();", self.source)

    def test_game_switch_ignores_stale_calculation_responses(self):
        self.assertIn("const requestedGame = BUILD.game;", self.source)
        self.assertIn("if (BUILD.game !== requestedGame) return;", self.source)

    def test_saved_build_waits_for_core_builder_data(self):
        self.assertIn(
            "AR_DATA_READY, CLASSES_READY, WEAPONS_READY,", self.source
        )
        self.assertIn(
            "SPELLS_READY, TALISMANS_READY, ARMOR_READY, ENKINDLING_READY,",
            self.source,
        )

    def test_enkindling_load_recalculates_every_sheet_consumer(self):
        loader = self.source.split(
            "function loadEnkindlingAffixes()", 1
        )[1].split("const _ENKINDLE_RARITY_TIER", 1)[0]
        self.assertIn("ENKINDLING_READY = fetch(", loader)
        self.assertIn("if (BUILD.game !== requestedGame) return;", loader)
        self.assertIn("updateAllStatBars();", loader)
        self.assertIn("updateDerivedStats();", loader)
        self.assertIn("updateAllWeaponARs();", loader)
        self.assertIn("updatePoise();", loader)
        self.assertIn("return ENKINDLING_READY;", loader)

    def test_smoldering_applies_all_three_resource_multipliers(self):
        modifiers = self.source.split(
            "function calcEnkindleModifiers()", 1
        )[1].split("function calcEnkindleSlotAttack(slot)", 1)[0]
        self.assertIn("case 'hp_fp_stamina_mult':", modifiers)
        self.assertIn("mods.hpMult *= e.hp", modifiers)
        self.assertIn("mods.fpMult *= e.fp", modifiers)
        self.assertIn("mods.staminaMult *= e.stamina", modifiers)
        self.assertIn("* enkindleMods.hpMult", self.source)
        self.assertIn("* enkindleMods.fpMult", self.source)
        self.assertIn("* enkindleMods.staminaMult", self.source)

    def test_enkindling_attack_bonus_is_typed_not_blanket_ar(self):
        attack = self.source.split(
            "function calcEnkindleSlotAttack(slot)", 1
        )[1].split("function loadCurios()", 1)[0]
        self.assertIn("physical: [0], magic: [1], fire: [2]", attack)
        self.assertIn("lightning: [3], holy: [4]", attack)
        self.assertIn("damageTypeIds[effect.damage_type] || []", attack)
        self.assertIn("const enkindleAttack = calcEnkindleSlotAttack(slot);", self.source)
        self.assertIn("* (enkindleAttack[damageType] || 1)", self.source)
        self.assertNotIn("* scaduMult * enkMult", self.source)

    def test_minor_fortune_is_linked_to_collection_runs(self):
        self.assertIn("item_type: 'minor_fortune'", self.source)
        self.assertIn("item_name: BUILD.minor_fortune.name", self.source)
        self.assertIn(
            "BUILD.id = Number.isFinite(parseInt(d.id, 10))", self.source
        )
        self.assertIn("build_id:     BUILD.id", self.source)
        self.assertIn("BUILD.id = null;", self.source)

    def test_editable_saved_build_stays_in_url_for_browser_refresh(self):
        self.assertIn("function setActiveBuildUrl(mode, shareToken", self.source)
        self.assertIn("url.searchParams.set(mode, shareToken)", self.source)
        self.assertIn("url.searchParams.set('game', game)", self.source)
        self.assertIn(
            "setActiveBuildUrl('load', d.share_token || shareToken, BUILD.game)",
            self.source,
        )
        self.assertNotIn(
            "window.history.replaceState({}, '', '/soulslike/builder/');",
            self.source,
        )

    def test_first_save_changes_blank_builder_to_reloadable_build_url(self):
        self.assertIn("BUILD.share_token = d.share_token || BUILD.share_token", self.source)
        self.assertIn(
            "setActiveBuildUrl('load', BUILD.share_token, BUILD.game)",
            self.source,
        )

    def test_intentional_reset_and_game_switch_clear_active_build_url(self):
        self.assertIn("function selectGame(gameKey, label, preserveBuildUrl = false)", self.source)
        self.assertIn("if (!preserveBuildUrl) setActiveBuildUrl(null, null)", self.source)
        self.assertIn("resetBuildSilent();\n  setActiveBuildUrl(null, null);", self.source)

    def test_enkindling_save_includes_builtin_weapon_skill(self):
        self.assertIn(
            "BUILD.aow.rh1?.name || BUILD.slots.rh1?.default_skill || null",
            self.source,
        )
        self.assertIn(
            "d.weapons?.[slot + '_aow'] || BUILD.slots[slot]?.default_skill",
            self.source,
        )

    def test_enkindling_eligibility_requests_are_deduplicated(self):
        self.assertIn("const _enkindleEligibleRequests = {};", self.source)
        self.assertIn("if (!_enkindleEligibleRequests[aowName])", self.source)
        self.assertIn(".then(populate)", self.source)

    def test_build_save_syncs_every_collection_item_to_linked_runs(self):
        self.assertIn("collection_items:   buildCollectionItems()", self.source)
        self.assertIn("item_type: 'crystal_tear'", self.source)
        self.assertIn("item_type: 'binding_rune'", self.source)
        self.assertIn("d.item_sync?.runs", self.source)
