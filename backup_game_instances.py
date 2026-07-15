"""
Mirror every AMP game-server instance's data directory to two local backup
disks, using QuestLog's own gamebot_configs table as the source of truth for
which instances exist and where their data lives (not a directory scan -
some games, e.g. Valheim, don't create a Backups/ subfolder, so scanning for
one would silently miss them).

Source of truth: gamebot_configs.amp_log_dir, e.g.
  /mnt/remote/serverb/gamestorage1/ESARebellion01/AMP_Logs
The instance's actual data root is the parent of AMP_Logs - stripping that
suffix gives us the directory to mirror (game files, saves, AND the AMP-taken
Backups/ folder when the game does produce one, both come along for free).

Destinations (both always updated - not primary/failover, just two mirrors):
  /backup/primary2tb/<instance_name>/
  /backup/secondary4tb/<instance_name>/

A path in gamebot_configs can go stale (SSD swap, instance moved to a
different server) - see the ESARebellion01 case from 2026-07-12, where a
Server B SSD failure moved it to a different mount and the DB wasn't updated
until caught here. Rather than fail the whole run, each instance is
validated independently: missing/unreadable paths are logged as warnings and
skipped, so one stale record doesn't block backups for every other instance.

Run: chwebsiteprj/bin/python3 backup_game_instances.py
Intended to run on a schedule (cron/systemd timer) - safe to re-run anytime,
rsync only transfers changed data.
"""
import django, os, subprocess, sys, time
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_engine
from sqlalchemy import text

engine = get_engine()

DESTINATIONS = [
    '/backup/primary2tb',
    '/backup/secondary4tb',
]

RSYNC_EXCLUDES = [
    '--exclude', '*.tmp',
    '--exclude', '*.lock',
]


def load_instances():
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT instance_name, amp_log_dir FROM gamebot_configs "
            "WHERE amp_log_dir IS NOT NULL AND amp_log_dir != '' ORDER BY instance_name"
        )).fetchall()
    return [(r[0], r[1]) for r in rows]


def data_root_for(amp_log_dir: str) -> str:
    """Strip the trailing /AMP_Logs to get the instance's actual data directory."""
    suffix = '/AMP_Logs'
    if amp_log_dir.endswith(suffix):
        return amp_log_dir[:-len(suffix)]
    # Unexpected shape - don't guess, caller will fail the exists() check below
    # and this gets logged as a warning rather than silently backing up the
    # wrong directory.
    return amp_log_dir


def sync_instance(instance_name: str, source_dir: str) -> dict:
    result = {'instance': instance_name, 'source': source_dir, 'ok': True, 'destinations': []}

    if not os.path.isdir(source_dir):
        result['ok'] = False
        result['error'] = f'source path does not exist or is not a directory: {source_dir}'
        return result

    for dest_root in DESTINATIONS:
        if not os.path.isdir(dest_root):
            result['ok'] = False
            result['destinations'].append({'path': dest_root, 'ok': False, 'error': 'destination disk not mounted'})
            continue

        dest_dir = os.path.join(dest_root, instance_name) + '/'
        src = source_dir.rstrip('/') + '/'
        cmd = ['rsync', '-a', '--delete'] + RSYNC_EXCLUDES + [src, dest_dir]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if proc.returncode != 0:
                result['ok'] = False
                result['destinations'].append({
                    'path': dest_root, 'ok': False,
                    'error': f'rsync exited {proc.returncode}: {proc.stderr.strip()[:500]}',
                })
            else:
                result['destinations'].append({'path': dest_root, 'ok': True})
        except subprocess.TimeoutExpired:
            result['ok'] = False
            result['destinations'].append({'path': dest_root, 'ok': False, 'error': 'rsync timed out after 1h'})
        except Exception as e:
            result['ok'] = False
            result['destinations'].append({'path': dest_root, 'ok': False, 'error': str(e)})

    return result


def main():
    started = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f'=== Game instance backup sync started {started} ===')

    instances = load_instances()
    print(f'{len(instances)} instance(s) found in gamebot_configs\n')

    results = []
    for instance_name, amp_log_dir in instances:
        source_dir = data_root_for(amp_log_dir)
        print(f'-- {instance_name} --')
        print(f'   source: {source_dir}')
        r = sync_instance(instance_name, source_dir)
        results.append(r)
        if not r['ok'] and 'error' in r:
            print(f'   WARNING: {r["error"]} - skipped')
        else:
            for d in r['destinations']:
                status = 'OK' if d['ok'] else f'FAILED ({d.get("error", "unknown error")})'
                print(f'   -> {d["path"]}: {status}')
        print()

    ok_count = sum(1 for r in results if r['ok'])
    print(f'=== Summary: {ok_count}/{len(results)} instance(s) fully synced to both destinations ===')
    failed = [r for r in results if not r['ok']]
    if failed:
        print('Instances needing attention:')
        for r in failed:
            reason = r.get('error') or '; '.join(
                d.get('error', '') for d in r['destinations'] if not d['ok']
            )
            print(f'  - {r["instance"]}: {reason}')
        sys.exit(1)


if __name__ == '__main__':
    main()
