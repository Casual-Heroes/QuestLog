import json
import re
import time
import logging

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET, require_http_methods
from django_ratelimit.decorators import ratelimit

from app.db import get_db_session
from app.questlog_web.models import (
    WebFfxivGuide, WebFfxivGuideLike, WebFfxivGuideComment,
    WebFfxivGuideCommentLike, WebUser,
)
from app.questlog_web.helpers import (
    sanitize_text, web_login_required, add_web_user_context,
    award_xp, safe_int,
)
from sqlalchemy import desc, func
from app.questlog_web.fluxer_webhooks import notify_new_job_guide

logger = logging.getLogger(__name__)

FLUXER_GUIDES_CHANNEL = '1499144185146676012'
FLUXER_GUIDES_INVITE  = 'https://web.fluxer.app/channels/1474761008438513445/1499144185146676012'

# ---------------------------------------------------------------------------
# Job definitions - static, won't change patch to patch
# ---------------------------------------------------------------------------

JOBS = {
    # Tanks
    'pld': {'name': 'Paladin',       'role': 'Tank',       'abbr': 'PLD', 'icon': 'pld'},
    'war': {'name': 'Warrior',       'role': 'Tank',       'abbr': 'WAR', 'icon': 'war'},
    'drk': {'name': 'Dark Knight',   'role': 'Tank',       'abbr': 'DRK', 'icon': 'drk'},
    'gnb': {'name': 'Gunbreaker',    'role': 'Tank',       'abbr': 'GNB', 'icon': 'gnb'},
    # Healers
    'whm': {'name': 'White Mage',    'role': 'Healer',     'abbr': 'WHM', 'icon': 'whm'},
    'sch': {'name': 'Scholar',       'role': 'Healer',     'abbr': 'SCH', 'icon': 'sch'},
    'ast': {'name': 'Astrologian',   'role': 'Healer',     'abbr': 'AST', 'icon': 'ast'},
    'sge': {'name': 'Sage',          'role': 'Healer',     'abbr': 'SGE', 'icon': 'sge'},
    # Melee DPS
    'mnk': {'name': 'Monk',          'role': 'Melee DPS',  'abbr': 'MNK', 'icon': 'mnk'},
    'drg': {'name': 'Dragoon',       'role': 'Melee DPS',  'abbr': 'DRG', 'icon': 'drg'},
    'nin': {'name': 'Ninja',         'role': 'Melee DPS',  'abbr': 'NIN', 'icon': 'nin'},
    'sam': {'name': 'Samurai',       'role': 'Melee DPS',  'abbr': 'SAM', 'icon': 'sam'},
    'rpr': {'name': 'Reaper',        'role': 'Melee DPS',  'abbr': 'RPR', 'icon': 'rpr'},
    'vpr': {'name': 'Viper',         'role': 'Melee DPS',  'abbr': 'VPR', 'icon': 'vpr'},
    # Ranged Physical DPS
    'brd': {'name': 'Bard',          'role': 'Ranged DPS', 'abbr': 'BRD', 'icon': 'brd'},
    'mch': {'name': 'Machinist',     'role': 'Ranged DPS', 'abbr': 'MCH', 'icon': 'mch'},
    'dnc': {'name': 'Dancer',        'role': 'Ranged DPS', 'abbr': 'DNC', 'icon': 'dnc'},
    # Caster DPS
    'blm': {'name': 'Black Mage',    'role': 'Caster DPS', 'abbr': 'BLM', 'icon': 'blm'},
    'smn': {'name': 'Summoner',      'role': 'Caster DPS', 'abbr': 'SMN', 'icon': 'smn'},
    'rdm': {'name': 'Red Mage',      'role': 'Caster DPS', 'abbr': 'RDM', 'icon': 'rdm'},
    'pct': {'name': 'Pictomancer',   'role': 'Caster DPS', 'abbr': 'PCT', 'icon': 'pct'},
    'blu': {'name': 'Blue Mage',     'role': 'Limited',    'abbr': 'BLU', 'icon': 'blu'},
    'bst': {'name': 'Beast Master',  'role': 'Limited',    'abbr': 'BST', 'icon': 'bst'},
}

ROLE_ORDER = ['Tank', 'Healer', 'Melee DPS', 'Ranged DPS', 'Caster DPS', 'Limited']

ROLE_COLORS = {
    'Tank':       'text-blue-400',
    'Healer':     'text-green-400',
    'Melee DPS':  'text-red-400',
    'Ranged DPS': 'text-yellow-400',
    'Caster DPS': 'text-purple-400',
    'Limited':    'text-gray-400',
}

ROLE_BORDERS = {
    'Tank':       'border-blue-700/50',
    'Healer':     'border-green-700/50',
    'Melee DPS':  'border-red-700/50',
    'Ranged DPS': 'border-yellow-700/50',
    'Caster DPS': 'border-purple-700/50',
    'Limited':    'border-neutral-700/50',
}

GUIDE_TAGS = [
    'Beginner', 'Intermediate', 'Advanced', 'Savage', 'Ultimate',
    'Casual', 'BiS', 'Leveling', 'Alliance Raid', 'Optimization',
    'Speedrun', 'Solo', 'Outdated',
]

PATCHES = ['7.5']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(s):
    s = s.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:160]


def _unique_slug(db, job_key, base_slug):
    slug = f"{job_key}-{base_slug}"
    existing = db.query(WebFfxivGuide).filter_by(slug=slug).first()
    if not existing:
        return slug
    i = 2
    while True:
        candidate = f"{job_key}-{base_slug}-{i}"
        if not db.query(WebFfxivGuide).filter_by(slug=candidate).first():
            return candidate
        i += 1


def _validate_blocks(raw_blocks):
    """Validate and sanitize guide content blocks. Returns (cleaned_list, error_str)."""
    if not isinstance(raw_blocks, list):
        return None, 'blocks must be a list'
    if len(raw_blocks) > 50:
        return None, 'too many blocks (max 50)'

    allowed_types = {'text', 'image', 'video', 'gear_table', 'rotation'}
    cleaned = []

    for i, block in enumerate(raw_blocks):
        if not isinstance(block, dict):
            return None, f'block {i} is not an object'

        btype = block.get('type', '')
        if btype not in allowed_types:
            return None, f'block {i} has invalid type: {btype}'

        content = block.get('content', '')

        if btype == 'text':
            if not isinstance(content, str):
                return None, f'block {i} text content must be a string'
            content = sanitize_text(content, max_length=5000)

        elif btype == 'image':
            # content must be a local /media/uploads/ URL - no external images
            if not isinstance(content, str):
                return None, f'block {i} image content must be a string'
            content = content.strip()
            if not re.match(r'^/media/uploads/[a-zA-Z0-9/_.\-]+\.(webp|jpg|jpeg|png|gif)$', content):
                return None, f'block {i} image must be a local /media/uploads/ path'
            caption = sanitize_text(block.get('caption', ''), max_length=200)

        elif btype == 'video':
            # Only YouTube/Twitch embeds
            if not isinstance(content, str):
                return None, f'block {i} video content must be a string'
            content = content.strip()
            yt = re.match(r'^(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})', content)
            tw = re.match(r'^(?:https?://)?(?:www\.)?twitch\.tv/videos/(\d+)', content)
            if not yt and not tw:
                return None, f'block {i} video must be a YouTube or Twitch URL'
            caption = sanitize_text(block.get('caption', ''), max_length=200)

        elif btype in ('gear_table', 'rotation'):
            if not isinstance(content, str):
                return None, f'block {i} content must be a string'
            content = sanitize_text(content, max_length=5000)

        entry = {'type': btype, 'content': content, 'sort_order': i}
        if btype in ('image', 'video'):
            entry['caption'] = sanitize_text(block.get('caption', ''), max_length=200)
        cleaned.append(entry)

    return cleaned, None


def _guide_to_dict(guide, author, viewer_id=None, db=None):
    job = JOBS.get(guide.job_key, {})
    liked = False
    if viewer_id and db:
        liked = db.query(WebFfxivGuideLike).filter_by(
            guide_id=guide.id, user_id=viewer_id
        ).first() is not None

    try:
        tags = json.loads(guide.tags) if guide.tags else []
    except Exception:
        tags = []

    try:
        blocks = json.loads(guide.blocks) if guide.blocks else []
    except Exception:
        blocks = []

    return {
        'id':            guide.id,
        'slug':          guide.slug,
        'job_key':       guide.job_key,
        'job_name':      job.get('name', guide.job_key.upper()),
        'job_abbr':      job.get('abbr', guide.job_key.upper()),
        'job_role':      job.get('role', ''),
        'title':         guide.title,
        'summary':       guide.summary or '',
        'tags':          tags,
        'patch_version': guide.patch_version or '',
        'blocks':        blocks,
        'is_pinned':     guide.is_pinned,
        'is_hidden':     guide.is_hidden,
        'view_count':    guide.view_count,
        'like_count':    guide.like_count,
        'comment_count': guide.comment_count,
        'liked':         liked,
        'author': {
            'id':       author.id,
            'username': author.username,
            'avatar':   author.avatar_url or '',
        },
        'created_at': guide.created_at,
        'updated_at': guide.updated_at,
    }


def _comment_to_dict(c, author, viewer_id=None, db=None):
    liked = False
    if viewer_id and db:
        liked = db.query(WebFfxivGuideCommentLike).filter_by(
            comment_id=c.id, user_id=viewer_id
        ).first() is not None
    return {
        'id':        c.id,
        'parent_id': c.parent_id,
        'body':      c.body if not c.is_deleted else '[deleted]',
        'is_deleted':c.is_deleted,
        'like_count':c.like_count,
        'liked':     liked,
        'author': {
            'id':       author.id,
            'username': author.username,
            'avatar':   author.avatar_url or '',
        },
        'created_at': c.created_at,
        'updated_at': c.updated_at,
    }


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@add_web_user_context
def ffxiv_job_guides(request):
    """Job cards listing page - all 21 jobs grouped by role."""
    with get_db_session() as db:
        # Guide counts per job
        counts = dict(
            db.query(WebFfxivGuide.job_key, func.count(WebFfxivGuide.id))
            .filter_by(is_published=True, is_hidden=False)
            .group_by(WebFfxivGuide.job_key)
            .all()
        )

    roles = []
    for role in ROLE_ORDER:
        jobs_in_role = [
            {
                'key':   key,
                'name':  info['name'],
                'abbr':  info['abbr'],
                'role':  role,
                'color': ROLE_COLORS[role],
                'border':ROLE_BORDERS[role],
                'guide_count': counts.get(key, 0),
                'icon_url': f'https://xivapi.com/i/062000/0620{_job_icon_id(key)}.png',
            }
            for key, info in JOBS.items()
            if info['role'] == role
        ]
        if jobs_in_role:
            roles.append({
                'name':   role,
                'color':  ROLE_COLORS[role],
                'jobs':   jobs_in_role,
            })

    context = {
        'web_user':   request.web_user,
        'active_page':'ffxiv_job_guides',
        'roles':      roles,
        'total_guides': sum(counts.values()),
        'fluxer_channel': FLUXER_GUIDES_INVITE,
    }
    return render(request, 'questlog_web/ffxiv_job_guides.html', context)


@add_web_user_context
def ffxiv_job_hub(request, job_key):
    """Per-job hub - lists all guides for that job."""
    job_key = job_key.lower()
    if job_key not in JOBS:
        return redirect('ffxiv_job_guides')

    job = JOBS[job_key]
    page = safe_int(request.GET.get('page'), 1, 1, 100)
    tag_filter = request.GET.get('tag', '').strip()
    per_page = 20

    with get_db_session() as db:
        q = db.query(WebFfxivGuide).filter_by(
            job_key=job_key, is_published=True, is_hidden=False
        )
        if tag_filter:
            q = q.filter(WebFfxivGuide.tags.like(f'%{tag_filter}%'))

        total = q.count()
        guides_raw = (
            q.order_by(WebFfxivGuide.is_pinned.desc(), WebFfxivGuide.like_count.desc(), WebFfxivGuide.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )

        author_ids = list({g.author_id for g in guides_raw})
        authors = {u.id: u for u in db.query(WebUser).filter(WebUser.id.in_(author_ids)).all()} if author_ids else {}

        viewer_id = request.web_user.id if request.web_user else None
        guides = [_guide_to_dict(g, authors[g.author_id], viewer_id, db) for g in guides_raw if g.author_id in authors]

        counts = dict(
            db.query(WebFfxivGuide.job_key, func.count(WebFfxivGuide.id))
            .filter_by(is_published=True, is_hidden=False)
            .group_by(WebFfxivGuide.job_key)
            .all()
        )

    # Build role groups for sidebar
    role_groups = []
    for role in ROLE_ORDER:
        jobs_in_role = [
            {
                'key':         k,
                'name':        v['name'],
                'abbr':        v['abbr'],
                'icon_url':    f'https://xivapi.com/i/062000/0620{_job_icon_id(k)}.png',
                'guide_count': counts.get(k, 0),
            }
            for k, v in JOBS.items() if v['role'] == role
        ]
        if jobs_in_role:
            role_groups.append({'name': role, 'jobs': jobs_in_role})

    context = {
        'web_user':      request.web_user,
        'active_page':   'ffxiv_job_guides',
        'job':           job,
        'job_key':       job_key,
        'job_icon_url':  f'https://xivapi.com/i/062000/0620{_job_icon_id(job_key)}.png',
        'role_color':    ROLE_COLORS[job['role']],
        'role_border':   ROLE_BORDERS[job['role']],
        'roles':         role_groups,
        'guides':        guides,
        'total':         total,
        'page':          page,
        'per_page':      per_page,
        'total_pages':   (total + per_page - 1) // per_page,
        'tag_filter':    tag_filter,
        'guide_tags':    GUIDE_TAGS,
        'fluxer_channel':FLUXER_GUIDES_INVITE,
    }
    return render(request, 'questlog_web/ffxiv_job_hub.html', context)


@add_web_user_context
def ffxiv_guide_detail(request, slug):
    """Individual guide page."""
    with get_db_session() as db:
        guide = db.query(WebFfxivGuide).filter_by(slug=slug).first()
        if not guide or (guide.is_hidden and not (request.web_user and request.web_user.is_admin)):
            return redirect('ffxiv_job_guides')

        author = db.query(WebUser).filter_by(id=guide.author_id).first()
        if not author:
            return redirect('ffxiv_job_guides')

        viewer_id = request.web_user.id if request.web_user else None
        is_author = viewer_id == guide.author_id
        is_admin  = bool(request.web_user and request.web_user.is_admin)

        guide_dict = _guide_to_dict(guide, author, viewer_id, db)

        # Increment view count (fire and forget - don't fail on error)
        try:
            guide.view_count = (guide.view_count or 0) + 1
            db.commit()
        except Exception:
            db.rollback()

        # Top-level comments + replies
        comments_raw = (
            db.query(WebFfxivGuideComment)
            .filter_by(guide_id=guide.id)
            .order_by(WebFfxivGuideComment.created_at.asc())
            .all()
        )
        comment_author_ids = list({c.author_id for c in comments_raw})
        comment_authors = {
            u.id: u for u in db.query(WebUser).filter(WebUser.id.in_(comment_author_ids)).all()
        } if comment_author_ids else {}

        comments = [
            _comment_to_dict(c, comment_authors[c.author_id], viewer_id, db)
            for c in comments_raw
            if c.author_id in comment_authors
        ]

    job = JOBS.get(guide_dict['job_key'], {})

    context = {
        'web_user':        request.web_user,
        'active_page':     'ffxiv_job_guides',
        'guide':           guide_dict,
        'job':             job,
        'job_key':         guide_dict['job_key'],
        'job_icon_url':    f"https://xivapi.com/i/062000/0620{_job_icon_id(guide_dict['job_key'])}.png",
        'role_color':      ROLE_COLORS.get(job.get('role', ''), 'text-gray-400'),
        'comments':        comments,
        'is_author':       is_author,
        'is_admin':        is_admin,
        'guide_tags':      GUIDE_TAGS,
        'patches':         PATCHES,
        'fluxer_channel':  FLUXER_GUIDES_INVITE,
    }
    return render(request, 'questlog_web/ffxiv_guide_detail.html', context)


@web_login_required
@add_web_user_context
def ffxiv_guide_create(request, job_key):
    """Guide creation page."""
    job_key = job_key.lower()
    if job_key not in JOBS:
        return redirect('ffxiv_job_guides')

    job = JOBS[job_key]
    context = {
        'web_user':    request.web_user,
        'active_page': 'ffxiv_job_guides',
        'job':         job,
        'job_key':     job_key,
        'job_icon_url':f'https://xivapi.com/i/062000/0620{_job_icon_id(job_key)}.png',
        'role_color':  ROLE_COLORS[job['role']],
        'guide_tags':  GUIDE_TAGS,
        'patches':     PATCHES,
        'mode':        'create',
    }
    return render(request, 'questlog_web/ffxiv_guide_editor.html', context)


@web_login_required
@add_web_user_context
def ffxiv_guide_edit(request, slug):
    """Guide edit page - author or admin only."""
    with get_db_session() as db:
        guide = db.query(WebFfxivGuide).filter_by(slug=slug).first()
        if not guide:
            return redirect('ffxiv_job_guides')

        viewer_id = request.web_user.id
        if guide.author_id != viewer_id and not request.web_user.is_admin:
            return redirect('ffxiv_guide_detail', slug=slug)

        job = JOBS.get(guide.job_key, {})
        try:
            blocks = json.loads(guide.blocks) if guide.blocks else []
        except Exception:
            blocks = []
        try:
            tags = json.loads(guide.tags) if guide.tags else []
        except Exception:
            tags = []

    context = {
        'web_user':     request.web_user,
        'active_page':  'ffxiv_job_guides',
        'job':          job,
        'job_key':      guide.job_key,
        'job_icon_url': f"https://xivapi.com/i/062000/0620{_job_icon_id(guide.job_key)}.png",
        'role_color':   ROLE_COLORS.get(job.get('role', ''), 'text-gray-400'),
        'guide_tags':   GUIDE_TAGS,
        'patches':      PATCHES,
        'mode':         'edit',
        'guide_id':     guide.id,
        'guide_slug':   guide.slug,
        'initial': {
            'title':         guide.title,
            'summary':       guide.summary or '',
            'tags':          tags,
            'patch_version': guide.patch_version or '',
            'blocks':        blocks,
        },
    }
    return render(request, 'questlog_web/ffxiv_guide_editor.html', context)


# ---------------------------------------------------------------------------
# API views
# ---------------------------------------------------------------------------

@web_login_required
@require_POST
@ratelimit(key='ip', rate='10/h', block=True)
def api_ffxiv_guide_save(request, job_key):
    """POST /api/ffxiv/guides/<job>/create/ - create a new guide."""
    job_key = job_key.lower()
    if job_key not in JOBS:
        return JsonResponse({'error': 'Invalid job'}, status=400)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    title = sanitize_text(data.get('title', ''), max_length=150).strip()
    if not title or len(title) < 5:
        return JsonResponse({'error': 'Title must be at least 5 characters'}, status=400)

    summary = sanitize_text(data.get('summary', ''), max_length=300).strip()

    raw_tags = data.get('tags', [])
    if not isinstance(raw_tags, list):
        return JsonResponse({'error': 'tags must be a list'}, status=400)
    tags = [t for t in raw_tags if t in GUIDE_TAGS][:8]

    patch = sanitize_text(data.get('patch_version', ''), max_length=20).strip()
    if patch and patch not in PATCHES:
        patch = ''

    notify_fluxer = bool(data.get('notify_fluxer', False))

    raw_blocks = data.get('blocks', [])
    blocks, err = _validate_blocks(raw_blocks)
    if err:
        return JsonResponse({'error': err}, status=400)

    now = int(time.time())
    web_user = request.web_user
    job_info = JOBS[job_key]

    with get_db_session() as db:
        base_slug = _slugify(title)
        slug = _unique_slug(db, job_key, base_slug)

        guide = WebFfxivGuide(
            author_id     = web_user.id,
            job_key       = job_key,
            title         = title,
            slug          = slug,
            summary       = summary or None,
            tags          = json.dumps(tags),
            patch_version = patch or None,
            blocks        = json.dumps(blocks),
            is_published  = True,
            is_hidden     = False,
            is_pinned     = False,
            view_count    = 0,
            like_count    = 0,
            comment_count = 0,
            created_at    = now,
            updated_at    = now,
        )
        db.add(guide)
        db.flush()
        guide_slug = guide.slug

    try:
        award_xp(web_user.id, 'post_create', ref_id=guide.id)
    except Exception:
        pass

    if notify_fluxer:
        guide_url = f'https://questlog.casual-heroes.com/ffxiv/tools/job-guides/guide/{guide_slug}/'
        try:
            notify_new_job_guide(
                job_name  = job_info['name'],
                author    = web_user.display_name or web_user.username,
                title     = title,
                guide_url = guide_url,
            )
        except Exception:
            logger.exception('notify_new_job_guide failed')

    return JsonResponse({'success': True, 'slug': guide_slug})


@web_login_required
@require_POST
@ratelimit(key='ip', rate='20/h', block=True)
def api_ffxiv_guide_update(request, guide_id):
    """POST /api/ffxiv/guides/<id>/edit/ - update an existing guide."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    web_user = request.web_user

    with get_db_session() as db:
        guide = db.query(WebFfxivGuide).filter_by(id=guide_id).first()
        if not guide:
            return JsonResponse({'error': 'Guide not found'}, status=404)
        if guide.author_id != web_user.id and not web_user.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        title = sanitize_text(data.get('title', guide.title), max_length=150).strip()
        if not title or len(title) < 5:
            return JsonResponse({'error': 'Title too short'}, status=400)

        summary = sanitize_text(data.get('summary', ''), max_length=300).strip()

        raw_tags = data.get('tags', [])
        tags = [t for t in raw_tags if t in GUIDE_TAGS][:8] if isinstance(raw_tags, list) else []

        patch = sanitize_text(data.get('patch_version', ''), max_length=20).strip()
        if patch and patch not in PATCHES:
            patch = ''

        raw_blocks = data.get('blocks', [])
        blocks, err = _validate_blocks(raw_blocks)
        if err:
            return JsonResponse({'error': err}, status=400)

        guide.title         = title
        guide.summary       = summary or None
        guide.tags          = json.dumps(tags)
        guide.patch_version = patch or None
        guide.blocks        = json.dumps(blocks)
        guide.updated_at    = int(time.time())
        db.commit()
        slug = guide.slug

    return JsonResponse({'success': True, 'slug': slug})


@web_login_required
@require_POST
@ratelimit(key='ip', rate='5/m', block=True)
def api_ffxiv_guide_like(request, guide_id):
    """POST /api/ffxiv/guides/<id>/like/ - toggle like."""
    web_user = request.web_user
    now = int(time.time())

    with get_db_session() as db:
        guide = db.query(WebFfxivGuide).filter_by(id=guide_id).first()
        if not guide or guide.is_hidden:
            return JsonResponse({'error': 'Not found'}, status=404)

        existing = db.query(WebFfxivGuideLike).filter_by(
            guide_id=guide_id, user_id=web_user.id
        ).first()

        if existing:
            db.delete(existing)
            guide.like_count = max(0, (guide.like_count or 0) - 1)
            liked = False
        else:
            db.add(WebFfxivGuideLike(
                guide_id=guide_id, user_id=web_user.id, created_at=now
            ))
            guide.like_count = (guide.like_count or 0) + 1
            liked = True
        db.commit()
        count = guide.like_count

    return JsonResponse({'success': True, 'liked': liked, 'like_count': count})


@web_login_required
@require_POST
@ratelimit(key='ip', rate='30/h', block=True)
def api_ffxiv_guide_comment(request, guide_id):
    """POST /api/ffxiv/guides/<id>/comments/ - add comment or reply."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    body = sanitize_text(data.get('body', ''), max_length=2000).strip()
    if not body or len(body) < 2:
        return JsonResponse({'error': 'Comment too short'}, status=400)

    parent_id = data.get('parent_id')
    if parent_id is not None:
        parent_id = int(parent_id) if str(parent_id).isdigit() else None

    web_user = request.web_user
    now = int(time.time())

    with get_db_session() as db:
        guide = db.query(WebFfxivGuide).filter_by(id=guide_id).first()
        if not guide or guide.is_hidden:
            return JsonResponse({'error': 'Guide not found'}, status=404)

        if parent_id:
            parent = db.query(WebFfxivGuideComment).filter_by(
                id=parent_id, guide_id=guide_id
            ).first()
            if not parent or parent.parent_id is not None:
                return JsonResponse({'error': 'Invalid parent comment'}, status=400)

        comment = WebFfxivGuideComment(
            guide_id  = guide_id,
            author_id = web_user.id,
            parent_id = parent_id,
            body      = body,
            is_deleted= False,
            like_count= 0,
            created_at= now,
            updated_at= now,
        )
        db.add(comment)
        guide.comment_count = (guide.comment_count or 0) + 1
        db.commit()

        author = db.query(WebUser).filter_by(id=web_user.id).first()
        result = _comment_to_dict(comment, author, web_user.id, db)

    try:
        award_xp(web_user.id, 'comment_create', ref_id=guide_id)
    except Exception:
        pass

    return JsonResponse({'success': True, 'comment': result})


@web_login_required
@require_POST
@ratelimit(key='ip', rate='5/m', block=True)
def api_ffxiv_guide_comment_like(request, comment_id):
    """POST /api/ffxiv/guide-comments/<id>/like/ - toggle comment like."""
    web_user = request.web_user
    now = int(time.time())

    with get_db_session() as db:
        comment = db.query(WebFfxivGuideComment).filter_by(id=comment_id).first()
        if not comment or comment.is_deleted:
            return JsonResponse({'error': 'Not found'}, status=404)

        existing = db.query(WebFfxivGuideCommentLike).filter_by(
            comment_id=comment_id, user_id=web_user.id
        ).first()

        if existing:
            db.delete(existing)
            comment.like_count = max(0, (comment.like_count or 0) - 1)
            liked = False
        else:
            db.add(WebFfxivGuideCommentLike(
                comment_id=comment_id, user_id=web_user.id, created_at=now
            ))
            comment.like_count = (comment.like_count or 0) + 1
            liked = True
        db.commit()
        count = comment.like_count

    return JsonResponse({'success': True, 'liked': liked, 'like_count': count})


@web_login_required
@require_POST
@ratelimit(key='ip', rate='10/h', block=True)
def api_ffxiv_guide_comment_delete(request, comment_id):
    """POST /api/ffxiv/guide-comments/<id>/delete/ - soft-delete (author or admin)."""
    web_user = request.web_user

    with get_db_session() as db:
        comment = db.query(WebFfxivGuideComment).filter_by(id=comment_id).first()
        if not comment:
            return JsonResponse({'error': 'Not found'}, status=404)
        if comment.author_id != web_user.id and not web_user.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        comment.is_deleted = True
        comment.body = ''
        comment.updated_at = int(time.time())

        guide = db.query(WebFfxivGuide).filter_by(id=comment.guide_id).first()
        if guide:
            guide.comment_count = max(0, (guide.comment_count or 0) - 1)
        db.commit()

    return JsonResponse({'success': True})


@web_login_required
@require_POST
def api_ffxiv_guide_delete(request, guide_id):
    """POST /api/ffxiv/guides/<id>/delete/ - hard delete (author or admin)."""
    web_user = request.web_user

    with get_db_session() as db:
        guide = db.query(WebFfxivGuide).filter_by(id=guide_id).first()
        if not guide:
            return JsonResponse({'error': 'Not found'}, status=404)
        if guide.author_id != web_user.id and not web_user.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        job_key = guide.job_key
        db.delete(guide)
        db.commit()

    return JsonResponse({'success': True, 'redirect': f'/ffxiv/tools/job-guides/{job_key}/'})


@web_login_required
@require_POST
def api_ffxiv_guide_hide(request, guide_id):
    """POST /api/ffxiv/guides/<id>/hide/ - admin/mod toggle hide."""
    if not request.web_user.is_admin:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    with get_db_session() as db:
        guide = db.query(WebFfxivGuide).filter_by(id=guide_id).first()
        if not guide:
            return JsonResponse({'error': 'Not found'}, status=404)
        guide.is_hidden = not guide.is_hidden
        db.commit()
        hidden = guide.is_hidden

    return JsonResponse({'success': True, 'is_hidden': hidden})


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

_JOB_ICON_MAP = {
    'pld': '05', 'war': '01', 'drk': '32', 'gnb': '37',
    'whm': '06', 'sch': '28', 'ast': '33', 'sge': '40',
    'mnk': '02', 'drg': '04', 'nin': '30', 'sam': '34',
    'rpr': '39', 'vpr': '41',
    'brd': '05', 'mch': '31', 'dnc': '38',
    'blm': '07', 'smn': '27', 'rdm': '35', 'pct': '42',
    'blu': '36',
    'bst': '43',
}

def _job_icon_id(job_key):
    return _JOB_ICON_MAP.get(job_key, '00')
