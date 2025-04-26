def home(request):
    return render(request, 'index.html')

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from dotenv import load_dotenv
import os
import asyncio
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
    "CasualHeroes-Conan01": {
        "display_name": "Conan Exiles",
        "description": "PvE meets PvP in a fully modded world. Let the chaos rain — builders and devs welcome in the Exiled Lands. LFM Devs!",
        "discord_invite": "https://discord.gg/S4XkS58HTq",
        "steam_link": "https://store.steampowered.com/app/440900/Conan_Exiles/",
        "steam_appid": "440900",
        "connect_pw": "No Password"
    },

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
        "description": "Soulslike combat, 255 altars, and modding as soon as it drops. Casual Heroes is building the wildest Enshrouded server yet. LFM devs.",
        "discord_invite": "https://discord.gg/YAFF4dfEWz",
        "steam_link": "https://store.steampowered.com/app/1203620/Enshrouded/",
        "steam_appid": "1203620",
        "connect_pw": "Join the Discord"
    },
    "CasualHeroes-Vrising01": {
        "display_name": "V Rising",
        "description": "Rise with us in a gothic, modded world. We're expanding fast, castle building, PvP, and dev spots open for those ready to reshape Vardoran. LFM Devs!",
        "discord_invite": "https://discord.gg/QBaxdqNDQH",
        "steam_link": "https://store.steampowered.com/app/1604030/V_Rising/",
        "steam_appid": "1604030",
        "connect_pw": "No Password"
    }
}
# Games tracked through Discord only
DISCORD_GAMES = [
    {
        "id": "Dragonwilds",
        "name": "Dragonwilds",
        "description": "As soon as dedicated servers drop, we’re self-hosting, building custom content, and launching a one-of-a-kind Dragonwilds adventure.",
        "steam_link": "https://store.steampowered.com/app/1374490/RuneScape_Dragonwilds/",
        "discord_invite": "https://discord.gg/WZzTppBgBz",
        "steam_appid": "1374490",
        "custom_img": "/static/img/games/Dragonwilds/dw_static.jpg",
        "online": "-",
        "max": "-",
        "link_label": "View on Steam"
    },
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
    {
        "id": "MHW",
        "name": "Monster Hunter Wilds",
        "description": "From fashion shows to chaotic wild hunts, our Monster Hunter community is growing fast. Whether you're min-maxing DPS or just showing off your best drip, there's a spot at the campfire for you.",
        "steam_link": "https://store.steampowered.com/app/2246340/Monster_Hunter_Wilds/",
        "discord_invite": "https://discord.gg/3rKQptH7Fd",
        "steam_appid": "2246340",
        "online": "-",
        "max": "-",
        "link_label": "View on Steam"
    },
    {
        "id": "PoE2",
        "name": "Path of Exile 2",
        "description": "You’ll always find someone theorycrafting their next crazy build here. Casual Heroes are farming, testing, and helping each other every step of the way.",
        "steam_link": "https://store.steampowered.com/app/2694490/Path_of_Exile_2/",
        "discord_invite": "https://discord.gg/fs9qAkVkxH",
        "steam_appid": "2694490",
        "online": "-",
        "max": "-",
        "link_label": "View on Steam"
    },
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

                ip = game_port.get("externalip") or game_port.get("hostname") or "72.69.139.105"
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

        # 🔥 Ensure name and source
        game["name"] = game.get("name", game["id"])
        game["source"] = "discord"

    all_games = amp_games + DISCORD_GAMES

    return render(request, 'gamesweplay.html', { 'games': all_games })

# Leave this here
def home(request):
    return render(request, 'index.html')

ACTIVITY_FILE = Path("/srv/ch-webserver/shared/activity_data.json")

def get_discord_activity_counts():
    if not ACTIVITY_FILE.exists():
        return {}

    with ACTIVITY_FILE.open("r") as f:
        return json.load(f)
    
def hosting(request):
    return render(request, 'hosting.html')

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

def reviews(request):
    return render(request, 'reviews.html')

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