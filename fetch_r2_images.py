"""
Download all Remnant 2 item images from the toolkit CDN and save locally.
Source: https://d2sqltdcj8czo5.cloudfront.net
Dest:   /srv/ch-webserver/app/static/r2/items/

Run: chwebsiteprj/bin/python3 fetch_r2_images.py
"""
import django, os, time, urllib.request, urllib.error
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

CDN_BASE  = 'https://d2sqltdcj8czo5.cloudfront.net'
LOCAL_BASE = '/srv/ch-webserver/app/static/r2'

TABLES_WITH_IMAGES = [
    ('r2_archetypes',       'image_path'),
    ('r2_skills',           'image_path'),
    ('r2_perks',            'image_path'),
    ('r2_traits',           'image_path'),
    ('r2_weapons',          'image_path'),
    ('r2_mods',             'image_path'),
    ('r2_rings',            'image_path'),
    ('r2_amulets',          'image_path'),
    ('r2_armor',            'image_path'),
    ('r2_mutators',         'image_path'),
    ('r2_relics',           'image_path'),
    ('r2_relic_fragments',  'image_path'),
]

def collect_paths():
    paths = set()
    with get_db_session() as db:
        for table, col in TABLES_WITH_IMAGES:
            rows = db.execute(text(f'SELECT {col} FROM {table} WHERE {col} IS NOT NULL')).fetchall()
            for r in rows:
                if r[0]:
                    paths.add(r[0])
    return paths

def download_image(path):
    local_path = os.path.join(LOCAL_BASE, path.lstrip('/'))
    if os.path.exists(local_path):
        return 'skip'
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    url = CDN_BASE + path
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            with open(local_path, 'wb') as f:
                f.write(resp.read())
        return 'ok'
    except urllib.error.HTTPError as e:
        return f'http_{e.code}'
    except Exception as e:
        return f'err_{type(e).__name__}'

def main():
    print('Collecting image paths from DB...')
    paths = collect_paths()
    print(f'Found {len(paths)} unique image paths')

    downloaded = skipped = failed = 0
    errors = []

    for i, path in enumerate(sorted(paths), 1):
        result = download_image(path)
        if result == 'ok':
            downloaded += 1
        elif result == 'skip':
            skipped += 1
        else:
            failed += 1
            errors.append((path, result))

        if i % 25 == 0 or i == len(paths):
            print(f'  [{i}/{len(paths)}] downloaded={downloaded} skipped={skipped} failed={failed}')

        # Be polite - small delay between requests
        if result == 'ok':
            time.sleep(0.1)

    print(f'\nDone. Downloaded: {downloaded}  Skipped: {skipped}  Failed: {failed}')
    if errors:
        print('Failures:')
        for path, err in errors[:20]:
            print(f'  {err}: {path}')

    # Count files on disk
    total_files = sum(len(files) for _, _, files in os.walk(LOCAL_BASE))
    print(f'Total files in {LOCAL_BASE}: {total_files}')

if __name__ == '__main__':
    main()
