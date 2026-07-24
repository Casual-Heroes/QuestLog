# Palworld AMP crash watchdog

`monitor_palworld_amp` watches AMP's controller-level application state for the
Palworld instance. AMP exposes `ready`, `stopped`, transitional states, `failed`
(100), and `indeterminate` (999); it does not expose a state literally named
`error`.

The watchdog is intentionally conservative:

- It must observe `ready` before it arms and persists that fact across watchdog
  restarts. A first-ever start with no state file while Palworld is already
  stopped will never start the server.
- It requires two consecutive unhealthy polls by default.
- It polls every 5 seconds by default, so a persistent crash is normally acted
  on within approximately 5–10 seconds.
- An observed `stopping`, sleeping, suspended, or maintenance state disarms it,
  so an intentional AMP stop is not undone.
- AMP/API connection errors never trigger a restart.
- One incident creates one ping, and automatic recovery has a 5-minute
  cooldown. Recovery and timeout follow-ups do not ping the role/user again.
- Its only persistent data is a small JSON state file in `cache/`; it does not
  query or modify the application database.

## Safe live check

This reads AMP once and makes no state-file, Discord, or AMP changes:

```bash
/srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py \
  monitor_palworld_amp --once --dry-run
```

Verify the output names the intended instance and reports `state=ready`. If the
AMP instance name differs, set `PALWORLD_AMP_INSTANCE` in
`/etc/casual-heroes/secrets.env`.

## Install the service

```bash
sudo cp /srv/ch-webserver/scripts/casualheroes-palworld-watchdog.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now casualheroes-palworld-watchdog.service
sudo systemctl status casualheroes-palworld-watchdog.service
```

Follow its logs with:

```bash
journalctl -u casualheroes-palworld-watchdog.service -f
```

For planned maintenance, stop Palworld normally through AMP while the watchdog
is running so it observes AMP's `stopping` state and disarms. If the watchdog is
stopped first while its persisted state is armed, move its state file aside
before later starting the watchdog with Palworld intentionally stopped:

```bash
mv /srv/ch-webserver/cache/palworld_amp_watchdog_state.json \
  /srv/ch-webserver/cache/palworld_amp_watchdog_state.pre-maintenance.json
```

The service runs as `fulldata:nogroup`, loads the same Django production env
files as the website, and may write only to `/srv/ch-webserver/cache`.

## Discord behavior

The crash alert is sent to mod-chat (`1376286847650758789`) with controlled
mentions for Ryven (`141890558045061120`) and Server Managers
(`1346385909158903839`). Discord `allowed_mentions` is restricted to those exact
IDs. Console content is excluded by default; set
`PALWORLD_CRASH_INCLUDE_CONSOLE=true` only if sharing matching fatal/error lines
in mod-chat is desired.
