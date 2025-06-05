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

    "Enshrouded01": {
        "display_name": "Enshrouded",
        "description": "Soulslike survival with tuned combat, custom altars, and strange terrain. Built for players who like challenge, discovery, and a bit of chaos.",
        "discord_invite": "https://discord.gg/CHHS",
        "steam_link": "https://store.steampowered.com/app/1203620/Enshrouded/",
        "steam_appid": "1203620",
        "connect_pw": "Join the Discord"
    },
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
    {
        "id": "WoW",
        "name": "World of Warcraft",
        "description": "Teaming up with longtime friend Eldronox and his legendary community 'Eternal Legends', we're building a World of Warcraft guild called <Casual Legends>. A chill, zero-drama space for adventurers who play at their own pace..",
        "steam_link": "https://worldofwarcraft.blizzard.com/en-us/",
        "discord_invite": "https://discord.gg/exRgR9YGyy",
        "custom_img": "/static/img/games/wow/dwarf.webp",
        "online": "-",
        "max": "-",
        "link_label": "View Site"
    }
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
        print(f"[ERROR] Could not fetch AMP instances: {e}")
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
                print(f"[WARN] AMP instance {instance_name} error: {e}")
                return safe_amp_fallback(instance_name)

    print(f"[INFO] AMP instance {instance_name} not found — using fallback.")
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
                print("[DEBUG] Raw Dune Activity:", raw)

                # Safely cast integers
                dune_data["total"] = int(raw["total"]) if str(raw.get("total", "")).isdigit() else "-"
                dune_data["online"] = int(raw["online"]) if str(raw.get("online", "")).isdigit() else "-"
                dune_data["active"] = int(raw["active"]) if str(raw.get("active", "")).isdigit() else "-"
        except Exception as e:
            print(f"[DUNE PAGE] Failed to load activity data: {e}")

    print("[DEBUG] Final dune_data:", dune_data)
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
                print("[DEBUG] Raw Pantheon Activity:", raw)

                # Safely cast integers
                pantheon_data["total"] = int(raw["total"]) if str(raw.get("total", "")).isdigit() else "-"
                pantheon_data["online"] = int(raw["online"]) if str(raw.get("online", "")).isdigit() else "-"
                pantheon_data["active"] = int(raw["active"]) if str(raw.get("active", "")).isdigit() else "-"
        except Exception as e:
            print(f"[PANTHEON PAGE] Failed to load activity data: {e}")

    print("[DEBUG] Final pantheon_data:", pantheon_data)
    return render(request, "pantheon.html", {
        "pantheon_activity": pantheon_data
    })

def wow_page(request):
    wow_data = {
        "total": "-",
        "online": "-",
        "active": "-"
    }

    if DISCORD_ACTIVITY_FILE.exists():
        try:
            with DISCORD_ACTIVITY_FILE.open("r") as f:
                all_activity = json.load(f)
                raw = all_activity.get("WoW", {})
                print("[DEBUG] Raw WoW Activity:", raw)

                # Safely cast integers
                wow_data["total"] = int(raw["total"]) if str(raw.get("total", "")).isdigit() else "-"
                wow_data["online"] = int(raw["online"]) if str(raw.get("online", "")).isdigit() else "-"
                wow_data["active"] = int(raw["active"]) if str(raw.get("active", "")).isdigit() else "-"
        except Exception as e:
            print(f"[WoW PAGE] Failed to load activity data: {e}")

    print("[DEBUG] Final wow_data:", wow_data)
    return render(request, "wow.html", {
        "wow_activity": wow_data
    })




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