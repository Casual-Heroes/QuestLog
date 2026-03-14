#!/usr/bin/env python3
"""
Set the stickerpicker widget for all existing Matrix users via SQLite directly.
Usage: sudo python3 set_widget_all_users.py
"""
import sqlite3
import json
import uuid

DB_PATH = "/opt/synapse/homeserver.db"
WIDGET_URL = "https://gifs.casual-heroes.com"
WIDGET_NAME = "Stickers & GIFs"

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Get all active non-guest users
    cur.execute("SELECT name FROM users WHERE deactivated=0 AND is_guest=0")
    users = [row[0] for row in cur.fetchall()]
    print(f"Found {len(users)} users")

    skipped = 0
    updated = 0
    errors = 0

    for user_id in users:
        try:
            # Get existing m.widgets account data
            cur.execute(
                "SELECT content FROM account_data WHERE user_id=? AND account_data_type='m.widgets'",
                (user_id,)
            )
            row = cur.fetchone()
            widgets = json.loads(row[0]) if row else {}

            # Check if stickerpicker already set
            already_set = any(
                v.get("content", {}).get("url", "").startswith(WIDGET_URL)
                for v in widgets.values()
                if isinstance(v, dict)
            )
            if already_set:
                print(f"  SKIP {user_id}")
                skipped += 1
                continue

            # Add stickerpicker widget
            widget_id = str(uuid.uuid4())
            widgets[widget_id] = {
                "content": {
                    "type": "m.stickerpicker",
                    "name": WIDGET_NAME,
                    "url": f"{WIDGET_URL}/?theme=$matrix_color_scheme&widgetId=$matrix_widget_id&parentUrl=$matrix_client_origin",
                    "creatorUserId": user_id,
                },
                "sender": user_id,
                "state_key": widget_id,
                "type": "m.widget",
                "id": widget_id,
            }

            content = json.dumps(widgets)
            if row:
                cur.execute(
                    "UPDATE account_data SET content=? WHERE user_id=? AND account_data_type='m.widgets'",
                    (content, user_id)
                )
            else:
                cur.execute(
                    "INSERT INTO account_data (user_id, account_data_type, stream_id, content) VALUES (?, 'm.widgets', (SELECT COALESCE(MAX(stream_id),0)+1 FROM account_data), ?)",
                    (user_id, content)
                )

            print(f"  SET  {user_id}")
            updated += 1

        except Exception as e:
            print(f"  ERR  {user_id}: {e}")
            errors += 1

    conn.commit()
    conn.close()
    print(f"\nDone: {updated} updated, {skipped} skipped, {errors} errors")

if __name__ == "__main__":
    main()
