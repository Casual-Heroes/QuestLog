#!/usr/bin/env python3
"""
Delete and recreate all casual-heroes.com rooms to wipe membership state events
(ban notifications that can't be purged via history API).

ONLY processes rooms where room_id ends with :casual-heroes.com
Skips federated rooms from other homeservers.

Steps per room:
  1. Record room name, topic, and which spaces it belongs to
  2. Delete the room via admin API (block=False so users can rejoin)
  3. Create a new room with the same name/topic
  4. Add the new room back to each space it was in

Usage:
  1. Get a fresh admin compat token:
     sudo docker exec $(sudo docker ps | grep mas | grep -v postgres | awk '{print $1}') \
       mas-cli --config /config/config.yaml manage issue-compatibility-token \
       --yes-i-want-to-grant-synapse-admin-privileges ryven

  2. Paste token below and run:
     python3 /srv/ch-webserver/recreate_matrix_rooms.py
"""
import json
import time
import urllib.request
import urllib.parse

TOKEN = "PASTE_TOKEN_HERE"
HOMESERVER = "http://localhost:8008"
# The bot user that will create the new rooms (must be a local user)
BOT_USER = "@ryven:casual-heroes.com"
DRY_RUN = True  # Set to False to actually make changes

def api_get(path):
    req = urllib.request.Request(
        f"{HOMESERVER}{path}",
        headers={"Authorization": f"Bearer {TOKEN}"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def api_post(path, data):
    req = urllib.request.Request(
        f"{HOMESERVER}{path}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def api_put(path, data):
    req = urllib.request.Request(
        f"{HOMESERVER}{path}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="PUT"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def api_delete(path, data):
    req = urllib.request.Request(
        f"{HOMESERVER}{path}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="DELETE"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

# Step 1: Get all rooms
print("Fetching all rooms...")
data = api_get("/_synapse/admin/v1/rooms?limit=500")
all_rooms = data.get("rooms", [])
print(f"Total rooms: {len(all_rooms)}")

# Filter to only our homeserver rooms, skip spaces (we don't want to delete the space itself)
our_rooms = [
    r for r in all_rooms
    if r["room_id"].endswith(":casual-heroes.com")
]
print(f"casual-heroes.com rooms: {len(our_rooms)}")

# Separate spaces from regular rooms
# Spaces have room_type = 'm.space'
spaces = [r for r in our_rooms if r.get("room_type") == "m.space"]
regular_rooms = [r for r in our_rooms if r.get("room_type") != "m.space"]

print(f"  Spaces (will NOT be recreated): {len(spaces)}")
print(f"  Regular rooms (will be recreated): {len(regular_rooms)}")
print()

for s in spaces:
    print(f"  SPACE: {s.get('name') or s['room_id']} ({s['room_id']})")
print()

# Show what we'll process
print("Rooms to recreate:")
for r in regular_rooms:
    name = r.get("name") or r["room_id"]
    members = r.get("joined_members", 0)
    print(f"  {name} | {r['room_id']} | {members} members")
print()

if DRY_RUN:
    print("=" * 60)
    print("DRY RUN - no changes made.")
    print("Set DRY_RUN = False to actually recreate rooms.")
    print("=" * 60)
    exit(0)

# Step 2: For each regular room, get its state (name, topic, parent spaces)
print("Starting room recreation...")
results = []

for room in regular_rooms:
    rid = room["room_id"]
    room_name = room.get("name") or ""
    encoded = urllib.parse.quote(rid, safe="")

    print(f"\nProcessing: {room_name} ({rid})")

    # Get full state to find parent spaces and topic
    topic = ""
    parent_space_ids = []
    try:
        state = api_get(f"/_matrix/client/v3/rooms/{encoded}/state")
        if isinstance(state, list):
            for event in state:
                if event.get("type") == "m.room.topic":
                    topic = event.get("content", {}).get("topic", "")
                if event.get("type") == "m.space.parent":
                    parent_space_ids.append(event.get("state_key", ""))
    except Exception as e:
        print(f"  WARN: could not fetch state: {e}")

    print(f"  Name: {room_name!r}, Topic: {topic!r}, Parents: {parent_space_ids}")

    # Delete the old room
    try:
        del_resp = api_delete(
            f"/_synapse/admin/v2/rooms/{encoded}",
            {
                "block": False,           # don't block users from rejoining
                "purge": True,            # purge local events (including those ban state events)
                "message": "Room reset - please rejoin",
                "new_room_user_id": BOT_USER,
            }
        )
        delete_id = del_resp.get("delete_id", "")
        print(f"  Deleted: delete_id={delete_id}")
    except Exception as e:
        print(f"  ERR deleting: {e}")
        results.append({"room": rid, "name": room_name, "status": "delete_failed", "error": str(e)})
        continue

    # Wait a moment for deletion to process
    time.sleep(2)

    # Create new room
    try:
        create_body = {
            "name": room_name,
            "preset": "private_chat",
            "visibility": "private",
            "creation_content": {},
        }
        if topic:
            create_body["topic"] = topic

        new_room = api_post("/_matrix/client/v3/createRoom", create_body)
        new_rid = new_room.get("room_id", "")
        print(f"  Created: {new_rid}")
    except Exception as e:
        print(f"  ERR creating: {e}")
        results.append({"room": rid, "name": room_name, "status": "create_failed", "error": str(e)})
        continue

    # Add new room to parent spaces
    new_encoded = urllib.parse.quote(new_rid, safe="")
    for space_id in parent_space_ids:
        space_encoded = urllib.parse.quote(space_id, safe="")
        try:
            # Add room as child of space
            api_put(
                f"/_matrix/client/v3/rooms/{space_encoded}/state/m.space.child/{new_encoded}",
                {"via": ["casual-heroes.com"], "suggested": False}
            )
            print(f"  Added to space: {space_id}")
        except Exception as e:
            print(f"  WARN: could not add to space {space_id}: {e}")

    results.append({
        "room": rid,
        "name": room_name,
        "new_room": new_rid,
        "status": "ok",
        "spaces": parent_space_ids,
    })

print("\n" + "=" * 60)
print("RESULTS:")
ok = [r for r in results if r["status"] == "ok"]
fail = [r for r in results if r["status"] != "ok"]
print(f"  Success: {len(ok)}")
print(f"  Failed:  {len(fail)}")
if fail:
    print("\nFailed rooms:")
    for r in fail:
        print(f"  {r['name']}: {r['status']} - {r.get('error', '')}")
print("=" * 60)
