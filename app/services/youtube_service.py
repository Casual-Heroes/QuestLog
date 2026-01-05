"""
YouTube API Service

Handles YouTube Data API v3 operations:
- OAuth2 authentication flow
- Channel information retrieval
- Live stream status checking
- Video/VOD fetching
- Token refresh handling
"""

import requests
import json
import time
from typing import Optional, Dict, Any, List
from django.conf import settings
from urllib.parse import urlencode
import logging

logger = logging.getLogger(__name__)


class YouTubeAPIError(Exception):
    """Custom exception for YouTube API errors."""
    pass


class YouTubeService:
    """Service class for interacting with YouTube Data API v3."""

    # API Endpoints
    OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
    API_BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        """Initialize YouTube service with credentials from settings."""
        self.client_id = settings.YOUTUBE_CLIENT_ID
        self.client_secret = settings.YOUTUBE_CLIENT_SECRET
        self.api_key = settings.YOUTUBE_API_KEY
        self.redirect_uri = settings.YOUTUBE_REDIRECT_URI
        self.scopes = settings.YOUTUBE_OAUTH_SCOPES

        if not all([self.client_id, self.client_secret, self.api_key]):
            logger.warning("YouTube API credentials not fully configured in settings")

    # =========================================================================
    # OAuth2 Flow
    # =========================================================================

    def get_authorization_url(self, state: str) -> str:
        """
        Generate OAuth2 authorization URL for user to grant access.

        Args:
            state: Random state string for CSRF protection

        Returns:
            Authorization URL to redirect user to
        """
        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(self.scopes),
            'access_type': 'offline',  # Get refresh token
            'prompt': 'consent',  # Force consent screen to get refresh token
            'state': state,
        }

        return f"{self.OAUTH_AUTH_URL}?{urlencode(params)}"

    def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Dict containing:
                - access_token: OAuth2 access token
                - refresh_token: OAuth2 refresh token
                - expires_in: Token expiration time in seconds
                - token_type: Token type (usually "Bearer")

        Raises:
            YouTubeAPIError: If token exchange fails
        """
        try:
            response = requests.post(self.OAUTH_TOKEN_URL, data={
                'code': code,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'redirect_uri': self.redirect_uri,
                'grant_type': 'authorization_code',
            })

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"YouTube token exchange failed: {e}")
            raise YouTubeAPIError(f"Failed to exchange code for tokens: {e}")

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token using refresh token.

        Args:
            refresh_token: OAuth2 refresh token

        Returns:
            Dict containing:
                - access_token: New access token
                - expires_in: Token expiration time in seconds
                - token_type: Token type

        Raises:
            YouTubeAPIError: If token refresh fails
        """
        try:
            response = requests.post(self.OAUTH_TOKEN_URL, data={
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token',
            })

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            logger.error(f"YouTube token refresh failed: {e}")
            raise YouTubeAPIError(f"Failed to refresh access token: {e}")

    # =========================================================================
    # Channel Information
    # =========================================================================

    def get_channel_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get authenticated user's channel information.

        Args:
            access_token: OAuth2 access token

        Returns:
            Dict containing channel info:
                - id: Channel ID
                - title: Channel name
                - description: Channel description
                - thumbnail_url: Channel thumbnail URL
                - subscriber_count: Number of subscribers
                - video_count: Number of videos
                - view_count: Total views
                - custom_url: Custom channel URL (if set)

        Raises:
            YouTubeAPIError: If API request fails
        """
        try:
            response = requests.get(
                f"{self.API_BASE_URL}/channels",
                headers={'Authorization': f'Bearer {access_token}'},
                params={
                    'part': 'snippet,statistics,contentDetails',
                    'mine': 'true',
                }
            )

            response.raise_for_status()
            data = response.json()

            if not data.get('items'):
                raise YouTubeAPIError("No channel found for this account")

            channel = data['items'][0]
            snippet = channel.get('snippet', {})
            statistics = channel.get('statistics', {})

            return {
                'id': channel.get('id'),
                'title': snippet.get('title'),
                'description': snippet.get('description'),
                'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                'custom_url': snippet.get('customUrl'),
                'subscriber_count': int(statistics.get('subscriberCount', 0)),
                'video_count': int(statistics.get('videoCount', 0)),
                'view_count': int(statistics.get('viewCount', 0)),
            }

        except requests.RequestException as e:
            logger.error(f"YouTube channel info request failed: {e}")
            raise YouTubeAPIError(f"Failed to get channel info: {e}")

    # =========================================================================
    # Live Stream Status
    # =========================================================================

    def get_live_broadcasts(
        self,
        access_token: str,
        channel_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Check if channel is currently live streaming.

        Args:
            access_token: OAuth2 access token

        Returns:
            Dict with live stream info if live, None if not live:
                - title: Stream title
                - description: Stream description
                - thumbnail_url: Stream thumbnail
                - viewer_count: Current viewers
                - started_at: Stream start timestamp
                - game_name: Category/game (if available)

        Raises:
            YouTubeAPIError: If API request fails
        """
        try:
            response = requests.get(
                f"{self.API_BASE_URL}/liveBroadcasts",
                headers={'Authorization': f'Bearer {access_token}'},
                params={
                    'part': 'snippet,status,contentDetails',
                    'mine': 'true',
                    'maxResults': 5,
                }
            )

            response.raise_for_status()
            data = response.json()

            items = data.get('items', [])
            if not items:
                return None  # Not currently live

            broadcast = None
            for item in items:
                status = item.get('status', {})
                if status.get('lifeCycleStatus') in ('live', 'liveStarting'):
                    broadcast = item
                    break

            if not broadcast:
                return None

            snippet = broadcast.get('snippet', {})

            # Try to get game/category from snippet
            game_name = None
            if snippet.get('categoryId'):
                game_name = self._get_category_name(snippet['categoryId'])

            return {
                'title': snippet.get('title'),
                'description': snippet.get('description'),
                'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                'viewer_count': 0,
                'started_at': snippet.get('actualStartTime'),  # ISO 8601 format
                'game_name': game_name,
            }

        except requests.RequestException as e:
            response = getattr(e, 'response', None)
            if response is not None:
                logger.error(
                    "YouTube live broadcast check failed: %s (status=%s, body=%s)",
                    e,
                    response.status_code,
                    response.text[:500],
                )
            else:
                logger.error(f"YouTube live broadcast check failed: {e}")

            if channel_id and self.api_key:
                try:
                    return self._get_live_broadcasts_by_channel_id(channel_id)
                except YouTubeAPIError:
                    raise
            raise YouTubeAPIError(f"Failed to check live status: {e}")

    def _get_live_broadcasts_by_channel_id(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        Fallback live check using channel ID and API key.

        Uses search.list + videos.list to determine if a public live stream is active.
        """
        try:
            search_resp = requests.get(
                f"{self.API_BASE_URL}/search",
                params={
                    'part': 'snippet',
                    'channelId': channel_id,
                    'eventType': 'live',
                    'type': 'video',
                    'maxResults': 1,
                    'key': self.api_key,
                }
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()

            if not search_data.get('items'):
                return None

            video_id = search_data['items'][0].get('id', {}).get('videoId')
            if not video_id:
                return None

            video_resp = requests.get(
                f"{self.API_BASE_URL}/videos",
                params={
                    'part': 'snippet,liveStreamingDetails,statistics',
                    'id': video_id,
                    'key': self.api_key,
                }
            )
            video_resp.raise_for_status()
            video_data = video_resp.json()
            if not video_data.get('items'):
                return None

            video = video_data['items'][0]
            snippet = video.get('snippet', {})
            live_details = video.get('liveStreamingDetails', {})
            statistics = video.get('statistics', {})

            game_name = None
            if snippet.get('categoryId'):
                game_name = self._get_category_name(snippet['categoryId'])

            viewer_count = live_details.get('concurrentViewers')
            if viewer_count is None:
                viewer_count = statistics.get('viewCount', 0)

            return {
                'title': snippet.get('title'),
                'description': snippet.get('description'),
                'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                'viewer_count': int(viewer_count or 0),
                'started_at': live_details.get('actualStartTime'),
                'game_name': game_name,
            }

        except requests.RequestException as e:
            response = getattr(e, 'response', None)
            if response is not None:
                logger.error(
                    "YouTube live fallback check failed: %s (status=%s, body=%s)",
                    e,
                    response.status_code,
                    response.text[:500],
                )
            raise YouTubeAPIError(f"Failed to check live status (fallback): {e}")

    def _get_category_name(self, category_id: str) -> Optional[str]:
        """
        Get category name from category ID.

        Args:
            category_id: YouTube video category ID

        Returns:
            Category name or None if not found
        """
        try:
            response = requests.get(
                f"{self.API_BASE_URL}/videoCategories",
                params={
                    'part': 'snippet',
                    'id': category_id,
                    'key': self.api_key,  # Use API key for public data
                }
            )

            response.raise_for_status()
            data = response.json()

            if data.get('items'):
                return data['items'][0]['snippet']['title']

            return None

        except requests.RequestException:
            return None

    # =========================================================================
    # Videos & VODs
    # =========================================================================

    def get_recent_videos(
        self,
        access_token: str,
        max_results: int = 10,
        include_live: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get recent videos/VODs from channel.

        Args:
            access_token: OAuth2 access token
            max_results: Maximum number of videos to return
            include_live: Whether to include live streams

        Returns:
            List of video dicts containing:
                - id: Video ID
                - title: Video title
                - description: Video description
                - thumbnail_url: Video thumbnail
                - published_at: Upload timestamp
                - duration: Video duration in seconds
                - view_count: View count
                - like_count: Like count
                - comment_count: Comment count

        Raises:
            YouTubeAPIError: If API request fails
        """
        try:
            # First, get channel ID
            channel_info = self.get_channel_info(access_token)
            channel_id = channel_info['id']

            # Get uploads playlist ID (channel uploads)
            response = requests.get(
                f"{self.API_BASE_URL}/channels",
                headers={'Authorization': f'Bearer {access_token}'},
                params={
                    'part': 'contentDetails',
                    'id': channel_id,
                }
            )

            response.raise_for_status()
            data = response.json()

            uploads_playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']

            # Get videos from uploads playlist
            playlist_response = requests.get(
                f"{self.API_BASE_URL}/playlistItems",
                headers={'Authorization': f'Bearer {access_token}'},
                params={
                    'part': 'snippet,contentDetails',
                    'playlistId': uploads_playlist_id,
                    'maxResults': max_results,
                }
            )

            playlist_response.raise_for_status()
            playlist_data = playlist_response.json()

            if not playlist_data.get('items'):
                return []

            # Get video IDs
            video_ids = [
                item['contentDetails']['videoId']
                for item in playlist_data['items']
            ]

            # Get detailed video info
            videos_response = requests.get(
                f"{self.API_BASE_URL}/videos",
                headers={'Authorization': f'Bearer {access_token}'},
                params={
                    'part': 'snippet,contentDetails,statistics',
                    'id': ','.join(video_ids),
                }
            )

            videos_response.raise_for_status()
            videos_data = videos_response.json()

            videos = []
            for video in videos_data.get('items', []):
                snippet = video.get('snippet', {})
                statistics = video.get('statistics', {})
                content_details = video.get('contentDetails', {})

                # Skip live streams if not wanted
                if not include_live and snippet.get('liveBroadcastContent') == 'live':
                    continue

                videos.append({
                    'id': video.get('id'),
                    'title': snippet.get('title'),
                    'description': snippet.get('description'),
                    'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url'),
                    'published_at': snippet.get('publishedAt'),
                    'duration': self._parse_duration(content_details.get('duration')),
                    'view_count': int(statistics.get('viewCount', 0)),
                    'like_count': int(statistics.get('likeCount', 0)),
                    'comment_count': int(statistics.get('commentCount', 0)),
                })

            return videos

        except requests.RequestException as e:
            logger.error(f"YouTube videos request failed: {e}")
            raise YouTubeAPIError(f"Failed to get recent videos: {e}")

    def _parse_duration(self, duration_str: str) -> int:
        """
        Parse ISO 8601 duration string to seconds.

        Args:
            duration_str: Duration in ISO 8601 format (e.g., "PT1H2M10S")

        Returns:
            Duration in seconds
        """
        if not duration_str:
            return 0

        import re

        # Parse PT1H2M10S format
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)

        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds
