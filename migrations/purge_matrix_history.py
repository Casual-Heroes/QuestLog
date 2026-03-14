#!/usr/bin/env python3
"""Purge all Matrix room history before today."""
import json
import time
import urllib.request
import urllib.parse

TOKEN = "mct_F5E4EymqoAfdunf3M4wdApNcwHgZyd_DyNMC4"
HOMESERVER = "http://localhost:8008"

# Purge everything before today midnight
import datetime
tomorrow = datetime.date.today() + datetime.timedelta(days=1)
purge_ts = int(time.mktime(tomorrow.timetuple())) * 1000
print(f"Purging ALL history up to tomorrow ({purge_ts})")

# Get all rooms
req = urllib.request.Request(
    f"{HOMESERVER}/_synapse/admin/v1/rooms?limit=200",
    headers={"Authorization": f"Bearer {TOKEN}"}
)
with urllib.request.urlopen(req) as r:
    rooms = json.loads(r.read().decode()).get("rooms", [])

print(f"Found {len(rooms)} rooms")

for room in rooms:
    rid = room["room_id"]
    name = room.get("name") or rid
    encoded = urllib.parse.quote(rid, safe="")
    try:
        req = urllib.request.Request(
            f"{HOMESERVER}/_synapse/admin/v1/purge_history/{encoded}",
            data=json.dumps({"purge_up_to_ts": purge_ts, "delete_local_events": False}).encode(),
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as r:
            resp = json.loads(r.read().decode())
            print(f"  OK  {name}: {resp}")
    except Exception as e:
        print(f"  ERR {name}: {e}")
