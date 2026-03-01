"""
Steam OpenID Authentication for QuestLog Web.

Steam uses OpenID 2.0 for authentication. The flow is:
1. Redirect user to Steam login page
2. Steam redirects back with OpenID response
3. Verify the response and extract Steam ID
4. Fetch user profile from Steam API (requires API key)

To get a Steam Web API key: https://steamcommunity.com/dev/apikey
"""

import re
import time
import logging
import requests
from urllib.parse import urlencode, parse_qs
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)

# Steam OpenID endpoint
STEAM_OPENID_URL = "https://steamcommunity.com/openid/login"

# Steam API for user profile data
STEAM_API_URL = "https://api.steampowered.com"


def get_steam_login_url(return_url: str, realm: str) -> str:
    """
    Generate Steam OpenID login URL.

    Args:
        return_url: URL to redirect back to after login (must match realm)
        realm: The realm (your site's base URL, e.g., https://casual-heroes.com)

    Returns:
        Steam login URL to redirect user to
    """
    params = {
        'openid.ns': 'http://specs.openid.net/auth/2.0',
        'openid.mode': 'checkid_setup',
        'openid.return_to': return_url,
        'openid.realm': realm,
        'openid.identity': 'http://specs.openid.net/auth/2.0/identifier_select',
        'openid.claimed_id': 'http://specs.openid.net/auth/2.0/identifier_select',
    }
    return f"{STEAM_OPENID_URL}?{urlencode(params)}"


def verify_steam_login(request_params: Dict) -> Tuple[bool, Optional[str]]:
    """
    Verify Steam OpenID login response.

    Args:
        request_params: The GET parameters from Steam's redirect

    Returns:
        Tuple of (success, steam_id or None)
    """
    # Check if this is a valid response
    if request_params.get('openid.mode') != 'id_res':
        logger.warning("Steam login: invalid openid.mode")
        return False, None

    # Build verification request
    verify_params = {
        'openid.assoc_handle': request_params.get('openid.assoc_handle'),
        'openid.signed': request_params.get('openid.signed'),
        'openid.sig': request_params.get('openid.sig'),
        'openid.ns': request_params.get('openid.ns'),
        'openid.mode': 'check_authentication',
    }

    # Add signed fields
    signed_fields = request_params.get('openid.signed', '').split(',')
    for field in signed_fields:
        key = f'openid.{field}'
        if key in request_params:
            verify_params[key] = request_params[key]

    try:
        # Verify with Steam
        response = requests.post(
            STEAM_OPENID_URL,
            data=verify_params,
            timeout=10
        )

        if 'is_valid:true' not in response.text:
            logger.warning("Steam login: verification failed")
            return False, None

        # Extract Steam ID from claimed_id
        # Format: https://steamcommunity.com/openid/id/76561198012345678
        claimed_id = request_params.get('openid.claimed_id', '')
        match = re.search(r'steamcommunity\.com/openid/id/(\d+)', claimed_id)

        if not match:
            logger.warning(f"Steam login: could not extract Steam ID from {claimed_id}")
            return False, None

        steam_id = match.group(1)
        logger.info(f"Steam login verified for Steam ID: {steam_id}")
        return True, steam_id

    except requests.RequestException as e:
        logger.error(f"Steam login verification request failed: {e}")
        return False, None


def get_steam_user_profile(steam_id: str, api_key: str) -> Optional[Dict]:
    """
    Fetch Steam user profile using Steam Web API.

    Args:
        steam_id: The user's Steam ID (64-bit)
        api_key: Your Steam Web API key

    Returns:
        User profile dict or None on failure
    """
    if not api_key:
        logger.warning("Steam API key not configured, can't fetch profile")
        return None

    url = f"{STEAM_API_URL}/ISteamUser/GetPlayerSummaries/v2/"
    params = {
        'key': api_key,
        'steamids': steam_id
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        players = data.get('response', {}).get('players', [])
        if not players:
            logger.warning(f"No player data returned for Steam ID {steam_id}")
            return None

        player = players[0]

        return {
            'steam_id': player.get('steamid'),
            'username': player.get('personaname'),
            'avatar': player.get('avatarfull'),  # Full size avatar
            'avatar_medium': player.get('avatarmedium'),
            'avatar_small': player.get('avatar'),
            'profile_url': player.get('profileurl'),
            'profile_state': player.get('profilestate'),  # 1 = public profile
            'persona_state': player.get('personastate'),  # Online status
            'last_logoff': player.get('lastlogoff'),
            'country_code': player.get('loccountrycode'),
        }

    except requests.RequestException as e:
        logger.error(f"Failed to fetch Steam profile for {steam_id}: {e}")
        return None


def get_steam_owned_games(steam_id: str, api_key: str, include_free: bool = True) -> Optional[list]:
    """
    Fetch user's owned Steam games.

    Note: This only works if the user's profile and game details are public.

    Args:
        steam_id: The user's Steam ID (64-bit)
        api_key: Your Steam Web API key
        include_free: Include free-to-play games

    Returns:
        List of owned games or None on failure
    """
    if not api_key:
        logger.warning("Steam API key not configured, can't fetch games")
        return None

    url = f"{STEAM_API_URL}/IPlayerService/GetOwnedGames/v1/"
    params = {
        'key': api_key,
        'steamid': steam_id,
        'include_appinfo': 1,
        'include_played_free_games': 1 if include_free else 0,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        games = data.get('response', {}).get('games', [])

        # Sort by playtime
        games.sort(key=lambda g: g.get('playtime_forever', 0), reverse=True)

        return [
            {
                'app_id': game.get('appid'),
                'name': game.get('name'),
                'playtime_minutes': game.get('playtime_forever', 0),
                'playtime_hours': round(game.get('playtime_forever', 0) / 60, 1),
                'icon_url': f"https://media.steampowered.com/steamcommunity/public/images/apps/{game.get('appid')}/{game.get('img_icon_url')}.jpg" if game.get('img_icon_url') else None,
                'last_played': game.get('rtime_last_played'),
            }
            for game in games
        ]

    except requests.RequestException as e:
        logger.error(f"Failed to fetch Steam games for {steam_id}: {e}")
        return None


def get_steam_recently_played(steam_id: str, api_key: str, count: int = 10) -> Optional[list]:
    """
    Fetch user's recently played Steam games.

    Args:
        steam_id: The user's Steam ID (64-bit)
        api_key: Your Steam Web API key
        count: Number of games to return

    Returns:
        List of recently played games or None on failure
    """
    if not api_key:
        return None

    url = f"{STEAM_API_URL}/IPlayerService/GetRecentlyPlayedGames/v1/"
    params = {
        'key': api_key,
        'steamid': steam_id,
        'count': count,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        games = data.get('response', {}).get('games', [])

        return [
            {
                'app_id': game.get('appid'),
                'name': game.get('name'),
                'playtime_2weeks_minutes': game.get('playtime_2weeks', 0),
                'playtime_2weeks_hours': round(game.get('playtime_2weeks', 0) / 60, 1),
                'playtime_total_minutes': game.get('playtime_forever', 0),
                'playtime_total_hours': round(game.get('playtime_forever', 0) / 60, 1),
                'icon_url': f"https://media.steampowered.com/steamcommunity/public/images/apps/{game.get('appid')}/{game.get('img_icon_url')}.jpg" if game.get('img_icon_url') else None,
            }
            for game in games
        ]

    except requests.RequestException as e:
        logger.error(f"Failed to fetch recently played games for {steam_id}: {e}")
        return None


def get_steam_stats(steam_id: str, api_key: str):
    """
    Fetch total achievements unlocked (across all games) and total hours played.
    Used by the hourly poll_steam_stats management command.

    Returns:
        dict with keys 'achievements_total' (int) and 'hours_total' (int, in minutes)
        or None on failure / private profile.
    """
    if not api_key:
        return None

    # Total playtime from owned games
    try:
        url = f"{STEAM_API_URL}/IPlayerService/GetOwnedGames/v1/"
        resp = requests.get(url, params={
            'key': api_key, 'steamid': steam_id,
            'include_played_free_games': 1,
        }, timeout=15)
        resp.raise_for_status()
        games = resp.json().get('response', {}).get('games', [])
        hours_total = sum(g.get('playtime_forever', 0) for g in games)  # in minutes
    except requests.RequestException as e:
        logger.error(f"get_steam_stats: failed to fetch owned games for {steam_id}: {e}")
        return None

    # Total unlocked achievements via GetPlayerAchievements per game is too slow at scale.
    # Use the global achievement percentages endpoint as a proxy — instead, use
    # GetPlayerStatsForGame is per-app only. Best scalable option: GetSchemaForGame per app.
    # Practical approach: count unlocked achievements from recently-played games only.
    achievements_total = 0
    try:
        for game in games:
            app_id = game.get('appid')
            if not app_id or game.get('playtime_forever', 0) == 0:
                continue
            try:
                ach_resp = requests.get(
                    f"{STEAM_API_URL}/ISteamUserStats/GetPlayerAchievements/v1/",
                    params={'key': api_key, 'steamid': steam_id, 'appid': app_id},
                    timeout=5,
                )
                if ach_resp.status_code == 200:
                    ach_data = ach_resp.json().get('playerstats', {})
                    achievements = ach_data.get('achievements', [])
                    achievements_total += sum(1 for a in achievements if a.get('achieved') == 1)
            except requests.RequestException:
                continue  # skip this game, not fatal
    except Exception as e:
        logger.warning(f"get_steam_stats: achievement scan partial failure for {steam_id}: {e}")

    return {
        'achievements_total': achievements_total,
        'hours_total': hours_total,  # minutes
    }
