# QuestLog - Blog / Articles

import re
import json
import time
import logging

from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils.html import mark_safe
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django_ratelimit.decorators import ratelimit

from sqlalchemy import desc, func

from app.db import get_db_session
from .models import (
    WebUser, WebFoundGame,
    WebArticle, WebArticleComment, WebArticleCommentLike,
)
from .helpers import (
    web_login_required, add_web_user_context,
    check_banned, check_posting_timeout,
    sanitize_text, sanitize_article_html,
    serialize_user_brief, award_xp, safe_int,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_CATEGORIES = ('guide', 'article', 'news', 'opinion')
ARTICLES_PER_PAGE = 12
COMMENTS_PER_PAGE = 50
COVER_URL_RE = re.compile(
    r'^/media/uploads/[a-zA-Z0-9/_.\-]+\.(webp|jpg|jpeg|png|gif)$'
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_contributor(user):
    """True if user is an admin or a designated contributor."""
    if user is None:
        return False
    return bool(user.is_admin) or bool(getattr(user, 'is_contributor', False))


def _slugify(s):
    s = s.lower().strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'[\s_]+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:200]


def _unique_slug(db, base_slug, exclude_id=None):
    """Return a slug that does not already exist in web_articles."""
    candidate = base_slug
    q = db.query(WebArticle).filter_by(slug=candidate)
    if exclude_id:
        q = q.filter(WebArticle.id != exclude_id)
    if not q.first():
        return candidate
    i = 2
    while True:
        candidate = f"{base_slug}-{i}"
        q = db.query(WebArticle).filter_by(slug=candidate)
        if exclude_id:
            q = q.filter(WebArticle.id != exclude_id)
        if not q.first():
            return candidate
        i += 1


def _article_to_dict(article, author, viewer_id=None):
    """Serialise an article for JSON API responses (listing + detail)."""
    return {
        'id':            article.id,
        'slug':          article.slug,
        'title':         article.title,
        'summary':       article.summary or '',
        'category':      article.category,
        'cover_url':     article.cover_url or '',
        'game_tag_name': article.game_tag_name or '',
        'is_published':  article.is_published,
        'is_pinned':     article.is_pinned,
        'comment_count': article.comment_count,
        'view_count':    article.view_count,
        'edited_at':     article.edited_at,
        'edit_count':    article.edit_count,
        'created_at':    article.created_at,
        'published_at':  article.published_at,
        'author':        serialize_user_brief(author) if author else None,
    }


def _serialize_comment(comment, author, viewer_id=None, db=None):
    liked = False
    if viewer_id and db and not comment.is_deleted:
        liked = db.query(WebArticleCommentLike).filter_by(
            comment_id=comment.id, user_id=viewer_id
        ).first() is not None
    return {
        'id':         comment.id,
        'article_id': comment.article_id,
        'parent_id':  comment.parent_id,
        'content':    '' if comment.is_deleted else comment.content,
        'is_deleted': comment.is_deleted,
        'like_count': comment.like_count,
        'liked':      liked,
        'created_at': comment.created_at,
        'updated_at': comment.updated_at,
        'author':     serialize_user_brief(author) if (author and not comment.is_deleted) else None,
    }


def _get_web_user(request):
    return getattr(request, 'web_user', None)


# ---------------------------------------------------------------------------
# Page: blog listing
# ---------------------------------------------------------------------------

@add_web_user_context
def blog_list(request):
    """Public listing page. Supports ?category= and ?q= filters."""
    category = request.GET.get('category', '').strip().lower()
    if category not in VALID_CATEGORIES:
        category = ''
    q = request.GET.get('q', '').strip()[:100]
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1, max_val=9999)

    web_user = _get_web_user(request)

    with get_db_session() as db:
        base_q = db.query(WebArticle).filter(
            WebArticle.is_published == True,
            WebArticle.is_hidden == False,
        )
        if category:
            base_q = base_q.filter(WebArticle.category == category)
        if q:
            like = f'%{q}%'
            base_q = base_q.filter(
                WebArticle.title.ilike(like) | WebArticle.summary.ilike(like)
            )

        total = base_q.count()
        articles_raw = (
            base_q
            .order_by(desc(WebArticle.is_pinned), desc(WebArticle.published_at))
            .offset((page - 1) * ARTICLES_PER_PAGE)
            .limit(ARTICLES_PER_PAGE)
            .all()
        )

        author_ids = {a.author_id for a in articles_raw}
        authors = {u.id: u for u in db.query(WebUser).filter(WebUser.id.in_(author_ids)).all()}

        articles = [_article_to_dict(a, authors.get(a.author_id)) for a in articles_raw]

        # Category counts as list of (name, count) tuples for easy template iteration
        category_tabs = []
        for cat in VALID_CATEGORIES:
            cnt = db.query(WebArticle).filter(
                WebArticle.is_published == True,
                WebArticle.is_hidden == False,
                WebArticle.category == cat,
            ).count()
            category_tabs.append((cat, cnt))

    total_pages = max(1, (total + ARTICLES_PER_PAGE - 1) // ARTICLES_PER_PAGE)
    user_can_write = _is_contributor(web_user)

    return render(request, 'questlog_web/blog_list.html', {
        'articles':         articles,
        'category':         category,
        'q':                q,
        'page':             page,
        'total':            total,
        'total_pages':      total_pages,
        'category_tabs':    category_tabs,
        'user_can_write':   user_can_write,
        'web_user':         web_user,
        'active_page':      'blog',
    })


# ---------------------------------------------------------------------------
# Page: article detail
# ---------------------------------------------------------------------------

@add_web_user_context
def blog_detail(request, slug):
    """Public article reader. Increments view_count once per session."""
    web_user = _get_web_user(request)
    viewer_id = web_user.id if web_user else None

    with get_db_session() as db:
        article = db.query(WebArticle).filter_by(slug=slug).first()
        if not article:
            return redirect('/blog/')

        # Non-admins cannot see unpublished or hidden articles
        if not article.is_published or article.is_hidden:
            if not (web_user and web_user.is_admin):
                return redirect('/blog/')

        author = db.query(WebUser).filter_by(id=article.author_id).first()

        # Increment view count at most once per session per article
        session_key = f'viewed_article_{article.id}'
        if not request.session.get(session_key):
            db.query(WebArticle).filter_by(id=article.id).update(
                {'view_count': WebArticle.view_count + 1}
            )
            db.commit()
            request.session[session_key] = True

        # Render markdown to sanitized HTML - mark_safe is intentional,
        # sanitize_article_html() enforces the allowlist before we get here
        body_html = mark_safe(sanitize_article_html(article.body_md))

        article_data = _article_to_dict(article, author, viewer_id)

        user_can_edit = bool(
            web_user and (web_user.is_admin or web_user.id == article.author_id)
        )

        # Top-level comments (not deleted threads shown as [deleted])
        comments_raw = (
            db.query(WebArticleComment)
            .filter(
                WebArticleComment.article_id == article.id,
                WebArticleComment.parent_id == None,
            )
            .order_by(WebArticleComment.created_at)
            .limit(COMMENTS_PER_PAGE)
            .all()
        )

        comment_author_ids = {c.author_id for c in comments_raw if not c.is_deleted}
        reply_ids = [c.id for c in comments_raw]
        replies_raw = (
            db.query(WebArticleComment)
            .filter(
                WebArticleComment.parent_id.in_(reply_ids),
                WebArticleComment.article_id == article.id,
            )
            .order_by(WebArticleComment.created_at)
            .all()
        ) if reply_ids else []

        comment_author_ids |= {c.author_id for c in replies_raw if not c.is_deleted}
        comment_authors = {
            u.id: u for u in db.query(WebUser).filter(WebUser.id.in_(comment_author_ids)).all()
        }

        replies_by_parent = {}
        for r in replies_raw:
            replies_by_parent.setdefault(r.parent_id, []).append(
                _serialize_comment(r, comment_authors.get(r.author_id), viewer_id, db)
            )

        comments = []
        for c in comments_raw:
            cd = _serialize_comment(c, comment_authors.get(c.author_id), viewer_id, db)
            cd['replies'] = replies_by_parent.get(c.id, [])
            comments.append(cd)

    return render(request, 'questlog_web/blog_detail.html', {
        'article':       article_data,
        'body_html':     body_html,
        'comments':      comments,
        'user_can_edit': user_can_edit,
        'web_user':      web_user,
        'active_page':   'blog',
    })


# ---------------------------------------------------------------------------
# Page: editor (create + edit)
# ---------------------------------------------------------------------------

@web_login_required
@add_web_user_context
def blog_editor(request, slug=None):
    """
    GET  /blog/new/          - blank editor (contributors/admins only)
    GET  /blog/<slug>/edit/  - load existing article for editing
    """
    web_user = _get_web_user(request)
    if not _is_contributor(web_user):
        return redirect('/blog/')

    article_data = None
    if slug:
        with get_db_session() as db:
            article = db.query(WebArticle).filter_by(slug=slug).first()
            if not article:
                return redirect('/blog/')
            if not (web_user.is_admin or article.author_id == web_user.id):
                return redirect('/blog/')
            author = db.query(WebUser).filter_by(id=article.author_id).first()
            article_data = _article_to_dict(article, author)
            article_data['body_md'] = article.body_md  # raw MD for editor

    return render(request, 'questlog_web/blog_editor.html', {
        'article':          article_data,
        'valid_categories': VALID_CATEGORIES,
        'web_user':         web_user,
        'active_page':      'blog',
    })


# ---------------------------------------------------------------------------
# API: create article
# ---------------------------------------------------------------------------

@web_login_required
@require_POST
@ratelimit(key='ip', rate='10/h', block=True)
def api_blog_create(request):
    """POST /ql/api/blog/ - create a new article (contributor/admin only)."""
    web_user = _get_web_user(request)
    if not _is_contributor(web_user):
        return JsonResponse({'error': 'Contributor access required'}, status=403)

    banned = check_banned(request)
    if banned:
        return banned

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    title = sanitize_text(data.get('title', ''), max_length=200).strip()
    if not title:
        return JsonResponse({'error': 'Title is required'}, status=400)
    if len(title) < 5:
        return JsonResponse({'error': 'Title must be at least 5 characters'}, status=400)

    summary = sanitize_text(data.get('summary', ''), max_length=500).strip()

    category = data.get('category', 'article')
    if category not in VALID_CATEGORIES:
        return JsonResponse({'error': 'Invalid category'}, status=400)

    body_md = str(data.get('body_md', '')).strip()
    if not body_md:
        return JsonResponse({'error': 'Body is required'}, status=400)
    if len(body_md) > 100_000:
        return JsonResponse({'error': 'Body too long (max 100,000 characters)'}, status=400)

    cover_url = str(data.get('cover_url', '')).strip()
    if cover_url and not COVER_URL_RE.match(cover_url):
        return JsonResponse({'error': 'Cover image must be a local /media/uploads/ path'}, status=400)

    is_published = bool(data.get('is_published', False))

    now = int(time.time())
    base_slug = _slugify(title)
    if not base_slug:
        return JsonResponse({'error': 'Title produces an empty slug'}, status=400)

    with get_db_session() as db:
        slug = _unique_slug(db, base_slug)
        article = WebArticle(
            author_id=web_user.id,
            title=title,
            slug=slug,
            summary=summary or None,
            category=category,
            cover_url=cover_url or None,
            body_md=body_md,
            is_published=is_published,
            published_at=now if is_published else None,
            created_at=now,
            updated_at=now,
        )
        db.add(article)
        db.commit()

        if is_published:
            award_xp(web_user.id, 'article_published', ref_id=article.id)

        author = db.query(WebUser).filter_by(id=web_user.id).first()
        return JsonResponse({
            'success': True,
            'article': _article_to_dict(article, author),
        }, status=201)


# ---------------------------------------------------------------------------
# API: edit article
# ---------------------------------------------------------------------------

@web_login_required
@require_http_methods(['PATCH'])
@ratelimit(key='ip', rate='30/h', block=True)
def api_blog_edit(request, article_id):
    """PATCH /ql/api/blog/<id>/ - edit an existing article."""
    web_user = _get_web_user(request)
    if not _is_contributor(web_user):
        return JsonResponse({'error': 'Contributor access required'}, status=403)

    banned = check_banned(request)
    if banned:
        return banned

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    now = int(time.time())

    with get_db_session() as db:
        article = db.query(WebArticle).filter_by(id=article_id).first()
        if not article:
            return JsonResponse({'error': 'Not found'}, status=404)

        if not (web_user.is_admin or article.author_id == web_user.id):
            return JsonResponse({'error': 'Forbidden'}, status=403)

        was_published = article.is_published

        if 'title' in data:
            title = sanitize_text(str(data['title']), max_length=200).strip()
            if not title or len(title) < 5:
                return JsonResponse({'error': 'Title must be at least 5 characters'}, status=400)
            article.title = title
            new_base_slug = _slugify(title)
            article.slug = _unique_slug(db, new_base_slug, exclude_id=article.id)

        if 'summary' in data:
            article.summary = sanitize_text(str(data['summary']), max_length=500).strip() or None

        if 'category' in data:
            cat = data['category']
            if cat not in VALID_CATEGORIES:
                return JsonResponse({'error': 'Invalid category'}, status=400)
            article.category = cat

        if 'body_md' in data:
            body = str(data['body_md']).strip()
            if not body:
                return JsonResponse({'error': 'Body cannot be empty'}, status=400)
            if len(body) > 100_000:
                return JsonResponse({'error': 'Body too long'}, status=400)
            article.body_md = body

        if 'cover_url' in data:
            cover = str(data['cover_url']).strip()
            if cover and not COVER_URL_RE.match(cover):
                return JsonResponse({'error': 'Cover must be a local /media/uploads/ path'}, status=400)
            article.cover_url = cover or None

        if 'is_published' in data:
            publishing_now = bool(data['is_published'])
            article.is_published = publishing_now
            if publishing_now and not was_published:
                article.published_at = now
                award_xp(web_user.id, 'article_published', ref_id=article.id)

        # Admins can pin/hide
        if web_user.is_admin:
            if 'is_pinned' in data:
                article.is_pinned = bool(data['is_pinned'])
            if 'is_hidden' in data:
                article.is_hidden = bool(data['is_hidden'])

        article.edited_at = now
        article.edit_count = (article.edit_count or 0) + 1
        article.updated_at = now

        db.commit()

        author = db.query(WebUser).filter_by(id=article.author_id).first()
        return JsonResponse({'success': True, 'article': _article_to_dict(article, author)})


# ---------------------------------------------------------------------------
# API: delete article
# ---------------------------------------------------------------------------

@web_login_required
@require_http_methods(['DELETE'])
@ratelimit(key='ip', rate='20/h', block=True)
def api_blog_delete(request, article_id):
    """DELETE /ql/api/blog/<id>/ - permanently delete article (author or admin)."""
    web_user = _get_web_user(request)
    if not _is_contributor(web_user):
        return JsonResponse({'error': 'Contributor access required'}, status=403)

    with get_db_session() as db:
        article = db.query(WebArticle).filter_by(id=article_id).first()
        if not article:
            return JsonResponse({'error': 'Not found'}, status=404)
        if not (web_user.is_admin or article.author_id == web_user.id):
            return JsonResponse({'error': 'Forbidden'}, status=403)

        # Delete comments and likes (cascade handles FK, but be explicit)
        comment_ids = [
            c.id for c in db.query(WebArticleComment.id)
            .filter_by(article_id=article.id).all()
        ]
        if comment_ids:
            db.query(WebArticleCommentLike).filter(
                WebArticleCommentLike.comment_id.in_(comment_ids)
            ).delete(synchronize_session=False)
        db.query(WebArticleComment).filter_by(article_id=article.id).delete(
            synchronize_session=False
        )
        db.delete(article)
        db.commit()

    return JsonResponse({'success': True})


# ---------------------------------------------------------------------------
# API: comments - list + create
# ---------------------------------------------------------------------------

@add_web_user_context
@require_http_methods(['GET', 'POST'])
def api_blog_comments(request, article_id):
    """GET: public. POST: verified login required."""
    with get_db_session() as db:
        article = db.query(WebArticle).filter_by(id=article_id).first()
        if not article or not article.is_published or article.is_hidden:
            return JsonResponse({'error': 'Article not found'}, status=404)

        if request.method == 'GET':
            return _get_article_comments(request, db, article_id)

        # POST - require login
        web_user = _get_web_user(request)
        if not web_user:
            return JsonResponse({'error': 'Login required'}, status=401)
        if not web_user.email_verified:
            return JsonResponse({'error': 'Please verify your email before commenting'}, status=403)

        banned = check_banned(request)
        if banned:
            return banned

        timeout = check_posting_timeout(request)
        if timeout:
            return timeout

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        content = sanitize_text(data.get('content', ''), max_length=1000)
        if not content:
            return JsonResponse({'error': 'Comment cannot be empty'}, status=400)

        parent_id = data.get('parent_id')
        if parent_id is not None:
            parent_id = safe_int(parent_id, default=None)
            if parent_id is None:
                return JsonResponse({'error': 'Invalid parent_id'}, status=400)
            parent = db.query(WebArticleComment).filter_by(
                id=parent_id, article_id=article_id
            ).first()
            if not parent or parent.is_deleted:
                return JsonResponse({'error': 'Parent comment not found'}, status=404)
            if parent.parent_id is not None:
                return JsonResponse({'error': 'Cannot reply to a reply'}, status=400)

        now = int(time.time())
        comment = WebArticleComment(
            article_id=article_id,
            author_id=web_user.id,
            parent_id=parent_id,
            content=content,
            created_at=now,
            updated_at=now,
        )
        db.add(comment)

        # Update denormalized counter
        db.query(WebArticle).filter_by(id=article_id).update(
            {'comment_count': WebArticle.comment_count + 1}
        )
        db.commit()
        db.refresh(comment)

        award_xp(web_user.id, 'article_comment', ref_id=comment.id)

        fresh_author = db.query(WebUser).filter_by(id=web_user.id).first()
        return JsonResponse({
            'success': True,
            'comment': _serialize_comment(comment, fresh_author, web_user.id, db),
        }, status=201)


def _get_article_comments(request, db, article_id):
    web_user = _get_web_user(request)
    viewer_id = web_user.id if web_user else None

    page = safe_int(request.GET.get('page', 1), default=1, min_val=1, max_val=9999)
    offset = (page - 1) * COMMENTS_PER_PAGE

    top_level = (
        db.query(WebArticleComment)
        .filter(
            WebArticleComment.article_id == article_id,
            WebArticleComment.parent_id == None,
        )
        .order_by(WebArticleComment.created_at)
        .offset(offset)
        .limit(COMMENTS_PER_PAGE)
        .all()
    )

    parent_ids = [c.id for c in top_level]
    replies = (
        db.query(WebArticleComment)
        .filter(WebArticleComment.parent_id.in_(parent_ids))
        .order_by(WebArticleComment.created_at)
        .all()
    ) if parent_ids else []

    author_ids = {c.author_id for c in top_level + replies if not c.is_deleted}
    authors = {
        u.id: u for u in db.query(WebUser).filter(WebUser.id.in_(author_ids)).all()
    }

    replies_by_parent = {}
    for r in replies:
        replies_by_parent.setdefault(r.parent_id, []).append(
            _serialize_comment(r, authors.get(r.author_id), viewer_id, db)
        )

    result = []
    for c in top_level:
        cd = _serialize_comment(c, authors.get(c.author_id), viewer_id, db)
        cd['replies'] = replies_by_parent.get(c.id, [])
        result.append(cd)

    return JsonResponse({'comments': result, 'page': page})


# ---------------------------------------------------------------------------
# API: delete comment (author soft-delete or admin hard-delete)
# ---------------------------------------------------------------------------

@add_web_user_context
@web_login_required
@require_http_methods(['DELETE'])
@ratelimit(key='ip', rate='30/h', block=True)
def api_blog_comment_delete(request, comment_id):
    web_user = _get_web_user(request)

    with get_db_session() as db:
        comment = db.query(WebArticleComment).filter_by(id=comment_id).first()
        if not comment:
            return JsonResponse({'error': 'Not found'}, status=404)

        is_owner = comment.author_id == web_user.id
        is_admin = bool(web_user.is_admin)
        if not (is_owner or is_admin):
            return JsonResponse({'error': 'Forbidden'}, status=403)

        now = int(time.time())
        comment.is_deleted = True
        comment.content = ''
        comment.updated_at = now

        # Decrement article comment counter
        db.query(WebArticle).filter_by(id=comment.article_id).update(
            {'comment_count': func.greatest(WebArticle.comment_count - 1, 0)}
        )
        db.commit()

    return JsonResponse({'success': True})


# ---------------------------------------------------------------------------
# API: like / unlike comment
# ---------------------------------------------------------------------------

@add_web_user_context
@web_login_required
@require_http_methods(['POST', 'DELETE'])
@ratelimit(key='ip', rate='60/h', block=True)
def api_blog_comment_like(request, comment_id):
    web_user = _get_web_user(request)

    with get_db_session() as db:
        comment = db.query(WebArticleComment).filter_by(id=comment_id).first()
        if not comment or comment.is_deleted:
            return JsonResponse({'error': 'Not found'}, status=404)

        existing = db.query(WebArticleCommentLike).filter_by(
            comment_id=comment_id, user_id=web_user.id
        ).first()

        if request.method == 'POST':
            if existing:
                return JsonResponse({'success': True, 'like_count': comment.like_count})
            db.add(WebArticleCommentLike(
                comment_id=comment_id,
                user_id=web_user.id,
                created_at=int(time.time()),
            ))
            comment.like_count = (comment.like_count or 0) + 1
        else:
            if not existing:
                return JsonResponse({'success': True, 'like_count': comment.like_count})
            db.delete(existing)
            comment.like_count = max(0, (comment.like_count or 1) - 1)

        db.commit()
        return JsonResponse({'success': True, 'like_count': comment.like_count})


# ---------------------------------------------------------------------------
# API: markdown preview (contributor/admin only)
# ---------------------------------------------------------------------------

@require_GET
def api_blog_recent(request):
    """GET /api/blog/recent/ - public endpoint, returns recent published articles."""
    limit = min(int(request.GET.get('limit', 5)), 10)
    with get_db_session() as db:
        articles = db.query(WebArticle).filter_by(
            is_published=True, is_hidden=False
        ).order_by(desc(WebArticle.published_at)).limit(limit).all()
        result = []
        for art in articles:
            author = db.query(WebUser).filter_by(id=art.author_id).first()
            result.append(_article_to_dict(art, author))
    return JsonResponse({'articles': result})


@web_login_required
@require_POST
@ratelimit(key='ip', rate='60/h', block=True)


def api_blog_preview(request):
    """POST /ql/api/blog/preview/ - render markdown and return safe HTML."""
    web_user = _get_web_user(request)
    if not _is_contributor(web_user):
        return JsonResponse({'error': 'Contributor access required'}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    md_source = str(data.get('body_md', ''))[:100_000]
    html = sanitize_article_html(md_source)
    return JsonResponse({'html': html})
