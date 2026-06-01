import json
import re
import time
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from app.db import get_db_session
from .models import WebIndieGame, WebCommunityPost, WebCommunityPostLike, WebUser, WebCommunity, WebFoundGame, WebUserFlair, WebIndieSuggestion
from .helpers import (
    add_web_user_context, web_login_required, web_admin_required, api_login_required,
    safe_int, sanitize_text, _is_valid_giphy_url, validate_admin_image_url,
)

logger = logging.getLogger(__name__)


def _extract_steam_app_id(url):
    """Extract Steam app ID from a store URL. Returns int or None."""
    if not url:
        return None
    m = re.search(r'store\.steampowered\.com/app/(\d+)', url)
    return int(m.group(1)) if m else None


def _steam_cover_url(app_id):
    """Return Steam library capsule (600x900 portrait) for a given app ID."""
    if not app_id:
        return None
    return f'https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/library_600x900.jpg'


def _slugify(name):
    slug = name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_-]+', '-', slug)
    slug = slug.strip('-')
    return slug[:200]


def _unique_slug(db, base_slug):
    slug = base_slug
    counter = 1
    while db.query(WebIndieGame).filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def _serialize_game(g, short=False):
    dev = g.dev_user
    added_by = g.added_by_user
    community = g.community
    data = {
        'id': g.id,
        'slug': g.slug,
        'name': g.name,
        'steam_app_id': g.steam_app_id,
        'steam_url': g.steam_url or '',
        'igdb_url': g.igdb_url or '',
        'cover_url': g.cover_url or '',
        'banner_url': g.banner_url or '',
        'platforms': json.loads(g.platforms or '[]'),
        'genres': json.loads(g.genres or '[]'),
        'steam_tags': json.loads(g.steam_tags or '[]'),
        'spotlight_quote': g.spotlight_quote or '',
        'release_date': g.release_date or '',
        'price': g.price or '',
        'review_score': g.review_score,
        'status': g.status or 'featured',
        'is_featured': g.is_featured,
        'post_count': g.post_count or 0,
        'created_at': g.created_at,
        'source': g.source or 'ch_spotlight',
        'claim_status': g.claim_status or '',
        'dev': {
            'user_id': dev.id if dev else None,
            'username': dev.username if dev else None,
            'display_name': (dev.display_name or dev.username) if dev else None,
            'avatar': dev.avatar_url or '' if dev else '',
        } if dev else None,
        'added_by': {
            'username': added_by.username if added_by else '',
            'display_name': (added_by.display_name or added_by.username) if added_by else '',
        },
        'community': {
            'id': community.id,
            'name': community.name,
            'icon_url': community.icon_url or '',
            'invite_url': community.invite_url or '',
            'platform': community.platform.value if community.platform else '',
        } if community else None,
    }
    if not short:
        data.update({
            'spotlight_text': g.spotlight_text or '',
            'dev_bio': g.dev_bio or '',
            'dev_devlog': g.dev_devlog or '',
            'dev_website': g.dev_website or '',
            'dev_twitter': g.dev_twitter or '',
            'dev_discord_url': g.dev_discord_url or '',
            'dev_fluxer_url': g.dev_fluxer_url or '',
            'dev_steam_url': g.dev_steam_url or '',
            'dev_itch_url': g.dev_itch_url or '',
            'dev_youtube_url': g.dev_youtube_url or '',
            'dev_twitch_url': g.dev_twitch_url or '',
            'dev_tiktok_url': g.dev_tiktok_url or '',
            'dev_instagram_url': g.dev_instagram_url or '',
            'dev_facebook_url': g.dev_facebook_url or '',
            'dev_bsky_url': g.dev_bsky_url or '',
            'dev_kick_url': g.dev_kick_url or '',
            'dev_edited_at': g.dev_edited_at,
            'submission_status': g.submission_status or '',
            'submission_pitch': g.submission_pitch or '',
            'submission_link': g.submission_link or '',
            'submission_note': g.submission_note or '',
            'claim_note': g.claim_note or '',
        })
    return data


@add_web_user_context
def indie_heroes(request):
    return render(request, 'questlog_web/indie_heroes.html', {
        'web_user': request.web_user,
        'active_page': 'indie_heroes',
    })


@add_web_user_context
def indie_game_detail(request, slug):
    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug).first()
        if not game:
            return render(request, 'questlog_web/indie_heroes.html', {
                'web_user': request.web_user,
                'active_page': 'indie_heroes',
                'not_found': True,
            })
        is_dev = bool(request.web_user and game.dev_user_id == request.web_user.id)
        is_admin = bool(request.web_user and request.web_user.is_admin)

        # Unpublished: only admin or the assigned dev can see it
        if not game.is_published and not is_admin and not is_dev:
            return render(request, 'questlog_web/indie_heroes.html', {
                'web_user': request.web_user,
                'active_page': 'indie_heroes',
                'not_found': True,
            })

        game_data = _serialize_game(game)

    return render(request, 'questlog_web/indie_game_detail.html', {
        'web_user': request.web_user,
        'active_page': 'indie_heroes',
        'game_json': game_data,
        'game_slug': slug,
        'game_name': game.name,
        'is_dev': is_dev,
        'is_admin': is_admin,
        'og_title': f"{game.name} - Indie Heroes",
        'og_desc': game.spotlight_quote or game.name,
        'og_image': game.banner_url or game.cover_url or '',
    })


@add_web_user_context
@require_http_methods(['GET'])
def api_indie_games(request):
    """Public listing of published indie games."""
    import random as _random
    status_filter = request.GET.get('status', '')
    random_count = safe_int(request.GET.get('random', 0), 0, 0, 20)
    page = safe_int(request.GET.get('page', 1), 1, 1, 100)
    section = request.GET.get('section', '')  # 'curated' | 'main' | '' (all)
    limit = 20
    offset = (page - 1) * limit

    with get_db_session() as db:
        q = db.query(WebIndieGame).filter_by(is_published=True)

        if section == 'curated':
            # CH Curated: admin-added spotlight games with no dev claimed yet
            q = q.filter(
                WebIndieGame.source == 'ch_spotlight',
                WebIndieGame.dev_user_id == None,
            )
        elif section == 'main':
            # Main section: self-submitted OR spotlight games that have been claimed by a dev
            from sqlalchemy import or_
            q = q.filter(
                or_(
                    WebIndieGame.source == 'self_submitted',
                    WebIndieGame.dev_user_id != None,
                )
            )
        # section='' returns all (used by discover widget random=5)

        if status_filter and status_filter in ('featured', 'new', 'spotlight', 'alumni'):
            q = q.filter_by(status=status_filter)

        if random_count:
            all_games = q.all()
            games = _random.sample(all_games, min(random_count, len(all_games)))
            return JsonResponse({
                'games': [_serialize_game(g, short=True) for g in games],
                'has_more': False,
            })

        # Featured games pinned first, then by created_at desc
        games = q.order_by(
            WebIndieGame.is_featured.desc(),
            WebIndieGame.created_at.desc()
        ).offset(offset).limit(limit + 1).all()

        has_more = len(games) > limit
        games = games[:limit]

        return JsonResponse({
            'games': [_serialize_game(g, short=True) for g in games],
            'has_more': has_more,
        })


@add_web_user_context
@require_http_methods(['GET'])
def api_indie_game_detail(request, slug):
    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)
        if not game.is_published and not (request.web_user and request.web_user.is_admin):
            return JsonResponse({'error': 'Not found'}, status=404)
        return JsonResponse({'game': _serialize_game(game)})


@ratelimit(key='ip', rate='30/h', method='POST', block=True)
@add_web_user_context
@require_http_methods(['GET', 'POST'])
def api_indie_wall(request, slug):
    """GET wall posts for an indie game. POST to create (any logged-in user)."""
    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug, is_published=True).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)

        user_id = request.web_user.id if request.web_user else None
        is_admin = bool(request.web_user and request.web_user.is_admin)
        is_dev = bool(user_id and game.dev_user_id == user_id)

        if request.method == 'POST':
            if not user_id:
                return JsonResponse({'error': 'Login required'}, status=401)
            if request.web_user.is_banned or request.web_user.is_disabled:
                return JsonResponse({'error': 'Your account cannot post.'}, status=403)
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

            content = (data.get('content') or '').strip()[:1000] or None
            gif_url = (data.get('gif_url') or '').strip()[:500]
            image_url = (data.get('image_url') or '').strip()[:500]
            parent_id = safe_int(data.get('parent_id'), None)

            if parent_id:
                parent = db.query(WebCommunityPost).filter_by(
                    id=parent_id, indie_game_id=game.id, is_deleted=False
                ).first()
                if not parent:
                    parent_id = None
                    parent = None
            else:
                parent = None

            media_url = None
            media_type = None
            if gif_url and _is_valid_giphy_url(gif_url):
                media_url = gif_url
                media_type = 'gif'
            elif image_url and image_url.startswith('/media/uploads/'):
                media_url = image_url
                media_type = 'image'

            if not content and not media_url:
                return JsonResponse({'error': 'Post must have content or media'}, status=400)

            game_tag_name = (data.get('game_tag_name') or '')[:200] or None
            game_tag_steam_id = safe_int(data.get('game_tag_steam_id'), None)

            now = int(time.time())
            post = WebCommunityPost(
                community_id=None,
                indie_game_id=game.id,
                author_id=user_id,
                content=content,
                media_url=media_url,
                media_type=media_type,
                game_tag_name=game_tag_name,
                game_tag_steam_id=game_tag_steam_id,
                parent_id=parent_id,
                is_pinned=False,
                is_deleted=False,
                like_count=0,
                reply_count=0,
                created_at=now,
                updated_at=now,
            )
            db.add(post)
            if parent:
                parent.reply_count = (parent.reply_count or 0) + 1
            game.post_count = (game.post_count or 0) + 1
            db.commit()

            author = db.query(WebUser).filter_by(id=user_id).first()
            return JsonResponse({'ok': True, 'post': {
                'id': post.id,
                'parent_id': parent_id,
                'content': post.content or '',
                'media_url': post.media_url or '',
                'media_type': post.media_type or '',
                'game_tag_name': post.game_tag_name or '',
                'game_tag_steam_id': post.game_tag_steam_id or 0,
                'is_pinned': False,
                'reply_count': 0,
                'like_count': 0,
                'liked': False,
                'created_at': now,
                'author_id': user_id,
                'author_username': author.username if author else '',
                'author_display_name': (author.display_name or author.username) if author else '',
                'author_avatar': author.avatar_url or '' if author else '',
                'is_mine': True,
                'can_delete': True,
                'can_pin': is_admin or is_dev,
                'replies': [],
            }})

        # GET - paginated wall posts
        page = safe_int(request.GET.get('page', 1), 1, 1, 100)
        limit = 20
        offset = (page - 1) * limit

        pinned = db.query(WebCommunityPost).filter(
            WebCommunityPost.indie_game_id == game.id,
            WebCommunityPost.is_deleted == False,
            WebCommunityPost.is_pinned == True,
            WebCommunityPost.parent_id == None,
        ).order_by(WebCommunityPost.created_at.desc()).all()

        regular = db.query(WebCommunityPost).filter(
            WebCommunityPost.indie_game_id == game.id,
            WebCommunityPost.is_deleted == False,
            WebCommunityPost.is_pinned == False,
            WebCommunityPost.parent_id == None,
        ).order_by(WebCommunityPost.created_at.desc()).offset(offset).limit(limit).all()

        all_top = pinned + regular
        top_ids = [p.id for p in all_top]

        all_descendants = []
        parent_ids = top_ids[:]
        seen_ids = set(top_ids)
        while parent_ids:
            children = db.query(WebCommunityPost).filter(
                WebCommunityPost.parent_id.in_(parent_ids),
                WebCommunityPost.is_deleted == False,
            ).order_by(WebCommunityPost.created_at.asc()).all()
            new_children = [c for c in children if c.id not in seen_ids]
            all_descendants.extend(new_children)
            seen_ids.update(c.id for c in new_children)
            parent_ids = [c.id for c in new_children]

        liked_ids = set()
        if user_id:
            all_ids = top_ids + [r.id for r in all_descendants]
            if all_ids:
                likes = db.query(WebCommunityPostLike.post_id).filter(
                    WebCommunityPostLike.user_id == user_id,
                    WebCommunityPostLike.post_id.in_(all_ids),
                ).all()
                liked_ids = {r[0] for r in likes}

        def serialize(p, depth=0):
            a = p.author
            return {
                'id': p.id,
                'parent_id': p.parent_id,
                'content': p.content or '',
                'media_url': p.media_url or '',
                'media_type': p.media_type or '',
                'game_tag_name': p.game_tag_name or '',
                'game_tag_steam_id': p.game_tag_steam_id or 0,
                'is_pinned': p.is_pinned,
                'reply_count': p.reply_count or 0,
                'like_count': p.like_count,
                'liked': p.id in liked_ids,
                'created_at': p.created_at,
                'author_id': p.author_id,
                'author_username': a.username if a else '',
                'author_display_name': (a.display_name or a.username) if a else '',
                'author_avatar': a.avatar_url or '' if a else '',
                'is_mine': p.author_id == user_id,
                'can_delete': p.author_id == user_id or is_admin or is_dev,
                'can_pin': is_admin or is_dev,
                'replies': [],
            }

        children_by_parent = {}
        for r in all_descendants:
            children_by_parent.setdefault(r.parent_id, []).append(r)

        def serialize_tree(p, depth=0):
            s = serialize(p, depth)
            s['replies'] = [serialize_tree(c, depth + 1) for c in children_by_parent.get(p.id, [])]
            return s

        return JsonResponse({
            'posts': [serialize_tree(p) for p in all_top],
            'has_more': len(regular) == limit,
            'can_post': bool(user_id),
            'is_admin': is_admin,
            'is_dev': is_dev,
        })


@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@api_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_indie_wall_action(request, slug, post_id):
    """Pin/unpin, delete, like, unlike a wall post."""
    user_id = request.web_user.id
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')
    if action not in ('delete', 'pin', 'unpin', 'like', 'unlike'):
        return JsonResponse({'error': 'Invalid action'}, status=400)

    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)

        post = db.query(WebCommunityPost).filter_by(id=post_id, indie_game_id=game.id, is_deleted=False).first()
        if not post:
            return JsonResponse({'error': 'Not found'}, status=404)

        is_admin = request.web_user.is_admin
        is_dev = game.dev_user_id == user_id
        can_manage = is_admin or is_dev

        if action == 'delete':
            if post.author_id != user_id and not can_manage:
                return JsonResponse({'error': 'Forbidden'}, status=403)
            post.is_deleted = True
            if post.parent_id:
                parent = db.query(WebCommunityPost).filter_by(id=post.parent_id).first()
                if parent:
                    parent.reply_count = max(0, (parent.reply_count or 1) - 1)
            game.post_count = max(0, (game.post_count or 1) - 1)
            db.commit()
            return JsonResponse({'ok': True, 'parent_id': post.parent_id})

        if action in ('pin', 'unpin'):
            if not can_manage:
                return JsonResponse({'error': 'Forbidden'}, status=403)
            post.is_pinned = (action == 'pin')
            db.commit()
            return JsonResponse({'ok': True, 'is_pinned': post.is_pinned})

        if action == 'like':
            existing = db.query(WebCommunityPostLike).filter_by(post_id=post_id, user_id=user_id).first()
            if not existing:
                db.add(WebCommunityPostLike(post_id=post_id, user_id=user_id, created_at=int(time.time())))
                post.like_count = max(0, post.like_count + 1)
                db.commit()
            return JsonResponse({'ok': True, 'like_count': post.like_count})

        if action == 'unlike':
            existing = db.query(WebCommunityPostLike).filter_by(post_id=post_id, user_id=user_id).first()
            if existing:
                db.delete(existing)
                post.like_count = max(0, post.like_count - 1)
                db.commit()
            return JsonResponse({'ok': True, 'like_count': post.like_count})


@api_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_indie_game_dev_edit(request, slug):
    """Dev edits their own game's dev section (bio, devlog, links, community)."""
    user_id = request.web_user.id
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)

        is_admin = request.web_user.is_admin
        is_dev = game.dev_user_id == user_id

        if not is_admin and not is_dev:
            return JsonResponse({'error': 'Forbidden'}, status=403)

        def clean_url(val, max_len=500):
            v = (val or '').strip()[:max_len]
            if v and not v.startswith('http'):
                v = 'https://' + v
            return v or None

        game.dev_bio = sanitize_text(data.get('dev_bio', '') or '', max_length=2000) or None
        game.dev_devlog = sanitize_text(data.get('dev_devlog', '') or '', max_length=5000) or None
        # Dev can edit spotlight quote/text but NOT status (admin only)
        if 'spotlight_quote' in data:
            game.spotlight_quote = sanitize_text(data.get('spotlight_quote', '') or '', max_length=300) or None
        if 'spotlight_text' in data:
            game.spotlight_text = sanitize_text(data.get('spotlight_text', '') or '', max_length=5000) or None
        game.dev_website = clean_url(data.get('dev_website'))
        game.dev_twitter = (data.get('dev_twitter') or '').strip()[:200] or None
        game.dev_discord_url = clean_url(data.get('dev_discord_url'))
        game.dev_fluxer_url = clean_url(data.get('dev_fluxer_url'))
        game.dev_steam_url = clean_url(data.get('dev_steam_url'))
        game.dev_itch_url = clean_url(data.get('dev_itch_url'))
        game.dev_youtube_url = clean_url(data.get('dev_youtube_url'))
        game.dev_twitch_url = clean_url(data.get('dev_twitch_url'))
        game.dev_tiktok_url = clean_url(data.get('dev_tiktok_url'))
        game.dev_instagram_url = clean_url(data.get('dev_instagram_url'))
        game.dev_facebook_url = clean_url(data.get('dev_facebook_url'))
        game.dev_bsky_url = clean_url(data.get('dev_bsky_url'))
        game.dev_kick_url = clean_url(data.get('dev_kick_url'))

        # Community link - only their own registered community
        community_id = safe_int(data.get('community_id'), None)
        if community_id:
            from .models import WebCommunityMember
            community = db.query(WebCommunity).filter_by(id=community_id, is_active=True).first()
            if community and (community.owner_id == user_id or is_admin):
                game.community_id = community_id
            elif is_admin:
                game.community_id = community_id
        elif 'community_id' in data:
            game.community_id = None

        game.dev_edited_at = int(time.time())
        game.updated_at = int(time.time())
        db.commit()

        return JsonResponse({'ok': True, 'dev_edited_at': game.dev_edited_at,
                             'spotlight_quote': game.spotlight_quote or '',
                             'spotlight_text': game.spotlight_text or ''})


@web_admin_required
@add_web_user_context
@require_http_methods(['POST'])
def api_indie_game_admin(request):
    """Admin: add a new indie game."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name = (data.get('name') or '').strip()[:500]
    if not name:
        return JsonResponse({'error': 'Name required'}, status=400)

    now = int(time.time())

    with get_db_session() as db:
        base_slug = _slugify(name)
        slug = _unique_slug(db, base_slug)

        game = WebIndieGame(
            slug=slug,
            name=name,
            steam_app_id=safe_int(data.get('steam_app_id'), None) or None,
            steam_url=(data.get('steam_url') or '').strip()[:500] or None,
            igdb_id=safe_int(data.get('igdb_id'), None) or None,
            igdb_url=(data.get('igdb_url') or '').strip()[:500] or None,
            cover_url=validate_admin_image_url((data.get('cover_url') or '').strip()) or None,
            banner_url=validate_admin_image_url((data.get('banner_url') or '').strip()) or None,
            platforms=json.dumps(data.get('platforms') or []),
            genres=json.dumps(data.get('genres') or []),
            steam_tags=json.dumps(data.get('steam_tags') or []),
            spotlight_text=sanitize_text(data.get('spotlight_text', '') or '', max_length=5000) or None,
            spotlight_quote=(data.get('spotlight_quote') or '').strip()[:500] or None,
            release_date=(data.get('release_date') or '').strip()[:100] or None,
            price=(data.get('price') or '').strip()[:50] or None,
            review_score=safe_int(data.get('review_score'), None) or None,
            status=data.get('status', 'featured') if data.get('status') in ('featured', 'new', 'spotlight', 'alumni') else 'featured',
            is_published=bool(data.get('is_published', False)),
            is_featured=bool(data.get('is_featured', False)),
            source='ch_spotlight',
            added_by=request.web_user.id,
            dev_user_id=safe_int(data.get('dev_user_id'), None) or None,
            post_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(game)
        db.commit()
        return JsonResponse({'ok': True, 'slug': game.slug, 'id': game.id})


@web_admin_required
@add_web_user_context
@require_http_methods(['POST'])
def api_indie_game_admin_update(request, slug):
    """Admin: update an existing indie game (spotlight text, status, assign dev, publish, etc.)."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)

        if 'name' in data:
            game.name = (data['name'] or '').strip()[:500] or game.name
        if 'spotlight_text' in data:
            game.spotlight_text = sanitize_text(data.get('spotlight_text', '') or '', max_length=5000) or None
        if 'spotlight_quote' in data:
            game.spotlight_quote = (data.get('spotlight_quote') or '').strip()[:500] or None
        if 'status' in data and data['status'] in ('featured', 'new', 'spotlight', 'alumni'):
            game.status = data['status']
        if 'is_published' in data:
            game.is_published = bool(data['is_published'])
        if 'is_featured' in data:
            game.is_featured = bool(data['is_featured'])
        if 'dev_user_id' in data:
            game.dev_user_id = safe_int(data.get('dev_user_id'), None) or None
        if 'cover_url' in data:
            game.cover_url = validate_admin_image_url((data.get('cover_url') or '').strip()) or None
        if 'banner_url' in data:
            game.banner_url = validate_admin_image_url((data.get('banner_url') or '').strip()) or None
        if 'platforms' in data:
            game.platforms = json.dumps(data.get('platforms') or [])
        if 'genres' in data:
            game.genres = json.dumps(data.get('genres') or [])
        if 'release_date' in data:
            game.release_date = (data.get('release_date') or '').strip()[:100] or None
        if 'price' in data:
            game.price = (data.get('price') or '').strip()[:50] or None
        if 'review_score' in data:
            game.review_score = safe_int(data.get('review_score'), None) or None

        game.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'ok': True, 'game': _serialize_game(game)})


@add_web_user_context
@web_admin_required
@require_http_methods(['DELETE'])
def api_indie_game_delete(request, slug):
    """Admin: permanently delete an indie game entry."""
    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)
        # Delete wall posts first to avoid FK issues
        db.query(WebCommunityPost).filter_by(indie_game_id=game.id).delete(synchronize_session=False)
        db.delete(game)
        db.commit()
    return JsonResponse({'ok': True})


@ratelimit(key='ip', rate='5/h', method='POST', block=True)
@api_login_required
@require_http_methods(['POST'])
def api_indie_dev_register(request):
    """Apply for a dev account - sets indie_dev_pending=True for admin approval."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)
        if user.is_indie_dev:
            return JsonResponse({'ok': True, 'already_dev': True})
        if user.indie_dev_pending:
            return JsonResponse({'ok': True, 'pending': True, 'message': 'Your dev application is already pending review.'})
        user.indie_dev_pending = True
        user.updated_at = int(time.time())
        db.commit()
    return JsonResponse({'ok': True, 'pending': True, 'message': 'Your dev application has been submitted. You\'ll be notified once approved.'})


@ratelimit(key='ip', rate='5/h', method='POST', block=True)
@api_login_required
@require_http_methods(['POST'])
def api_indie_submit(request):
    """Dev submits a new game - requires an approved dev account."""
    user_id = request.web_user.id

    # Gate: must be an approved indie dev
    if not request.web_user.is_indie_dev:
        if request.web_user.indie_dev_pending:
            return JsonResponse({'error': 'Your dev account application is pending admin approval. Check back soon.'}, status=403)
        return JsonResponse({'error': 'You need a dev account to submit a game. Apply from the Indie Heroes page.'}, status=403)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    name       = sanitize_text(data.get('name', '') or '', max_length=200)
    pitch      = sanitize_text(data.get('pitch', '') or '', max_length=1000)
    steam_url  = (data.get('steam_url', '') or '').strip()[:500]
    itch_url   = (data.get('itch_url', '') or '').strip()[:500]
    # fallback: old single-field clients send 'link'
    link       = steam_url or itch_url or (data.get('link', '') or '').strip()[:500]

    if not name:
        return JsonResponse({'error': 'Game name is required'}, status=400)
    if not pitch:
        return JsonResponse({'error': 'A description is required'}, status=400)
    if not link:
        return JsonResponse({'error': 'Please add a Steam or itch.io link'}, status=400)

    with get_db_session() as db:
        # Check if dev already has a pending submission
        existing = db.query(WebIndieGame).filter(
            WebIndieGame.submitted_by == user_id,
            WebIndieGame.submission_status.in_(['pending', 'resubmitted']),
        ).first()
        if existing:
            return JsonResponse({'error': 'You already have a submission pending review.'}, status=400)

        now = int(time.time())
        base_slug = _unique_slug(db, _slugify(name))
        steam_app_id = _extract_steam_app_id(steam_url or link)
        cover_url = _steam_cover_url(steam_app_id)
        game = WebIndieGame(
            slug=base_slug,
            name=name,
            status='new',
            is_published=True,
            is_featured=False,
            source='self_submitted',
            submission_status='approved',
            submission_pitch=pitch,
            submission_link=link,
            steam_url=steam_url or None,
            dev_itch_url=itch_url or None,
            steam_app_id=steam_app_id,
            cover_url=cover_url,
            submitted_by=user_id,
            dev_user_id=user_id,
            added_by=user_id,
            platforms='[]',
            genres='[]',
            steam_tags='[]',
            post_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(game)
        db.commit()
        return JsonResponse({'ok': True, 'slug': game.slug})


@add_web_user_context
@api_login_required
@require_http_methods(['POST'])
def api_indie_resubmit(request, slug):
    """Dev resubmits a rejected game after updating their pitch/link."""
    user_id = request.web_user.id
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug, submitted_by=user_id).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)
        if game.submission_status != 'rejected':
            return JsonResponse({'error': 'Only rejected submissions can be resubmitted'}, status=400)

        pitch = sanitize_text(data.get('pitch', '') or '', max_length=1000)
        link = (data.get('link', '') or '').strip()[:500]
        if not pitch or not link:
            return JsonResponse({'error': 'Pitch and link are required'}, status=400)

        game.submission_pitch = pitch
        game.submission_link = link
        game.submission_status = 'resubmitted'
        game.submission_note = None
        game.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'ok': True})


@add_web_user_context
@web_admin_required
@require_http_methods(['GET'])
def api_indie_admin_submissions(request):

    with get_db_session() as db:
        # Self-submitted games awaiting review
        submitted = db.query(WebIndieGame).filter(
            WebIndieGame.submission_status.in_(['pending', 'resubmitted']),
        ).order_by(WebIndieGame.created_at.asc()).all()

        # CH-spotlight games with pending dev claim requests
        claims = db.query(WebIndieGame).filter(
            WebIndieGame.claim_status == 'pending_claim',
        ).order_by(WebIndieGame.created_at.asc()).all()

        def _sub(g):
            submitter_name = None
            if g.submitted_by:
                u = db.query(WebUser).filter_by(id=g.submitted_by).first()
                submitter_name = u.username if u else None
            return {
                'type': 'submission',
                'slug': g.slug,
                'name': g.name,
                'cover_url': g.cover_url or '',
                'submission_status': g.submission_status,
                'submission_pitch': g.submission_pitch or '',
                'submission_link': g.submission_link or '',
                'submission_note': g.submission_note or '',
                'submitted_by': g.submitted_by,
                'submitter_name': submitter_name,
                'created_at': g.created_at,
            }

        def _claim(g):
            claimant_name = None
            if g.claim_user_id:
                u = db.query(WebUser).filter_by(id=g.claim_user_id).first()
                claimant_name = u.username if u else None
            return {
                'type': 'claim',
                'slug': g.slug,
                'name': g.name,
                'cover_url': g.cover_url or '',
                'claim_status': g.claim_status,
                'claim_note': g.claim_note or '',
                'claim_user_id': g.claim_user_id,
                'claimant_name': claimant_name,
                'created_at': g.created_at,
            }

        return JsonResponse({
            'submissions': [_sub(g) for g in submitted],
            'claims': [_claim(g) for g in claims],
        })


@add_web_user_context
@web_admin_required
@require_http_methods(['POST'])
def api_indie_admin_review(request, slug):
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = (data.get('action') or '').strip()
    if action not in ('approve', 'reject'):
        return JsonResponse({'error': 'Invalid action'}, status=400)

    note = sanitize_text(data.get('note', '') or '', max_length=500)

    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)
        if game.submission_status not in ('pending', 'resubmitted'):
            return JsonResponse({'error': 'This submission is not awaiting review'}, status=400)

        if action == 'approve':
            game.is_published = True
            game.submission_status = 'approved'
            game.submission_note = None
        else:
            game.submission_status = 'rejected'
            game.submission_note = note or None

        game.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'ok': True, 'action': action})


@ratelimit(key='ip', rate='5/h', method='POST', block=True)
@add_web_user_context
@api_login_required
@require_http_methods(['POST'])
def api_indie_claim(request, slug):
    """Dev requests to claim a CH-spotlight game as their own."""
    user_id = request.web_user.id
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    note = sanitize_text(data.get('note', '') or '', max_length=1000)
    if not note:
        return JsonResponse({'error': 'Please tell us how to verify you are this game\'s developer'}, status=400)

    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug, is_published=True).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)
        if game.source != 'ch_spotlight':
            return JsonResponse({'error': 'This game is not claimable'}, status=400)
        if game.dev_user_id:
            return JsonResponse({'error': 'This game already has a verified developer'}, status=400)
        if game.claim_status == 'pending_claim':
            if game.claim_user_id == user_id:
                return JsonResponse({'error': 'You already have a pending claim for this game'}, status=400)
            return JsonResponse({'error': 'Another claim request is already pending review for this game'}, status=400)

        game.claim_status = 'pending_claim'
        game.claim_user_id = user_id
        game.claim_note = note
        game.updated_at = int(time.time())
        db.commit()
        return JsonResponse({'ok': True})


@add_web_user_context
@api_login_required
@require_http_methods(['POST'])
def api_indie_claim_review(request, slug):
    """Admin approves or denies a dev's claim on a CH-spotlight game."""
    if not (request.web_user and request.web_user.is_admin):
        return JsonResponse({'error': 'Forbidden'}, status=403)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = (data.get('action') or '').strip()
    if action not in ('approve', 'deny'):
        return JsonResponse({'error': 'Invalid action'}, status=400)

    with get_db_session() as db:
        game = db.query(WebIndieGame).filter_by(slug=slug).first()
        if not game:
            return JsonResponse({'error': 'Not found'}, status=404)
        if game.claim_status != 'pending_claim':
            return JsonResponse({'error': 'No pending claim for this game'}, status=400)

        if action == 'approve':
            game.dev_user_id = game.claim_user_id
            game.claim_status = 'claimed'
            game.updated_at = int(time.time())
        else:
            game.claim_status = None
            game.claim_user_id = None
            game.claim_note = None
            game.updated_at = int(time.time())

        db.commit()
        return JsonResponse({'ok': True, 'action': action})


@ratelimit(key='ip', rate='10/h', method='POST', block=True)
@add_web_user_context
@api_login_required
@require_http_methods(['POST'])
def api_indie_suggest(request):
    """Any logged-in user can suggest an indie game for CH to curate."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    game_name = sanitize_text(data.get('game_name', '') or '', max_length=200)
    steam_url = (data.get('steam_url', '') or '').strip()[:500]
    itch_url  = (data.get('itch_url', '') or '').strip()[:500]
    other_url = (data.get('other_url', '') or '').strip()[:500]
    note      = sanitize_text(data.get('note', '') or '', max_length=500)

    if not game_name:
        return JsonResponse({'error': 'Game name is required'}, status=400)
    if not (steam_url or itch_url or other_url):
        return JsonResponse({'error': 'Please add at least one link'}, status=400)

    with get_db_session() as db:
        # One pending suggestion per user per game name
        existing = db.query(WebIndieSuggestion).filter(
            WebIndieSuggestion.suggested_by == request.web_user.id,
            WebIndieSuggestion.game_name.ilike(game_name),
            WebIndieSuggestion.status == 'pending',
        ).first()
        if existing:
            return JsonResponse({'error': 'You already suggested this game.'}, status=400)

        s = WebIndieSuggestion(
            game_name=game_name,
            steam_url=steam_url or None,
            itch_url=itch_url or None,
            other_url=other_url or None,
            note=note or None,
            suggested_by=request.web_user.id,
            status='pending',
            created_at=int(time.time()),
        )
        db.add(s)
        db.commit()

    return JsonResponse({'ok': True})


@add_web_user_context
@web_admin_required
@require_http_methods(['GET'])
def api_indie_suggestions_list(request):
    """Admin: list pending game suggestions."""
    with get_db_session() as db:
        rows = db.query(WebIndieSuggestion).filter_by(status='pending').order_by(
            WebIndieSuggestion.created_at.desc()
        ).limit(100).all()

        suggestions = []
        for s in rows:
            user = db.query(WebUser).filter_by(id=s.suggested_by).first() if s.suggested_by else None
            suggestions.append({
                'id': s.id,
                'game_name': s.game_name,
                'steam_url': s.steam_url or '',
                'itch_url': s.itch_url or '',
                'other_url': s.other_url or '',
                'note': s.note or '',
                'suggested_by': user.username if user else 'anonymous',
                'created_at': s.created_at,
            })

    return JsonResponse({'suggestions': suggestions})


@add_web_user_context
@web_admin_required
@require_http_methods(['POST'])
def api_indie_suggestion_action(request, suggestion_id):
    """Admin: approve (convert to curated game) or dismiss a suggestion."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action', '')
    if action not in ('approve', 'dismiss'):
        return JsonResponse({'error': 'Invalid action'}, status=400)

    with get_db_session() as db:
        s = db.query(WebIndieSuggestion).filter_by(id=suggestion_id).first()
        if not s:
            return JsonResponse({'error': 'Not found'}, status=404)

        if action == 'dismiss':
            s.status = 'dismissed'
            db.commit()
            return JsonResponse({'ok': True})

        # approve: create a ch_spotlight game entry ready for admin to enrich
        now = int(time.time())
        base_slug = _unique_slug(db, _slugify(s.game_name))
        game = WebIndieGame(
            slug=base_slug,
            name=s.game_name,
            status='new',
            is_published=False,
            is_featured=False,
            source='ch_spotlight',
            steam_url=s.steam_url or None,
            dev_itch_url=s.itch_url or None,
            added_by=request.web_user.id,
            platforms='[]',
            genres='[]',
            steam_tags='[]',
            post_count=0,
            created_at=now,
            updated_at=now,
        )
        db.add(game)
        s.status = 'approved'
        db.commit()
        return JsonResponse({'ok': True, 'slug': game.slug})
