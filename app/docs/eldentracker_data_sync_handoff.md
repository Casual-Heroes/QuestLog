# EldenTracker server-data and calculation handoff

## One-link bootstrap

Give the app developer or coding agent this single URL:

```text
https://questlog.casual-heroes.com/api/soulslike/data/handoff/
```

It contains the complete integration contract. The directly downloadable reference
updater is available at:

```text
https://questlog.casual-heroes.com/api/soulslike/data/reference-client/
```

Both URLs are developer references. The production app must only auto-download the JSON
manifest, immutable datasets, and advertised JSON live resources.

## Decision

An account is **not** required to run EldenTracker or receive game-data updates.
The app has two independent server connections:

1. The public catalog connection downloads factual game data and regulation-derived
   calculation inputs. It sends no listener key and works before login.
2. The existing Profile/run connection uses `X-Listener-Key` for cloud builds, live
   runs, deaths, boss focus, and profile restore.

The app must ship with one known-good bundled snapshot. On launch it checks the public
manifest, downloads only changed JSON, validates it, and atomically replaces its cache.
If QuestLog is unavailable, the app uses its last verified cache, then the bundled
snapshot. It never downloads or executes Python, DLLs, scripts, or arbitrary code.

This removes the need to manually maintain two copies of boss, weapon, armor, class,
and ERR regulation data. Formula implementations remain versioned app code. A bumped
`calculation_contract_version` tells an old app to retain its old calculation data and
show an update-required notice instead of silently calculating with an incompatible
algorithm.

## Public API added to QuestLog

No authentication or CSRF token is required:

```http
GET /api/soulslike/data/manifest/
GET /api/soulslike/data/<dataset>/<sha256-revision>/
```

Current content-addressed datasets:

- `vanilla_calculations`: Vanilla classes, all 3,216 named weapon/affinity
  variants, armor, deterministic talisman and selected-Physick modifiers,
  AR curves, AEC rows, every reinforcement level, and exact HP/FP/Stamina/
  equip-load curves verified against the supplied `regulation.bin`. Conditional
  combat and move-specific buffs are intentionally descriptive-only.
- `err_calculations`: ERR v2.2.9.5 classes, weapons and every affinity variant,
  armor, regulation-named talismans, AR curves, AEC rows, reinforcement levels,
  HP/FP/Stamina lookup curves, ERR weight sources, and the deterministic
  Enkindling calculation contract (rarity tiers, non-stacking rule, stats,
  HP/FP/Stamina, equip load, poise, and typed sheet-AR bonuses), plus the
  deterministic ERR talisman calculation contract.
- `bosses_err`: canonical ERR boss registry plus supplemental encounters.
- `bosses_vanilla`: canonical vanilla boss registry.

The manifest also advertises existing public database-backed resources under
`live_resources`: Vanilla and ERR classes, weapons, armor, talismans, spells,
Spirit Ashes, and Crystal Tears, plus ERR affinities, fortunes, curios,
runeforging, Ash-of-War skills, and Enkindling. The app should refresh only the
resources it actually presents and no more than once every
`live_resource_poll_seconds` (currently six hours).

Relevant response guarantees:

- `account_required` is `false`.
- Every immutable dataset supplies `revision`, `sha256`, exact `bytes`, and `url`.
- A dataset URL is valid only for that exact SHA-256 revision.
- Manifest responses support `ETag` and `If-None-Match`.
- Dataset responses are `immutable` and also support `ETag`.
- JSON is deterministic UTF-8, so the SHA-256 is reproducible.
- CORS is public for a future Twitch extension or other read-only clients.

Example shape:

```json
{
  "api_version": 1,
  "schema_version": 1,
  "calculation_contract_version": 1,
  "account_required": false,
  "poll_after_seconds": 21600,
  "datasets": {
    "vanilla_calculations": {
      "schema_version": 1,
      "regulation_sha256": "7b6d07c357b639c902d48403ffe3612db35e0cf8d6fcc82d3fb24ea6eb6cf30a",
      "revision": "<64-character dataset SHA-256>",
      "sha256": "<same dataset SHA-256>",
      "bytes": 123,
      "url": "https://questlog.casual-heroes.com/api/soulslike/data/vanilla_calculations/<SHA-256>/"
    },
    "err_calculations": {
      "schema_version": 1,
      "regulation_version": "2.2.9.5",
      "revision": "<64-character SHA-256>",
      "sha256": "<same SHA-256>",
      "bytes": 123,
      "url": "https://questlog.casual-heroes.com/api/soulslike/data/err_calculations/<SHA-256>/"
    }
  },
  "live_resource_poll_seconds": 21600,
  "live_resources": {
    "weapons_err": "https://questlog.casual-heroes.com/api/soulslike/weapons/?game=err&limit=1000"
  }
}
```

## App files and cache layout

Add the [reference updater](https://questlog.casual-heroes.com/api/soulslike/data/reference-client/)
to the current Windows app as `questlog/catalog_sync.py` (or its equivalent package path).

Use a local application-data directory, not OneDrive and not the source checkout:

```text
%LOCALAPPDATA%/QuestLog/EldenTracker/catalog/
  manifest.json
  state.json
  datasets/
    vanilla_calculations.json
    err_calculations.json
    bosses_err.json
    bosses_vanilla.json
  live/
    weapons_err.json
    talismans_err.json
    fortunes_err.json
    ...
```

Package the same layout under a read-only `resources/catalog/` directory in the app.
The first release containing this feature should bundle the current server snapshots.

## Exact startup order

Keep the current Profile API and automatic run restore. Insert catalog synchronization
after logging/overlay initialization and before constructing the boss matcher or build
calculator:

```python
from pathlib import Path
import os
import threading

from questlog.catalog_sync import CatalogStore


cache_root = Path(os.environ["LOCALAPPDATA"]) / "QuestLog" / "EldenTracker" / "catalog"
bundled_root = application_resource_path("resources/catalog")
catalog = CatalogStore(
    base_url="https://questlog.casual-heroes.com",
    cache_dir=cache_root,
    bundled_dir=bundled_root,
    app_version=APP_VERSION,
    logger=log,
)


def refresh_catalog_then_start_tracker():
    result = catalog.refresh()
    live = catalog.refresh_live_resources({
        "weapons_vanilla", "armor_vanilla", "talismans_vanilla",
        "spells_vanilla",
        "weapons_err", "armor_err", "talismans_err", "spells_err",
        "affinities_err", "fortunes_err", "curios_err",
        "runeforging_err", "aow_skills_err", "enkindling_err",
    })
    log.info(
        "Catalog sync — updated=%s unchanged=%s offline=%s",
        result.updated + live.updated,
        result.unchanged + live.unchanged,
        result.offline,
    )
    for warning in result.warnings + live.warnings:
        log.warning("Catalog sync — %s", warning)
    if result.app_update_required:
        ui.show_nonblocking_update_notice(
            "QuestLog calculation rules have changed. Update EldenTracker before "
            "using newly published calculation data."
        )

    vanilla_catalog = catalog.load("vanilla_calculations")["payload"]
    err_catalog = catalog.load("err_calculations")["payload"]
    err_bosses = catalog.load("bosses_err")["bosses"]
    vanilla_bosses = catalog.load("bosses_vanilla")["bosses"]
    ui_dispatch(
        lambda: tracker.install_catalogs(
            vanilla_catalog, err_catalog, err_bosses, vanilla_bosses
        )
    )


threading.Thread(
    target=refresh_catalog_then_start_tracker,
    name="questlog-catalog-sync",
    daemon=True,
).start()

# This stays independent and may run in parallel:
# Profile API status=200
# Auto-restoring session for 'Ryven'
# Server runs — active=2 history=2
```

For ERR Enkindling calculations, use
`err_catalog["enkindling"]["affixes"]` even when the app is offline. The map is
keyed by affix name and cumulative tier number. For example, Smoldering tier 1
is:

```json
{
  "type": "hp_fp_stamina_mult",
  "hp": 1.02,
  "fp": 1.03,
  "stamina": 1.04
}
```

Common applies tier 1, Rare applies tiers 1-2, and Legendary applies tiers
1-3. Apply an identical passive affix tier only once across equipped weapons.
Elemental `damage_mult` effects apply only to the matching damage component of
the weapon carrying that Enkindled Ash of War; do not multiply the weapon's
entire AR. Keep move-specific, enemy-category, timed, and triggered effects
descriptive unless the app has the required combat context.

The `enkindling_err` live resource is still useful for display descriptions and
per-Ash-of-War eligibility. It may refresh online and remain cached offline, but
calculation correctness does not depend on that live resource being present on
a fresh offline install.

ERR talisman rows in `err_catalog["talismans"]` include a `modifiers` object.
Treat the saved base attribute as the rune-level allocation, but display the
attribute after `statFlat` modifiers to match the in-game status screen. For
example, a saved Endurance value of 32 with the base Viridian Amber Medallion
displays 35, uses 35 for stamina/requirements/scaling, and then multiplies the
resulting maximum stamina by `1.01`. Other resource multipliers and Smoldering
compound after the effective attribute lookup. Do not add the displayed bonus
to the saved rune-level allocation.

Always clamp a loaded saved allocation to the selected class's starting value,
but never infer unrecorded allocated points from total rune level. The current
ERR Prisoner starts at Mind `13`; if the character has invested to base Mind
`15`, the app must save `15`. Spellsword `+6` and rare Mundane `+2` then make
the same field display Mind `23`.

Do not block the GUI thread on network I/O. Do not let a failed catalog request stop the
overlay or local tracking. However, construct/reload boss matching and builder lookup
objects only after `catalog.load(...)` has selected cache or bundled fallback.

The app must rebuild derived in-memory indexes when a revision changes; do not keep an
old module-level boss dictionary or weapon dictionary alive after installing new data.

## Synchronization and safety rules

The reference updater implements these rules:

1. Send a five-second-timeout `GET` for the manifest on launch with the cached ETag.
2. A `304` means use the cached manifest and datasets.
3. Reject an unsupported API/schema version.
4. Reject a dataset if its URL is not on the configured QuestLog API origin.
5. Reject downloads larger than 32 MiB.
6. Verify exact byte count and SHA-256 before parsing or installing.
7. Verify the inner `dataset` name and `schema_version`.
8. Write to a temporary file, flush it, and use `os.replace`; a crash cannot leave a
   half-written active catalog.
9. Preserve the last valid cache on HTTP, timeout, JSON, schema, length, or hash failure.
10. Never retry indefinitely during startup.
11. Refresh DB-backed live resources at most once per six hours, canonicalize their JSON,
    compare a local SHA-256, and replace only changed files.
12. If the calculation contract is newer than the app, skip both calculation
    datasets, retain the compatible cached/bundled versions, and prompt for an
    app update.

## Saved level rules

`level` stored in the build is authoritative. It represents the player's current rune
level and may be greater than the minimum implied by allocated base stats because the
player can have unallocated levels.

```python
STAT_KEYS = (
    "vigor", "mind", "endurance", "strength",
    "dexterity", "intelligence", "faith", "arcane",
)


def displayed_level(character_class, base_stats, stored_level, game="err"):
    cap = 200 if game == "err" else 713
    minimum = character_class["level"] + sum(
        max(0, int(base_stats[key]) - int(character_class[key]))
        for key in STAT_KEYS
    )
    minimum = min(cap, minimum)
    if stored_level is None:
        return minimum, minimum
    return min(cap, max(minimum, int(stored_level))), minimum
```

Load and display the saved `level`/`level_override` on every build load. Keep it locked by
default. Raise it automatically only if edited base stats require a higher minimum. Do not
replace a valid level such as 105 with the calculated minimum such as 97.

## ERR level-up cost

ERR and vanilla use different progression. For ERR v2.2.9.5:

```python
import math


def err_runes_to_next_level(current_level: int) -> int:
    if current_level >= 200:
        return 0
    adjusted = current_level + 81
    growth = max(0.0, (adjusted - 91) * 0.015)
    return max(0, math.floor((growth + 0.34) * adjusted * adjusted - 1886))
```

The contract intentionally returns **59,175 at current level 105**, matching the ERR
regulation. Do not use the vanilla formula or the spreadsheet's transposed 59,715 entry.

## Effective stats and derived HP/FP/Stamina

Base build stats determine rune level. Permanent bonuses do not count as spent levels.
For ERR, calculate effective stats independently and cap each at 99:

```text
effective stat = min(99,
  saved base stat
  + Binding Rune flat bonus
  + Fortune flat bonus
  + Enkindling flat bonus
  + talisman flat bonus)
```

Read exact base derived values from the downloaded regulation payload:

```python
def curve_value(err_data, curve_name, stat):
    index = max(0, min(149, int(stat)))
    return err_data["derived_curves"][curve_name][index]

base_hp = curve_value(err_data, "vigor_hp", effective_vigor)
base_fp = curve_value(err_data, "mind_fp", effective_mind)
base_stamina = curve_value(err_data, "endurance_stamina", effective_endurance)
```

Apply permanent multiplicative effects in this order and floor the final value:

```text
HP      = floor(base HP      × Fortune × Minor Fortune × Binding Runes × talismans × Enkindling)
FP      = floor(base FP      × Fortune × Binding Runes × talismans × Enkindling)
Stamina = floor(base Stamina × Fortune × Minor Fortune × Binding Runes × talismans × Enkindling)
```

Read main and Minor Fortune values from
`err_data["fortune_calculation_contract"]`. A selected Minor Fortune applies
the current deterministic `×1.01` HP and Stamina effect; it does not multiply
FP.

Binding Rune resource effects do not exponentiate the first-copy value. Read
the exact total-copy tier from
`err_data["binding_rune_calculation_contract"]["runes"][name]["multipliers_by_copies"]`.
For example, two Leonine Stamina copies select `1.0160000324249268`.

The app must read permanent talisman modifiers from
`err_data["talismans"][name]["modifiers"]`; do not maintain a second hardcoded
copy. Conditional effects such as "after a critical hit" or "at full HP" are
not permanent character-sheet stats.

The Viridian Amber ranks are a regression test:

- base: `+3 Endurance`, `×1.01 Max Stamina`
- +1: `+2 Endurance`, `×1.06 Max Stamina`
- +2: no flat Endurance, `×1.12 Max Stamina`
- +3: no flat Endurance, `×1.13 Max Stamina`

## ERR attack rating

Use the downloaded `weapons`, `aec`, `curves`, and `reinforce` maps. Never substitute an
Excel optimizer formula for regulation AR.

1. Select `weapons[weapon_name][equipped_affinity]`; fall back to `Standard`, then the
   first available variant.
2. Clamp the selected upgrade to the variant's `max_upgrade`.
3. Read the exact reinforcement level from
   `reinforce[str(reinforce_type_id)]["levels"][upgrade]`.
4. Determine unmet STR/DEX/INT/FAI/ARC requirements.
5. For each damage type `0..4` (physical, magic, fire, lightning, holy):
   - `max_base = raw_base × reinforcement_attack_multiplier`
   - read applicable attributes from `aec[str(aec_id)][str(damage_type)]`
   - if any applicable requirement is unmet, `total_scaling = 0.5` for ERR
   - otherwise, for each applicable stat:
     - `upgraded_scaling = base_scaling × reinforcement_scaling_multiplier`
     - boolean AEC uses `upgraded_scaling`
     - numeric AEC uses `AEC × upgraded_scaling / base_scaling`
     - multiply by the correction value at the player's stat from the variant's
       `calc_correct_graph_ids` curve
   - `damage_total = max_base × (1 + summed_scaling_bonus)`
   - display base, scaling, and total using `floor(value + 1e-9)`
6. Sum raw damage totals and truncate once for total AR.
7. Apply permanent per-damage talisman multipliers, Scadutree multiplier, and this weapon
   slot's Enkindling damage multiplier last, then floor.
8. For casting tools, spell scaling for a relevant damage channel is
   `floor(100 × total_scaling + 1e-9)`.

Do not permanently apply conditional affinity text to AR unless it has a deterministic,
always-active structured effect in the contract.

## ERR weapon, armor, and equip weight

- Weapon variant weight comes from the selected downloaded affinity variant.
- A fixed-affinity unique weapon with no separate variant row and Gravitational affinity
  uses `floor(base_weight × 0.5 × 10) / 10`.
- Armor weight comes from the regulation `armor` map.
- ERR talisman weight is zero.
- Equipped weapon weight is the heaviest right-hand slot plus the heaviest left-hand slot,
  not the sum of all six weapon slots.

```text
equipped weight = armor total + max(RH1,RH2,RH3) + max(LH1,LH2,LH3)
```

ERR base equip load is 100 and Endurance does not change it:

```text
max equip load = round-to-1-decimal(
  100
  × Fortune equip-load multiplier
  × Binding Rune equip-load multiplier
  × talisman equip-load multipliers
  × Enkindling equip-load multiplier
  × selected Physick multiplier)
```

Fortune and Physick weight values come from `err_data["weight_sources"]`; current Winged
Crystal Tear is `1.10`. Frame thresholds use the unrounded ratio:

- `< 0.333`: Nimble Frame
- `< 0.666`: Balanced Frame
- `< 1.0`: Heavy Frame
- otherwise: Massive Frame
- Bulwark always displays Massive Frame.

## Enkindling, talismans, affinities, and collection items

Use the manifest's live resources for the descriptive/structured database records. The
app should not keep a second hand-maintained copy of these catalogs. Enkindling applies
only tiers up to the selection rarity (`common=1`, `rare=2`, `legendary=3`) and only
structured `static_effect` fields. Keep conditional prose informational.

Affinities must remain per weapon. Do not infer Gravitational for every weapon from another
equipped slot. Meteorite Staff shows Gravitational only when its own ERR record assigns it.

When creating a run from a linked build, include both main and minor Fortune selections in
the run's collectible items. The server now also merges both selections from the linked
build for browser and desktop run creation, but the app should send the complete build
payload so its local state stays 1:1.

## What still requires an app release

JSON content changes do not require an app release. The following do:

- a new schema version;
- a calculation formula/order change;
- a new UI behavior;
- a new API authentication or write contract;
- executable tracker/overlay changes.

For any incompatible calculation change, increment
`CALCULATION_CONTRACT_VERSION` on the server and ship app support before allowing the new
calculation dataset to replace the app's verified cache.

## Acceptance checks for the app

1. Start online with no listener key: public catalogs update and local tracking opens.
2. Start offline with a cache: the app opens and logs that cached data is in use.
3. Start offline on a clean install: the bundled snapshot is used.
4. Tamper with a downloaded byte: SHA-256 validation fails and the prior cache remains.
5. Return a higher schema/calculation contract: the app warns and retains compatible data.
6. Add a server boss, refresh, and verify the app recognizes it without a release.
7. Load saved ERR level 105 whose allocated minimum is 97: both app and site display 105.
8. Verify level 105 costs 59,175 runes.
9. Verify Ruins Greatsword uses its own Gravitational assignment and regulation weight.
10. Verify Viridian Amber Medallion affects Endurance and Max Stamina at each rank.
11. Select a minor Fortune, start a run, and verify it appears as collectible on app/site.
