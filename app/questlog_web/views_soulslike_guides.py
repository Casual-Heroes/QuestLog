"""SoulsLike community guides - list, detail, create, edit, like, comment."""
import json
import re
import time

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
from sqlalchemy import text

from app.db import get_db_session
from .helpers import (
    web_login_required, add_web_user_context,
    sanitize_text, sanitize_article_html,
    award_xp, safe_int,
)

GUIDE_TYPES = {
    'boss':       'Boss Strategy',
    'build':      'Build Guide',
    'progression':'Progression Route',
    'lore':       'Lore & Story',
    'tips':       'Tips & Tricks',
    'general':    'General Guide',
}

SUPPORTED_GAMES = {
    'elden_ring':       'Elden Ring',
    'dark_souls_1':     'Dark Souls',
    'dark_souls_2':     'Dark Souls II',
    'dark_souls_3':     'Dark Souls III',
    'bloodborne':       'Bloodborne',
    'sekiro':           'Sekiro',
    'demons_souls':     "Demon's Souls",
    'lies_of_p':        'Lies of P',
    'the_surge':        'The Surge',
    'other':            'Other',
}


def _slug(title, uid, now):
    base = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:80]
    return f'{base}-{uid}-{now}'


def _fmt_ts(ts):
    import datetime
    try:
        return datetime.datetime.utcfromtimestamp(ts).strftime('%b %d, %Y')
    except Exception:
        return ''


# ── List ──────────────────────────────────────────────────────────────────────

@add_web_user_context
def sl_guides(request):
    uid      = request.web_user.id if request.web_user else None
    page     = safe_int(request.GET.get('page', 1), default=1, min_val=1, max_val=999)
    per_page = 20
    offset   = (page - 1) * per_page
    game     = request.GET.get('game', '')[:32]
    gtype    = request.GET.get('type', '')[:32]
    q        = sanitize_text(request.GET.get('q', ''))[:100]

    filters = "WHERE g.is_published=1 AND g.is_hidden=0"
    params  = {}
    if game:
        filters += " AND g.game=:game"
        params['game'] = game
    if gtype and gtype in GUIDE_TYPES:
        filters += " AND g.guide_type=:gtype"
        params['gtype'] = gtype
    if q:
        filters += " AND (g.title LIKE :q OR g.summary LIKE :q)"
        params['q'] = f'%{q}%'

    with get_db_session() as db:
        total = db.execute(text(
            f"SELECT COUNT(*) FROM sl_guides g {filters}"
        ), params).scalar() or 0

        rows = db.execute(text(f"""
            SELECT g.id, g.title, g.slug, g.summary, g.game, g.game_mode,
                   g.guide_type, g.game_tag_name, g.game_tag_steam_id,
                   g.like_count, g.comment_count, g.view_count,
                   g.created_at, g.is_pinned,
                   u.username, u.avatar_url
            FROM sl_guides g
            JOIN web_users u ON u.id = g.author_id
            {filters}
            ORDER BY g.is_pinned DESC, g.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {**params, 'limit': per_page, 'offset': offset}).fetchall()

        liked_ids = set()
        if uid:
            lrows = db.execute(text(
                "SELECT guide_id FROM sl_guide_likes WHERE user_id=:uid"
            ), {'uid': uid}).fetchall()
            liked_ids = {r[0] for r in lrows}

    guides = [
        {
            'id': r[0], 'title': r[1], 'slug': r[2], 'summary': r[3] or '',
            'game': r[4], 'game_label': SUPPORTED_GAMES.get(r[4], r[4]),
            'game_mode': r[5] or '',
            'guide_type': r[6], 'type_label': GUIDE_TYPES.get(r[6], 'Guide'),
            'game_tag_name': r[7] or '', 'game_tag_steam_id': r[8],
            'like_count': r[9] or 0, 'comment_count': r[10] or 0,
            'view_count': r[11] or 0,
            'date': _fmt_ts(r[12]), 'is_pinned': bool(r[13]),
            'author': r[14], 'avatar': r[15] or '',
            'liked': r[0] in liked_ids,
        }
        for r in rows
    ]

    return render(request, 'questlog_web/sl_guides.html', {
        'web_user':   request.web_user,
        'active_page':'soulslike_guides',
        'guides':     guides,
        'total':      total,
        'page':       page,
        'per_page':   per_page,
        'has_next':   (offset + per_page) < total,
        'has_prev':   page > 1,
        'game_filter':  game,
        'type_filter':  gtype,
        'q':            q,
        'GUIDE_TYPES':  GUIDE_TYPES,
        'SUPPORTED_GAMES': SUPPORTED_GAMES,
    })


# ── Detail ────────────────────────────────────────────────────────────────────

@add_web_user_context
def sl_guide_detail(request, slug):
    from django.http import Http404
    uid = request.web_user.id if request.web_user else None

    with get_db_session() as db:
        row = db.execute(text("""
            SELECT g.id, g.title, g.slug, g.summary, g.body,
                   g.game, g.game_mode, g.guide_type,
                   g.game_tag_name, g.game_tag_steam_id,
                   g.like_count, g.comment_count, g.view_count,
                   g.created_at, g.updated_at, g.is_pinned,
                   g.author_id, u.username, u.avatar_url
            FROM sl_guides g
            JOIN web_users u ON u.id = g.author_id
            WHERE g.slug=:slug AND g.is_published=1 AND g.is_hidden=0
        """), {'slug': slug}).fetchone()
        if not row:
            raise Http404

        # Increment view count
        db.execute(text(
            "UPDATE sl_guides SET view_count=view_count+1 WHERE id=:id"
        ), {'id': row[0]})

        liked = False
        if uid:
            liked = bool(db.execute(text(
                "SELECT 1 FROM sl_guide_likes WHERE guide_id=:gid AND user_id=:uid"
            ), {'gid': row[0], 'uid': uid}).fetchone())

        comments = db.execute(text("""
            SELECT c.id, c.body, c.like_count, c.created_at,
                   u.username, u.avatar_url, c.author_id
            FROM sl_guide_comments c
            JOIN web_users u ON u.id = c.author_id
            WHERE c.guide_id=:gid AND c.is_deleted=0
            ORDER BY c.created_at ASC
        """), {'gid': row[0]}).fetchall()

        db.commit()

    guide = {
        'id': row[0], 'title': row[1], 'slug': row[2], 'summary': row[3] or '',
        'body': row[4] or '',
        'game': row[5], 'game_label': SUPPORTED_GAMES.get(row[5], row[5]),
        'game_mode': row[6] or '',
        'guide_type': row[7], 'type_label': GUIDE_TYPES.get(row[7], 'Guide'),
        'game_tag_name': row[8] or '', 'game_tag_steam_id': row[9],
        'like_count': row[10] or 0, 'comment_count': row[11] or 0,
        'view_count': (row[12] or 0) + 1,
        'date': _fmt_ts(row[13]), 'updated': _fmt_ts(row[14]),
        'is_pinned': bool(row[15]),
        'author_id': row[16], 'author': row[17], 'avatar': row[18] or '',
        'liked': liked,
        'is_owner': uid == row[16],
        'is_admin': bool(request.web_user and request.web_user.is_admin) if request.web_user else False,
    }

    comment_list = [
        {
            'id': c[0], 'body': c[1], 'like_count': c[2] or 0,
            'date': _fmt_ts(c[3]), 'author': c[4], 'avatar': c[5] or '',
            'is_owner': uid == c[6],
        }
        for c in comments
    ]

    return render(request, 'questlog_web/sl_guide_detail.html', {
        'web_user':    request.web_user,
        'active_page': 'soulslike_hub',
        'guide':       guide,
        'comments':    comment_list,
    })


# ── Editor (create / edit) ────────────────────────────────────────────────────

@web_login_required
@add_web_user_context
def sl_guide_editor(request, slug=None):
    guide = None
    if slug:
        from django.http import Http404
        uid = request.web_user.id
        with get_db_session() as db:
            row = db.execute(text("""
                SELECT id, title, slug, summary, body, game, game_mode,
                       guide_type, game_tag_name, game_tag_steam_id, author_id
                FROM sl_guides WHERE slug=:slug
            """), {'slug': slug}).fetchone()
            if not row:
                raise Http404
            if row[10] != uid and not request.web_user.is_admin:
                from django.http import HttpResponseForbidden
                return HttpResponseForbidden()
        guide = {
            'id': row[0], 'title': row[1], 'slug': row[2],
            'summary': row[3] or '', 'body': row[4] or '',
            'game': row[5], 'game_mode': row[6] or '',
            'guide_type': row[7],
            'game_tag_name': row[8] or '', 'game_tag_steam_id': row[9] or '',
        }

    return render(request, 'questlog_web/sl_guide_editor.html', {
        'web_user':    request.web_user,
        'active_page': 'soulslike_hub',
        'guide':       guide,
        'GUIDE_TYPES': GUIDE_TYPES,
        'SUPPORTED_GAMES': SUPPORTED_GAMES,
    })


# ── API: Create ───────────────────────────────────────────────────────────────

@web_login_required
@ratelimit(key='user', rate='10/h', block=True)
@require_http_methods(['POST'])
def api_sl_guide_create(request):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    uid   = request.web_user.id
    now   = int(time.time())
    title = sanitize_text(data.get('title', ''))[:200].strip()
    if not title:
        return JsonResponse({'error': 'Title required'}, status=400)

    summary    = sanitize_text(data.get('summary', ''))[:400].strip()
    body       = sanitize_article_html(data.get('body', ''))
    game       = str(data.get('game', 'elden_ring'))[:50]
    if game not in SUPPORTED_GAMES:
        game = 'other'
    game_mode      = sanitize_text(data.get('game_mode', ''))[:32]
    guide_type     = str(data.get('guide_type', 'general'))[:30]
    if guide_type not in GUIDE_TYPES:
        guide_type = 'general'
    game_tag_name     = sanitize_text(data.get('game_tag_name', ''))[:200]
    game_tag_steam_id = safe_int(data.get('game_tag_steam_id'), None)

    slug = _slug(title, uid, now)

    with get_db_session() as db:
        db.execute(text("""
            INSERT INTO sl_guides
                (author_id, title, slug, summary, body, game, game_mode,
                 guide_type, game_tag_name, game_tag_steam_id,
                 is_published, created_at, updated_at)
            VALUES
                (:uid, :title, :slug, :summary, :body, :game, :gmode,
                 :gtype, :gtname, :gtid,
                 1, :now, :now)
        """), {
            'uid': uid, 'title': title, 'slug': slug,
            'summary': summary, 'body': body,
            'game': game, 'gmode': game_mode or None,
            'gtype': guide_type,
            'gtname': game_tag_name or None,
            'gtid': game_tag_steam_id,
            'now': now,
        })
        guide_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        db.commit()

    award_xp(uid, 'guide_published', ref_id=guide_id)

    return JsonResponse({'ok': True, 'slug': slug})


# ── API: Edit ─────────────────────────────────────────────────────────────────

@web_login_required
@require_http_methods(['POST'])
def api_sl_guide_edit(request, guide_id):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    uid = request.web_user.id
    now = int(time.time())

    with get_db_session() as db:
        row = db.execute(text(
            "SELECT author_id, slug FROM sl_guides WHERE id=:id"
        ), {'id': guide_id}).fetchone()
        if not row:
            return JsonResponse({'error': 'Not found'}, status=404)
        if row[0] != uid and not request.web_user.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        title      = sanitize_text(data.get('title', ''))[:200].strip() or None
        summary    = sanitize_text(data.get('summary', ''))[:400].strip()
        body       = sanitize_article_html(data.get('body', ''))
        game       = str(data.get('game', 'elden_ring'))[:50]
        if game not in SUPPORTED_GAMES:
            game = 'other'
        game_mode      = sanitize_text(data.get('game_mode', ''))[:32]
        guide_type     = str(data.get('guide_type', 'general'))[:30]
        if guide_type not in GUIDE_TYPES:
            guide_type = 'general'
        game_tag_name     = sanitize_text(data.get('game_tag_name', ''))[:200]
        game_tag_steam_id = safe_int(data.get('game_tag_steam_id'), None)

        db.execute(text("""
            UPDATE sl_guides SET
                title=:title, summary=:summary, body=:body,
                game=:game, game_mode=:gmode, guide_type=:gtype,
                game_tag_name=:gtname, game_tag_steam_id=:gtid,
                updated_at=:now
            WHERE id=:id
        """), {
            'title': title, 'summary': summary, 'body': body,
            'game': game, 'gmode': game_mode or None, 'gtype': guide_type,
            'gtname': game_tag_name or None, 'gtid': game_tag_steam_id,
            'now': now, 'id': guide_id,
        })
        db.commit()
        slug = row[1]

    return JsonResponse({'ok': True, 'slug': slug})


# ── API: Delete ───────────────────────────────────────────────────────────────

@web_login_required
@require_http_methods(['POST'])
def api_sl_guide_delete(request, guide_id):
    uid = request.web_user.id
    with get_db_session() as db:
        row = db.execute(text(
            "SELECT author_id FROM sl_guides WHERE id=:id"
        ), {'id': guide_id}).fetchone()
        if not row:
            return JsonResponse({'error': 'Not found'}, status=404)
        if row[0] != uid and not request.web_user.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        db.execute(text("DELETE FROM sl_guide_comments WHERE guide_id=:id"), {'id': guide_id})
        db.execute(text("DELETE FROM sl_guide_likes WHERE guide_id=:id"), {'id': guide_id})
        db.execute(text("DELETE FROM sl_guides WHERE id=:id"), {'id': guide_id})
        db.commit()
    return JsonResponse({'ok': True})


# ── API: Like ─────────────────────────────────────────────────────────────────

@web_login_required
@require_http_methods(['POST'])
def api_sl_guide_like(request, guide_id):
    uid = request.web_user.id
    now = int(time.time())
    with get_db_session() as db:
        existing = db.execute(text(
            "SELECT id FROM sl_guide_likes WHERE guide_id=:gid AND user_id=:uid"
        ), {'gid': guide_id, 'uid': uid}).fetchone()
        if existing:
            db.execute(text(
                "DELETE FROM sl_guide_likes WHERE guide_id=:gid AND user_id=:uid"
            ), {'gid': guide_id, 'uid': uid})
            db.execute(text(
                "UPDATE sl_guides SET like_count=GREATEST(0,like_count-1) WHERE id=:id"
            ), {'id': guide_id})
            liked = False
        else:
            db.execute(text(
                "INSERT IGNORE INTO sl_guide_likes (guide_id, user_id, created_at) VALUES (:gid, :uid, :now)"
            ), {'gid': guide_id, 'uid': uid, 'now': now})
            db.execute(text(
                "UPDATE sl_guides SET like_count=like_count+1 WHERE id=:id"
            ), {'id': guide_id})
            liked = True
        count = db.execute(text(
            "SELECT like_count FROM sl_guides WHERE id=:id"
        ), {'id': guide_id}).scalar() or 0
        db.commit()
    return JsonResponse({'ok': True, 'liked': liked, 'like_count': count})


# ── API: Comments ─────────────────────────────────────────────────────────────

@web_login_required
@ratelimit(key='user', rate='30/h', block=True)
@require_http_methods(['POST'])
def api_sl_guide_comment(request, guide_id):
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    uid  = request.web_user.id
    now  = int(time.time())
    body = sanitize_text(data.get('body', ''))[:2000].strip()
    if not body:
        return JsonResponse({'error': 'Comment cannot be empty'}, status=400)

    with get_db_session() as db:
        exists = db.execute(text(
            "SELECT id FROM sl_guides WHERE id=:id AND is_published=1 AND is_hidden=0"
        ), {'id': guide_id}).fetchone()
        if not exists:
            return JsonResponse({'error': 'Guide not found'}, status=404)

        db.execute(text("""
            INSERT INTO sl_guide_comments (guide_id, author_id, body, created_at, updated_at)
            VALUES (:gid, :uid, :body, :now, :now)
        """), {'gid': guide_id, 'uid': uid, 'body': body, 'now': now})
        comment_id = db.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        db.execute(text(
            "UPDATE sl_guides SET comment_count=comment_count+1 WHERE id=:id"
        ), {'id': guide_id})
        username   = request.web_user.username
        avatar_url = request.web_user.avatar_url or ''
        db.commit()

    award_xp(uid, 'guide_comment', ref_id=comment_id)

    return JsonResponse({
        'ok': True,
        'comment': {
            'id': comment_id, 'body': body,
            'like_count': 0, 'date': _fmt_ts(now),
            'author': username, 'avatar': avatar_url,
            'is_owner': True,
        }
    })


@web_login_required
@require_http_methods(['POST'])
def api_sl_guide_comment_delete(request, comment_id):
    uid = request.web_user.id
    with get_db_session() as db:
        row = db.execute(text(
            "SELECT author_id, guide_id FROM sl_guide_comments WHERE id=:id AND is_deleted=0"
        ), {'id': comment_id}).fetchone()
        if not row:
            return JsonResponse({'error': 'Not found'}, status=404)
        if row[0] != uid and not request.web_user.is_admin:
            return JsonResponse({'error': 'Forbidden'}, status=403)
        db.execute(text(
            "UPDATE sl_guide_comments SET is_deleted=1 WHERE id=:id"
        ), {'id': comment_id})
        db.execute(text(
            "UPDATE sl_guides SET comment_count=GREATEST(0,comment_count-1) WHERE id=:id"
        ), {'id': row[1]})
        db.commit()
    return JsonResponse({'ok': True})
