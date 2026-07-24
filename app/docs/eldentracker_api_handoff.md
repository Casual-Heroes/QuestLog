# EldenTracker death, timer, and Fury integration handoff

This document describes the current QuestLog server contract and the client changes required
after the EldenTracker 1.0.2c repeated-hotkey issue. It preserves the existing boss-focus,
death-attribution, timer, session, and Tarnished Fury behavior.

## Desktop build API

Every desktop build request uses the API-key endpoint and headers:

```http
X-Listener-Key: ql_...
X-App-Version: 1.0.2c
Content-Type: application/json
```

List builds or save/update a build:

```http
GET  /api/soulslike/desktop/builds/?game=err
POST /api/soulslike/desktop/builds/?game=err
```

The collection `POST` handles both create and update; it upserts an owned build by
name. `save_build()` must not post to `/api/soulslike/builds/`, which is the browser
session endpoint and correctly requires a CSRF token. Do not use item `PATCH` for an
update because that method is not part of the desktop contract.

```python
response = requests.post(
    f"{base_url}/api/soulslike/desktop/builds/",
    params={"game": game},
    headers={
        "X-Listener-Key": api_key,
        "X-App-Version": app_version,
        "User-Agent": f"QuestLog-EldenTracker/{app_version}",
    },
    json=build_payload,
    timeout=30,
)
```

Fetch one owned build using either identifier returned by the list endpoint:

```http
GET /api/soulslike/desktop/builds/<numeric-id>/?game=err
GET /api/soulslike/desktop/builds/<share-token>/?game=err
```

Delete an owned build:

```http
POST /api/soulslike/desktop/builds/<numeric-id>/delete/?game=err
```

ERR Enkindling reference data uses:

```http
GET /api/soulslike/err/enkindling/
GET /api/soulslike/err/enkindling/eligible/?aow=<name>
```

For every equipped ERR weapon, persist the selected Enkindling in the desktop
build `POST` using the flat slot fields below. Send the weapon's built-in skill
as `*_aow_name` when no replaceable Ash of War is equipped; Enkindling is
validated against that skill.

```json
{
  "rh1_aow_name": "Flame of the Redmanes",
  "rh1_enkindle_affix": "Mundane",
  "rh1_enkindle_rarity": "rare"
}
```

The same pattern applies to `rh2`, `rh3`, `lh1`, `lh2`, and `lh3`. Rarity is
`common`, `rare`, or `legendary`. To clear a slot, explicitly send both
Enkindling fields as `null`. If an older client omits them, the server preserves
the saved values instead of erasing them.

The desktop build-detail and startup profile responses return these fields
inside each build's `weapons` object, for example
`weapons.rh1_enkindle_affix` and `weapons.rh1_enkindle_rarity`. Restore those
values after loading the weapon and Ash of War eligibility list. The server
also accepts the nested app form
`enkindling.rh1 = {"affix":"Mundane","rarity":"rare"}` on save.

ERR weapon records returned by:

```http
GET /api/soulslike/weapons/?game=err&limit=1000
```

include `affinity` and `affinities` for unique/locked weapon affinity effects.
The factual mapping comes from the ERR weapon-change data, with
`sl_err_aow_skills.affinity` used as a fallback. `affinity` is the primary value
for simple clients; `affinities` is the complete list for weapons that have more
than one. An empty list/`null` means no affinity is assigned and must not be
displayed as `Standard`.
This is separate from a saved build slot's selected infusion, which continues
to use `rh1_affinity`, `rh2_affinity`, etc. in the build-detail response.

### Additive linked-run collection synchronization

Updating an existing saved build synchronizes all its collectibles into every
active run linked to that build: weapons, Ashes of War, armor, talismans,
spells, Spirit Ashes, Crystal Tears, Fortunes, Curios, and Binding Runes.

The checklist is cumulative journey history. Newly selected items are added
uncollected, existing collection status is preserved, and removing or replacing
an item in the current build never deletes or uncollects its historical run
entry. Selecting the old item again reuses the existing entry rather than
creating a duplicate.

Curios are the stateful exception: sealed/unsealed is build configuration, not
collection ownership. Unsealing a Curio can add it to the run checklist, but
sealing it later never removes or uncollects the Curio. The run continues to
record that it was acquired while the build separately records which Curio is
currently unsealed.

The desktop app may send the current complete list explicitly:

```json
{
  "collection_items": [
    {"item_type":"weapon", "item_id":42, "item_name":"Claymore"},
    {"item_type":"crystal_tear", "item_id":null, "item_name":"Lightning-Shrouding Cracked Tear"},
    {"item_type":"binding_rune", "item_id":null, "item_name":"Grafted Vigor"}
  ]
}
```

If omitted, the server derives the checklist from the normal build fields.

If EldenTracker has authoritative live inventory data, include the optional list:

```json
{
  "talisman_1_id": 1020,
  "talisman_2_id": 1042,
  "talisman_3_id": null,
  "talisman_4_id": null,
  "collected_talisman_ids": [1020]
}
```

When `collected_talisman_ids` is present, IDs in that list are marked collected.
IDs absent from it retain their existing state; collection history is never
reversed by a build save. When it is omitted, existing status is preserved and
new entries default to uncollected. The build-save response includes:

```json
{"item_sync":{"runs":1,"added":3,"removed":0,"updated":2,"preserved":1}}
```

`talisman_sync` remains as a compatibility alias for released clients.

## Required client input behavior

All death inputs (F9, the Log Death button, OCR/template detection) must enter one shared
`request_death()` function. Do not increment a local death counter before the API confirms
the write.

1. Register each global hotkey once. Save every handle returned by `keyboard.on_press_key()`
   and `keyboard.on_release_key()`, and call `keyboard.unhook(handle)` before registering a
   replacement set when switching runs or restarting the listener.
2. Use an F9 key-down/key-up latch. Windows key-repeat produces multiple press events while
   F9 remains down; only the first press may call `request_death()`. Clear the latch on key-up.
3. Use one death-request lock shared by F9, the button, and automatic detection. Ignore input
   while a death POST is in flight.
4. Use an eight-second monotonic cooldown shared by manual and automatic death detection.
   This prevents F9 plus OCR from reporting the same on-screen death twice.
5. On success, replace local counters and Fury state with the values returned by the server.
   Never use `local_deaths += 1` as the authoritative result.
6. On timeout or non-2xx response, do not change local counters. Fetch `status/` and resync.
7. Do not automatically retry a timed-out death POST. Resync first; the original request may
   have committed even if its response was lost.

Suggested state:

```python
self._hotkey_handles = []
self._f9_is_down = False
self._death_request_lock = threading.Lock()
self._last_death_request = 0.0
```

The Log Death button calls `request_death()` directly. The F9 press handler only calls it
after acquiring the key latch; the F9 release handler clears the latch.

## Log death

```http
POST /api/soulslike/session/<session_token>/death/
Content-Type: application/json

{
  "boss": "Margit, the Fell Omen",
  "boss_key": "Margit, the Fell Omen (Stormveil Castle Gate)",
  "source": "listener"
}
```

`boss` and `boss_key` may be empty. With `source: "listener"`, the server falls back to the
run's currently focused boss. When the app knows the focused boss, send both values. Always
use `boss_key` as identity because several encounters share the same display name.

Normal success:

```json
{
  "ok": true,
  "duplicate": false,
  "deaths": 406,
  "total_deaths": 406,
  "session_deaths": 2,
  "boss": "Margit, the Fell Omen",
  "boss_key": "Margit, the Fell Omen (Stormveil Castle Gate)",
  "rage_pct": 50,
  "rage_name": "Frenzied",
  "is_hollow": false,
  "hollow_streak": 0,
  "just_went_hollow": false,
  "life_duration": 45,
  "total_survival": 1234,
  "longest_life": 3300,
  "current_life_sec": 0
}
```

The server has an eight-second same-run/same-boss safety window. A repeat returns HTTP 200
with `ok: true`, `duplicate: true`, and the already-authoritative death, session, and Fury
values. Treat that as a successful synchronization, not as another local increment.
Set the app's local current-streak timer from `current_life_sec` for both normal and
duplicate responses.

If the emergency request ceiling is reached, the server returns HTTP 429 JSON and a
`Retry-After` header. Release F9, wait for that duration, then fetch `status/`. Do not treat a
403/429 or any other non-2xx response as a logged death.

## Undo death

```http
POST /api/soulslike/session/<session_token>/subtract-death/
Content-Type: application/json

{}
```

F10 and the Undo button must share one in-flight lock. The server selects and deletes the
exact latest death event, then returns one authoritative recalculated snapshot:

```json
{
  "ok": true,
  "deaths": 967,
  "total_deaths": 967,
  "session_deaths": 3,
  "undone_event_id": 1787,
  "undone_boss": "Godskin Apostle",
  "undone_boss_key": "Godskin Apostle (Dominula, Windmill Village)",
  "undone_boss_deaths": 3,
  "current_boss": "Godskin Apostle",
  "current_boss_key": "Godskin Apostle (Dominula, Windmill Village)",
  "current_boss_deaths": 3,
  "boss_deaths_total": 460,
  "non_boss_deaths_total": 507,
  "true_death_rate": 20.0,
  "death_rate_ready": true,
  "session_deaths_per_hour": 20.3,
  "run_deaths_per_hour": 9.4,
  "last_death": "Godskin Apostle",
  "rage_pct": 100,
  "rage_name": "HOLLOW",
  "is_hollow": true,
  "hollow_streak": 131
}
```

Replace every matching local value from this response. In particular, set the per-boss
map entry identified by `undone_boss_key` to `undone_boss_deaths`; do not merely subtract
the Total and This Session cards. This keeps Total Deaths, This Session, Current Boss,
Boss Deaths, Everything Else, Deaths/Boss, both Deaths/Hour values, Last Death, and
Fury/Hollow synchronized in one operation. Fetch `status/` after applying the response
as a verification pass, not as the source of a client-side guess.

The Fury recovery consumes one excess Hollow stack first; only after the stack count
reaches zero can it lower the visible Fury bar below 100.

## Authoritative death math and F9 behavior

`boss_deaths_total` and `non_boss_deaths_total` are mutually exclusive, run-wide
buckets. They always reconcile to the run total:

```text
boss_deaths_total + non_boss_deaths_total == total_deaths
```

`session_deaths` is already contained within `total_deaths`. Never add it to
`boss_deaths_total`, `non_boss_deaths_total`, or `total_deaths`. For example, a
snapshot of 1,084 total deaths, 570 boss deaths, 514 non-boss deaths, and 46
session deaths must display 570 + 514 = 1,084—not 616 + 514.

Every successful `death/` response, including an idempotent duplicate response,
now returns:

```json
{
  "deaths": 1084,
  "total_deaths": 1084,
  "session_deaths": 46,
  "boss_deaths_total": 570,
  "non_boss_deaths_total": 514,
  "current_boss_deaths": 146,
  "death_breakdown_total": 1084,
  "death_breakdown_valid": true
}
```

The desktop app must replace its displayed values with these values. It must not
optimistically increment a second local copy when F9 is pressed. F9 and the Log
Death button should share one in-flight lock: send one POST, show a pending state,
then replace the cards from the response. A later `status/` poll is only a
verification snapshot and must also replace values directly rather than apply a
delta. This removes the brief +2 followed by -1 flicker.

## Correct the exact run Total Deaths

This corrects the displayed run total and does not use the normal death
button/F9 cooldown:

```http
POST /api/soulslike/session/<session_token>/set-total-deaths/
X-Listener-Key: ql_...
Content-Type: application/json

{"total_deaths": 901}
```

`total_deaths` is the exact desired run total and may be higher or lower than
the current value. The correction does not create death events, alter boss or
Everything Else attribution, change This Session, or reset Current Streak.
Boss Deaths remains the count of explicitly boss-attributed events. Everything
Else is derived as `max(0, Total Deaths - Boss Deaths)`, so the two breakdown
cards always add up to the authoritative total, including imported history.

Replace the app's total with the response and fetch `status/`. Do not alter
local boss attribution, session deaths, Fury, or Current Streak.

Compatibility note: if `cleaned_adjustments` is greater than zero, the server
removed synthetic rows created by the retired additive editor. In that one-time
repair response, also accept the returned `session_deaths`, `rage_pct`,
`rage_name`, and `hollow_streak`; Current Streak still remains untouched.

## Correct exact This Session deaths

This is deliberately separate from correcting Total Deaths:

```http
POST /api/soulslike/session/<session_token>/set-session-deaths/
X-Listener-Key: ql_...
Content-Type: application/json

{"session_deaths": 2}
```

It changes only This Session and its Deaths/Hour rate. Total Deaths, event/boss
attribution, Fury/Hollow, and Current Streak remain unchanged. This Session may
not exceed Total Deaths; if both need correction, set Total Deaths first. Replace
the app values with `deaths`, `session_deaths`, `session_deaths_per_hour`, and
`run_deaths_per_hour` from the response.

The status response is the shared rendering contract for the site, desktop app,
and every OBS/browser overlay. It is explicitly `no-store`. All death mutation
events (`death`, `undo`, `total_death_adjustment`, and
`session_death_adjustment`) cause the combined overlay to fetch a complete new
status snapshot, so future overlay metrics must also be sourced there rather
than maintained as independent counters.

## Status and Deaths/Hour

```http
GET /api/soulslike/session/<session_token>/status/
```

Relevant fields:

```json
{
  "deaths": 405,
  "session_deaths": 1,
  "last_attempted_boss": "Margit, the Fell Omen",
  "last_attempted_boss_key": "Margit, the Fell Omen (Stormveil Castle Gate)",
  "listener_session_sec": 14,
  "current_life_sec": 14,
  "lifetime_playtime_sec": 310200,
  "session_deaths_per_hour": 257.1,
  "run_deaths_per_hour": 4.7,
  "rage_pct": 100,
  "rage_name": "HOLLOW",
  "is_hollow": true,
  "hollow_streak": 128
}
```

Display the two returned rate fields; do not divide by wall-clock time in the app.

- Session rate = `session_deaths * 3600 / listener_session_sec`.
- Run rate = `deaths * 3600 / lifetime_playtime_sec`.
- The API returns `null` only when the matching played-time clock is zero.
- A short session can initially show a high rate; it naturally settles as played time grows.

## Heartbeat and timer ownership

Send every five seconds:

```http
POST /api/soulslike/session/<session_token>/heartbeat/
Content-Type: application/json

{
  "game_running": true,
  "session_sec": 14,
  "streak_sec": 14,
  "longest_sec": 3300,
  "survival_sec": 14
}
```

Timer values are absolute, monotonic seconds for the current game launch. The server adds
only the positive session delta to lifetime playtime. Do not reset them on a run-picker UI
refresh or transient network failure. The existing three-minute game-stop grace period and
new-launch session reset remain in force.

After an accepted death response, immediately set the app's local `streak_sec` to `0` before
the next heartbeat. Continue the streak from that reset value; do not send the pre-death
streak again. A duplicate response uses its returned `current_life_sec` as the canonical
value instead.

## Boss focus and attribution

```http
POST /api/soulslike/session/<session_token>/set-focus/
X-Listener-Key: ql_...
Content-Type: application/json

{"boss_name": "Margit, the Fell Omen", "boss_key": "Margit, the Fell Omen (Stormveil Castle Gate)"}
```

Send empty values to clear focus. Preserve the current UX: if a boss is focused, F9 logs
immediately against it; only ask the player to choose a boss when nothing is focused.

When the app confirms a registry encounter was defeated, use the same endpoint as
the web tracker:

```http
POST /api/soulslike/session/<session_token>/boss/mark/
X-Listener-Key: ql_...
Content-Type: application/json

{"boss_key":"Margit, the Fell Omen (Stormveil Castle Gate)"}
```

The success response includes `tier`, `rage_pct`, `rage_name`, `is_hollow`, and
`hollow_streak`. Replace the app's entire Fury/Hollow state with those values and
then allow the normal status poll to verify it. The `enemy` recovery tier means a
registry encounter categorized as Enemy/field boss; ordinary untracked world mobs
do not have a server event and therefore cannot change the shared site state.

## Tarnished Fury and Hollow rules to preserve

- Treat Fury as debt in 25-point units. Each accepted death adds one unit.
- The first four units display as 0, 25, 50, 75, and then 100 Fury. Additional
  units remain at 100 Fury and add one `hollow_streak` stack each.
- 0 = Maiden's Grace, 25 = Staggered, 50 = Frenzied, 75 = Cursed, 100 = HOLLOW.
- Duplicate death responses do not add Fury.
- Undo removes one unit, consuming an excess Hollow stack before lowering visible Fury.
- Defeats recover server-authoritative units by tier: Enemy 1, Great Enemy 2,
  Legend 4, Demigod 5, and God clears all Fury and Hollow stacks. Recovery
  consumes excess Hollow stacks before lowering the visible Fury bar.
- `hollow_streak` is no longer capped at 127. The web display renders an excess
  value of `127` as `x128` because the first HOLLOW state is included in the label.
- Death, undo, boss-mark, duplicate-death, and status responses all return the
  authoritative `rage_pct`, `rage_name`, `is_hollow`, and `hollow_streak` fields.
  The app must replace all four local values from every successful response and
  must never increment or decrement Hollow independently.

Before deploying the corresponding server code, preserve and widen the existing
counter columns, then rebuild active-run counters from their retained event history:

```bash
./chwebsiteprj/bin/python manage.py upgrade_soulslike_hollow_counters
```

The command is idempotent. It changes `hollow_streak` and `hollow_boss_kills` to
`BIGINT UNSIGNED`, replays existing death/boss events to repair the complete Fury/Hollow
state for active sessions, and does not delete session, death, boss, or collection rows.
