import json
import time
import re
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from app.db import get_db_session
from app.questlog_web.models import WebEsoBuild, WebEsoBuildVote, WebEsoBuildComment, WebEsoBuildBookmark, WebUser
from app.questlog_web.helpers import get_web_user, sanitize_text, web_login_required, add_web_user_context
from sqlalchemy import desc, func

ESO_CLASSES = [
    'Dragonknight', 'Sorcerer', 'Nightblade', 'Templar',
    'Warden', 'Necromancer', 'Arcanist',
]

ESO_ROLES = ['dps', 'healer', 'tank']
ESO_RESOURCES = ['magicka', 'stamina', 'hybrid']

GEAR_SLOTS = [
    'Head', 'Shoulders', 'Chest', 'Hands', 'Waist',
    'Legs', 'Feet', 'Necklace', 'Ring 1', 'Ring 2',
    'Weapon 1', 'Weapon 2',
]

GEAR_WEIGHTS = ['Light', 'Medium', 'Heavy', 'Jewelry', 'Weapon', 'Shield']

TRAITS = [
    'Divines', 'Infused', 'Impenetrable', 'Reinforced', 'Well-Fitted',
    'Sturdy', 'Training', 'Nirnhoned', 'Sharpened', 'Precise',
    'Powered', 'Charged', 'Defending', 'Decisive', 'Arcane',
    'Healthy', 'Robust', 'Bloodthirsty', 'Harmony', 'Triune',
    'Swift', 'Protective', 'Any',
]

PATCHES = ['U49', 'U50 (June 8, 2026)']


def _skill_bar_data():
    bars = [('Main Bar', 0), ('Back Bar', 1)]
    result = []
    for bar_label, bi in bars:
        slots = []
        for sj in range(6):
            slots.append({
                'label': 'Ultimate' if sj == 5 else f'Slot {sj + 1}',
                'name_field': f'skill_name_{bi}_{sj}',
                'url_field': f'skill_url_{bi}_{sj}',
            })
        result.append((bar_label, slots))
    return result


def _slugify(title):
    slug = title.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = slug.strip('-')
    return slug[:120]


def _unique_slug(db, base_slug):
    slug = base_slug
    counter = 1
    while db.query(WebEsoBuild).filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def _safe_int(val, default=None, min_val=None, max_val=None):
    try:
        v = int(val)
        if min_val is not None and v < min_val:
            return default
        if max_val is not None and v > max_val:
            return default
        return v
    except (TypeError, ValueError):
        return default


def _build_to_dict(build, author, viewer_id=None, db=None):
    vote = None
    bookmarked = False
    if viewer_id and db:
        v = db.query(WebEsoBuildVote).filter_by(build_id=build.id, user_id=viewer_id).first()
        vote = v.vote if v else None
        bm = db.query(WebEsoBuildBookmark).filter_by(build_id=build.id, user_id=viewer_id).first()
        bookmarked = bool(bm)

    return {
        'id': build.id,
        'slug': build.slug,
        'title': build.title,
        'tagline': build.tagline or '',
        'patch_version': build.patch_version or '',
        'eso_class': build.eso_class,
        'role': build.role,
        'resource': build.resource or '',
        'is_meta': build.is_meta,
        'upvotes': build.upvotes,
        'downvotes': build.downvotes,
        'comment_count': build.comment_count,
        'view_count': build.view_count,
        'created_at': build.created_at,
        'author': {
            'id': author.id,
            'username': author.username,
            'display_name': author.display_name or author.username,
            'avatar_url': author.avatar_url or '',
        },
        'vote': vote,
        'bookmarked': bookmarked,
    }


@add_web_user_context
def eso_builds_browse(request):
    web_user = get_web_user(request)
    filter_class = request.GET.get('class', '')
    filter_role  = request.GET.get('role', '')
    filter_meta  = request.GET.get('meta', '')
    page = _safe_int(request.GET.get('page', 1), 1, 1)
    per_page = 12

    with get_db_session() as db:
        q = db.query(WebEsoBuild).filter_by(is_published=True)
        if filter_class and filter_class in ESO_CLASSES:
            q = q.filter(WebEsoBuild.eso_class == filter_class)
        if filter_role and filter_role in ESO_ROLES:
            q = q.filter(WebEsoBuild.role == filter_role)
        if filter_meta == '1':
            q = q.filter(WebEsoBuild.is_meta == True)

        total = q.count()
        builds_raw = q.order_by(desc(WebEsoBuild.is_meta), desc(WebEsoBuild.upvotes), desc(WebEsoBuild.created_at))\
                      .offset((page - 1) * per_page).limit(per_page).all()

        author_ids = [b.author_id for b in builds_raw]
        authors = {}
        if author_ids:
            for u in db.query(WebUser).filter(WebUser.id.in_(author_ids)).all():
                authors[u.id] = u

        viewer_id = web_user.id if web_user else None
        builds = [_build_to_dict(b, authors[b.author_id], viewer_id, db) for b in builds_raw if b.author_id in authors]

    total_pages = max(1, (total + per_page - 1) // per_page)

    return render(request, 'questlog_web/eso_builds_browse.html', {
        'web_user': web_user,
        'active_page': 'eso_builds',
        'builds': builds,
        'eso_classes': ESO_CLASSES,
        'eso_roles': ESO_ROLES,
        'filter_class': filter_class,
        'filter_role': filter_role,
        'filter_meta': filter_meta,
        'page': page,
        'total_pages': total_pages,
        'total': total,
    })


@web_login_required
@add_web_user_context
def eso_build_create(request):
    web_user = get_web_user(request)

    if request.method == 'POST':
        return _handle_build_save(request, web_user, build=None)

    return render(request, 'questlog_web/eso_build_create.html', {
        'web_user': web_user,
        'active_page': 'eso_builds',
        'eso_classes': ESO_CLASSES,
        'eso_roles': ESO_ROLES,
        'eso_resources': ESO_RESOURCES,
        'gear_slots': GEAR_SLOTS,
        'gear_weights': GEAR_WEIGHTS,
        'traits': TRAITS,
        'patches': PATCHES,
        'bar_data': _skill_bar_data(),
    })


@add_web_user_context
def eso_build_detail(request, slug):
    web_user = get_web_user(request)

    with get_db_session() as db:
        build = db.query(WebEsoBuild).filter_by(slug=slug, is_published=True).first()
        if not build:
            from django.http import Http404
            raise Http404

        author = db.query(WebUser).filter_by(id=build.author_id).first()

        viewer_id = web_user.id if web_user else None

        # increment view count - skip if the author is viewing their own build
        if viewer_id != build.author_id:
            build.view_count = (build.view_count or 0) + 1
            db.commit()

        vote = None
        bookmarked = False
        if viewer_id:
            v = db.query(WebEsoBuildVote).filter_by(build_id=build.id, user_id=viewer_id).first()
            vote = v.vote if v else None
            bm = db.query(WebEsoBuildBookmark).filter_by(build_id=build.id, user_id=viewer_id).first()
            bookmarked = bool(bm)

        comments_raw = db.query(WebEsoBuildComment)\
            .filter_by(build_id=build.id)\
            .order_by(WebEsoBuildComment.created_at)\
            .limit(100).all()

        commenter_ids = list({c.author_id for c in comments_raw})
        commenters = {}
        if commenter_ids:
            for u in db.query(WebUser).filter(WebUser.id.in_(commenter_ids)).all():
                commenters[u.id] = u

        comments = []
        for c in comments_raw:
            cu = commenters.get(c.author_id)
            if cu:
                comments.append({
                    'id': c.id,
                    'body': c.body,
                    'created_at': c.created_at,
                    'author': {
                        'id': cu.id,
                        'username': cu.username,
                        'display_name': cu.display_name or cu.username,
                        'avatar_url': cu.avatar_url or '',
                    },
                    'is_mine': viewer_id == cu.id,
                })

        gear   = json.loads(build.gear)   if build.gear   else []
        skills = json.loads(build.skills) if build.skills else [[], []]
        pros   = json.loads(build.pros)   if build.pros   else []
        cons   = json.loads(build.cons)   if build.cons   else []

        build_data = {
            'id': build.id,
            'slug': build.slug,
            'title': build.title,
            'tagline': build.tagline or '',
            'patch_version': build.patch_version or '',
            'eso_class': build.eso_class,
            'role': build.role,
            'resource': build.resource or '',
            'is_meta': build.is_meta,
            'stat_health':   build.stat_health,
            'stat_magicka':  build.stat_magicka,
            'stat_stamina':  build.stat_stamina,
            'stat_dps':      build.stat_dps,
            'stat_hps':      build.stat_hps,
            'difficulty':    build.difficulty,
            'how_it_works':  build.how_it_works or '',
            'champion_points': build.champion_points or '',
            'rotation':      build.rotation or '',
            'mundus':        build.mundus or '',
            'buff_food':     build.buff_food or '',
            'upvotes':       build.upvotes,
            'downvotes':     build.downvotes,
            'view_count':    build.view_count,
            'comment_count': build.comment_count,
            'created_at':    build.created_at,
            'updated_at':    build.updated_at,
            'gear': gear,
            'skills': skills,
            'pros': pros,
            'cons': cons,
            'gear_json':   json.dumps(gear),
            'skills_json': json.dumps(skills),
            'pros_json':   json.dumps(pros),
            'cons_json':   json.dumps(cons),
            'author': {
                'id': author.id,
                'username': author.username,
                'display_name': author.display_name or author.username,
                'avatar_url': author.avatar_url or '',
            } if author else {},
        }

    return render(request, 'questlog_web/eso_build_detail.html', {
        'web_user': web_user,
        'active_page': 'eso_builds',
        'build': build_data,
        'comments': comments,
        'vote': vote,
        'bookmarked': bookmarked,
        'is_author': web_user and web_user.id == build_data['author'].get('id'),
        'gear_slots': GEAR_SLOTS,
    })


@web_login_required
@add_web_user_context
def eso_build_edit(request, slug):
    web_user = get_web_user(request)

    with get_db_session() as db:
        build = db.query(WebEsoBuild).filter_by(slug=slug).first()
        if not build:
            from django.http import Http404
            raise Http404
        if build.author_id != web_user.id and not web_user.is_admin:
            from django.http import Http404
            raise Http404

        if request.method == 'POST':
            return _handle_build_save(request, web_user, build=build)

        gear   = json.loads(build.gear)   if build.gear   else []
        skills = json.loads(build.skills) if build.skills else [[], []]
        pros   = json.loads(build.pros)   if build.pros   else []
        cons   = json.loads(build.cons)   if build.cons   else []

        build_data = {
            'id': build.id, 'slug': build.slug, 'title': build.title,
            'tagline': build.tagline or '', 'patch_version': build.patch_version or '',
            'eso_class': build.eso_class, 'role': build.role, 'resource': build.resource or '',
            'stat_health': build.stat_health, 'stat_magicka': build.stat_magicka,
            'stat_stamina': build.stat_stamina, 'stat_dps': build.stat_dps,
            'stat_hps': build.stat_hps, 'difficulty': build.difficulty,
            'how_it_works': build.how_it_works or '', 'champion_points': build.champion_points or '',
            'rotation': build.rotation or '', 'mundus': build.mundus or '',
            'buff_food': build.buff_food or '', 'gear': gear, 'skills': skills,
            'pros': pros, 'cons': cons,
        }

    return render(request, 'questlog_web/eso_build_create.html', {
        'web_user': web_user,
        'active_page': 'eso_builds',
        'editing': True,
        'build': build_data,
        'eso_classes': ESO_CLASSES,
        'eso_roles': ESO_ROLES,
        'eso_resources': ESO_RESOURCES,
        'gear_slots': GEAR_SLOTS,
        'gear_weights': GEAR_WEIGHTS,
        'traits': TRAITS,
        'patches': PATCHES,
        'bar_data': _skill_bar_data(),
    })


def _handle_build_save(request, web_user, build=None):
    p = request.POST
    title = sanitize_text(p.get('title', '').strip())[:120]
    if not title:
        return redirect('/eso/builds/')

    tagline       = sanitize_text(p.get('tagline', '').strip())[:200]
    patch_version = p.get('patch_version', '').strip()[:20]
    eso_class     = p.get('eso_class', '').strip()
    role          = p.get('role', '').strip()
    resource      = p.get('resource', '').strip()
    mundus        = sanitize_text(p.get('mundus', '').strip())[:80]
    buff_food     = sanitize_text(p.get('buff_food', '').strip())[:120]

    if eso_class not in ESO_CLASSES:
        eso_class = ESO_CLASSES[0]
    if role not in ESO_ROLES:
        role = 'dps'
    if resource not in ESO_RESOURCES:
        resource = None

    stat_health  = _safe_int(p.get('stat_health'),  None, 0, 200000)
    stat_magicka = _safe_int(p.get('stat_magicka'), None, 0, 200000)
    stat_stamina = _safe_int(p.get('stat_stamina'), None, 0, 200000)
    stat_dps     = _safe_int(p.get('stat_dps'),     None, 0, 1000000)
    stat_hps     = _safe_int(p.get('stat_hps'),     None, 0, 1000000)
    difficulty   = _safe_int(p.get('difficulty'),   None, 1, 5)

    # Sanitized rich text fields - allow basic formatting tags only
    allowed = {'p','br','strong','em','ul','ol','li','h3','h4','blockquote','span','a'}

    def sanitize_rich(raw):
        if not raw:
            return ''
        import bleach
        return bleach.clean(raw, tags=allowed, attributes={'a': ['href'], 'span': ['class']}, strip=True)[:50000]

    try:
        import bleach
        how_it_works    = sanitize_rich(p.get('how_it_works', ''))
        champion_points = sanitize_rich(p.get('champion_points', ''))
        rotation        = sanitize_rich(p.get('rotation', ''))
    except ImportError:
        how_it_works    = sanitize_text(p.get('how_it_works', ''))[:50000]
        champion_points = sanitize_text(p.get('champion_points', ''))[:50000]
        rotation        = sanitize_text(p.get('rotation', ''))[:50000]

    # Pros/cons - plain text list
    pros_raw = [sanitize_text(x.strip())[:200] for x in p.get('pros', '').split('\n') if x.strip()][:20]
    cons_raw = [sanitize_text(x.strip())[:200] for x in p.get('cons', '').split('\n') if x.strip()][:20]

    # Gear - 12 slots submitted as gear_slot_0..11 etc
    gear = []
    for i, slot_name in enumerate(GEAR_SLOTS):
        set_name = sanitize_text(p.get(f'gear_set_{i}', '').strip())[:120]
        set_url  = p.get(f'gear_url_{i}', '').strip()[:300]
        weight   = p.get(f'gear_weight_{i}', '').strip()
        trait    = p.get(f'gear_trait_{i}', '').strip()
        enchant  = sanitize_text(p.get(f'gear_enchant_{i}', '').strip())[:80]
        # Validate URL is eso-hub.com or elderscrollsbote.de only
        if set_url and not re.match(r'https://(eso-hub\.com|www\.elderscrollsbote\.de)/', set_url):
            set_url = ''
        gear.append({
            'slot': slot_name,
            'set_name': set_name,
            'set_url': set_url,
            'weight': weight if weight in GEAR_WEIGHTS else '',
            'trait': trait if trait in TRAITS else '',
            'enchant': enchant,
        })

    # Skills - 2 bars x 6 slots
    skills = []
    for bar_i in range(2):
        bar = []
        for slot_j in range(6):
            skill_name = sanitize_text(p.get(f'skill_name_{bar_i}_{slot_j}', '').strip())[:80]
            skill_url  = p.get(f'skill_url_{bar_i}_{slot_j}', '').strip()[:300]
            is_ult     = slot_j == 5
            if skill_url and not re.match(r'https://(eso-hub\.com|www\.elderscrollsbote\.de)/', skill_url):
                skill_url = ''
            bar.append({'name': skill_name, 'url': skill_url, 'is_ultimate': is_ult})
        skills.append(bar)

    now = int(time.time())

    with get_db_session() as db:
        if build is None:
            base_slug = _slugify(title)
            slug = _unique_slug(db, base_slug)
            build = WebEsoBuild(
                author_id=web_user.id,
                title=title, slug=slug, tagline=tagline,
                patch_version=patch_version, eso_class=eso_class,
                role=role, resource=resource,
                stat_health=stat_health, stat_magicka=stat_magicka,
                stat_stamina=stat_stamina, stat_dps=stat_dps,
                stat_hps=stat_hps, difficulty=difficulty,
                how_it_works=how_it_works, pros=json.dumps(pros_raw),
                cons=json.dumps(cons_raw), champion_points=champion_points,
                rotation=rotation, gear=json.dumps(gear), skills=json.dumps(skills),
                mundus=mundus, buff_food=buff_food,
                is_published=True, created_at=now, updated_at=now,
            )
            db.add(build)
            db.commit()
            db.refresh(build)
            return redirect(f'/eso/builds/{build.slug}/')
        else:
            build.title = title
            build.tagline = tagline
            build.patch_version = patch_version
            build.eso_class = eso_class
            build.role = role
            build.resource = resource
            build.stat_health = stat_health
            build.stat_magicka = stat_magicka
            build.stat_stamina = stat_stamina
            build.stat_dps = stat_dps
            build.stat_hps = stat_hps
            build.difficulty = difficulty
            build.how_it_works = how_it_works
            build.pros = json.dumps(pros_raw)
            build.cons = json.dumps(cons_raw)
            build.champion_points = champion_points
            build.rotation = rotation
            build.gear = json.dumps(gear)
            build.skills = json.dumps(skills)
            build.mundus = mundus
            build.buff_food = buff_food
            build.updated_at = now
            db.commit()
            return redirect(f'/eso/builds/{build.slug}/')


@require_POST
@web_login_required
def api_eso_build_delete(request, build_id):
    web_user = get_web_user(request)
    with get_db_session() as db:
        build = db.query(WebEsoBuild).filter_by(id=build_id).first()
        if not build:
            return JsonResponse({'error': 'not found'}, status=404)
        if build.author_id != web_user.id and not web_user.is_admin:
            return JsonResponse({'error': 'forbidden'}, status=403)
        db.delete(build)
        db.commit()
    return JsonResponse({'deleted': True})


@require_POST
@web_login_required
def api_eso_build_vote(request, build_id):
    web_user = get_web_user(request)
    try:
        data = json.loads(request.body)
        vote_val = int(data.get('vote', 0))
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'invalid'}, status=400)

    if vote_val not in (1, -1, 0):
        return JsonResponse({'error': 'invalid'}, status=400)

    with get_db_session() as db:
        build = db.query(WebEsoBuild).filter_by(id=build_id, is_published=True).first()
        if not build:
            return JsonResponse({'error': 'not found'}, status=404)

        existing = db.query(WebEsoBuildVote).filter_by(build_id=build_id, user_id=web_user.id).first()

        if vote_val == 0:
            if existing:
                if existing.vote == 1:
                    build.upvotes = max(0, build.upvotes - 1)
                else:
                    build.downvotes = max(0, build.downvotes - 1)
                db.delete(existing)
        elif existing:
            if existing.vote != vote_val:
                if existing.vote == 1:
                    build.upvotes   = max(0, build.upvotes - 1)
                    build.downvotes += 1
                else:
                    build.downvotes = max(0, build.downvotes - 1)
                    build.upvotes   += 1
                existing.vote = vote_val
        else:
            db.add(WebEsoBuildVote(
                build_id=build_id, user_id=web_user.id,
                vote=vote_val, created_at=int(time.time())
            ))
            if vote_val == 1:
                build.upvotes += 1
            else:
                build.downvotes += 1

        db.commit()
        return JsonResponse({'upvotes': build.upvotes, 'downvotes': build.downvotes, 'vote': vote_val if vote_val != 0 else None})


@require_POST
@web_login_required
def api_eso_build_comment(request, build_id):
    web_user = get_web_user(request)
    try:
        data = json.loads(request.body)
        body = sanitize_text(data.get('body', '').strip())[:2000]
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid'}, status=400)

    if not body:
        return JsonResponse({'error': 'empty'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        build = db.query(WebEsoBuild).filter_by(id=build_id, is_published=True).first()
        if not build:
            return JsonResponse({'error': 'not found'}, status=404)

        comment = WebEsoBuildComment(
            build_id=build_id, author_id=web_user.id,
            body=body, created_at=now, updated_at=now
        )
        db.add(comment)
        build.comment_count = (build.comment_count or 0) + 1
        db.commit()
        db.refresh(comment)

        return JsonResponse({
            'id': comment.id,
            'body': comment.body,
            'created_at': comment.created_at,
            'author': {
                'id': web_user.id,
                'username': web_user.username,
                'display_name': web_user.display_name or web_user.username,
                'avatar_url': web_user.avatar_url or '',
            },
            'is_mine': True,
        })


@require_POST
@web_login_required
def api_eso_build_bookmark(request, build_id):
    web_user = get_web_user(request)
    with get_db_session() as db:
        build = db.query(WebEsoBuild).filter_by(id=build_id, is_published=True).first()
        if not build:
            return JsonResponse({'error': 'not found'}, status=404)

        existing = db.query(WebEsoBuildBookmark).filter_by(build_id=build_id, user_id=web_user.id).first()
        if existing:
            db.delete(existing)
            db.commit()
            return JsonResponse({'bookmarked': False})
        else:
            db.add(WebEsoBuildBookmark(
                build_id=build_id, user_id=web_user.id, created_at=int(time.time())
            ))
            db.commit()
            return JsonResponse({'bookmarked': True})
