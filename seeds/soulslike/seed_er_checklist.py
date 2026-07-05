"""
Seed Elden Ring 100% checklist data from CasualHeroes/EldenRingChecklist fork.
Data by RainingChain and Fextralife community contributors.

Run: chwebsiteprj/bin/python3 seed_er_checklist.py
"""
import json, os, time, re, sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
import django; django.setup()

from app.db import get_db_session
from sqlalchemy import text

JSON_FILE = '/tmp/EldenRing.json'
GAME = 'elden_ring'
NOW = int(time.time())

def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')

def main():
    with open(JSON_FILE) as f:
        data = json.load(f)

    categories = data.get('categories', [])
    quests = data.get('quests', [])

    with get_db_session() as db:
        existing_cats = db.execute(text("SELECT COUNT(*) FROM sl_checklist_categories WHERE game='elden_ring'")).scalar()
        if existing_cats > 0:
            print(f'Already seeded ({existing_cats} categories). Delete first to re-seed.')
            return

        # ── Categories + Items ────────────────────────────────────────────────
        cat_ids = {}
        total_items = 0

        for sort_idx, cat in enumerate(categories):
            group = cat.get('group', 'Other')
            name = cat.get('name', '')
            items = cat.get('list', [])

            db.execute(text("""
                INSERT INTO sl_checklist_categories (game, group_name, name, sort_order)
                VALUES (:g, :grp, :name, :sort)
            """), {'g': GAME, 'grp': group, 'name': name, 'sort': sort_idx})
            cat_id = db.execute(text('SELECT LAST_INSERT_ID()')).scalar()
            cat_ids[name] = cat_id

            for item_idx, item in enumerate(items):
                iname = item.get('name', '')
                if not iname:
                    continue

                maps = item.get('maps', [])
                location = ', '.join(maps) if maps else None

                drops = []
                if item.get('dropAllMaps'):
                    drops.extend(item['dropAllMaps'])
                if item.get('dropByMap'):
                    for entry in item['dropByMap']:
                        if isinstance(entry, list) and len(entry) > 1:
                            drops.extend(entry[1:])
                drops_json = json.dumps(list(set(drops))) if drops else None

                db.execute(text("""
                    INSERT INTO sl_checklist_items
                        (category_id, game, name, location, is_dlc, wiki_href, drops, sort_order)
                    VALUES (:cid, :g, :name, :loc, :dlc, :href, :drops, :sort)
                """), {
                    'cid': cat_id, 'g': GAME, 'name': iname,
                    'loc': location, 'dlc': 1 if item.get('dlc') else 0,
                    'href': item.get('href'), 'drops': drops_json,
                    'sort': item_idx,
                })
                total_items += 1

        db.commit()
        print(f'Categories: {len(categories)}, Items: {total_items}')

        # ── Quests ────────────────────────────────────────────────────────────
        quest_count = 0
        for idx, quest in enumerate(quests):
            name = quest.get('name', '')
            if not name:
                continue

            maps = quest.get('maps', [])
            start_loc = ', '.join(maps) if maps else None
            complete_within = quest.get('completeWithin')
            unique_items = quest.get('uniqueItems', [])
            conflicts = quest.get('conflicts', [])
            is_missable = 1 if conflicts else 0

            db.execute(text("""
                INSERT INTO sl_checklist_quests
                    (game, name, start_location, complete_within, is_missable,
                     unique_items, conflicts, sort_order)
                VALUES (:g, :name, :start, :complete, :miss, :items, :conf, :sort)
            """), {
                'g': GAME, 'name': name, 'start': start_loc,
                'complete': complete_within, 'miss': is_missable,
                'items': json.dumps(unique_items) if unique_items else None,
                'conf': json.dumps(conflicts) if conflicts else None,
                'sort': idx,
            })
            quest_count += 1

        db.commit()
        print(f'Quests: {quest_count}')

        # Summary
        print('\nFinal counts:')
        for table in ('sl_checklist_categories', 'sl_checklist_items', 'sl_checklist_quests'):
            c = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
            print(f'  {table}: {c}')

        # By group
        print('\nItems by group:')
        rows = db.execute(text("""
            SELECT c.group_name, COUNT(i.id)
            FROM sl_checklist_items i
            JOIN sl_checklist_categories c ON i.category_id = c.id
            WHERE i.game='elden_ring'
            GROUP BY c.group_name ORDER BY COUNT(i.id) DESC
        """)).fetchall()
        for r in rows:
            print(f'  {r[0]}: {r[1]}')

if __name__ == '__main__':
    main()
