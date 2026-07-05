"""
Download Remnant 2 item images from remnant2.wiki.gg using the MediaWiki API.
Saves to /srv/ch-webserver/app/static/r2/items/<category>/

Run: chwebsiteprj/bin/python3 fetch_r2_images_wiki.py
"""
import django, os, time, re, json
import urllib.request, urllib.parse
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

LOCAL_BASE = '/srv/ch-webserver/app/static/r2/items'
WIKI_API   = 'https://remnant2.wiki.gg/api.php'
WIKI_BASE  = 'https://remnant2.wiki.gg'

# Map our DB table -> (category_folder, query_titles)
# We'll query the wiki API for image info per item name
CATEGORIES = {
    'r2_archetypes':      'archetypes',
    'r2_weapons':         'weapons',
    'r2_mods':            'mods',
    'r2_rings':           'rings',
    'r2_amulets':         'amulets',
    'r2_armor':           'armor',
    'r2_mutators':        'mutators',
    'r2_relics':          'relics',
    'r2_relic_fragments': 'relicfragments',
    'r2_traits':          'traits',
}

def wiki_api(params):
    params['format'] = 'json'
    url = WIKI_API + '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': 'QuestLog/1.0 (casual-heroes.com)'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def get_image_url_for_title(title):
    """Query wiki API for the main image of a page."""
    data = wiki_api({
        'action': 'query',
        'titles': title,
        'prop': 'pageimages',
        'piprop': 'original',
        'pilimit': 1,
    })
    pages = data.get('query', {}).get('pages', {})
    for page in pages.values():
        orig = page.get('original', {})
        if orig.get('source'):
            return orig['source']
    return None

def get_image_urls_batch(titles):
    """Batch query up to 50 titles at once."""
    data = wiki_api({
        'action': 'query',
        'titles': '|'.join(titles),
        'prop': 'pageimages',
        'piprop': 'original',
        'pilimit': 50,
    })
    result = {}
    pages = data.get('query', {}).get('pages', {})
    for page in pages.values():
        name = page.get('title', '')
        orig = page.get('original', {})
        if orig.get('source'):
            result[name] = orig['source']
    return result

def download_file(url, local_path):
    if os.path.exists(local_path):
        return 'skip'
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'QuestLog/1.0 (casual-heroes.com)'})
        with urllib.request.urlopen(req, timeout=15) as r:
            with open(local_path, 'wb') as f:
                f.write(r.read())
        return 'ok'
    except Exception as e:
        return f'err_{type(e).__name__}'

def slugify_filename(name):
    """Convert item name to likely wiki page title."""
    return name  # Wiki uses exact item names as page titles

def main():
    os.makedirs(LOCAL_BASE, exist_ok=True)
    total_downloaded = total_skipped = total_failed = 0
    db_updates = []

    with get_db_session() as db:
        for table, folder in CATEGORIES.items():
            print(f'\n[{table}]')
            rows = db.execute(text(f'SELECT id, name FROM {table}')).fetchall()
            if not rows:
                print('  No rows.')
                continue

            # Batch in groups of 50
            batch_size = 50
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i+batch_size]
                titles = [r[1] for r in batch]

                try:
                    url_map = get_image_urls_batch(titles)
                    time.sleep(0.3)
                except Exception as e:
                    print(f'  API error: {e}')
                    url_map = {}

                for row_id, name in batch:
                    img_url = url_map.get(name)
                    if not img_url:
                        # Try without special chars
                        clean = re.sub(r"['\"]", '', name)
                        img_url = url_map.get(clean)

                    if not img_url:
                        total_failed += 1
                        continue

                    # Derive local filename from URL
                    filename = os.path.basename(img_url.split('?')[0])
                    local_path = os.path.join(LOCAL_BASE, folder, filename)
                    rel_path = f'/static/r2/items/{folder}/{filename}'

                    result = download_file(img_url, local_path)
                    if result == 'ok':
                        total_downloaded += 1
                        db_updates.append((table, row_id, rel_path))
                        time.sleep(0.05)
                    elif result == 'skip':
                        total_skipped += 1
                        db_updates.append((table, row_id, rel_path))
                    else:
                        total_failed += 1
                        print(f'  FAIL {name}: {result}')

            print(f'  done ({len(rows)} items)')

        # Update image_path in DB
        print(f'\nUpdating DB image_path for {len(db_updates)} items...')
        for table, row_id, rel_path in db_updates:
            db.execute(text(f'UPDATE {table} SET image_path=:p WHERE id=:id'),
                       {'p': rel_path, 'id': row_id})
        db.commit()

    print(f'\nDone.')
    print(f'  Downloaded: {total_downloaded}')
    print(f'  Skipped:    {total_skipped}')
    print(f'  Failed:     {total_failed}')

    total_files = sum(len(fs) for _, _, fs in os.walk(LOCAL_BASE))
    print(f'  Files on disk: {total_files}')

if __name__ == '__main__':
    main()
