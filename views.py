def home(request):
    return render(request, 'index.html')

from django.shortcuts import render
import requests
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.shortcuts import redirect, render
from django.contrib.admin.views.decorators import staff_member_required
from dotenv import load_dotenv
import os
import asyncio
import logging
from ampapi.dataclass import APIParams
from ampapi.bridge import Bridge
from ampapi.controller import AMPControllerInstance
import json
from pathlib import Path

load_dotenv()

# Configure logger for views
logger = logging.getLogger(__name__)

DISCORD_ACTIVITY_FILE = Path("/srv/ch-webserver/gamingactivity/activity_data.json")

def get_discord_activity():
    if DISCORD_ACTIVITY_FILE.exists():
        with open(DISCORD_ACTIVITY_FILE, "r") as f:
            return json.load(f)
    return {}


# Games tracked through AMP
STATIC_GAME_INFO = {
    "CasualHeroes-7DTD01": {
        "display_name": "7 Days to Die",
        "description": "A custom survival world where biomes bite back. Bots spawn threats, buffs twist the rules, nothing is predictable, and that’s the point.",
        "discord_invite": "https://discord.gg/CHHS",
        "steam_link": "https://store.steampowered.com/app/251570/7_Days_to_Die/",
        "steam_appid": "251570",
        "connect_pw": "N/A"
    },
    "CasualHeroes-ASA01": {
        "display_name": "Ark: Survival Ascended",
        "description": "Custom dinos, wild events, and evolving threats. Build smart, hunt fast, or get hunted.",
        "discord_invite": "https://discord.gg/Zs8tFYY7Gf",
        "steam_link": "https://store.steampowered.com/app/2399830/ARK_Survival_Ascended/",
        "steam_appid": "2399830",
        "connect_pw": "Join our Discord to gain access!"
    },
    # "CasualHeroes-Conan01": {
    #     "display_name": "Conan Exiles",
    #     "description": "PvE meets PvP in a fully modded world. Let the chaos rain — builders and devs welcome in the Exiled Lands. LFM Devs!",
    #     "discord_invite": "https://discord.gg/S4XkS58HTq",
    #     "steam_link": "https://store.steampowered.com/app/440900/Conan_Exiles/",
    #     "steam_appid": "440900",
    #     "connect_pw": "No Password"
    # },

    # "CasualHeroes-Ascended01": {
    #     "display_name": "Dragonwilds",
    #     "description": "As soon as dedicated servers drop, we’re self-hosting, building custom content, and launching a one-of-a-kind Dragonwilds adventure.",
    #     "discord_invite": "https://discord.gg/WZzTppBgBz",
    #     "steam_link": "https://store.steampowered.com/app/1374490/RuneScape_Dragonwilds/",
    #     "custom_amp_img": "/static/img/games/Dragonwilds/dw_static.jpg",
    #     # "steam_appid": "1374490",
    #     "connect_pw": "N/A"
    # },

    # "Enshrouded01": {
    #     "display_name": "Enshrouded",
    #     "description": "Soulslike survival with tuned combat, custom altars, and strange terrain. Built for players who like challenge, discovery, and a bit of chaos.",
    #     "discord_invite": "https://discord.gg/CHHS",
    #     "steam_link": "https://store.steampowered.com/app/1203620/Enshrouded/",
    #     "steam_appid": "1203620",
    #     "connect_pw": "Join the Discord"
    # },
    "CasualHeroes-Vrising01": {
        "display_name": "V Rising",
        "description": "Modded gothic survival with PvP and random preset days, castle building, and a world that rewards planning over panic. Vardoran’s waiting, Rise. Bite. Build.",
        "discord_invite": "https://discord.gg/CHHS",
        "steam_link": "https://store.steampowered.com/app/1604030/V_Rising/",
        "steam_appid": "1604030",
        "connect_pw": "No Password"
    }
}
# Games tracked through Discord only
DISCORD_GAMES = [
        {
        "id": "Dune",
        "name": "Dune: Awakening",
        "description": "The premier casual guild in the Dune uninverse. Chill dungeon runs, late-night banter, and a crew that’s always online. Whether you're new or a raiding vet, Casual Heroes has a spot for you.",
        "guild_page": "https://casual-heroes.com/dune/",
        "steam_link": "https://store.steampowered.com/app/1172710/Dune_Awakening/",
        "discord_invite": "https://discord.gg/jAJvykZvej",
        "steam_appid": "1172710",
        "online": "-",
        "max": "-",
        "link_label": "View on Steam"
    },
    # {
    #     "id": "Dragonwilds",
    #     "name": "Dragonwilds",
    #     "description": "As soon as dedicated servers drop, we’re self-hosting, building custom content, and launching a one-of-a-kind Dragonwilds adventure.",
    #     "steam_link": "https://store.steampowered.com/app/1374490/RuneScape_Dragonwilds/",
    #     "discord_invite": "https://discord.gg/WZzTppBgBz",
    #     "steam_appid": "1374490",
    #     "custom_img": "/static/img/games/Dragonwilds/dw_static.jpg",
    #     "online": "-",
    #     "max": "-",
    #     "link_label": "View on Steam"
    # },
    # {
    #     "id": "MHW",
    #     "name": "Monster Hunter Wilds",
    #     "description": "From fashion shows to chaotic wild hunts, our Monster Hunter community is growing fast. Whether you're min-maxing DPS or just showing off your best drip, there's a spot at the campfire for you.",
    #     "steam_link": "https://store.steampowered.com/app/2246340/Monster_Hunter_Wilds/",
    #     "discord_invite": "https://discord.gg/3rKQptH7Fd",
    #     "steam_appid": "2246340",
    #     "online": "-",
    #     "max": "-",
    #     "link_label": "View on Steam"
    # },
    {
        "id": "Pantheon",
        "name": "Pantheon: Rise of the Fallen",
        "description": "The premier casual guild in the Pantheon world. Chill dungeon runs, late-night banter, and a crew that’s always online. Whether you're new or a raiding vet, Casual Heroes has a spot for you.",
        "steam_link": "https://store.steampowered.com/app/3107230/Pantheon_Rise_of_the_Fallen/",
        "discord_invite": "https://discord.gg/REHJrygu64",
        "steam_appid": "3107230",
        "online": "-",
        "max": "-",
        "link_label": "View on Steam"
    },
    # {
    #     "id": "PoE2",
    #     "name": "Path of Exile 2",
    #     "description": "You’ll always find someone theorycrafting their next crazy build here. Casual Heroes are farming, testing, and helping each other every step of the way.",
    #     "steam_link": "https://store.steampowered.com/app/2694490/Path_of_Exile_2/",
    #     "discord_invite": "https://discord.gg/fs9qAkVkxH",
    #     "steam_appid": "2694490",
    #     "online": "-",
    #     "max": "-",
    #     "link_label": "View on Steam"
    # },
    # {
    #     "id": "WoW",
    #     "name": "World of Warcraft",
    #     "description": "Teaming up with longtime friend Eldronox and his legendary community 'Eternal Legends', we're building a World of Warcraft guild called <Casual Legends>. A chill, zero-drama space for adventurers who play at their own pace..",
    #     "steam_link": "https://worldofwarcraft.blizzard.com/en-us/",
    #     "discord_invite": "https://discord.gg/exRgR9YGyy",
    #     "custom_img": "/static/img/games/wow/dwarf.webp",
    #     "online": "-",
    #     "max": "-",
    #     "link_label": "View Site"
    # }
]



async def fetch_instance_data(instance_name):
    _params = APIParams(
        url=os.getenv("AMP_URL"),
        user=os.getenv("AMP_USER"),
        password=os.getenv("AMP_PASSWORD")
    )
    Bridge(api_params=_params)

    controller = AMPControllerInstance()
    try:
        await controller.get_instances()
    except Exception as e:
        logger.error(f"Could not fetch AMP instances: {e}")
        return safe_amp_fallback(instance_name)

    for instance in controller.instances:
        if instance.instance_name == instance_name:
            try:
                status = await instance.get_status(format_data=False)
                ports = await instance.get_port_summaries(format_data=False)

                valid_ports = [
                    p for p in ports
                    if not p.get("internalonly", False)
                    and p.get("port") is not None
                ]

                preferred_order = ["Game Port", "Game and Mods Port", "Query Port"]
                game_port = next(
                    (p for name in preferred_order for p in valid_ports if name.lower() in p.get("name", "").lower()),
                    None
                )

                if not game_port and valid_ports:
                    game_port = valid_ports[0]

                ip = (
                game_port.get("ip")
                or game_port.get("hostname")
                or requests.get("https://ifconfig.me").text.strip()
                or "Unknown"
            )
                port = str(game_port.get("port")) if game_port else "Unknown"

                static_info = STATIC_GAME_INFO.get(instance_name, {})

                # ✅ Check if AMP reports the server as Running
                is_running = status.get("running", True)


                return {
                    "id": instance_name,
                    "name": static_info.get("display_name", instance_name),
                    "title": static_info.get("display_name", instance_name),
                    "description": static_info.get("description", ""),
                    "discord_invite": static_info.get("discord_invite", "#"),
                    "guild_page": static_info.get("guild_page", ""),
                    "steam_link": static_info.get("steam_link", "#"),
                    "steam_appid": static_info.get("steam_appid"),
                    "custom_img": static_info.get("custom_img"),
                    "custom_amp_img": static_info.get("custom_amp_img"),
                    "online": status["metrics"]["active_users"]["raw_value"],
                    "max": status["metrics"]["active_users"]["max_value"],
                    "ip": f"{ip}:{port}",
                    "pw": static_info.get("connect_pw", "Unknown"),
                    "source": "amp",
                    "status_label": "🟢 Online" if is_running else "🔴 Offline"
                }

            except Exception as e:
                logger.warning(f"AMP instance {instance_name} error: {e}")
                return safe_amp_fallback(instance_name)

    logger.info(f"AMP instance {instance_name} not found — using fallback.")
    return safe_amp_fallback(instance_name)


    # fallback
def safe_amp_fallback(instance_name):
    static_info = STATIC_GAME_INFO.get(instance_name, {})
    return {
        "id": instance_name,
        "name": static_info.get("display_name", instance_name),
        "title": static_info.get("display_name", instance_name),
        "description": static_info.get("description", ""),
        "discord_invite": static_info.get("discord_invite", "#"),
        "guild_page": static_info.get("guild_page", ""),
        "steam_link": static_info.get("steam_link", "#"),
        "steam_appid": static_info.get("steam_appid"),
        "custom_img": static_info.get("custom_img"),
        "custom_amp_img": static_info.get("custom_amp_img"),
        "online": "-",
        "max": "-",
        "ip": "Unavailable",
        "pw": static_info.get("connect_pw", "Unknown"),
        "source": "amp",
        "status_label": "🔴 Offline" 
    }


# Merge and render
def games_we_play(request):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    instance_names = list(STATIC_GAME_INFO.keys())
    amp_games = loop.run_until_complete(asyncio.gather(
        *(fetch_instance_data(name) for name in instance_names)
    ))

    # Inject steam_appid and custom_img into AMP games
    for game in amp_games:
        game["title"] = game.get("name")
        instance_info = STATIC_GAME_INFO.get(game["id"])
        if instance_info:
            game["steam_appid"] = instance_info.get("steam_appid")
            game["custom_img"] = instance_info.get("custom_img")  # Optional for WoW or non-Steam

    # Combine AMP + Discord games into one list
    # Load Discord activity
    discord_activity = get_discord_activity()

    # Inject activity into Discord-only games
    activity_counts = get_discord_activity_counts()
    for game in DISCORD_GAMES:
        game["title"] = game.get("name")
        stats = discord_activity.get(game["id"])
        if stats:
            game["online"] = stats.get("active", "-")
            game["max"] = stats.get("total", "-")
            game["live_now"] = stats.get("active", 0) > 0

        # Inject steam_appid and fallback images
        static_info = STATIC_GAME_INFO.get(game["id"])
        if static_info:
            game["steam_appid"] = static_info.get("steam_appid")
            game["custom_img"] = static_info.get("custom_img")

        # Ensure name and source
        game["name"] = game.get("name", game["id"])
        game["source"] = "discord"

    all_games = amp_games + DISCORD_GAMES

    return render(request, 'gamesweplay.html', { 'games': all_games })

# Leave this here
def home(request):
    return render(request, 'index.html')


def dune_page(request):
    dune_data = {
        "total": "-",
        "online": "-",
        "active": "-"
    }

    if DISCORD_ACTIVITY_FILE.exists():
        try:
            with DISCORD_ACTIVITY_FILE.open("r") as f:
                all_activity = json.load(f)
                raw = all_activity.get("Dune", {})
                logger.debug(f"Raw Dune Activity: {raw}")

                # Safely cast integers
                dune_data["total"] = int(raw["total"]) if str(raw.get("total", "")).isdigit() else "-"
                dune_data["online"] = int(raw["online"]) if str(raw.get("online", "")).isdigit() else "-"
                dune_data["active"] = int(raw["active"]) if str(raw.get("active", "")).isdigit() else "-"
        except Exception as e:
            logger.error(f"Dune page failed to load activity data: {e}")

    logger.debug(f"Final dune_data: {dune_data}")
    return render(request, "dune.html", {
        "dune_activity": dune_data
    })


def pantheon_page(request):
    pantheon_data = {
        "total": "-",
        "online": "-",
        "active": "-"
    }

    if DISCORD_ACTIVITY_FILE.exists():
        try:
            with DISCORD_ACTIVITY_FILE.open("r") as f:
                all_activity = json.load(f)
                raw = all_activity.get("Pantheon", {})
                logger.debug(f"Raw Pantheon Activity: {raw}")

                # Safely cast integers
                pantheon_data["total"] = int(raw["total"]) if str(raw.get("total", "")).isdigit() else "-"
                pantheon_data["online"] = int(raw["online"]) if str(raw.get("online", "")).isdigit() else "-"
                pantheon_data["active"] = int(raw["active"]) if str(raw.get("active", "")).isdigit() else "-"
        except Exception as e:
            logger.error(f"Pantheon page failed to load activity data: {e}")

    logger.debug(f"Final pantheon_data: {pantheon_data}")
    return render(request, "pantheon.html", {
        "pantheon_activity": pantheon_data
    })

# def wow_page(request):
#     wow_data = {
#         "total": "-",
#         "online": "-",
#         "active": "-"
#     }

#     if DISCORD_ACTIVITY_FILE.exists():
#         try:
#             with DISCORD_ACTIVITY_FILE.open("r") as f:
#                 all_activity = json.load(f)
#                 raw = all_activity.get("WoW", {})
#                 print("[DEBUG] Raw WoW Activity:", raw)

#                 # Safely cast integers
#                 wow_data["total"] = int(raw["total"]) if str(raw.get("total", "")).isdigit() else "-"
#                 wow_data["online"] = int(raw["online"]) if str(raw.get("online", "")).isdigit() else "-"
#                 wow_data["active"] = int(raw["active"]) if str(raw.get("active", "")).isdigit() else "-"
#         except Exception as e:
#             print(f"[WoW PAGE] Failed to load activity data: {e}")

#     print("[DEBUG] Final wow_data:", wow_data)
#     return render(request, "wow.html", {
#         "wow_activity": wow_data
#     })




def get_discord_activity_counts():
    if not DISCORD_ACTIVITY_FILE.exists():
        return {}

    with DISCORD_ACTIVITY_FILE.open("r") as f:
        return json.load(f)

articles = [
    {
        "slug": "survival-games-2025",
        "title": "Top Survival Games in 2025",
        "author": "FullData",
        "games": [
            {
                "title": "Dune: Awakening",
                "summary": """Set on the unforgiving planet of Arrakis, Dune: Awakening blends survival mechanics with MMO elements. 
                Players must navigate sandstorms, harvest spice, and avoid colossal sandworms. The game emphasizes base-building, resource management, and PvP combat.
                While the world-building and atmosphere have been praised, some players have noted that combat mechanics feel clunky and could use refinement.
                The game's success will likely hinge on how well it balances its ambitious features.""",
                "image": "img/games/survivalgames/Dune1.jpg"
            },
            {
                "title": "Subnautica 2",
                "summary": """Diving back into the depths, Subnautica 2 offers a new alien ocean world to explore. 
                The sequel introduces co-op gameplay, allowing up to four players to explore together. Players can expect new biomes, creatures, and crafting options. 
                Early impressions highlight the game's immersive environment and improved mechanics. 
                However, some fans express concerns about the game's shorter story length, aiming for around 15 hours, and the introduction of microtransactions.""",
                "image": "img/games/survivalgames/sub2.jpg"
            },
            {
                "title": "The Alters",
                "summary": """The Alters presents a unique survival experience where players create alternate versions of themselves to survive on a hostile planet. 
                Each "alter" possesses different skills, aiding in tasks like base-building and exploration. 
                The game's narrative-driven approach has been lauded for its depth and originality. 
                However, some players feel that the gameplay leans heavily on dialogue and could benefit from more interactive elements.""",
                "image": "img/games/survivalgames/Alters.jpg"
            },
            {
                "title": "RuneScape: Dragonwilds",
                "summary": """A spin-off from the classic MMO, RuneScape: Dragonwilds ventures into survival territory. 
                Set in the continent of Ashenfall, players engage in base-building, crafting, and combat against dragons. 
                The game has seen a strong start, with over 600,000 copies sold and positive reviews highlighting its engaging mechanics. 
                Nonetheless, some players feel that the game lacks depth in its current state and hope for more content in future updates.""",
                "image": "img/games/survivalgames/dragonwilds_static.jpg"
            },
            {
                "title": "V Rising: Invaders of Oakveil",
                "summary": """V Rising: Invaders of Oakveil is out now and it’s a massive step forward for the game. 
                It builds smartly on what V Rising already did well — from world design to progression — and adds meaningful features like the cursed forest biome, PvP duel arenas, and deeper character customization.
                What really stands out in this update is how it pushes both PvE and PvP players forward. The cursed forest introduces new tactical layers with poison-based enemies and new gear, while the duel arenas finally give PvP-focused players a structured way to test their builds.
                If you were already a fan of V Rising, this update makes the game feel more complete. And if you're new? There’s never been a better time to jump in.""",
                "image": "img/games/survivalgames/V-Rising-Invaders-of-Oakveil.jpg"
            },
            {
                "title": "The Forever Winter",
                "summary": """Set in a post-apocalyptic world, The Forever Winter combines survival horror with extraction shooter mechanics. 
                Players scavenge resources while avoiding massive war machines. The game's unique art style, inspired by anime and dystopian themes, has garnered attention. 
                While the dynamic encounter system keeps gameplay fresh, some players have criticized certain mechanics, like the water system, though recent updates have addressed these concerns.""",
                "image": "img/games/survivalgames/TheForeverWinter_SteamImage.jpg"
            },
            {
                "title": "Oppidum",
                "summary": """Aimed at a broader audience, Oppidum offers a more accessible survival experience. 
                With its colorful visuals and simplified mechanics, it's reminiscent of titles like The Legend of Zelda. Players can engage in crafting, farming, and exploration. 
                While the game has been praised for its charm and cooperative gameplay, some have pointed out issues like limited inventory space and a cumbersome travel system.""",
                "image": "img/games/survivalgames/Oppidum.png"
            },
            {
                "title": "Autonomica",
                "summary": """Autonomica stands out with its solarpunk aesthetic and ambitious blend of farming, automation, and time-travel elements. 
                Players can build automated farms, engage in mech battles, and even pursue romantic relationships with NPCs. 
                The game's Kickstarter success indicates strong interest, but some are cautious about how all these features will integrate seamlessly.""",
                "image": "img/games/survivalgames/autonomica.jpg"
            },
            {
                "title": "Terminator: Survivors",
                "summary": """Set between Judgment Day and the rise of John Connor's resistance, Terminator: Survivors is an open-world survival game where players scavenge resources while evading Skynet's machines. 
                The game emphasizes co-op gameplay and base-building. 
                While the premise is intriguing, some players are concerned about the game's delayed release and hope that it delivers a polished experience upon launch.""",
                "image": "img/games/survivalgames/Terminiator.webp"
            },
            {
                "title": "Outward 2",
                "summary": """Building upon its predecessor, Outward 2 offers a challenging action RPG experience with survival elements. 
                Players can expect improved combat mechanics, a richer world, and the ability to drop backpacks to manage weight. 
                While early impressions are positive, some have noted issues like unpredictable enemy movements and occasional bugs. 
                The developers' shift from Unity to Unreal Engine 5 suggests a commitment to enhancing the game's quality.""",
                "image": "img/games/survivalgames/outward2.jpg"
            }
        ]
    }
]

def features(request):
    articles = [
        {
            "slug": "survival-games-2025",
            "title": "Top Survival Games in 2025",
            "summary": "What's next after V Rising and Enshrouded?",
            "image_url": "img/games/survivalgames/survival2025.png"
        },
    ]
    return render(request, "features/features.html", {"articles": articles})


def features_detail(request, slug):
    article = next((a for a in articles if a["slug"] == slug), None)
    if not article:
        return render(request, "404.html", status=404)
    return render(request, "features/article_details.html", {"article": article})


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid username or password.")
    return render(request, "auth/login.html")

from django.contrib.auth.decorators import login_required

@login_required
def dashboard(request):
    return render(request, "dashboard.html")

def hosting(request):
    return render(request, 'hosting.html')

def sevendtd(request):
    sevendtd_instance = asyncio.run(fetch_instance_data("CasualHeroes-7DTD01"))

    return render(request, '7dtd.html', {
        "sevendtd_instance": sevendtd_instance
    })


def dragonwilds(request):
    return render(request, 'dragonwilds.html')

def gameshype(request):
    return render(request, 'gameshype.html')

def gamesuggest(request):
    return render(request, 'gamesuggest.html')

def enshrouded(request):
    enshrouded_instance = asyncio.run(fetch_instance_data("Enshrouded01"))

    return render(request, 'enshrouded.html', {
        "enshrouded_instance": enshrouded_instance
    })

def vrising(request):
    vrising_instance = asyncio.run(fetch_instance_data("CasualHeroes-Vrising01"))

    return render(request, 'vrising.html', {
        "vrising_instance": vrising_instance
    })

def conan(request):
    conan_instance = asyncio.run(fetch_instance_data("CasualHeroes-Conan01"))

    return render(request, 'conan.html', {
        "conan_instance": conan_instance
    })
def guides(request):
    return render(request, 'guides.html')

def content(request):
    return render(request, 'content.html')

def aboutus(request):
    return render(request, 'aboutus.html')

def privacy(request):
    return render(request, 'privacy.html')

def terms(request):
    return render(request, 'terms.html')

def contactus(request):
    return render(request, 'contactus.html')

def faq(request):
    return render(request, 'faq.html')

@staff_member_required
def analytics_view(request):
    return render(request, 'admin/analytics.html')


# =============================================================================
# Discord OAuth2 Authentication
# =============================================================================

from .discord_auth import (
    get_discord_login_url,
    exchange_code_for_token,
    get_discord_user,
    get_discord_guilds,
    get_discord_avatar_url,
    revoke_token,
)
import secrets
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User


def discord_login(request):
    """Initiate Discord OAuth2 login flow"""
    # Generate a state token for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session['discord_oauth_state'] = state

    # Store the 'next' URL if provided
    next_url = request.GET.get('next', '/dashboard/')
    request.session['discord_login_next'] = next_url

    login_url = get_discord_login_url(state=state)
    return redirect(login_url)


def discord_callback(request):
    """Handle Discord OAuth2 callback"""
    error = request.GET.get('error')
    if error:
        messages.error(request, f"Discord login failed: {error}")
        return redirect('home')

    code = request.GET.get('code')
    state = request.GET.get('state')

    # Verify state token
    stored_state = request.session.get('discord_oauth_state')
    if not state or state != stored_state:
        messages.error(request, "Invalid state token. Please try again.")
        return redirect('home')

    # Clear the state from session
    del request.session['discord_oauth_state']

    try:
        # Exchange code for token
        token_data = exchange_code_for_token(code)
        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token')

        # Get Discord user info
        discord_user = get_discord_user(access_token)

        # Get user's guilds
        discord_guilds = get_discord_guilds(access_token)

        # Store Discord info in session
        request.session['discord_user'] = {
            'id': discord_user['id'],
            'username': discord_user['username'],
            'global_name': discord_user.get('global_name') or discord_user['username'],
            'email': discord_user.get('email'),
            'avatar': discord_user.get('avatar'),
            'avatar_url': get_discord_avatar_url(discord_user['id'], discord_user.get('avatar')),
            'discriminator': discord_user.get('discriminator', '0'),
            'access_token': access_token,
            'refresh_token': refresh_token,
        }

        # Store guilds where user has admin permissions (permission 0x8 = Administrator)
        admin_guilds = [
            {
                'id': g['id'],
                'name': g['name'],
                'icon': g.get('icon'),
                'owner': g.get('owner', False),
                'permissions': g.get('permissions', 0),
            }
            for g in discord_guilds
            if g.get('owner') or (int(g.get('permissions', 0)) & 0x8)
        ]
        request.session['discord_admin_guilds'] = admin_guilds
        request.session['discord_all_guilds'] = [
            {'id': g['id'], 'name': g['name'], 'icon': g.get('icon')}
            for g in discord_guilds
        ]

        # Optionally link to Django user (create if doesn't exist)
        try:
            user, created = User.objects.get_or_create(
                username=f"discord_{discord_user['id']}",
                defaults={
                    'email': discord_user.get('email', ''),
                    'first_name': discord_user.get('global_name', discord_user['username'])[:30],
                }
            )
            if not created and discord_user.get('email'):
                user.email = discord_user['email']
                user.save()

            # Log in the Django user
            from django.contrib.auth import login as auth_login
            auth_login(request, user)
        except Exception as e:
            # Even if Django user creation fails, session-based auth works
            logger.warning(f"Could not create Django user: {e}")

        messages.success(request, f"Welcome, {discord_user.get('global_name', discord_user['username'])}!")

        # Redirect to stored 'next' URL or dashboard
        next_url = request.session.pop('discord_login_next', '/dashboard/')
        return redirect(next_url)

    except Exception as e:
        logger.error(f"Discord OAuth callback failed: {e}")
        messages.error(request, "Failed to authenticate with Discord. Please try again.")
        return redirect('home')


def discord_logout(request):
    """Log out user and revoke Discord token"""
    discord_user = request.session.get('discord_user')

    if discord_user and discord_user.get('access_token'):
        # Attempt to revoke the Discord token
        revoke_token(discord_user['access_token'])

    # Clear Discord session data
    for key in ['discord_user', 'discord_admin_guilds', 'discord_all_guilds']:
        if key in request.session:
            del request.session[key]

    # Log out Django user if logged in
    auth_logout(request)

    messages.info(request, "You have been logged out.")
    return redirect('home')


def discord_required(view_func):
    """Decorator to require Discord authentication"""
    def wrapper(request, *args, **kwargs):
        if not request.session.get('discord_user'):
            messages.warning(request, "Please log in with Discord to access this page.")
            return redirect(f"/auth/discord/login/?next={request.path}")
        return view_func(request, *args, **kwargs)
    return wrapper


@discord_required
def user_profile(request):
    """User profile page showing Discord account info and connected guilds"""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])
    all_guilds = request.session.get('discord_all_guilds', [])

    context = {
        'discord_user': discord_user,
        'admin_guilds': admin_guilds,
        'all_guilds': all_guilds,
        'guild_count': len(all_guilds),
        'admin_guild_count': len(admin_guilds),
    }
    return render(request, 'auth/profile.html', context)


@discord_required
def warden_dashboard(request):
    """Main Warden bot dashboard - select a guild to manage"""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    context = {
        'discord_user': discord_user,
        'admin_guilds': admin_guilds,
    }
    return render(request, 'warden/dashboard.html', context)


@discord_required
def guild_dashboard(request, guild_id):
    """Dashboard for a specific guild"""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    # Verify user has admin access to this guild
    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
    }
    return render(request, 'warden/guild_dashboard.html', context)


# =============================================================================
# Tracker Management Dashboard Page
# =============================================================================

@discord_required
def guild_trackers(request, guild_id):
    """Manage channel stat trackers for a guild."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    # Fetch existing trackers from database
    trackers = []
    try:
        from .db import get_db_session
        from .models import ChannelStatTracker

        with get_db_session() as db:
            db_trackers = db.query(ChannelStatTracker).filter_by(
                guild_id=int(guild_id)
            ).all()

            trackers = [
                {
                    'id': t.id,
                    'channel_id': str(t.channel_id),
                    'role_id': str(t.role_id),
                    'label': t.label,
                    'emoji': t.emoji,
                    'game_name': t.game_name,
                    'show_playing_count': t.show_playing_count,
                    'enabled': t.enabled,
                    'last_topic': t.last_topic,
                }
                for t in db_trackers
            ]
    except Exception as e:
        logger.warning(f"Could not fetch trackers: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'trackers': trackers,
    }
    return render(request, 'warden/trackers.html', context)


# =============================================================================
# Tracker API Endpoints (REST API for AJAX calls)
# =============================================================================

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json as json_lib


def api_auth_required(view_func):
    """Check Discord auth and guild admin access for API endpoints."""
    def wrapper(request, guild_id, *args, **kwargs):
        discord_user = request.session.get('discord_user')
        if not discord_user:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        admin_guilds = request.session.get('discord_admin_guilds', [])
        guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
        if not guild:
            return JsonResponse({'error': 'No admin access to this guild'}, status=403)

        return view_func(request, guild_id, *args, **kwargs)
    return wrapper


@api_auth_required
def api_trackers_list(request, guild_id):
    """GET /api/guild/<id>/trackers/ - List all trackers for a guild."""
    try:
        from .db import get_db_session
        from .models import ChannelStatTracker

        with get_db_session() as db:
            trackers = db.query(ChannelStatTracker).filter_by(
                guild_id=int(guild_id)
            ).all()

            return JsonResponse({
                'success': True,
                'trackers': [
                    {
                        'id': t.id,
                        'channel_id': str(t.channel_id),
                        'role_id': str(t.role_id),
                        'label': t.label,
                        'emoji': t.emoji,
                        'game_name': t.game_name,
                        'show_playing_count': t.show_playing_count,
                        'enabled': t.enabled,
                        'last_topic': t.last_topic,
                        'last_updated': t.last_updated,
                    }
                    for t in trackers
                ]
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_tracker_create(request, guild_id):
    """POST /api/guild/<id>/trackers/ - Create a new tracker."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    required = ['channel_id', 'role_id', 'label']
    for field in required:
        if field not in data:
            return JsonResponse({'error': f'Missing required field: {field}'}, status=400)

    try:
        from .db import get_db_session
        from .models import ChannelStatTracker

        discord_user = request.session.get('discord_user', {})

        with get_db_session() as db:
            # Check if tracker already exists for this channel
            existing = db.query(ChannelStatTracker).filter_by(
                guild_id=int(guild_id),
                channel_id=int(data['channel_id'])
            ).first()

            if existing:
                return JsonResponse({
                    'error': 'A tracker already exists for this channel'
                }, status=400)

            # Create new tracker
            tracker = ChannelStatTracker(
                guild_id=int(guild_id),
                channel_id=int(data['channel_id']),
                role_id=int(data['role_id']),
                label=data['label'],
                emoji=data.get('emoji'),
                game_name=data.get('game_name'),
                show_playing_count=bool(data.get('game_name')),
                enabled=True,
                created_by=int(discord_user.get('id', 0))
            )

            db.add(tracker)
            db.flush()  # Get the ID

            return JsonResponse({
                'success': True,
                'tracker': {
                    'id': tracker.id,
                    'channel_id': str(tracker.channel_id),
                    'role_id': str(tracker.role_id),
                    'label': tracker.label,
                    'emoji': tracker.emoji,
                    'game_name': tracker.game_name,
                    'show_playing_count': tracker.show_playing_count,
                    'enabled': tracker.enabled,
                }
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["PATCH", "PUT"])
@api_auth_required
def api_tracker_update(request, guild_id, tracker_id):
    """PATCH /api/guild/<id>/trackers/<tracker_id>/ - Update a tracker."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import ChannelStatTracker

        with get_db_session() as db:
            tracker = db.query(ChannelStatTracker).filter_by(
                id=int(tracker_id),
                guild_id=int(guild_id)
            ).first()

            if not tracker:
                return JsonResponse({'error': 'Tracker not found'}, status=404)

            # Update allowed fields
            if 'label' in data:
                tracker.label = data['label']
            if 'emoji' in data:
                tracker.emoji = data['emoji'] or None
            if 'role_id' in data:
                tracker.role_id = int(data['role_id'])
            if 'game_name' in data:
                tracker.game_name = data['game_name'] or None
                tracker.show_playing_count = bool(data['game_name'])
            if 'enabled' in data:
                tracker.enabled = bool(data['enabled'])

            # Reset last_topic to force update on next bot cycle
            tracker.last_topic = None

            return JsonResponse({
                'success': True,
                'tracker': {
                    'id': tracker.id,
                    'channel_id': str(tracker.channel_id),
                    'role_id': str(tracker.role_id),
                    'label': tracker.label,
                    'emoji': tracker.emoji,
                    'game_name': tracker.game_name,
                    'show_playing_count': tracker.show_playing_count,
                    'enabled': tracker.enabled,
                }
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
@api_auth_required
def api_tracker_delete(request, guild_id, tracker_id):
    """DELETE /api/guild/<id>/trackers/<tracker_id>/ - Delete a tracker."""
    try:
        from .db import get_db_session
        from .models import ChannelStatTracker

        with get_db_session() as db:
            tracker = db.query(ChannelStatTracker).filter_by(
                id=int(tracker_id),
                guild_id=int(guild_id)
            ).first()

            if not tracker:
                return JsonResponse({'error': 'Tracker not found'}, status=404)

            db.delete(tracker)

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# XP & Leveling Dashboard
# =============================================================================

@discord_required
def guild_xp(request, guild_id):
    """XP and leveling management page for a guild."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    # Fetch XP config and leaderboard from database
    xp_config = None
    leaderboard = []
    level_roles = []
    total_members = 0

    try:
        from .db import get_db_session
        from .models import XPConfig, GuildMember, LevelRole, Guild as GuildModel

        with get_db_session() as db:
            # Get or create XP config
            config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()
            if config:
                xp_config = {
                    'message_xp': config.message_xp,
                    'media_multiplier': config.media_multiplier,
                    'reaction_xp': config.reaction_xp,
                    'voice_xp': config.voice_xp_per_interval,
                    'command_xp': config.command_xp,
                    'gaming_xp': config.gaming_xp_per_interval,
                    'invite_xp': config.invite_xp,
                    'message_cooldown': config.message_cooldown,
                    'voice_interval': config.voice_interval,
                    'max_level': config.max_level,
                    'tokens_active': config.tokens_per_100_xp_active,
                    'tokens_passive': config.tokens_per_100_xp_passive,
                }

            # Get top 50 leaderboard
            members = db.query(GuildMember).filter_by(
                guild_id=int(guild_id)
            ).order_by(GuildMember.xp.desc()).limit(50).all()

            leaderboard = [
                {
                    'user_id': str(m.user_id),
                    'display_name': m.display_name or f'User {m.user_id}',
                    'username': m.username,
                    'xp': round(m.xp, 1),
                    'level': m.level,
                    'hero_tokens': m.hero_tokens,
                    'message_count': m.message_count,
                    'voice_minutes': m.voice_minutes,
                }
                for m in members
            ]

            total_members = db.query(GuildMember).filter_by(
                guild_id=int(guild_id)
            ).count()

            # Get level roles
            roles = db.query(LevelRole).filter_by(
                guild_id=int(guild_id)
            ).order_by(LevelRole.level).all()

            level_roles = [
                {
                    'id': r.id,
                    'level': r.level,
                    'role_id': str(r.role_id),
                    'role_name': r.role_name,
                    'remove_previous': r.remove_previous,
                }
                for r in roles
            ]

    except Exception as e:
        logger.warning(f"Could not fetch XP data: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'xp_config': xp_config or {},
        'leaderboard': leaderboard,
        'level_roles': level_roles,
        'total_members': total_members,
    }
    return render(request, 'warden/xp.html', context)


# =============================================================================
# XP API Endpoints
# =============================================================================

@api_auth_required
def api_xp_config(request, guild_id):
    """GET /api/guild/<id>/xp/config/ - Get XP configuration."""
    try:
        from .db import get_db_session
        from .models import XPConfig

        with get_db_session() as db:
            config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()

            if not config:
                # Return defaults
                return JsonResponse({
                    'success': True,
                    'config': {
                        'message_xp': 1.5,
                        'media_multiplier': 1.3,
                        'reaction_xp': 1.0,
                        'voice_xp': 1.3,
                        'command_xp': 1.0,
                        'gaming_xp': 1.2,
                        'invite_xp': 50.0,
                        'message_cooldown': 60,
                        'voice_interval': 5400,
                        'max_level': 99,
                        'tokens_active': 15,
                        'tokens_passive': 5,
                    }
                })

            return JsonResponse({
                'success': True,
                'config': {
                    'message_xp': config.message_xp,
                    'media_multiplier': config.media_multiplier,
                    'reaction_xp': config.reaction_xp,
                    'voice_xp': config.voice_xp_per_interval,
                    'command_xp': config.command_xp,
                    'gaming_xp': config.gaming_xp_per_interval,
                    'invite_xp': config.invite_xp,
                    'message_cooldown': config.message_cooldown,
                    'voice_interval': config.voice_interval,
                    'max_level': config.max_level,
                    'tokens_active': config.tokens_per_100_xp_active,
                    'tokens_passive': config.tokens_per_100_xp_passive,
                }
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST", "PATCH"])
@api_auth_required
def api_xp_config_update(request, guild_id):
    """POST /api/guild/<id>/xp/config/ - Update XP configuration."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import XPConfig, Guild as GuildModel

        with get_db_session() as db:
            # Ensure guild exists
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                guild_record = GuildModel(guild_id=int(guild_id))
                db.add(guild_record)
                db.flush()

            config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                config = XPConfig(guild_id=int(guild_id))
                db.add(config)

            # Update fields
            if 'message_xp' in data:
                config.message_xp = float(data['message_xp'])
            if 'media_multiplier' in data:
                config.media_multiplier = float(data['media_multiplier'])
            if 'reaction_xp' in data:
                config.reaction_xp = float(data['reaction_xp'])
            if 'voice_xp' in data:
                config.voice_xp_per_interval = float(data['voice_xp'])
            if 'command_xp' in data:
                config.command_xp = float(data['command_xp'])
            if 'gaming_xp' in data:
                config.gaming_xp_per_interval = float(data['gaming_xp'])
            if 'invite_xp' in data:
                config.invite_xp = float(data['invite_xp'])
            if 'message_cooldown' in data:
                config.message_cooldown = int(data['message_cooldown'])
            if 'voice_interval' in data:
                config.voice_interval = int(data['voice_interval'])
            if 'max_level' in data:
                config.max_level = int(data['max_level'])
            if 'tokens_active' in data:
                config.tokens_per_100_xp_active = int(data['tokens_active'])
            if 'tokens_passive' in data:
                config.tokens_per_100_xp_passive = int(data['tokens_passive'])

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_auth_required
def api_xp_leaderboard(request, guild_id):
    """GET /api/guild/<id>/xp/leaderboard/ - Get XP leaderboard."""
    try:
        from .db import get_db_session
        from .models import GuildMember

        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 50))
        offset = (page - 1) * per_page

        with get_db_session() as db:
            members = db.query(GuildMember).filter_by(
                guild_id=int(guild_id)
            ).order_by(GuildMember.xp.desc()).offset(offset).limit(per_page).all()

            total = db.query(GuildMember).filter_by(guild_id=int(guild_id)).count()

            return JsonResponse({
                'success': True,
                'leaderboard': [
                    {
                        'user_id': str(m.user_id),
                        'display_name': m.display_name or f'User {m.user_id}',
                        'username': m.username,
                        'xp': round(m.xp, 1),
                        'level': m.level,
                        'hero_tokens': m.hero_tokens,
                        'message_count': m.message_count,
                        'voice_minutes': m.voice_minutes,
                    }
                    for m in members
                ],
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page,
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_xp_member_update(request, guild_id, user_id):
    """POST /api/guild/<id>/xp/member/<user_id>/ - Update a member's XP/tokens."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .actions import queue_xp_add, queue_xp_set, queue_tokens_add

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        action_type = data.get('action', 'set')  # 'add', 'remove', 'set'
        amount = float(data.get('amount', 0))
        field = data.get('field', 'xp')  # 'xp' or 'tokens'

        if field == 'xp':
            if action_type == 'add':
                action_id = queue_xp_add(
                    guild_id=int(guild_id),
                    user_id=int(user_id),
                    amount=amount,
                    triggered_by=triggered_by,
                    triggered_by_name=triggered_by_name
                )
            else:
                action_id = queue_xp_set(
                    guild_id=int(guild_id),
                    user_id=int(user_id),
                    amount=amount,
                    triggered_by=triggered_by,
                    triggered_by_name=triggered_by_name
                )
        elif field == 'tokens':
            action_id = queue_tokens_add(
                guild_id=int(guild_id),
                user_id=int(user_id),
                amount=int(amount),
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name
            )
        else:
            return JsonResponse({'error': 'Invalid field'}, status=400)

        return JsonResponse({
            'success': True,
            'action_id': action_id,
            'message': f'Action queued (ID: {action_id})'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_auth_required
def api_xp_level_roles(request, guild_id):
    """GET /api/guild/<id>/xp/roles/ - Get level roles."""
    try:
        from .db import get_db_session
        from .models import LevelRole

        with get_db_session() as db:
            roles = db.query(LevelRole).filter_by(
                guild_id=int(guild_id)
            ).order_by(LevelRole.level).all()

            return JsonResponse({
                'success': True,
                'level_roles': [
                    {
                        'id': r.id,
                        'level': r.level,
                        'role_id': str(r.role_id),
                        'role_name': r.role_name,
                        'remove_previous': r.remove_previous,
                    }
                    for r in roles
                ]
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_xp_level_role_create(request, guild_id):
    """POST /api/guild/<id>/xp/roles/ - Create a level role."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    required = ['level', 'role_id']
    for field in required:
        if field not in data:
            return JsonResponse({'error': f'Missing required field: {field}'}, status=400)

    try:
        from .db import get_db_session
        from .models import LevelRole

        with get_db_session() as db:
            # Check if level already has a role
            existing = db.query(LevelRole).filter_by(
                guild_id=int(guild_id),
                level=int(data['level'])
            ).first()

            if existing:
                return JsonResponse({'error': 'A role already exists for this level'}, status=400)

            role = LevelRole(
                guild_id=int(guild_id),
                level=int(data['level']),
                role_id=int(data['role_id']),
                role_name=data.get('role_name'),
                remove_previous=data.get('remove_previous', True)
            )
            db.add(role)
            db.flush()

            return JsonResponse({
                'success': True,
                'level_role': {
                    'id': role.id,
                    'level': role.level,
                    'role_id': str(role.role_id),
                    'role_name': role.role_name,
                    'remove_previous': role.remove_previous,
                }
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
@api_auth_required
def api_xp_level_role_delete(request, guild_id, role_id):
    """DELETE /api/guild/<id>/xp/roles/<role_id>/ - Delete a level role."""
    try:
        from .db import get_db_session
        from .models import LevelRole

        with get_db_session() as db:
            role = db.query(LevelRole).filter_by(
                id=int(role_id),
                guild_id=int(guild_id)
            ).first()

            if not role:
                return JsonResponse({'error': 'Level role not found'}, status=404)

            db.delete(role)
            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# Role Management Dashboard (with CSV Import - Pro/Premium)
# =============================================================================

@discord_required
def guild_roles(request, guild_id):
    """Role management page for a guild."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    # Fetch guild info including subscription tier
    is_premium = False
    pending_actions = []
    recent_imports = []

    try:
        from .db import get_db_session
        from .models import Guild as GuildModel, PendingAction, ActionStatus, BulkImportJob

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if guild_record:
                is_premium = guild_record.is_premium()

            # Get pending role actions
            actions = db.query(PendingAction).filter_by(
                guild_id=int(guild_id)
            ).filter(
                PendingAction.action_type.in_(['role_add', 'role_remove', 'role_bulk_add', 'role_bulk_remove'])
            ).order_by(PendingAction.created_at.desc()).limit(10).all()

            pending_actions = [
                {
                    'id': a.id,
                    'action_type': a.action_type.value,
                    'status': a.status.value,
                    'created_at': a.created_at,
                    'triggered_by_name': a.triggered_by_name,
                }
                for a in actions
            ]

            # Get recent bulk imports
            imports = db.query(BulkImportJob).filter_by(
                guild_id=int(guild_id),
                job_type='role_assign'
            ).order_by(BulkImportJob.created_at.desc()).limit(5).all()

            recent_imports = [
                {
                    'id': i.id,
                    'filename': i.filename,
                    'status': i.status,
                    'total_records': i.total_records,
                    'success_count': i.success_count,
                    'error_count': i.error_count,
                    'created_at': i.created_at,
                }
                for i in imports
            ]

    except Exception as e:
        logger.warning(f"Could not fetch role data: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'is_premium': is_premium,
        'pending_actions': pending_actions,
        'recent_imports': recent_imports,
    }
    return render(request, 'warden/roles.html', context)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_role_action(request, guild_id):
    """POST /api/guild/<id>/roles/action/ - Queue a role action."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action')  # 'add' or 'remove'
    user_id = data.get('user_id')
    role_id = data.get('role_id')
    reason = data.get('reason', f'Role {action} via web dashboard')

    if not all([action, user_id, role_id]):
        return JsonResponse({'error': 'Missing required fields'}, status=400)

    try:
        from .actions import queue_role_add, queue_role_remove

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        if action == 'add':
            action_id = queue_role_add(
                guild_id=int(guild_id),
                user_id=int(user_id),
                role_id=int(role_id),
                reason=reason,
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name
            )
        elif action == 'remove':
            action_id = queue_role_remove(
                guild_id=int(guild_id),
                user_id=int(user_id),
                role_id=int(role_id),
                reason=reason,
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name
            )
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)

        return JsonResponse({
            'success': True,
            'action_id': action_id,
            'message': f'Role {action} queued (ID: {action_id})'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_role_bulk_import(request, guild_id):
    """POST /api/guild/<id>/roles/import/ - Import CSV for bulk role assignment."""
    # Check if premium/pro
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record or not guild_record.is_premium():
                return JsonResponse({
                    'error': 'Bulk import requires Premium or Pro subscription'
                }, status=403)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    # Get uploaded file
    csv_file = request.FILES.get('file')
    if not csv_file:
        return JsonResponse({'error': 'No file uploaded'}, status=400)

    role_id = request.POST.get('role_id')
    action = request.POST.get('action', 'add')  # 'add' or 'remove'

    if not role_id:
        return JsonResponse({'error': 'Missing role_id'}, status=400)

    try:
        import csv
        import io
        from .actions import (
            queue_bulk_role_add, create_bulk_import_job, update_bulk_import_progress
        )

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        # Read CSV
        content = csv_file.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))

        user_ids = []
        errors = []

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            user_id = row.get('user_id') or row.get('discord_id') or row.get('id')
            if user_id:
                try:
                    user_ids.append(int(user_id))
                except ValueError:
                    errors.append({'row': row_num, 'error': f'Invalid user_id: {user_id}'})
            else:
                errors.append({'row': row_num, 'error': 'Missing user_id column'})

        if not user_ids:
            return JsonResponse({
                'error': 'No valid user IDs found in CSV',
                'parse_errors': errors
            }, status=400)

        # Create bulk import job for tracking
        job_id = create_bulk_import_job(
            guild_id=int(guild_id),
            job_type='role_assign',
            filename=csv_file.name,
            total_records=len(user_ids),
            triggered_by=triggered_by,
            triggered_by_name=triggered_by_name
        )

        # Queue the bulk action
        if action == 'add':
            action_id = queue_bulk_role_add(
                guild_id=int(guild_id),
                role_id=int(role_id),
                user_ids=user_ids,
                reason=f'Bulk import from {csv_file.name}',
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name
            )
        else:
            from .actions import queue_action, ActionType
            action_id = queue_action(
                guild_id=int(guild_id),
                action_type=ActionType.ROLE_BULK_REMOVE,
                payload={'role_id': int(role_id), 'user_ids': user_ids},
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name,
                source='csv_import'
            )

        return JsonResponse({
            'success': True,
            'job_id': job_id,
            'action_id': action_id,
            'total_users': len(user_ids),
            'parse_errors': errors[:10] if errors else [],  # Return first 10 errors
            'message': f'Queued bulk {action} for {len(user_ids)} users'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_auth_required
def api_bulk_import_status(request, guild_id, job_id):
    """GET /api/guild/<id>/roles/import/<job_id>/ - Get bulk import status."""
    try:
        from .actions import get_bulk_import_job

        job = get_bulk_import_job(int(job_id))
        if not job or job['guild_id'] != int(guild_id):
            return JsonResponse({'error': 'Job not found'}, status=404)

        return JsonResponse({'success': True, 'job': job})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# Audit Logs Dashboard
# =============================================================================

@discord_required
def guild_audit_logs(request, guild_id):
    """View audit logs for a guild."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    # Get filter parameters
    action_filter = request.GET.get('action', '')
    actor_filter = request.GET.get('actor', '')
    target_filter = request.GET.get('target', '')
    days = int(request.GET.get('days', 7))

    # Fetch audit logs from database
    audit_logs = []
    total_count = 0
    action_types = []

    try:
        from .db import get_db_session
        from .models import AuditLog, AuditAction, Guild as GuildModel
        import time

        with get_db_session() as db:
            # Get guild info
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild_record.is_premium() if guild_record else False

            # Limit days based on subscription
            if not is_premium:
                days = min(days, 7)  # Free: 7 days max
            elif guild_record and guild_record.subscription_tier.value == 'pro':
                days = min(days, 90)  # Pro: 90 days
            else:
                days = min(days, 30)  # Premium: 30 days

            # Calculate time threshold
            time_threshold = int(time.time()) - (days * 24 * 60 * 60)

            # Build query
            query = db.query(AuditLog).filter(
                AuditLog.guild_id == int(guild_id),
                AuditLog.timestamp >= time_threshold
            )

            # Apply filters
            if action_filter:
                try:
                    action_enum = AuditAction(action_filter)
                    query = query.filter(AuditLog.action == action_enum)
                except ValueError:
                    pass

            if actor_filter:
                query = query.filter(AuditLog.actor_id == int(actor_filter))

            if target_filter:
                query = query.filter(AuditLog.target_id == int(target_filter))

            # Get total count
            total_count = query.count()

            # Get logs (most recent first, limit 100)
            logs = query.order_by(AuditLog.timestamp.desc()).limit(100).all()

            audit_logs = [
                {
                    'id': log.id,
                    'action': log.action.value,
                    'action_display': log.action.value.replace('_', ' ').title(),
                    'category': log.action_category or get_action_category(log.action.value),
                    'actor_id': str(log.actor_id) if log.actor_id else None,
                    'actor_name': log.actor_name or 'System',
                    'target_id': str(log.target_id) if log.target_id else None,
                    'target_name': log.target_name,
                    'target_type': log.target_type,
                    'reason': log.reason,
                    'details': log.details,
                    'timestamp': log.timestamp,
                }
                for log in logs
            ]

            # Get unique action types for filter dropdown
            action_types = [a.value for a in AuditAction]

    except Exception as e:
        logger.warning(f"Could not fetch audit logs: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'audit_logs': audit_logs,
        'total_count': total_count,
        'action_types': action_types,
        'current_filters': {
            'action': action_filter,
            'actor': actor_filter,
            'target': target_filter,
            'days': days,
        },
    }
    return render(request, 'warden/audit.html', context)


def get_action_category(action: str) -> str:
    """Get category for an audit action."""
    if action.startswith('member_'):
        return 'members'
    elif action.startswith('role_'):
        return 'roles'
    elif action.startswith('channel_'):
        return 'channels'
    elif action.startswith('message_'):
        return 'messages'
    elif action.startswith('verification_'):
        return 'verification'
    elif action in ['raid_detected', 'lockdown_activated', 'lockdown_deactivated']:
        return 'security'
    else:
        return 'other'


# =============================================================================
# Audit Logs API Endpoints
# =============================================================================

@api_auth_required
def api_audit_logs(request, guild_id):
    """GET /api/guild/<id>/audit/ - Get paginated audit logs."""
    try:
        from .db import get_db_session
        from .models import AuditLog, AuditAction, Guild as GuildModel
        import time

        # Pagination
        page = int(request.GET.get('page', 1))
        per_page = min(int(request.GET.get('per_page', 50)), 100)
        offset = (page - 1) * per_page

        # Filters
        action_filter = request.GET.get('action', '')
        actor_filter = request.GET.get('actor', '')
        target_filter = request.GET.get('target', '')
        days = int(request.GET.get('days', 7))

        with get_db_session() as db:
            # Check subscription for day limits
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild_record.is_premium() if guild_record else False

            if not is_premium:
                days = min(days, 7)
            elif guild_record and guild_record.subscription_tier.value == 'pro':
                days = min(days, 90)
            else:
                days = min(days, 30)

            time_threshold = int(time.time()) - (days * 24 * 60 * 60)

            # Build query
            query = db.query(AuditLog).filter(
                AuditLog.guild_id == int(guild_id),
                AuditLog.timestamp >= time_threshold
            )

            if action_filter:
                try:
                    action_enum = AuditAction(action_filter)
                    query = query.filter(AuditLog.action == action_enum)
                except ValueError:
                    pass

            if actor_filter:
                query = query.filter(AuditLog.actor_id == int(actor_filter))

            if target_filter:
                query = query.filter(AuditLog.target_id == int(target_filter))

            total = query.count()
            logs = query.order_by(AuditLog.timestamp.desc()).offset(offset).limit(per_page).all()

            return JsonResponse({
                'success': True,
                'logs': [
                    {
                        'id': log.id,
                        'action': log.action.value,
                        'action_display': log.action.value.replace('_', ' ').title(),
                        'category': log.action_category or get_action_category(log.action.value),
                        'actor_id': str(log.actor_id) if log.actor_id else None,
                        'actor_name': log.actor_name or 'System',
                        'target_id': str(log.target_id) if log.target_id else None,
                        'target_name': log.target_name,
                        'target_type': log.target_type,
                        'reason': log.reason,
                        'details': log.details,
                        'timestamp': log.timestamp,
                    }
                    for log in logs
                ],
                'total': total,
                'page': page,
                'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page,
                'max_days': days,
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_auth_required
def api_audit_stats(request, guild_id):
    """GET /api/guild/<id>/audit/stats/ - Get audit log statistics."""
    try:
        from .db import get_db_session
        from .models import AuditLog, AuditAction
        from sqlalchemy import func
        import time

        days = int(request.GET.get('days', 7))
        time_threshold = int(time.time()) - (days * 24 * 60 * 60)

        with get_db_session() as db:
            # Count by action type
            action_counts = db.query(
                AuditLog.action,
                func.count(AuditLog.id).label('count')
            ).filter(
                AuditLog.guild_id == int(guild_id),
                AuditLog.timestamp >= time_threshold
            ).group_by(AuditLog.action).all()

            # Top actors
            top_actors = db.query(
                AuditLog.actor_id,
                AuditLog.actor_name,
                func.count(AuditLog.id).label('count')
            ).filter(
                AuditLog.guild_id == int(guild_id),
                AuditLog.timestamp >= time_threshold,
                AuditLog.actor_id.isnot(None)
            ).group_by(AuditLog.actor_id, AuditLog.actor_name).order_by(
                func.count(AuditLog.id).desc()
            ).limit(10).all()

            # Total count
            total = db.query(AuditLog).filter(
                AuditLog.guild_id == int(guild_id),
                AuditLog.timestamp >= time_threshold
            ).count()

            return JsonResponse({
                'success': True,
                'stats': {
                    'total': total,
                    'by_action': {
                        action.value: count for action, count in action_counts
                    },
                    'top_actors': [
                        {
                            'actor_id': str(actor_id),
                            'actor_name': actor_name or f'User {actor_id}',
                            'count': count
                        }
                        for actor_id, actor_name, count in top_actors
                    ],
                    'days': days,
                }
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# Welcome/Goodbye Messages Dashboard
# =============================================================================

@discord_required
def guild_welcome(request, guild_id):
    """Welcome and goodbye message configuration page."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    # Fetch welcome config from database
    welcome_config = None
    guild_channels = []

    try:
        from .db import get_db_session
        from .models import WelcomeConfig, Guild as GuildModel

        with get_db_session() as db:
            # Ensure guild exists
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            # Get welcome config
            config = db.query(WelcomeConfig).filter_by(guild_id=int(guild_id)).first()

            if config:
                welcome_config = {
                    'enabled': config.enabled,
                    'channel_message_enabled': config.channel_message_enabled,
                    'channel_message': config.channel_message,
                    'channel_embed_enabled': config.channel_embed_enabled,
                    'channel_embed_title': config.channel_embed_title,
                    'channel_embed_color': config.channel_embed_color,
                    'channel_embed_thumbnail': config.channel_embed_thumbnail,
                    'channel_embed_footer': config.channel_embed_footer,
                    'dm_enabled': config.dm_enabled,
                    'dm_message': config.dm_message,
                    'goodbye_enabled': config.goodbye_enabled,
                    'goodbye_message': config.goodbye_message,
                    'auto_role_id': str(config.auto_role_id) if config.auto_role_id else '',
                }

                # Get welcome channel from guild record
                if guild_record:
                    welcome_config['welcome_channel_id'] = str(guild_record.welcome_channel_id) if guild_record.welcome_channel_id else ''
            else:
                # Defaults
                welcome_config = {
                    'enabled': True,
                    'channel_message_enabled': True,
                    'channel_message': 'Welcome to **{server}**, {user}! You are member #{member_count}.',
                    'channel_embed_enabled': True,
                    'channel_embed_title': 'Welcome!',
                    'channel_embed_color': 0x5865F2,
                    'channel_embed_thumbnail': True,
                    'channel_embed_footer': '',
                    'dm_enabled': False,
                    'dm_message': 'Welcome to **{server}**! Please read the rules and enjoy your stay.',
                    'goodbye_enabled': False,
                    'goodbye_message': '**{username}** has left the server.',
                    'auto_role_id': '',
                    'welcome_channel_id': '',
                }

    except Exception as e:
        logger.warning(f"Could not fetch welcome config: {e}")
        welcome_config = {}

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'welcome_config': welcome_config,
    }
    return render(request, 'warden/welcome.html', context)


@csrf_exempt
@require_http_methods(["POST", "PATCH"])
@api_auth_required
def api_welcome_config_update(request, guild_id):
    """POST /api/guild/<id>/welcome/config/ - Update welcome configuration."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import WelcomeConfig, Guild as GuildModel
        import time

        with get_db_session() as db:
            # Ensure guild exists
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                guild_record = GuildModel(guild_id=int(guild_id))
                db.add(guild_record)
                db.flush()

            # Get or create welcome config
            config = db.query(WelcomeConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                config = WelcomeConfig(guild_id=int(guild_id))
                db.add(config)

            # Update fields
            if 'enabled' in data:
                config.enabled = bool(data['enabled'])
            if 'channel_message_enabled' in data:
                config.channel_message_enabled = bool(data['channel_message_enabled'])
            if 'channel_message' in data:
                config.channel_message = data['channel_message']
            if 'channel_embed_enabled' in data:
                config.channel_embed_enabled = bool(data['channel_embed_enabled'])
            if 'channel_embed_title' in data:
                config.channel_embed_title = data['channel_embed_title']
            if 'channel_embed_color' in data:
                config.channel_embed_color = int(data['channel_embed_color'])
            if 'channel_embed_thumbnail' in data:
                config.channel_embed_thumbnail = bool(data['channel_embed_thumbnail'])
            if 'channel_embed_footer' in data:
                config.channel_embed_footer = data['channel_embed_footer'] or None
            if 'dm_enabled' in data:
                config.dm_enabled = bool(data['dm_enabled'])
            if 'dm_message' in data:
                config.dm_message = data['dm_message']
            if 'goodbye_enabled' in data:
                config.goodbye_enabled = bool(data['goodbye_enabled'])
            if 'goodbye_message' in data:
                config.goodbye_message = data['goodbye_message']
            if 'auto_role_id' in data:
                config.auto_role_id = int(data['auto_role_id']) if data['auto_role_id'] else None

            # Update welcome channel in guild record
            if 'welcome_channel_id' in data:
                guild_record.welcome_channel_id = int(data['welcome_channel_id']) if data['welcome_channel_id'] else None

            config.updated_at = int(time.time())

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_auth_required
def api_welcome_config(request, guild_id):
    """GET /api/guild/<id>/welcome/config/ - Get welcome configuration."""
    try:
        from .db import get_db_session
        from .models import WelcomeConfig, Guild as GuildModel

        with get_db_session() as db:
            config = db.query(WelcomeConfig).filter_by(guild_id=int(guild_id)).first()
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            if not config:
                return JsonResponse({
                    'success': True,
                    'config': {
                        'enabled': True,
                        'channel_message_enabled': True,
                        'channel_message': 'Welcome to **{server}**, {user}! You are member #{member_count}.',
                        'channel_embed_enabled': True,
                        'channel_embed_title': 'Welcome!',
                        'channel_embed_color': 0x5865F2,
                        'channel_embed_thumbnail': True,
                        'channel_embed_footer': '',
                        'dm_enabled': False,
                        'dm_message': 'Welcome to **{server}**! Please read the rules and enjoy your stay.',
                        'goodbye_enabled': False,
                        'goodbye_message': '**{username}** has left the server.',
                        'auto_role_id': '',
                        'welcome_channel_id': '',
                    }
                })

            return JsonResponse({
                'success': True,
                'config': {
                    'enabled': config.enabled,
                    'channel_message_enabled': config.channel_message_enabled,
                    'channel_message': config.channel_message,
                    'channel_embed_enabled': config.channel_embed_enabled,
                    'channel_embed_title': config.channel_embed_title,
                    'channel_embed_color': config.channel_embed_color,
                    'channel_embed_thumbnail': config.channel_embed_thumbnail,
                    'channel_embed_footer': config.channel_embed_footer or '',
                    'dm_enabled': config.dm_enabled,
                    'dm_message': config.dm_message,
                    'goodbye_enabled': config.goodbye_enabled,
                    'goodbye_message': config.goodbye_message,
                    'auto_role_id': str(config.auto_role_id) if config.auto_role_id else '',
                    'welcome_channel_id': str(guild_record.welcome_channel_id) if guild_record and guild_record.welcome_channel_id else '',
                }
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_auth_required
def api_welcome_test(request, guild_id):
    """POST /api/guild/<id>/welcome/test/ - Send a test welcome message."""
    try:
        from .actions import queue_action, ActionType

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        message_type = request.GET.get('type', 'welcome')  # 'welcome' or 'goodbye'

        action_id = queue_action(
            guild_id=int(guild_id),
            action_type=ActionType.MESSAGE_SEND,
            payload={
                'type': f'test_{message_type}',
                'target_user_id': triggered_by,
            },
            triggered_by=triggered_by,
            triggered_by_name=triggered_by_name,
            source='website'
        )

        return JsonResponse({
            'success': True,
            'action_id': action_id,
            'message': f'Test {message_type} message queued!'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# Level-Up Messages Dashboard
# =============================================================================

@discord_required
def guild_levelup(request, guild_id):
    """Level-up message configuration page."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    levelup_config = None

    try:
        from .db import get_db_session
        from .models import LevelUpConfig, Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            config = db.query(LevelUpConfig).filter_by(guild_id=int(guild_id)).first()

            if config:
                levelup_config = {
                    'enabled': config.enabled,
                    'destination': config.destination,
                    'message': config.message,
                    'use_embed': config.use_embed,
                    'embed_color': config.embed_color,
                    'show_progress': config.show_progress,
                    'ping_user': config.ping_user,
                    'announce_role_reward': config.announce_role_reward,
                    'role_reward_message': config.role_reward_message,
                    'milestone_levels': config.milestone_levels or '[]',
                    'milestone_message': config.milestone_message,
                    'quiet_hours_enabled': config.quiet_hours_enabled,
                    'quiet_hours_start': config.quiet_hours_start,
                    'quiet_hours_end': config.quiet_hours_end,
                    'level_up_channel_id': str(guild_record.level_up_channel_id) if guild_record and guild_record.level_up_channel_id else '',
                }
            else:
                levelup_config = {
                    'enabled': True,
                    'destination': 'current',
                    'message': "Congrats {user}! You've reached **Level {level}**!",
                    'use_embed': True,
                    'embed_color': 0x5865F2,
                    'show_progress': True,
                    'ping_user': True,
                    'announce_role_reward': True,
                    'role_reward_message': "You've also earned the **{role}** role!",
                    'milestone_levels': '[10, 25, 50, 100]',
                    'milestone_message': "Incredible! You've hit the **Level {level}** milestone!",
                    'quiet_hours_enabled': False,
                    'quiet_hours_start': 22,
                    'quiet_hours_end': 8,
                    'level_up_channel_id': '',
                }

    except Exception as e:
        logger.warning(f"Could not fetch level-up config: {e}")
        levelup_config = {}

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'levelup_config': levelup_config,
    }
    return render(request, 'warden/levelup.html', context)


@csrf_exempt
@require_http_methods(["POST", "PATCH"])
@api_auth_required
def api_levelup_config_update(request, guild_id):
    """POST /api/guild/<id>/levelup/config/ - Update level-up configuration."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import LevelUpConfig, Guild as GuildModel
        import time

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                guild_record = GuildModel(guild_id=int(guild_id))
                db.add(guild_record)
                db.flush()

            config = db.query(LevelUpConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                config = LevelUpConfig(guild_id=int(guild_id))
                db.add(config)

            # Update fields
            if 'enabled' in data:
                config.enabled = bool(data['enabled'])
            if 'destination' in data:
                config.destination = data['destination']
            if 'message' in data:
                config.message = data['message']
            if 'use_embed' in data:
                config.use_embed = bool(data['use_embed'])
            if 'embed_color' in data:
                config.embed_color = int(data['embed_color'])
            if 'show_progress' in data:
                config.show_progress = bool(data['show_progress'])
            if 'ping_user' in data:
                config.ping_user = bool(data['ping_user'])
            if 'announce_role_reward' in data:
                config.announce_role_reward = bool(data['announce_role_reward'])
            if 'role_reward_message' in data:
                config.role_reward_message = data['role_reward_message']
            if 'milestone_levels' in data:
                config.milestone_levels = data['milestone_levels']
            if 'milestone_message' in data:
                config.milestone_message = data['milestone_message']
            if 'quiet_hours_enabled' in data:
                config.quiet_hours_enabled = bool(data['quiet_hours_enabled'])
            if 'quiet_hours_start' in data:
                config.quiet_hours_start = int(data['quiet_hours_start'])
            if 'quiet_hours_end' in data:
                config.quiet_hours_end = int(data['quiet_hours_end'])

            # Update channel in guild record
            if 'level_up_channel_id' in data:
                guild_record.level_up_channel_id = int(data['level_up_channel_id']) if data['level_up_channel_id'] else None

            config.updated_at = int(time.time())

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# Admin/Server Settings Dashboard
# =============================================================================

@discord_required
def guild_settings(request, guild_id):
    """Server settings configuration page."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    settings = {}

    try:
        from .db import get_db_session
        from .models import Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            if guild_record:
                settings = {
                    'prefix': guild_record.bot_prefix or '!',
                    'language': guild_record.language or 'en',
                    'timezone': guild_record.timezone or 'UTC',
                    'token_name': guild_record.token_name or 'Hero Tokens',
                    'token_emoji': guild_record.token_emoji or ':coin:',
                    'mod_log_channel_id': str(guild_record.mod_log_channel_id) if guild_record.mod_log_channel_id else '',
                    'subscription_tier': guild_record.subscription_tier.value if guild_record.subscription_tier else 'free',
                }
            else:
                settings = {
                    'prefix': '!',
                    'language': 'en',
                    'timezone': 'UTC',
                    'token_name': 'Hero Tokens',
                    'token_emoji': ':coin:',
                    'mod_log_channel_id': '',
                    'subscription_tier': 'free',
                }

    except Exception as e:
        logger.warning(f"Could not fetch settings: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'settings': settings,
    }
    return render(request, 'warden/settings.html', context)


@csrf_exempt
@require_http_methods(["POST", "PATCH"])
@api_auth_required
def api_settings_update(request, guild_id):
    """POST /api/guild/<id>/settings/ - Update server settings."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                guild_record = GuildModel(guild_id=int(guild_id))
                db.add(guild_record)

            # Update fields
            if 'prefix' in data:
                guild_record.bot_prefix = data['prefix'][:10] if data['prefix'] else '!'
            if 'language' in data:
                guild_record.language = data['language']
            if 'timezone' in data:
                guild_record.timezone = data['timezone']
            if 'token_name' in data:
                guild_record.token_name = data['token_name'][:50] if data['token_name'] else 'Hero Tokens'
            if 'token_emoji' in data:
                guild_record.token_emoji = data['token_emoji'][:20] if data['token_emoji'] else ':coin:'
            if 'mod_log_channel_id' in data:
                guild_record.mod_log_channel_id = int(data['mod_log_channel_id']) if data['mod_log_channel_id'] else None

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# Verification Configuration Dashboard
# =============================================================================

@discord_required
def guild_verification(request, guild_id):
    """Verification configuration page."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    verification_config = {}

    try:
        from .db import get_db_session
        from .models import VerificationConfig, Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            config = db.query(VerificationConfig).filter_by(guild_id=int(guild_id)).first()

            if config:
                verification_config = {
                    'verification_type': config.verification_type.value,
                    'require_account_age': config.require_account_age,
                    'min_account_age_days': config.min_account_age_days,
                    'button_text': config.button_text,
                    'captcha_length': config.captcha_length,
                    'captcha_timeout_seconds': config.captcha_timeout_seconds,
                    'require_rules_read': config.require_rules_read,
                    'require_intro_message': config.require_intro_message,
                    'intro_channel_id': str(config.intro_channel_id) if config.intro_channel_id else '',
                    'verification_instructions': config.verification_instructions or '',
                    'verified_message': config.verified_message or 'You have been verified!',
                    'verification_timeout_hours': config.verification_timeout_hours,
                    'kick_on_timeout': config.kick_on_timeout,
                    'verification_channel_id': str(guild_record.verification_channel_id) if guild_record and guild_record.verification_channel_id else '',
                    'verified_role_id': str(guild_record.verified_role_id) if guild_record and guild_record.verified_role_id else '',
                }
            else:
                verification_config = {
                    'verification_type': 'button',
                    'require_account_age': True,
                    'min_account_age_days': 7,
                    'button_text': 'I agree to the rules',
                    'captcha_length': 6,
                    'captcha_timeout_seconds': 300,
                    'require_rules_read': False,
                    'require_intro_message': False,
                    'intro_channel_id': '',
                    'verification_instructions': '',
                    'verified_message': 'You have been verified!',
                    'verification_timeout_hours': 24,
                    'kick_on_timeout': False,
                    'verification_channel_id': '',
                    'verified_role_id': '',
                }

    except Exception as e:
        logger.warning(f"Could not fetch verification config: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'verification_config': verification_config,
    }
    return render(request, 'warden/verification.html', context)


@csrf_exempt
@require_http_methods(["POST", "PATCH"])
@api_auth_required
def api_verification_config_update(request, guild_id):
    """POST /api/guild/<id>/verification/config/ - Update verification configuration."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import VerificationConfig, VerificationType, Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                guild_record = GuildModel(guild_id=int(guild_id))
                db.add(guild_record)
                db.flush()

            config = db.query(VerificationConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                config = VerificationConfig(guild_id=int(guild_id))
                db.add(config)

            # Update fields
            if 'verification_type' in data:
                config.verification_type = VerificationType(data['verification_type'])
            if 'require_account_age' in data:
                config.require_account_age = bool(data['require_account_age'])
            if 'min_account_age_days' in data:
                config.min_account_age_days = int(data['min_account_age_days'])
            if 'button_text' in data:
                config.button_text = data['button_text'][:100]
            if 'captcha_length' in data:
                config.captcha_length = max(4, min(10, int(data['captcha_length'])))
            if 'captcha_timeout_seconds' in data:
                config.captcha_timeout_seconds = int(data['captcha_timeout_seconds'])
            if 'require_rules_read' in data:
                config.require_rules_read = bool(data['require_rules_read'])
            if 'require_intro_message' in data:
                config.require_intro_message = bool(data['require_intro_message'])
            if 'intro_channel_id' in data:
                config.intro_channel_id = int(data['intro_channel_id']) if data['intro_channel_id'] else None
            if 'verification_instructions' in data:
                config.verification_instructions = data['verification_instructions']
            if 'verified_message' in data:
                config.verified_message = data['verified_message']
            if 'verification_timeout_hours' in data:
                config.verification_timeout_hours = int(data['verification_timeout_hours'])
            if 'kick_on_timeout' in data:
                config.kick_on_timeout = bool(data['kick_on_timeout'])

            # Update guild channels/roles
            if 'verification_channel_id' in data:
                guild_record.verification_channel_id = int(data['verification_channel_id']) if data['verification_channel_id'] else None
            if 'verified_role_id' in data:
                guild_record.verified_role_id = int(data['verified_role_id']) if data['verified_role_id'] else None

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# Moderation Dashboard
# =============================================================================

@discord_required
def guild_moderation(request, guild_id):
    """Moderation dashboard - warnings, bans, timeouts."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    warnings = []
    stats = {'total': 0, 'active': 0, 'week': 0}

    try:
        from .db import get_db_session
        from .models import Warning
        import time

        with get_db_session() as db:
            # Get recent warnings
            recent_warnings = db.query(Warning).filter(
                Warning.guild_id == int(guild_id)
            ).order_by(Warning.issued_at.desc()).limit(50).all()

            warnings = [
                {
                    'id': w.id,
                    'user_id': str(w.user_id),
                    'warning_type': w.warning_type.value,
                    'reason': w.reason,
                    'severity': w.severity,
                    'issued_by': str(w.issued_by) if w.issued_by else 'AutoMod',
                    'issued_by_name': w.issued_by_name or 'AutoMod',
                    'issued_at': w.issued_at,
                    'is_active': w.is_active,
                    'pardoned': w.pardoned,
                    'action_taken': w.action_taken,
                }
                for w in recent_warnings
            ]

            # Stats
            week_ago = int(time.time()) - (7 * 24 * 60 * 60)
            stats['total'] = db.query(Warning).filter(Warning.guild_id == int(guild_id)).count()
            stats['active'] = db.query(Warning).filter(Warning.guild_id == int(guild_id), Warning.is_active == True).count()
            stats['week'] = db.query(Warning).filter(Warning.guild_id == int(guild_id), Warning.issued_at >= week_ago).count()

    except Exception as e:
        logger.warning(f"Could not fetch moderation data: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'warnings': warnings,
        'stats': stats,
    }
    return render(request, 'warden/moderation.html', context)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_warning_pardon(request, guild_id, warning_id):
    """POST /api/guild/<id>/warnings/<warning_id>/pardon/ - Pardon a warning."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        data = {}

    try:
        from .db import get_db_session
        from .models import Warning
        import time

        discord_user = request.session.get('discord_user', {})
        pardoned_by = int(discord_user.get('id', 0))

        with get_db_session() as db:
            warning = db.query(Warning).filter(
                Warning.id == int(warning_id),
                Warning.guild_id == int(guild_id)
            ).first()

            if not warning:
                return JsonResponse({'error': 'Warning not found'}, status=404)

            warning.is_active = False
            warning.pardoned = True
            warning.pardoned_by = pardoned_by
            warning.pardoned_at = int(time.time())
            warning.pardon_reason = data.get('reason', '')

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_auth_required
def api_warnings_list(request, guild_id):
    """GET /api/guild/<id>/warnings/ - Get warnings list with pagination."""
    try:
        from .db import get_db_session
        from .models import Warning

        page = int(request.GET.get('page', 1))
        per_page = min(int(request.GET.get('per_page', 25)), 100)
        offset = (page - 1) * per_page
        user_filter = request.GET.get('user', '')
        active_only = request.GET.get('active', 'false').lower() == 'true'

        with get_db_session() as db:
            query = db.query(Warning).filter(Warning.guild_id == int(guild_id))

            if user_filter:
                query = query.filter(Warning.user_id == int(user_filter))
            if active_only:
                query = query.filter(Warning.is_active == True)

            total = query.count()
            warnings = query.order_by(Warning.issued_at.desc()).offset(offset).limit(per_page).all()

            return JsonResponse({
                'success': True,
                'warnings': [
                    {
                        'id': w.id,
                        'user_id': str(w.user_id),
                        'warning_type': w.warning_type.value,
                        'reason': w.reason,
                        'severity': w.severity,
                        'issued_by_name': w.issued_by_name or 'AutoMod',
                        'issued_at': w.issued_at,
                        'is_active': w.is_active,
                        'pardoned': w.pardoned,
                        'action_taken': w.action_taken,
                    }
                    for w in warnings
                ],
                'total': total,
                'page': page,
                'per_page': per_page,
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# Templates Dashboard (Channel & Role Templates)
# =============================================================================

@discord_required
def guild_templates(request, guild_id):
    """Templates dashboard for channel and role templates."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('warden_dashboard')

    channel_templates = []
    role_templates = []
    is_premium = False

    try:
        from .db import get_db_session
        from .models import ChannelTemplate, RoleTemplate, Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild_record.is_premium() if guild_record else False

            # Get channel templates
            ch_templates = db.query(ChannelTemplate).filter(
                ChannelTemplate.guild_id == int(guild_id)
            ).order_by(ChannelTemplate.created_at.desc()).all()

            channel_templates = [
                {
                    'id': t.id,
                    'name': t.name,
                    'description': t.description,
                    'use_count': t.use_count,
                    'created_at': t.created_at,
                }
                for t in ch_templates
            ]

            # Get role templates
            r_templates = db.query(RoleTemplate).filter(
                RoleTemplate.guild_id == int(guild_id)
            ).order_by(RoleTemplate.created_at.desc()).all()

            role_templates = [
                {
                    'id': t.id,
                    'name': t.name,
                    'description': t.description,
                    'use_count': t.use_count,
                    'created_at': t.created_at,
                }
                for t in r_templates
            ]

    except Exception as e:
        logger.warning(f"Could not fetch templates: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'channel_templates': channel_templates,
        'role_templates': role_templates,
        'is_premium': is_premium,
    }
    return render(request, 'warden/templates.html', context)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_channel_template_create(request, guild_id):
    """POST /api/guild/<id>/templates/channels/ - Create channel template."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import ChannelTemplate

        discord_user = request.session.get('discord_user', {})
        created_by = int(discord_user.get('id', 0))

        with get_db_session() as db:
            template = ChannelTemplate(
                guild_id=int(guild_id),
                name=data.get('name', 'Untitled')[:100],
                description=data.get('description', '')[:500],
                template_data=json_lib.dumps(data.get('channels', [])),
                created_by=created_by,
            )
            db.add(template)
            db.flush()

            return JsonResponse({'success': True, 'id': template.id})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_role_template_create(request, guild_id):
    """POST /api/guild/<id>/templates/roles/ - Create role template."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import RoleTemplate

        discord_user = request.session.get('discord_user', {})
        created_by = int(discord_user.get('id', 0))

        with get_db_session() as db:
            template = RoleTemplate(
                guild_id=int(guild_id),
                name=data.get('name', 'Untitled')[:100],
                description=data.get('description', '')[:500],
                template_data=json_lib.dumps(data.get('roles', [])),
                created_by=created_by,
            )
            db.add(template)
            db.flush()

            return JsonResponse({'success': True, 'id': template.id})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
@api_auth_required
def api_template_delete(request, guild_id, template_type, template_id):
    """DELETE /api/guild/<id>/templates/<type>/<id>/ - Delete template."""
    try:
        from .db import get_db_session
        from .models import ChannelTemplate, RoleTemplate

        with get_db_session() as db:
            if template_type == 'channels':
                template = db.query(ChannelTemplate).filter(
                    ChannelTemplate.id == int(template_id),
                    ChannelTemplate.guild_id == int(guild_id)
                ).first()
            else:
                template = db.query(RoleTemplate).filter(
                    RoleTemplate.id == int(template_id),
                    RoleTemplate.guild_id == int(guild_id)
                ).first()

            if not template:
                return JsonResponse({'error': 'Template not found'}, status=404)

            db.delete(template)
            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_template_apply(request, guild_id, template_type, template_id):
    """POST /api/guild/<id>/templates/<type>/<id>/apply/ - Apply template."""
    try:
        from .db import get_db_session
        from .models import ChannelTemplate, RoleTemplate
        from .actions import queue_action, ActionType

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        with get_db_session() as db:
            if template_type == 'channels':
                template = db.query(ChannelTemplate).filter(
                    ChannelTemplate.id == int(template_id),
                    ChannelTemplate.guild_id == int(guild_id)
                ).first()
                action_type = ActionType.CHANNEL_CREATE
            else:
                template = db.query(RoleTemplate).filter(
                    RoleTemplate.id == int(template_id),
                    RoleTemplate.guild_id == int(guild_id)
                ).first()
                action_type = ActionType.ROLE_CREATE

            if not template:
                return JsonResponse({'error': 'Template not found'}, status=404)

            # Queue the action
            action_id = queue_action(
                guild_id=int(guild_id),
                action_type=action_type,
                payload={
                    'template_id': template.id,
                    'template_data': template.template_data,
                    'type': template_type,
                },
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name,
                source='website'
            )

            # Increment use count
            template.use_count += 1

            return JsonResponse({'success': True, 'action_id': action_id})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Wrapper functions for specific template types
@csrf_exempt
@require_http_methods(["DELETE"])
@api_auth_required
def api_channel_template_delete(request, guild_id, template_id):
    """DELETE /api/guild/<id>/templates/channels/<id>/ - Delete channel template."""
    return api_template_delete(request, guild_id, 'channels', template_id)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_channel_template_apply(request, guild_id, template_id):
    """POST /api/guild/<id>/templates/channels/<id>/apply/ - Apply channel template."""
    return api_template_apply(request, guild_id, 'channels', template_id)


@csrf_exempt
@require_http_methods(["DELETE"])
@api_auth_required
def api_role_template_delete(request, guild_id, template_id):
    """DELETE /api/guild/<id>/templates/roles/<id>/ - Delete role template."""
    return api_template_delete(request, guild_id, 'roles', template_id)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_role_template_apply(request, guild_id, template_id):
    """POST /api/guild/<id>/templates/roles/<id>/apply/ - Apply role template."""
    return api_template_apply(request, guild_id, 'roles', template_id)


# =============================================================================
# DISCOVERY / SELF-PROMO
# =============================================================================

@discord_required
def guild_discovery(request, guild_id):
    """Discovery/Self-Promo dashboard."""
    user_guilds = request.session.get('discord_guilds', [])
    guild = next((g for g in user_guilds if str(g.get('id')) == str(guild_id)), None)

    if not guild:
        return redirect('warden_dashboard')

    # Check admin permission
    permissions = int(guild.get('permissions', 0))
    is_admin = (permissions & 0x8) == 0x8 or (permissions & 0x20) == 0x20
    if not is_admin:
        return redirect('warden_dashboard')

    try:
        from .db import get_db_session
        from .models import DiscoveryConfig, FeaturedPool, Guild
        import time

        now = int(time.time())

        with get_db_session() as db:
            # Get or create discovery config
            discovery_config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not discovery_config:
                discovery_config = DiscoveryConfig(guild_id=int(guild_id))
                db.add(discovery_config)
                db.flush()

            # Get pool entries
            pool_entries = db.query(FeaturedPool).filter(
                FeaturedPool.guild_id == int(guild_id),
                FeaturedPool.was_selected == False,
                FeaturedPool.expires_at > now
            ).order_by(FeaturedPool.entered_at.desc()).all()

            # Get recent features
            recent_features = db.query(FeaturedPool).filter(
                FeaturedPool.guild_id == int(guild_id),
                FeaturedPool.was_selected == True
            ).order_by(FeaturedPool.selected_at.desc()).limit(10).all()

            # Check premium
            guild_record = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild_record.is_premium() if guild_record else False

            context = {
                'guild': guild,
                'discovery_config': discovery_config,
                'pool_entries': pool_entries,
                'pool_count': len(pool_entries),
                'recent_features': recent_features,
                'is_premium': is_premium,
            }

            return render(request, 'warden/discovery.html', context)

    except Exception as e:
        return render(request, 'warden/discovery.html', {
            'guild': guild,
            'error': str(e),
        })


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_discovery_config_update(request, guild_id):
    """POST /api/guild/<id>/discovery/config/update/ - Update discovery config."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import DiscoveryConfig
        import time

        with get_db_session() as db:
            config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                config = DiscoveryConfig(guild_id=int(guild_id))
                db.add(config)

            # Update fields
            if 'enabled' in data:
                config.enabled = bool(data['enabled'])
            if 'selfpromo_channel_id' in data:
                config.selfpromo_channel_id = int(data['selfpromo_channel_id']) if data['selfpromo_channel_id'] else None
            if 'feature_channel_id' in data:
                config.feature_channel_id = int(data['feature_channel_id']) if data['feature_channel_id'] else None
            if 'feature_interval_hours' in data:
                config.feature_interval_hours = max(1, min(24, int(data['feature_interval_hours'])))
            if 'post_response' in data:
                config.post_response = data['post_response'][:500]
            if 'feature_message' in data:
                config.feature_message = data['feature_message'][:500]
            if 'use_embed' in data:
                config.use_embed = bool(data['use_embed'])
            if 'embed_color' in data:
                config.embed_color = int(data['embed_color'])
            if 'require_tokens' in data:
                config.require_tokens = bool(data['require_tokens'])
            if 'token_cost' in data:
                config.token_cost = max(0, int(data['token_cost']))
            if 'pool_entry_duration_hours' in data:
                config.pool_entry_duration_hours = max(1, min(168, int(data['pool_entry_duration_hours'])))
            if 'remove_after_feature' in data:
                config.remove_after_feature = bool(data['remove_after_feature'])
            if 'feature_cooldown_hours' in data:
                config.feature_cooldown_hours = max(0, min(168, int(data['feature_cooldown_hours'])))

            config.updated_at = int(time.time())

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_auth_required
def api_discovery_pool(request, guild_id):
    """GET /api/guild/<id>/discovery/pool/ - Get current pool entries."""
    try:
        from .db import get_db_session
        from .models import FeaturedPool
        import time

        now = int(time.time())

        with get_db_session() as db:
            entries = db.query(FeaturedPool).filter(
                FeaturedPool.guild_id == int(guild_id),
                FeaturedPool.was_selected == False,
                FeaturedPool.expires_at > now
            ).order_by(FeaturedPool.entered_at.desc()).all()

            pool_data = []
            for entry in entries:
                pool_data.append({
                    'id': entry.id,
                    'user_id': str(entry.user_id),
                    'content': entry.content,
                    'link_url': entry.link_url,
                    'platform': entry.platform,
                    'entered_at': entry.entered_at,
                    'expires_at': entry.expires_at,
                })

            return JsonResponse({'success': True, 'pool': pool_data, 'count': len(pool_data)})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
@api_auth_required
def api_discovery_pool_remove(request, guild_id, entry_id):
    """DELETE /api/guild/<id>/discovery/pool/<entry_id>/ - Remove entry from pool."""
    try:
        from .db import get_db_session
        from .models import FeaturedPool

        with get_db_session() as db:
            entry = db.query(FeaturedPool).filter(
                FeaturedPool.id == int(entry_id),
                FeaturedPool.guild_id == int(guild_id)
            ).first()

            if not entry:
                return JsonResponse({'error': 'Entry not found'}, status=404)

            db.delete(entry)
            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_discovery_force_feature(request, guild_id):
    """POST /api/guild/<id>/discovery/feature/ - Force a feature selection now."""
    try:
        from .db import get_db_session
        from .models import DiscoveryConfig, FeaturedPool
        from .actions import queue_action, ActionType
        import time

        now = int(time.time())
        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        with get_db_session() as db:
            config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not config or not config.enabled:
                return JsonResponse({'error': 'Discovery is disabled'}, status=400)

            # Check if there are entries
            entry_count = db.query(FeaturedPool).filter(
                FeaturedPool.guild_id == int(guild_id),
                FeaturedPool.was_selected == False,
                FeaturedPool.expires_at > now
            ).count()

            if entry_count == 0:
                return JsonResponse({'error': 'No entries in pool'}, status=400)

            # Queue the action for the bot to process
            action_id = queue_action(
                guild_id=int(guild_id),
                action_type=ActionType.MESSAGE_SEND,  # Using generic action type
                payload={
                    'action': 'force_feature',
                    'triggered_by': triggered_by,
                },
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name,
                source='website'
            )

            return JsonResponse({'success': True, 'action_id': action_id, 'pool_count': entry_count})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =============================================================================
# LFG (Looking For Group) Dashboard
# =============================================================================

@login_required_discord
def guild_lfg(request, guild_id):
    """LFG dashboard."""
    user_guilds = request.session.get('discord_guilds', [])
    guild = next((g for g in user_guilds if str(g.get('id')) == str(guild_id)), None)

    if not guild:
        return redirect('warden_dashboard')

    # Check admin permission
    permissions = int(guild.get('permissions', 0))
    is_admin = (permissions & 0x8) == 0x8 or (permissions & 0x20) == 0x20

    if not is_admin:
        messages.error(request, 'You need Admin or Manage Server permission.')
        return redirect('warden_dashboard')

    try:
        from .db import get_db_session
        from .models import Guild, LFGGame

        with get_db_session() as db:
            guild_db = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild_db.is_premium() if guild_db else False

            games = db.query(LFGGame).filter_by(guild_id=int(guild_id)).all()
            games_data = []
            for game in games:
                games_data.append({
                    'id': game.id,
                    'game_name': game.game_name,
                    'game_short': game.game_short,
                    'igdb_id': game.igdb_id,
                    'cover_url': game.cover_url,
                    'platforms': game.platforms,
                    'is_custom_game': game.is_custom_game,
                    'lfg_channel_id': game.lfg_channel_id,
                    'notify_role_id': game.notify_role_id,
                    'max_group_size': game.max_group_size,
                    'custom_options': game.custom_options,
                    'require_rank': game.require_rank,
                    'rank_label': game.rank_label,
                    'enabled': game.enabled,
                })

        # Get channels and roles from Discord API (mock for now)
        channels = []  # TODO: Fetch from Discord API
        roles = []  # TODO: Fetch from Discord API

        return render(request, 'warden/lfg.html', {
            'guild': guild,
            'games': games_data,
            'channels': channels,
            'roles': roles,
            'is_premium': is_premium,
        })

    except Exception as e:
        messages.error(request, f'Error loading LFG: {e}')
        return redirect('guild_dashboard', guild_id=guild_id)


@require_http_methods(["GET"])
def api_lfg_search(request, guild_id):
    """GET /api/guild/<id>/lfg/search/?q=query - Search IGDB for games."""
    query = request.GET.get('q', '')
    if not query or len(query) < 2:
        return JsonResponse({'error': 'Query too short', 'games': []})

    try:
        import asyncio
        from .utils import igdb

        # Run async search in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            games = loop.run_until_complete(igdb.search_games(query, limit=10))
        finally:
            loop.close()

        games_data = []
        for game in games:
            games_data.append({
                'id': game.id,
                'name': game.name,
                'slug': game.slug,
                'cover_url': game.cover_url,
                'platforms': ', '.join(game.platforms) if game.platforms else None,
                'release_year': game.release_year,
            })

        return JsonResponse({'success': True, 'games': games_data})

    except Exception as e:
        return JsonResponse({'error': str(e), 'games': []})


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_lfg_add(request, guild_id):
    """POST /api/guild/<id>/lfg/add/ - Add a game to LFG."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import Guild, LFGGame

        with get_db_session() as db:
            is_custom = data.get('is_custom', False)

            short_code = data.get('short_code', '').upper().strip()
            if not short_code:
                return JsonResponse({'error': 'Short code required'}, status=400)

            # Check if short code already exists
            existing = db.query(LFGGame).filter(
                LFGGame.guild_id == int(guild_id),
                LFGGame.game_short.ilike(short_code)
            ).first()

            if existing:
                return JsonResponse({'error': f'Short code "{short_code}" already exists'}, status=400)

            # Create game
            game = LFGGame(
                guild_id=int(guild_id),
                game_name=data.get('game_name', 'Unknown Game'),
                game_short=short_code,
                igdb_id=int(data.get('igdb_id')) if data.get('igdb_id') else None,
                cover_url=data.get('cover_url'),
                platforms=data.get('platforms'),
                is_custom_game=is_custom,
                lfg_channel_id=int(data.get('channel_id')) if data.get('channel_id') else None,
                notify_role_id=int(data.get('notify_role_id')) if data.get('notify_role_id') else None,
                max_group_size=int(data.get('max_size', 4)),
            )
            db.add(game)

            return JsonResponse({'success': True, 'game_id': game.id})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
@api_auth_required
def api_lfg_remove(request, guild_id, game_id):
    """DELETE /api/guild/<id>/lfg/<game_id>/ - Remove a game from LFG."""
    try:
        from .db import get_db_session
        from .models import LFGGame

        with get_db_session() as db:
            game = db.query(LFGGame).filter(
                LFGGame.id == int(game_id),
                LFGGame.guild_id == int(guild_id)
            ).first()

            if not game:
                return JsonResponse({'error': 'Game not found'}, status=404)

            db.delete(game)
            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_auth_required
def api_lfg_game_update(request, guild_id, game_id):
    """GET/POST /api/guild/<id>/lfg/<game_id>/update/ - Get or update a game."""
    try:
        from .db import get_db_session
        from .models import LFGGame
        import json

        with get_db_session() as db:
            game = db.query(LFGGame).filter(
                LFGGame.id == int(game_id),
                LFGGame.guild_id == int(guild_id)
            ).first()

            if not game:
                return JsonResponse({'error': 'Game not found'}, status=404)

            if request.method == 'GET':
                return JsonResponse({
                    'id': game.id,
                    'game_name': game.game_name,
                    'game_short': game.game_short,
                    'game_emoji': game.game_emoji,
                    'igdb_id': game.igdb_id,
                    'cover_url': game.cover_url,
                    'platforms': game.platforms,
                    'is_custom_game': game.is_custom_game,
                    'lfg_channel_id': str(game.lfg_channel_id) if game.lfg_channel_id else None,
                    'notify_role_id': str(game.notify_role_id) if game.notify_role_id else None,
                    'custom_options': json.loads(game.custom_options) if game.custom_options else None,
                    'max_group_size': game.max_group_size,
                    'thread_auto_archive_hours': game.thread_auto_archive_hours,
                    'enabled': game.enabled,
                    'require_rank': game.require_rank,
                    'rank_label': game.rank_label,
                    'rank_min': game.rank_min,
                    'rank_max': game.rank_max,
                })

            # POST - update game
            data = json.loads(request.body)

            if 'game_name' in data:
                game.game_name = data['game_name']
            if 'game_emoji' in data:
                game.game_emoji = data['game_emoji']
            if 'lfg_channel_id' in data:
                game.lfg_channel_id = int(data['lfg_channel_id']) if data['lfg_channel_id'] else None
            if 'notify_role_id' in data:
                game.notify_role_id = int(data['notify_role_id']) if data['notify_role_id'] else None
            if 'max_group_size' in data:
                game.max_group_size = int(data['max_group_size'])
            if 'thread_auto_archive_hours' in data:
                game.thread_auto_archive_hours = int(data['thread_auto_archive_hours'])
            if 'enabled' in data:
                game.enabled = bool(data['enabled'])
            if 'require_rank' in data:
                game.require_rank = bool(data['require_rank'])
            if 'rank_label' in data:
                game.rank_label = data['rank_label']
            if 'rank_min' in data:
                game.rank_min = int(data['rank_min'])
            if 'rank_max' in data:
                game.rank_max = int(data['rank_max'])
            if 'custom_options' in data:
                game.custom_options = json.dumps(data['custom_options']) if data['custom_options'] else None

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@api_auth_required
def api_lfg_config(request, guild_id):
    """GET/POST /api/guild/<id>/lfg/config/ - Get or update LFG config (Premium)."""
    try:
        from .db import get_db_session
        from .models import LFGConfig, Guild
        import json
        import time

        with get_db_session() as db:
            # Check premium
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild.is_premium() if guild else False

            config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()

            if request.method == 'GET':
                if not config:
                    return JsonResponse({
                        'is_premium': is_premium,
                        'attendance_tracking_enabled': False,
                        'auto_noshow_hours': 1,
                        'require_confirmation': False,
                        'min_reliability_score': 0,
                        'warn_at_reliability': 50,
                        'auto_blacklist_noshows': 0,
                        'notify_on_noshow': False,
                        'notify_channel_id': None,
                    })

                return JsonResponse({
                    'is_premium': is_premium,
                    'attendance_tracking_enabled': config.attendance_tracking_enabled,
                    'auto_noshow_hours': config.auto_noshow_hours,
                    'require_confirmation': config.require_confirmation,
                    'min_reliability_score': config.min_reliability_score,
                    'warn_at_reliability': config.warn_at_reliability,
                    'auto_blacklist_noshows': config.auto_blacklist_noshows,
                    'notify_on_noshow': config.notify_on_noshow,
                    'notify_channel_id': str(config.notify_channel_id) if config.notify_channel_id else None,
                })

            # POST - update config (requires premium)
            if not is_premium:
                return JsonResponse({'error': 'Premium required'}, status=403)

            data = json.loads(request.body)

            if not config:
                config = LFGConfig(guild_id=int(guild_id))
                db.add(config)

            if 'attendance_tracking_enabled' in data:
                config.attendance_tracking_enabled = bool(data['attendance_tracking_enabled'])
            if 'auto_noshow_hours' in data:
                config.auto_noshow_hours = max(0, int(data['auto_noshow_hours']))
            if 'require_confirmation' in data:
                config.require_confirmation = bool(data['require_confirmation'])
            if 'min_reliability_score' in data:
                config.min_reliability_score = max(0, min(100, int(data['min_reliability_score'])))
            if 'warn_at_reliability' in data:
                config.warn_at_reliability = max(0, min(100, int(data['warn_at_reliability'])))
            if 'auto_blacklist_noshows' in data:
                config.auto_blacklist_noshows = max(0, int(data['auto_blacklist_noshows']))
            if 'notify_on_noshow' in data:
                config.notify_on_noshow = bool(data['notify_on_noshow'])
            if 'notify_channel_id' in data:
                config.notify_channel_id = int(data['notify_channel_id']) if data['notify_channel_id'] else None

            config.updated_at = int(time.time())

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_auth_required
def api_lfg_stats(request, guild_id):
    """GET /api/guild/<id>/lfg/stats/ - Get member stats/leaderboard (Premium)."""
    try:
        from .db import get_db_session
        from .models import LFGMemberStats, Guild

        with get_db_session() as db:
            # Check premium
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild or not guild.is_premium():
                return JsonResponse({'error': 'Premium required', 'members': []}, status=403)

            # Get query params
            sort = request.GET.get('sort', 'reliability')  # reliability, active, flaky
            limit = min(50, int(request.GET.get('limit', 20)))

            query = db.query(LFGMemberStats).filter(
                LFGMemberStats.guild_id == int(guild_id)
            )

            if sort == 'reliability':
                query = query.order_by(LFGMemberStats.reliability_score.desc())
            elif sort == 'active':
                query = query.order_by(LFGMemberStats.total_signups.desc())
            elif sort == 'flaky':
                query = query.order_by(LFGMemberStats.total_no_shows.desc())

            members = query.limit(limit).all()

            return JsonResponse({
                'members': [{
                    'user_id': str(m.user_id),
                    'total_signups': m.total_signups,
                    'total_showed': m.total_showed,
                    'total_no_shows': m.total_no_shows,
                    'total_cancelled': m.total_cancelled,
                    'total_late': m.total_late,
                    'reliability_score': m.reliability_score,
                    'current_show_streak': m.current_show_streak,
                    'best_show_streak': m.best_show_streak,
                    'is_blacklisted': m.is_blacklisted,
                    'blacklist_reason': m.blacklist_reason,
                } for m in members]
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_auth_required
def api_lfg_blacklist(request, guild_id):
    """GET /api/guild/<id>/lfg/blacklist/ - Get blacklisted members (Premium)."""
    try:
        from .db import get_db_session
        from .models import LFGMemberStats, Guild

        with get_db_session() as db:
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild or not guild.is_premium():
                return JsonResponse({'error': 'Premium required', 'members': []}, status=403)

            members = db.query(LFGMemberStats).filter(
                LFGMemberStats.guild_id == int(guild_id),
                LFGMemberStats.is_blacklisted == True
            ).all()

            return JsonResponse({
                'members': [{
                    'user_id': str(m.user_id),
                    'reliability_score': m.reliability_score,
                    'total_no_shows': m.total_no_shows,
                    'blacklist_reason': m.blacklist_reason,
                    'blacklisted_at': m.blacklisted_at,
                    'blacklisted_by': str(m.blacklisted_by) if m.blacklisted_by else None,
                } for m in members]
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@api_auth_required
def api_lfg_blacklist_update(request, guild_id, user_id):
    """POST /api/guild/<id>/lfg/blacklist/<user_id>/ - Update blacklist status (Premium)."""
    try:
        from .db import get_db_session
        from .models import LFGMemberStats, Guild
        import json
        import time

        with get_db_session() as db:
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild or not guild.is_premium():
                return JsonResponse({'error': 'Premium required'}, status=403)

            data = json.loads(request.body)
            action = data.get('action', 'add')  # 'add' or 'remove'
            reason = data.get('reason', '')

            stats = db.query(LFGMemberStats).filter_by(
                guild_id=int(guild_id), user_id=int(user_id)
            ).first()

            if not stats:
                stats = LFGMemberStats(guild_id=int(guild_id), user_id=int(user_id))
                db.add(stats)

            now = int(time.time())

            if action == 'add':
                stats.is_blacklisted = True
                stats.blacklisted_at = now
                stats.blacklist_reason = reason or 'Blacklisted via dashboard'
            else:
                stats.is_blacklisted = False
                stats.blacklisted_at = None
                stats.blacklisted_by = None
                stats.blacklist_reason = None

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
@api_auth_required
def api_lfg_groups(request, guild_id):
    """GET /api/guild/<id>/lfg/groups/ - List active LFG groups."""
    try:
        from .db import get_db_session
        from .models import LFGGroup, LFGGame
        import time

        with get_db_session() as db:
            # Get groups from last 7 days
            week_ago = int(time.time()) - (7 * 24 * 3600)

            groups = db.query(LFGGroup).filter(
                LFGGroup.guild_id == int(guild_id),
                LFGGroup.created_at >= week_ago
            ).order_by(LFGGroup.created_at.desc()).limit(50).all()

            return JsonResponse({
                'groups': [{
                    'id': g.id,
                    'game_id': g.game_id,
                    'thread_id': str(g.thread_id) if g.thread_id else None,
                    'thread_name': g.thread_name,
                    'creator_id': str(g.creator_id),
                    'creator_name': g.creator_name,
                    'scheduled_time': g.scheduled_time,
                    'status': g.status,
                    'member_count': g.member_count,
                    'created_at': g.created_at,
                } for g in groups]
            })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)