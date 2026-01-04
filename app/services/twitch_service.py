"""
Twitch API Service

Handles Twitch OAuth, API interactions, and live stream monitoring.
Security: All tokens are encrypted before storage using encryption.py
"""

import os
import requests
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta


class TwitchAPIError(Exception):
    """Custom exception for Twitch API errors."""
    pass


class TwitchService:
    """Service for interacting with Twitch API."""

    def __init__(self):
        self.client_id = os.getenv('TWITCH_CLIENT_ID', '')
        self.client_secret = os.getenv('TWITCH_CLIENT_SECRET', '')
        self.redirect_uri = os.getenv('TWITCH_REDIRECT_URI', 'https://casual-heroes.com/api/twitch/oauth/callback')

        if not self.client_id or not self.client_secret:
            raise TwitchAPIError("Twitch API credentials not configured")

    def get_authorization_url(self, state: str) -> str:
        """
        Generate Twitch OAuth authorization URL.

        Args:
            state: CSRF protection token

        Returns:
            Authorization URL to redirect user to
        """
        scopes = [
            'user:read:email',
            'channel:read:subscriptions',
        ]

        params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': ' '.join(scopes),
            'state': state,
            'force_verify': 'true',  # Force user to re-authorize for fresh tokens
        }

        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"https://id.twitch.tv/oauth2/authorize?{query_string}"

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Dict with access_token, refresh_token, expires_in, token_type

        Raises:
            TwitchAPIError: If token exchange fails
        """
        url = 'https://id.twitch.tv/oauth2/token'
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri,
        }

        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise TwitchAPIError(f"Failed to exchange code for token: {e}")

    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh an expired access token.

        Args:
            refresh_token: The refresh token

        Returns:
            Dict with new access_token and expires_in

        Raises:
            TwitchAPIError: If token refresh fails
        """
        url = 'https://id.twitch.tv/oauth2/token'
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }

        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise TwitchAPIError(f"Failed to refresh token: {e}")

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get authenticated user's Twitch info.

        Args:
            access_token: OAuth access token

        Returns:
            Dict with: id, login, display_name, profile_image_url, view_count, broadcaster_type

        Raises:
            TwitchAPIError: If API request fails
        """
        url = 'https://api.twitch.tv/helix/users'
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Client-Id': self.client_id,
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get('data'):
                raise TwitchAPIError("No user data returned")

            user = data['data'][0]
            return {
                'id': user['id'],
                'login': user['login'],
                'display_name': user['display_name'],
                'profile_image_url': user.get('profile_image_url'),
                'view_count': user.get('view_count', 0),
                'broadcaster_type': user.get('broadcaster_type', ''),
            }
        except requests.exceptions.RequestException as e:
            raise TwitchAPIError(f"Failed to get user info: {e}")

    def get_channel_info(self, access_token: str, user_id: str) -> Dict[str, Any]:
        """
        Get channel information (followers, etc).

        Args:
            access_token: OAuth access token
            user_id: Twitch user ID

        Returns:
            Dict with follower_count and other channel stats

        Raises:
            TwitchAPIError: If API request fails
        """
        # Get follower count
        url = f'https://api.twitch.tv/helix/channels/followers?broadcaster_id={user_id}'
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Client-Id': self.client_id,
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            return {
                'follower_count': data.get('total', 0),
            }
        except requests.exceptions.RequestException as e:
            raise TwitchAPIError(f"Failed to get channel info: {e}")

    def get_live_streams(self, access_token: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Check if user is currently live streaming.

        Args:
            access_token: OAuth access token
            user_id: Twitch user ID

        Returns:
            Dict with stream info if live, None if offline
            Stream info: title, game_name, viewer_count, started_at, thumbnail_url

        Raises:
            TwitchAPIError: If API request fails
        """
        url = f'https://api.twitch.tv/helix/streams?user_id={user_id}'
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Client-Id': self.client_id,
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data.get('data'):
                return None  # Not live

            stream = data['data'][0]

            # Parse started_at timestamp
            started_at_str = stream.get('started_at')
            started_at = None
            if started_at_str:
                try:
                    dt = datetime.strptime(started_at_str, '%Y-%m-%dT%H:%M:%SZ')
                    started_at = int(dt.timestamp())
                except ValueError:
                    pass

            # Generate thumbnail URL (replace template variables)
            thumbnail_url = stream.get('thumbnail_url', '')
            if thumbnail_url:
                thumbnail_url = thumbnail_url.replace('{width}', '1920').replace('{height}', '1080')

            return {
                'title': stream.get('title', 'Untitled Stream'),
                'game_name': stream.get('game_name', 'No Category'),
                'viewer_count': stream.get('viewer_count', 0),
                'started_at': started_at,
                'thumbnail_url': thumbnail_url,
                'stream_type': stream.get('type', 'live'),
            }
        except requests.exceptions.RequestException as e:
            raise TwitchAPIError(f"Failed to get live streams: {e}")

    def get_recent_videos(self, access_token: str, user_id: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """
        Get recent VODs from a Twitch channel.

        Args:
            access_token: OAuth access token
            user_id: Twitch user ID
            max_results: Maximum number of videos to return

        Returns:
            List of video dicts with: id, title, description, thumbnail_url,
            duration, view_count, published_at, url

        Raises:
            TwitchAPIError: If API request fails
        """
        url = f'https://api.twitch.tv/helix/videos?user_id={user_id}&first={max_results}&type=archive'
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Client-Id': self.client_id,
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            videos = []
            for video in data.get('data', []):
                # Parse published timestamp
                published_at_str = video.get('published_at')
                published_at = None
                if published_at_str:
                    try:
                        dt = datetime.strptime(published_at_str, '%Y-%m-%dT%H:%M:%SZ')
                        published_at = int(dt.timestamp())
                    except ValueError:
                        pass

                # Parse duration (format: "1h2m3s")
                duration_str = video.get('duration', '0s')
                duration_seconds = self._parse_duration(duration_str)

                videos.append({
                    'id': video['id'],
                    'title': video.get('title', 'Untitled'),
                    'description': video.get('description', ''),
                    'thumbnail_url': video.get('thumbnail_url', ''),
                    'duration': duration_seconds,
                    'view_count': video.get('view_count', 0),
                    'published_at': published_at,
                    'url': video.get('url', ''),
                })

            return videos
        except requests.exceptions.RequestException as e:
            raise TwitchAPIError(f"Failed to get recent videos: {e}")

    def _parse_duration(self, duration_str: str) -> int:
        """
        Parse Twitch duration string to seconds.

        Args:
            duration_str: Duration like "1h2m3s"

        Returns:
            Total seconds
        """
        total_seconds = 0
        current_num = ''

        for char in duration_str:
            if char.isdigit():
                current_num += char
            elif char == 'h' and current_num:
                total_seconds += int(current_num) * 3600
                current_num = ''
            elif char == 'm' and current_num:
                total_seconds += int(current_num) * 60
                current_num = ''
            elif char == 's' and current_num:
                total_seconds += int(current_num)
                current_num = ''

        return total_seconds

    def revoke_token(self, access_token: str) -> bool:
        """
        Revoke an access token.

        Args:
            access_token: Token to revoke

        Returns:
            True if successful

        Raises:
            TwitchAPIError: If revocation fails
        """
        url = 'https://id.twitch.tv/oauth2/revoke'
        data = {
            'client_id': self.client_id,
            'token': access_token,
        }

        try:
            response = requests.post(url, data=data, timeout=10)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            raise TwitchAPIError(f"Failed to revoke token: {e}")
