# QuestLog future product design

Status: design discussion only. Nothing in this document is approved for
immediate implementation, and none of it changes the current database or API.

## Profile-first journeys

The permanent link people share should identify the person, not one run:

```text
/@ryven
```

Individual public journeys live beneath that profile:

```text
/@ryven/radahn-fantasy
```

Existing internal session identifiers and compatibility routes remain stable.
Public aliases do not replace relational IDs, session tokens, desktop tracker
identifiers, or overlay identifiers.

### Agreed behavior

- A user may intentionally have multiple active runs at the same time, including
  private, practice, challenge, and streaming runs.
- A run appears as the profile's featured journey only after the user explicitly
  selects it. There is no automatic newest-run fallback.
- If no run is featured, the profile has no featured-journey card. Other public
  active runs may still appear under Active Journeys.
- Private runs never appear to visitors and cannot accidentally be featured.
- Selecting a new featured run replaces the previous selection; unfeaturing a
  run leaves the featured area empty.
- The canonical public handle follows the user's current username.
- Previous handles remain reserved to that account and permanently redirect to
  the current handle so old shared links continue to work.
- A run title is separate from its build name. Changing the title does not
  automatically change its established public slug.
- Run slugs are unique per user, not globally.

## Twitch Panel Extension

The long-term Twitch link remains the user's permanent QuestLog profile. A
Twitch Panel Extension can additionally display the explicitly featured public
journey and update while the run is active.

### Panel behavior

- Resolve the QuestLog account using Twitch's stable numeric broadcaster ID,
  never the broadcaster's changeable Twitch username.
- Display only the explicitly featured public journey.
- When nothing is featured, show a neutral "No journey currently featured"
  state and a link to the user's QuestLog profile.
- If a featured run becomes private, stop serving it to the extension
  immediately.
- Distinguish stream state from run state: Live, Journey Active / Stream Offline,
  Paused, and Completed are different conditions.
- Keep version one read-only unless viewer interaction is separately designed,
  threat-modeled, and approved.

### Data flow

```text
EldenTracker / QuestLog web controls
                |
                v
       QuestLog authoritative state
                |
                +-- initial sanitized snapshot
                |
                +-- compact Twitch Extension PubSub updates
                                |
                                v
                       Twitch panel viewers
```

- The Extension Backend Service validates Twitch's signed Extension JWT and
  uses its channel/broadcaster identity to resolve the QuestLog account.
- The panel receives sanitized, read-only state. Session write tokens, listener
  API keys, overlay tokens, and other capabilities are never sent to viewers.
- Load one complete snapshot when the panel opens or becomes visible.
- Push compact updates after deaths, boss changes, collection changes, rage or
  streak changes, session state changes, and featured-run changes.
- Periodically resynchronize a full snapshot to recover from missed events.
- Do not make every viewer poll the normal tracker API.

### Candidate version-one panel content

- Journey title, game, and mode
- Live / active / paused / completed state
- Total and current-session deaths
- Current boss and boss-attributed deaths
- Boss progress
- Current streak and Tarnished Fury state
- Collection progress
- Link to the full public journey/profile

### Delivery stages

1. Ship the permanent profile and public journey aliases.
2. Create a Twitch Hosted Test panel for a Casual Heroes test channel.
3. Add broadcaster configuration and QuestLog account linking.
4. Add initial snapshot loading and real-time PubSub updates.
5. Test with several consenting Casual Heroes streamers.
6. Complete Twitch review materials and submit the public Panel Extension.
7. Consider a separate video-component extension only after the panel is stable.

Official Twitch references:

- https://dev.twitch.tv/docs/extensions/
- https://dev.twitch.tv/docs/extensions/designing/
- https://dev.twitch.tv/docs/extensions/required-technical-background/
- https://dev.twitch.tv/docs/extensions/life-cycle

## Image-optional game builders

Future builders, including a rebuilt Remnant 2 builder and possible Lies of P
support, are text-first and image-optional. The ER/ERR presentation is the safe,
functional baseline: original factual descriptions, statistics, mechanics,
acquisition information, filtering, comparison, and original interface design.

### Media rules

- A builder must remain complete and usable without publisher-owned images.
- Use original generic category artwork or icons that do not reproduce a
  recognizable game asset or item design.
- Do not scrape or extract wiki screenshots, game textures, inventory icons,
  logos, audio, artwork, or promotional assets merely because attribution is
  available.
- A wiki's general content license does not automatically cover files identified
  as publisher copyright or other third-party material.
- Official media-gallery availability is not treated as redistribution
  permission without applicable license language or written authorization.
- Real item images may be added individually only after their rights basis and
  required notices have been reviewed and recorded.

### Image provenance record

An image-capable implementation should track at least:

```text
item_id
image_url or storage_key
rights_holder
source_url
license_identifier
license_notice
permission_reference
captured_by
reviewed_at
rights_status
content_hash
```

Only an approved rights status renders publicly. Missing, pending, rejected, or
expired records fall back to the text-first card and original category artwork.
Publisher-specific permissions can therefore be added later without redesigning
the underlying builder.

Official publisher references reviewed during this design discussion:

- https://www.arcgames.com/en/games/remnant-ii/media
- https://account.arcgames.com/en/about/terms
- https://www.neowiz.com/en/media/press-release-detail/3344
