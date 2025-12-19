"""
Steam Web API wrapper for game discovery.

Provides functions to fetch new game releases from Steam and filter them
based on user-selected criteria (genres, OS, platforms, etc.).
"""

import requests
import time
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class SteamAPI:
    """Steam Web API client for game discovery."""

    BASE_URL = "https://store.steampowered.com/api"

    # Map our genre names to Steam tags
    GENRE_TAG_MAPPING = {
        "Adventure": ["Adventure"],
        "Indie": ["Indie"],
        "Arcade": ["Arcade"],
        "Visual Novel": ["Visual Novel"],
        "Card & Board Game": ["Card Game", "Board Game"],
        "MOBA": ["MOBA"],
        "Point-and-click": ["Point & Click"],
        "Fighting": ["Fighting"],
        "Shooter": ["Shooter", "FPS"],
        "Music": ["Music"],
        "Platform": ["Platformer"],
        "Puzzle": ["Puzzle"],
        "Racing": ["Racing"],
        "Real Time Strategy (RTS)": ["RTS", "Real-Time Strategy"],
        "Role-playing (RPG)": ["RPG"],
        "Simulator": ["Simulation"],
        "Sport": ["Sports"],
        "Strategy": ["Strategy"],
        "Turn-based strategy (TBS)": ["Turn-Based Strategy"],
        "Tactical": ["Tactical"],
        "Hack and slash/Beat 'em up": ["Hack and Slash", "Beat 'em up"],
        "Quiz/Trivia": ["Trivia"],
    }

    # Map our theme names to Steam tags
    THEME_TAG_MAPPING = {
        "Action": ["Action"],
        "Fantasy": ["Fantasy"],
        "Science fiction": ["Sci-fi"],
        "Horror": ["Horror"],
        "Thriller": ["Thriller"],
        "Survival": ["Survival"],
        "Historical": ["Historical"],
        "Stealth": ["Stealth"],
        "Comedy": ["Comedy"],
        "Business": ["Management"],
        "Drama": ["Story Rich"],
        "Sandbox": ["Sandbox"],
        "Educational": ["Education"],
        "Kids": ["Family Friendly"],
        "Open world": ["Open World"],
        "Warfare": ["War", "Military"],
        "Party": ["Party Game"],
        "4X (explore, expand, exploit, and exterminate)": ["4X"],
        "Mystery": ["Mystery"],
    }

    # Map our OS filter values to Steam platform requirements
    OS_MAPPING = {
        "windows": "win",
        "mac": "mac",
        "linux": "linux"
    }

    def __init__(self, rate_limit_delay: float = 1.5):
        """
        Initialize Steam API client.

        Args:
            rate_limit_delay: Delay in seconds between API requests to avoid rate limiting
        """
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'QuestLog Game Discovery (Discord Bot)'
        })

    def _rate_limit(self):
        """Ensure we don't exceed rate limits."""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        self.last_request_time = time.time()

    def _make_request(self, url: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make a rate-limited request to Steam API.

        Args:
            url: The URL to request
            params: Optional query parameters

        Returns:
            JSON response data or None on failure
        """
        self._rate_limit()

        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Steam API request failed: {e}")
            return None

    def get_new_releases(self, days_back: int = 7, max_results: int = 50) -> List[Dict]:
        """
        Fetch recently released games from Steam.

        Args:
            days_back: How many days back to look for releases
            max_results: Maximum number of results to return

        Returns:
            List of game data dictionaries
        """
        # Steam doesn't have a simple "new releases" API endpoint
        # We'll use the featured games endpoint and filter by release date
        url = f"{self.BASE_URL}/featured/"

        data = self._make_request(url)
        if not data:
            return []

        games = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Check different sections for new releases
        sections = ['new_releases', 'coming_soon', 'featured_win', 'featured_mac', 'featured_linux']

        for section in sections:
            if section in data and 'items' in data[section]:
                for item in data[section]['items']:
                    app_id = item.get('id')
                    if app_id and app_id not in [g.get('steam_app_id') for g in games]:
                        # Get detailed info for this app
                        game_details = self.get_game_details(app_id)
                        if game_details:
                            games.append(game_details)

                            if len(games) >= max_results:
                                return games

        return games

    def get_game_details(self, app_id: int) -> Optional[Dict]:
        """
        Get detailed information about a specific game.

        Args:
            app_id: Steam application ID

        Returns:
            Normalized game data dictionary or None
        """
        url = f"{self.BASE_URL}/appdetails"
        params = {'appids': app_id}

        data = self._make_request(url, params)
        if not data or str(app_id) not in data:
            return None

        app_data = data[str(app_id)]
        if not app_data.get('success') or 'data' not in app_data:
            return None

        game = app_data['data']

        # Only return actual games (type == 'game')
        if game.get('type') != 'game':
            return None

        # Normalize the data to match our expected format
        return self._normalize_game_data(game)

    def _normalize_game_data(self, game: Dict) -> Dict:
        """
        Convert Steam game data to our normalized format.

        Args:
            game: Raw Steam game data

        Returns:
            Normalized game data dictionary
        """
        # Extract release date
        release_date = None
        if 'release_date' in game and not game['release_date'].get('coming_soon'):
            date_str = game['release_date'].get('date', '')
            try:
                # Steam dates can be in various formats
                for fmt in ['%b %d, %Y', '%B %d, %Y', '%d %b, %Y', '%Y']:
                    try:
                        release_date = datetime.strptime(date_str, fmt)
                        break
                    except ValueError:
                        continue
            except Exception:
                pass

        # Extract platforms
        platforms = []
        if game.get('platforms'):
            if game['platforms'].get('windows'):
                platforms.append('windows')
            if game['platforms'].get('mac'):
                platforms.append('mac')
            if game['platforms'].get('linux'):
                platforms.append('linux')

        # Extract tags/genres
        tags = []
        if 'genres' in game:
            tags.extend([g['description'] for g in game['genres']])
        if 'categories' in game:
            tags.extend([c['description'] for c in game['categories']])

        return {
            'steam_app_id': game.get('steam_appid'),
            'name': game.get('name'),
            'description': game.get('short_description', game.get('detailed_description', '')),
            'release_date': release_date.timestamp() if release_date else None,
            'cover_url': game.get('header_image'),
            'steam_url': f"https://store.steampowered.com/app/{game.get('steam_appid')}",
            'platforms': platforms,
            'tags': tags,
            'price': game.get('price_overview', {}).get('final_formatted', 'Free') if game.get('is_free') is False else 'Free',
            'is_free': game.get('is_free', False),
            'developers': game.get('developers', []),
            'publishers': game.get('publishers', []),
        }

    def filter_games(
        self,
        games: List[Dict],
        genres: Optional[List[str]] = None,
        themes: Optional[List[str]] = None,
        os_filter: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Filter games based on user-selected criteria.

        Args:
            games: List of game dictionaries to filter
            genres: List of genre names to include
            themes: List of theme names to include
            os_filter: List of OS names to include (windows, mac, linux)
            platforms: List of platform names to include

        Returns:
            Filtered list of games
        """
        filtered = []

        # Build sets of required tags from genres and themes
        required_tags = set()
        if genres:
            for genre in genres:
                if genre in self.GENRE_TAG_MAPPING:
                    required_tags.update(self.GENRE_TAG_MAPPING[genre])

        if themes:
            for theme in themes:
                if theme in self.THEME_TAG_MAPPING:
                    required_tags.update(self.THEME_TAG_MAPPING[theme])

        for game in games:
            # Check OS filter
            if os_filter:
                game_platforms = set(game.get('platforms', []))
                required_os = set(os_filter)
                if not game_platforms.intersection(required_os):
                    continue

            # Check tags (genres + themes)
            if required_tags:
                game_tags = set(game.get('tags', []))
                # Game must have at least one matching tag
                if not game_tags.intersection(required_tags):
                    continue

            filtered.append(game)

        return filtered

    def search_new_games(
        self,
        days_back: int = 7,
        max_results: int = 50,
        genres: Optional[List[str]] = None,
        themes: Optional[List[str]] = None,
        os_filter: Optional[List[str]] = None,
        platforms: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Search for new games matching the specified filters.

        Args:
            days_back: How many days back to look for releases
            max_results: Maximum number of results to return
            genres: List of genre names to include
            themes: List of theme names to include
            os_filter: List of OS names to include
            platforms: List of platform names to include

        Returns:
            List of matching games
        """
        # Fetch new releases
        games = self.get_new_releases(days_back=days_back, max_results=max_results * 2)

        # Apply filters
        filtered_games = self.filter_games(
            games=games,
            genres=genres,
            themes=themes,
            os_filter=os_filter,
            platforms=platforms,
        )

        # Limit to max_results
        return filtered_games[:max_results]


# Singleton instance
_steam_api_instance = None


def get_steam_api() -> SteamAPI:
    """Get the singleton Steam API instance."""
    global _steam_api_instance
    if _steam_api_instance is None:
        _steam_api_instance = SteamAPI()
    return _steam_api_instance
