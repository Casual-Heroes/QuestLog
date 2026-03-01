# QuestLog Web — file uploads & GIF search

import os
import json
import time
import logging

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .models import WebUser, WebCommunity
from app.db import get_db_session
from .helpers import (
    web_login_required, add_web_user_context,
    check_banned, process_uploaded_image,
)

logger = logging.getLogger(__name__)


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='20/h', method='POST', block=True)
def api_upload_image(request):
    """POST: Upload an image for use in posts. Max 40MB input (15MB GIF). Always converted to WebP on save."""
    banned = check_banned(request)
    if banned:
        return banned

    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image file provided'}, status=400)

    try:
        result = process_uploaded_image(request.FILES['image'], dest_subdir='posts')
        return JsonResponse({'success': True, **result})
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Image upload error: {e}")
        return JsonResponse({'error': 'Upload failed'}, status=500)


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='5/h', method='POST', block=True)
def api_upload_avatar(request):
    """POST: Upload avatar image. Max 2MB."""
    banned = check_banned(request)
    if banned:
        return banned

    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image file provided'}, status=400)

    try:
        result = process_uploaded_image(
            request.FILES['image'], dest_subdir='avatars',
            max_size_bytes=2 * 1024 * 1024, max_gif_size=2 * 1024 * 1024
        )
        with get_db_session() as db:
            user = db.query(WebUser).filter_by(id=request.web_user.id).first()
            if user:
                user.avatar_url = result['image_url']
                user.updated_at = int(time.time())
                db.commit()
        # Update session so navbar avatar refreshes without a page reload
        request.session['web_user_avatar'] = result['image_url']
        request.session.modified = True
        return JsonResponse({'success': True, 'avatar_url': result['image_url']})
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Avatar upload error: {e}")
        return JsonResponse({'error': 'Upload failed'}, status=500)


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='5/h', method='POST', block=True)
def api_upload_banner(request):
    """POST: Upload banner image. Max 5MB."""
    banned = check_banned(request)
    if banned:
        return banned

    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image file provided'}, status=400)

    try:
        result = process_uploaded_image(
            request.FILES['image'], dest_subdir='banners'
        )
        with get_db_session() as db:
            user = db.query(WebUser).filter_by(id=request.web_user.id).first()
            if user:
                user.banner_url = result['image_url']
                user.updated_at = int(time.time())
                db.commit()
        return JsonResponse({'success': True, 'banner_url': result['image_url']})
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Banner upload error: {e}")
        return JsonResponse({'error': 'Upload failed'}, status=500)


# =============================================================================
# COMMUNITY IMAGE UPLOADS
# =============================================================================

@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def api_upload_community_icon(request, community_id):
    """POST: Upload community icon (avatar). Max 2MB. Owner only."""
    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image file provided'}, status=400)

    with get_db_session() as db:
        community = db.query(WebCommunity).filter_by(id=community_id).first()
        if not community:
            return JsonResponse({'error': 'Community not found'}, status=404)
        if community.owner_id != request.web_user.id:
            return JsonResponse({'error': 'Not your community'}, status=403)

        try:
            result = process_uploaded_image(
                request.FILES['image'], dest_subdir='community_icons',
                max_size_bytes=2 * 1024 * 1024, max_gif_size=2 * 1024 * 1024
            )
            community.icon_url = result['image_url']
            community.updated_at = int(time.time())
            db.commit()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            logger.error(f"Community icon upload error: {e}")
            return JsonResponse({'error': 'Upload failed'}, status=500)

    return JsonResponse({'success': True, 'icon_url': result['image_url']})


@web_login_required
@require_http_methods(["POST"])
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def api_upload_community_banner(request, community_id):
    """POST: Upload community banner. Max 5MB. Owner only."""
    if 'image' not in request.FILES:
        return JsonResponse({'error': 'No image file provided'}, status=400)

    with get_db_session() as db:
        community = db.query(WebCommunity).filter_by(id=community_id).first()
        if not community:
            return JsonResponse({'error': 'Community not found'}, status=404)
        if community.owner_id != request.web_user.id:
            return JsonResponse({'error': 'Not your community'}, status=403)

        try:
            result = process_uploaded_image(
                request.FILES['image'], dest_subdir='community_banners',
                max_size_bytes=5 * 1024 * 1024
            )
            community.banner_url = result['image_url']
            community.updated_at = int(time.time())
            db.commit()
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        except Exception as e:
            logger.error(f"Community banner upload error: {e}")
            return JsonResponse({'error': 'Upload failed'}, status=500)

    return JsonResponse({'success': True, 'banner_url': result['image_url']})


# =============================================================================
# GIF SEARCH API (Tenor proxy)
# =============================================================================

@web_login_required
@add_web_user_context
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def api_gif_search(request):
    """GET: Search GIPHY for GIFs. Proxied to keep API key server-side."""
    import urllib.request
    import urllib.parse

    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    api_key = os.getenv('GIPHY_API_KEY', '')
    if not api_key:
        return JsonResponse({'error': 'GIF search not configured'}, status=503)

    try:
        params = urllib.parse.urlencode({
            'q': query,
            'api_key': api_key,
            'limit': 20,
            'rating': 'pg-13',
            'lang': 'en',
        })
        url = f'https://api.giphy.com/v1/gifs/search?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'QuestLog/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            giphy_data = json.loads(resp.read().decode())

        results = []
        for item in giphy_data.get('data', []):
            images = item.get('images', {})
            original = images.get('original', {})
            preview = images.get('fixed_width_small', {}) or images.get('preview_gif', {})
            if original.get('url'):
                results.append({
                    'id': item.get('id'),
                    'url': original['url'],
                    'preview': preview.get('url', original['url']),
                    'width': int(original.get('width', 0)),
                    'height': int(original.get('height', 0)),
                    'title': item.get('title', ''),
                })
        return JsonResponse({'results': results})
    except Exception as e:
        logger.error(f"GIPHY search error: {e}")
        return JsonResponse({'results': [], 'error': 'Search failed'})


@web_login_required
@add_web_user_context
@require_http_methods(["GET"])
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def api_gif_trending(request):
    """GET: Trending GIFs from GIPHY."""
    import urllib.request
    import urllib.parse

    api_key = os.getenv('GIPHY_API_KEY', '')
    if not api_key:
        return JsonResponse({'results': []})

    try:
        params = urllib.parse.urlencode({
            'api_key': api_key,
            'limit': 20,
            'rating': 'pg-13',
        })
        url = f'https://api.giphy.com/v1/gifs/trending?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'QuestLog/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            giphy_data = json.loads(resp.read().decode())

        results = []
        for item in giphy_data.get('data', []):
            images = item.get('images', {})
            original = images.get('original', {})
            preview = images.get('fixed_width_small', {}) or images.get('preview_gif', {})
            if original.get('url'):
                results.append({
                    'id': item.get('id'),
                    'url': original['url'],
                    'preview': preview.get('url', original['url']),
                    'width': int(original.get('width', 0)),
                    'height': int(original.get('height', 0)),
                    'title': item.get('title', ''),
                })
        return JsonResponse({'results': results})
    except Exception as e:
        logger.error(f"GIPHY trending error: {e}")
        return JsonResponse({'results': []})
