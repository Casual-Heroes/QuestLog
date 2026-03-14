#!/usr/bin/env python3
"""
Add saved_roles column to web_fluxer_members for role persistence.
Runs against the warden database (Fluxer bot DB).
"""
import sys
import MySQLdb

SOCKET = '/var/run/mysqld/mysqld.sock'
USER = 'warden'
PASS = 'VueHm6m!8RSeZ+W7WGu!HD*ECTgUaqLqgSxd3'
DB = 'warden'

conn = MySQLdb.connect(unix_socket=SOCKET, user=USER, passwd=PASS, db=DB)
c = conn.cursor()

# Check if column already exists
c.execute("SHOW COLUMNS FROM web_fluxer_members LIKE 'saved_roles'")
if c.fetchone():
    print("saved_roles column already exists - nothing to do.")
    conn.close()
    sys.exit(0)

print("Adding saved_roles column to web_fluxer_members...")
c.execute("""
    ALTER TABLE web_fluxer_members
    ADD COLUMN saved_roles TEXT NULL DEFAULT NULL
        COMMENT 'JSON list of role IDs saved on member leave for role persistence'
    AFTER roles
""")
conn.commit()
print("Done.")

# Verify
c.execute("SHOW COLUMNS FROM web_fluxer_members LIKE 'saved_roles'")
row = c.fetchone()
print(f"Column confirmed: {row}")
conn.close()
