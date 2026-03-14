"""
Migration: Add available_from / available_until time-gate columns to web_flairs.
Also sets the Founding Member flair (id=37) to available_until = July 6, 2026 00:00 UTC
(one month after Open Beta launch on June 6, 2026).

Run with:
  chwebsiteprj/bin/python3 alter_flairs_add_time_gate.py
"""
import django
import os
from datetime import datetime, timezone
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

# June 6, 2026 00:00 UTC - Open Beta launch (Founding Member becomes available)
OPEN_BETA_TS = int(datetime(2026, 6, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())
# July 6, 2026 00:00 UTC - Founding Member window closes (exactly 1 month)
FOUNDING_ENDS_TS = int(datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc).timestamp())

engine = get_engine()
with engine.connect() as conn:
    cols = {row[0] for row in conn.execute(text("DESCRIBE web_flairs")).fetchall()}

    if 'available_from' not in cols:
        conn.execute(text(
            "ALTER TABLE web_flairs ADD COLUMN available_from BIGINT NULL AFTER display_order"
        ))
        print("Added available_from")
    else:
        print("available_from already exists - skipped")

    if 'available_until' not in cols:
        conn.execute(text(
            "ALTER TABLE web_flairs ADD COLUMN available_until BIGINT NULL AFTER available_from"
        ))
        print("Added available_until")
    else:
        print("available_until already exists - skipped")

    # Set Founding Member (id=37) time gate:
    # - available_from = Open Beta launch (June 6, 2026) - not claimable before then
    # - available_until = July 6, 2026 - window closes after 1 month
    # Early Access users already have the flair granted directly, so the time gate
    # only affects the claim-on-registration path during Open Beta.
    conn.execute(text(
        "UPDATE web_flairs SET available_from=:af, available_until=:au WHERE id=37"
    ), {'af': OPEN_BETA_TS, 'au': FOUNDING_ENDS_TS})
    print(f"Set Founding Member available_from={OPEN_BETA_TS} ({datetime.fromtimestamp(OPEN_BETA_TS, tz=timezone.utc).isoformat()})")
    print(f"Set Founding Member available_until={FOUNDING_ENDS_TS} ({datetime.fromtimestamp(FOUNDING_ENDS_TS, tz=timezone.utc).isoformat()})")

    conn.commit()

print("Done.")
