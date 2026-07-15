#!/bin/bash
# fix_amp_instance_perms.sh
#
# Grants read+traverse access to UID 33 (www-data on the QuestLog web/bot server,
# CH-CmtyServer) for the AMP_Logs folder and GenericModule.kvp file of every AMP
# game server instance found under the given storage root(s) - the only two
# things the QuestLog bots actually read. Deliberately does NOT touch the rest
# of the instance directory (world saves, player data), which can carry special
# ownership/attributes AMP itself relies on. Safe to re-run any time - idempotent,
# and covers new instances automatically without needing to know their names in
# advance.
#
# Why UID 33 and not a username: this script may run on a different machine
# (Server B / Server C) than where "www-data" was created, so the NFS client
# (sec=sys) only ever presents the raw UID over the wire - granting by username
# here would silently do nothing if no local account happens to share that name.
#
# Usage:
#   sudo ./fix_amp_instance_perms.sh /mnt/gamestorage1 [/mnt/gamestorage2 ...]
#
# Recommended: add to a cron job (e.g. hourly) or a systemd timer on each AMP
# host so newly created instances get fixed automatically without manual action:
#   0 * * * * root /path/to/fix_amp_instance_perms.sh /mnt/gamestorage1 /mnt/gamestorage2 >> /var/log/amp_perms_fix.log 2>&1

set -euo pipefail

WWW_DATA_UID=33

if [ "$#" -eq 0 ]; then
  echo "Usage: $0 <storage_root> [storage_root...]" >&2
  exit 1
fi

if ! command -v setfacl >/dev/null 2>&1; then
  echo "ERROR: setfacl not found. Install acl package (apt install acl) and ensure the filesystem is mounted with acl support." >&2
  exit 1
fi

fixed_count=0
skipped_count=0

for root in "$@"; do
  if [ ! -d "$root" ]; then
    echo "WARNING: $root does not exist, skipping" >&2
    continue
  fi
  echo "Scanning $root for AMP instances..."
  # An AMP instance directory: owned by 'amp' user, contains an AMP_Logs subfolder.
  # -maxdepth 1 keeps this to top-level instance dirs, not arbitrary nested folders.
  while IFS= read -r -d '' instance_dir; do
    name=$(basename "$instance_dir")
    if [ ! -d "$instance_dir/AMP_Logs" ]; then
      skipped_count=$((skipped_count + 1))
      continue
    fi
    # Test if ACLs are actually supported here before attempting - fails loudly
    # and clearly if the filesystem doesn't support them, instead of a cryptic
    # per-directory error for every single instance.
    if ! setfacl -m u:${WWW_DATA_UID}:rx "$instance_dir" 2>/tmp/setfacl_err; then
      echo "ERROR: setfacl not supported on this filesystem ($root). $(cat /tmp/setfacl_err)" >&2
      rm -f /tmp/setfacl_err
      exit 1
    fi
    rm -f /tmp/setfacl_err
    # Only AMP_Logs needs to be readable by www-data (that's all the bots ever
    # read) - recursing into the whole instance dir also touches game-save
    # internals (world data, player saves) that can carry special ownership/
    # attributes AMP itself relies on, and setfacl -R aborts the whole run on
    # the first file it can't touch there. GenericModule.kvp is also read
    # directly (join/leave regex config), so it gets an explicit grant too.
    setfacl -R -m u:${WWW_DATA_UID}:rx "$instance_dir/AMP_Logs"
    setfacl -R -d -m u:${WWW_DATA_UID}:rx "$instance_dir/AMP_Logs"
    if [ -f "$instance_dir/GenericModule.kvp" ]; then
      setfacl -m u:${WWW_DATA_UID}:r "$instance_dir/GenericModule.kvp"
    fi
    echo "  fixed: $name"
    fixed_count=$((fixed_count + 1))
  done < <(find "$root" -maxdepth 1 -mindepth 1 -type d -user amp -print0)
done

echo ""
echo "Done. Fixed: $fixed_count instance(s). Skipped (no AMP_Logs found): $skipped_count."
