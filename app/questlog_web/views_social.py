# QuestLog Web — social features

import re
import json
import time
import random
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from sqlalchemy import or_, and_, func, case

from .models import (
    WebUser, WebFollow, WebPost, WebPostImage, WebLike,
    WebComment, WebCommentLike, WebNotification, WebUserBlock,
    WebFoundGame, WebCreatorProfile,
    WebGiveaway, WebGiveawayEntry,
)
from app.db import get_db_session
from .helpers import (
    web_login_required, add_web_user_context,
    check_banned, check_posting_timeout,
    is_blocked, create_notification,
    sanitize_text, parse_embed_url, reconstruct_embed_url, _is_valid_giphy_url,
    serialize_user_brief, serialize_post, award_hero_points, safe_int,
)

logger = logging.getLogger(__name__)


# =============================================================================
# BLOCK API
# =============================================================================

@web_login_required
@require_http_methods(["POST", "DELETE"])
def api_block(request, user_id):
    """POST: Block a user. DELETE: Unblock."""
    banned = check_banned(request)
    if banned:
        return banned

    if user_id == request.web_user.id:
        return JsonResponse({'error': 'Cannot block yourself'}, status=400)

    with get_db_session() as db:
        target = db.query(WebUser).filter_by(id=user_id).first()
        if not target:
            return JsonResponse({'error': 'User not found'}, status=404)

        if target.is_admin:
            return JsonResponse({'error': 'Cannot block administrators'}, status=403)

        if request.method == 'POST':
            existing = db.query(WebUserBlock).filter_by(
                blocker_id=request.web_user.id, blocked_id=user_id
            ).first()
            if existing:
                return JsonResponse({'success': True, 'is_blocked': True})

            block = WebUserBlock(
                blocker_id=request.web_user.id,
                blocked_id=user_id,
                created_at=int(time.time()),
            )
            db.add(block)

            # Remove any follow relationships in both directions
            follows_removed = 0
            follow1 = db.query(WebFollow).filter_by(
                follower_id=request.web_user.id, following_id=user_id
            ).first()
            if follow1:
                db.delete(follow1)
                follows_removed += 1
                me = db.query(WebUser).filter_by(id=request.web_user.id).first()
                if me and me.following_count > 0:
                    me.following_count -= 1
                if target.follower_count > 0:
                    target.follower_count -= 1

            follow2 = db.query(WebFollow).filter_by(
                follower_id=user_id, following_id=request.web_user.id
            ).first()
            if follow2:
                db.delete(follow2)
                follows_removed += 1
                me = db.query(WebUser).filter_by(id=request.web_user.id).first()
                if me and me.follower_count > 0:
                    me.follower_count -= 1
                if target.following_count > 0:
                    target.following_count -= 1

            db.commit()
            return JsonResponse({'success': True, 'is_blocked': True})

        else:  # DELETE
            block = db.query(WebUserBlock).filter_by(
                blocker_id=request.web_user.id, blocked_id=user_id
            ).first()
            if block:
                db.delete(block)
                db.commit()
            return JsonResponse({'success': True, 'is_blocked': False})


@web_login_required
def api_block_list(request):
    """GET: List users the current user has blocked."""
    with get_db_session() as db:
        blocks = db.query(WebUserBlock).filter_by(
            blocker_id=request.web_user.id
        ).order_by(WebUserBlock.created_at.desc()).all()

        blocked_ids = [b.blocked_id for b in blocks]
        users = {}
        if blocked_ids:
            for u in db.query(WebUser).filter(WebUser.id.in_(blocked_ids)).all():
                users[u.id] = u

        data = []
        for b in blocks:
            u = users.get(b.blocked_id)
            if u:
                d = serialize_user_brief(u)
                d['blocked_at'] = b.created_at
                data.append(d)

    return JsonResponse({'blocked_users': data})


# =============================================================================
# FOLLOW API
# =============================================================================

@web_login_required
@require_http_methods(["POST", "DELETE"])
@ratelimit(key='user', rate='60/h', method='POST', block=True)
def api_follow(request, user_id):
    """POST: Follow a user. DELETE: Unfollow."""
    banned = check_banned(request)
    if banned:
        return banned

    if user_id == request.web_user.id:
        return JsonResponse({'error': 'Cannot follow yourself'}, status=400)

    with get_db_session() as db:
        target = db.query(WebUser).filter_by(id=user_id).first()
        if not target:
            return JsonResponse({'error': 'User not found'}, status=404)

        if is_blocked(db, request.web_user.id, user_id):
            return JsonResponse({'error': 'Cannot follow this user'}, status=403)

        if request.method == 'POST':
            existing = db.query(WebFollow).filter_by(
                follower_id=request.web_user.id, following_id=user_id
            ).first()
            if existing:
                is_mutual = db.query(WebFollow).filter_by(
                    follower_id=user_id, following_id=request.web_user.id
                ).first() is not None
                return JsonResponse({
                    'success': True, 'is_following': True, 'is_mutual': is_mutual
                })

            follow = WebFollow(
                follower_id=request.web_user.id,
                following_id=user_id,
                created_at=int(time.time()),
            )
            db.add(follow)

            me = db.query(WebUser).filter_by(id=request.web_user.id).first()
            if me:
                me.following_count = (me.following_count or 0) + 1
            target.follower_count = (target.follower_count or 0) + 1

            create_notification(
                db, user_id=user_id, actor_id=request.web_user.id,
                notification_type='follow', target_type='user',
                target_id=request.web_user.id,
                message=f'{request.web_user.display_name or request.web_user.username} followed you'
            )

            db.commit()

            award_hero_points(request.web_user.id, 'follow', ref_id=str(user_id))

            is_mutual = db.query(WebFollow).filter_by(
                follower_id=user_id, following_id=request.web_user.id
            ).first() is not None
            return JsonResponse({
                'success': True, 'is_following': True, 'is_mutual': is_mutual
            })

        else:  # DELETE
            follow = db.query(WebFollow).filter_by(
                follower_id=request.web_user.id, following_id=user_id
            ).first()
            if follow:
                db.delete(follow)
                me = db.query(WebUser).filter_by(id=request.web_user.id).first()
                if me and me.following_count and me.following_count > 0:
                    me.following_count -= 1
                if target.follower_count and target.follower_count > 0:
                    target.follower_count -= 1
                db.commit()
            return JsonResponse({
                'success': True, 'is_following': False, 'is_mutual': False
            })


@add_web_user_context
def api_followers(request, user_id):
    """GET: List followers of a user. Paginated."""
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1)
    per_page = safe_int(request.GET.get('per_page', 20), default=20, min_val=1, max_val=50)
    offset = (page - 1) * per_page

    with get_db_session() as db:
        blocked_ids = set()
        if request.web_user:
            blocks = db.query(WebUserBlock).filter(
                or_(
                    WebUserBlock.blocker_id == request.web_user.id,
                    WebUserBlock.blocked_id == request.web_user.id,
                )
            ).all()
            for b in blocks:
                blocked_ids.add(b.blocker_id if b.blocked_id == request.web_user.id else b.blocked_id)

        query = db.query(WebFollow).filter_by(following_id=user_id)
        if blocked_ids:
            query = query.filter(~WebFollow.follower_id.in_(blocked_ids))

        total = query.count()
        follows = query.order_by(WebFollow.created_at.desc()).offset(offset).limit(per_page).all()

        follower_ids = [f.follower_id for f in follows]
        users = {}
        if follower_ids:
            for u in db.query(WebUser).filter(WebUser.id.in_(follower_ids)).all():
                users[u.id] = u

        # Find which of these followers the viewer also follows back
        my_following = set()
        if request.web_user and follower_ids:
            my_follows = db.query(WebFollow.following_id).filter(
                WebFollow.follower_id == request.web_user.id,
                WebFollow.following_id.in_(follower_ids)
            ).all()
            my_following = {f[0] for f in my_follows}

        data = []
        for f in follows:
            u = users.get(f.follower_id)
            if u:
                d = serialize_user_brief(u)
                d['is_following'] = f.follower_id in my_following
                d['followed_at'] = f.created_at
                data.append(d)

    return JsonResponse({'followers': data, 'total': total, 'page': page})


@add_web_user_context
def api_following(request, user_id):
    """GET: List who a user is following. Paginated."""
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1)
    per_page = safe_int(request.GET.get('per_page', 20), default=20, min_val=1, max_val=50)
    offset = (page - 1) * per_page

    with get_db_session() as db:
        blocked_ids = set()
        if request.web_user:
            blocks = db.query(WebUserBlock).filter(
                or_(
                    WebUserBlock.blocker_id == request.web_user.id,
                    WebUserBlock.blocked_id == request.web_user.id,
                )
            ).all()
            for b in blocks:
                blocked_ids.add(b.blocker_id if b.blocked_id == request.web_user.id else b.blocked_id)

        query = db.query(WebFollow).filter_by(follower_id=user_id)
        if blocked_ids:
            query = query.filter(~WebFollow.following_id.in_(blocked_ids))

        total = query.count()
        follows = query.order_by(WebFollow.created_at.desc()).offset(offset).limit(per_page).all()

        following_ids = [f.following_id for f in follows]
        users = {}
        if following_ids:
            for u in db.query(WebUser).filter(WebUser.id.in_(following_ids)).all():
                users[u.id] = u

        # Mark which of these accounts follow the user back (mutual)
        follows_back = set()
        if following_ids:
            reverse = db.query(WebFollow.follower_id).filter(
                WebFollow.following_id == user_id,
                WebFollow.follower_id.in_(following_ids)
            ).all()
            follows_back = {f[0] for f in reverse}

        data = []
        for f in follows:
            u = users.get(f.following_id)
            if u:
                d = serialize_user_brief(u)
                d['is_following_back'] = f.following_id in follows_back
                d['followed_at'] = f.created_at
                data.append(d)

    return JsonResponse({'following': data, 'total': total, 'page': page})


@web_login_required
def api_follow_status(request, user_id):
    """GET: Check follow status between current user and target."""
    with get_db_session() as db:
        is_following = db.query(WebFollow).filter_by(
            follower_id=request.web_user.id, following_id=user_id
        ).first() is not None

        is_followed_by = db.query(WebFollow).filter_by(
            follower_id=user_id, following_id=request.web_user.id
        ).first() is not None

        blocked = is_blocked(db, request.web_user.id, user_id)

    return JsonResponse({
        'is_following': is_following,
        'is_followed_by': is_followed_by,
        'is_mutual': is_following and is_followed_by,
        'is_blocked': blocked,
    })


# =============================================================================
# POST API
# =============================================================================

@web_login_required
@require_http_methods(["GET", "POST"])
@ratelimit(key='user', rate='10/h', method='POST', block=True)
@ratelimit(key='ip', rate='60/h', method='POST', block=True)
def api_posts(request):
    """GET: Feed posts. POST: Create post."""
    if request.method == 'GET':
        return _get_feed_posts(request)

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

    content = sanitize_text(data.get('content', ''), max_length=2000)
    post_type = data.get('post_type', 'text')
    if post_type not in ('text', 'image', 'video_embed', 'game_tag', 'gif'):
        return JsonResponse({'error': 'Invalid post type'}, status=400)

    # Must have content or media
    media_urls = data.get('media_urls', [])
    embed_url = data.get('embed_url', '')
    gif_url = data.get('gif_url', '')
    game_tag_id = data.get('game_tag_id')

    if not content and not media_urls and not embed_url and not gif_url:
        return JsonResponse({'error': 'Post must have content or media'}, status=400)

    try:
        with get_db_session() as db:
            now = int(time.time())
            post = WebPost(
                author_id=request.web_user.id,
                content=content,
                post_type=post_type,
                created_at=now,
                updated_at=now,
            )

            # GIFs must come from GIPHY's CDN — reject anything else
            if post_type == 'gif' and gif_url:
                if not _is_valid_giphy_url(gif_url):
                    return JsonResponse({'error': 'Invalid GIF source'}, status=400)
                thumb = data.get('gif_thumbnail', gif_url)
                if thumb and not _is_valid_giphy_url(thumb):
                    thumb = gif_url
                post.media_url = gif_url
                post.thumbnail_url = thumb

            # Handle explicit video embed
            if post_type == 'video_embed' and embed_url:
                platform, vid_id = parse_embed_url(embed_url)
                if not platform:
                    return JsonResponse({'error': 'Invalid or unsupported video URL'}, status=400)
                post.embed_platform = platform
                post.embed_id = vid_id
                post.media_url = embed_url.strip()

            # Auto-detect video URLs in text content (for text/game_tag posts)
            if post_type in ('text', 'game_tag') and content and not post.embed_platform:
                urls = re.findall(r'https?://[^\s<]+', content)
                for url in urls:
                    platform, vid_id = parse_embed_url(url)
                    if platform:
                        post.embed_platform = platform
                        post.embed_id = vid_id
                        post.media_url = reconstruct_embed_url(platform, vid_id)
                        if post_type == 'text':
                            post.post_type = 'video_embed'
                        break

            # Handle game tag (supports both WebFoundGame IDs and IGDB IDs)
            if game_tag_id:
                game_tag_name_input = data.get('game_tag_name', '').strip()
                game_tag_steam_id = data.get('game_tag_steam_id')
                # Try local WebFoundGame first
                game = db.query(WebFoundGame).filter_by(id=game_tag_id).first()
                if game:
                    post.game_tag_id = game.id
                    post.game_tag_name = game.name
                    post.game_tag_steam_id = game.steam_app_id
                elif game_tag_name_input:
                    # IGDB game - only store the name (no FK since IGDB ID isn't in web_found_games)
                    post.game_tag_name = sanitize_text(game_tag_name_input, max_length=100)
                    if game_tag_steam_id:
                        post.game_tag_steam_id = int(game_tag_steam_id)
                if post.game_tag_name and (not post_type or post_type == 'text'):
                    post.post_type = 'game_tag'

            db.add(post)
            db.flush()  # Get post.id

            # media_urls are pre-uploaded via /api/upload/image/ — just store the references
            if media_urls and post_type == 'image':
                for i, img_data in enumerate(media_urls[:4]):
                    if isinstance(img_data, dict) and img_data.get('image_url'):
                        post_image = WebPostImage(
                            post_id=post.id,
                            image_url=img_data['image_url'],
                            thumbnail_url=img_data.get('thumbnail_url', img_data['image_url']),
                            sort_order=i,
                            file_size=img_data.get('file_size', 0),
                            width=img_data.get('width'),
                            height=img_data.get('height'),
                            created_at=now,
                        )
                        db.add(post_image)
                        if i == 0:
                            post.media_url = img_data['image_url']
                            post.thumbnail_url = img_data.get('thumbnail_url', img_data['image_url'])

            user = db.query(WebUser).filter_by(id=request.web_user.id).first()
            if user:
                user.post_count = (user.post_count or 0) + 1
                user.last_post_at = now

            db.commit()
            award_hero_points(request.web_user.id, 'post', ref_id=str(post.id))

            # Refetch to populate relationships (author, images)
            post = db.query(WebPost).filter_by(id=post.id).first()
            post_data = serialize_post(post, request.web_user.id, db)

        return JsonResponse({'success': True, 'post': post_data}, status=201)
    except Exception as e:
        logger.error(f"Post creation error: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to create post. Please try again.'}, status=500)


def _get_feed_posts(request):
    """Get feed posts for current user (posts from followed users + own)."""
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1)
    per_page = safe_int(request.GET.get('per_page', 20), default=20, min_val=1, max_val=50)
    offset = (page - 1) * per_page

    with get_db_session() as db:
        following = db.query(WebFollow.following_id).filter_by(
            follower_id=request.web_user.id
        ).all()
        following_ids = [f[0] for f in following]
        following_ids.append(request.web_user.id)  # Include own posts
        following_ids_set = frozenset(following_ids)

        blocked_ids = set()
        blocks = db.query(WebUserBlock).filter(
            or_(
                WebUserBlock.blocker_id == request.web_user.id,
                WebUserBlock.blocked_id == request.web_user.id,
            )
        ).all()
        for b in blocks:
            blocked_ids.add(b.blocker_id if b.blocked_id == request.web_user.id else b.blocked_id)

        query = db.query(WebPost).filter(
            WebPost.author_id.in_(following_ids),
            WebPost.is_deleted == False,
            WebPost.is_hidden == False,
        )
        if blocked_ids:
            query = query.filter(~WebPost.author_id.in_(blocked_ids))

        total = query.count()
        posts = query.order_by(WebPost.created_at.desc()).offset(offset).limit(per_page).all()

        data = [serialize_post(p, request.web_user.id, db, following_ids=following_ids_set) for p in posts]

    return JsonResponse({
        'posts': data, 'total': total, 'page': page,
        'has_more': (offset + per_page) < total,
    })


@add_web_user_context
@require_http_methods(["GET", "PUT", "DELETE"])
def api_post_detail(request, post_id):
    """GET: Single post. PUT: Edit (author/admin). DELETE: Soft-delete."""
    with get_db_session() as db:
        post = db.query(WebPost).filter_by(id=post_id).first()
        if not post or post.is_deleted:
            return JsonResponse({'error': 'Post not found'}, status=404)

        if request.method == 'GET':
            if post.is_hidden and (not request.web_user or not request.web_user.is_admin):
                return JsonResponse({'error': 'Post not found'}, status=404)
            if request.web_user and is_blocked(db, request.web_user.id, post.author_id):
                return JsonResponse({'error': 'Post not found'}, status=404)
            data = serialize_post(
                post, request.web_user.id if request.web_user else None, db
            )
            return JsonResponse({'post': data})

        # PUT/DELETE require auth
        if not request.web_user:
            return JsonResponse({'error': 'Authentication required'}, status=401)

        banned = check_banned(request)
        if banned:
            return banned

        is_author = post.author_id == request.web_user.id
        is_admin = request.web_user.is_admin

        if not is_author and not is_admin:
            return JsonResponse({'error': 'Not authorized'}, status=403)

        if request.method == 'PUT':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            if 'content' in data:
                post.content = sanitize_text(data['content'], max_length=2000)
            if 'game_tag_id' in data:
                game = db.query(WebFoundGame).filter_by(id=data['game_tag_id']).first()
                if game:
                    post.game_tag_id = game.id
                    post.game_tag_name = game.name
            post.updated_at = int(time.time())
            db.commit()
            return JsonResponse({'success': True, 'post': serialize_post(post, request.web_user.id, db)})

        else:  # DELETE
            post.is_deleted = True
            post.updated_at = int(time.time())
            user = db.query(WebUser).filter_by(id=post.author_id).first()
            if user and user.post_count and user.post_count > 0:
                user.post_count -= 1
            db.commit()
            return JsonResponse({'success': True})


@add_web_user_context
def api_user_posts(request, user_id):
    """GET: All posts by a specific user. Paginated."""
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1)
    per_page = safe_int(request.GET.get('per_page', 20), default=20, min_val=1, max_val=50)
    offset = (page - 1) * per_page

    with get_db_session() as db:
        target_user = db.query(WebUser).filter_by(id=user_id).first()
        if not target_user or target_user.is_banned or target_user.is_disabled:
            return JsonResponse({'posts': [], 'total': 0, 'page': page, 'has_more': False})

        if request.web_user and is_blocked(db, request.web_user.id, user_id):
            return JsonResponse({'posts': [], 'total': 0, 'page': page, 'has_more': False})

        query = db.query(WebPost).filter(
            WebPost.author_id == user_id,
            WebPost.is_deleted == False,
            WebPost.is_hidden == False,
        )
        total = query.count()
        posts = query.order_by(WebPost.created_at.desc()).offset(offset).limit(per_page).all()

        current_uid = request.web_user.id if request.web_user else None
        data = [serialize_post(p, current_uid, db) for p in posts]

    return JsonResponse({
        'posts': data, 'total': total, 'page': page,
        'has_more': (offset + per_page) < total,
    })


@add_web_user_context
@require_http_methods(["GET"])
def api_global_posts(request):
    """GET: Recent public posts from all users (global discovery feed).
    No auth required - shows all non-deleted, non-hidden public posts.
    Respects blocks for logged-in users."""
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1)
    per_page = safe_int(request.GET.get('per_page', 20), default=20, min_val=1, max_val=50)
    offset = (page - 1) * per_page

    with get_db_session() as db:
        # Always exclude posts from banned or non-discoverable authors
        hidden_ids = [u.id for u in db.query(WebUser.id).filter(
            (WebUser.is_banned == True) | (WebUser.allow_discovery == False)
        ).all()]
        query = db.query(WebPost).filter(
            WebPost.is_deleted == False,
            WebPost.is_hidden == False,
        )
        if hidden_ids:
            query = query.filter(~WebPost.author_id.in_(hidden_ids))

        if request.web_user:
            blocked_ids = set()
            blocks = db.query(WebUserBlock).filter(
                or_(
                    WebUserBlock.blocker_id == request.web_user.id,
                    WebUserBlock.blocked_id == request.web_user.id,
                )
            ).all()
            for b in blocks:
                blocked_ids.add(b.blocker_id if b.blocked_id == request.web_user.id else b.blocked_id)
            if blocked_ids:
                query = query.filter(~WebPost.author_id.in_(blocked_ids))

        total = query.count()
        posts = query.order_by(WebPost.created_at.desc()).offset(offset).limit(per_page).all()

        current_uid = request.web_user.id if request.web_user else None
        global_following_ids = None
        if request.web_user:
            follows = db.query(WebFollow.following_id).filter_by(
                follower_id=request.web_user.id
            ).all()
            global_following_ids = frozenset(f[0] for f in follows) | {request.web_user.id}
        data = [serialize_post(p, current_uid, db, following_ids=global_following_ids) for p in posts]

    return JsonResponse({
        'posts': data, 'total': total, 'page': page,
        'has_more': (offset + per_page) < total,
    })


@add_web_user_context
@require_http_methods(["GET"])
def api_recent_activity(request):
    """GET: Rich platform activity data for the home page.
    Returns stats, trending games, suggested gamers, and activity ticker."""
    try:
        return _get_recent_activity(request)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Activity API error: {e}", exc_info=True)
        return JsonResponse({
            'total_users': 0, 'total_posts': 0, 'posts_today': 0,
            'active_posters_today': 0, 'suggested_gamers': [],
            'new_members': [], 'trending_games': [], 'ticker': [],
            'error': str(e),
        })


def _get_recent_activity(request):
    """Internal: fetch activity data."""
    with get_db_session() as db:
        now = int(time.time())
        day_ago = now - 86400
        week_ago = now - 604800

        total_users = db.query(WebUser).filter(
            WebUser.is_banned == False,
            WebUser.is_disabled == False,
        ).count()

        # Exclude posts from banned/disabled authors in all counts
        banned_author_ids = [
            row[0] for row in db.query(WebUser.id).filter(
                (WebUser.is_banned == True) | (WebUser.is_disabled == True)
            ).all()
        ]
        post_base = db.query(WebPost).filter(WebPost.is_deleted == False)
        if banned_author_ids:
            post_base = post_base.filter(~WebPost.author_id.in_(banned_author_ids))

        total_posts = post_base.count()
        posts_today = post_base.filter(WebPost.created_at >= day_ago).count()
        active_posters_q = post_base.filter(
            WebPost.created_at >= day_ago
        ).with_entities(WebPost.author_id).distinct().count()

        current_uid = request.web_user.id if request.web_user else None
        suggested_q = db.query(WebUser).filter(
            WebUser.is_banned == False,
            WebUser.allow_discovery == True,
            WebUser.post_count > 0,
        )
        if current_uid:
            following_ids = [f[0] for f in db.query(WebFollow.following_id).filter_by(
                follower_id=current_uid
            ).all()]
            following_ids.append(current_uid)
            suggested_q = suggested_q.filter(~WebUser.id.in_(following_ids))
            blocked_ids = set()
            blocks = db.query(WebUserBlock).filter(
                or_(
                    WebUserBlock.blocker_id == current_uid,
                    WebUserBlock.blocked_id == current_uid,
                )
            ).all()
            for b in blocks:
                blocked_ids.add(b.blocker_id if b.blocked_id == current_uid else b.blocked_id)
            if blocked_ids:
                suggested_q = suggested_q.filter(~WebUser.id.in_(blocked_ids))

        # Random selection from active users so the list varies each page load
        suggested_users = suggested_q.order_by(func.rand()).limit(6).all()

        # Batch-fetch creator profiles to avoid N+1
        suggested_ids = [u.id for u in suggested_users]
        cp_map = {}
        if suggested_ids:
            cps = db.query(WebCreatorProfile).filter(
                WebCreatorProfile.user_id.in_(suggested_ids)
            ).all()
            cp_map = {cp.user_id: cp for cp in cps}

        suggested_data = []
        for u in suggested_users:
            cp = cp_map.get(u.id)
            raw_ps = u.playstyle or ''
            ps_list = (
                json.loads(raw_ps) if raw_ps.startswith('[')
                else ([raw_ps] if raw_ps else [])
            )
            suggested_data.append({
                'id': u.id,
                'username': u.username,
                'display_name': u.display_name or u.username,
                'avatar_url': u.avatar_url or '',
                'bio': (u.bio or '')[:120],
                'post_count': u.post_count or 0,
                'follower_count': u.follower_count or 0,
                'playstyle': ps_list,
                'gaming_platforms': json.loads(u.gaming_platforms) if u.gaming_platforms else [],
                'favorite_genres': json.loads(u.favorite_genres) if u.favorite_genres else [],
                'twitch_username': u.twitch_username or '',
                'youtube_channel_name': u.youtube_channel_name or '',
                'twitter_url': (cp.twitter_url or '') if cp else '',
                'bluesky_url': (cp.bluesky_url or '') if cp else '',
                'tiktok_url': (cp.tiktok_url or '') if cp else '',
                'instagram_url': (cp.instagram_url or '') if cp else '',
                'website_url': (cp.website_url or '') if cp else '',
            })

        # New members this week — used as sidebar fallback when no suggested users
        new_members_q = db.query(WebUser).filter(
            WebUser.created_at >= week_ago,
            WebUser.is_banned == False,
            WebUser.is_disabled == False,
            WebUser.email_verified == True,
            WebUser.allow_discovery == True,
        )
        if current_uid:
            new_members_q = new_members_q.filter(~WebUser.id.in_(following_ids))
        new_members = new_members_q.order_by(func.rand()).limit(6).all()
        new_members_data = [{
            'id': u.id,
            'username': u.username,
            'display_name': u.display_name or u.username,
            'avatar_url': u.avatar_url or '',
            'bio': (u.bio or '')[:80],
            'playstyle': u.playstyle or '',
            'gaming_platforms': json.loads(u.gaming_platforms) if u.gaming_platforms else [],
            'twitch_username': u.twitch_username or '',
            'youtube_channel_name': u.youtube_channel_name or '',
            'follower_count': u.follower_count or 0,
        } for u in new_members]

        trending_q = db.query(
            WebPost.game_tag_id,
            WebPost.game_tag_name,
            func.count(WebPost.id).label('post_count')
        ).filter(
            WebPost.game_tag_id.isnot(None),
            WebPost.is_deleted == False,
            WebPost.created_at >= week_ago,
        )
        if banned_author_ids:
            trending_q = trending_q.filter(~WebPost.author_id.in_(banned_author_ids))
        trending_games_q = trending_q.group_by(
            WebPost.game_tag_id, WebPost.game_tag_name
        ).order_by(func.count(WebPost.id).desc()).limit(8).all()

        trending_games = []
        if trending_games_q:
            game_ids = [g[0] for g in trending_games_q]
            games_map = {}
            if game_ids:
                games = db.query(WebFoundGame).filter(WebFoundGame.id.in_(game_ids)).all()
                games_map = {g.id: g for g in games}
            for game_tag_id, game_tag_name, pc in trending_games_q:
                game = games_map.get(game_tag_id)
                trending_games.append({
                    'id': game_tag_id,
                    'name': game_tag_name,
                    'cover_url': game.cover_url if game else None,
                    'post_count': pc,
                })

        ticker = []
        two_hours_ago = now - 7200
        recent_posts = db.query(WebPost).filter(
            WebPost.is_deleted == False,
            WebPost.is_hidden == False,
            WebPost.created_at >= two_hours_ago,
        ).order_by(WebPost.created_at.desc()).limit(10).all()
        for p in recent_posts:
            author = p.author
            if author and not author.is_banned and not author.is_disabled and author.allow_discovery:
                msg = f"posted"
                if p.game_tag_name:
                    msg += f" about {p.game_tag_name}"
                elif p.post_type == 'video_embed':
                    msg += " a video"
                elif p.post_type == 'image':
                    msg += " a photo"
                ticker.append({
                    'type': 'post',
                    'username': author.username,
                    'display_name': author.display_name or author.username,
                    'avatar_url': author.avatar_url or '',
                    'message': msg,
                    'timestamp': p.created_at,
                    'post_id': p.id,
                })

        recent_follows = db.query(WebFollow).filter(
            WebFollow.created_at >= two_hours_ago,
        ).order_by(WebFollow.created_at.desc()).limit(10).all()
        for f in recent_follows:
            follower = db.query(WebUser).filter_by(id=f.follower_id).first()
            followed = db.query(WebUser).filter_by(id=f.following_id).first()
            if follower and followed and not follower.is_banned and not followed.is_banned and follower.allow_discovery and followed.allow_discovery:
                ticker.append({
                    'type': 'follow',
                    'username': follower.username,
                    'display_name': follower.display_name or follower.username,
                    'avatar_url': follower.avatar_url or '',
                    'message': f"followed {followed.display_name or followed.username}",
                    'timestamp': f.created_at,
                })

        recent_signups = db.query(WebUser).filter(
            WebUser.created_at >= day_ago,
            WebUser.is_banned == False,
            WebUser.is_disabled == False,
            WebUser.email_verified == True,
            WebUser.allow_discovery == True,
        ).order_by(WebUser.created_at.desc()).limit(5).all()
        for u in recent_signups:
            ticker.append({
                'type': 'join',
                'username': u.username,
                'display_name': u.display_name or u.username,
                'avatar_url': u.avatar_url or '',
                'message': 'joined QuestLog',
                'timestamp': u.created_at,
            })

        ticker.sort(key=lambda x: x['timestamp'], reverse=True)
        ticker = ticker[:15]

    return JsonResponse({
        'total_users': total_users,
        'total_posts': total_posts,
        'posts_today': posts_today,
        'active_posters_today': active_posters_q,
        'suggested_gamers': suggested_data,
        'new_members': new_members_data,
        'trending_games': trending_games,
        'ticker': ticker,
    })


# =============================================================================
# LIKE API
# =============================================================================

@web_login_required
@require_http_methods(["POST", "DELETE"])
@ratelimit(key='user', rate='120/h', method='POST', block=True)
def api_post_like(request, post_id):
    """POST: Like a post. DELETE: Unlike."""
    banned = check_banned(request)
    if banned:
        return banned

    with get_db_session() as db:
        post = db.query(WebPost).filter_by(id=post_id).first()
        if not post or post.is_deleted:
            return JsonResponse({'error': 'Post not found'}, status=404)

        if is_blocked(db, request.web_user.id, post.author_id):
            return JsonResponse({'error': 'Cannot interact with this post'}, status=403)

        is_own_post = post.author_id == request.web_user.id

        if request.method == 'POST':
            existing = db.query(WebLike).filter_by(
                user_id=request.web_user.id, post_id=post_id
            ).first()
            if not existing:
                like = WebLike(
                    user_id=request.web_user.id,
                    post_id=post_id,
                    created_at=int(time.time()),
                )
                db.add(like)
                post.like_count = (post.like_count or 0) + 1

                if not is_own_post:
                    create_notification(
                        db, user_id=post.author_id, actor_id=request.web_user.id,
                        notification_type='like', target_type='post', target_id=post_id,
                        message=f'{request.web_user.display_name or request.web_user.username} liked your post'
                    )
                db.commit()
                if not is_own_post:
                    award_hero_points(request.web_user.id, 'like', ref_id=str(post_id))
            return JsonResponse({
                'success': True, 'liked': True, 'like_count': post.like_count or 0
            })

        else:  # DELETE
            like = db.query(WebLike).filter_by(
                user_id=request.web_user.id, post_id=post_id
            ).first()
            if like:
                db.delete(like)
                if post.like_count and post.like_count > 0:
                    post.like_count -= 1
                db.commit()
            return JsonResponse({
                'success': True, 'liked': False, 'like_count': post.like_count or 0
            })


# =============================================================================
# COMMENT API
# =============================================================================

@web_login_required
@require_http_methods(["GET", "POST"])
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def api_comments(request, post_id):
    """GET: List comments for a post. POST: Create comment."""
    with get_db_session() as db:
        post = db.query(WebPost).filter_by(id=post_id).first()
        if not post or post.is_deleted:
            return JsonResponse({'error': 'Post not found'}, status=404)

        if request.method == 'GET':
            return _get_comments(request, db, post_id)

        banned = check_banned(request)
        if banned:
            return banned

        timeout = check_posting_timeout(request)
        if timeout:
            return timeout

        if is_blocked(db, request.web_user.id, post.author_id):
            return JsonResponse({'error': 'Cannot interact with this post'}, status=403)

        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        content = sanitize_text(data.get('content', ''), max_length=500)
        if not content:
            return JsonResponse({'error': 'Comment cannot be empty'}, status=400)

        parent_id = data.get('parent_id')
        if parent_id:
            parent = db.query(WebComment).filter_by(id=parent_id, post_id=post_id).first()
            if not parent:
                return JsonResponse({'error': 'Parent comment not found'}, status=404)
            # Max 1 level nesting
            if parent.parent_id is not None:
                return JsonResponse({'error': 'Cannot reply to a reply'}, status=400)

        now = int(time.time())
        comment = WebComment(
            post_id=post_id,
            author_id=request.web_user.id,
            content=content,
            parent_id=parent_id,
            created_at=now,
            updated_at=now,
        )
        db.add(comment)

        post.comment_count = (post.comment_count or 0) + 1

        create_notification(
            db, user_id=post.author_id, actor_id=request.web_user.id,
            notification_type='comment', target_type='post', target_id=post_id,
            message=f'{request.web_user.display_name or request.web_user.username} commented on your post'
        )

        # If it's a reply, also notify the parent comment author (unless they wrote the post)
        if parent_id and parent.author_id != post.author_id:
            create_notification(
                db, user_id=parent.author_id, actor_id=request.web_user.id,
                notification_type='comment', target_type='comment', target_id=parent_id,
                message=f'{request.web_user.display_name or request.web_user.username} replied to your comment'
            )

        db.commit()

        comment_data = {
            'id': comment.id,
            'author': serialize_user_brief(request.web_user),
            'content': comment.content,
            'parent_id': comment.parent_id,
            'like_count': 0,
            'created_at': comment.created_at,
            'replies': [],
            'liked_by_me': False,
        }

    return JsonResponse({'success': True, 'comment': comment_data}, status=201)


def _get_comments(request, db, post_id):
    """Get threaded comments for a post."""
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1)
    per_page = safe_int(request.GET.get('per_page', 20), default=20, min_val=1, max_val=50)
    offset = (page - 1) * per_page

    blocked_ids = set()
    if request.web_user:
        blocks = db.query(WebUserBlock).filter(
            or_(
                WebUserBlock.blocker_id == request.web_user.id,
                WebUserBlock.blocked_id == request.web_user.id,
            )
        ).all()
        for b in blocks:
            blocked_ids.add(b.blocker_id if b.blocked_id == request.web_user.id else b.blocked_id)

    # Top-level comments only (replies are fetched separately below)
    query = db.query(WebComment).filter(
        WebComment.post_id == post_id,
        WebComment.parent_id == None,
        WebComment.is_deleted == False,
    )
    if blocked_ids:
        query = query.filter(~WebComment.author_id.in_(blocked_ids))

    total = query.count()
    comments = query.order_by(WebComment.created_at.asc()).offset(offset).limit(per_page).all()

    comment_ids = [c.id for c in comments]
    replies = []
    if comment_ids:
        reply_query = db.query(WebComment).filter(
            WebComment.parent_id.in_(comment_ids),
            WebComment.is_deleted == False,
        )
        if blocked_ids:
            reply_query = reply_query.filter(~WebComment.author_id.in_(blocked_ids))
        replies = reply_query.order_by(WebComment.created_at.asc()).all()

    all_author_ids = set(c.author_id for c in comments) | set(r.author_id for r in replies)
    authors = {}
    if all_author_ids:
        for u in db.query(WebUser).filter(WebUser.id.in_(all_author_ids)).all():
            authors[u.id] = u

    my_likes = set()
    if request.web_user:
        all_comment_ids = [c.id for c in comments] + [r.id for r in replies]
        if all_comment_ids:
            liked = db.query(WebCommentLike.comment_id).filter(
                WebCommentLike.user_id == request.web_user.id,
                WebCommentLike.comment_id.in_(all_comment_ids)
            ).all()
            my_likes = {l[0] for l in liked}

    # Build reply map
    reply_map = {}
    for r in replies:
        reply_map.setdefault(r.parent_id, []).append(r)

    def serialize_comment(c):
        author = authors.get(c.author_id)
        return {
            'id': c.id,
            'author': serialize_user_brief(author) if author else None,
            'content': c.content,
            'parent_id': c.parent_id,
            'like_count': c.like_count or 0,
            'created_at': c.created_at,
            'liked_by_me': c.id in my_likes,
            'replies': [serialize_comment(r) for r in reply_map.get(c.id, [])],
        }

    data = [serialize_comment(c) for c in comments]

    return JsonResponse({
        'comments': data, 'total': total, 'page': page,
    })


@web_login_required
@require_http_methods(["PUT", "DELETE"])
def api_comment_detail(request, comment_id):
    """PUT: Edit comment. DELETE: Soft-delete."""
    banned = check_banned(request)
    if banned:
        return banned

    with get_db_session() as db:
        comment = db.query(WebComment).filter_by(id=comment_id).first()
        if not comment or comment.is_deleted:
            return JsonResponse({'error': 'Comment not found'}, status=404)

        is_author = comment.author_id == request.web_user.id
        is_admin = request.web_user.is_admin

        if not is_author and not is_admin:
            return JsonResponse({'error': 'Not authorized'}, status=403)

        if request.method == 'PUT':
            try:
                data = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            content = sanitize_text(data.get('content', ''), max_length=500)
            if not content:
                return JsonResponse({'error': 'Comment cannot be empty'}, status=400)
            comment.content = content
            comment.updated_at = int(time.time())
            db.commit()
            return JsonResponse({'success': True})

        else:  # DELETE
            comment.is_deleted = True
            post = db.query(WebPost).filter_by(id=comment.post_id).first()
            if post and post.comment_count and post.comment_count > 0:
                post.comment_count -= 1
            db.commit()
            return JsonResponse({'success': True})


@web_login_required
@require_http_methods(["POST", "DELETE"])
@ratelimit(key='user', rate='120/h', method='POST', block=True)
def api_comment_like(request, comment_id):
    """POST: Like a comment. DELETE: Unlike."""
    banned = check_banned(request)
    if banned:
        return banned

    with get_db_session() as db:
        comment = db.query(WebComment).filter_by(id=comment_id).first()
        if not comment or comment.is_deleted:
            return JsonResponse({'error': 'Comment not found'}, status=404)

        if is_blocked(db, request.web_user.id, comment.author_id):
            return JsonResponse({'error': 'Cannot interact with this comment'}, status=403)

        is_own_comment = comment.author_id == request.web_user.id

        if request.method == 'POST':
            existing = db.query(WebCommentLike).filter_by(
                user_id=request.web_user.id, comment_id=comment_id
            ).first()
            if not existing:
                cl = WebCommentLike(
                    user_id=request.web_user.id,
                    comment_id=comment_id,
                    created_at=int(time.time()),
                )
                db.add(cl)
                comment.like_count = (comment.like_count or 0) + 1

                if not is_own_comment:
                    create_notification(
                        db, user_id=comment.author_id, actor_id=request.web_user.id,
                        notification_type='comment_like', target_type='comment',
                        target_id=comment_id,
                    )
                db.commit()
            return JsonResponse({
                'success': True, 'liked': True, 'like_count': comment.like_count or 0
            })

        else:  # DELETE
            cl = db.query(WebCommentLike).filter_by(
                user_id=request.web_user.id, comment_id=comment_id
            ).first()
            if cl:
                db.delete(cl)
                if comment.like_count and comment.like_count > 0:
                    comment.like_count -= 1
                db.commit()
            return JsonResponse({
                'success': True, 'liked': False, 'like_count': comment.like_count or 0
            })


# =============================================================================
# NOTIFICATION API
# =============================================================================

@web_login_required
def api_notifications(request):
    """GET: List notifications for current user. Paginated."""
    page = safe_int(request.GET.get('page', 1), default=1, min_val=1)
    per_page = safe_int(request.GET.get('per_page', 20), default=20, min_val=1, max_val=50)
    offset = (page - 1) * per_page
    unread_only = request.GET.get('unread_only', 'false').lower() == 'true'

    with get_db_session() as db:
        query = db.query(WebNotification).filter_by(user_id=request.web_user.id)
        if unread_only:
            query = query.filter_by(is_read=False)

        total = query.count()
        unread_count = db.query(WebNotification).filter_by(
            user_id=request.web_user.id, is_read=False
        ).count()

        notifs = query.order_by(
            WebNotification.created_at.desc()
        ).offset(offset).limit(per_page).all()

        actor_ids = set(n.actor_id for n in notifs)
        actors = {}
        if actor_ids:
            for u in db.query(WebUser).filter(WebUser.id.in_(actor_ids)).all():
                actors[u.id] = u

        data = [{
            'id': n.id,
            'type': n.notification_type,
            'actor': serialize_user_brief(actors[n.actor_id]) if n.actor_id in actors else None,
            'target_type': n.target_type,
            'target_id': n.target_id,
            'message': n.message,
            'is_read': n.is_read,
            'created_at': n.created_at,
        } for n in notifs]

    return JsonResponse({
        'notifications': data, 'total': total,
        'unread_count': unread_count, 'page': page,
    })


@web_login_required
def api_notification_count(request):
    """GET: Unread notification count."""
    with get_db_session() as db:
        count = db.query(WebNotification).filter_by(
            user_id=request.web_user.id, is_read=False
        ).count()
    return JsonResponse({'unread_count': count})


@web_login_required
@require_http_methods(["POST"])
def api_notifications_mark_read(request):
    """POST: Mark notifications as read. Body: {notification_ids: [...]} or {} for all."""
    try:
        data = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    with get_db_session() as db:
        query = db.query(WebNotification).filter_by(
            user_id=request.web_user.id, is_read=False
        )
        notification_ids = data.get('notification_ids')
        if notification_ids and isinstance(notification_ids, list):
            query = query.filter(WebNotification.id.in_(notification_ids))

        count = query.update({'is_read': True}, synchronize_session=False)
        db.commit()

    return JsonResponse({'success': True, 'marked_count': count})


@web_login_required
@require_http_methods(["POST"])
def api_notification_mark_read(request, notification_id):
    """POST: Mark a single notification as read."""
    with get_db_session() as db:
        notif = db.query(WebNotification).filter_by(
            id=notification_id, user_id=request.web_user.id
        ).first()
        if notif:
            notif.is_read = True
            db.commit()
    return JsonResponse({'success': True})


# =============================================================================
# SHARE API
# =============================================================================

@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='20/h', block=True)
def api_post_share(request, post_id):
    """
    POST: Record a share event and award Hero Points.
    Called client-side when the user taps Share on a post.
    Does not create a new post — just logs the action for HP purposes.
    """
    banned = check_banned(request)
    if banned:
        return banned

    with get_db_session() as db:
        post = db.query(WebPost).filter_by(id=post_id).first()
        if not post or post.is_deleted:
            return JsonResponse({'error': 'Post not found'}, status=404)

        if is_blocked(db, request.web_user.id, post.author_id):
            return JsonResponse({'error': 'Cannot interact with this post'}, status=403)

        is_own_post = post.author_id == request.web_user.id
        post.repost_count = (post.repost_count or 0) + 1
        db.commit()

    points = 0 if is_own_post else award_hero_points(request.web_user.id, 'share', ref_id=str(post_id))
    return JsonResponse({'success': True, 'hp_awarded': points})


# =============================================================================
# GIVEAWAY API (user-facing)
# =============================================================================

def _giveaway_public_dict(g, current_user_id=None, db=None):
    ticket_count = 0
    if current_user_id and db:
        entry = db.query(WebGiveawayEntry).filter_by(
            giveaway_id=g.id, user_id=current_user_id
        ).first()
        ticket_count = entry.ticket_count if entry else 0
    # Parse all winners for display
    winners = []
    if g.winners_json and db:
        try:
            import json as _j
            from app.questlog_web.models import WebUser as _WU
            for wid in _j.loads(g.winners_json):
                wu = db.query(_WU).filter_by(id=wid).first()
                if wu:
                    winners.append(serialize_user_brief(wu))
        except Exception:
            pass
    return {
        'id': g.id,
        'title': g.title,
        'description': g.description,
        'prize': g.prize,
        'image_url': g.image_url,
        'status': g.status,
        'ends_at': g.ends_at,
        'entry_count': g.entry_count,
        'max_winners': g.max_winners or 1,
        'max_entries_per_user': g.max_entries_per_user or 1,
        'hp_per_extra_ticket': g.hp_per_extra_ticket or 0,
        'winner': serialize_user_brief(db.query(WebUser).filter_by(id=g.winner_user_id).first()) if g.winner_user_id and db else None,
        'winners': winners,
        'entered': ticket_count > 0,
        'ticket_count': ticket_count,
    }


@add_web_user_context
@require_http_methods(['GET'])
def api_giveaways(request):
    """List active (and recent closed/won) giveaways."""
    with get_db_session() as db:
        giveaways = (
            db.query(WebGiveaway)
            .filter(WebGiveaway.status.in_(['active', 'closed', 'winner_selected']))
            .order_by(WebGiveaway.created_at.desc())
            .limit(20)
            .all()
        )
        current_uid = request.web_user.id if request.web_user else None
        return JsonResponse({
            'giveaways': [_giveaway_public_dict(g, current_uid, db) for g in giveaways]
        })


@web_login_required
@require_http_methods(['POST', 'DELETE'])
def api_giveaway_enter(request, giveaway_id):
    """POST: enter/buy tickets. DELETE: withdraw all tickets."""
    banned = check_banned(request)
    if banned:
        return banned

    with get_db_session() as db:
        g = db.query(WebGiveaway).filter_by(id=giveaway_id).first()
        if not g:
            return JsonResponse({'error': 'Giveaway not found'}, status=404)
        if g.status != 'active':
            return JsonResponse({'error': 'Giveaway is not accepting entries'}, status=400)
        if g.ends_at and int(time.time()) > g.ends_at:
            return JsonResponse({'error': 'Giveaway entry deadline has passed'}, status=400)

        existing = db.query(WebGiveawayEntry).filter_by(
            giveaway_id=giveaway_id, user_id=request.web_user.id
        ).first()

        if request.method == 'POST':
            # Parse desired ticket count (1 = free entry, >1 = buy extras with HP)
            try:
                body = json.loads(request.body) if request.body else {}
            except (json.JSONDecodeError, ValueError):
                body = {}
            desired_tickets = max(1, int(body.get('tickets', 1)))
            max_per_user = max(1, g.max_entries_per_user or 1)
            desired_tickets = min(desired_tickets, max_per_user)

            current_tickets = existing.ticket_count if existing else 0
            extra_needed = desired_tickets - current_tickets
            if extra_needed <= 0:
                return JsonResponse({'success': True, 'entered': True, 'ticket_count': current_tickets, 'entry_count': g.entry_count})

            # Calculate HP cost for extra tickets above 1
            hp_cost = 0
            hp_rate = g.hp_per_extra_ticket or 0
            if hp_rate > 0:
                # Tickets 2+ cost HP; ticket 1 is always free
                free_already_covered = min(current_tickets, 1)
                paid_current = max(0, current_tickets - free_already_covered)
                paid_new = max(0, desired_tickets - 1) - paid_current
                hp_cost = max(0, paid_new) * hp_rate

            if hp_cost > 0:
                # Use with_for_update() to lock row and prevent concurrent double-spend
                user = db.query(WebUser).filter_by(id=request.web_user.id).with_for_update().first()
                if not user or user.hero_points < hp_cost:
                    have = user.hero_points if user else 0
                    return JsonResponse({'error': f'Not enough Hero Points ({hp_cost} HP needed, you have {have})'}, status=400)
                user.hero_points = max(0, user.hero_points - hp_cost)

            now = int(time.time())
            if existing:
                existing.ticket_count = desired_tickets
            else:
                entry = WebGiveawayEntry(
                    giveaway_id=giveaway_id,
                    user_id=request.web_user.id,
                    entered_at=now,
                    ticket_count=desired_tickets,
                )
                db.add(entry)
                g.entry_count = (g.entry_count or 0) + 1
            db.commit()
            return JsonResponse({
                'success': True,
                'entered': True,
                'ticket_count': desired_tickets,
                'entry_count': g.entry_count,
                'hp_spent': hp_cost,
            })

        else:  # DELETE - withdraw all tickets (no HP refund)
            if existing:
                db.delete(existing)
                if g.entry_count and g.entry_count > 0:
                    g.entry_count -= 1
                db.commit()
            return JsonResponse({'success': True, 'entered': False, 'ticket_count': 0, 'entry_count': g.entry_count or 0})
