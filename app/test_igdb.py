#!/usr/bin/env python3
"""
Simple IGDB API test script
Tests basic connectivity and query functionality
"""
import asyncio
import os
import sys
import time
from dotenv import load_dotenv

# Add the parent directory to path so we can import from utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils import igdb

# Load environment variables
load_dotenv()

async def test_basic_search():
    """Test 1: Basic search without filters"""
    print("=" * 80)
    print("TEST 1: Basic search - Next 90 days, no filters")
    print("=" * 80)

    games = await igdb.search_upcoming_games(
        days_ahead=90,
        days_behind=0,
        limit=10
    )

    print(f"\nFound {len(games)} games")
    for game in games[:5]:
        release = time.strftime('%Y-%m-%d', time.localtime(game.release_date)) if game.release_date else "Unknown"
        print(f"  - {game.name} ({release}) - Platforms: {', '.join(game.platforms[:3])}")
    print()


async def test_genre_only():
    """Test 2: Genre filter only (RPG)"""
    print("=" * 80)
    print("TEST 2: RPG games only - Next 90 days")
    print("=" * 80)

    games = await igdb.search_upcoming_games(
        days_ahead=90,
        days_behind=0,
        genres=["Role-playing (RPG)"],
        limit=10
    )

    print(f"\nFound {len(games)} games")
    for game in games[:5]:
        release = time.strftime('%Y-%m-%d', time.localtime(game.release_date)) if game.release_date else "Unknown"
        genres = ', '.join(game.genres[:3]) if hasattr(game, 'genres') else "N/A"
        print(f"  - {game.name} ({release})")
        print(f"    Genres: {genres}")
        print(f"    Platforms: {', '.join(game.platforms[:3])}")
    print()


async def test_platform_only():
    """Test 3: Platform filter only (PC)"""
    print("=" * 80)
    print("TEST 3: PC games only - Next 90 days")
    print("=" * 80)

    games = await igdb.search_upcoming_games(
        days_ahead=90,
        days_behind=0,
        platforms=["PC (Microsoft Windows)"],
        limit=10
    )

    print(f"\nFound {len(games)} games")
    for game in games[:5]:
        release = time.strftime('%Y-%m-%d', time.localtime(game.release_date)) if game.release_date else "Unknown"
        print(f"  - {game.name} ({release})")
        print(f"    Platforms: {', '.join(game.platforms[:3])}")
    print()


async def test_genre_and_platform():
    """Test 4: Genre + Platform (RPG + PC)"""
    print("=" * 80)
    print("TEST 4: RPG games on PC - Next 90 days")
    print("=" * 80)

    games = await igdb.search_upcoming_games(
        days_ahead=90,
        days_behind=0,
        genres=["Role-playing (RPG)"],
        platforms=["PC (Microsoft Windows)"],
        limit=10
    )

    print(f"\nFound {len(games)} games")
    for game in games[:5]:
        release = time.strftime('%Y-%m-%d', time.localtime(game.release_date)) if game.release_date else "Unknown"
        genres = ', '.join(game.genres[:3]) if hasattr(game, 'genres') else "N/A"
        print(f"  - {game.name} ({release})")
        print(f"    Genres: {genres}")
        print(f"    Platforms: {', '.join(game.platforms[:3])}")
    print()


async def test_all_filters():
    """Test 5: All filters (RPG + PC + Single player)"""
    print("=" * 80)
    print("TEST 5: RPG + PC + Single player - Next 90 days")
    print("=" * 80)

    games = await igdb.search_upcoming_games(
        days_ahead=90,
        days_behind=0,
        genres=["Role-playing (RPG)"],
        platforms=["PC (Microsoft Windows)"],
        game_modes=["Single player"],
        limit=10
    )

    print(f"\nFound {len(games)} games")
    for game in games[:5]:
        release = time.strftime('%Y-%m-%d', time.localtime(game.release_date)) if game.release_date else "Unknown"
        genres = ', '.join(game.genres[:3]) if hasattr(game, 'genres') else "N/A"
        modes = ', '.join(game.game_modes) if hasattr(game, 'game_modes') else "N/A"
        print(f"  - {game.name} ({release})")
        print(f"    Genres: {genres}")
        print(f"    Modes: {modes}")
        print(f"    Platforms: {', '.join(game.platforms[:3])}")
    print()


async def test_wider_window():
    """Test 6: Wider time window (1 year)"""
    print("=" * 80)
    print("TEST 6: RPG + PC - Next 365 days (1 year)")
    print("=" * 80)

    games = await igdb.search_upcoming_games(
        days_ahead=365,
        days_behind=0,
        genres=["Role-playing (RPG)"],
        platforms=["PC (Microsoft Windows)"],
        limit=20
    )

    print(f"\nFound {len(games)} games")
    for game in games[:10]:
        release = time.strftime('%Y-%m-%d', time.localtime(game.release_date)) if game.release_date else "Unknown"
        genres = ', '.join(game.genres[:3]) if hasattr(game, 'genres') else "N/A"
        print(f"  - {game.name} ({release})")
        print(f"    Genres: {genres}")
    print()


async def main():
    """Run all tests"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 25 + "IGDB API TEST SUITE" + " " * 34 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    # Check credentials
    if not igdb.is_configured():
        print("❌ ERROR: IGDB credentials not configured!")
        print("   Please set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET in .env")
        return

    print("✅ IGDB credentials found")
    print()

    try:
        # Run tests in sequence
        await test_basic_search()
        await test_genre_only()
        await test_platform_only()
        await test_genre_and_platform()
        await test_all_filters()
        await test_wider_window()

        print("=" * 80)
        print("ALL TESTS COMPLETED")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
