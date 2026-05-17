"""
IGDB (Internet Game Database) API integration
Requires Twitch Client ID and Client Secret
"""
import os
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class IGDBGame:
    """Represents a game from IGDB"""
    def __init__(self, data: dict):
        self.id = data.get('id')
        self.name = data.get('name')
        self.slug = data.get('slug', '')
        self.summary = data.get('summary', '')

        # Cover image
        cover = data.get('cover', {})
        if isinstance(cover, dict):
            image_id = cover.get('image_id')
            self.cover_url = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg" if image_id else None
        else:
            self.cover_url = None

        # Platforms
        platforms = data.get('platforms', [])
        self.platforms = [p.get('name') for p in platforms if isinstance(p, dict) and p.get('name')]

        # Release date
        first_release_date = data.get('first_release_date')
        if first_release_date:
            try:
                release_dt = datetime.fromtimestamp(first_release_date)
                self.release_year = release_dt.year
            except:
                self.release_year = None
        else:
            self.release_year = None

        # Game modes
        game_modes = data.get('game_modes', [])
        self.game_modes = [m.get('name') for m in game_modes if isinstance(m, dict) and m.get('name')]

        # Steam ID from external_games - take the lowest (oldest/base game) app ID
        # to avoid picking free trials or DLC entries that have no cover art
        self.steam_id = None
        external_games = data.get('external_games', [])
        steam_ids = []
        for ext in external_games:
            if not isinstance(ext, dict):
                continue
            url = ext.get('url', '')
            if 'steampowered.com' in url:
                uid = ext.get('uid')
                if uid and str(uid).isdigit():
                    steam_ids.append(int(uid))
        if steam_ids:
            self.steam_id = min(steam_ids)


class IGDBClient:
    """IGDB API client"""
    BASE_URL = "https://api.igdb.com/v4"
    TOKEN_URL = "https://id.twitch.tv/oauth2/token"

    def __init__(self):
        self.client_id = os.getenv('IGDB_CLIENT_ID', '')
        self.client_secret = os.getenv('IGDB_CLIENT_SECRET', '')
        self.access_token = None
        self.token_expires_at = None

    async def get_access_token(self) -> str:
        """Get or refresh Twitch OAuth token for IGDB"""
        # Check if we have a valid token
        if self.access_token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.access_token

        # Request new token
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.TOKEN_URL, params=params) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"Failed to get IGDB token: {resp.status} - {error_text}")

                data = await resp.json()
                self.access_token = data['access_token']
                expires_in = data.get('expires_in', 3600)
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer

                return self.access_token

    async def search_games(self, query: str, limit: int = 10) -> List[IGDBGame]:
        """Search for games on IGDB"""
        if not self.client_id or not self.client_secret:
            logger.error("IGDB credentials not configured")
            return []

        try:
            token = await self.get_access_token()

            query_body = f"""
                search "{query}";
                fields name, slug, summary, cover.image_id, platforms.name, first_release_date, external_games.uid, external_games.url, game_modes.name;
                limit {limit};
                where version_parent = null;
            """.strip()

            headers = {
                'Client-ID': self.client_id,
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.BASE_URL}/games",
                    headers=headers,
                    data=query_body
                ) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"IGDB search failed: {resp.status} - {error_text}")
                        return []

                    data = await resp.json()
                    return [IGDBGame(game) for game in data]

        except Exception as e:
            logger.error(f"IGDB search error: {e}")
            return []


# Global client instance
_client = IGDBClient()


async def search_games(query: str, limit: int = 10) -> List[IGDBGame]:
    """Search for games (async function)"""
    return await _client.search_games(query, limit)


async def get_trending_games(limit: int = 5) -> list:
    """Fetch trending games from IGDB popularity_primitives, returns plain dicts."""
    if not _client.client_id or not _client.client_secret:
        return []
    try:
        token = await _client.get_access_token()
        headers = {
            'Client-ID': _client.client_id,
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        }
        # Step 1: get top game_ids by popularity (type 1 = IGDB visits)
        pop_body = f'fields game_id, value; sort value desc; limit {limit}; where popularity_type = 1;'
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{IGDBClient.BASE_URL}/popularity_primitives',
                headers=headers, data=pop_body
            ) as resp:
                if resp.status != 200:
                    return []
                pop_data = await resp.json()

        game_ids = [str(r['game_id']) for r in pop_data if r.get('game_id')]
        if not game_ids:
            return []

        # Step 2: fetch game details for those IDs
        ids_str = ','.join(game_ids)
        games_body = f'fields name, cover.image_id; where id = ({ids_str}); limit {limit};'
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'{IGDBClient.BASE_URL}/games',
                headers=headers, data=games_body
            ) as resp:
                if resp.status != 200:
                    return []
                games_data = await resp.json()

        results = []
        for g in games_data:
            cover = g.get('cover') or {}
            image_id = cover.get('image_id') if isinstance(cover, dict) else None
            results.append({
                'name': g.get('name', ''),
                'cover_url': f'https://images.igdb.com/igdb/image/upload/t_cover_small/{image_id}.jpg' if image_id else None,
            })
        return results
    except Exception as e:
        logger.error(f'IGDB trending error: {e}')
        return []
