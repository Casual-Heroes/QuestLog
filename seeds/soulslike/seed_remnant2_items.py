"""
Parse remnant2-toolkit TypeScript constants and seed all r2_* item tables.
Source files expected in /tmp/ (fetched from GitHub).

Run: chwebsiteprj/bin/python3 seed_remnant2_items.py
"""
import django, os, re, time, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
django.setup()

from app.db import get_db_session
from sqlalchemy import text

NOW = int(time.time())

# ── TypeScript block parser ──────────────────────────────────────────────────

def extract_blocks(ts_text):
    """Extract each { ... } top-level object from the array."""
    blocks = []
    depth = 0
    start = None
    for i, ch in enumerate(ts_text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append(ts_text[start:i+1])
                start = None
    return blocks


def get_str(block, key):
    """Extract a simple string value: key: 'value' or key: `value`"""
    m = re.search(r'\b' + key + r"""\s*:\s*[`'"]([^`'"]*)[`'"]""", block)
    return m.group(1).strip() if m else None


def get_num(block, key):
    """Extract a numeric value: key: 123 or key: -10"""
    m = re.search(r'\b' + key + r'\s*:\s*(-?\d+(?:\.\d+)?)', block)
    return float(m.group(1)) if m else None


def get_dlc(block):
    m = re.search(r'\bdlc\s*:\s*[\'"`]([\w\d]+)[\'"`]', block)
    return m.group(1) if m else 'base'


def get_location(block):
    loc_m = re.search(r'location\s*:\s*\{([^}]+)\}', block, re.DOTALL)
    if not loc_m:
        return None, None
    loc_block = loc_m.group(1)
    world_m = re.search(r'world\s*:\s*[`\'"]([^`\'"]+)[`\'"]', loc_block)
    world = world_m.group(1) if world_m else None
    dung_m = re.search(r'dungeon\s*:\s*(?:\[([^\]]+)\]|[`\'"]([^`\'"]+)[`\'"])', loc_block)
    if dung_m:
        if dung_m.group(1):
            dungeons = re.findall(r'[`\'"]([^`\'"]+)[`\'"]', dung_m.group(1))
            dungeon = ', '.join(dungeons)
        else:
            dungeon = dung_m.group(2)
    else:
        dungeon = None
    return world, dungeon


def get_tags(block):
    tags_m = re.search(r'tags\s*:\s*\[([^\]]+)\]', block, re.DOTALL)
    if not tags_m:
        return None
    tags = re.findall(r'[`\'"]([^`\'"]+)[`\'"]', tags_m.group(1))
    return ', '.join(tags) if tags else None


def get_linked_names(block, key):
    """Extract array of name strings from linkedItems.key: [{name:'X'},...]"""
    section_m = re.search(key + r'\s*:\s*\[([^\]]+)\]', block, re.DOTALL)
    if not section_m:
        return []
    return re.findall(r'name\s*:\s*[`\'"]([^`\'"]+)[`\'"]', section_m.group(1))


def get_linked_traits(block):
    """Extract [{name, amount}] from linkedItems.traits"""
    section_m = re.search(r'traits\s*:\s*\[([^\]]+(?:\{[^}]*\}[^\]]*)*)\]', block, re.DOTALL)
    if not section_m:
        return []
    results = []
    for entry in re.finditer(r'\{([^}]+)\}', section_m.group(1)):
        name_m = re.search(r'name\s*:\s*[`\'"]([^`\'"]+)[`\'"]', entry.group(1))
        amt_m  = re.search(r'amount\s*:\s*(\d+)', entry.group(1))
        if name_m:
            results.append({'name': name_m.group(1), 'amount': int(amt_m.group(1)) if amt_m else 1})
    return results


def get_linked_mod(block):
    mod_m = re.search(r'mod\s*:\s*\{[^}]*name\s*:\s*[`\'"]([^`\'"]+)[`\'"]', block)
    return mod_m.group(1) if mod_m else None


def get_linked_set(block):
    set_m = re.search(r'set\s*:\s*\{[^}]*name\s*:\s*[`\'"]([^`\'"]+)[`\'"]', block)
    return set_m.group(1) if set_m else None


def slugify(name, suffix=None):
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    return f'{base}-{suffix}' if suffix else base


# ── Loaders ──────────────────────────────────────────────────────────────────

def load_archetypes():
    with open('/tmp/archetype-items.ts') as f:
        raw = f.read()
    items = []
    for block in extract_blocks(raw):
        name = get_str(block, 'name')
        if not name:
            continue
        world, dungeon = get_location(block)
        items.append({
            'name': name,
            'slug': slugify(name),
            'dlc': get_dlc(block),
            'image_path': get_str(block, 'imagePath'),
            'save_slug': get_str(block, 'saveFileSlug'),
            'wiki_url': None,
            'world': world,
            'dungeon': dungeon,
            'skills': get_linked_names(block, 'skills'),
            'perks': get_linked_names(block, 'perks'),
            'traits': get_linked_traits(block),
        })
    return items


def load_weapons():
    with open('/tmp/weapon-items.ts') as f:
        raw = f.read()
    items = []
    for block in extract_blocks(raw):
        name = get_str(block, 'name')
        if not name:
            continue
        world, dungeon = get_location(block)
        items.append({
            'name': name,
            'slug': slugify(name),
            'weapon_type': get_str(block, 'type') or 'unknown',
            'dlc': get_dlc(block),
            'image_path': get_str(block, 'imagePath'),
            'save_slug': get_str(block, 'saveFileSlug'),
            'damage': get_num(block, 'damage'),
            'rps': get_num(block, 'rps'),
            'magazine': get_num(block, 'magazine'),
            'accuracy': get_num(block, 'accuracy'),
            'ideal': get_num(block, 'ideal'),
            'falloff': get_num(block, 'falloff'),
            'ammo': get_num(block, 'ammo'),
            'crit': get_num(block, 'crit'),
            'weakspot': get_num(block, 'weakspot'),
            'stagger': get_num(block, 'stagger'),
            'world': world,
            'dungeon': dungeon,
            'linked_mod': get_linked_mod(block),
        })
    return items


def load_mods():
    with open('/tmp/mod-items.ts') as f:
        raw = f.read()
    items = []
    for block in extract_blocks(raw):
        name = get_str(block, 'name')
        if not name:
            continue
        world, dungeon = get_location(block)
        items.append({
            'name': name,
            'slug': slugify(name),
            'dlc': get_dlc(block),
            'image_path': get_str(block, 'imagePath'),
            'save_slug': get_str(block, 'saveFileSlug'),
            'world': world,
            'dungeon': dungeon,
        })
    return items


def load_rings():
    with open('/tmp/ring-items.ts') as f:
        raw = f.read()
    items = []
    for block in extract_blocks(raw):
        name = get_str(block, 'name')
        if not name:
            continue
        world, dungeon = get_location(block)
        items.append({
            'name': name,
            'slug': slugify(name),
            'dlc': get_dlc(block),
            'image_path': get_str(block, 'imagePath'),
            'save_slug': get_str(block, 'saveFileSlug'),
            'tags': get_tags(block),
            'world': world,
            'dungeon': dungeon,
        })
    return items


def load_amulets():
    with open('/tmp/amulet-items.ts') as f:
        raw = f.read()
    items = []
    for block in extract_blocks(raw):
        name = get_str(block, 'name')
        if not name:
            continue
        world, dungeon = get_location(block)
        items.append({
            'name': name,
            'slug': slugify(name),
            'dlc': get_dlc(block),
            'image_path': get_str(block, 'imagePath'),
            'save_slug': get_str(block, 'saveFileSlug'),
            'tags': get_tags(block),
            'world': world,
            'dungeon': dungeon,
        })
    return items


def load_traits():
    with open('/tmp/trait-items.ts') as f:
        raw = f.read()
    items = []
    for block in extract_blocks(raw):
        name = get_str(block, 'name')
        if not name:
            continue
        world, _ = get_location(block)
        # linked archetype
        arch_m = re.search(r'archetype\s*:\s*\{[^}]*name\s*:\s*[`\'"]([^`\'"]+)[`\'"]', block)
        items.append({
            'name': name,
            'slug': slugify(name),
            'dlc': get_dlc(block),
            'image_path': get_str(block, 'imagePath'),
            'save_slug': get_str(block, 'saveFileSlug'),
            'world': world,
            'linked_archetype': arch_m.group(1) if arch_m else None,
        })
    return items


def load_skills():
    with open('/tmp/skill-items.ts') as f:
        raw = f.read()
    items = []
    for block in extract_blocks(raw):
        name = get_str(block, 'name')
        if not name:
            continue
        arch_m = re.search(r'archetype\s*:\s*\{[^}]*name\s*:\s*[`\'"]([^`\'"]+)[`\'"]', block)
        items.append({
            'name': name,
            'slug': slugify(name),
            'dlc': get_dlc(block),
            'image_path': get_str(block, 'imagePath'),
            'save_slug': get_str(block, 'saveFileSlug'),
            'linked_archetype': arch_m.group(1) if arch_m else None,
            'cooldown': get_num(block, 'cooldown'),
        })
    return items


def load_armor():
    with open('/tmp/armor-items.ts') as f:
        raw = f.read()
    items = []
    for block in extract_blocks(raw):
        name = get_str(block, 'name')
        if not name:
            continue
        cat_m = re.search(r'category\s*:\s*[`\'"](\w+)[`\'"]', block)
        slot = cat_m.group(1) if cat_m else 'helm'
        items.append({
            'name': name,
            'slug': slugify(name),
            'slot': slot,
            'dlc': get_dlc(block),
            'image_path': get_str(block, 'imagePath'),
            'save_slug': get_str(block, 'saveFileSlug'),
            'armor_value': get_num(block, 'armor'),
            'weight': get_num(block, 'weight'),
            'set_name': get_linked_set(block),
        })
    return items


# ── Seeder ───────────────────────────────────────────────────────────────────

def seed_all():
    print('Parsing TypeScript files...')
    archetypes = load_archetypes()
    weapons    = load_weapons()
    mods       = load_mods()
    rings      = load_rings()
    amulets    = load_amulets()
    traits     = load_traits()
    skills     = load_skills()
    armor      = load_armor()

    print(f'  Archetypes: {len(archetypes)}')
    print(f'  Weapons:    {len(weapons)}')
    print(f'  Mods:       {len(mods)}')
    print(f'  Rings:      {len(rings)}')
    print(f'  Amulets:    {len(amulets)}')
    print(f'  Traits:     {len(traits)}')
    print(f'  Skills:     {len(skills)}')
    print(f'  Armor:      {len(armor)}')

    with get_db_session() as db:
        # Check if already seeded
        existing = db.execute(text('SELECT COUNT(*) FROM r2_archetypes')).scalar()
        if existing > 0:
            print(f'WARNING: {existing} archetypes already exist. Delete first to re-seed.')
            return

        # 1. Mods first (weapons reference them)
        # De-dupe slugs using save_slug suffix when names collide
        seen_slugs = {}
        for m in mods:
            base_slug = m['slug']
            if base_slug in seen_slugs:
                # Use save_slug suffix to disambiguate
                save_part = re.sub(r'[^a-z0-9]+', '-', (m['save_slug'] or '').lower()).strip('-')[-12:]
                m['slug'] = f'{base_slug}-{save_part}' if save_part else f'{base_slug}-2'
            seen_slugs[m['slug']] = True

        mod_name_to_id = {}
        for m in mods:
            db.execute(text("""
                INSERT INTO r2_mods (slug, name, dlc, image_path, save_slug, world, dungeon, created_at)
                VALUES (:slug, :name, :dlc, :img, :save, :world, :dungeon, :now)
            """), {'slug': m['slug'], 'name': m['name'], 'dlc': m['dlc'],
                   'img': m['image_path'], 'save': m['save_slug'],
                   'world': m['world'], 'dungeon': m['dungeon'], 'now': NOW})
            row_id = db.execute(text('SELECT LAST_INSERT_ID()')).scalar()
            # Map by name - last one wins for dupes (fine since weapon links by name)
            mod_name_to_id[m['name']] = row_id
        db.commit()
        print(f'  Seeded {len(mods)} mods')

        # 2. Weapons
        for w in weapons:
            mod_id = mod_name_to_id.get(w['linked_mod']) if w['linked_mod'] else None
            db.execute(text("""
                INSERT INTO r2_weapons
                    (slug, name, weapon_type, damage, rps, magazine, accuracy,
                     ideal_range, falloff_range, max_ammo, crit_chance, weakspot_bonus,
                     stagger, dlc, world, dungeon, image_path, save_slug, linked_mod_id, created_at)
                VALUES
                    (:slug, :name, :wt, :dmg, :rps, :mag, :acc,
                     :ideal, :falloff, :ammo, :crit, :weakspot,
                     :stagger, :dlc, :world, :dungeon, :img, :save, :mod_id, :now)
            """), {
                'slug': w['slug'], 'name': w['name'], 'wt': w['weapon_type'],
                'dmg': w['damage'], 'rps': w['rps'], 'mag': w['magazine'],
                'acc': w['accuracy'], 'ideal': w['ideal'], 'falloff': w['falloff'],
                'ammo': w['ammo'], 'crit': w['crit'], 'weakspot': w['weakspot'],
                'stagger': w['stagger'], 'dlc': w['dlc'],
                'world': w['world'], 'dungeon': w['dungeon'],
                'img': w['image_path'], 'save': w['save_slug'],
                'mod_id': mod_id, 'now': NOW,
            })
        db.commit()
        print(f'  Seeded {len(weapons)} weapons')

        # 3. Archetypes
        archetype_name_to_id = {}
        for a in archetypes:
            db.execute(text("""
                INSERT INTO r2_archetypes (slug, name, dlc, image_path, save_slug, created_at)
                VALUES (:slug, :name, :dlc, :img, :save, :now)
            """), {'slug': a['slug'], 'name': a['name'], 'dlc': a['dlc'],
                   'img': a['image_path'], 'save': a['save_slug'], 'now': NOW})
            archetype_name_to_id[a['name']] = db.execute(text('SELECT LAST_INSERT_ID()')).scalar()
        db.commit()
        print(f'  Seeded {len(archetypes)} archetypes')

        # 4. Skills (linked to archetypes by name from archetype file)
        skill_insert_count = 0
        for a in archetypes:
            arch_id = archetype_name_to_id.get(a['name'])
            for skill_name in a['skills']:
                slug = slugify(skill_name)
                try:
                    db.execute(text("""
                        INSERT IGNORE INTO r2_skills (slug, name, archetype_id, dlc, created_at)
                        VALUES (:slug, :name, :arch_id, :dlc, :now)
                    """), {'slug': slug, 'name': skill_name, 'arch_id': arch_id,
                           'dlc': a['dlc'], 'now': NOW})
                    skill_insert_count += 1
                except Exception:
                    pass
        db.commit()

        # skill-items.ts parser picks up archetype names from linkedItems refs - skip it,
        # all skills already inserted from archetype linkedItems above.
        db.commit()
        total_skills = db.execute(text('SELECT COUNT(*) FROM r2_skills')).scalar()
        print(f'  Seeded {total_skills} skills')

        # 5. Perks (from archetype linkedItems.perks)
        for a in archetypes:
            arch_id = archetype_name_to_id.get(a['name'])
            for perk_name in a['perks']:
                slug = slugify(perk_name)
                db.execute(text("""
                    INSERT IGNORE INTO r2_perks (slug, name, archetype_id, dlc, created_at)
                    VALUES (:slug, :name, :arch_id, :dlc, :now)
                """), {'slug': slug, 'name': perk_name, 'arch_id': arch_id,
                       'dlc': a['dlc'], 'now': NOW})
        db.commit()
        total_perks = db.execute(text('SELECT COUNT(*) FROM r2_perks')).scalar()
        print(f'  Seeded {total_perks} perks')

        # 6. Traits
        for t in traits:
            arch_id = archetype_name_to_id.get(t['linked_archetype']) if t['linked_archetype'] else None
            db.execute(text("""
                INSERT IGNORE INTO r2_traits
                    (slug, name, dlc, image_path, save_slug, linked_archetype_id, created_at)
                VALUES (:slug, :name, :dlc, :img, :save, :arch_id, :now)
            """), {'slug': t['slug'], 'name': t['name'], 'dlc': t['dlc'],
                   'img': t['image_path'], 'save': t['save_slug'],
                   'arch_id': arch_id, 'now': NOW})
        db.commit()
        print(f'  Seeded {len(traits)} traits')

        # 7. Rings
        for r in rings:
            db.execute(text("""
                INSERT IGNORE INTO r2_rings
                    (slug, name, dlc, image_path, save_slug, tags, world, dungeon, created_at)
                VALUES (:slug, :name, :dlc, :img, :save, :tags, :world, :dungeon, :now)
            """), {'slug': r['slug'], 'name': r['name'], 'dlc': r['dlc'],
                   'img': r['image_path'], 'save': r['save_slug'],
                   'tags': r['tags'], 'world': r['world'], 'dungeon': r['dungeon'], 'now': NOW})
        db.commit()
        print(f'  Seeded {len(rings)} rings')

        # 8. Amulets
        for a in amulets:
            db.execute(text("""
                INSERT IGNORE INTO r2_amulets
                    (slug, name, dlc, image_path, save_slug, tags, world, dungeon, created_at)
                VALUES (:slug, :name, :dlc, :img, :save, :tags, :world, :dungeon, :now)
            """), {'slug': a['slug'], 'name': a['name'], 'dlc': a['dlc'],
                   'img': a['image_path'], 'save': a['save_slug'],
                   'tags': a['tags'], 'world': a['world'], 'dungeon': a['dungeon'], 'now': NOW})
        db.commit()
        print(f'  Seeded {len(amulets)} amulets')

        # 9. Armor
        for ar in armor:
            db.execute(text("""
                INSERT IGNORE INTO r2_armor
                    (slug, name, slot, armor_value, weight, set_name, dlc, image_path, save_slug, created_at)
                VALUES (:slug, :name, :slot, :armor, :weight, :set_name, :dlc, :img, :save, :now)
            """), {'slug': ar['slug'], 'name': ar['name'], 'slot': ar['slot'],
                   'armor': ar['armor_value'], 'weight': ar['weight'],
                   'set_name': ar['set_name'], 'dlc': ar['dlc'],
                   'img': ar['image_path'], 'save': ar['save_slug'], 'now': NOW})
        db.commit()
        print(f'  Seeded {len(armor)} armor pieces')

    print('\nDone. Final counts:')
    with get_db_session() as db:
        for table in ('r2_archetypes', 'r2_skills', 'r2_perks', 'r2_traits',
                      'r2_weapons', 'r2_mods', 'r2_rings', 'r2_amulets', 'r2_armor', 'r2_bosses'):
            c = db.execute(text(f'SELECT COUNT(*) FROM {table}')).scalar()
            print(f'  {table}: {c}')


if __name__ == '__main__':
    seed_all()
