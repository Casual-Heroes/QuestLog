"""
Remnant 2 views - Hub, Builder, Runs, Run Detail, and API endpoints.
Lives under /soulslike/r2/
Mirrors existing SoulsLike infrastructure exactly - same auth, same patterns.
"""
import json
import secrets
import time

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django_ratelimit.decorators import ratelimit

from app.db import get_db_session
from sqlalchemy import text

from .helpers import sanitize_text, award_xp, web_login_required, add_web_user_context, require_verified
from .views_pages import safe_int


# ── Hub ──────────────────────────────────────────────────────────────────────

@add_web_user_context
def r2_hub(request):
    with get_db_session() as db:
        try:
            total_runs   = db.execute(text('SELECT COUNT(*) FROM r2_runs')).scalar() or 0
            active_runs  = db.execute(text('SELECT COUNT(*) FROM r2_runs WHERE is_active=1')).scalar() or 0
            total_deaths = db.execute(text('SELECT COALESCE(SUM(death_count),0) FROM r2_runs')).scalar() or 0
            total_bosses = db.execute(text('SELECT COALESCE(SUM(bosses_killed),0) FROM r2_runs')).scalar() or 0
            total_items  = db.execute(text('SELECT COALESCE(SUM(items_found),0) FROM r2_runs')).scalar() or 0
        except Exception:
            total_runs = active_runs = total_deaths = total_bosses = total_items = 0

        # Recent public runs
        recent_runs = []
        try:
            rows = db.execute(text("""
                SELECT r.token, r.name, r.run_type, r.is_hardcore, r.death_count,
                       r.bosses_killed, r.items_found, r.created_at, r.is_active,
                       u.username, u.avatar_url
                FROM r2_runs r
                JOIN web_users u ON r.user_id = u.id
                WHERE r.is_public = 1
                ORDER BY r.created_at DESC LIMIT 6
            """)).fetchall()
            for row in rows:
                recent_runs.append({
                    'token': row[0], 'name': row[1], 'run_type': row[2],
                    'is_hardcore': row[3], 'deaths': row[4],
                    'bosses_killed': row[5], 'items_found': row[6],
                    'created_at': row[7], 'is_active': row[8],
                    'username': row[9], 'avatar': row[10],
                })
        except Exception:
            pass

    return render(request, 'questlog_web/r2_hub.html', {
        'web_user': request.web_user,
        'active_page': 'questlog_web_r2_hub',
        'stats_list': [
            ('Runs',    total_runs,    'text-purple-400'),
            ('Active',  active_runs,   'text-green-400'),
            ('Deaths',  total_deaths,  'text-red-400'),
            ('Bosses',  total_bosses,  'text-amber-400'),
            ('Items',   total_items,   'text-cyan-400'),
        ],
        'recent_runs': recent_runs,
    })


# ── Builder ───────────────────────────────────────────────────────────────────

@add_web_user_context
def r2_builder(request):
    """Build planner - archetypes, gear, traits, weapons."""
    share_token = request.GET.get('load', '')[:32]
    load_build = None
    if share_token:
        with get_db_session() as db:
            row = db.execute(text(
                'SELECT id, name, description, is_public, primary_archetype_id, '
                'secondary_archetype_id, primary_skill_id, secondary_skill_id, '
                'amulet_id, trait_points_json, playstyle, notes, user_id '
                'FROM r2_builds WHERE share_token=:tok'
            ), {'tok': share_token}).fetchone()
            if row:
                load_build = dict(zip([
                    'id', 'name', 'description', 'is_public',
                    'primary_archetype_id', 'secondary_archetype_id',
                    'primary_skill_id', 'secondary_skill_id',
                    'amulet_id', 'trait_points_json', 'playstyle', 'notes', 'user_id'
                ], row))

    return render(request, 'questlog_web/r2_builder.html', {
        'web_user': request.web_user,
        'load_build': json.dumps(load_build) if load_build else 'null',
        'share_token': share_token,
        'active_page': 'questlog_web_r2_builder',
        'weapon_slots': [
            ('main',      'fas fa-crosshairs', 'Long Gun'),
            ('secondary', 'fas fa-gun',         'Hand Gun'),
            ('melee',     'fas fa-khanda',       'Melee'),
        ],
    })


# ── My Builds ─────────────────────────────────────────────────────────────────

@web_login_required
@add_web_user_context
def r2_my_builds(request):
    uid = request.web_user.id
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT b.id, b.name, b.share_token, b.is_public, b.playstyle,
                   b.created_at, b.updated_at,
                   a1.name as primary_arch, a2.name as secondary_arch
            FROM r2_builds b
            LEFT JOIN r2_archetypes a1 ON b.primary_archetype_id = a1.id
            LEFT JOIN r2_archetypes a2 ON b.secondary_archetype_id = a2.id
            WHERE b.user_id = :uid
            ORDER BY b.updated_at DESC LIMIT 50
        """), {'uid': uid}).fetchall()

        builds = []
        for r in rows:
            builds.append({
                'id': r[0], 'name': r[1], 'token': r[2], 'is_public': r[3],
                'playstyle': r[4], 'created_at': r[5], 'updated_at': r[6],
                'primary_arch': r[7] or '', 'secondary_arch': r[8] or '',
            })

    return render(request, 'questlog_web/r2_my_builds.html', {
        'web_user': request.web_user,
        'active_page': 'questlog_web_r2_my_builds',
        'builds': builds,
    })


# ── Runs list ─────────────────────────────────────────────────────────────────

@web_login_required
@add_web_user_context
def r2_runs(request):
    uid = request.web_user.id
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT r.token, r.name, r.run_type, r.is_hardcore, r.is_active,
                   r.is_public, r.death_count, r.bosses_killed, r.items_found,
                   r.created_at, r.completed_at,
                   b.name as build_name,
                   GROUP_CONCAT(z.world ORDER BY z.world SEPARATOR ', ') as zones
            FROM r2_runs r
            LEFT JOIN r2_builds b ON r.build_id = b.id
            LEFT JOIN r2_run_zones z ON z.run_id = r.id
            WHERE r.user_id = :uid
            GROUP BY r.id
            ORDER BY r.created_at DESC LIMIT 50
        """), {'uid': uid}).fetchall()

        runs = []
        for row in rows:
            runs.append({
                'token': row[0], 'name': row[1], 'run_type': row[2],
                'is_hardcore': row[3], 'is_active': row[4], 'is_public': row[5],
                'deaths': row[6], 'bosses_killed': row[7], 'items_found': row[8],
                'created_at': row[9], 'completed_at': row[10],
                'build_name': row[11] or '', 'zones': row[12] or '',
            })

        # Previous completed runs available for import
        completed = db.execute(text("""
            SELECT token, name, completed_at, bosses_killed, items_found
            FROM r2_runs
            WHERE user_id = :uid AND is_active = 0
            ORDER BY completed_at DESC LIMIT 20
        """), {'uid': uid}).fetchall()

        previous_runs = [
            {'token': r[0], 'name': r[1], 'completed_at': r[2],
             'bosses_killed': r[3], 'items_found': r[4]}
            for r in completed
        ]

    return render(request, 'questlog_web/r2_runs.html', {
        'web_user': request.web_user,
        'active_page': 'questlog_web_r2_runs',
        'runs': runs,
        'previous_runs': previous_runs,
        'worlds': [
            {'name': "N'Erud"},
            {'name': 'Yaesha'},
            {'name': 'Losomn'},
            {'name': 'Root Earth'},
            {'name': 'Labyrinth'},
        ],
    })


# ── Run Detail ────────────────────────────────────────────────────────────────

@add_web_user_context
def r2_run_detail(request, token):
    uid = request.web_user.id if request.web_user else None
    with get_db_session() as db:
        run = db.execute(text("""
            SELECT r.id, r.token, r.name, r.run_type, r.is_hardcore, r.is_active,
                   r.is_public, r.death_count, r.session_death_count,
                   r.bosses_killed, r.items_found, r.created_at, r.completed_at,
                   r.user_id, r.build_id,
                   u.username, u.avatar_url,
                   b.name as build_name
            FROM r2_runs r
            JOIN web_users u ON r.user_id = u.id
            LEFT JOIN r2_builds b ON r.build_id = b.id
            WHERE r.token = :tok
        """), {'tok': token}).fetchone()

        if not run:
            from django.http import Http404
            raise Http404

        is_owner = uid and run[13] == uid
        if not run[6] and not is_owner:
            from django.http import Http404
            raise Http404

        run_id = run[0]

        # Zones for this run
        zones = [r[0] for r in db.execute(text(
            'SELECT world FROM r2_run_zones WHERE run_id=:rid ORDER BY world'
        ), {'rid': run_id}).fetchall()]

        # Bosses for this run (filtered by spawned=1 OR all if owner)
        boss_rows = db.execute(text("""
            SELECT rb.boss_id, rb.spawned, rb.killed, rb.killed_at,
                   b.name, b.boss_type, b.world, b.zone, b.drop_notes, b.dlc
            FROM r2_run_bosses rb
            JOIN r2_bosses b ON rb.boss_id = b.id
            WHERE rb.run_id = :rid
            ORDER BY b.world, b.boss_type, b.name
        """), {'rid': run_id}).fetchall()

        # Reference pool (all bosses for this run's zones, not yet added)
        zone_filter = zones if zones else []
        if zone_filter:
            placeholders = ','.join([f':z{i}' for i in range(len(zone_filter))])
            params = {'rid': run_id}
            params.update({f'z{i}': z for i, z in enumerate(zone_filter)})
            available_bosses = db.execute(text(f"""
                SELECT b.id, b.name, b.boss_type, b.world, b.zone, b.drop_notes, b.dlc
                FROM r2_bosses b
                WHERE b.world IN ({placeholders})
                  AND b.id NOT IN (
                      SELECT boss_id FROM r2_run_bosses WHERE run_id = :rid
                  )
                ORDER BY b.world, b.boss_type, b.name
            """), params).fetchall()
        else:
            available_bosses = db.execute(text("""
                SELECT b.id, b.name, b.boss_type, b.world, b.zone, b.drop_notes, b.dlc
                FROM r2_bosses b
                WHERE b.id NOT IN (
                    SELECT boss_id FROM r2_run_bosses WHERE run_id = :rid
                )
                ORDER BY b.world, b.boss_type, b.name
            """), {'rid': run_id}).fetchall()

        # Items found this run
        item_rows = db.execute(text("""
            SELECT ri.item_type, ri.item_id, ri.found, ri.found_at
            FROM r2_run_items ri
            WHERE ri.run_id = :rid
            ORDER BY ri.item_type, ri.item_id
        """), {'rid': run_id}).fetchall()

    run_data = {
        'id': run[0], 'token': run[1], 'name': run[2], 'run_type': run[3],
        'is_hardcore': run[4], 'is_active': run[5], 'is_public': run[6],
        'deaths': run[7], 'session_deaths': run[8],
        'bosses_killed': run[9], 'items_found': run[10],
        'created_at': run[11], 'completed_at': run[12],
        'user_id': run[13], 'build_id': run[14],
        'username': run[15], 'avatar': run[16], 'build_name': run[17] or '',
    }

    bosses = [{'boss_id': r[0], 'spawned': r[1], 'killed': r[2], 'killed_at': r[3],
               'name': r[4], 'boss_type': r[5], 'world': r[6], 'zone': r[7],
               'drops': r[8], 'dlc': r[9]} for r in boss_rows]

    ref_bosses = [{'id': r[0], 'name': r[1], 'boss_type': r[2], 'world': r[3],
                   'zone': r[4], 'drops': r[5], 'dlc': r[6]} for r in available_bosses]

    items = [{'type': r[0], 'item_id': r[1], 'found': r[2], 'found_at': r[3]}
             for r in item_rows]

    return render(request, 'questlog_web/r2_run_detail.html', {
        'web_user': request.web_user,
        'active_page': 'questlog_web_r2_run_detail',
        'run': run_data,
        'is_owner': is_owner,
        'zones': zones,
        'bosses': bosses,
        'ref_bosses': ref_bosses,
        'items': items,
        'zones_json': json.dumps(zones),
        'bosses_json': json.dumps(bosses),
        'items_json': json.dumps(items),
    })


# ── API: Reference data ───────────────────────────────────────────────────────

def api_r2_archetypes(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, description, dlc, image_path FROM r2_archetypes ORDER BY name'
        )).fetchall()
        skills = db.execute(text(
            'SELECT id, name, archetype_id, dlc FROM r2_skills ORDER BY archetype_id, id'
        )).fetchall()
        perks = db.execute(text(
            'SELECT id, name, archetype_id, perk_type, dlc FROM r2_perks ORDER BY archetype_id, id'
        )).fetchall()
        # Get linked trait name per archetype
        traits = db.execute(text(
            'SELECT linked_archetype_id, name FROM r2_traits WHERE linked_archetype_id IS NOT NULL'
        )).fetchall()

    skill_map = {}
    for s in skills:
        skill_map.setdefault(s[2], []).append({'id': s[0], 'name': s[1], 'dlc': s[3]})
    perk_map = {}
    for p in perks:
        perk_map.setdefault(p[2], []).append({'id': p[0], 'name': p[1], 'perk_type': p[3], 'dlc': p[4]})
    trait_map = {t[0]: t[1] for t in traits}

    return JsonResponse({'archetypes': [
        {'id': r[0], 'name': r[1], 'description': r[2], 'dlc': r[3],
         'image_path': r[4],
         'trait_name': trait_map.get(r[0], ''),
         'skills': skill_map.get(r[0], []),
         'perks': perk_map.get(r[0], [])}
        for r in rows
    ]})


def api_r2_weapons(request):
    wtype = request.GET.get('type', '')[:20]
    with get_db_session() as db:
        q = 'SELECT id, name, weapon_type, damage, crit_chance, weakspot_bonus, stagger, dlc, image_path, linked_mod_id FROM r2_weapons'
        params = {}
        if wtype in ('melee', 'long gun', 'hand gun'):
            q += ' WHERE weapon_type=:t'
            params['t'] = wtype
        q += ' ORDER BY name'
        rows = db.execute(text(q), params).fetchall()
    return JsonResponse({'weapons': [
        {'id': r[0], 'name': r[1], 'type': r[2], 'damage': r[3],
         'crit': r[4], 'weakspot': r[5], 'stagger': r[6],
         'dlc': r[7], 'image_path': r[8], 'mod_id': r[9]}
        for r in rows
    ]})


def api_r2_mods(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, description, dlc, image_path FROM r2_mods ORDER BY name'
        )).fetchall()
    return JsonResponse({'mods': [
        {'id': r[0], 'name': r[1], 'description': r[2], 'dlc': r[3], 'image_path': r[4]}
        for r in rows
    ]})


def api_r2_mutators(request):
    mtype = request.GET.get('type', '')[:10]
    with get_db_session() as db:
        q = 'SELECT id, name, mutator_type, description, dlc, image_path FROM r2_mutators'
        params = {}
        if mtype in ('ranged', 'melee'):
            q += ' WHERE mutator_type=:t'
            params['t'] = mtype
        q += ' ORDER BY name'
        rows = db.execute(text(q), params).fetchall()
    return JsonResponse({'mutators': [
        {'id': r[0], 'name': r[1], 'type': r[2], 'description': r[3], 'dlc': r[4], 'image_path': r[5]}
        for r in rows
    ]})


def api_r2_armor(request):
    slot = request.GET.get('slot', '')[:10]
    with get_db_session() as db:
        q = 'SELECT id, name, slot, armor_value, weight, set_name, dlc, image_path FROM r2_armor'
        params = {}
        if slot in ('helm', 'torso', 'legs', 'gloves'):
            q += ' WHERE slot=:s'
            params['s'] = slot
        q += ' ORDER BY set_name, name'
        rows = db.execute(text(q), params).fetchall()
    return JsonResponse({'armor': [
        {'id': r[0], 'name': r[1], 'slot': r[2], 'armor': r[3],
         'weight': float(r[4]) if r[4] else 0, 'set_name': r[5],
         'dlc': r[6], 'image_path': r[7],
         'description': f"Armor: {r[3]}  |  Weight: {float(r[4]) if r[4] else 0}" + (f"  |  Set: {r[5]}" if r[5] else '')}
        for r in rows
    ]})


def api_r2_rings(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, description, tags, dlc, image_path FROM r2_rings ORDER BY name'
        )).fetchall()
    return JsonResponse({'rings': [
        {'id': r[0], 'name': r[1], 'description': r[2], 'tags': r[3], 'dlc': r[4], 'image_path': r[5]}
        for r in rows
    ]})


def api_r2_amulets(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, description, tags, dlc, image_path FROM r2_amulets ORDER BY name'
        )).fetchall()
    return JsonResponse({'amulets': [
        {'id': r[0], 'name': r[1], 'description': r[2], 'tags': r[3], 'dlc': r[4], 'image_path': r[5]}
        for r in rows
    ]})


def api_r2_relics(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, description, dlc, image_path FROM r2_relics ORDER BY name'
        )).fetchall()
    return JsonResponse({'relics': [
        {'id': r[0], 'name': r[1], 'description': r[2], 'dlc': r[3], 'image_path': r[4]}
        for r in rows
    ]})


def api_r2_relic_fragments(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, fragment_type, effect_value, description, dlc, image_path '
            'FROM r2_relic_fragments ORDER BY fragment_type, name'
        )).fetchall()
        fusions = db.execute(text(
            'SELECT id, name, fragment1, fragment2, stat1, stat2, val1, val2 '
            'FROM r2_fusion_fragments ORDER BY name'
        )).fetchall()
    return JsonResponse({
        'fragments': [
            {'id': r[0], 'name': r[1], 'type': r[2], 'value': r[3],
             'description': r[4], 'dlc': r[5], 'image_path': r[6]}
            for r in rows
        ],
        'fusions': [
            {'id': r[0], 'name': r[1], 'fragment1': r[2], 'fragment2': r[3],
             'stat1': r[4], 'stat2': r[5], 'val1': r[6], 'val2': r[7]}
            for r in fusions
        ],
    })


def api_r2_traits(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, category, max_points, dlc, source, linked_archetype_id, image_path, description '
            'FROM r2_traits ORDER BY category, name'
        )).fetchall()
    return JsonResponse({'traits': [
        {'id': r[0], 'name': r[1], 'category': r[2], 'max_points': r[3],
         'dlc': r[4], 'source': r[5], 'archetype_id': r[6], 'image_path': r[7],
         'description': r[8]}
        for r in rows
    ]})


def api_r2_bosses(request):
    world = request.GET.get('world', '')[:64]
    btype = request.GET.get('type', '')[:20]
    with get_db_session() as db:
        q = 'SELECT id, name, boss_type, world, zone, is_optional, dlc, drop_notes FROM r2_bosses WHERE 1=1'
        params = {}
        if world:
            q += ' AND world=:w'
            params['w'] = world
        if btype in ('boss', 'world_boss', 'aberration'):
            q += ' AND boss_type=:t'
            params['t'] = btype
        q += ' ORDER BY world, boss_type, name'
        rows = db.execute(text(q), params).fetchall()
    return JsonResponse({'bosses': [
        {'id': r[0], 'name': r[1], 'type': r[2], 'world': r[3], 'zone': r[4],
         'is_optional': r[5], 'dlc': r[6], 'drops': r[7]}
        for r in rows
    ]})


# ── API: Build save/load ──────────────────────────────────────────────────────

@web_login_required
def api_r2_build_save(request):
    """POST - save or update a build."""
    gate = require_verified(request);
    if gate: return gate
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    uid   = request.web_user.id
    now   = int(time.time())
    name  = sanitize_text(str(data.get('name', 'My Build'))[:200])
    desc  = sanitize_text(str(data.get('description', ''))[:2000])
    is_public = 1 if data.get('is_public') else 0
    playstyle = sanitize_text(str(data.get('playstyle', ''))[:100])
    notes = sanitize_text(str(data.get('notes', ''))[:2000])

    primary_arch    = safe_int(data.get('primary_archetype_id'), None)
    secondary_arch  = safe_int(data.get('secondary_archetype_id'), None)
    primary_skill   = safe_int(data.get('primary_skill_id'), None)
    secondary_skill = safe_int(data.get('secondary_skill_id'), None)
    amulet_id       = safe_int(data.get('amulet_id'), None)

    trait_points = data.get('trait_points', {})
    if not isinstance(trait_points, dict):
        trait_points = {}
    trait_json = json.dumps(trait_points)

    weapons = data.get('weapons', [])
    rings   = data.get('rings', [])
    armor   = data.get('armor', [])

    build_id    = safe_int(data.get('build_id'), None)
    share_token = data.get('share_token', '')[:32]

    with get_db_session() as db:
        existing = None
        if build_id:
            existing = db.execute(text(
                'SELECT id FROM r2_builds WHERE id=:id AND user_id=:uid'
            ), {'id': build_id, 'uid': uid}).scalar()

        if existing:
            db.execute(text("""
                UPDATE r2_builds SET name=:name, description=:desc, is_public=:pub,
                    primary_archetype_id=:pa, secondary_archetype_id=:sa,
                    primary_skill_id=:ps, secondary_skill_id=:ss,
                    amulet_id=:am, trait_points_json=:tp, playstyle=:pl,
                    notes=:notes, updated_at=:now
                WHERE id=:id AND user_id=:uid
            """), {
                'name': name, 'desc': desc, 'pub': is_public,
                'pa': primary_arch, 'sa': secondary_arch,
                'ps': primary_skill, 'ss': secondary_skill,
                'am': amulet_id, 'tp': trait_json, 'pl': playstyle,
                'notes': notes, 'now': now, 'id': existing, 'uid': uid,
            })
            bid = existing
        else:
            token = secrets.token_urlsafe(16)
            db.execute(text("""
                INSERT INTO r2_builds
                    (user_id, name, description, share_token, is_public,
                     primary_archetype_id, secondary_archetype_id,
                     primary_skill_id, secondary_skill_id,
                     amulet_id, trait_points_json, playstyle, notes,
                     created_at, updated_at)
                VALUES (:uid, :name, :desc, :tok, :pub,
                        :pa, :sa, :ps, :ss, :am, :tp, :pl, :notes, :now, :now)
            """), {
                'uid': uid, 'name': name, 'desc': desc, 'tok': token,
                'pub': is_public, 'pa': primary_arch, 'sa': secondary_arch,
                'ps': primary_skill, 'ss': secondary_skill,
                'am': amulet_id, 'tp': trait_json, 'pl': playstyle,
                'notes': notes, 'now': now,
            })
            bid = db.execute(text('SELECT LAST_INSERT_ID()')).scalar()
            share_token = token
            award_xp(uid, 'sl_build_create', ref_id=bid)

        # Weapons
        db.execute(text('DELETE FROM r2_build_weapons WHERE build_id=:bid'), {'bid': bid})
        for w in weapons[:3]:
            slot      = str(w.get('slot', ''))[:16]
            weapon_id = safe_int(w.get('weapon_id'), None)
            mod_id    = safe_int(w.get('mod_id'), None)
            mutator_id= safe_int(w.get('mutator_id'), None)
            if slot in ('main', 'secondary', 'melee') and weapon_id:
                db.execute(text("""
                    INSERT INTO r2_build_weapons (build_id, slot, weapon_id, mod_id, mutator_id)
                    VALUES (:bid, :slot, :wid, :mid, :mut)
                """), {'bid': bid, 'slot': slot, 'wid': weapon_id, 'mid': mod_id, 'mut': mutator_id})

        # Rings
        db.execute(text('DELETE FROM r2_build_rings WHERE build_id=:bid'), {'bid': bid})
        for i, ring_id in enumerate(rings[:4]):
            if ring_id:
                db.execute(text(
                    'INSERT INTO r2_build_rings (build_id, slot, ring_id) VALUES (:bid, :slot, :rid)'
                ), {'bid': bid, 'slot': i + 1, 'rid': safe_int(ring_id, None)})

        # Armor
        db.execute(text('DELETE FROM r2_build_armor WHERE build_id=:bid'), {'bid': bid})
        for ar in armor[:4]:
            slot    = str(ar.get('slot', ''))[:16]
            armor_id= safe_int(ar.get('armor_id'), None)
            if slot in ('helm', 'torso', 'legs', 'gloves') and armor_id:
                db.execute(text(
                    'INSERT INTO r2_build_armor (build_id, slot, armor_id) VALUES (:bid, :slot, :aid)'
                ), {'bid': bid, 'slot': slot, 'aid': armor_id})

        db.commit()

    return JsonResponse({'ok': True, 'build_id': bid, 'share_token': share_token})


@web_login_required
def api_r2_build_delete(request, build_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    uid = request.web_user.id
    with get_db_session() as db:
        existing = db.execute(text(
            'SELECT id FROM r2_builds WHERE id=:id AND user_id=:uid'
        ), {'id': build_id, 'uid': uid}).scalar()
        if not existing:
            return JsonResponse({'error': 'Not found'}, status=404)
        db.execute(text('DELETE FROM r2_build_weapons WHERE build_id=:bid'), {'bid': build_id})
        db.execute(text('DELETE FROM r2_build_rings WHERE build_id=:bid'), {'bid': build_id})
        db.execute(text('DELETE FROM r2_build_armor WHERE build_id=:bid'), {'bid': build_id})
        db.execute(text('DELETE FROM r2_builds WHERE id=:id AND user_id=:uid'), {'id': build_id, 'uid': uid})
        db.commit()
    return JsonResponse({'ok': True})


@add_web_user_context
def api_r2_build_detail(request, share_token):
    with get_db_session() as db:
        row = db.execute(text("""
            SELECT b.id, b.name, b.description, b.is_public, b.share_token,
                   b.primary_archetype_id, b.secondary_archetype_id,
                   b.primary_skill_id, b.secondary_skill_id,
                   b.amulet_id, b.trait_points_json, b.playstyle, b.notes,
                   b.user_id, b.created_at, b.updated_at,
                   u.username
            FROM r2_builds b
            JOIN web_users u ON b.user_id = u.id
            WHERE b.share_token = :tok
        """), {'tok': share_token}).fetchone()

        if not row:
            return JsonResponse({'error': 'Not found'}, status=404)

        uid = request.web_user.id if request.web_user else None
        is_owner = uid and row[13] == uid
        if not row[3] and not is_owner:
            return JsonResponse({'error': 'Not found'}, status=404)

        bid = row[0]
        weapons = db.execute(text(
            'SELECT slot, weapon_id, mod_id, mutator_id FROM r2_build_weapons WHERE build_id=:bid'
        ), {'bid': bid}).fetchall()
        rings = db.execute(text(
            'SELECT slot, ring_id FROM r2_build_rings WHERE build_id=:bid ORDER BY slot'
        ), {'bid': bid}).fetchall()
        armor = db.execute(text(
            'SELECT slot, armor_id FROM r2_build_armor WHERE build_id=:bid'
        ), {'bid': bid}).fetchall()

    return JsonResponse({
        'ok': True,
        'build': {
            'id': row[0], 'name': row[1], 'description': row[2],
            'is_public': row[3], 'share_token': row[4],
            'primary_archetype_id': row[5], 'secondary_archetype_id': row[6],
            'primary_skill_id': row[7], 'secondary_skill_id': row[8],
            'amulet_id': row[9],
            'trait_points': json.loads(row[10]) if row[10] else {},
            'playstyle': row[11], 'notes': row[12],
            'user_id': row[13], 'username': row[16],
            'weapons': [{'slot': w[0], 'weapon_id': w[1], 'mod_id': w[2], 'mutator_id': w[3]} for w in weapons],
            'rings': [{'slot': r[0], 'ring_id': r[1]} for r in rings],
            'armor': [{'slot': a[0], 'armor_id': a[1]} for a in armor],
        },
        'is_owner': is_owner,
    })


# ── API: Run create ───────────────────────────────────────────────────────────

@web_login_required
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def api_r2_run_create(request):
    gate = require_verified(request);
    if gate: return gate
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    uid         = request.web_user.id
    now         = int(time.time())
    name        = sanitize_text(str(data.get('name', 'My Run'))[:200])
    run_type    = str(data.get('run_type', 'campaign'))[:16]
    is_hardcore = 1 if data.get('is_hardcore') else 0
    is_public   = 1 if data.get('is_public') else 0
    build_id    = safe_int(data.get('build_id'), None)
    zones       = data.get('zones', [])
    import_token= str(data.get('import_from', ''))[:32]

    if run_type not in ('campaign', 'adventure'):
        run_type = 'campaign'
    if not isinstance(zones, list):
        zones = []
    zones = [str(z)[:64] for z in zones[:6] if z]

    token = secrets.token_urlsafe(16)

    with get_db_session() as db:
        # Validate build ownership if provided
        if build_id:
            b = db.execute(text(
                'SELECT id FROM r2_builds WHERE id=:id AND user_id=:uid'
            ), {'id': build_id, 'uid': uid}).scalar()
            if not b:
                build_id = None

        db.execute(text("""
            INSERT INTO r2_runs
                (user_id, build_id, token, name, run_type, is_hardcore, is_public,
                 death_count, session_death_count, session_death_baseline,
                 bosses_killed, items_found, is_active, created_at)
            VALUES (:uid, :bid, :tok, :name, :rtype, :hc, :pub,
                    0, 0, 0, 0, 0, 1, :now)
        """), {
            'uid': uid, 'bid': build_id, 'tok': token, 'name': name,
            'rtype': run_type, 'hc': is_hardcore, 'pub': is_public, 'now': now,
        })
        run_id = db.execute(text('SELECT LAST_INSERT_ID()')).scalar()

        # Insert zones
        for world in zones:
            db.execute(text(
                'INSERT INTO r2_run_zones (run_id, world) VALUES (:rid, :w)'
            ), {'rid': run_id, 'w': world})

        # Import manifest from previous run if requested
        if import_token:
            prev_run = db.execute(text(
                'SELECT id FROM r2_runs WHERE token=:tok AND user_id=:uid AND is_active=0'
            ), {'tok': import_token, 'uid': uid}).fetchone()

            if prev_run:
                prev_id = prev_run[0]
                # Import found items from manifest
                manifest_rows = db.execute(text(
                    'SELECT item_type, item_id FROM r2_manifest WHERE user_id=:uid'
                ), {'uid': uid}).fetchall()

                for item_type, item_id in manifest_rows:
                    db.execute(text("""
                        INSERT IGNORE INTO r2_run_items
                            (run_id, item_type, item_id, found, found_at)
                        VALUES (:rid, :itype, :iid, 1, :now)
                    """), {'rid': run_id, 'itype': item_type, 'iid': item_id, 'now': now})

                # Import killed bosses from manifest
                manifest_bosses = db.execute(text(
                    'SELECT boss_id FROM r2_manifest_bosses WHERE user_id=:uid'
                ), {'uid': uid}).fetchall()

                for (boss_id,) in manifest_bosses:
                    db.execute(text("""
                        INSERT IGNORE INTO r2_run_bosses
                            (run_id, boss_id, spawned, killed, killed_at)
                        VALUES (:rid, :bid, 1, 1, :now)
                    """), {'rid': run_id, 'bid': boss_id, 'now': now})

        db.commit()

    return JsonResponse({
        'ok': True,
        'token': token,
        'run_url': f'/soulslike/r2/runs/{token}/',
    })


# ── API: Run actions (boss/item mark, death, end run) ─────────────────────────

def _get_run_owner(db, token, uid):
    """Return run row if uid owns it, else None."""
    return db.execute(text(
        'SELECT id, is_active, death_count, session_death_count, '
        'session_death_baseline, bosses_killed, items_found '
        'FROM r2_runs WHERE token=:tok AND user_id=:uid'
    ), {'tok': token, 'uid': uid}).fetchone()


@web_login_required
def api_r2_boss_mark(request, token):
    """POST - mark a boss as spawned and/or killed."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    uid     = request.web_user.id
    boss_id = safe_int(data.get('boss_id'), None)
    spawned = 1 if data.get('spawned') else 0
    killed  = 1 if data.get('killed') else 0

    if not boss_id:
        return JsonResponse({'error': 'boss_id required'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        run = _get_run_owner(db, token, uid)
        if not run:
            return JsonResponse({'error': 'Not found'}, status=404)
        if not run[1]:
            return JsonResponse({'error': 'Run not active'}, status=400)

        run_id = run[0]

        # Upsert boss entry
        existing = db.execute(text(
            'SELECT id, killed FROM r2_run_bosses WHERE run_id=:rid AND boss_id=:bid'
        ), {'rid': run_id, 'bid': boss_id}).fetchone()

        was_killed = existing[1] if existing else 0

        if existing:
            db.execute(text("""
                UPDATE r2_run_bosses SET spawned=:s, killed=:k,
                    killed_at=CASE WHEN :k=1 AND killed=0 THEN :now ELSE killed_at END
                WHERE run_id=:rid AND boss_id=:bid
            """), {'s': spawned, 'k': killed, 'now': now, 'rid': run_id, 'bid': boss_id})
        else:
            db.execute(text("""
                INSERT INTO r2_run_bosses (run_id, boss_id, spawned, killed, killed_at)
                VALUES (:rid, :bid, :s, :k, :ktime)
            """), {'rid': run_id, 'bid': boss_id, 's': spawned, 'k': killed,
                   'ktime': now if killed else None})

        # Update boss kill counter
        if killed and not was_killed:
            db.execute(text(
                'UPDATE r2_runs SET bosses_killed=bosses_killed+1 WHERE id=:rid'
            ), {'rid': run_id})
            # Update manifest
            db.execute(text("""
                INSERT INTO r2_manifest_bosses (user_id, boss_id, first_killed_run_id, kill_count)
                VALUES (:uid, :bid, :rid, 1)
                ON DUPLICATE KEY UPDATE kill_count=kill_count+1
            """), {'uid': uid, 'bid': boss_id, 'rid': run_id})
        elif not killed and was_killed:
            db.execute(text(
                'UPDATE r2_runs SET bosses_killed=GREATEST(0,bosses_killed-1) WHERE id=:rid'
            ), {'rid': run_id})

        db.commit()

    return JsonResponse({'ok': True, 'spawned': spawned, 'killed': killed})


@web_login_required
def api_r2_item_mark(request, token):
    """POST - mark an item as found."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    uid       = request.web_user.id
    item_type = str(data.get('item_type', ''))[:16]
    item_id   = safe_int(data.get('item_id'), None)
    found     = 1 if data.get('found') else 0

    VALID_TYPES = ('weapon', 'ring', 'amulet', 'armor', 'mod', 'mutator', 'relic')
    if item_type not in VALID_TYPES or not item_id:
        return JsonResponse({'error': 'Invalid item'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        run = _get_run_owner(db, token, uid)
        if not run:
            return JsonResponse({'error': 'Not found'}, status=404)
        if not run[1]:
            return JsonResponse({'error': 'Run not active'}, status=400)

        run_id = run[0]
        existing = db.execute(text(
            'SELECT id, found FROM r2_run_items WHERE run_id=:rid AND item_type=:t AND item_id=:iid'
        ), {'rid': run_id, 't': item_type, 'iid': item_id}).fetchone()

        was_found = existing[1] if existing else 0

        if existing:
            db.execute(text("""
                UPDATE r2_run_items SET found=:f,
                    found_at=CASE WHEN :f=1 AND found=0 THEN :now ELSE found_at END
                WHERE id=:eid
            """), {'f': found, 'now': now, 'eid': existing[0]})
        else:
            db.execute(text("""
                INSERT INTO r2_run_items (run_id, item_type, item_id, found, found_at)
                VALUES (:rid, :t, :iid, :f, :ft)
            """), {'rid': run_id, 't': item_type, 'iid': item_id,
                   'f': found, 'ft': now if found else None})

        # Update items_found counter
        if found and not was_found:
            db.execute(text(
                'UPDATE r2_runs SET items_found=items_found+1 WHERE id=:rid'
            ), {'rid': run_id})
            # Update manifest
            db.execute(text("""
                INSERT INTO r2_manifest (user_id, item_type, item_id, first_found_run_id, find_count)
                VALUES (:uid, :t, :iid, :rid, 1)
                ON DUPLICATE KEY UPDATE find_count=find_count+1
            """), {'uid': uid, 't': item_type, 'iid': item_id, 'rid': run_id})
        elif not found and was_found:
            db.execute(text(
                'UPDATE r2_runs SET items_found=GREATEST(0,items_found-1) WHERE id=:rid'
            ), {'rid': run_id})

        db.commit()

    return JsonResponse({'ok': True, 'found': found})


@web_login_required
def api_r2_death(request, token):
    """POST - record a death."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    uid = request.web_user.id
    now = int(time.time())

    with get_db_session() as db:
        run = _get_run_owner(db, token, uid)
        if not run:
            return JsonResponse({'error': 'Not found'}, status=404)
        if not run[1]:
            return JsonResponse({'error': 'Run not active'}, status=400)

        run_id = run[0]
        db.execute(text("""
            UPDATE r2_runs
            SET death_count=death_count+1,
                session_death_count=session_death_count+1
            WHERE id=:rid
        """), {'rid': run_id})
        db.commit()

        new_total   = db.execute(text('SELECT death_count FROM r2_runs WHERE id=:rid'), {'rid': run_id}).scalar()
        new_session = db.execute(text('SELECT session_death_count FROM r2_runs WHERE id=:rid'), {'rid': run_id}).scalar()

    return JsonResponse({'ok': True, 'total_deaths': new_total, 'session_deaths': new_session})


@web_login_required
def api_r2_run_end(request, token):
    """POST - end/complete a run, flush to manifest."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    uid = request.web_user.id
    now = int(time.time())

    with get_db_session() as db:
        run = _get_run_owner(db, token, uid)
        if not run:
            return JsonResponse({'error': 'Not found'}, status=404)

        run_id = run[0]

        # Mark complete
        db.execute(text("""
            UPDATE r2_runs SET is_active=0, completed_at=:now WHERE id=:rid
        """), {'now': now, 'rid': run_id})

        # Flush all found items to manifest
        found_items = db.execute(text("""
            SELECT item_type, item_id FROM r2_run_items
            WHERE run_id=:rid AND found=1
        """), {'rid': run_id}).fetchall()

        for item_type, item_id in found_items:
            db.execute(text("""
                INSERT INTO r2_manifest (user_id, item_type, item_id, first_found_run_id, find_count)
                VALUES (:uid, :t, :iid, :rid, 1)
                ON DUPLICATE KEY UPDATE find_count=find_count+1
            """), {'uid': uid, 't': item_type, 'iid': item_id, 'rid': run_id})

        # Flush killed bosses to manifest
        killed_bosses = db.execute(text("""
            SELECT boss_id FROM r2_run_bosses WHERE run_id=:rid AND killed=1
        """), {'rid': run_id}).fetchall()

        for (boss_id,) in killed_bosses:
            db.execute(text("""
                INSERT INTO r2_manifest_bosses (user_id, boss_id, first_killed_run_id, kill_count)
                VALUES (:uid, :bid, :rid, 1)
                ON DUPLICATE KEY UPDATE kill_count=kill_count+1
            """), {'uid': uid, 'bid': boss_id, 'rid': run_id})

        db.commit()
        award_xp(uid, 'sl_run_complete', ref_id=run_id)

    return JsonResponse({'ok': True})


@web_login_required
def api_r2_run_status(request, token):
    """GET - current run status (deaths, bosses, items)."""
    uid = request.web_user.id
    with get_db_session() as db:
        run = db.execute(text("""
            SELECT id, is_active, death_count, session_death_count,
                   bosses_killed, items_found, name, run_type, is_hardcore
            FROM r2_runs WHERE token=:tok AND user_id=:uid
        """), {'tok': token, 'uid': uid}).fetchone()
        if not run:
            return JsonResponse({'error': 'Not found'}, status=404)

    return JsonResponse({
        'ok': True,
        'is_active': bool(run[1]),
        'total_deaths': run[2],
        'session_deaths': run[3],
        'bosses_killed': run[4],
        'items_found': run[5],
        'name': run[6],
        'run_type': run[7],
        'is_hardcore': bool(run[8]),
    })


def api_r2_prisms(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, how_to_get, dlc FROM r2_prisms ORDER BY name'
        )).fetchall()
    return JsonResponse({'prisms': [
        {'id': r[0], 'name': r[1], 'how_to_get': r[2], 'dlc': r[3]}
        for r in rows
    ]})


def api_r2_legendary_bonuses(request):
    with get_db_session() as db:
        rows = db.execute(text(
            'SELECT id, name, description FROM r2_legendary_bonuses ORDER BY name'
        )).fetchall()
    return JsonResponse({'legendaries': [
        {'id': r[0], 'name': r[1], 'description': r[2]}
        for r in rows
    ]})


def api_r2_builds_browse(request):
    """GET /api/r2/builds/browse/ - public R2 build browsing."""
    q     = request.GET.get('q', '')[:100]
    sort  = request.GET.get('sort', 'recent')[:16]
    limit = safe_int(request.GET.get('limit', 30), 30, 1, 100)
    order = 'b.updated_at DESC' if sort == 'recent' else 'b.created_at DESC'

    with get_db_session() as db:
        params = {'lim': limit}
        where = 'WHERE b.is_public=1 AND u.is_banned=0'
        if q:
            where += ' AND b.name LIKE :q'
            params['q'] = f'%{q}%'
        rows = db.execute(text(f"""
            SELECT b.id, b.name, b.description, b.share_token, b.playstyle,
                   b.created_at, b.updated_at,
                   u.username, u.avatar_url,
                   a1.name as primary_arch, a2.name as secondary_arch,
                   a1.image_path as arch_img
            FROM r2_builds b
            JOIN web_users u ON b.user_id = u.id
            LEFT JOIN r2_archetypes a1 ON b.primary_archetype_id = a1.id
            LEFT JOIN r2_archetypes a2 ON b.secondary_archetype_id = a2.id
            {where}
            ORDER BY {order} LIMIT :lim
        """), params).fetchall()

    return JsonResponse({'builds': [{
        'id': r[0], 'name': r[1], 'description': r[2], 'share_token': r[3],
        'playstyle': r[4], 'created_at': r[5], 'updated_at': r[6],
        'username': r[7], 'avatar': r[8],
        'primary_arch': r[9] or '', 'secondary_arch': r[10] or '',
        'arch_img': r[11],
    } for r in rows]})


@web_login_required
def api_r2_manifest(request):
    """GET - user's full manifest (all items + bosses found across all runs)."""
    uid = request.web_user.id
    with get_db_session() as db:
        items = db.execute(text(
            'SELECT item_type, item_id, find_count FROM r2_manifest WHERE user_id=:uid'
        ), {'uid': uid}).fetchall()
        bosses = db.execute(text(
            'SELECT boss_id, kill_count FROM r2_manifest_bosses WHERE user_id=:uid'
        ), {'uid': uid}).fetchall()

    return JsonResponse({
        'items': [{'type': r[0], 'item_id': r[1], 'count': r[2]} for r in items],
        'bosses': [{'boss_id': r[0], 'count': r[1]} for r in bosses],
    })
