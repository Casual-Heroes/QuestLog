# QuestLog Web - profile & privacy views

import os
import json
import time
import logging

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from django.conf import settings as django_settings
from sqlalchemy import func, or_, text as sa_text

from .models import (
    WebUser, WebFollow, WebPost, WebPostImage, WebLike,
    WebComment, WebCommentLike, WebNotification, WebUserBlock,
    WebCommunity, WebCommunityMember, WebLFGMember, WebRaffleEntry, WebCreatorProfile,
    WebReferral, WebFlair, WebUserFlair, WebRankTitle, WebHeroPointEvent,
    WebFfxivCharacter, WebFfxivAchievementReward, WebIndieGame,
)
from app.db import get_db_session
from .helpers import (
    web_login_required, web_verified_required, add_web_user_context,
    check_banned, is_blocked,
    sanitize_text, parse_embed_url,
    serialize_post, award_hero_points,
)

logger = logging.getLogger(__name__)


def _queue_flair_role_update(web_user_id: int, action: str, flair_emoji: str | None, flair_name: str | None):
    """Queue flair role sync for both Fluxer and Discord bots."""
    try:
        from .models import WebFluxerRoleUpdate, WebDiscordPendingRoleUpdate
        now = int(time.time())
        with get_db_session() as db:
            db.add(WebFluxerRoleUpdate(
                web_user_id=web_user_id,
                action=action,
                flair_emoji=flair_emoji,
                flair_name=flair_name,
                created_at=now,
            ))
            db.add(WebDiscordPendingRoleUpdate(
                web_user_id=web_user_id,
                action=action,
                flair_emoji=flair_emoji,
                flair_name=flair_name,
                created_at=now,
            ))
            db.commit()
    except Exception as exc:
        logger.warning(f'_queue_flair_role_update: failed for user {web_user_id}: {exc}')


# =============================================================================
# PROFILE UPDATE API
# =============================================================================

@web_login_required
@require_http_methods(["PUT"])
@ratelimit(key='ip', rate='20/h', method='PUT', block=True)
def api_profile_update(request):
    """PUT: Update current user's profile."""
    banned = check_banned(request)
    if banned:
        return banned

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        if 'username' in data:
            new_uname = sanitize_text(data['username'], max_length=50).strip()
            _RESERVED = {
                'admin','administrator','root','superuser','moderator','mod',
                'staff','support','help','info','contact','system','service',
                'questlog','questlogbot','casualheroes','casual_heroes',
                'bot','api','null','undefined','anonymous','guest','official',
            }
            import re as _re
            if (new_uname and new_uname != user.username
                    and _re.match(r'^[a-zA-Z0-9_]{3,30}$', new_uname)
                    and new_uname.lower() not in _RESERVED):
                taken = db.query(WebUser).filter(
                    WebUser.username == new_uname,
                    WebUser.id != user.id
                ).first()
                if not taken:
                    user.username = new_uname
                    request.session['web_user_name'] = new_uname
                    request.session.modified = True

        if 'avatar_url' in data:
            url = (data['avatar_url'] or '').strip()
            if not url:
                user.avatar_url = None
            elif url.startswith('/media/uploads/'):
                # Local upload - always allowed
                user.avatar_url = url
                request.session['web_user_avatar'] = url
                request.session.modified = True
            else:
                # External URLs: restrict to known CDNs to prevent tracking pixels
                _AVATAR_ALLOWED_HOSTS = {
                    'cdn.discordapp.com', 'media.discordapp.net',
                    'avatars.steamstatic.com', 'steamuserimages-a.akamaihd.net',
                    'steamcdn-a.akamaihd.net', 'avatars.akamai.steamstatic.com',
                }
                from urllib.parse import urlparse as _urlparse
                _p = _urlparse(url)
                if _p.scheme == 'https' and _p.netloc in _AVATAR_ALLOWED_HOSTS:
                    user.avatar_url = url
                    request.session['web_user_avatar'] = url
                    request.session.modified = True

        if 'display_name' in data:
            val = sanitize_text(data['display_name'], max_length=100)
            if val:
                user.display_name = val

        if 'bio' in data:
            user.bio = sanitize_text(data['bio'], max_length=1000)

        if 'banner_url' in data:
            url = (data['banner_url'] or '').strip()
            if not url:
                user.banner_url = None
            else:
                from .helpers import validate_admin_image_url
                if validate_admin_image_url(url):
                    user.banner_url = url[:500]

        if 'banner_url' in data:
            url = (data['banner_url'] or '').strip()
            if not url:
                user.banner_url = None
            else:
                from .helpers import validate_admin_image_url
                if validate_admin_image_url(url):
                    user.banner_url = url[:500]

        if 'twitch_username' in data:
            val = sanitize_text(data['twitch_username'], max_length=50).strip()
            user.twitch_username = val if val else None
            # Keep creator profile in sync
            cp = db.query(WebCreatorProfile).filter_by(user_id=user.id).first()
            if cp:
                cp.twitch_url = f'https://twitch.tv/{val}' if val else None

        if 'youtube_channel_name' in data:
            val = sanitize_text(data['youtube_channel_name'], max_length=100).strip()
            user.youtube_channel_name = val if val else None
            # Keep creator profile in sync
            cp = db.query(WebCreatorProfile).filter_by(user_id=user.id).first()
            if cp:
                cp.youtube_url = f'https://youtube.com/@{val}' if val else None

        if 'playstyle' in data:
            _allowed_styles = {'Casual', 'Hardcore', 'Competitive', 'Completionist', 'Explorer', 'Social'}
            raw = data['playstyle']
            if isinstance(raw, list):
                clean = [s for s in raw if isinstance(s, str) and s in _allowed_styles]
                user.playstyle = json.dumps(clean) if clean else None
            else:
                val = sanitize_text(raw, max_length=100)
                if val in _allowed_styles:
                    user.playstyle = json.dumps([val])
                elif not val:
                    user.playstyle = None

        if 'favorite_genres' in data:
            genres = data['favorite_genres']
            if isinstance(genres, list) and len(genres) <= 10:
                clean = [sanitize_text(g, 50) for g in genres if isinstance(g, str)]
                user.favorite_genres = json.dumps(clean)

        if 'favorite_games' in data:
            games = data['favorite_games']
            if isinstance(games, list) and len(games) <= 20:
                clean = []
                for g in games:
                    if isinstance(g, dict):
                        # New format: {name, igdb_id, cover_url}
                        name = sanitize_text(str(g.get('name', '')), 200).strip()
                        if not name:
                            continue
                        igdb_id = g.get('igdb_id')
                        if igdb_id is not None:
                            try:
                                igdb_id = int(igdb_id)
                            except (ValueError, TypeError):
                                igdb_id = None
                        cover_url = str(g.get('cover_url', '') or '').strip()
                        # Only allow IGDB image URLs for cover art
                        if cover_url and not cover_url.startswith('https://images.igdb.com/'):
                            cover_url = ''
                        clean.append({'name': name, 'igdb_id': igdb_id, 'cover_url': cover_url})
                    elif isinstance(g, str):
                        # Legacy plain string format
                        name = sanitize_text(g, 200).strip()
                        if name:
                            clean.append({'name': name, 'igdb_id': None, 'cover_url': ''})
                user.favorite_games = json.dumps(clean)

        if 'gaming_platforms' in data:
            platforms = data['gaming_platforms']
            allowed_platforms = ['PC', 'PS5', 'PS4', 'Xbox Series', 'Xbox One', 'Switch', 'Mobile', 'Steam Deck']
            if isinstance(platforms, list):
                clean = [p for p in platforms if p in allowed_platforms]
                user.gaming_platforms = json.dumps(clean)

        if 'revolt_url' in data:
            val = (data['revolt_url'] or '').strip()[:500]
            if not val:
                user.revolt_url = None
            elif val.startswith('https://'):
                user.revolt_url = val

        if 'root_url' in data:
            val = (data['root_url'] or '').strip()[:500]
            if not val:
                user.root_url = None
            elif val.startswith('https://'):
                user.root_url = val

        if 'allow_discovery' in data:
            user.allow_discovery = bool(data['allow_discovery'])

        if 'primary_community_id' in data:
            val = data['primary_community_id']
            if val is None or val == '':
                user.primary_community_id = None
            else:
                try:
                    cid = int(val)
                    # Must be a community the user is a member of, owns, or is active in via bot
                    allowed = False
                    community = db.query(WebCommunity).filter_by(
                        id=cid, is_active=True, network_status='approved'
                    ).first()
                    if community:
                        if db.query(WebCommunityMember).filter_by(user_id=user.id, community_id=cid).first():
                            allowed = True
                        elif db.query(WebCommunity).filter_by(id=cid, owner_id=user.id).first():
                            allowed = True
                        else:
                            _plat = community.platform.value if hasattr(community.platform, 'value') else community.platform
                            if _plat == 'fluxer' and user.fluxer_id:
                                row = db.execute(
                                    sa_text("SELECT 1 FROM fluxer_member_xp WHERE user_id=:uid AND guild_id=:gid LIMIT 1"),
                                    {'uid': user.fluxer_id, 'gid': community.platform_id}
                                ).fetchone()
                                if row:
                                    allowed = True
                            elif _plat == 'discord' and user.discord_id:
                                row = db.execute(
                                    sa_text("SELECT 1 FROM guild_members WHERE user_id=:uid AND guild_id=:gid LIMIT 1"),
                                    {'uid': user.discord_id, 'gid': community.platform_id}
                                ).fetchone()
                                if row:
                                    allowed = True
                    if allowed:
                        user.primary_community_id = cid
                except (ValueError, TypeError):
                    pass

        user.updated_at = int(time.time())
        db.commit()

        user_data = {
            'id': user.id,
            'username': user.username,
            'display_name': user.display_name,
            'bio': user.bio,
            'avatar_url': user.avatar_url or '',
            'playstyle': user.playstyle,
            'favorite_genres': json.loads(user.favorite_genres) if user.favorite_genres else [],
            'favorite_games': json.loads(user.favorite_games) if user.favorite_games else [],
            'gaming_platforms': json.loads(user.gaming_platforms) if user.gaming_platforms else [],
            'twitch_username': user.twitch_username or '',
            'youtube_channel_name': user.youtube_channel_name or '',
            'allow_discovery': user.allow_discovery,
        }

    return JsonResponse({'success': True, 'user': user_data})


# =============================================================================
# EMBED VALIDATION API
# =============================================================================

@web_login_required
@require_http_methods(["POST"])
def api_validate_embed(request):
    """POST: Validate a video embed URL."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    url = data.get('url', '')
    platform, embed_id = parse_embed_url(url)

    if platform:
        return JsonResponse({
            'valid': True, 'platform': platform, 'embed_id': embed_id
        })
    return JsonResponse({
        'valid': False,
        'error': 'Unsupported URL. Supported: YouTube, Twitch, TikTok, Instagram, Kick, Twitter/X'
    })


# =============================================================================
# PUBLIC PROFILE PAGE
# =============================================================================

@ensure_csrf_cookie
@add_web_user_context
def public_profile(request, username):
    """Public profile page at u/<username>/."""
    with get_db_session() as db:
        profile_user = db.query(WebUser).filter_by(username=username).first()
        if not profile_user:
            return render(request, 'questlog_web/public_profile.html', {
                'web_user': request.web_user,
                'profile_user': None,
                'error': 'User not found',
                'active_page': 'profile',
            })

        # Hidden/banned/disabled profiles are invisible to non-admins
        is_admin_viewer = request.web_user and (request.web_user.is_admin or request.web_user.is_mod)
        is_own_profile = request.web_user and request.web_user.id == profile_user.id
        if not is_admin_viewer and not is_own_profile:
            if profile_user.is_banned or profile_user.is_disabled or profile_user.is_hidden:
                return render(request, 'questlog_web/public_profile.html', {
                    'web_user': request.web_user,
                    'profile_user': None,
                    'error': 'User not found',
                    'active_page': 'profile',
                })

        if request.web_user and is_blocked(db, request.web_user.id, profile_user.id):
            return render(request, 'questlog_web/public_profile.html', {
                'web_user': request.web_user,
                'profile_user': None,
                'error': 'User not found',
                'active_page': 'profile',
            })

        is_own = request.web_user and request.web_user.id == profile_user.id
        is_following = False
        is_mutual = False
        if request.web_user and not is_own:
            is_following = db.query(WebFollow).filter_by(
                follower_id=request.web_user.id, following_id=profile_user.id
            ).first() is not None
            if is_following:
                is_mutual = db.query(WebFollow).filter_by(
                    follower_id=profile_user.id, following_id=request.web_user.id
                ).first() is not None

        genres = json.loads(profile_user.favorite_genres) if profile_user.favorite_genres else []
        # Pull games from library (web_user_games) instead of legacy favorite_games JSON
        from .models import WebUserGame as _PubWebUserGame
        from sqlalchemy import case as _pub_case
        _pub_order = _pub_case(
            (_PubWebUserGame.status == 'play_together', 0),
            (_PubWebUserGame.status == 'playing', 1),
            else_=2,
        )
        lib_rows = db.query(_PubWebUserGame).filter_by(web_user_id=profile_user.id).order_by(
            _pub_order, _PubWebUserGame.updated_at.desc()
        ).limit(20).all()
        fav_games = [{'name': g.name, 'igdb_id': g.igdb_id, 'cover_url': g.cover_url or ''} for g in lib_rows]
        platforms = json.loads(profile_user.gaming_platforms) if profile_user.gaming_platforms else []
        raw_ps = profile_user.playstyle or ''
        playstyle_list = (
            json.loads(raw_ps) if raw_ps.startswith('[')
            else ([raw_ps] if raw_ps else [])
        )

        creator_profile = db.query(WebCreatorProfile).filter_by(user_id=profile_user.id).first()
        if creator_profile:
            db.expunge(creator_profile)

        from .helpers import get_user_flair_and_title as _get_flair
        flair_emoji, flair_name, rank_title = _get_flair(profile_user)

        # FFXIV character + achievement rewards (only if user opted in)
        ffxiv_char = None
        ffxiv_rewards = []
        if profile_user.track_achievements:
            ffxiv_char = db.query(WebFfxivCharacter).filter_by(
                user_id=profile_user.id, is_primary=True, sync_status='ok'
            ).first()
            if ffxiv_char:
                db.expunge(ffxiv_char)
                rewards = db.query(WebFfxivAchievementReward).filter_by(
                    user_id=profile_user.id
                ).order_by(WebFfxivAchievementReward.awarded_at.desc()).all()
                ffxiv_rewards = [
                    {'name': r.achievement_name, 'xp': r.xp_awarded, 'legacy': r.legacy_awarded}
                    for r in rewards
                ]

        # Indie games this user is listed as dev for
        indie_games = db.query(WebIndieGame).filter(
            WebIndieGame.dev_user_id == profile_user.id,
            WebIndieGame.is_published == True,
        ).order_by(WebIndieGame.created_at.desc()).all()
        indie_games_data = [
            {
                'name': g.name,
                'slug': g.slug,
                'cover_url': g.cover_url or '',
                'dev_bio': g.dev_bio or '',
                'dev_devlog': g.dev_devlog or '',
                'status': g.status or '',
                'dev_website': g.dev_website or '',
                'dev_twitter': g.dev_twitter or '',
                'dev_discord_url': g.dev_discord_url or '',
                'dev_fluxer_url': g.dev_fluxer_url or '',
                'dev_itch_url': g.dev_itch_url or '',
                'dev_youtube_url': g.dev_youtube_url or '',
                'dev_twitch_url': g.dev_twitch_url or '',
                'dev_steam_url': g.dev_steam_url or '',
                'dev_tiktok_url': g.dev_tiktok_url or '',
                'dev_instagram_url': g.dev_instagram_url or '',
                'dev_facebook_url': g.dev_facebook_url or '',
                'dev_bsky_url': g.dev_bsky_url or '',
                'dev_kick_url': g.dev_kick_url or '',
            }
            for g in indie_games
        ]

        db.expunge(profile_user)

    og_name = profile_user.display_name or profile_user.username
    og_desc = (profile_user.bio or f"{og_name}'s profile on QuestLog")[:200]

    return render(request, 'questlog_web/public_profile.html', {
        'web_user': request.web_user,
        'profile_user': profile_user,
        'is_own_profile': is_own,
        'is_following': is_following,
        'is_mutual': is_mutual,
        'genres': genres,
        'favorite_games': fav_games,
        'gaming_platforms': platforms,
        'playstyle_list': playstyle_list,
        'creator_profile': creator_profile,
        'ffxiv_char': ffxiv_char,
        'ffxiv_rewards': ffxiv_rewards,
        'flair_emoji': flair_emoji,
        'flair_name': flair_name,
        'rank_title': rank_title,
        'indie_games': indie_games_data,
        'is_vip': bool(profile_user.is_vip),
        'is_founder': bool(profile_user.is_founder),
        'active_page': 'public_profile',
        'og_title': f"{og_name} on QuestLog",
        'og_desc': og_desc,
        'og_image': profile_user.avatar_url or None,
        'og_url': f"https://casual-heroes.comu/{profile_user.username}/",
    })


def public_profile_followers(request, username):
    """Public profile - followers tab."""
    return public_profile(request, username)


def public_profile_following(request, username):
    """Public profile - following tab."""
    return public_profile(request, username)


# =============================================================================
# SOCIAL FEED PAGE
# =============================================================================

@ensure_csrf_cookie
@add_web_user_context
def social_feed(request):
    """Main social feed page."""
    game_filter = request.GET.get('game', '').strip()[:200]
    return render(request, 'questlog_web/feed.html', {
        'web_user': getattr(request, 'web_user', None),
        'active_page': 'feed',
        'game_filter': game_filter,
    })


# =============================================================================
# INVITE / REFERRAL
# =============================================================================

@web_login_required
@require_http_methods(["GET"])
def api_invite_link(request):
    """GET: Return the user's personal invite link + referral stats.
    Auto-generates an invite_code on first call."""
    import secrets as _secrets

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        if not user.invite_code:
            # Generate a unique 10-char alphanumeric code
            for _ in range(10):
                code = _secrets.token_urlsafe(7)[:10]
                if not db.query(WebUser).filter_by(invite_code=code).first():
                    user.invite_code = code
                    user.updated_at = int(time.time())
                    db.commit()
                    break

        completed = db.query(WebReferral).filter_by(
            referrer_id=user.id, status='completed'
        ).count()
        pending = db.query(WebReferral).filter_by(
            referrer_id=user.id, status='pending'
        ).count()

        invite_code = user.invite_code

    invite_url = request.build_absolute_uri(f'/register/?ref={invite_code}')

    return JsonResponse({
        'invite_code': invite_code,
        'invite_url': invite_url,
        'completed_referrals': completed,
        'pending_referrals': pending,
        'hp_per_referral': 50,
    })


# =============================================================================
# PRIVACY / GDPR ENDPOINTS
# =============================================================================

@web_login_required
@require_http_methods(["GET"])
def api_privacy_data_summary(request):
    """GET: Show what data we store about the current user."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        post_count = db.query(func.count(WebPost.id)).filter_by(author_id=user.id).scalar()
        comment_count = db.query(func.count(WebComment.id)).filter_by(author_id=user.id).scalar()
        like_count = db.query(func.count(WebLike.id)).filter_by(user_id=user.id).scalar()
        follower_count = db.query(func.count(WebFollow.id)).filter_by(following_id=user.id).scalar()
        following_count = db.query(func.count(WebFollow.id)).filter_by(follower_id=user.id).scalar()
        notification_count = db.query(func.count(WebNotification.id)).filter_by(user_id=user.id).scalar()
        block_count = db.query(func.count(WebUserBlock.id)).filter_by(blocker_id=user.id).scalar()
        image_count = db.query(func.count(WebPostImage.id)).filter(
            WebPostImage.post_id.in_(
                db.query(WebPost.id).filter_by(author_id=user.id)
            )
        ).scalar()

    return JsonResponse({
        'data_summary': {
            'account': {
                'username': user.username,
                'display_name': user.display_name,
                'email': user.email or '(not set)',
                'created_at': user.created_at,
                'last_login_at': user.last_login_at,
            },
            'linked_accounts': {
                'steam': bool(user.steam_id),
                'discord': bool(user.discord_id),
                'twitch': bool(user.twitch_id),
                'youtube': bool(user.youtube_channel_id),
            },
            'content_counts': {
                'posts': post_count,
                'comments': comment_count,
                'likes_given': like_count,
                'images_uploaded': image_count,
            },
            'social_counts': {
                'followers': follower_count,
                'following': following_count,
                'notifications': notification_count,
                'blocked_users': block_count,
            },
            'stored_fields': [
                'Username, display name, bio',
                'Avatar URL, banner URL',
                'Steam ID and profile info (used for login)',
                'Linked account IDs (Discord, Twitch, YouTube) if connected',
                'Email (if provided, optional)',
                'Posts, comments, likes, follows',
                'Notification history',
                'Gaming preferences (genres, platforms, playstyle)',
            ],
            'not_stored': [
                'Passwords in plaintext (stored as PBKDF2 hashes via Django auth)',
                'Payment information (Stripe handles this)',
                'IP addresses (hashed in admin audit logs only)',
                'Browsing history or tracking data',
            ],
        }
    })


@web_login_required
@ratelimit(key='ip', rate='1/d', block=True)
@require_http_methods(["GET"])
def api_privacy_export(request):
    """GET: Export all user data as JSON. Rate limited to 1 per day."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        posts = db.query(WebPost).filter_by(author_id=user.id).order_by(WebPost.created_at.desc()).all()
        comments = db.query(WebComment).filter_by(author_id=user.id).order_by(WebComment.created_at.desc()).all()
        likes = db.query(WebLike).filter_by(user_id=user.id).all()
        followers = db.query(WebFollow).filter_by(following_id=user.id).all()
        following = db.query(WebFollow).filter_by(follower_id=user.id).all()
        notifications = db.query(WebNotification).filter_by(user_id=user.id).all()
        blocks = db.query(WebUserBlock).filter_by(blocker_id=user.id).all()
        communities = db.query(WebCommunityMember).filter_by(user_id=user.id).all()

        export_data = {
            'export_date': int(time.time()),
            'account': {
                'id': user.id,
                'username': user.username,
                'display_name': user.display_name,
                'bio': user.bio,
                'email': user.email,
                'avatar_url': user.avatar_url,
                'banner_url': user.banner_url,
                'steam_id': user.steam_id,
                'steam_username': user.steam_username,
                'discord_id': user.discord_id,
                'discord_username': user.discord_username,
                'twitch_id': user.twitch_id,
                'twitch_username': user.twitch_username,
                'youtube_channel_id': user.youtube_channel_id,
                'favorite_genres': json.loads(user.favorite_genres or '[]'),
                'favorite_games': json.loads(user.favorite_games or '[]'),
                'playstyle': user.playstyle,
                'gaming_platforms': json.loads(user.gaming_platforms or '[]'),
                'web_xp': user.web_xp,
                'web_level': user.web_level,
                'hero_points': user.hero_points,
                'created_at': user.created_at,
                'last_login_at': user.last_login_at,
            },
            'posts': [{
                'id': p.id,
                'content': p.content,
                'post_type': p.post_type,
                'media_url': p.media_url,
                'embed_platform': p.embed_platform,
                'embed_id': p.embed_id,
                'like_count': p.like_count,
                'comment_count': p.comment_count,
                'created_at': p.created_at,
            } for p in posts],
            'comments': [{
                'id': c.id,
                'post_id': c.post_id,
                'content': c.content,
                'created_at': c.created_at,
            } for c in comments],
            'likes': [{
                'post_id': l.post_id,
                'created_at': l.created_at,
            } for l in likes],
            'followers': [{
                'follower_id': f.follower_id,
                'created_at': f.created_at,
            } for f in followers],
            'following': [{
                'following_id': f.following_id,
                'created_at': f.created_at,
            } for f in following],
            'blocked_users': [{
                'blocked_id': b.blocked_id,
                'created_at': b.created_at,
            } for b in blocks],
            'community_memberships': [{
                'community_id': m.community_id,
                'role': m.role,
                'joined_at': m.joined_at,
            } for m in communities],
            'notification_count': len(notifications),
        }

    response = JsonResponse(export_data)
    response['Content-Disposition'] = 'attachment; filename="questlog_data_export.json"'
    return response


@web_login_required
@require_http_methods(["POST"])
def api_privacy_delete(request):
    """POST: Hard delete the current user's account and ALL associated data.
    This is irreversible - all posts, comments, likes, follows, notifications,
    and uploaded images are permanently deleted."""
    user_id = request.web_user.id
    media_root = django_settings.MEDIA_ROOT

    _xff = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('HTTP_X_FORWARDED_FOR', '')
    _ip = _xff.split(',')[0].strip() if _xff else request.META.get('REMOTE_ADDR', 'unknown')
    logger.warning("Account self-deletion initiated: user_id=%s ip=%s", user_id, _ip)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        # Gather file paths to delete from disk after the DB transaction
        post_ids = [p.id for p in db.query(WebPost.id).filter_by(author_id=user_id).all()]
        image_paths = []
        media_root_abs = os.path.abspath(media_root)

        def _safe_media_path(url):
            """Resolve a /media/... URL to an absolute path, rejecting traversal attempts."""
            if not url:
                return None
            rel = url.lstrip('/')
            if rel.startswith('media/'):
                rel = rel[6:]
            full = os.path.abspath(os.path.join(media_root, rel))
            if not full.startswith(media_root_abs + os.sep):
                logger.warning("Blocked path traversal attempt in file deletion: %s", url)
                return None
            return full

        if post_ids:
            images = db.query(WebPostImage).filter(WebPostImage.post_id.in_(post_ids)).all()
            for img in images:
                for url in [img.image_url, img.thumbnail_url]:
                    p = _safe_media_path(url)
                    if p:
                        image_paths.append(p)

        for url in [user.avatar_url, user.banner_url]:
            if url and url.startswith('/media/uploads/'):
                p = _safe_media_path(url)
                if p:
                    image_paths.append(p)

        # Delete child rows before parents (FK dependency order)
        user_comment_ids = [c.id for c in db.query(WebComment.id).filter_by(author_id=user_id).all()]
        if user_comment_ids:
            db.query(WebCommentLike).filter(WebCommentLike.comment_id.in_(user_comment_ids)).delete(synchronize_session=False)
        db.query(WebCommentLike).filter_by(user_id=user_id).delete(synchronize_session=False)
        db.query(WebComment).filter_by(author_id=user_id).delete(synchronize_session=False)

        if post_ids:
            db.query(WebPostImage).filter(WebPostImage.post_id.in_(post_ids)).delete(synchronize_session=False)
            db.query(WebLike).filter(WebLike.post_id.in_(post_ids)).delete(synchronize_session=False)
        db.query(WebLike).filter_by(user_id=user_id).delete(synchronize_session=False)
        db.query(WebPost).filter_by(author_id=user_id).delete(synchronize_session=False)

        db.query(WebFollow).filter(
            or_(WebFollow.follower_id == user_id, WebFollow.following_id == user_id)
        ).delete(synchronize_session=False)
        db.query(WebNotification).filter(
            or_(WebNotification.user_id == user_id, WebNotification.actor_id == user_id)
        ).delete(synchronize_session=False)
        db.query(WebUserBlock).filter(
            or_(WebUserBlock.blocker_id == user_id, WebUserBlock.blocked_id == user_id)
        ).delete(synchronize_session=False)

        db.query(WebCommunityMember).filter_by(user_id=user_id).delete(synchronize_session=False)
        db.query(WebLFGMember).filter_by(user_id=user_id).delete(synchronize_session=False)
        db.query(WebRaffleEntry).filter_by(user_id=user_id).delete(synchronize_session=False)
        db.query(WebCreatorProfile).filter_by(user_id=user_id).delete(synchronize_session=False)
        db.query(WebUser).filter_by(id=user_id).delete(synchronize_session=False)

        db.commit()

    # Image files are deleted after the DB commit so we don't orphan records if unlink fails
    for file_path in image_paths:
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
        except OSError:
            logger.warning(f"Failed to delete file during account deletion: {file_path}")

    logger.warning("Account self-deletion completed: user_id=%s ip=%s", user_id, _ip)
    request.session.flush()

    return JsonResponse({'success': True, 'message': 'Account and all data permanently deleted'})


# =============================================================================
# PRIVACY & NOTIFICATION PREFERENCES
# =============================================================================

@web_login_required
@require_http_methods(["POST"])
def api_save_user_prefs(request):
    """POST: Save privacy and notification preference checkboxes."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        # Privacy
        if 'show_steam_profile' in data:
            user.show_steam_profile = bool(data['show_steam_profile'])
        if 'share_steam_library' in data:
            user.share_steam_library = bool(data['share_steam_library'])
        if 'show_activity' in data:
            user.show_activity = bool(data['show_activity'])
        if 'allow_messages' in data:
            user.allow_messages = bool(data['allow_messages'])
        # Champion opt-in listing (only Champions can enable this)
        if 'show_as_champion' in data and user.is_hero:
            user.show_as_champion = 1 if data['show_as_champion'] else 0

        # Activity feed / ticker opt-outs
        _ticker_fields = [
            'ticker_show_live', 'ticker_show_playing', 'ticker_show_posts',
            'ticker_show_follows', 'ticker_show_lfg',
        ]
        for field in _ticker_fields:
            if field in data:
                setattr(user, field, bool(data[field]))

        # Notifications
        _notif_fields = [
            'notify_follows', 'notify_likes', 'notify_comments', 'notify_comment_likes',
            'notify_shares', 'notify_mentions',
            'notify_giveaways', 'notify_lfg_join', 'notify_lfg_leave', 'notify_lfg_full',
            'notify_lfg_game_owned', 'notify_community_join', 'notify_now_playing', 'notify_level_up',
        ]
        for field in _notif_fields:
            if field in data:
                setattr(user, field, bool(data[field]))

        user.updated_at = int(time.time())
        db.commit()

        return JsonResponse({
            'success': True,
            'show_steam_profile': user.show_steam_profile,
            'show_activity': user.show_activity,
            'allow_messages': user.allow_messages,
            'show_as_champion': bool(user.show_as_champion),
            **{f: getattr(user, f) for f in _notif_fields},
        })


# =============================================================================
# STEAM TRACKING PREFERENCES
# =============================================================================

@web_login_required
@require_http_methods(["POST"])
def api_save_steam_prefs(request):
    """POST: Save Steam tracking opt-in preferences."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        if not user.steam_id:
            return JsonResponse({'error': 'No Steam account linked.'}, status=400)

        if 'track_achievements' in data:
            user.track_achievements = bool(data['track_achievements'])
        if 'track_hours_played' in data:
            user.track_hours_played = bool(data['track_hours_played'])
        if 'show_playing_status' in data:
            user.show_playing_status = bool(data['show_playing_status'])
            # Clear current_game immediately when opting out
            if not user.show_playing_status:
                user.current_game = None
        if 'track_game_launches' in data:
            user.track_game_launches = bool(data['track_game_launches'])
        if 'share_steam_library' in data:
            user.share_steam_library = bool(data['share_steam_library'])
        if 'fluxer_sync_custom_status' in data:
            # Only allow if Fluxer is actually linked and we have a stored token
            if user.fluxer_id and user.fluxer_access_token_enc:
                user.fluxer_sync_custom_status = bool(data['fluxer_sync_custom_status'])

        user.updated_at = int(time.time())
        db.commit()

    return JsonResponse({
        'success': True,
        'track_achievements': user.track_achievements,
        'track_hours_played': user.track_hours_played,
        'show_playing_status': user.show_playing_status,
        'track_game_launches': user.track_game_launches,
        'fluxer_sync_custom_status': user.fluxer_sync_custom_status,
    })


# =============================================================================
# NOW PLAYING STATUS (polled every 30s by client)
# =============================================================================

_NSFW_TAGS = ('sexual content', 'hentai', 'adult only sexual content')


def _is_game_nsfw(db, appid) -> bool:
    """Return True if this Steam appid has NSFW tags in web_steam_app_tags."""
    if not appid:
        return False
    try:
        row = db.execute(
            sa_text(
                "SELECT 1 FROM web_steam_app_tags "
                "WHERE app_id = :aid AND tag_name IN :tags LIMIT 1"
            ),
            {'aid': appid, 'tags': _NSFW_TAGS},
        ).first()
        return row is not None
    except Exception:
        return False


@web_login_required
@require_http_methods(["GET"])
def api_me_now_playing(request):
    """GET: Return current user's live now-playing status (fresh DB read)."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'current_game': None, 'is_live': False})
        game = user.current_game if user.show_playing_status else None
        game_appid = user.current_game_appid if game else None
        if game and _is_game_nsfw(db, game_appid):
            game = None
            game_appid = None
    return JsonResponse({
        'current_game': game,
        'current_game_appid': game_appid,
        'is_live': bool(user.is_live),
        'live_platform': user.live_platform or '',
        'live_url': user.live_url or '',
    })


@require_http_methods(["GET"])
def api_user_now_playing(request, username):
    """GET: Public now-playing status for any user (no auth required)."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(
            username=username, is_banned=False, is_disabled=False,
        ).first()
        if not user:
            return JsonResponse({'current_game': None, 'is_live': False})
        game = user.current_game if user.show_playing_status else None
        game_appid = user.current_game_appid if game else None
        if game and _is_game_nsfw(db, game_appid):
            game = None
            game_appid = None
    return JsonResponse({
        'current_game': game,
        'current_game_appid': game_appid,
        'is_live': bool(user.is_live),
        'live_platform': user.live_platform or '',
        'live_url': user.live_url or '',
    })


# =============================================================================
# PULL AVATAR FROM LINKED ACCOUNT
# =============================================================================

@web_login_required
@require_http_methods(["POST"])
def api_pull_avatar(request):
    """Set avatar_url to the user's Steam or Discord avatar."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    source = data.get('source', '').lower()
    if source not in ('steam', 'discord'):
        return JsonResponse({'error': 'Invalid source. Must be steam or discord.'}, status=400)

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user:
            return JsonResponse({'error': 'User not found'}, status=404)

        if source == 'steam':
            if not user.steam_avatar:
                return JsonResponse({'error': 'No Steam account linked.'}, status=400)
            user.avatar_url = user.steam_avatar
            new_url = user.steam_avatar

        elif source == 'discord':
            from urllib.parse import urlparse as _urlparse
            discord_user = request.session.get('discord_user', {})
            avatar_url = discord_user.get('avatar_url')
            if not avatar_url:
                return JsonResponse({'error': 'No Discord account linked or no avatar set.'}, status=400)
            _p = _urlparse(avatar_url)
            if _p.scheme != 'https' or _p.netloc not in ('cdn.discordapp.com', 'media.discordapp.net'):
                return JsonResponse({'error': 'Invalid avatar URL.'}, status=400)
            user.avatar_url = avatar_url
            new_url = avatar_url

        user.updated_at = int(time.time())

    # Update session so the navbar avatar updates immediately
    request.session['web_user_avatar'] = new_url
    request.session.modified = True

    return JsonResponse({'success': True, 'avatar_url': new_url})


# =============================================================================
# FLAIR ENDPOINTS
# =============================================================================

@web_login_required
@add_web_user_context
@require_http_methods(['GET'])
def api_flairs(request):
    """List flairs for the current user.
    Shop-visible: all enabled non-admin-only flairs (whether owned or not).
    Also included: any admin-only flairs the user actually owns.
    """
    with get_db_session() as db:
        user_id = request.web_user.id
        equipped_id = request.web_user.active_flair_id
        equipped_id2 = getattr(request.web_user, 'active_flair2_id', None)

        # All flairs the user owns (any type)
        owned_rows = db.query(WebUserFlair).filter_by(user_id=user_id).all()
        owned_ids = {uf.flair_id for uf in owned_rows}

        # Shop flairs: enabled, non-admin-only
        shop_flairs = (
            db.query(WebFlair)
            .filter(WebFlair.enabled == True, WebFlair.admin_only != 1)
            .order_by(WebFlair.display_order, WebFlair.id)
            .all()
        )
        # Admin-only flairs this user owns (granted by admin) - not in shop
        admin_owned_flairs = (
            db.query(WebFlair)
            .filter(WebFlair.enabled == True, WebFlair.admin_only == 1,
                    WebFlair.id.in_(owned_ids))
            .order_by(WebFlair.display_order, WebFlair.id)
            .all()
        ) if owned_ids else []

        from sqlalchemy import func as sqlfunc
        owner_counts = {
            flair_id: count
            for flair_id, count in db.query(WebUserFlair.flair_id, sqlfunc.count(WebUserFlair.id))
            .group_by(WebUserFlair.flair_id).all()
        }

        from app.questlog_web.views_auth import FOUNDING_FLAIR_LIMIT, FOUNDING_FLAIR_NAME
        now_ts = int(time.time())

        def _serialize(f, is_admin_only_owned=False):
            is_owned = f.id in owned_ids
            available = True
            available_from_ts = None
            available_until_ts = None
            available_from_label = None
            if f.available_from and now_ts < f.available_from:
                available = False
                available_from_ts = f.available_from
                from datetime import datetime, timezone as tz
                dt = datetime.fromtimestamp(f.available_from, tz=tz.utc)
                available_from_label = f"Available {dt.strftime('%b %-d, %Y')}"
            if f.available_until:
                available_until_ts = f.available_until
            return {
                'id': f.id,
                'name': f.name,
                'emoji': f.emoji or '',
                'description': f.description or '',
                'flair_type': f.flair_type,
                'hp_cost': f.hp_cost,
                'owned': is_owned,
                'admin_only': bool(getattr(f, 'admin_only', 0)),
                'equipped': f.id == equipped_id,
                'equipped_slot2': f.id == equipped_id2 if equipped_id2 else False,
                'available': available,
                'available_from': available_from_ts,
                'available_from_label': available_from_label,
                'available_until': available_until_ts,
                'equippable': bool(getattr(f, 'equippable', 1)),
            }

        data = [_serialize(f) for f in shop_flairs]
        # Append admin-only owned flairs at the end (not visible in shop, but user can equip)
        data += [_serialize(f, is_admin_only_owned=True) for f in admin_owned_flairs]

    return JsonResponse({'flairs': data})


@web_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_flair_buy(request, flair_id):
    """Purchase a flair with Hero Points."""
    resp = check_banned(request)
    if resp:
        return resp

    with get_db_session() as db:
        flair = db.query(WebFlair).filter_by(id=flair_id, enabled=True).first()
        if not flair:
            return JsonResponse({'error': 'Flair not found.'}, status=404)

        # Exclusive and admin-only flairs cannot be purchased
        if flair.flair_type == 'exclusive':
            return JsonResponse({'error': 'This flair is award-only and cannot be purchased.'}, status=403)
        if getattr(flair, 'admin_only', 0):
            return JsonResponse({'error': 'This flair can only be assigned by an admin.'}, status=403)

        already = db.query(WebUserFlair).filter_by(
            user_id=request.web_user.id, flair_id=flair_id
        ).first()
        if already:
            return JsonResponse({'error': 'You already own this flair.'}, status=400)

        # Time-gate check: flair has a limited availability window
        now_ts = int(time.time())
        if flair.available_from and now_ts < flair.available_from:
            return JsonResponse({'error': 'This flair is not yet available.'}, status=403)
        if flair.available_until and now_ts > flair.available_until:
            return JsonResponse({'error': 'This flair is no longer available.'}, status=403)

        # Hero-exclusive flairs require an active Hero subscription (admins bypass)
        if flair.flair_type == 'hero':
            now_ts = int(time.time())
            check_user = db.query(WebUser).filter_by(id=request.web_user.id).first()
            is_admin = bool(getattr(check_user, 'is_admin', 0))
            if not is_admin and not (
                check_user
                and getattr(check_user, 'is_hero', 0)
                and getattr(check_user, 'hero_expires_at', None)
                and check_user.hero_expires_at > now_ts
            ):
                return JsonResponse({'error': 'This flair is exclusive to Hero subscribers.'}, status=403)

        # Use with_for_update() to lock the row and prevent race condition
        # (two concurrent requests both passing the HP check and double-spending)
        user = db.query(WebUser).filter_by(id=request.web_user.id).with_for_update().first()
        if (user.hero_points or 0) < flair.hp_cost:
            return JsonResponse({'error': f'Not enough Hero Points (need {flair.hp_cost}, have {user.hero_points or 0}).'}, status=400)

        user.hero_points = (user.hero_points or 0) - flair.hp_cost
        now = int(time.time())
        # Log HP spend
        from .models import WebHeroPointEvent
        db.add(WebHeroPointEvent(
            user_id=user.id,
            action_type='flair_purchase',
            points=-flair.hp_cost,
            source='web',
            ref_id=str(flair.id),
            created_at=now,
        ))
        db.add(WebUserFlair(
            user_id=user.id,
            flair_id=flair.id,
            is_equipped=False,
            purchased_at=now,
        ))
        db.commit()

    return JsonResponse({'success': True, 'hero_points': user.hero_points})


@web_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_flair_equip(request, flair_id):
    """Equip (or unequip) a flair the user owns.
    Champions can use slot=2 in the request body to equip a second flair simultaneously.
    Slot 1 is always available; slot 2 requires is_hero=1.
    """
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, ValueError):
        body = {}
    slot = 2 if str(body.get('slot', '1')) == '2' else 1

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        is_champion = bool(user.is_hero) or bool(user.is_admin)

        # Champions and admins only for slot 2
        if slot == 2 and not is_champion:
            return JsonResponse({'error': 'Second flair slot requires Champion status.'}, status=403)

        if flair_id == 0:
            # Unequip the requested slot
            if slot == 2:
                user.active_flair2_id = None
            else:
                user.active_flair_id = None
                db.query(WebUserFlair).filter_by(
                    user_id=user.id, is_equipped=True
                ).update({'is_equipped': False})
                _queue_flair_role_update(user.id, 'clear_flair', None, None)
            db.commit()
            return JsonResponse({'success': True, 'slot': slot, 'equipped_flair_id': None})

        uf = db.query(WebUserFlair).filter_by(
            user_id=user.id, flair_id=flair_id
        ).first()
        if not uf:
            return JsonResponse({'error': 'You do not own this flair.'}, status=403)

        flair = db.query(WebFlair).filter_by(id=flair_id).first()
        if flair and not getattr(flair, 'equippable', 1):
            return JsonResponse({'error': 'This flair is a trophy and cannot be equipped.'}, status=403)
        flair_emoji = flair.emoji if flair else ''
        flair_name  = flair.name  if flair else ''

        if slot == 2:
            # Slot 2: just assign, don't touch slot 1
            user.active_flair2_id = flair_id
        else:
            # Slot 1: unequip all is_equipped flags, equip this one
            db.query(WebUserFlair).filter_by(user_id=user.id, is_equipped=True).update({'is_equipped': False})
            uf.is_equipped = True
            user.active_flair_id = flair_id
            _queue_flair_role_update(user.id, 'set_flair', flair_emoji, flair_name)
        db.commit()

    return JsonResponse({'success': True, 'slot': slot, 'equipped_flair_id': flair_id})
