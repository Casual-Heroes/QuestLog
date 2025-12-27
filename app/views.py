def home(request):
    return render(request, 'index.html')

from django.shortcuts import render
import requests
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.shortcuts import redirect, render
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv
import os
import asyncio
import logging

from ampapi.dataclass import APIParams
from ampapi.bridge import Bridge
from ampapi.controller import AMPControllerInstance
import json
from pathlib import Path
from sqlalchemy import or_, and_
import time
from django_ratelimit.decorators import ratelimit
from casualsite.settings import get_client_ip
from .decorators import validate_json_schema, require_subscription_tier

load_dotenv()

# Configure logger for views
logger = logging.getLogger(__name__)

# Discord bot API configuration
DISCORD_BOT_API_URL = os.getenv('DISCORD_BOT_API_URL', 'http://localhost:8001')
DISCORD_BOT_API_TOKEN = os.getenv('DISCORD_BOT_API_TOKEN', 'development-token')

# Cache for guilds_with_bot to prevent excessive API calls
_guilds_cache = {'data': None, 'timestamp': 0}
GUILDS_CACHE_TTL = 300  # Cache for 5 minutes (300 seconds) to prevent Discord API rate limiting

# LFG Game Limits by Tier
def get_lfg_game_limit(guild):
    """Get LFG game limit based on guild subscription tier."""
    if guild.is_vip or guild.subscription_tier in ['premium', 'Premium']:
        return None  # Unlimited
    elif guild.subscription_tier in ['pro', 'Pro']:
        return 10
    else:  # free tier
        return 5

def get_guilds_with_bot():
    """Get set of guild IDs where the bot is actually installed (queried from bot API with caching)."""
    global _guilds_cache

    # Check if cache is still valid
    current_time = time.time()
    if _guilds_cache['data'] is not None and (current_time - _guilds_cache['timestamp']) < GUILDS_CACHE_TTL:
        return _guilds_cache['data']

    # Cache expired or empty, fetch fresh data
    guilds_with_bot = set()
    try:
        import requests
        response = requests.get(
            f'{DISCORD_BOT_API_URL}/api/guilds',
            headers={'Authorization': f'Bearer {DISCORD_BOT_API_TOKEN}'},
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            guilds_with_bot = set(data.get('guild_ids', []))
        else:
            logger.warning(f"Failed to get guild list from bot API: {response.status_code}")
            # Fallback to database check if API fails
            from .db import get_db_session
            from .models import Guild as GuildModel
            with get_db_session() as db:
                installed_guilds = db.query(GuildModel.guild_id).all()
                guilds_with_bot = {str(g.guild_id) for g in installed_guilds}
    except Exception as e:
        logger.error(f"Error checking installed guilds from API: {e}", exc_info=True)
        # Fallback to database check
        try:
            from .db import get_db_session
            from .models import Guild as GuildModel
            with get_db_session() as db:
                installed_guilds = db.query(GuildModel.guild_id).all()
                guilds_with_bot = {str(g.guild_id) for g in installed_guilds}
        except Exception as fallback_error:
            logger.error(f"Database fallback also failed: {fallback_error}", exc_info=True)

    # Update cache
    _guilds_cache['data'] = guilds_with_bot
    _guilds_cache['timestamp'] = current_time

    return guilds_with_bot

def get_member_guilds(request):
    """Calculate member guilds (guilds where user is member but NOT admin) that have the bot installed."""
    admin_guilds = request.session.get('discord_admin_guilds', [])
    all_guilds = request.session.get('discord_all_guilds', [])
    admin_guild_ids = {str(g['id']) for g in admin_guilds}
    member_guilds = [g for g in all_guilds if str(g['id']) not in admin_guild_ids]

    # Get guilds with bot installed
    guilds_with_bot = get_guilds_with_bot()

    # Only return member guilds where bot is installed
    return [g for g in member_guilds if str(g['id']) in guilds_with_bot]

def add_has_bot_flag(guilds):
    """Add 'has_bot' flag to each guild dict."""
    guilds_with_bot = get_guilds_with_bot()
    for guild in guilds:
        guild_id_str = str(guild['id'])
        guild['has_bot'] = guild_id_str in guilds_with_bot
    return guilds

def check_lfg_game_limit(db, guild_id, guild):
    """Check if guild has reached their LFG game limit. Returns (can_add, current_count, limit)."""
    from .models import LFGGame

    limit = get_lfg_game_limit(guild)
    if limit is None:
        return (True, None, None)  # Unlimited

    current_count = db.query(LFGGame).filter_by(guild_id=int(guild_id), enabled=True).count()
    can_add = current_count < limit

    return (can_add, current_count, limit)


def get_discovery_lfg_post_limit(guild):
    """Get Discovery Network LFG monthly posting limit based on guild subscription tier."""
    from .module_utils import has_module_access

    # Complete Suite or LFG Module = Unlimited
    if guild.subscription_tier in ['premium', 'Premium'] or guild.is_vip:
        return None  # Unlimited

    # Check if they have LFG module
    if has_module_access(guild.guild_id, 'lfg'):
        return None  # Unlimited

    # Free tier = 5 posts per month
    return 5


def check_discovery_lfg_post_limit(db, guild_id, guild):
    """
    Check if guild has reached their Discovery Network LFG monthly posting limit.
    Returns (can_post, current_count, limit, reset_date).
    """
    from .models import LFGGroup
    from datetime import datetime, timezone
    from dateutil.relativedelta import relativedelta

    limit = get_discovery_lfg_post_limit(guild)
    if limit is None:
        return (True, None, None, None)  # Unlimited

    # Calculate start of current month (UTC)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_timestamp = int(month_start.timestamp())

    # Calculate next month for reset date
    next_month = month_start + relativedelta(months=1)
    reset_date = next_month.strftime('%B %d, %Y')

    # Count LFG posts created this month in Discovery Network
    # (LFG groups that were created via Discovery Network have member_count >= 0)
    current_count = db.query(LFGGroup).filter(
        LFGGroup.guild_id == int(guild_id),
        LFGGroup.created_at >= month_start_timestamp,
        LFGGroup.thread_id == 0  # Discovery Network posts use placeholder thread_id
    ).count()

    can_post = current_count < limit

    return (can_post, current_count, limit, reset_date)


def get_discovery_game_share_limit(guild):
    """Get Discovery Network game sharing monthly limit based on guild subscription tier."""
    from .module_utils import has_module_access

    # Complete Suite or Discovery Module = Unlimited
    if guild.subscription_tier in ['premium', 'Premium'] or guild.is_vip:
        return None  # Unlimited

    # Check if they have Discovery module
    if has_module_access(guild.guild_id, 'discovery'):
        return None  # Unlimited

    # Free tier = 3 shares per month (matches their 3 search config limit)
    return 3


def check_discovery_game_share_limit(db, guild_id, guild):
    """
    Check if guild has reached their Discovery Network game sharing monthly limit.
    Returns (can_share, current_count, limit, reset_date).
    """
    from .models import AnnouncedGame
    from datetime import datetime, timezone
    from dateutil.relativedelta import relativedelta

    limit = get_discovery_game_share_limit(guild)
    if limit is None:
        return (True, None, None, None)  # Unlimited

    # Calculate start of current month (UTC)
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_timestamp = int(month_start.timestamp())

    # Calculate next month for reset date
    next_month = month_start + relativedelta(months=1)
    reset_date = next_month.strftime('%B %d, %Y')

    # Count game shares created this month
    # (We'll add a 'shared_to_network' flag to track Discovery Network shares)
    current_count = db.query(AnnouncedGame).filter(
        AnnouncedGame.guild_id == int(guild_id),
        AnnouncedGame.announced_at >= month_start_timestamp
    ).count()

    can_share = current_count < limit

    return (can_share, current_count, limit, reset_date)


class DiscordBotSession:
    """Wrapper for making Discord API calls with bot token"""

    def __init__(self, base_url='https://discord.com/api/v10'):
        self.base_url = base_url
        bot_token = os.getenv('DISCORD_BOT_TOKEN')
        if not bot_token or bot_token == 'your_bot_token_here':
            self.headers = None
        else:
            self.headers = {'Authorization': f'Bot {bot_token}'}

    def get(self, path, **kwargs):
        """Make GET request to Discord API"""
        if not self.headers:
            # Return a mock response with 401 status if no token
            class MockResponse:
                status_code = 401
                text = "Bot token not configured"
                def json(self):
                    return {}
            return MockResponse()

        url = f"{self.base_url}{path}"
        return requests.get(url, headers=self.headers, **kwargs)

    def post(self, path, **kwargs):
        """Make POST request to Discord API"""
        if not self.headers:
            # Return a mock response with 401 status if no token
            class MockResponse:
                status_code = 401
                text = "Bot token not configured"
                def json(self):
                    return {}
            return MockResponse()

        url = f"{self.base_url}{path}"
        return requests.post(url, headers=self.headers, **kwargs)

    def put(self, path, **kwargs):
        """Make PUT request to Discord API"""
        if not self.headers:
            class MockResponse:
                status_code = 401
                text = "Bot token not configured"
                def json(self):
                    return {}
            return MockResponse()

        url = f"{self.base_url}{path}"
        return requests.put(url, headers=self.headers, **kwargs)

    def patch(self, path, **kwargs):
        """Make PATCH request to Discord API"""
        if not self.headers:
            class MockResponse:
                status_code = 401
                text = "Bot token not configured"
                def json(self):
                    return {}
            return MockResponse()

        url = f"{self.base_url}{path}"
        return requests.patch(url, headers=self.headers, **kwargs)

    def delete(self, path, **kwargs):
        """Make DELETE request to Discord API"""
        if not self.headers:
            class MockResponse:
                status_code = 401
                text = "Bot token not configured"
                def json(self):
                    return {}
            return MockResponse()

        url = f"{self.base_url}{path}"
        return requests.delete(url, headers=self.headers, **kwargs)


def get_bot_session(guild_id):
    """
    Get a Discord bot API session for making requests.
    Returns None if bot token is not configured.
    """
    bot_token = os.getenv('DISCORD_BOT_TOKEN')
    if not bot_token or bot_token == 'your_bot_token_here':
        logger.warning(f"DISCORD_BOT_TOKEN not configured for guild {guild_id}")
        return None

    return DiscordBotSession()


def check_lfg_manager_role(guild_id, user_id):
    """
    Check if a user has the "LFG Manager" role with required permissions.

    The LFG Manager role must have both:
    - CREATE_EVENTS permission (bit 44)
    - MANAGE_EVENTS permission (bit 33)

    Args:
        guild_id: Discord guild ID
        user_id: Discord user ID

    Returns:
        bool: True if user has valid LFG Manager role, False otherwise
    """
    if not user_id:
        return False

    try:
        import requests

        bot_token = os.getenv('DISCORD_BOT_TOKEN')
        if not bot_token:
            return False

        # Get guild roles from cache (no Discord API call!)
        from .discord_resources import get_guild_roles, get_guild_member

        roles = get_guild_roles(str(guild_id))

        lfg_manager_role_id = None
        for role in roles:
            if role.get('name') == 'LFG Manager':
                # Verify role has both CREATE_EVENTS and MANAGE_EVENTS permissions
                role_permissions = int(role.get('permissions', 0))
                # CREATE_EVENTS = 1 << 44 (17592186044416), MANAGE_EVENTS = 1 << 33 (8589934592)
                has_create = (role_permissions & (1 << 44)) != 0
                has_manage = (role_permissions & (1 << 33)) != 0
                if has_create and has_manage:
                    lfg_manager_role_id = role.get('id')
                break

        # Check if user has the LFG Manager role (from cache, no API call!)
        if lfg_manager_role_id:
            member_data = get_guild_member(str(guild_id), str(user_id))
            if member_data:
                member_roles = member_data.get('roles', [])
                if str(lfg_manager_role_id) in member_roles:
                    return True

    except Exception as e:
        logger.error(f"Error checking LFG Manager role: {e}", exc_info=True)

    return False


def log_lfg_audit(db, guild_id, group_id, action, actor_id, actor_name,
                  field_changed=None, old_value=None, new_value=None,
                  group_name=None, game_name=None):
    """
    Create an audit log entry for LFG group changes.

    Args:
        db: Database session
        guild_id: Discord guild ID
        group_id: LFG group ID (can be None for deletions after commit)
        action: Action performed ('create', 'update', 'delete')
        actor_id: Discord user ID who performed the action
        actor_name: Discord username
        field_changed: Which field was changed (for updates)
        old_value: Previous value (will be JSON encoded if complex type)
        new_value: New value (will be JSON encoded if complex type)
        group_name: Thread/group name for context
        game_name: Game name for context
    """
    try:
        from .models import LFGGroupAuditLog

        # Convert complex values to JSON strings
        if old_value is not None and not isinstance(old_value, str):
            old_value = json.dumps(old_value)
        if new_value is not None and not isinstance(new_value, str):
            new_value = json.dumps(new_value)

        audit_entry = LFGGroupAuditLog(
            guild_id=int(guild_id),
            group_id=group_id,
            action=action,
            actor_id=int(actor_id),
            actor_name=actor_name,
            field_changed=field_changed,
            old_value=old_value,
            new_value=new_value,
            group_name=group_name,
            game_name=game_name
        )
        db.add(audit_entry)
        # Note: Caller is responsible for committing the transaction

    except Exception as e:
        logger.error(f"Error creating audit log entry: {e}", exc_info=True)


def send_lfg_browser_notification(guild_id, lfg_config, notification_type, embed_data):
    """
    Send LFG Browser notification to configured channel and/or webhook.

    Args:
        guild_id: Discord guild ID
        lfg_config: LFGConfig instance with notification settings
        notification_type: Type of notification ('create', 'update', 'delete', 'join', 'leave')
        embed_data: Dict with embed fields (title, description, color, fields, etc.)
    """
    try:
        import requests

        # Check if this notification type is enabled
        notification_enabled = {
            'create': lfg_config.notify_on_group_create,
            'update': lfg_config.notify_on_group_update,
            'delete': lfg_config.notify_on_group_delete,
            'join': lfg_config.notify_on_member_join,
            'leave': lfg_config.notify_on_member_leave,
        }.get(notification_type, False)

        if not notification_enabled:
            return

        # Build embed
        embed = {
            'title': embed_data.get('title', 'LFG Group Update'),
            'description': embed_data.get('description', ''),
            'color': embed_data.get('color', 0x5865F2),
            'fields': embed_data.get('fields', []),
            'timestamp': embed_data.get('timestamp'),
            'footer': embed_data.get('footer'),
        }

        # Send to channel if configured
        if lfg_config.browser_notify_channel_id:
            bot_session = get_bot_session(guild_id)
            if bot_session:
                try:
                    # For group creation, queue bot action to create thread with interactive view
                    if notification_type == 'create' and embed_data.get('group_id'):
                        from .models import PendingAction, ActionType, ActionStatus
                        from .db import get_db_session as get_db
                        import time as time_lib

                        # Queue action for bot to create thread with interactive components
                        with get_db() as db_session:
                            action = PendingAction(
                                guild_id=int(guild_id),
                                action_type=ActionType.LFG_THREAD_CREATE,
                                payload=json.dumps({
                                    'group_id': embed_data.get('group_id'),
                                    'channel_id': str(lfg_config.browser_notify_channel_id)
                                }),
                                status=ActionStatus.PENDING,
                                priority=1,  # High priority
                                created_at=int(time_lib.time())
                            )
                            db_session.add(action)
                            db_session.flush()
                            logger.info(f"Queued LFG thread creation action for group {embed_data.get('group_id')}")
                    else:
                        # For other notifications, just post to channel
                        response = bot_session.post(
                            f'/channels/{lfg_config.browser_notify_channel_id}/messages',
                            json={'embeds': [embed]}
                        )
                        if response.status_code != 200:
                            logger.warning(f"Failed to send LFG notification to channel: {response.status_code}")
                except Exception as e:
                    logger.error(f"Error sending LFG channel notification: {e}")

        # Send to webhook if configured
        if lfg_config.webhook_url:
            try:
                response = requests.post(
                    lfg_config.webhook_url,
                    json={'embeds': [embed]},
                    timeout=5
                )
                if response.status_code not in [200, 204]:
                    logger.warning(f"Failed to send LFG webhook notification: {response.status_code}")
            except Exception as e:
                logger.error(f"Error sending LFG webhook notification: {e}")

    except Exception as e:
        logger.error(f"Error in send_lfg_browser_notification: {e}", exc_info=True)


def send_lfg_webhook_notification(webhook_url, embed_data):
    """
    Send LFG notification to a webhook.

    Args:
        webhook_url: Discord webhook URL
        embed_data: Dict with embed fields
    """
    try:
        import requests

        # Build Discord embed
        embed = {
            'title': embed_data.get('title', 'LFG Group'),
            'description': embed_data.get('description', ''),
            'color': embed_data.get('color', 0x5865F2),
            'fields': embed_data.get('fields', []),
        }

        if embed_data.get('footer'):
            embed['footer'] = embed_data['footer']

        response = requests.post(
            webhook_url,
            json={'embeds': [embed]},
            timeout=5
        )
        if response.status_code not in [200, 204]:
            logger.warning(f"Failed to send LFG webhook notification: {response.status_code}")
    except Exception as e:
        logger.error(f"Error sending LFG webhook notification: {e}")


def send_lfg_browser_dm(guild_id, user_id, embed_data):
    """
    Send a DM to a user about an LFG Browser event.

    Args:
        guild_id: Discord guild ID (for bot session)
        user_id: Discord user ID to DM
        embed_data: Dict with embed fields

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        bot_session = get_bot_session(guild_id)
        if not bot_session:
            return False

        # Create DM channel
        dm_response = bot_session.post('/users/@me/channels', json={'recipient_id': str(user_id)})
        if dm_response.status_code != 200:
            logger.warning(f"Failed to create DM channel for user {user_id}: {dm_response.status_code}")
            return False

        dm_channel = dm_response.json()
        dm_channel_id = dm_channel.get('id')

        if not dm_channel_id:
            return False

        # Build embed
        embed = {
            'title': embed_data.get('title', 'LFG Group Update'),
            'description': embed_data.get('description', ''),
            'color': embed_data.get('color', 0x5865F2),
            'fields': embed_data.get('fields', []),
            'timestamp': embed_data.get('timestamp'),
            'footer': embed_data.get('footer', {'text': 'LFG Browser'}),
        }

        # Send DM
        msg_response = bot_session.post(f'/channels/{dm_channel_id}/messages', json={'embeds': [embed]})
        if msg_response.status_code != 200:
            logger.warning(f"Failed to send DM to user {user_id}: {msg_response.status_code}")
            return False

        return True

    except Exception as e:
        logger.error(f"Error sending LFG Browser DM to {user_id}: {e}")
        return False


def send_lfg_browser_dms(guild_id, user_ids, embed_data):
    """
    Send DMs to multiple users about an LFG Browser event.

    Args:
        guild_id: Discord guild ID
        user_ids: List of Discord user IDs
        embed_data: Dict with embed fields

    Returns:
        int: Number of successful DMs sent
    """
    success_count = 0
    for user_id in user_ids:
        if send_lfg_browser_dm(guild_id, user_id, embed_data):
            success_count += 1
    return success_count


# ============================================================================
# Bulk Operation Rate Limiting Helper Functions
# ============================================================================

def get_tier_limits(guild_record):
    """
    Get daily and per-operation limits based on guild subscription tier.
    Returns: (max_items_per_operation, max_items_per_day)

    - Free: 6 items per operation, 6 total per day
    - Pro: 10 items per operation, 10 total per day
    - Premium/VIP/Engagement Module: Unlimited
    """
    from .models import SubscriptionTier
    from .module_utils import has_module_access

    # Check if guild has Engagement Module (grants unlimited bulk operations)
    if has_module_access(guild_record.guild_id, 'engagement'):
        return (None, None)  # Unlimited

    if guild_record.is_vip or guild_record.subscription_tier == SubscriptionTier.PREMIUM.value:
        return (None, None)  # Unlimited
    elif guild_record.subscription_tier == SubscriptionTier.PRO.value:
        return (10, 10)
    else:  # Free tier
        return (6, 6)


def check_daily_bulk_limit(guild_id, operation_category, items_count, guild_record):
    """
    Check if guild has exceeded daily bulk operation limit.
    Returns: (allowed: bool, error_message: str or None, usage_info: dict)
    """
    from .db import get_db_session
    from .models import DailyBulkUsage
    from datetime import datetime

    max_per_op, max_per_day = get_tier_limits(guild_record)

    # Premium/VIP has no limits
    if max_per_op is None:
        return (True, None, {'tier': 'premium', 'unlimited': True})

    # Check per-operation limit first
    if items_count > max_per_op:
        tier_name = 'Pro' if max_per_op == 10 else 'Free'
        return (False, f'{tier_name} tier limited to {max_per_op} items per operation. You have {items_count} items.', None)

    # Check daily limit
    today = int(datetime.now().strftime('%Y%m%d'))

    with get_db_session() as db:
        usage = db.query(DailyBulkUsage).filter_by(
            guild_id=int(guild_id),
            date=today,
            operation_category=operation_category
        ).first()

        current_usage = usage.items_processed if usage else 0

        if current_usage + items_count > max_per_day:
            tier_name = 'Pro' if max_per_day == 10 else 'Free'
            return (
                False,
                f'{tier_name} tier limited to {max_per_day} items per day. You have used {current_usage}/{max_per_day} today. Upgrade to Premium for unlimited operations.',
                {'current_usage': current_usage, 'max_per_day': max_per_day, 'requested': items_count}
            )

        return (True, None, {'current_usage': current_usage, 'max_per_day': max_per_day, 'remaining': max_per_day - current_usage - items_count})


def record_bulk_usage(guild_id, operation_category, items_count):
    """
    Record bulk operation usage for daily tracking.
    """
    from .db import get_db_session
    from .models import DailyBulkUsage
    from datetime import datetime
    from sqlalchemy import func

    today = int(datetime.now().strftime('%Y%m%d'))
    current_time = int(time.time())

    with get_db_session() as db:
        usage = db.query(DailyBulkUsage).filter_by(
            guild_id=int(guild_id),
            date=today,
            operation_category=operation_category
        ).first()

        if usage:
            usage.items_processed += items_count
            usage.operations_count += 1
            usage.last_operation_at = current_time
        else:
            usage = DailyBulkUsage(
                guild_id=int(guild_id),
                date=today,
                operation_category=operation_category,
                items_processed=items_count,
                operations_count=1,
                first_operation_at=current_time,
                last_operation_at=current_time
            )
            db.add(usage)


DISCORD_ACTIVITY_FILE = Path("/srv/ch-webserver/gamingactivity/activity_data.json")

def get_discord_activity():
    if DISCORD_ACTIVITY_FILE.exists():
        with open(DISCORD_ACTIVITY_FILE, "r") as f:
            return json.load(f)
    return {}


# Games tracked through AMP
STATIC_GAME_INFO = {
    "CH-7DTD01": {
        "display_name": "Dynamic Horde Protocol (PvE)",
        "description": "A custom survival world where biomes bite back. Bots spawn threats, buffs twist the rules, nothing is predictable, and that’s the point.",
        "discord_invite": "https://discord.gg/ECwJWppSjQ",
        "steam_link": "https://store.steampowered.com/app/251570/7_Days_to_Die/",
        "steam_appid": "251570",
        "connect_pw": "Join our Discord to gain access!"
    },
    "CH-Icarus01": {
        "display_name": "Prospectors Lounge",
        "description": "Custom server, No Lifing is Optional",
        "discord_invite": "https://discord.gg/ECwJWppSjQ",
        "steam_link": "https://store.steampowered.com/app/1149460/ICARUS/",
        "steam_appid": "1149460",
        "connect_pw": "Join our Discord to gain access!"
    },
    "CH-Palworld01": {
        "display_name": "Pal Sanctuary",
        "description": "Where we catch Pals and ignore responsibilities together!",
        "discord_invite": "https://discord.gg/ECwJWppSjQ",
        "steam_link": "https://store.steampowered.com/app/1623730/Palworld/",
        "steam_appid": "1623730",
        "connect_pw": "Join our Discord to gain access!"
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

    # "Enshrouded01": {
    #     "display_name": "Enshrouded",
    #     "description": "Soulslike survival with tuned combat, custom altars, and strange terrain. Built for players who like challenge, discovery, and a bit of chaos.",
    #     "discord_invite": "https://discord.gg/CHHS",
    #     "steam_link": "https://store.steampowered.com/app/1203620/Enshrouded/",
    #     "steam_appid": "1203620",
    #     "connect_pw": "Join the Discord"
    # },
    # "CasualHeroes-Vrising01": {
    #     "display_name": "V Rising",
    #     "description": "Modded gothic survival with PvP and random preset days, castle building, and a world that rewards planning over panic. Vardoran’s waiting, Rise. Bite. Build.",
    #     "discord_invite": "https://discord.gg/CHHS",
    #     "steam_link": "https://store.steampowered.com/app/1604030/V_Rising/",
    #     "steam_appid": "1604030",
    #     "connect_pw": "No Password"
    # }
}
# Games tracked through Discord only
DISCORD_GAMES = [
    #     {
    #     "id": "Dune",
    #     "name": "Dune: Awakening",
    #     "description": "The premier casual guild in the Dune uninverse. Chill dungeon runs, late-night banter, and a crew that’s always online. Whether you're new or a raiding vet, Casual Heroes has a spot for you.",
    #     "guild_page": "https://casual-heroes.com/dune/",
    #     "steam_link": "https://store.steampowered.com/app/1172710/Dune_Awakening/",
    #     "discord_invite": "https://discord.gg/jAJvykZvej",
    #     "steam_appid": "1172710",
    #     "online": "-",
    #     "max": "-",
    #     "link_label": "View on Steam"
    # },
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
    # {
    #     "id": "Pantheon",
    #     "name": "Pantheon: Rise of the Fallen",
    #     "description": "The premier casual guild in the Pantheon world. Chill dungeon runs, late-night banter, and a crew that’s always online. Whether you're new or a raiding vet, Casual Heroes has a spot for you.",
    #     "steam_link": "https://store.steampowered.com/app/3107230/Pantheon_Rise_of_the_Fallen/",
    #     "discord_invite": "https://discord.gg/REHJrygu64",
    #     "steam_appid": "3107230",
    #     "online": "-",
    #     "max": "-",
    #     "link_label": "View on Steam"
    # },
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

# ============================================
# AMP Instance Data Cache (PERSISTENT - Industry Standard)
# ============================================
# Uses persistent file cache system (survives restarts)
# Same approach as Discord caching for consistency
#
# ⚙️ CACHE CONFIGURATION - Adjust this to control how often AMP API is called
# Lower value = more real-time updates, but more API calls
# Higher value = fewer API calls, but slower to show status changes
#
AMP_CACHE_TTL = 60  # 60 seconds (1 minute) - Good balance for game server status
#
# Common values:
#   60   = 1 minute  (very responsive, good for game servers)
#   300  = 5 minutes (good balance)
#   600  = 10 minutes (slower updates, lower API usage)
#   1800 = 30 minutes (slow updates, minimal API usage)
#   3600 = 60 minutes (very slow updates, very low API usage)

def get_cached_instance_data(instance_name):
    """
    Get cached AMP instance data using persistent cache.

    Returns cached data if valid, None if expired or not found.
    """
    from .discord_cache import get_cache

    cache = get_cache()
    cache_key = f"amp_instance:{instance_name}"

    cached = cache.get(cache_key)
    if cached is not None:
        logger.info(f"AMP cache HIT for {instance_name}")
        return cached

    logger.debug(f"AMP cache MISS for {instance_name}")
    return None

def set_cached_instance_data(instance_name, data):
    """
    Store AMP instance data in persistent cache with TTL.

    Cache survives Django restarts.
    """
    from .discord_cache import get_cache

    cache = get_cache()
    cache_key = f"amp_instance:{instance_name}"

    cache.set(cache_key, data, ttl=AMP_CACHE_TTL)
    logger.info(f"Cached AMP data for {instance_name} (TTL: {AMP_CACHE_TTL}s)")

def clear_amp_cache(instance_name=None):
    """
    Clear AMP cache for a specific instance or all instances.

    Args:
        instance_name: Specific instance to clear, or None to clear all

    Returns:
        True if cache was cleared
    """
    from .discord_cache import get_cache

    cache = get_cache()

    if instance_name:
        cache_key = f"amp_instance:{instance_name}"
        cache.delete(cache_key)
        logger.info(f"Cleared AMP cache for {instance_name}")
        return True
    else:
        # Clear all AMP instance caches
        # Note: This requires iterating through known instances
        from .views import STATIC_GAME_INFO
        for name in STATIC_GAME_INFO.keys():
            cache.delete(f"amp_instance:{name}")
        logger.info("Cleared all AMP instance caches")
        return True

async def fetch_instance_data(instance_name):
    # Check cache first
    cached_data = get_cached_instance_data(instance_name)
    if cached_data:
        return cached_data
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

                # Filter out internal ports and non-game ports (SFTP, etc.)
                valid_ports = [
                    p for p in ports
                    if not p.get("internalonly", False)
                    and p.get("port") is not None
                    and "sftp" not in p.get("name", "").lower()  # Exclude SFTP ports
                ]

                # Preferred port names (in order of preference)
                # Different games use different naming conventions in AMP
                preferred_order = [
                    "server and steam port",  # 7 Days to Die
                    "game port",              # Most games
                    "game and mods port",     # Some games
                    "query port",             # Fallback for some games
                ]

                game_port = next(
                    (p for name in preferred_order for p in valid_ports if name.lower() in p.get("name", "").lower()),
                    None
                )

                # If no preferred port found, use the first valid port
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

                # Build the data object
                data = {
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

                # Cache the successful result
                set_cached_instance_data(instance_name, data)
                return data

            except Exception as e:
                logger.warning(f"AMP instance {instance_name} error: {e}")
                fallback = safe_amp_fallback(instance_name)
                # Cache fallback data too to prevent repeated failures
                set_cached_instance_data(instance_name, fallback)
                return fallback

    logger.info(f"AMP instance {instance_name} not found — using fallback.")
    fallback = safe_amp_fallback(instance_name)
    # Cache fallback data to prevent repeated lookups
    set_cached_instance_data(instance_name, fallback)
    return fallback


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
    # enshrouded_instance = asyncio.run(fetch_instance_data("Enshrouded01"))

    return render(request, 'enshrouded.html', {
        # "enshrouded_instance": enshrouded_instance
    })

def vrising(request):
    # vrising_instance = asyncio.run(fetch_instance_data("CasualHeroes-Vrising01"))

    return render(request, 'vrising.html', {
        # "vrising_instance": vrising_instance
    })

def palworld(request):
    palworld_instance = asyncio.run(fetch_instance_data("CH-Palworld01"))

    return render(request, 'palworld.html', {
        "palworld_instance": palworld_instance
    })

def icarus(request):
    icarus_instance = asyncio.run(fetch_instance_data("CH-Icarus01"))

    return render(request, 'icarus.html', {
        "icarus_instance": icarus_instance
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

def questlog_overview(request):
    return render(request, 'questlog_overview.html')

def questlog_login(request):
    """Redirect to QuestLog dashboard with Discord OAuth"""
    import secrets
    from .discord_auth import get_discord_login_url

    # Check if already logged in
    if request.session.get('discord_user'):
        # Already authenticated, redirect directly to dashboard
        return redirect('https://dashboard.casual-heroes.com/questlog/')

    # Generate a state token for CSRF protection
    state = secrets.token_urlsafe(32)
    request.session['discord_oauth_state'] = state

    # Set the next URL to the dashboard subdomain
    request.session['discord_login_next'] = 'https://dashboard.casual-heroes.com/questlog/'

    # Force session save before OAuth redirect
    request.session.modified = True
    request.session.save()

    # Use the existing Discord OAuth login URL generator
    login_url = get_discord_login_url(state=state)
    return redirect(login_url)

def creator_of_the_month_page(request):
    """Public page showing all Creator of the Month winners across all guilds."""
    from .db import get_db_session
    from .models import CreatorOfTheMonth, Guild
    import datetime

    with get_db_session() as db:
        # Get all COTM records, newest first
        cotm_records = db.query(CreatorOfTheMonth).order_by(
            CreatorOfTheMonth.year.desc(),
            CreatorOfTheMonth.month.desc()
        ).all()

        # Enrich with guild info
        for record in cotm_records:
            guild = db.query(Guild).filter_by(guild_id=record.guild_id).first()
            record.guild_name = guild.name if guild else f"Guild {record.guild_id}"
            record.guild_icon = guild.icon_url if guild else None

            # Format month name
            record.month_name = datetime.datetime(record.year, record.month, 1).strftime("%B")

        return render(request, 'questlog/creator_of_the_month.html', {
            'cotm_records': cotm_records,
            'page_title': 'Creator of the Month - Hall of Fame'
        })

def creator_of_the_week_page(request):
    """Public page showing all Creator of the Week winners across all guilds."""
    from .db import get_db_session
    from .models import CreatorOfTheWeek, Guild

    with get_db_session() as db:
        # Get all COTW records, newest first
        cotw_records = db.query(CreatorOfTheWeek).order_by(
            CreatorOfTheWeek.year.desc(),
            CreatorOfTheWeek.week.desc()
        ).all()

        # Enrich with guild info
        for record in cotw_records:
            guild = db.query(Guild).filter_by(guild_id=record.guild_id).first()
            record.guild_name = guild.name if guild else f"Guild {record.guild_id}"
            record.guild_icon = guild.icon_url if guild else None

        return render(request, 'questlog/creator_of_the_week.html', {
            'cotw_records': cotw_records,
            'page_title': 'Creator of the Week - Hall of Fame'
        })

@staff_member_required
def analytics_view(request):
    return render(request, 'admin/analytics.html')


# Discord OAuth2 Authentication

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


@ratelimit(key=get_client_ip, rate='10/m', method='GET')
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

        # Store guilds where user has admin permissions
        # 0x8 = Administrator, 0x20 = Manage Server (for trusted mods)
        admin_guilds = [
            {
                'id': g['id'],
                'name': g['name'],
                'icon': g.get('icon'),
                'owner': g.get('owner', False),
                'permissions': g.get('permissions', 0),
            }
            for g in discord_guilds
            if g.get('owner') or (int(g.get('permissions', 0)) & 0x8) or (int(g.get('permissions', 0)) & 0x20)
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
            # Specify backend to avoid "multiple backends" error
            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        except Exception as e:
            # Even if Django user creation fails, session-based auth works
            logger.warning(f"Could not create Django user: {e}")

        messages.success(request, f"Welcome, {discord_user.get('global_name', discord_user['username'])}!")

        # Explicitly save session before redirect to ensure data persists
        # This is critical in multi-worker environments like Gunicorn
        request.session.modified = True
        request.session.save()

        # Redirect to stored 'next' URL or dashboard
        next_url = request.session.pop('discord_login_next', '/dashboard/')

        # Save again after popping discord_login_next
        request.session.modified = True
        request.session.save()

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


@require_http_methods(["POST"])
def discord_refresh_guilds(request):
    """Refresh the user's guild list from Discord without logging out"""
    discord_user = request.session.get('discord_user')

    if not discord_user:
        return JsonResponse({'error': 'Not authenticated with Discord'}, status=401)

    access_token = discord_user.get('access_token')
    if not access_token:
        return JsonResponse({'error': 'No access token found'}, status=401)

    try:
        # Fetch fresh guild list from Discord
        guilds_response = requests.get(
            'https://discord.com/api/users/@me/guilds',
            headers={'Authorization': f'Bearer {access_token}'}
        )

        if guilds_response.status_code != 200:
            logger.error(f"Failed to fetch guilds: {guilds_response.status_code} {guilds_response.text}")
            return JsonResponse({'error': 'Failed to fetch guilds from Discord'}, status=guilds_response.status_code)

        discord_guilds = guilds_response.json()

        # Update admin guilds (same logic as in callback)
        admin_guilds = [
            {
                'id': g['id'],
                'name': g['name'],
                'icon': g.get('icon'),
                'owner': g.get('owner', False),
                'permissions': g.get('permissions', 0),
            }
            for g in discord_guilds
            if g.get('owner') or (int(g.get('permissions', 0)) & 0x8) or (int(g.get('permissions', 0)) & 0x20)
        ]

        # Update session
        request.session['discord_admin_guilds'] = admin_guilds
        request.session['discord_all_guilds'] = [
            {'id': g['id'], 'name': g['name'], 'icon': g.get('icon')}
            for g in discord_guilds
        ]

        request.session.modified = True
        request.session.save()

        logger.info(f"Refreshed guilds for user {discord_user.get('username')}: found {len(admin_guilds)} admin guilds")

        return JsonResponse({
            'success': True,
            'admin_guilds_count': len(admin_guilds),
            'total_guilds_count': len(discord_guilds)
        })

    except Exception as e:
        logger.error(f"Error refreshing guilds: {e}", exc_info=True)
        return JsonResponse({'error': 'An error occurred while refreshing guilds'}, status=500)


def discord_required(view_func):
    """Decorator to require Discord authentication (skips auth for social media crawlers for Open Graph)"""
    def wrapper(request, *args, **kwargs):
        # Allow social media crawlers through without auth for Open Graph meta tags
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        is_crawler = any(bot in user_agent for bot in [
            'facebookexternalhit', 'twitterbot', 'linkedinbot', 'discordbot',
            'slackbot', 'telegrambot', 'whatsapp', 'pinterest', 'bot'
        ])

        # Skip auth check for crawlers - let the view handle Open Graph response
        if is_crawler:
            return view_func(request, *args, **kwargs)

        # Normal auth check for non-crawlers
        if not request.session.get('discord_user'):
            messages.warning(request, "Please log in with Discord to access this page.")
            return redirect(f"/auth/discord/login/?next={request.path}")
        return view_func(request, *args, **kwargs)
    return wrapper


@discord_required
def user_profile(request):
    """User profile page showing Discord account info and connected guilds"""
    import json as json_lib

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])
    all_guilds = request.session.get('discord_all_guilds', [])

    context = {
        'discord_user': discord_user,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'all_guilds': all_guilds,
        'all_guilds_json': json_lib.dumps(all_guilds),  # JSON-encoded for JavaScript
        'guild_count': len(all_guilds),
        'admin_guild_count': len(admin_guilds),
    }
    return render(request, 'auth/profile.html', context)


@discord_required
def questlog_dashboard(request):
    """Main Warden bot dashboard - select a guild to manage"""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    # Add 'has_bot' flag to admin guilds
    admin_guilds = add_has_bot_flag(admin_guilds)

    # Get member guilds (already filtered to only show guilds with bot)
    member_guilds = get_member_guilds(request)

    context = {
        'discord_user': discord_user,
        'admin_guilds': admin_guilds,
        'member_guilds': member_guilds,
        'total_guilds': len(admin_guilds) + len(member_guilds),
        'bot_client_id': os.getenv('DISCORD_CLIENT_ID', ''),
    }
    return render(request, 'questlog/dashboard.html', context)


@discord_required
def guild_dashboard(request, guild_id):
    """Dashboard for a specific guild - shows admin config or member portal based on permissions"""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])
    admin_guilds = add_has_bot_flag(admin_guilds)
    all_guilds = request.session.get('discord_all_guilds', [])

    # Check if user is admin OR member of this guild
    is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)
    guild = next((g for g in all_guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "You are not a member of this server.")
        return redirect('questlog_dashboard')

    # If not admin, show member landing page instead
    if not is_admin:
        return render(request, 'questlog/member_portal.html', {
            'discord_user': discord_user,
            'guild': guild,
            'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
            'member_guilds': get_member_guilds(request),
            'is_admin': False,
        })

    # Fetch feature statuses
    feature_status = {
        'welcome_enabled': False,
        'discovery_enabled': False,
        'creator_discovery_enabled': False,
        'game_discovery_enabled': False,
        'discovery_feature_interval': 3,
        'verification_enabled': False,
    }

    # Initialize metrics
    metrics = {
        'total_members': 0,
        'active_today': 0,
        'engagement_rate': 0,
        'warnings_this_week': 0,
    }

    guild_record = None

    try:
        from .db import get_db_session
        from .models import (
            WelcomeConfig, DiscoveryConfig, VerificationConfig, VerificationType,
            GuildMember, Warning, LevelRole, ReactRole, ChannelStatTracker
        )
        from datetime import datetime, timedelta
        import time

        logger.info(f"[METRICS DEBUG] Loading dashboard for guild {guild_id}")

        with get_db_session() as db:
            # Check welcome messages
            welcome_config = db.query(WelcomeConfig).filter_by(guild_id=int(guild_id)).first()
            if welcome_config:
                feature_status['welcome_enabled'] = welcome_config.enabled
                logger.info(f"[METRICS DEBUG] Welcome: {welcome_config.enabled}")

            # Check discovery
            discovery_config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if discovery_config:
                feature_status['discovery_enabled'] = discovery_config.enabled or discovery_config.game_discovery_enabled
                feature_status['creator_discovery_enabled'] = discovery_config.enabled
                feature_status['game_discovery_enabled'] = discovery_config.game_discovery_enabled
                feature_status['discovery_feature_interval'] = discovery_config.feature_interval_hours
                logger.info(f"[METRICS DEBUG] Discovery - enabled: {discovery_config.enabled}, game_discovery: {discovery_config.game_discovery_enabled}, combined: {feature_status['discovery_enabled']}")
            else:
                logger.info(f"[METRICS DEBUG] No DiscoveryConfig found for guild {guild_id}")

            # Check verification
            verification_config = db.query(VerificationConfig).filter_by(guild_id=int(guild_id)).first()
            if verification_config:
                feature_status['verification_enabled'] = verification_config.verification_type != VerificationType.NONE
                logger.info(f"[METRICS DEBUG] Verification: {feature_status['verification_enabled']}")

            # Calculate metrics from Discord data (cached by bot)
            # Get guild record to access cached Discord stats
            from .models import Guild as GuildModel
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            # Total Members (from Discord, cached by bot)
            metrics['total_members'] = guild_record.member_count if guild_record and guild_record.member_count else 0
            logger.info(f"[METRICS DEBUG] Total members (from Discord cache): {metrics['total_members']}")

            # Active Today = Currently Online (from Discord presence, cached by bot)
            metrics['active_today'] = guild_record.online_count if guild_record and guild_record.online_count else 0
            logger.info(f"[METRICS DEBUG] Currently online: {metrics['active_today']}")

            # Engagement Rate - Based on REAL activity (messages, voice, reactions, media)
            # Count members who were active in last 7 days (check timestamp columns)
            week_start = int(time.time()) - (7 * 86400)  # 7 days ago
            engaged_members = db.query(GuildMember).filter(
                GuildMember.guild_id == int(guild_id),
                GuildMember.is_bot == False,
                or_(
                    GuildMember.last_message_ts >= week_start,
                    GuildMember.last_media_ts >= week_start,
                    GuildMember.last_voice_join_ts >= week_start,
                    GuildMember.last_react_ts >= week_start,
                    GuildMember.last_command_ts >= week_start,
                    GuildMember.last_gaming_ts >= week_start
                )
            ).count()

            if metrics['total_members'] > 0:
                metrics['engagement_rate'] = round((engaged_members / metrics['total_members']) * 100, 1)
            else:
                metrics['engagement_rate'] = 0
            logger.info(f"[METRICS DEBUG] Engagement rate (7-day activity): {metrics['engagement_rate']}% ({engaged_members}/{metrics['total_members']})")

            # Get active members from DB for XP leaderboards (last 24h)
            today_start = int(time.time()) - 86400  # 24 hours ago
            active_members = db.query(GuildMember).filter(
                GuildMember.guild_id == int(guild_id),
                GuildMember.is_bot == False,
                GuildMember.last_active >= today_start
            ).all()

            # Exclude current viewer from leaderboards
            current_user_id = int(discord_user.get('id', 0)) if discord_user.get('id') else None
            eligible_members = [m for m in active_members if m.user_id != current_user_id] if current_user_id else active_members

            # Top XP Earner Today (among active members, excluding viewer)
            if eligible_members:
                top_xp_member = max(eligible_members, key=lambda m: m.xp)
                metrics['top_xp_earner'] = {
                    'name': top_xp_member.display_name or top_xp_member.username or f"User#{top_xp_member.user_id}",
                    'xp': round(top_xp_member.xp, 1)
                }
            else:
                metrics['top_xp_earner'] = None
            logger.info(f"[METRICS DEBUG] Top XP earner: {metrics['top_xp_earner']}")

            # Top Token Holder Today (among active members, excluding viewer)
            if eligible_members:
                top_token_member = max(eligible_members, key=lambda m: m.hero_tokens)
                metrics['top_token_holder'] = {
                    'name': top_token_member.display_name or top_token_member.username or f"User#{top_token_member.user_id}",
                    'tokens': top_token_member.hero_tokens
                }
            else:
                metrics['top_token_holder'] = None
            logger.info(f"[METRICS DEBUG] Top token holder: {metrics['top_token_holder']}")

            # Warnings This Week
            week_start = int(time.time()) - (7 * 86400)  # 7 days ago
            warnings_count = db.query(Warning).filter(
                Warning.guild_id == int(guild_id),
                Warning.issued_at >= week_start
            ).count()
            metrics['warnings_this_week'] = warnings_count
            logger.info(f"[METRICS DEBUG] Warnings this week: {metrics['warnings_this_week']}")

            # Module stats
            metrics['xp_tracked_members'] = metrics['total_members']  # All members tracked
            metrics['level_roles'] = db.query(LevelRole).filter_by(guild_id=int(guild_id)).count()
            metrics['reaction_role_menus'] = db.query(ReactRole).filter_by(guild_id=int(guild_id)).count()
            metrics['member_trackers'] = db.query(ChannelStatTracker).filter_by(guild_id=int(guild_id)).count()

            logger.info(f"[METRICS DEBUG] Module stats - XP: {metrics['xp_tracked_members']}, LevelRoles: {metrics['level_roles']}, ReactionRoles: {metrics['reaction_role_menus']}, Trackers: {metrics['member_trackers']}")
            logger.info(f"[METRICS DEBUG] Final metrics: {metrics}")

    except Exception as e:
        logger.error(f"Could not fetch feature statuses or metrics for guild {guild_id}: {e}", exc_info=True)

    # Get subscription tier info
    is_vip = guild_record.is_vip if guild_record else False
    subscription_tier = guild_record.subscription_tier if guild_record else 'free'
    billing_cycle = guild_record.billing_cycle if guild_record else None

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'member_guilds': get_member_guilds(request),
        'is_admin': is_admin,
        'feature_status': feature_status,
        'metrics': metrics,
        'guild_record': guild_record,
        'is_vip': is_vip,
        'subscription_tier': subscription_tier,
        'billing_cycle': billing_cycle,
        'active_page': 'dashboard',
    }
    return render(request, 'questlog/guild_dashboard.html', context)


@discord_required
def force_sync_guild(request, guild_id):
    """Force an immediate sync of guild stats from Discord via bot API."""
    from django.http import JsonResponse

    try:
        # Call bot API to trigger sync
        bot_api_url = os.getenv('WARDEN_BOT_API_URL', 'http://localhost:8001')
        bot_api_token = os.getenv('DISCORD_BOT_API_TOKEN')
        response = requests.post(
            f'{bot_api_url}/api/sync/{guild_id}',
            headers={'Authorization': f'Bearer {bot_api_token}'},
            timeout=10
        )

        if response.status_code == 200:
            # Invalidate cache so new data loads immediately
            from .discord_resources import invalidate_guild_cache
            invalidate_guild_cache(guild_id)
            return JsonResponse({'success': True, 'message': 'Guild synced successfully'})
        else:
            return JsonResponse({
                'success': False,
                'error': response.json().get('error', 'Unknown error')
            }, status=response.status_code)

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to sync guild {guild_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Failed to connect to bot API'
        }, status=503)


def invalidate_cache(request, guild_id):
    """Invalidate Django cache for a guild (called by bot after auto-sync)."""
    from django.http import JsonResponse
    from .discord_resources import invalidate_guild_cache

    try:
        invalidate_guild_cache(guild_id)
        logger.info(f"Cache invalidated for guild {guild_id} via API")
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Failed to invalidate cache for guild {guild_id}: {e}")
        return JsonResponse({'success': False, 'error': 'An internal error occurred. Please try again later.'}, status=500)


# Flair Store

@discord_required
def flair_store(request, guild_id):
    """Flair store for members to purchase and equip flairs."""
    from django.http import JsonResponse
    from .db import get_db_session
    from .models import GuildMember, Guild as GuildModel, GuildFlair
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    all_guilds = request.session.get('discord_all_guilds', [])
    admin_guilds = request.session.get('discord_admin_guilds', [])

    # Verify user is a member of this guild
    guild = next((g for g in all_guilds if str(g['id']) == str(guild_id)), None)
    if not guild:
        messages.error(request, "You are not a member of this server.")
        return redirect('questlog_dashboard')

    # Handle POST (purchase flair)
    if request.method == 'POST':
        import json
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        # Handle flair removal (no replacement)
        if data.get('remove_flair'):
            try:
                with get_db_session() as db:
                    member = db.query(GuildMember).filter_by(
                        guild_id=int(guild_id),
                        user_id=int(discord_user['id'])
                    ).first()

                    if not member:
                        return JsonResponse({
                            'success': False,
                            'error': 'You are not a member of this server yet. Please interact in Discord first.'
                        }, status=404)

                    # Clear current flair
                    member.flair = None

                    # Add pending action to remove flair roles in Discord
                    from .models import PendingAction, ActionType, ActionStatus
                    action = PendingAction(
                        guild_id=int(guild_id),
                        action_type=ActionType.FLAIR_ASSIGN.value,
                        status=ActionStatus.PENDING.value,
                        payload=json.dumps({
                            'target_user_id': int(discord_user['id']),
                            'flair_name': None  # signals removal
                        }),
                        triggered_by=int(discord_user['id']),
                        triggered_by_name=discord_user.get('username', 'Unknown')
                    )
                    db.add(action)

                    logger.info(f"User {discord_user.get('username')} removed flair in guild {guild_id}")

                    return JsonResponse({
                        'success': True,
                        'message': 'Flair removed. Your Discord roles will update automatically.'
                    })
            except Exception as e:
                logger.error(f"Error removing flair: {e}", exc_info=True)
                return JsonResponse({'success': False, 'error': 'Failed to remove flair'}, status=500)

        flair_name = data.get('flair_name')

        # Look up flair in database
        try:
            with get_db_session() as db:
                flair = db.query(GuildFlair).filter_by(
                    guild_id=int(guild_id),
                    flair_name=flair_name,
                    enabled=True
                ).first()

                if not flair:
                    return JsonResponse({
                        'success': False,
                        'error': 'Flair not found or is disabled'
                    }, status=404)

                # Check if custom flair requires premium
                if flair.flair_type == 'custom':
                    guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
                    is_premium = (guild_record and (
                        guild_record.subscription_tier == 'complete' or guild_record.is_vip
                    ))
                    if not is_premium:
                        return JsonResponse({
                            'success': False,
                            'error': 'Custom flairs require the Complete Suite or Engagement module!'
                        }, status=403)

                cost = flair.cost

        except Exception as e:
            logger.error(f"Error looking up flair: {e}", exc_info=True)
            return JsonResponse({'success': False, 'error': 'Failed to look up flair'}, status=500)

        # Purchase flair
        try:
            with get_db_session() as db:
                member = db.query(GuildMember).filter_by(
                    guild_id=int(guild_id),
                    user_id=int(discord_user['id'])
                ).first()

                if not member:
                    return JsonResponse({
                        'success': False,
                        'error': 'You are not a member of this server yet. Please interact in Discord first.'
                    }, status=404)

                # Check if user already owns this flair
                owned_flairs = []
                if member.owned_flairs:
                    try:
                        owned_flairs = json.loads(member.owned_flairs)
                    except:
                        owned_flairs = []

                already_owned = flair_name in owned_flairs

                # Only charge tokens if not already owned
                if not already_owned:
                    if member.hero_tokens < cost:
                        return JsonResponse({
                            'success': False,
                            'error': f'Insufficient tokens. You need {cost} but only have {member.hero_tokens}.'
                        }, status=400)

                    # Deduct tokens and add to owned flairs
                    if cost > 0:
                        member.hero_tokens -= cost
                    owned_flairs.append(flair_name)
                    member.owned_flairs = json.dumps(owned_flairs)

                # Equip the flair
                member.flair = flair_name

                # Create pending action for bot to assign Discord role
                from .models import PendingAction, ActionType, ActionStatus
                action = PendingAction(
                    guild_id=int(guild_id),
                    action_type=ActionType.FLAIR_ASSIGN.value,
                    status=ActionStatus.PENDING.value,
                    payload=json.dumps({
                        'target_user_id': int(discord_user['id']),
                        'flair_name': flair_name
                    }),
                    triggered_by=int(discord_user['id']),
                    triggered_by_name=discord_user.get('username', 'Unknown')
                )
                db.add(action)

                # Log appropriate action
                action_verb = "equipped" if already_owned else "purchased"
                logger.info(f"User {discord_user['username']} {action_verb} flair {flair_name} in guild {guild_id}")

                # Return appropriate message
                if already_owned:
                    message = f'Switched to {flair_name}! Your Discord role will update automatically.'
                else:
                    message = f'Successfully purchased {flair_name} for {cost} tokens! Your Discord role will update automatically.'

                return JsonResponse({
                    'success': True,
                    'flair': flair_name,
                    'tokens_remaining': member.hero_tokens,
                    'message': message,
                    'already_owned': already_owned
                })

        except Exception as e:
            logger.error(f"Error purchasing flair: {e}", exc_info=True)
            return JsonResponse({
                'success': False,
                'error': 'An error occurred while processing your purchase. Please try again or contact support.'
            }, status=500)

    # GET request - show flair store
    normal_flairs = {}
    seasonal_flairs = {}
    custom_flairs = {}
    current_tokens = 0
    current_flair = None
    owned_flairs = []
    subscription_tier = 'free'
    is_vip = False
    is_premium = False
    is_pro = False
    token_name = "Hero Tokens"  # Default
    token_emoji = ":coin:"      # Default

    try:
        with get_db_session() as db:
            # Get member info
            member = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                user_id=int(discord_user['id'])
            ).first()

            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

            current_tokens = member.hero_tokens if member else 0
            current_flair = member.flair if member else None

            # Get list of owned flairs
            if member and member.owned_flairs:
                try:
                    import json
                    owned_flairs = json.loads(member.owned_flairs)
                except:
                    owned_flairs = []

            subscription_tier = guild_record.subscription_tier if guild_record else 'free'
            is_vip = guild_record.is_vip if guild_record else False
            billing_cycle = guild_record.billing_cycle if guild_record else None
            token_name = guild_record.token_name if guild_record and guild_record.token_name else "Hero Tokens"
            token_emoji = guild_record.token_emoji if guild_record and guild_record.token_emoji else ":coin:"

            # Premium access = Complete tier OR VIP
            is_premium = subscription_tier == 'complete' or is_vip
            # All premium features available in Complete tier
            is_pro = is_premium

            # Load flairs from database
            flairs = db.query(GuildFlair).filter_by(
                guild_id=int(guild_id),
                enabled=True
            ).order_by(
                GuildFlair.flair_type,
                GuildFlair.display_order,
                GuildFlair.id
            ).all()

            # Organize flairs by type
            for flair in flairs:
                if flair.flair_type == 'normal':
                    normal_flairs[flair.flair_name] = flair.cost
                elif flair.flair_type == 'seasonal':
                    seasonal_flairs[flair.flair_name] = flair.cost
                elif flair.flair_type == 'custom':
                    custom_flairs[flair.flair_name] = flair.cost

    except Exception as e:
        logger.error(f"Error loading flair store: {e}", exc_info=True)

    # Check if user has admin permissions for this guild
    is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)

    # Check if guild has engagement module access
    has_engagement_module = has_module_access(guild_id, 'engagement')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,  # Add for sidebar navigation
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': is_admin,
        'normal_flairs': normal_flairs,
        'seasonal_flairs': seasonal_flairs,
        'custom_flairs': custom_flairs,
        'current_tokens': current_tokens,
        'current_flair': current_flair,
        'owned_flairs': owned_flairs,
        'subscription_tier': subscription_tier,
        'is_vip': is_vip,
        'billing_cycle': billing_cycle,
        'is_premium': is_premium,
        'is_pro': is_pro,
        'token_name': token_name,
        'token_emoji': token_emoji,
        'has_engagement_module': has_engagement_module,
        'has_any_module': has_any_module,
        'active_page': 'flair_store',
    }
    return render(request, 'questlog/flair_store.html', context)


# Member Profile
@discord_required
def member_profile(request, guild_id):
    """View member's own profile with XP, tokens, level, and stats."""
    from .db import get_db_session
    from .models import GuildMember, Guild as GuildModel

    discord_user = request.session.get('discord_user', {})
    all_guilds = request.session.get('discord_all_guilds', [])
    admin_guilds = request.session.get('discord_admin_guilds', [])

    # Check if user is member of this guild
    guild = next((g for g in all_guilds if str(g['id']) == str(guild_id)), None)
    if not guild:
        messages.error(request, "You are not a member of this server.")
        return redirect('questlog_dashboard')

    is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)

    # Get member stats from database
    member_stats = None
    guild_record = None
    token_name = "Hero Tokens"
    token_emoji = ":coin:"

    try:
        with get_db_session() as db:
            member = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                user_id=int(discord_user['id'])
            ).first()

            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            token_name = guild_record.token_name if guild_record and guild_record.token_name else "Hero Tokens"
            token_emoji = guild_record.token_emoji if guild_record and guild_record.token_emoji else ":coin:"

            # Build avatar URL
            avatar_url = None
            if discord_user.get('avatar'):
                avatar_url = f"https://cdn.discordapp.com/avatars/{discord_user['id']}/{discord_user['avatar']}.png?size=256"
            else:
                # Default Discord avatar (based on discriminator or user ID)
                discriminator = int(discord_user.get('discriminator', '0'))
                default_num = (discriminator % 5) if discriminator > 0 else (int(discord_user['id']) >> 22) % 6
                avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_num}.png"

            if member:
                member_stats = {
                    'display_name': member.display_name or member.username,
                    'avatar_url': avatar_url,
                    'level': member.level,
                    'xp': member.xp,
                    'tokens': member.hero_tokens,
                    'flair': member.flair,
                    'message_count': member.message_count,
                    'voice_minutes': member.voice_minutes,
                    'reaction_count': member.reaction_count,
                    'media_count': member.media_count,
                }
            else:
                member_stats = {
                    'display_name': discord_user.get('username', 'Unknown'),
                    'avatar_url': avatar_url,
                    'level': 0,
                    'xp': 0,
                    'tokens': 0,
                    'flair': None,
                    'message_count': 0,
                    'voice_minutes': 0,
                    'reaction_count': 0,
                    'media_count': 0,
                }
    except Exception as e:
        logger.error(f"Error loading member profile: {e}", exc_info=True)
        member_stats = {}

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,  # Add for sidebar navigation
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': is_admin,
        'member_stats': member_stats,
        'token_name': token_name,
        'token_emoji': token_emoji,
        'active_page': 'profile',
    }
    return render(request, 'questlog/member_profile.html', context)


# Leaderboards
@discord_required
def guild_leaderboards(request, guild_id):
    """View guild leaderboards for XP, tokens, and activity."""
    from .db import get_db_session
    from .models import GuildMember, Guild as GuildModel

    discord_user = request.session.get('discord_user', {})
    all_guilds = request.session.get('discord_all_guilds', [])
    admin_guilds = request.session.get('discord_admin_guilds', [])

    # Check if user is member of this guild
    guild = next((g for g in all_guilds if str(g['id']) == str(guild_id)), None)
    if not guild:
        messages.error(request, "You are not a member of this server.")
        return redirect('questlog_dashboard')

    is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)

    # Get leaderboards from database
    xp_leaders = []
    token_leaders = []
    message_leaders = []
    token_name = "Hero Tokens"
    token_emoji = ":coin:"

    try:
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            token_name = guild_record.token_name if guild_record and guild_record.token_name else "Hero Tokens"
            token_emoji = guild_record.token_emoji if guild_record and guild_record.token_emoji else ":coin:"

            # Top 10 by XP
            xp_leaders = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                is_bot=False
            ).order_by(GuildMember.xp.desc()).limit(10).all()

            # Top 10 by Tokens
            token_leaders = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                is_bot=False
            ).order_by(GuildMember.hero_tokens.desc()).limit(10).all()

            # Top 10 by Messages
            message_leaders = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                is_bot=False
            ).order_by(GuildMember.message_count.desc()).limit(10).all()

    except Exception as e:
        logger.error(f"Error loading leaderboards: {e}", exc_info=True)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,  # Add for sidebar navigation
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': is_admin,
        'xp_leaders': xp_leaders,
        'token_leaders': token_leaders,
        'message_leaders': message_leaders,
        'token_name': token_name,
        'token_emoji': token_emoji,
        'active_page': 'leaderboards',
    }
    return render(request, 'questlog/leaderboards.html', context)


# Flair Management Dashboard (Premium Feature)

@discord_required
def flair_management(request, guild_id):
    """Flair management page - bulk editor for customizing flairs and prices."""
    from .db import get_db_session
    from .models import Guild as GuildModel
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    # Check premium status
    is_premium = False
    is_vip = False
    subscription_tier = 'free'

    try:
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if guild_record:
                subscription_tier = guild_record.subscription_tier
                is_vip = guild_record.is_vip
                billing_cycle = guild_record.billing_cycle
                is_premium = subscription_tier == 'complete' or is_vip

    except Exception as e:
        logger.warning(f"Could not fetch guild premium status: {e}")

    # Check if guild has engagement module access
    has_engagement_module = has_module_access(guild_id, 'engagement')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,  # User already validated as admin above
        'is_premium': is_premium,
        'is_vip': is_vip,
        'subscription_tier': subscription_tier,
        'billing_cycle': billing_cycle if 'billing_cycle' in locals() else None,
        'has_engagement_module': has_engagement_module,
        'has_any_module': has_any_module,
        'active_page': 'flair_management',
    }
    return render(request, 'questlog/flair_management.html', context)


# Tracker Management Dashboard Page

@discord_required
def guild_trackers(request, guild_id):
    """Manage channel stat trackers for a guild."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

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

    # Check if guild has LFG module access
    has_lfg_module = has_module_access(guild_id, 'lfg')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'trackers': trackers,
        'has_lfg_module': has_lfg_module,
        'has_any_module': has_any_module,
        'active_page': 'trackers',
    }
    return render(request, 'questlog/trackers.html', context)


# Tracker API Endpoints (REST API for AJAX calls)

from django.http import JsonResponse, HttpResponseForbidden, HttpResponseNotFound
import json as json_lib


# PERSISTENT CACHE for Discord guild permissions (industry standard: persistent cache)
_PERMISSION_CACHE_TTL = 14400  # 4 hours cache for permission checks (admin permissions rarely change)

# Rate limit tracking constants (per-user tracking)
_DISCORD_API_RATE_LIMIT_PER_USER = 1  # Max 1 call per user per window (Discord's actual limit)
_RATE_LIMIT_WINDOW = 3  # 3 second window per user to be VERY safe

# Emergency circuit breaker - completely stop API calls if we get too many 429s
_CIRCUIT_BREAKER_THRESHOLD = 5  # After 5 429s in a row
_CIRCUIT_BREAKER_DURATION = 300  # Stop all calls for 5 minutes

def api_auth_required(view_func):
    """
    Check Discord auth and guild admin access for API endpoints.

    ZERO DISCORD API CALLS - Uses session data from OAuth login (industry standard).
    Session data is populated during login and refreshed on re-auth.
    """
    def wrapper(request, guild_id, *args, **kwargs):
        from .discord_cache import get_cache

        cache = get_cache()

        discord_user = request.session.get('discord_user')
        if not discord_user:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        user_id = discord_user.get('id')
        cache_key = f"discord_permission:{user_id}:{guild_id}"

        # Check persistent cache first (4 hour TTL)
        cached = cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Permission cache HIT for user {user_id} guild {guild_id}")
            if not cached['is_admin']:
                return JsonResponse({'error': 'No admin access to this guild'}, status=403)
            return view_func(request, guild_id, *args, **kwargs)

        # Cache MISS: Use session data (populated during OAuth login)
        # This is the industry-standard approach - trust the session data from OAuth
        admin_guilds = request.session.get('discord_admin_guilds', [])
        guild = next((g for g in admin_guilds if str(g['id']) == str(guild_id)), None)

        if not guild:
            # Cache negative result
            cache.set(cache_key, {'is_admin': False}, ttl=_PERMISSION_CACHE_TTL)
            logger.debug(f"Permission cache MISS: User {user_id} has no admin access to guild {guild_id}")
            return JsonResponse({'error': 'No admin access to this guild'}, status=403)

        # Cache positive result
        cache.set(cache_key, {'is_admin': True}, ttl=_PERMISSION_CACHE_TTL)
        logger.debug(f"Permission cache MISS: Cached admin access for user {user_id} guild {guild_id} from session data")
        return view_func(request, guild_id, *args, **kwargs)
    return wrapper


def api_member_auth_required(view_func):
    """Check Discord auth and guild member access for API endpoints."""
    def wrapper(request, guild_id, *args, **kwargs):
        discord_user = request.session.get('discord_user')
        if not discord_user:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        all_guilds = request.session.get('discord_all_guilds', [])
        guild = next((g for g in all_guilds if str(g['id']) == str(guild_id)), None)
        if not guild:
            return JsonResponse({'error': 'No access to this guild'}, status=403)

        return view_func(request, guild_id, *args, **kwargs)
    return wrapper


# Flair Management API Endpoints

@api_auth_required
def api_flair_list(request, guild_id):
    """GET /api/guild/<id>/flairs/ - Get all flairs for a guild."""
    try:
        from .models import GuildFlair
        from .db import get_db_session

        with get_db_session() as db:
            flairs = db.query(GuildFlair).filter_by(
                guild_id=int(guild_id)
            ).order_by(
                GuildFlair.flair_type,
                GuildFlair.display_order,
                GuildFlair.id
            ).all()

            flair_data = [
                {
                    'id': f.id,
                    'flair_name': f.flair_name,
                    'flair_type': f.flair_type,
                    'cost': f.cost,
                    'enabled': f.enabled,
                    'created_by': str(f.created_by) if f.created_by else None,
                    'display_order': f.display_order,
                }
                for f in flairs
            ]

            return JsonResponse({
                'success': True,
                'flairs': flair_data
            })

    except Exception as e:
        logger.error(f"Error fetching flairs: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@api_auth_required
def api_flair_bulk_update(request, guild_id):
    """POST /api/guild/<id>/flairs/bulk-update/ - Update multiple flairs at once."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        from .models import GuildFlair
        from .db import get_db_session
        import json

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        flairs_to_update = data.get('flairs', [])

        if not flairs_to_update:
            return JsonResponse({'error': 'No flairs provided'}, status=400)

        rename_results = []

        with get_db_session() as db:
            updated = 0
            for flair_data in flairs_to_update:
                flair_id = int(flair_data['id'])
                flair = db.query(GuildFlair).filter_by(
                    id=flair_id,
                    guild_id=int(guild_id)
                ).first()

                if flair:
                    old_name = flair.flair_name
                    old_display_order = flair.display_order
                    new_name = flair_data.get('flair_name', flair.flair_name)
                    new_display_order = int(flair_data.get('display_order', flair.display_order))

                    # Update flair properties
                    flair.flair_name = new_name
                    flair.cost = int(flair_data.get('cost', flair.cost))
                    flair.enabled = flair_data.get('enabled', flair.enabled)
                    flair.display_order = new_display_order
                    flair.updated_at = int(time.time())
                    updated += 1

                    # Rename Discord role if flair name changed (for all flair types)
                    if new_name != old_name:
                        try:
                            bot_session = get_bot_session(int(guild_id))
                            if bot_session:
                                # Get all roles in the guild
                                roles_resp = bot_session.get(f'/guilds/{guild_id}/roles')
                                if roles_resp.status_code == 200:
                                    roles = roles_resp.json()
                                    # Find the role with the old name
                                    matching_role = next((r for r in roles if r['name'] == old_name), None)

                                    if matching_role:
                                        # Rename the role
                                        patch_resp = bot_session.patch(
                                            f'/guilds/{guild_id}/roles/{matching_role["id"]}',
                                            json={'name': new_name}
                                        )
                                        if patch_resp.status_code == 200:
                                            logger.info(f"Renamed Discord role '{old_name}' to '{new_name}' in guild {guild_id}")
                                            rename_results.append({'old': old_name, 'new': new_name, 'success': True})
                                        else:
                                            logger.warning(f"Failed to rename Discord role '{old_name}' in guild {guild_id}: {patch_resp.status_code}")
                                            rename_results.append({'old': old_name, 'new': new_name, 'success': False})
                                    else:
                                        logger.warning(f"Discord role '{old_name}' not found in guild {guild_id}")
                                else:
                                    logger.warning(f"Failed to fetch roles for guild {guild_id}: {roles_resp.status_code}")
                            else:
                                logger.warning(f"Bot session not available for guild {guild_id}")
                        except Exception as e:
                            logger.error(f"Error renaming Discord role '{old_name}' to '{new_name}' in guild {guild_id}: {e}", exc_info=True)

                    # Update Discord role position if display_order changed
                    if new_display_order != old_display_order:
                        try:
                            bot_session = get_bot_session(int(guild_id))
                            if bot_session:
                                # Get all roles in the guild to find the role ID
                                roles_resp = bot_session.get(f'/guilds/{guild_id}/roles')
                                if roles_resp.status_code == 200:
                                    roles = roles_resp.json()
                                    # Find the role with the current flair name (use new_name in case it was renamed)
                                    matching_role = next((r for r in roles if r['name'] == new_name), None)

                                    if matching_role:
                                        # Update the role position
                                        # Discord API expects an array of role position objects
                                        patch_resp = bot_session.patch(
                                            f'/guilds/{guild_id}/roles',
                                            json=[{'id': matching_role['id'], 'position': new_display_order}]
                                        )
                                        if patch_resp.status_code == 200:
                                            logger.info(f"Updated Discord role '{new_name}' position from {old_display_order} to {new_display_order} in guild {guild_id}")
                                        else:
                                            logger.warning(f"Failed to update Discord role '{new_name}' position in guild {guild_id}: {patch_resp.status_code}")
                                    else:
                                        logger.warning(f"Discord role '{new_name}' not found in guild {guild_id} for position update")
                                else:
                                    logger.warning(f"Failed to fetch roles for guild {guild_id} for position update: {roles_resp.status_code}")
                            else:
                                logger.warning(f"Bot session not available for guild {guild_id} for position update")
                        except Exception as e:
                            logger.error(f"Error updating Discord role '{new_name}' position in guild {guild_id}: {e}", exc_info=True)

            db.commit()

            return JsonResponse({
                'success': True,
                'updated': updated,
                'roles_renamed': len(rename_results),
                'rename_details': rename_results
            })

    except Exception as e:
        logger.error(f"Error bulk updating flairs: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@api_auth_required
def api_flair_create(request, guild_id):
    """POST /api/guild/<id>/flairs/create/ - Create a new custom flair."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST allowed'}, status=405)

    try:
        from .models import GuildFlair
        from .db import get_db_session
        import json

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        flair_name = data.get('flair_name', '').strip()
        cost = int(data.get('cost', 100))
        role_position = data.get('role_position')  # Optional position for the Discord role

        if not flair_name:
            return JsonResponse({'error': 'Flair name is required'}, status=400)

        if len(flair_name) > 100:
            return JsonResponse({'error': 'Flair name must be 100 characters or less'}, status=400)

        # Check if flair already exists
        with get_db_session() as db:
            existing = db.query(GuildFlair).filter_by(
                guild_id=int(guild_id),
                flair_name=flair_name
            ).first()

            if existing:
                return JsonResponse({'error': 'A flair with this name already exists'}, status=400)

            # Create new flair
            new_flair = GuildFlair(
                guild_id=int(guild_id),
                flair_name=flair_name,
                flair_type='custom',
                cost=cost,
                enabled=True,
                created_by=int(request.session.get('discord_user', {}).get('id', 0)),
                display_order=999,  # Put custom flairs at the end
                created_at=int(time.time()),
                updated_at=int(time.time())
            )

            db.add(new_flair)
            db.commit()

            # Create the Discord role for this flair
            role_created = False
            role_error = None
            try:
                bot_session = get_bot_session(int(guild_id))
                if bot_session:
                    # Create role with default settings (no special permissions, not hoisted by default)
                    role_data = {
                        'name': flair_name,
                        'permissions': '0',
                        'color': 0,
                        'hoist': False,  # Don't hoist by default
                        'mentionable': False,
                    }

                    resp = bot_session.post(f'/guilds/{guild_id}/roles', json=role_data)
                    if resp.status_code == 200:
                        role = resp.json()
                        role_created = True
                        logger.info(f"Created Discord role '{flair_name}' (ID: {role['id']}) for flair in guild {guild_id}")

                        # Set role position if specified
                        if role_position is not None:
                            try:
                                position = int(role_position)
                                patch_resp = bot_session.patch(
                                    f'/guilds/{guild_id}/roles',
                                    json=[{'id': role['id'], 'position': position}]
                                )
                                if patch_resp.status_code != 200:
                                    logger.warning(f"Failed to set role position for '{flair_name}' in guild {guild_id}: {patch_resp.status_code}")
                            except Exception as e:
                                logger.warning(f"Error setting role position for '{flair_name}' in guild {guild_id}: {e}")
                    else:
                        role_error = f"Discord API returned status {resp.status_code}"
                        logger.warning(f"Failed to create Discord role for flair '{flair_name}' in guild {guild_id}: {role_error}")
                else:
                    role_error = "Bot session not available"
                    logger.warning(f"Could not create Discord role for flair '{flair_name}': Bot not connected to guild {guild_id}")
            except Exception as e:
                role_error = str(e)
                logger.error(f"Error creating Discord role for flair '{flair_name}' in guild {guild_id}: {e}", exc_info=True)

            return JsonResponse({
                'success': True,
                'flair': {
                    'id': new_flair.id,
                    'flair_name': new_flair.flair_name,
                    'flair_type': new_flair.flair_type,
                    'cost': new_flair.cost,
                    'enabled': new_flair.enabled,
                    'created_by': str(new_flair.created_by) if new_flair.created_by else None,
                    'display_order': new_flair.display_order,
                },
                'role_created': role_created,
                'role_info': 'Discord role created successfully' if role_created else f'Flair created but Discord role creation failed: {role_error}'
            })

    except Exception as e:
        logger.error(f"Error creating flair: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@api_auth_required
def api_flair_delete(request, guild_id, flair_id):
    """DELETE /api/guild/<id>/flairs/<flair_id>/ - Delete a custom flair."""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Only DELETE allowed'}, status=405)

    try:
        from .models import GuildFlair
        from .db import get_db_session

        with get_db_session() as db:
            flair = db.query(GuildFlair).filter_by(
                id=int(flair_id),
                guild_id=int(guild_id)
            ).first()

            if not flair:
                return JsonResponse({'error': 'Flair not found'}, status=404)

            # Only allow deleting custom flairs
            if flair.flair_type != 'custom':
                return JsonResponse({'error': 'Cannot delete default flairs'}, status=403)

            db.delete(flair)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': f'Flair "{flair.flair_name}" deleted'
            })

    except Exception as e:
        logger.error(f"Error deleting flair: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_flair_create_default_roles(request, guild_id):
    """POST /api/guild/<id>/flairs/create-default-roles/ - Queue creation of default flair roles."""
    try:
        from .models import PendingAction, ActionType, ActionStatus
        from .db import get_db_session

        discord_user = request.session.get('discord_user', {})

        with get_db_session() as db:
            # Avoid duplicate pending actions
            existing = db.query(PendingAction).filter_by(
                guild_id=int(guild_id),
                action_type=ActionType.FLAIR_SEED_ROLES.value,
                status=ActionStatus.PENDING.value
            ).first()

            if existing:
                return JsonResponse({
                    'success': True,
                    'message': 'A flair role creation task is already queued.'
                })

            action = PendingAction(
                guild_id=int(guild_id),
                action_type=ActionType.FLAIR_SEED_ROLES.value,
                status=ActionStatus.PENDING.value,
                payload=json.dumps({}),
                triggered_by=int(discord_user.get('id', 0)),
                triggered_by_name=discord_user.get('username', 'Unknown')
            )
            db.add(action)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Default flair roles will be created and hoisted automatically.'
            })

    except Exception as e:
        logger.error(f"Error queueing default flair role creation for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to queue flair role creation'}, status=500)


# Tracker API Endpoints

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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_guild_resources(request, guild_id):
    """GET /api/guild/<id>/resources/ - Fetch guild channels, roles, and cached members."""
    try:
        from .db import get_db_session
        from .models import GuildMember as MemberModel

        # Get Discord bot token from session or settings
        admin_guilds = request.session.get('discord_admin_guilds', [])
        guild = next((g for g in admin_guilds if g['id'] == guild_id), None)

        if not guild:
            return JsonResponse({'error': 'Guild not found'}, status=404)

        response_data = {
            'channels': [],
            'roles': [],
            'members': []
        }

        # Get channels from Discord guild data (if available in session)
        if 'channels' in guild:
            response_data['channels'] = [
                {'id': str(ch.get('id')), 'name': ch.get('name'), 'type': ch.get('type')}
                for ch in guild.get('channels', [])
            ]

        # Get roles from Discord guild data (if available in session)
        if 'roles' in guild:
            response_data['roles'] = [
                {'id': str(role.get('id')), 'name': role.get('name'), 'color': role.get('color', 0)}
                for role in guild.get('roles', [])
            ]

        # Get cached members from database
        try:
            with get_db_session() as db:
                members = db.query(MemberModel).filter_by(
                    guild_id=int(guild_id)
                ).limit(1000).all()  # Limit to 1000 for performance

                response_data['members'] = [
                    {'id': str(m.user_id), 'name': m.display_name or f'User {m.user_id}'}
                    for m in members
                ]
        except Exception as e:
            logger.warning(f"Could not fetch members from DB: {e}")

        return JsonResponse(response_data)

    except Exception as e:
        logger.error(f"Error fetching guild resources: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_member_auth_required
def api_guild_members(request, guild_id):
    """GET /api/guild/<id>/members/ - Fetch cached members (id + name)."""
    try:
        from .db import get_db_session
        from .models import GuildMember as MemberModel

        with get_db_session() as db:
            members = db.query(MemberModel).filter_by(guild_id=int(guild_id)).limit(1000).all()
            members_list = [
                {
                    'id': str(m.user_id),
                    'username': m.display_name or f'User {m.user_id}',
                    'display_name': m.display_name or f'User {m.user_id}'
                }
                for m in members
            ]
        return JsonResponse({'success': True, 'members': members_list})
    except Exception as e:
        logger.error(f"Error fetching guild members for {guild_id}: {e}")
        return JsonResponse({'success': False, 'error': 'An internal error occurred. Please try again later.'}, status=500)


# REMOVED DUPLICATE - See the correct api_guild_emojis implementation at line ~6252


@require_http_methods(["POST"])
@api_auth_required
def api_message_action(request, guild_id):
    """POST /api/guild/<id>/messages/ - Queue message/embed send/edit/broadcast."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    mode = data.get('mode')
    if mode not in ('send', 'send_embed', 'edit', 'edit_embed', 'broadcast'):
        return JsonResponse({'error': 'Invalid mode'}, status=400)

    try:
        from .actions import queue_action, ActionType

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        payload = data
        payload['mode'] = mode
        payload['guild_id'] = int(guild_id)

        action_id = queue_action(
            guild_id=int(guild_id),
            action_type=ActionType.MESSAGE_SEND,
            payload=payload,
            triggered_by=triggered_by,
            triggered_by_name=triggered_by_name,
            source='website'
        )

        return JsonResponse({'success': True, 'action_id': action_id, 'message': 'Queued'})

    except Exception as e:
        logger.error(f"Error queueing message action for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to queue message action'}, status=500)


# Scheduled Messages Endpoints

@require_http_methods(["POST"])
@api_auth_required
def api_scheduled_messages_create(request, guild_id):
    """POST /api/guild/<id>/scheduled-messages/ - Create a scheduled message."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Validate required fields
    message_type = data.get('message_type')
    if message_type not in ('message', 'embed', 'broadcast'):
        return JsonResponse({'error': 'Invalid message_type. Must be message, embed, or broadcast'}, status=400)

    scheduled_time = data.get('scheduled_time')
    if not scheduled_time:
        return JsonResponse({'error': 'scheduled_time is required'}, status=400)

    content_data = data.get('content_data')
    if not content_data:
        return JsonResponse({'error': 'content_data is required'}, status=400)

    # Validate destination
    if message_type in ('message', 'embed') and not data.get('channel_id'):
        return JsonResponse({'error': 'channel_id is required for message and embed types'}, status=400)

    if message_type == 'broadcast' and not data.get('category_id'):
        return JsonResponse({'error': 'category_id is required for broadcast type'}, status=400)

    try:
        from .db import get_db_session
        from .models import ScheduledMessage
        import time

        discord_user = request.session.get('discord_user', {})
        user_id = int(discord_user.get('id', 0))

        with get_db_session() as db:
            scheduled_msg = ScheduledMessage(
                guild_id=int(guild_id),
                message_type=message_type,
                channel_id=int(data.get('channel_id')) if data.get('channel_id') else None,
                category_id=int(data.get('category_id')) if data.get('category_id') else None,
                scheduled_time=int(scheduled_time),
                timezone=data.get('timezone', 'UTC'),
                content_data=json_lib.dumps(content_data),
                status='pending',
                created_by=user_id,
                created_at=int(time.time()),
                updated_at=int(time.time())
            )
            db.add(scheduled_msg)
            db.commit()
            db.refresh(scheduled_msg)

            return JsonResponse({
                'success': True,
                'message': 'Scheduled message created successfully',
                'id': scheduled_msg.id
            })

    except Exception as e:
        logger.error(f"Error creating scheduled message for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to create scheduled message'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_scheduled_messages_list(request, guild_id):
    """GET /api/guild/<id>/scheduled-messages/ - List all scheduled messages for a guild."""
    try:
        from .db import get_db_session
        from .models import ScheduledMessage

        # Optional status filter
        status_filter = request.GET.get('status', None)

        with get_db_session() as db:
            from .models import Guild

            # Get guild to access cached channels/roles
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Parse cached resources
            cached_channels = json_lib.loads(guild.cached_channels) if guild.cached_channels else []
            channel_map = {str(ch['id']): ch['name'] for ch in cached_channels}

            query = db.query(ScheduledMessage).filter_by(guild_id=int(guild_id))

            if status_filter:
                query = query.filter_by(status=status_filter)

            # Order by scheduled_time ascending (soonest first)
            scheduled_messages = query.order_by(ScheduledMessage.scheduled_time.asc()).all()

            messages_data = []
            for msg in scheduled_messages:
                # Get channel/category name
                channel_name = None
                category_name = None

                if msg.channel_id:
                    channel_name = channel_map.get(str(msg.channel_id), f"Unknown ({msg.channel_id})")
                if msg.category_id:
                    category_name = channel_map.get(str(msg.category_id), f"Unknown ({msg.category_id})")

                messages_data.append({
                    'id': msg.id,
                    'message_type': msg.message_type,
                    'channel_id': str(msg.channel_id) if msg.channel_id else None,
                    'channel_name': channel_name,
                    'category_id': str(msg.category_id) if msg.category_id else None,
                    'category_name': category_name,
                    'scheduled_time': msg.scheduled_time,
                    'timezone': msg.timezone,
                    'content_data': json_lib.loads(msg.content_data),
                    'status': msg.status,
                    'sent_at': msg.sent_at,
                    'error_message': msg.error_message,
                    'created_by': str(msg.created_by),
                    'created_at': msg.created_at,
                    'updated_at': msg.updated_at
                })

            return JsonResponse({
                'success': True,
                'messages': messages_data,
                'count': len(messages_data)
            })

    except Exception as e:
        logger.error(f"Error listing scheduled messages for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to list scheduled messages'}, status=500)


@require_http_methods(["PUT"])
@api_auth_required
def api_scheduled_messages_update(request, guild_id, message_id):
    """PUT /api/guild/<id>/scheduled-messages/<msg_id>/ - Update a scheduled message."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import ScheduledMessage
        import time

        with get_db_session() as db:
            scheduled_msg = db.query(ScheduledMessage).filter_by(
                id=int(message_id),
                guild_id=int(guild_id)
            ).first()

            if not scheduled_msg:
                return JsonResponse({'error': 'Scheduled message not found'}, status=404)

            # Only allow editing pending messages
            if scheduled_msg.status != 'pending':
                return JsonResponse({
                    'error': f'Cannot edit {scheduled_msg.status} messages. Only pending messages can be edited.'
                }, status=400)

            # Update fields if provided
            if 'scheduled_time' in data:
                scheduled_msg.scheduled_time = int(data['scheduled_time'])

            if 'timezone' in data:
                scheduled_msg.timezone = data['timezone']

            if 'content_data' in data:
                scheduled_msg.content_data = json_lib.dumps(data['content_data'])

            if 'channel_id' in data:
                scheduled_msg.channel_id = int(data['channel_id']) if data['channel_id'] else None

            if 'category_id' in data:
                scheduled_msg.category_id = int(data['category_id']) if data['category_id'] else None

            scheduled_msg.updated_at = int(time.time())

            db.commit()
            db.refresh(scheduled_msg)

            return JsonResponse({
                'success': True,
                'message': 'Scheduled message updated successfully'
            })

    except Exception as e:
        logger.error(f"Error updating scheduled message {message_id} for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to update scheduled message'}, status=500)


@require_http_methods(["DELETE"])
@api_auth_required
def api_scheduled_messages_cancel(request, guild_id, message_id):
    """DELETE /api/guild/<id>/scheduled-messages/<msg_id>/ - Cancel a scheduled message."""
    try:
        from .db import get_db_session
        from .models import ScheduledMessage
        import time

        with get_db_session() as db:
            scheduled_msg = db.query(ScheduledMessage).filter_by(
                id=int(message_id),
                guild_id=int(guild_id)
            ).first()

            if not scheduled_msg:
                return JsonResponse({'error': 'Scheduled message not found'}, status=404)

            # Only allow cancelling pending messages
            if scheduled_msg.status != 'pending':
                return JsonResponse({
                    'error': f'Cannot cancel {scheduled_msg.status} messages. Only pending messages can be cancelled.'
                }, status=400)

            scheduled_msg.status = 'cancelled'
            scheduled_msg.updated_at = int(time.time())

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Scheduled message cancelled successfully'
            })

    except Exception as e:
        logger.error(f"Error cancelling scheduled message {message_id} for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to cancel scheduled message'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_guild_leave(request, guild_id):
    """POST /api/guild/<id>/leave/ - Make the bot leave the specified guild."""
    try:
        # Verify user has admin access to this guild
        admin_guilds = request.session.get('discord_admin_guilds', [])
        guild = next((g for g in admin_guilds if g['id'] == guild_id), None)

        if not guild:
            return JsonResponse({'error': 'You do not have admin access to this server'}, status=403)

        # Get bot token from environment
        bot_token = os.getenv('DISCORD_BOT_TOKEN')

        if not bot_token or bot_token == 'your_bot_token_here':
            logger.error("DISCORD_BOT_TOKEN not configured")
            return JsonResponse({'error': 'Bot token not configured'}, status=500)

        # Make Discord API call to leave the guild
        response = requests.delete(
            f'https://discord.com/api/v10/users/@me/guilds/{guild_id}',
            headers={'Authorization': f'Bot {bot_token}'}
        )

        if response.status_code == 204:
            logger.info(f"Bot successfully left guild {guild_id} ({guild.get('name', 'Unknown')})")
            return JsonResponse({
                'success': True,
                'message': f'Successfully removed bot from {guild.get("name", "server")}'
            })
        elif response.status_code == 404:
            return JsonResponse({'error': 'Bot is not in this server or server not found'}, status=404)
        else:
            logger.error(f"Failed to leave guild {guild_id}: {response.status_code} - {response.text}")
            return JsonResponse({
                'error': f'Failed to leave server (Discord API error: {response.status_code})'
            }, status=500)

    except Exception as e:
        logger.error(f"Error leaving guild {guild_id}: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# XP & Leveling Dashboard

@discord_required
def guild_xp(request, guild_id):
    """XP and leveling management page for a guild."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    # Fetch XP config and leaderboard from database
    xp_config = None
    leaderboard = []
    level_roles = []
    total_members = 0
    guild_record = None

    try:
        from .db import get_db_session
        from .models import XPConfig, GuildMember, LevelRole, Guild as GuildModel, DailyBulkUsage
        import time
        from datetime import datetime

        # Get today's date as integer (YYYYMMDD)
        today_date = int(datetime.now().strftime('%Y%m%d'))

        with get_db_session() as db:
            # Get guild record for tier checking
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()

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

            # Get daily bulk operation usage for today
            bulk_edit_usage = db.query(DailyBulkUsage).filter_by(
                guild_id=int(guild_id),
                date=today_date,
                operation_category='xp_bulk_edit'
            ).first()

            import_usage = db.query(DailyBulkUsage).filter_by(
                guild_id=int(guild_id),
                date=today_date,
                operation_category='xp_import'
            ).first()

            bulk_edit_items_today = bulk_edit_usage.items_processed if bulk_edit_usage else 0
            import_items_today = import_usage.items_processed if import_usage else 0

    except Exception as e:
        logger.warning(f"Could not fetch XP data: {e}")
        bulk_edit_items_today = 0
        import_items_today = 0

    # Check if guild has engagement module access
    has_engagement_module = has_module_access(guild_id, 'engagement')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'xp_config': xp_config or {},
        'leaderboard': leaderboard,
        'level_roles': level_roles,
        'total_members': total_members,
        'has_engagement_module': has_engagement_module,
        'has_any_module': has_any_module,
        'active_page': 'xp',
        'bulk_edit_items_today': bulk_edit_items_today,
        'import_items_today': import_items_today,
    }
    return render(request, 'questlog/xp.html', context)


# XP API Endpoints

@api_auth_required
def api_xp_config(request, guild_id):
    """GET /api/guild/<id>/xp/config/ - Get XP configuration."""
    try:
        from .db import get_db_session
        from .models import XPConfig
        from sqlalchemy.exc import ProgrammingError
        from sqlalchemy import text

        with get_db_session() as db:
            try:
                config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()
            except ProgrammingError as pe:
                logger.error(f"XP config query failed (likely missing columns). Defaulting config. {pe}")
                # Attempt to add missing column if absent
                try:
                    db.execute(text("ALTER TABLE xp_configs ADD COLUMN xp_enabled TINYINT(1) DEFAULT 1"))
                    db.flush()
                    config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()
                except Exception as alter_err:
                    logger.error(f"Could not auto-add xp_enabled column: {alter_err}")
                config = None

            if not config:
                # Return defaults
                return JsonResponse({
                    'success': True,
                    'config': {
                        'xp_enabled': False,  # XP disabled by default
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
                    'xp_enabled': config.xp_enabled,
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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        from sqlalchemy.exc import ProgrammingError
        from sqlalchemy import text

        with get_db_session() as db:
            # Ensure guild exists
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                guild_record = GuildModel(guild_id=int(guild_id))
                db.add(guild_record)
                db.flush()

            try:
                config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()
            except ProgrammingError as pe:
                logger.error(f"XP config query failed (likely missing columns). Defaulting config. {pe}")
                try:
                    db.execute(text("ALTER TABLE xp_configs ADD COLUMN xp_enabled TINYINT(1) DEFAULT 1"))
                    db.flush()
                    config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()
                except Exception as alter_err:
                    logger.error(f"Could not auto-add xp_enabled column: {alter_err}")
                config = None
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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_xp_toggle(request, guild_id):
    """POST /api/guild/<id>/xp/toggle/ - Toggle XP system on/off."""
    import json
    try:
        from .db import get_db_session
        from .models import XPConfig
        from sqlalchemy.exc import ProgrammingError
        from sqlalchemy import text

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        xp_enabled = data.get('xp_enabled', False)

        with get_db_session() as db:
            try:
                config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()
            except ProgrammingError as pe:
                logger.error(f"XP toggle query failed (likely missing columns). Creating default. {pe}")
                try:
                    db.execute(text("ALTER TABLE xp_configs ADD COLUMN xp_enabled TINYINT(1) DEFAULT 1"))
                    db.flush()
                    config = db.query(XPConfig).filter_by(guild_id=int(guild_id)).first()
                except Exception as alter_err:
                    logger.error(f"Could not auto-add xp_enabled column: {alter_err}")
                config = None

            if not config:
                # Create new config with the enabled status
                config = XPConfig(guild_id=int(guild_id), xp_enabled=xp_enabled)
                db.add(config)
            else:
                # Update existing config
                config.xp_enabled = xp_enabled

            # Keep guild table flag in sync (bot checks Guild.xp_enabled)
            from .models import Guild as GuildModel
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if guild_record:
                guild_record.xp_enabled = xp_enabled

            db.commit()

            return JsonResponse({
                'success': True,
                'xp_enabled': config.xp_enabled
            })

    except Exception as e:
        logger.error(f"Error toggling XP system: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
@ratelimit(key='user_or_ip', rate='30/m', method='POST', block=True)
@validate_json_schema({
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["add", "subtract", "set"]},
        "amount": {"type": "number", "minimum": -1000000, "maximum": 1000000},
        "field": {"type": "string", "enum": ["xp", "tokens"]}
    },
    "required": ["action", "amount", "field"]
})
def api_xp_member_update(request, guild_id, user_id):
    """POST /api/guild/<id>/xp/member/<user_id>/ - Update a member's XP/tokens."""
    data = request.validated_data

    try:
        from .actions import queue_xp_add, queue_xp_set, queue_tokens_add, queue_tokens_set

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        action_type = data.get('action', 'set')  # 'add', 'subtract', 'set'
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
            elif action_type == 'subtract':
                # Use negative amount for subtraction
                action_id = queue_xp_add(
                    guild_id=int(guild_id),
                    user_id=int(user_id),
                    amount=-abs(amount),
                    triggered_by=triggered_by,
                    triggered_by_name=triggered_by_name
                )
            elif action_type == 'set':
                action_id = queue_xp_set(
                    guild_id=int(guild_id),
                    user_id=int(user_id),
                    amount=amount,
                    triggered_by=triggered_by,
                    triggered_by_name=triggered_by_name
                )
            else:
                return JsonResponse({'error': 'Invalid action type'}, status=400)
        elif field == 'tokens':
            if action_type == 'add':
                action_id = queue_tokens_add(
                    guild_id=int(guild_id),
                    user_id=int(user_id),
                    amount=int(amount),
                    triggered_by=triggered_by,
                    triggered_by_name=triggered_by_name
                )
            elif action_type == 'subtract':
                # Use negative amount for subtraction
                action_id = queue_tokens_add(
                    guild_id=int(guild_id),
                    user_id=int(user_id),
                    amount=-abs(int(amount)),
                    triggered_by=triggered_by,
                    triggered_by_name=triggered_by_name
                )
            elif action_type == 'set':
                action_id = queue_tokens_set(
                    guild_id=int(guild_id),
                    user_id=int(user_id),
                    amount=int(amount),
                    triggered_by=triggered_by,
                    triggered_by_name=triggered_by_name
                )
            else:
                return JsonResponse({'error': 'Invalid action type'}, status=400)
        else:
            return JsonResponse({'error': 'Invalid field'}, status=400)

        return JsonResponse({
            'success': True,
            'action_id': action_id,
            'message': f'Action queued (ID: {action_id})'
        })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_xp_level_role_bulk_create(request, guild_id):
    """POST /api/guild/<id>/xp/roles/bulk-create/ - Create multiple level roles at once."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    if 'roles' not in data or not isinstance(data['roles'], list):
        return JsonResponse({'error': 'Missing or invalid "roles" array'}, status=400)

    if len(data['roles']) == 0:
        return JsonResponse({'error': 'No roles provided'}, status=400)

    try:
        from .db import get_db_session
        from .models import LevelRole

        created_count = 0
        errors = []

        with get_db_session() as db:
            for idx, role_data in enumerate(data['roles']):
                # Validate required fields
                if 'level' not in role_data or 'role_id' not in role_data:
                    errors.append(f"Row {idx + 1}: Missing level or role_id")
                    continue

                try:
                    level = int(role_data['level'])
                    role_id = int(role_data['role_id'])
                except (ValueError, TypeError):
                    errors.append(f"Row {idx + 1}: Invalid level or role_id")
                    continue

                # Check if level already has a role
                existing = db.query(LevelRole).filter_by(
                    guild_id=int(guild_id),
                    level=level
                ).first()

                if existing:
                    errors.append(f"Row {idx + 1}: Level {level} already has a role assigned")
                    continue

                # Create new level role
                role = LevelRole(
                    guild_id=int(guild_id),
                    level=level,
                    role_id=role_id,
                    role_name=role_data.get('role_name'),
                    remove_previous=role_data.get('remove_previous', True)
                )
                db.add(role)
                created_count += 1

            db.flush()

            return JsonResponse({
                'success': True,
                'created': created_count,
                'errors': errors if errors else None
            })

    except Exception as e:
        logger.error(f"Bulk level role creation error: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["DELETE"])
@api_auth_required
def api_xp_member_delete(request, guild_id, user_id):
    """DELETE /api/guild/<id>/xp/member/<user_id>/delete/ - Remove a member from XP system."""
    try:
        from .db import get_db_session
        from .models import GuildMember

        with get_db_session() as db:
            member = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                user_id=int(user_id)
            ).first()

            if not member:
                return JsonResponse({'error': 'Member not found'}, status=404)

            display_name = member.display_name or f"User {user_id}"
            db.delete(member)

            return JsonResponse({
                'success': True,
                'message': f'Removed {display_name} from XP system'
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_xp_member_add(request, guild_id):
    """POST /api/guild/<id>/xp/member/add/ - Manually add a member to XP system."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import GuildMember

        user_id = int(data.get('user_id'))
        xp = float(data.get('xp', 0))
        level = int(data.get('level', 0))
        hero_tokens = int(data.get('hero_tokens', 0))
        display_name = data.get('display_name', '')

        with get_db_session() as db:
            # Check if member already exists
            existing = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                user_id=user_id
            ).first()

            if existing:
                return JsonResponse({'error': 'Member already exists in XP system'}, status=400)

            # Create new member
            member = GuildMember(
                guild_id=int(guild_id),
                user_id=user_id,
                xp=xp,
                level=level,
                hero_tokens=hero_tokens,
                display_name=display_name
            )
            db.add(member)

            return JsonResponse({
                'success': True,
                'message': f'Added {display_name or user_id} to XP system'
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_xp_import_csv(request, guild_id):
    """POST /api/guild/<id>/xp/import/ - Import XP data from CSV or XLSX file."""
    try:
        import logging
        logger = logging.getLogger(__name__)

        if 'csv_file' not in request.FILES:
            return JsonResponse({'error': 'No file provided'}, status=400)

        upload_file = request.FILES['csv_file']
        filename = upload_file.name.lower()

        # LOG who is uploading XP files
        user_session = request.session.get('discord_user', {})
        logger.warning(
            f"[XP IMPORT TRACKER] User {user_session.get('username', 'UNKNOWN')} "
            f"(ID: {user_session.get('id', 'UNKNOWN')}) uploading XP file '{filename}' "
            f"for guild {guild_id}"
        )

        from .db import get_db_session
        from .models import GuildMember

        # Parse file based on extension
        rows = []

        if filename.endswith('.xlsx'):
            # Parse XLSX file
            from openpyxl import load_workbook
            from io import BytesIO

            wb = load_workbook(BytesIO(upload_file.read()))
            ws = wb.active

            # Get headers from first row
            headers = [cell.value for cell in ws[1]]

            # Read data rows
            for row in ws.iter_rows(min_row=2, values_only=True):
                row_dict = {}
                for i, value in enumerate(row):
                    if i < len(headers) and headers[i]:
                        row_dict[headers[i]] = str(value) if value is not None else ''
                rows.append(row_dict)

        else:
            # Parse CSV/TSV file
            import csv
            from io import StringIO

            # Try different encodings
            content = None
            for encoding in ['utf-8', 'cp1252', 'latin-1', 'iso-8859-1']:
                try:
                    content = upload_file.read().decode(encoding)
                    break
                except UnicodeDecodeError:
                    upload_file.seek(0)
                    continue

            if not content:
                return JsonResponse({'error': 'Could not read file with any supported encoding'}, status=400)

            # Detect delimiter (comma or tab)
            try:
                dialect = csv.Sniffer().sniff(content[:1024], delimiters=',\t')
                reader = csv.DictReader(StringIO(content), dialect=dialect)
            except:
                reader = csv.DictReader(StringIO(content))

            rows = list(reader)

        # Check tier limits and daily usage
        from .models import Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Check daily bulk limit
            allowed, error_msg, usage_info = check_daily_bulk_limit(
                guild_id, 'xp_import', len(rows), guild_record
            )

            if not allowed:
                return JsonResponse({
                    'error': error_msg,
                    'limit_exceeded': True,
                    'usage_info': usage_info
                }, status=403)

        created = 0
        updated = 0
        skipped = 0
        errors = []

        with get_db_session() as db:
            for row in rows:
                try:
                    # Handle scientific notation in user_id
                    user_id_str = row.get('user_id', '').strip()
                    if not user_id_str:
                        skipped += 1
                        continue

                    # Clean up any Excel artifacts
                    user_id_str = user_id_str.replace("'", "").replace('"', '').replace('=', '')

                    # Convert directly to int - DO NOT use float() as it loses precision for large numbers!
                    user_id = int(user_id_str)

                    # VALIDATE: Detect corrupted IDs from Excel (trailing zeros = precision loss)
                    user_id_check = str(user_id)
                    if user_id_check.endswith('000000000'):  # 9+ trailing zeros = corrupted
                        errors.append(f"CORRUPTED ID detected: {user_id_check} for {row.get('display_name', 'unknown')}. "
                                    f"Excel converted IDs to scientific notation! "
                                    f"FIX: Format user_id column as TEXT before pasting IDs, or use Google Sheets.")
                        skipped += 1
                        continue

                    # VALIDATE: Check if string was converted through float() (subtle corruption)
                    # If the original string doesn't match the parsed int, it was corrupted
                    if user_id_str != str(user_id):
                        errors.append(
                            f"CORRUPTED ID detected: input '{user_id_str}' became {user_id} for "
                            f"{row.get('display_name', 'unknown')}. This is float precision loss! "
                            f"FIX: Check your Excel/CSV formatting."
                        )
                        logger.error(
                            f"[XP IMPORT] REJECTED CORRUPTED ID: '{user_id_str}' -> {user_id} "
                            f"for {row.get('display_name', 'unknown')}"
                        )
                        skipped += 1
                        continue

                    # Validate ID is reasonable (Discord IDs are 17-19 digits)
                    if user_id < 100000000000000000 or user_id > 9999999999999999999:
                        errors.append(f"Invalid user_id {user_id} for {row.get('display_name', 'unknown')} - must be 17-19 digits")
                        skipped += 1
                        continue

                    xp = float(row.get('xp', 0))
                    level = int(row.get('level', 0))
                    hero_tokens = int(row.get('hero_tokens', 0))
                    display_name = row.get('display_name', '').strip()

                    # Skip members with 0 XP and level
                    if xp == 0 and level == 0:
                        skipped += 1
                        continue

                    # Check if member exists
                    member = db.query(GuildMember).filter_by(
                        guild_id=int(guild_id),
                        user_id=user_id
                    ).first()

                    if member:
                        # Update existing
                        member.xp = xp
                        member.level = level
                        member.hero_tokens = hero_tokens
                        if display_name:
                            member.display_name = display_name
                        updated += 1
                    else:
                        # Create new
                        logger.warning(
                            f"[XP IMPORT TRACKER] CREATING NEW MEMBER: guild={guild_id}, "
                            f"user_id={user_id}, display_name={display_name}, xp={xp}, "
                            f"from_file={filename}"
                        )
                        member = GuildMember(
                            guild_id=int(guild_id),
                            user_id=user_id,
                            xp=xp,
                            level=level,
                            hero_tokens=hero_tokens,
                            display_name=display_name
                        )
                        db.add(member)
                        created += 1

                except Exception as e:
                    errors.append(f"Row error: {str(e)}")
                    continue

        # Record usage for daily tracking (only count successfully processed rows)
        processed_count = created + updated
        if processed_count > 0:
            record_bulk_usage(guild_id, 'xp_import', processed_count)

        return JsonResponse({
            'success': True,
            'created': created,
            'updated': updated,
            'skipped': skipped,
            'errors': errors[:10]  # Return first 10 errors
        })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
@require_subscription_tier('pro', 'premium')
@ratelimit(key='user_or_ip', rate='10/h', method='GET', block=True)
def api_xp_export_csv(request, guild_id):
    """GET /api/guild/<id>/xp/export/ - Export XP data as Excel (Pro/Premium only, 10 req/hour)."""
    try:
        from .db import get_db_session
        from .models import GuildMember
        from django.http import HttpResponse
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from io import BytesIO

        with get_db_session() as db:
            members = db.query(GuildMember).filter_by(guild_id=int(guild_id)).order_by(GuildMember.xp.desc()).all()

            # Create XLSX workbook
            wb = Workbook()
            ws = wb.active
            ws.title = "XP Data"

            # Write headers
            headers = ['user_id', 'display_name', 'xp', 'level', 'hero_tokens', 'message_count']
            ws.append(headers)

            # Bold headers
            for cell in ws[1]:
                cell.font = Font(bold=True)

            # Write data
            for member in members:
                ws.append([
                    str(member.user_id),
                    member.display_name or '',
                    member.xp,
                    member.level,
                    member.hero_tokens,
                    member.message_count or 0
                ])

            # Format user_id column as TEXT (prevents Excel scientific notation)
            for row in range(2, ws.max_row + 1):
                ws.cell(row=row, column=1).number_format = '@'  # @ = TEXT format

            # Adjust column widths
            ws.column_dimensions['A'].width = 20  # user_id
            ws.column_dimensions['B'].width = 25  # display_name
            ws.column_dimensions['C'].width = 12  # xp
            ws.column_dimensions['D'].width = 10  # level
            ws.column_dimensions['E'].width = 15  # hero_tokens
            ws.column_dimensions['F'].width = 15  # message_count

            # Save to BytesIO
            excel_file = BytesIO()
            wb.save(excel_file)
            excel_file.seek(0)

            # Create response
            response = HttpResponse(
                excel_file.getvalue(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="guild_{guild_id}_xp_export.xlsx"'

            return response

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET", "POST"])
@api_auth_required
@require_subscription_tier('pro', 'premium')
@ratelimit(key='user_or_ip', rate='5/h', method='POST', block=True)
def api_xp_bulk_edit(request, guild_id):
    """GET/POST /api/guild/<id>/xp/bulk-edit/ - Bulk edit XP for active members (Pro/Premium only, 5 req/hour)."""
    try:
        from .db import get_db_session
        from .models import GuildMember
        import json

        if request.method == 'GET':
            # Fetch all members from the database
            with get_db_session() as db:
                members = db.query(GuildMember).filter(
                    GuildMember.guild_id == int(guild_id)
                ).order_by(GuildMember.xp.desc()).all()

                member_data = [
                    {
                        'user_id': str(member.user_id),
                        'display_name': member.display_name or f'User {member.user_id}',
                        'xp': float(member.xp),
                        'level': member.level,
                        'hero_tokens': member.hero_tokens or 0
                    }
                    for member in members
                ]

                return JsonResponse({
                    'success': True,
                    'members': member_data
                })

        elif request.method == 'POST':
            # Update members
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
            members_to_update = data.get('members', [])

            if not members_to_update:
                return JsonResponse({'error': 'No members provided'}, status=400)

            # Check tier limits and daily usage
            from .models import Guild as GuildModel

            with get_db_session() as db:
                guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
                if not guild_record:
                    return JsonResponse({'error': 'Guild not found'}, status=404)

                # Check daily bulk limit
                allowed, error_msg, usage_info = check_daily_bulk_limit(
                    guild_id, 'xp_bulk', len(members_to_update), guild_record
                )

                if not allowed:
                    return JsonResponse({
                        'error': error_msg,
                        'limit_exceeded': True,
                        'usage_info': usage_info
                    }, status=403)

            with get_db_session() as db:
                updated = 0
                for member_data in members_to_update:
                    user_id = int(member_data['user_id'])
                    member = db.query(GuildMember).filter_by(
                        guild_id=int(guild_id),
                        user_id=user_id
                    ).first()

                    if member:
                        # Update XP, Level, Hero Tokens
                        member.xp = float(member_data.get('xp', member.xp))
                        member.level = int(member_data.get('level', member.level))
                        member.hero_tokens = int(member_data.get('hero_tokens', member.hero_tokens or 0))

                        updated += 1

                db.commit()

                # Record usage for daily tracking
                record_bulk_usage(guild_id, 'xp_bulk', len(members_to_update))

                return JsonResponse({
                    'success': True,
                    'updated': updated
                })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# XP Boost Events API

@api_auth_required
def api_xp_boost_events_list(request, guild_id):
    """GET /api/guild/<id>/xp/boost-events/ - Get all boost events for a guild."""
    try:
        from .db import get_db_session
        from .models import XPBoostEvent
        import time

        with get_db_session() as db:
            events = db.query(XPBoostEvent).filter_by(
                guild_id=int(guild_id)
            ).order_by(XPBoostEvent.is_default.desc(), XPBoostEvent.name).all()

            return JsonResponse({
                'success': True,
                'events': [
                    {
                        'id': e.id,
                        'name': e.name,
                        'description': e.description,
                        'multiplier': float(e.multiplier),
                        'start_time': e.start_time,
                        'end_time': e.end_time,
                        'is_active': e.is_active,
                        'is_default': e.is_default,
                        'scope': e.scope,
                        'scope_id': str(e.scope_id) if e.scope_id else None,
                        'token_bonus': e.token_bonus,
                        'announcement_channel_id': str(e.announcement_channel_id) if e.announcement_channel_id else None,
                        'announcement_role_id': str(e.announcement_role_id) if e.announcement_role_id else None,
                        'created_at': e.created_at,
                        'updated_at': e.updated_at,
                    }
                    for e in events
                ]
            })
    except Exception as e:
        logger.error(f"Error fetching boost events for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["PATCH"])
@api_auth_required
def api_xp_boost_event_update(request, guild_id, event_id):
    """PATCH /api/guild/<id>/xp/boost-events/<event_id>/ - Update a boost event."""
    try:
        import json as json_lib
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import XPBoostEvent, PendingAction, ActionType
        import time

        with get_db_session() as db:
            event = db.query(XPBoostEvent).filter_by(
                id=int(event_id),
                guild_id=int(guild_id)
            ).first()

            if not event:
                return JsonResponse({'error': 'Boost event not found'}, status=404)

            # Track old is_active state for announcement triggering
            was_active = event.is_active
            should_announce = False

            # Update fields
            if 'is_active' in data:
                new_is_active = bool(data['is_active'])
                event.is_active = new_is_active
                # Queue announcement if event is being activated
                if not was_active and new_is_active:
                    should_announce = True

            if 'name' in data:
                event.name = data['name']
            if 'description' in data:
                event.description = data['description']
            if 'multiplier' in data:
                event.multiplier = float(data['multiplier'])
            if 'token_bonus' in data:
                event.token_bonus = int(data['token_bonus'])
            if 'scope' in data:
                event.scope = data['scope']
            if 'scope_id' in data:
                event.scope_id = int(data['scope_id']) if data['scope_id'] else None

            # Timing fields
            if 'start_time' in data:
                event.start_time = int(data['start_time']) if data['start_time'] else None
            if 'end_time' in data:
                event.end_time = int(data['end_time']) if data['end_time'] else None

            # Announcement fields
            if 'announcement_channel_id' in data:
                event.announcement_channel_id = int(data['announcement_channel_id']) if data['announcement_channel_id'] else None
            if 'announcement_role_id' in data:
                event.announcement_role_id = int(data['announcement_role_id']) if data['announcement_role_id'] else None

            event.updated_at = int(time.time())
            db.commit()

            # Queue announcement action if event was just activated
            if should_announce and event.announcement_channel_id:
                import json as json_module

                action_data = {
                    'event_id': event.id,
                    'event_name': event.name,
                    'multiplier': float(event.multiplier),
                    'description': event.description,
                    'channel_id': str(event.announcement_channel_id),
                    'role_id': str(event.announcement_role_id) if event.announcement_role_id else None,
                    'end_time': event.end_time,
                }

                pending_action = PendingAction(
                    guild_id=int(guild_id),
                    action_type=ActionType.BOOST_EVENT_START,
                    payload=json_module.dumps(action_data),
                    status='pending'
                )
                db.add(pending_action)
                db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Boost event updated successfully'
            })

    except Exception as e:
        logger.error(f"Error updating boost event {event_id} for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["DELETE"])
@api_auth_required
def api_xp_boost_event_delete(request, guild_id, event_id):
    """DELETE /api/guild/<id>/xp/boost-events/<event_id>/ - Delete a custom boost event."""
    try:
        from .db import get_db_session
        from .models import XPBoostEvent
        from .module_utils import has_module_access

        # Only allow deletion of custom events (not defaults)
        # Require Engagement Module
        if not has_module_access(guild_id, 'engagement'):
            return JsonResponse({'error': 'Engagement Module required to delete custom boost events'}, status=403)

        with get_db_session() as db:
            event = db.query(XPBoostEvent).filter_by(
                id=int(event_id),
                guild_id=int(guild_id)
            ).first()

            if not event:
                return JsonResponse({'error': 'Boost event not found'}, status=404)

            if event.is_default:
                return JsonResponse({'error': 'Cannot delete default boost events'}, status=400)

            db.delete(event)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Boost event deleted successfully'
            })

    except Exception as e:
        logger.error(f"Error deleting boost event {event_id} for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_xp_boost_event_create(request, guild_id):
    """POST /api/guild/<id>/xp/boost-events/create/ - Create a custom boost event."""
    try:
        import json as json_lib
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import XPBoostEvent
        from .module_utils import has_module_access
        import time

        # Require Engagement Module for custom events
        if not has_module_access(guild_id, 'engagement'):
            return JsonResponse({'error': 'Engagement Module required to create custom boost events'}, status=403)

        # Validate required fields
        name = data.get('name', '').strip()
        if not name:
            return JsonResponse({'error': 'Event name is required'}, status=400)
        if len(name) > 255:
            return JsonResponse({'error': 'Event name must be 255 characters or less'}, status=400)

        description = data.get('description', '').strip()

        # Validate multiplier
        try:
            multiplier = float(data.get('multiplier', 2.0))
            if multiplier < 1.0 or multiplier > 10.0:
                return JsonResponse({'error': 'Multiplier must be between 1.0 and 10.0'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid multiplier value'}, status=400)

        # Validate scope
        scope = data.get('scope', 'server')
        if scope not in ['server', 'role', 'channel']:
            return JsonResponse({'error': 'Invalid scope. Must be server, role, or channel'}, status=400)

        # Validate scope_id if scope is role or channel
        scope_id = None
        if scope in ['role', 'channel']:
            scope_id_str = data.get('scope_id', '').strip()
            if not scope_id_str:
                return JsonResponse({'error': f'Scope ID is required when scope is {scope}'}, status=400)
            try:
                scope_id = int(scope_id_str)
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid scope ID'}, status=400)

        # Validate token bonus
        try:
            token_bonus = int(data.get('token_bonus', 0))
            if token_bonus < 0:
                return JsonResponse({'error': 'Token bonus cannot be negative'}, status=400)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid token bonus value'}, status=400)

        # Parse timing fields
        start_time = None
        end_time = None
        if 'start_time' in data and data['start_time']:
            try:
                start_time = int(data['start_time'])
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid start time'}, status=400)

        if 'end_time' in data and data['end_time']:
            try:
                end_time = int(data['end_time'])
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid end time'}, status=400)

        # Validate end_time is after start_time
        if start_time and end_time and end_time <= start_time:
            return JsonResponse({'error': 'End time must be after start time'}, status=400)

        # Parse announcement fields
        announcement_channel_id = None
        announcement_role_id = None
        if 'announcement_channel_id' in data and data['announcement_channel_id']:
            try:
                announcement_channel_id = int(data['announcement_channel_id'])
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid announcement channel ID'}, status=400)

        if 'announcement_role_id' in data and data['announcement_role_id']:
            try:
                announcement_role_id = int(data['announcement_role_id'])
            except (ValueError, TypeError):
                return JsonResponse({'error': 'Invalid announcement role ID'}, status=400)

        current_time = int(time.time())

        with get_db_session() as db:
            # Create new boost event
            new_event = XPBoostEvent(
                guild_id=int(guild_id),
                name=name,
                description=description or None,
                multiplier=multiplier,
                start_time=start_time,
                end_time=end_time,
                is_active=False,
                is_default=False,  # Custom events are not defaults
                scope=scope,
                scope_id=scope_id,
                token_bonus=token_bonus,
                announcement_channel_id=announcement_channel_id,
                announcement_role_id=announcement_role_id,
                created_at=current_time,
                updated_at=current_time
            )

            db.add(new_event)
            db.commit()
            db.refresh(new_event)

            return JsonResponse({
                'success': True,
                'message': 'Boost event created successfully',
                'event': {
                    'id': new_event.id,
                    'name': new_event.name,
                    'description': new_event.description,
                    'multiplier': float(new_event.multiplier),
                    'start_time': new_event.start_time,
                    'end_time': new_event.end_time,
                    'is_active': new_event.is_active,
                    'is_default': new_event.is_default,
                    'scope': new_event.scope,
                    'scope_id': str(new_event.scope_id) if new_event.scope_id else None,
                    'token_bonus': new_event.token_bonus,
                    'announcement_channel_id': str(new_event.announcement_channel_id) if new_event.announcement_channel_id else None,
                    'announcement_role_id': str(new_event.announcement_role_id) if new_event.announcement_role_id else None,
                }
            })

    except Exception as e:
        logger.error(f"Error creating boost event for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# Role Management Dashboard (with CSV Import - Pro/Premium)

@discord_required
def guild_roles(request, guild_id):
    """Role management page for a guild."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    # Fetch guild info including subscription tier
    is_premium = False
    pending_actions = []
    recent_imports = []
    guild_record = None

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

    # Check if guild has roles module access
    has_roles_module = has_module_access(guild_id, 'roles')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'is_premium': is_premium,
        'pending_actions': pending_actions,
        'recent_imports': recent_imports,
        'has_roles_module': has_roles_module,
        'has_any_module': has_any_module,
        'active_page': 'roles',
    }
    return render(request, 'questlog/roles.html', context)


def _serialize_reaction_role_menus(db, guild_id, message_id=None):
    """Build reaction role menu payloads grouped by message_id."""
    from .models import ReactRole

    query = db.query(ReactRole).filter_by(guild_id=int(guild_id))
    if message_id is not None:
        query = query.filter_by(message_id=int(message_id))

    roles = query.all()
    menus = {}

    for rr in roles:
        menu = menus.get(rr.message_id)
        if not menu:
            menu = {
                'id': rr.message_id,
                'message_id': str(rr.message_id),
                'channel_id': str(rr.channel_id),
                'title': None,
                'description': None,
                'enabled': True,
                'roles': []
            }
            menus[rr.message_id] = menu

        menu['roles'].append({
            'id': rr.id,
            'emoji': rr.emoji,
            'role_id': str(rr.role_id),
            'role_name': rr.role_name or '',
            'remove_on_unreact': bool(rr.remove_on_unreact),
            'exclusive_group': rr.exclusive_group or ''
        })

    results = []
    for menu in menus.values():
        menu['role_count'] = len(menu['roles'])
        results.append(menu)

    # Try to hydrate title/description from the Discord message embed
    bot_session = get_bot_session(int(guild_id))
    if bot_session:
        for menu in results:
            try:
                resp = bot_session.get(f"/channels/{menu['channel_id']}/messages/{menu['message_id']}")
                if resp.status_code == 200:
                    msg_json = resp.json()
                    embeds = msg_json.get('embeds', [])
                    if embeds:
                        embed = embeds[0]
                        menu['title'] = embed.get('title') or menu['title'] or f"Menu #{menu['message_id']}"
                        menu['description'] = embed.get('description') or menu['description'] or ''
                    else:
                        menu['title'] = menu['title'] or f"Menu #{menu['message_id']}"
                        menu['description'] = menu['description'] or ''
                else:
                    menu['title'] = menu['title'] or f"Menu #{menu['message_id']}"
                    menu['description'] = menu['description'] or ''
            except Exception as e:
                logger.warning(f"Could not fetch reaction role message {menu['message_id']}: {e}")
                menu['title'] = menu['title'] or f"Menu #{menu['message_id']}"
                menu['description'] = menu['description'] or ''
    else:
        for menu in results:
            menu['title'] = menu['title'] or f"Menu #{menu['message_id']}"
            menu['description'] = menu['description'] or ''

    # If a specific menu was requested, return it directly
    if message_id is not None:
        return results[0] if results else None

    return results


@discord_required
def guild_reaction_roles(request, guild_id):
    """Reaction roles management page for a guild."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    # Fetch reaction role menus from database
    reaction_menus = []
    guild_record = None

    try:
        from .db import get_db_session
        from .models import Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            reaction_menus = _serialize_reaction_role_menus(db, guild_id)
    except Exception as e:
        logger.warning(f"Could not fetch reaction role menus: {e}")

    # Check if guild has roles module access
    has_roles_module = has_module_access(guild_id, 'roles')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'reaction_menus': reaction_menus,
        'has_roles_module': has_roles_module,
        'has_any_module': has_any_module,
        'active_page': 'reaction_roles',
    }
    return render(request, 'questlog/reaction_roles.html', context)


@require_http_methods(["GET", "POST"])
@api_auth_required
def api_reaction_roles(request, guild_id):
    """
    GET /api/guild/<id>/reaction-roles/ - List reaction role menus
    POST /api/guild/<id>/reaction-roles/ - Create and deploy a new reaction role menu
    """
    try:
        from .db import get_db_session
        from .models import ReactRole
        from urllib.parse import quote

        guild_id_int = int(guild_id)

        if request.method == "GET":
            with get_db_session() as db:
                menus = _serialize_reaction_role_menus(db, guild_id)
                return JsonResponse({'success': True, 'menus': menus})

        # POST - create menu and send message
        try:
            data = json_lib.loads(request.body)
        except json_lib.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        channel_id = data.get('channel_id')
        roles_data = data.get('roles', [])
        title = data.get('title') or 'Choose your roles'
        description = data.get('description') or ''

        # Bot session required to post message and add reactions
        bot_session = get_bot_session(guild_id_int)
        if not bot_session:
            return JsonResponse({'error': 'Bot not connected to this guild'}, status=400)

        try:
            channel_id_int = int(channel_id)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'channel_id is required'}, status=400)

        if not isinstance(roles_data, list) or len(roles_data) == 0:
            return JsonResponse({'error': 'At least one role entry is required'}, status=400)

        parsed_roles = []
        seen_emojis = set()
        for item in roles_data:
            emoji = (item.get('emoji') or '').strip()
            role_id = item.get('role_id')
            if not emoji or not role_id:
                return JsonResponse({'error': 'Each entry needs emoji and role_id'}, status=400)
            if emoji in seen_emojis:
                return JsonResponse({'error': f'Duplicate emoji "{emoji}" in menu'}, status=400)
            seen_emojis.add(emoji)

            try:
                role_id_int = int(role_id)
            except (TypeError, ValueError):
                return JsonResponse({'error': 'role_id must be numeric'}, status=400)

            parsed_roles.append({
                'emoji': emoji,
                'role_id': role_id_int,
                'role_name': item.get('role_name') or '',
                'remove_on_unreact': bool(item.get('remove_on_unreact', True)),
                'exclusive_group': (item.get('exclusive_group') or '').strip() or None,
            })

        # Build embed description
        lines = []
        if description:
            lines.append(description)
            lines.append('')
        for entry in parsed_roles:
            role_display = entry['role_name'] or f"Role {entry['role_id']}"
            flags = []
            if entry['exclusive_group']:
                flags.append(f"Group: {entry['exclusive_group']}")
            if not entry['remove_on_unreact']:
                flags.append("Keeps role on unreact")
            flags_text = f" ({'; '.join(flags)})" if flags else ''
            lines.append(f"{entry['emoji']} — {role_display}{flags_text}")

        embed_description = "\n".join(lines) if lines else "Choose your roles below."

        # Send message via bot
        message_payload = {
            'content': '',
            'embeds': [{
                'title': title,
                'description': embed_description,
                'color': 0xF6C454
            }]
        }

        msg_resp = bot_session.post(f'/channels/{channel_id_int}/messages', json=message_payload)
        if msg_resp.status_code not in (200, 201):
            logger.error(f"Failed to send reaction role message: {msg_resp.status_code} {msg_resp.text}")
            return JsonResponse({'error': 'Failed to send message to channel'}, status=500)

        msg_json = msg_resp.json()
        try:
            message_id_int = int(msg_json.get('id'))
        except (TypeError, ValueError):
            logger.error(f"Reaction role message response missing ID: {msg_json}")
            return JsonResponse({'error': 'Failed to send message to channel'}, status=500)

        # Add reactions
        for entry in parsed_roles:
            try:
                emoji_encoded = quote(entry['emoji'])
                react_resp = bot_session.put(f'/channels/{channel_id_int}/messages/{message_id_int}/reactions/{emoji_encoded}/@me')
                if react_resp.status_code not in (200, 204):
                    logger.warning(f"Failed to add reaction {entry['emoji']} to message {message_id_int}: {react_resp.status_code} {react_resp.text}")
            except Exception as react_err:
                logger.warning(f"Error adding reaction {entry['emoji']} to message {message_id_int}: {react_err}")

        with get_db_session() as db:
            for entry in parsed_roles:
                db.add(ReactRole(
                    guild_id=guild_id_int,
                    message_id=message_id_int,
                    channel_id=channel_id_int,
                    emoji=entry['emoji'],
                    role_id=entry['role_id'],
                    role_name=entry['role_name'],
                    remove_on_unreact=entry['remove_on_unreact'],
                    exclusive_group=entry['exclusive_group']
                ))

            db.flush()
            menu = _serialize_reaction_role_menus(db, guild_id, message_id_int)

            return JsonResponse({'success': True, 'menu': menu})

    except Exception as e:
        logger.error(f"Error handling reaction roles: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET", "PUT", "DELETE"])
@api_auth_required
def api_reaction_role_detail(request, guild_id, message_id):
    """
    GET /api/guild/<id>/reaction-roles/<message_id>/ - Get a menu
    PUT /api/guild/<id>/reaction-roles/<message_id>/ - Update menu roles and message
    DELETE /api/guild/<id>/reaction-roles/<message_id>/ - Delete menu (and message)
    """
    try:
        from .db import get_db_session
        from .models import ReactRole
        from urllib.parse import quote

        guild_id_int = int(guild_id)

        try:
            message_id_int = int(message_id)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'Invalid message_id'}, status=400)

        if request.method == "GET":
            with get_db_session() as db:
                menu = _serialize_reaction_role_menus(db, guild_id, message_id_int)
                if not menu:
                    return JsonResponse({'error': 'Menu not found'}, status=404)
                return JsonResponse({'success': True, 'menu': menu})

        if request.method == "DELETE":
            with get_db_session() as db:
                existing = db.query(ReactRole).filter_by(
                    guild_id=guild_id_int,
                    message_id=message_id_int
                ).all()
                channel_id = existing[0].channel_id if existing else None
                deleted = db.query(ReactRole).filter_by(
                    guild_id=guild_id_int,
                    message_id=message_id_int
                ).delete()

            if deleted == 0:
                return JsonResponse({'error': 'Menu not found'}, status=404)

            # Attempt to delete the Discord message too
            if channel_id:
                bot_session = get_bot_session(guild_id_int)
                if bot_session:
                    bot_session.delete(f'/channels/{channel_id}/messages/{message_id_int}')

            return JsonResponse({'success': True})

        # PUT - update menu
        try:
            data = json_lib.loads(request.body)
        except json_lib.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        channel_id = data.get('channel_id')
        roles_data = data.get('roles', [])
        title = data.get('title') or 'Choose your roles'
        description = data.get('description') or ''

        try:
            channel_id_int = int(channel_id)
        except (TypeError, ValueError):
            return JsonResponse({'error': 'channel_id is required'}, status=400)

        if not isinstance(roles_data, list) or len(roles_data) == 0:
            return JsonResponse({'error': 'At least one role entry is required'}, status=400)

        # Normalize roles: keep last occurrence per role, then last per emoji
        entries = []
        for item in roles_data:
            emoji = (item.get('emoji') or '').strip()
            role_id = item.get('role_id')
            if not emoji or not role_id:
                return JsonResponse({'error': 'Each entry needs emoji and role_id'}, status=400)
            try:
                role_id_int = int(role_id)
            except (TypeError, ValueError):
                return JsonResponse({'error': 'role_id must be numeric'}, status=400)
            entries.append({
                'emoji': emoji,
                'role_id': role_id_int,
                'role_name': item.get('role_name') or '',
                'remove_on_unreact': bool(item.get('remove_on_unreact', True)),
                'exclusive_group': (item.get('exclusive_group') or '').strip() or None,
            })

        # Last entry per role_id wins
        by_role = {}
        for entry in entries:
            by_role[entry['role_id']] = entry

        # Preserve only the final value per role
        parsed_roles = list(by_role.values())

        bot_session = get_bot_session(guild_id_int)
        if not bot_session:
            return JsonResponse({'error': 'Bot not connected to this guild'}, status=400)

        # Build embed description
        lines = []
        if description:
            lines.append(description)
            lines.append('')
        for entry in parsed_roles:
            role_display = entry['role_name'] or f"Role {entry['role_id']}"
            flags = []
            if entry['exclusive_group']:
                flags.append(f"Group: {entry['exclusive_group']}")
            if not entry['remove_on_unreact']:
                flags.append("Keeps role on unreact")
            flags_text = f" ({'; '.join(flags)})" if flags else ''
            lines.append(f"{entry['emoji']} — {role_display}{flags_text}")

        embed_description = "\n".join(lines) if lines else "Choose your roles below."

        logger.info(f"[ReactionRole PUT] Updating message {message_id_int}: {len(parsed_roles)} roles, new emojis: {[e['emoji'] for e in parsed_roles]}")

        with get_db_session() as db:
            existing = db.query(ReactRole).filter_by(
                guild_id=guild_id_int,
                message_id=message_id_int
            ).all()
            if not existing:
                return JsonResponse({'error': 'Menu not found'}, status=404)

            # Get old emojis so we can remove them from the message
            old_emojis = {record.emoji for record in existing}
            logger.info(f"[ReactionRole PUT] Old emojis: {old_emojis}")

            # Delete existing rows for this menu
            db.query(ReactRole).filter_by(
                guild_id=guild_id_int,
                message_id=message_id_int
            ).delete()
            db.commit()

        # Update the existing Discord message (PATCH instead of delete/recreate)
        message_payload = {
            'embeds': [{
                'title': title,
                'description': embed_description,
                'color': 0xF6C454
            }]
        }
        logger.info(f"[ReactionRole PUT] Sending PATCH to Discord: {message_payload}")

        try:
            patch_resp = bot_session.patch(
                f'/channels/{channel_id_int}/messages/{message_id_int}',
                json=message_payload
            )
            logger.info(f"[ReactionRole PUT] Discord PATCH response: {patch_resp.status_code}")
            if patch_resp.status_code not in (200, 201):
                logger.error(f"Failed to update message {message_id_int}: {patch_resp.status_code} {patch_resp.text}")
                return JsonResponse({'error': 'Failed to update message on Discord'}, status=500)
        except Exception as patch_err:
            logger.error(f"Error updating reaction-role message: {patch_err}", exc_info=True)
            return JsonResponse({'error': 'Failed to update message on Discord'}, status=500)

        # Remove old reactions that are no longer in the new config
        new_emojis = {entry['emoji'] for entry in parsed_roles}
        emojis_to_remove = old_emojis - new_emojis
        logger.info(f"[ReactionRole PUT] Removing old emojis: {emojis_to_remove}, keeping: {new_emojis}")

        for emoji in emojis_to_remove:
            try:
                emoji_encoded = quote(emoji)
                logger.info(f"[ReactionRole PUT] Deleting reaction {emoji} (encoded: {emoji_encoded})")
                del_resp = bot_session.delete(f'/channels/{channel_id_int}/messages/{message_id_int}/reactions/{emoji_encoded}')
                logger.info(f"[ReactionRole PUT] Delete reaction response: {del_resp.status_code}")
            except Exception as remove_err:
                logger.warning(f"Error removing old reaction {emoji} from message {message_id_int}: {remove_err}")

        # Add new reactions (Discord API is idempotent, so re-adding existing ones is safe)
        for entry in parsed_roles:
            try:
                emoji_encoded = quote(entry['emoji'])
                logger.info(f"[ReactionRole PUT] Adding reaction {entry['emoji']} (encoded: {emoji_encoded})")
                react_resp = bot_session.put(f'/channels/{channel_id_int}/messages/{message_id_int}/reactions/{emoji_encoded}/@me')
                logger.info(f"[ReactionRole PUT] Add reaction response: {react_resp.status_code}")
            except Exception as react_err:
                logger.warning(f"Error adding reaction {entry['emoji']} to message {message_id_int}: {react_err}")

        # Persist new rows with same message_id
        with get_db_session() as db:
            for entry in parsed_roles:
                db.add(ReactRole(
                    guild_id=guild_id_int,
                    message_id=message_id_int,
                    channel_id=channel_id_int,
                    emoji=entry['emoji'],
                    role_id=entry['role_id'],
                    role_name=entry['role_name'],
                    remove_on_unreact=entry['remove_on_unreact'],
                    exclusive_group=entry['exclusive_group']
                ))
            db.commit()
            menu = _serialize_reaction_role_menus(db, guild_id, message_id_int)

        return JsonResponse({'success': True, 'menu': menu})

    except Exception as e:
        logger.error(f"Error handling reaction role menu {message_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
@ratelimit(key='user_or_ip', rate='20/m', method='POST', block=True)
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
        from .actions import queue_action, ActionType

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        # Prepare payload
        payload = {
            'user_id': int(user_id),
            'role_id': int(role_id),
            'reason': reason
        }

        if action == 'add':
            action_id = queue_action(
                guild_id=int(guild_id),
                action_type=ActionType.ROLE_ADD,
                payload=payload,
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name,
                source='website'
            )
        elif action == 'remove':
            action_id = queue_action(
                guild_id=int(guild_id),
                action_type=ActionType.ROLE_REMOVE,
                payload=payload,
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name,
                source='website'
            )
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)

        return JsonResponse({
            'success': True,
            'action_id': action_id,
            'message': f'Role {action} queued (ID: {action_id})'
        })

    except Exception as e:
        logger.error(f"Error queuing role action: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
@require_subscription_tier('pro', 'premium')
@ratelimit(key='user_or_ip', rate='5/h', method='POST', block=True)
def api_role_bulk_import(request, guild_id):
    """POST /api/guild/<id>/roles/import/ - Import XLSX for bulk role assignment (Pro/Premium only, 5 req/hour)."""
    # Check subscription tier and determine limits
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel, SubscriptionTier

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Determine import limit based on tier
            # Free tier blocked by @require_subscription_tier decorator
            # VIP and Premium: Unlimited
            # Pro: 10 users
            if guild_record.is_vip or guild_record.subscription_tier == SubscriptionTier.PREMIUM.value:
                max_users = None  # Unlimited
            else:  # Pro tier
                max_users = 10
    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)

    # Get uploaded file
    excel_file = request.FILES.get('file')
    if not excel_file:
        return JsonResponse({'error': 'No file uploaded'}, status=400)

    role_id = request.POST.get('role_id')
    action = request.POST.get('action', 'add')  # 'add' or 'remove'

    if not role_id:
        return JsonResponse({'error': 'Missing role_id'}, status=400)

    try:
        from openpyxl import load_workbook
        from io import BytesIO
        from .actions import (
            queue_bulk_role_add, create_bulk_import_job, update_bulk_import_progress
        )

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        # Read XLSX file
        wb = load_workbook(BytesIO(excel_file.read()), read_only=True, data_only=True)
        ws = wb.active

        # Get header row
        headers = [cell.value for cell in ws[1]]

        # Find user_id column (flexible column names)
        user_id_col = None
        for idx, header in enumerate(headers):
            if header and str(header).lower() in ['user_id', 'discord_id', 'id']:
                user_id_col = idx
                break

        if user_id_col is None:
            return JsonResponse({
                'error': 'No user_id column found. Expected columns: user_id, discord_id, or id'
            }, status=400)

        user_ids = []
        errors = []

        # Read data rows (skip header)
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row or row_num > 10001:  # Limit to 10,000 rows
                break

            user_id = row[user_id_col] if user_id_col < len(row) else None

            if user_id:
                # Convert to string first, then to int (handles TEXT formatted cells)
                user_id_str = str(user_id).strip()
                try:
                    user_ids.append(int(user_id_str))
                except ValueError:
                    errors.append({'row': row_num, 'error': f'Invalid user_id: {user_id_str}'})
            else:
                errors.append({'row': row_num, 'error': 'Missing user_id'})

        wb.close()

        if not user_ids:
            return JsonResponse({
                'error': 'No valid user IDs found in XLSX',
                'parse_errors': errors
            }, status=400)

        # Check daily bulk limit (replaces simple per-operation check)
        allowed, error_msg, usage_info = check_daily_bulk_limit(
            guild_id, 'role_bulk', len(user_ids), guild_record
        )

        if not allowed:
            return JsonResponse({
                'error': error_msg,
                'limit_exceeded': True,
                'usage_info': usage_info
            }, status=403)

        # Create bulk import job for tracking
        job_id = create_bulk_import_job(
            guild_id=int(guild_id),
            job_type='role_assign',
            filename=excel_file.name,
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
                reason=f'Bulk import from {excel_file.name}',
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
                source='xlsx_import'
            )

        # Record usage for daily tracking
        record_bulk_usage(guild_id, 'role_bulk', len(user_ids))

        return JsonResponse({
            'success': True,
            'job_id': job_id,
            'action_id': action_id,
            'total_users': len(user_ids),
            'parse_errors': errors[:10] if errors else [],  # Return first 10 errors
            'message': f'Queued bulk {action} for {len(user_ids)} users'
        })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@api_auth_required
def api_role_export_template(request, guild_id):
    """GET /api/guild/<id>/roles/export-template/ - Export blank XLSX template for bulk role import."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from io import BytesIO
        from django.http import HttpResponse

        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Role Import Template"

        # Add headers with formatting
        headers = ['user_id']
        ws.append(headers)

        # Style header row
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")

        # Add a few example rows with instructions
        ws.append(['1234567890123456'])  # Example Discord ID
        ws.append(['9876543210987654'])  # Example Discord ID

        # Format user_id column as TEXT (prevents scientific notation)
        for row in range(2, ws.max_row + 1):
            ws.cell(row=row, column=1).number_format = '@'

        # Set column width
        ws.column_dimensions['A'].width = 20

        # Add instructions sheet
        ws_info = wb.create_sheet(title="Instructions")
        ws_info['A1'] = "Bulk Role Import Instructions"
        ws_info['A1'].font = Font(bold=True, size=14)

        instructions = [
            "",
            "How to use this template:",
            "1. Fill in the 'user_id' column with Discord user IDs",
            "2. Delete the example rows",
            "3. Save the file",
            "4. Upload it via the Bulk Import button",
            "5. Select the role to assign/remove",
            "",
            "Tips:",
            "- User IDs are 17-19 digit numbers",
            "- You can export current server members from Discord",
            "- The user_id column is pre-formatted as TEXT to prevent Excel issues",
            "- Maximum 10,000 rows per import",
        ]

        for i, instruction in enumerate(instructions, start=2):
            ws_info[f'A{i}'] = instruction

        ws_info.column_dimensions['A'].width = 70

        # Save to BytesIO
        excel_file = BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)

        # Return as download
        response = HttpResponse(
            excel_file.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="role_import_template.xlsx"'
        return response

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@api_auth_required
def api_role_export_current(request, guild_id):
    """GET /api/guild/<id>/roles/export-roles/ - Export all guild roles with their permissions."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from io import BytesIO
        from django.http import HttpResponse
        from datetime import datetime

        # Get bot session
        guild_id_int = int(guild_id)
        bot_session = get_bot_session(guild_id_int)
        if not bot_session:
            return JsonResponse({'error': 'Bot not connected to this guild'}, status=400)

        # Fetch guild roles
        roles_resp = bot_session.get(f'/guilds/{guild_id_int}/roles')
        if roles_resp.status_code != 200:
            logger.error(f"Failed to fetch roles: {roles_resp.status_code} {roles_resp.text}")
            return JsonResponse({'error': 'Failed to fetch roles from Discord'}, status=500)

        roles_data = roles_resp.json()

        # Discord permission flags (all major permissions)
        permission_flags = [
            ('create_instant_invite', 0x1),
            ('kick_members', 0x2),
            ('ban_members', 0x4),
            ('administrator', 0x8),
            ('manage_channels', 0x10),
            ('manage_guild', 0x20),
            ('add_reactions', 0x40),
            ('view_audit_log', 0x80),
            ('priority_speaker', 0x100),
            ('stream', 0x200),
            ('view_channel', 0x400),
            ('send_messages', 0x800),
            ('send_tts_messages', 0x1000),
            ('manage_messages', 0x2000),
            ('embed_links', 0x4000),
            ('attach_files', 0x8000),
            ('read_message_history', 0x10000),
            ('mention_everyone', 0x20000),
            ('use_external_emojis', 0x40000),
            ('view_guild_insights', 0x80000),
            ('connect', 0x100000),
            ('speak', 0x200000),
            ('mute_members', 0x400000),
            ('deafen_members', 0x800000),
            ('move_members', 0x1000000),
            ('use_vad', 0x2000000),
            ('change_nickname', 0x4000000),
            ('manage_nicknames', 0x8000000),
            ('manage_roles', 0x10000000),
            ('manage_webhooks', 0x20000000),
            ('manage_expressions', 0x40000000),
            ('use_application_commands', 0x80000000),
            ('request_to_speak', 0x100000000),
            ('manage_events', 0x200000000),
            ('manage_threads', 0x400000000),
            ('create_public_threads', 0x800000000),
            ('create_private_threads', 0x1000000000),
            ('use_external_stickers', 0x2000000000),
            ('send_messages_in_threads', 0x4000000000),
            ('use_embedded_activities', 0x8000000000),
            ('moderate_members', 0x10000000000),
        ]

        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Role Definitions"

        # Build headers: basic info + all permissions
        headers = ['role_id', 'name', 'color', 'position', 'hoist', 'mentionable', 'permissions_value']
        headers.extend([perm[0] for perm in permission_flags])
        ws.append(headers)

        # Style header row
        for idx, cell in enumerate(ws[1], 1):
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        # Add role data
        for role in sorted(roles_data, key=lambda r: r.get('position', 0), reverse=True):
            permissions_int = int(role.get('permissions', 0))

            # Build row with basic info
            row_data = [
                str(role.get('id', '')),
                str(role.get('name', '')),
                str(role.get('color', '0')),
                str(role.get('position', '0')),
                'TRUE' if role.get('hoist', False) else 'FALSE',
                'TRUE' if role.get('mentionable', False) else 'FALSE',
                str(permissions_int)
            ]

            # Add permission flags
            for perm_name, perm_value in permission_flags:
                has_permission = bool(permissions_int & perm_value)
                row_data.append('TRUE' if has_permission else 'FALSE')

            ws.append(row_data)

        # Format all cells as TEXT
        for row in range(1, ws.max_row + 1):
            for col in range(1, ws.max_column + 1):
                cell = ws.cell(row=row, column=col)
                cell.number_format = '@'

        # Set column widths
        ws.column_dimensions['A'].width = 20  # role_id
        ws.column_dimensions['B'].width = 25  # name
        ws.column_dimensions['C'].width = 12  # color
        ws.column_dimensions['D'].width = 10  # position
        ws.column_dimensions['E'].width = 10  # hoist
        ws.column_dimensions['F'].width = 12  # mentionable
        ws.column_dimensions['G'].width = 20  # permissions_value

        # Set permission column widths
        for col_idx in range(8, ws.max_column + 1):
            ws.column_dimensions[ws.cell(1, col_idx).column_letter].width = 18

        # Freeze header row
        ws.freeze_panes = 'A2'

        # Save to BytesIO
        excel_file = BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)

        # Return as download
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse(
            excel_file.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="guild_{guild_id}_role_definitions_{timestamp}.xlsx"'
        return response

    except Exception as e:
        logger.error(f"Role export error: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_role_create(request, guild_id):
    """POST /api/guild/<id>/roles/create/ - Create a new Discord role."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    required = ['name']
    for field in required:
        if field not in data:
            return JsonResponse({'error': f'Missing required field: {field}'}, status=400)

    try:
        # Get bot session
        guild_id_int = int(guild_id)
        bot_session = get_bot_session(guild_id_int)
        if not bot_session:
            return JsonResponse({'error': 'Bot not connected to this guild'}, status=400)

        # Prepare role data for Discord API
        role_data = {
            'name': data['name'],
            'permissions': str(data.get('permissions', '0')),
            'color': int(data.get('color', 0)),
            'hoist': bool(data.get('hoist', False)),
            'mentionable': bool(data.get('mentionable', False)),
        }

        # Create role via Discord API
        resp = bot_session.post(f'/guilds/{guild_id_int}/roles', json=role_data)

        if resp.status_code == 200:
            role = resp.json()

            # If a position was requested, attempt to move the role using Discord's bulk role move
            desired_position = data.get('position')
            if desired_position is not None:
                try:
                    desired_position = int(desired_position)
                    patch_resp = bot_session.patch(
                        f'/guilds/{guild_id_int}/roles',
                        json=[{'id': role['id'], 'position': desired_position}]
                    )
                    if patch_resp.status_code != 200:
                        logger.warning(
                            f"Failed to set role position for role {role['id']} in guild {guild_id_int}: "
                            f"{patch_resp.status_code} {patch_resp.text}"
                        )
                except Exception as e:
                    logger.warning(f"Error adjusting role position in guild {guild_id_int}: {e}", exc_info=True)

            return JsonResponse({
                'success': True,
                'message': f'Role "{data["name"]}" created successfully!',
                'role': {
                    'id': role['id'],
                    'name': role['name'],
                    'color': role['color'],
                }
            })
        else:
            error_data = resp.json() if resp.headers.get('content-type') == 'application/json' else {}
            return JsonResponse({
                'error': error_data.get('message', f'Discord API error: {resp.status_code}')
            }, status=500)

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


def _ensure_admin(guild_id, request):
    all_admin_guilds = request.session.get('discord_admin_guilds', [])
    return any(str(g['id']) == str(guild_id) for g in all_admin_guilds)


@login_required
def guild_raffles(request, guild_id):
    """Render raffles dashboard."""
    from .db import get_db_session
    from .module_utils import has_module_access, has_any_module_access

    admin_guilds = request.session.get('discord_admin_guilds', [])
    guild = next((g for g in admin_guilds if str(g.get('id')) == str(guild_id)), None)
    if not guild:
        messages.error(request, "You don't have permission to manage raffles.")
        return redirect('questlog_dashboard')

    # Require Admin or Manage Server
    permissions = int(guild.get('permissions', 0))
    is_admin = (permissions & 0x8) == 0x8 or (permissions & 0x20) == 0x20
    if not is_admin:
        messages.error(request, "You need Admin or Manage Server permission.")
        return redirect('questlog_dashboard')

    is_vip = False
    subscription_tier = 'free'
    guild_record = None
    try:
        with get_db_session() as db:
            from .models import GuildMember, Guild as GuildModel
            member = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                user_id=int(request.session.get('discord_user', {}).get('id', 0))
            ).first()
            current_tokens = member.hero_tokens if member else 0

            # Get subscription tier info
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if guild_record:
                is_vip = guild_record.is_vip
                subscription_tier = guild_record.subscription_tier if guild_record.subscription_tier else 'free'
                billing_cycle = guild_record.billing_cycle
    except Exception:
        current_tokens = 0
        billing_cycle = None

    # Check if guild has engagement module access
    has_engagement_module = has_module_access(guild_id, 'engagement')
    has_any_module = has_any_module_access(guild_id)

    return render(request, 'questlog/raffles.html', {
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'discord_user': request.session.get('discord_user', {}),
        'is_admin': True,
        'current_tokens': current_tokens,
        'is_vip': is_vip,
        'subscription_tier': subscription_tier,
        'billing_cycle': billing_cycle if 'billing_cycle' in locals() else None,
        'has_engagement_module': has_engagement_module,
        'has_any_module': has_any_module,
        'active_page': 'raffles',
    })


def _raffle_status(raffle):
    import time
    now = int(time.time())
    if raffle.winners:
        return 'completed'
    if not raffle.active:
        return 'closed'
    # Only mark as ended if auto_pick is enabled (bot will handle it)
    # If auto_pick is off, keep it active so admins can manually pick winners
    if raffle.end_at and now > raffle.end_at and raffle.auto_pick:
        return 'ended'
    if raffle.start_at and now < raffle.start_at:
        return 'scheduled'
    return 'active'


def _draw_winners(db, raffle):
    import random
    from .models import RaffleEntry
    entries = db.query(RaffleEntry).filter_by(raffle_id=raffle.id).all()
    if not entries:
        raffle.winners = json_lib.dumps([])
        raffle.active = False
        return []

    population = []
    for e in entries:
        population.append({'user_id': e.user_id, 'username': e.username, 'weight': max(1, e.tickets)})

    # weighted sampling without replacement
    winners = []
    remaining = population[:]
    total_winners = max(1, raffle.max_winners or 1)
    rng = random.SystemRandom()

    for _ in range(total_winners):
        if not remaining:
            break
        total_weight = sum(item['weight'] for item in remaining)
        pick = rng.uniform(0, total_weight)
        cumulative = 0
        chosen = None
        for item in remaining:
            cumulative += item['weight']
            if pick <= cumulative:
                chosen = item
                break
        if chosen:
            winners.append({'user_id': chosen['user_id'], 'username': chosen.get('username')})
            remaining = [r for r in remaining if r['user_id'] != chosen['user_id']]

    raffle.winners = json_lib.dumps(winners)
    raffle.active = False
    return winners


@require_http_methods(["POST"])
@api_auth_required
def api_role_bulk_create(request, guild_id):
    """POST /api/guild/<id>/roles/bulk-create/ - Create multiple roles from XLSX import."""
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded'}, status=400)

    # Check subscription tier and determine limits
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel, SubscriptionTier

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Determine role creation limit based on tier
            # VIP and Premium: Unlimited (cap at 100 for safety)
            # Pro: 10 roles
            # Free: 6 roles
            if guild_record.is_vip or guild_record.subscription_tier == SubscriptionTier.PREMIUM.value:
                max_roles = 100  # Safety limit
            elif guild_record.subscription_tier == SubscriptionTier.PRO.value:
                max_roles = 10
            else:  # Free tier
                max_roles = 6
    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_raffle_list(request, guild_id):
    """List raffles; auto-finalize ended raffles with auto_pick."""
    from .db import get_db_session
    from .models import Raffle, RaffleEntry
    import time
    now = int(time.time())

    try:
        with get_db_session() as db:
            # auto finalize ended raffles that requested auto_pick and have no winners
            auto_raffles = db.query(Raffle).filter(
                Raffle.guild_id == int(guild_id),
                Raffle.active == True,
                Raffle.auto_pick == True,
                Raffle.end_at != None,
                Raffle.end_at < now,
                Raffle.winners == None
            ).all()
            for r in auto_raffles:
                _draw_winners(db, r)
            if auto_raffles:
                db.flush()

            raffles = db.query(Raffle).filter_by(guild_id=int(guild_id)).order_by(Raffle.id.desc()).all()

            active, ended = [], []
            admin = _ensure_admin(guild_id, request)

            for r in raffles:
                entry_count = db.query(RaffleEntry).filter_by(raffle_id=r.id).count()
                winners = []
                if r.winners:
                    try:
                        winners = json_lib.loads(r.winners)
                    except Exception:
                        winners = []

                row = {
                    'id': r.id,
                    'title': r.title,
                    'description': r.description,
                    'cost_tokens': r.cost_tokens,
                    'max_winners': r.max_winners,
                    'start_at': r.start_at,
                    'end_at': r.end_at,
                    'auto_pick': r.auto_pick,
                    'active': r.active,
                    'announce_channel_id': str(r.announce_channel_id) if r.announce_channel_id else None,
                    'announce_role_id': str(r.announce_role_id) if r.announce_role_id else None,
                    'announce_message': r.announce_message,
                    'winner_message': r.winner_message,
                    'entry_emoji': r.entry_emoji,
                    'announce_message_id': str(r.announce_message_id) if r.announce_message_id else None,
                    'reminder_channel_id': str(r.reminder_channel_id) if r.reminder_channel_id else None,
                    'entry_count': entry_count,
                    'winners': winners,
                    'can_manage': admin,
                }

                if _raffle_status(r) in ['completed', 'ended', 'closed']:
                    ended.append(row)
                else:
                    active.append(row)

            return JsonResponse({'active': active, 'ended': ended})
    except Exception as e:
        logger.error(f"Error listing raffles: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to load raffles'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_raffle_create(request, guild_id):
    """Create a raffle (admin only)."""
    from .db import get_db_session
    from .models import Raffle, Guild as GuildModel

    logger.info(f"Raffle create request for guild {guild_id}")

    if not _ensure_admin(guild_id, request):
        logger.warning(f"Permission denied for guild {guild_id}")
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        data = json_lib.loads(request.body)
        logger.info(f"Raffle data received: {data}")
        logger.info(f"Channel ID raw: {data.get('announce_channel_id')} (type: {type(data.get('announce_channel_id'))})")
        logger.info(f"Role ID raw: {data.get('announce_role_id')} (type: {type(data.get('announce_role_id'))})")
    except json_lib.JSONDecodeError as e:
        logger.error(f"Invalid JSON: {e}")
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    def _to_int(val):
        try:
            return int(val) if val else None
        except Exception:
            return None

    try:
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                logger.warning(f"Guild {guild_id} not found in database")
                # Create guild record if it doesn't exist
                guild_record = GuildModel(guild_id=int(guild_id))
                db.add(guild_record)
                db.flush()

            raffle = Raffle(
                guild_id=int(guild_id),
                title=data.get('title', '').strip(),
                description=data.get('description', ''),
                cost_tokens=max(0, int(data.get('cost_tokens', 0))),
                max_winners=max(1, int(data.get('max_winners', 1))),
                start_at=data.get('start_at') or None,
                end_at=data.get('end_at') or None,
                auto_pick=bool(data.get('auto_pick', False)),
                announce_channel_id=_to_int(data.get('announce_channel_id')),
                announce_role_id=_to_int(data.get('announce_role_id')),
                announce_message=(data.get('announce_message') or '').strip(),
                winner_message=(data.get('winner_message') or '').strip(),
                entry_emoji=data.get('entry_emoji') or "🎟️",
                reminder_channel_id=_to_int(data.get('reminder_channel_id')),
                active=True,
                winners=None,
                created_by=_to_int(request.session.get('discord_user', {}).get('id')),
                created_by_name=request.session.get('discord_user', {}).get('username')
            )
            db.add(raffle)
            db.flush()

            logger.info(f"Raffle created successfully with ID: {raffle.id}")

            return JsonResponse({'success': True, 'id': raffle.id})
    except Exception as e:
        logger.error(f"Error creating raffle: {e}", exc_info=True)
        return JsonResponse({'error': f'Failed to create raffle: {str(e)}'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_raffle_update(request, guild_id, raffle_id):
    """Update an existing raffle (admin only)."""
    from .db import get_db_session
    from .models import Raffle
    if not _ensure_admin(guild_id, request):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    def _to_int(val):
        try:
            return int(val)
        except Exception:
            return None

    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        with get_db_session() as db:
            raffle = db.query(Raffle).filter_by(id=raffle_id, guild_id=int(guild_id)).first()
            if not raffle:
                return JsonResponse({'error': 'Raffle not found'}, status=404)

            raffle.title = data.get('title', raffle.title).strip()
            raffle.description = data.get('description', raffle.description)
            raffle.cost_tokens = max(0, int(data.get('cost_tokens', raffle.cost_tokens or 0)))
            raffle.max_winners = max(1, int(data.get('max_winners', raffle.max_winners or 1)))
            raffle.start_at = data.get('start_at') or None
            raffle.end_at = data.get('end_at') or None
            raffle.auto_pick = bool(data.get('auto_pick', raffle.auto_pick))
            raffle.announce_channel_id = _to_int(data.get('announce_channel_id'))
            raffle.announce_role_id = _to_int(data.get('announce_role_id'))
            raffle.announce_message = (data.get('announce_message') or '').strip()
            raffle.winner_message = (data.get('winner_message') or '').strip()
            raffle.entry_emoji = data.get('entry_emoji') or raffle.entry_emoji or "🎟️"
            raffle.reminder_channel_id = _to_int(data.get('reminder_channel_id'))
            # reset announce message id if channel changed so bot can re-post
            if data.get('announce_channel_id') and str(raffle.announce_channel_id) != str(data.get('announce_channel_id')):
                raffle.announce_message_id = None
            return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error updating raffle: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to update raffle'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_raffle_enter(request, guild_id, raffle_id):
    """Enter a raffle using tokens."""
    from .db import get_db_session
    from .models import Raffle, RaffleEntry, GuildMember
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    tickets = max(1, int(data.get('tickets', 1)))
    discord_user = request.session.get('discord_user', {})

    try:
        with get_db_session() as db:
            raffle = db.query(Raffle).filter_by(id=raffle_id, guild_id=int(guild_id)).first()
            if not raffle:
                return JsonResponse({'error': 'Raffle not found'}, status=404)

            # status checks
            status = _raffle_status(raffle)
            if status == 'completed':
                return JsonResponse({'error': 'Raffle already completed'}, status=400)
            if status == 'closed':
                return JsonResponse({'error': 'Raffle closed'}, status=400)

            import time
            now = int(time.time())
            if raffle.start_at and now < raffle.start_at:
                return JsonResponse({'error': 'Raffle has not started yet'}, status=400)
            if raffle.end_at and now > raffle.end_at:
                return JsonResponse({'error': 'Raffle has ended'}, status=400)

            member = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                user_id=int(discord_user.get('id', 0))
            ).first()
            if not member:
                return JsonResponse({'error': 'You must interact in the server first.'}, status=400)

            cost = raffle.cost_tokens * tickets
            if member.hero_tokens < cost:
                return JsonResponse({'error': f'Not enough tokens. Need {cost}, have {member.hero_tokens}.'}, status=400)

            member.hero_tokens -= cost
            entry = RaffleEntry(
                raffle_id=raffle.id,
                user_id=int(discord_user.get('id')),
                username=discord_user.get('username'),
                tickets=tickets
            )
            db.add(entry)

            return JsonResponse({
                'success': True,
                'message': 'Entry submitted!',
                'tokens_remaining': member.hero_tokens
            })
    except Exception as e:
        logger.error(f"Error entering raffle: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to enter raffle'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_raffle_pick(request, guild_id, raffle_id):
    """Pick winners (admin only)."""
    from .db import get_db_session
    from .models import Raffle
    if not _ensure_admin(guild_id, request):
        return JsonResponse({'error': 'Permission denied'}, status=403)

    try:
        with get_db_session() as db:
            raffle = db.query(Raffle).filter_by(id=raffle_id, guild_id=int(guild_id)).first()
            if not raffle:
                return JsonResponse({'error': 'Raffle not found'}, status=404)

            winners = _draw_winners(db, raffle)
            return JsonResponse({
                'success': True,
                'message': 'Winners selected!' if winners else 'No entries to draw from.',
                'winners': winners
            })
    except Exception as e:
        logger.error(f"Error picking winners: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to pick winners'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_raffle_start_now(request, guild_id, raffle_id):
    """Manually start a raffle immediately (set start_at to now and clear announce message so bot can post)."""
    from .db import get_db_session
    from .models import Raffle
    if not _ensure_admin(guild_id, request):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    import time
    now = int(time.time())
    try:
        with get_db_session() as db:
            raffle = db.query(Raffle).filter_by(id=raffle_id, guild_id=int(guild_id)).first()
            if not raffle:
                return JsonResponse({'error': 'Raffle not found'}, status=404)
            raffle.start_at = now
            raffle.active = True
            raffle.announce_message_id = None
            # if no end supplied, leave as None and rely on manual end/pick
            return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error starting raffle {raffle_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to start raffle'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_raffle_end_now(request, guild_id, raffle_id):
    """Manually end a raffle immediately; marks end_at and triggers draw if auto_pick."""
    from .db import get_db_session
    from .models import Raffle
    if not _ensure_admin(guild_id, request):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    import time
    now = int(time.time())
    try:
        with get_db_session() as db:
            raffle = db.query(Raffle).filter_by(id=raffle_id, guild_id=int(guild_id)).first()
            if not raffle:
                return JsonResponse({'error': 'Raffle not found'}, status=404)
            raffle.end_at = now
            raffle.active = False
            if raffle.auto_pick:
                _draw_winners(db, raffle)
            return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error ending raffle {raffle_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to end raffle'}, status=500)

    excel_file = request.FILES['file']

    try:
        from openpyxl import load_workbook
        from io import BytesIO

        # Get bot session
        guild_id_int = int(guild_id)
        bot_session = get_bot_session(guild_id_int)
        if not bot_session:
            return JsonResponse({'error': 'Bot not connected to this guild'}, status=400)

        # Read XLSX file
        wb = load_workbook(BytesIO(excel_file.read()), read_only=True, data_only=True)
        ws = wb.active

        # Get header row
        headers = [cell.value for cell in ws[1]]

        # Find required columns
        name_col = next((i for i, h in enumerate(headers) if h and str(h).lower() == 'name'), None)
        color_col = next((i for i, h in enumerate(headers) if h and str(h).lower() == 'color'), None)
        permissions_col = next((i for i, h in enumerate(headers) if h and str(h).lower() == 'permissions'), None)
        hoist_col = next((i for i, h in enumerate(headers) if h and str(h).lower() == 'hoist'), None)
        mentionable_col = next((i for i, h in enumerate(headers) if h and str(h).lower() == 'mentionable'), None)

        if name_col is None:
            return JsonResponse({'error': 'Missing required column: name'}, status=400)

        roles_created = []
        errors = []

        # Count total roles first to check limits
        total_rows = sum(1 for _ in ws.iter_rows(min_row=2, values_only=True))

        # Check daily bulk limit
        allowed, error_msg, usage_info = check_daily_bulk_limit(
            guild_id, 'role_create', total_rows, guild_record
        )

        if not allowed:
            return JsonResponse({
                'error': error_msg,
                'limit_exceeded': True,
                'usage_info': usage_info
            }, status=403)

        # Read data rows (skip header)
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not row:
                break

            name = row[name_col] if name_col < len(row) else None
            if not name:
                errors.append({'row': row_num, 'error': 'Missing name'})
                continue

            # Parse color (hex to decimal)
            color = 0
            if color_col is not None and color_col < len(row) and row[color_col]:
                color_str = str(row[color_col]).strip()
                if color_str.startswith('#'):
                    color_str = color_str[1:]
                try:
                    color = int(color_str, 16)
                except ValueError:
                    errors.append({'row': row_num, 'error': f'Invalid color: {row[color_col]}'})
                    continue

            # Parse permissions
            permissions = '0'
            if permissions_col is not None and permissions_col < len(row) and row[permissions_col]:
                try:
                    permissions = str(int(float(row[permissions_col])))
                except (ValueError, TypeError):
                    errors.append({'row': row_num, 'error': f'Invalid permissions: {row[permissions_col]}'})
                    continue

            # Parse boolean fields
            hoist = False
            if hoist_col is not None and hoist_col < len(row) and row[hoist_col]:
                hoist_val = str(row[hoist_col]).strip().upper()
                hoist = hoist_val in ['TRUE', 'YES', '1', 'Y']

            mentionable = False
            if mentionable_col is not None and mentionable_col < len(row) and row[mentionable_col]:
                ment_val = str(row[mentionable_col]).strip().upper()
                mentionable = ment_val in ['TRUE', 'YES', '1', 'Y']

            # Create role via Discord API
            role_data = {
                'name': str(name),
                'permissions': permissions,
                'color': color,
                'hoist': hoist,
                'mentionable': mentionable,
            }

            resp = bot_session.post(f'/guilds/{guild_id_int}/roles', json=role_data)

            if resp.status_code == 200:
                role = resp.json()
                roles_created.append(role['name'])
            else:
                error_data = resp.json() if resp.headers.get('content-type') == 'application/json' else {}
                errors.append({'row': row_num, 'error': error_data.get('message', f'Discord API error: {resp.status_code}')})

        # Record usage for daily tracking
        if len(roles_created) > 0:
            record_bulk_usage(guild_id, 'role_create', len(roles_created))

        return JsonResponse({
            'success': True,
            'created_count': len(roles_created),
            'roles_created': roles_created[:10],  # Show first 10
            'errors': errors[:10] if errors else [],  # Show first 10 errors
            'message': f'Created {len(roles_created)} roles successfully!'
        })

    except Exception as e:
        logger.error(f"Error in bulk role create for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': f'An internal error occurred: {str(e)}'}, status=500)


@api_auth_required
def api_role_export_create_template(request, guild_id):
    """GET /api/guild/<id>/roles/export-create-template/ - Export XLSX template for bulk role creation."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from io import BytesIO
        from django.http import HttpResponse

        # Create workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Role Creation Template"

        # Add headers with formatting
        headers = ['name', 'color', 'permissions', 'hoist', 'mentionable']
        ws.append(headers)

        # Style header row
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="7C3AED", end_color="7C3AED", fill_type="solid")

        # Add example rows
        ws.append(['Member', '#5865F2', '0', 'FALSE', 'TRUE'])
        ws.append(['Moderator', '#F23F43', '8388614', 'TRUE', 'TRUE'])
        ws.append(['VIP', '#FEE75C', '0', 'TRUE', 'FALSE'])

        # Set column widths
        ws.column_dimensions['A'].width = 20  # name
        ws.column_dimensions['B'].width = 12  # color
        ws.column_dimensions['C'].width = 15  # permissions
        ws.column_dimensions['D'].width = 12  # hoist
        ws.column_dimensions['E'].width = 15  # mentionable

        # Add instructions sheet
        ws_info = wb.create_sheet(title="Instructions")
        ws_info['A1'] = "Bulk Role Creation Instructions"
        ws_info['A1'].font = Font(bold=True, size=14)

        instructions = [
            "",
            "How to use this template:",
            "1. Fill in the role details in the 'Role Creation Template' sheet",
            "2. Delete the example rows",
            "3. Save the file",
            "4. Upload it via the Bulk Create button",
            "",
            "Column Descriptions:",
            "• name - Role name (required)",
            "• color - Hex color code with # (e.g., #FF5733)",
            "• permissions - Permission number (0 = no permissions, use Discord permission calculator)",
            "• hoist - Display separately in member list (TRUE/FALSE)",
            "• mentionable - Allow role to be mentioned (TRUE/FALSE)",
            "",
            "Common Permission Numbers:",
            "• 0 = No permissions",
            "• 8 = Administrator (DANGEROUS - full access)",
            "• 8388614 = Moderator (Kick, Ban, Manage Messages, etc.)",
            "• 104189504 = Read & Send Messages",
            "",
            "Tips:",
            "• Maximum 100 roles per import",
            "• Use TRUE/FALSE for boolean fields",
            "• Colors should be hex codes (#RRGGBB)",
        ]

        for i, instruction in enumerate(instructions, start=2):
            ws_info[f'A{i}'] = instruction

        ws_info.column_dimensions['A'].width = 70

        # Save to BytesIO
        excel_file = BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)

        # Return as download
        response = HttpResponse(
            excel_file.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="role_creation_template.xlsx"'
        return response

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# Audit Logs Dashboard

@discord_required
def guild_audit_logs(request, guild_id):
    """View audit logs for a guild."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    # Get filter parameters
    action_filter = request.GET.get('action', '')
    actor_filter = request.GET.get('actor', '')
    target_filter = request.GET.get('target', '')
    days = int(request.GET.get('days', 7))

    # Fetch audit logs from database
    audit_logs = []
    total_count = 0
    action_types = []
    guild_record = None

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
            elif guild_record and guild_record.subscription_tier == 'pro':
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

    # Get audit log channel configuration
    audit_log_channel_id = ''
    if guild_record:
        audit_log_channel_id = str(guild_record.log_channel_id) if guild_record.log_channel_id else ''

    # Check if guild has moderation module access
    has_moderation_module = has_module_access(guild_id, 'moderation')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'audit_logs': audit_logs,
        'total_count': total_count,
        'action_types': action_types,
        'audit_log_channel_id': audit_log_channel_id,
        'audit_enabled': bool(guild_record.audit_logging_enabled) if guild_record else False,
        'audit_event_config': guild_record.audit_event_config if guild_record else '',
        'has_moderation_module': has_moderation_module,
        'has_any_module': has_any_module,
        'current_filters': {
            'action': action_filter,
            'actor': actor_filter,
            'target': target_filter,
            'days': days,
        },
        'active_page': 'audit',
    }
    return render(request, 'questlog/audit.html', context)


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


# Audit Logs API Endpoints

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
            elif guild_record and guild_record.subscription_tier == 'pro':
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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET", "POST", "PATCH"])
@api_auth_required
def api_audit_config_update(request, guild_id):
    """GET/POST /api/guild/<id>/audit/config/ - Fetch or update audit log configuration."""
    # GET: return current config
    if request.method == "GET":
        try:
            from .db import get_db_session
            from .models import Guild as GuildModel

            with get_db_session() as db:
                guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
                return JsonResponse({
                    'success': True,
                    'log_channel_id': str(guild_record.log_channel_id) if guild_record and guild_record.log_channel_id else '',
                    'audit_enabled': bool(guild_record.audit_logging_enabled) if guild_record else False,
                    'event_config': json_lib.loads(guild_record.audit_event_config or '{}') if guild_record else {}
                })
        except Exception as e:
            logger.error(f"Error fetching audit config: {e}", exc_info=True)
            return JsonResponse({'error': 'Failed to fetch audit config'}, status=500)

    # POST/PATCH: update config
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

            # Update log channel
            if 'log_channel_id' in data:
                try:
                    guild_record.log_channel_id = int(data['log_channel_id']) if data['log_channel_id'] else None
                except (TypeError, ValueError):
                    guild_record.log_channel_id = None
            if data.get('audit_enabled') is False:
                guild_record.log_channel_id = None
                guild_record.audit_logging_enabled = False
            elif data.get('audit_enabled') is True:
                guild_record.audit_logging_enabled = True
            if 'event_config' in data:
                guild_record.audit_event_config = json_lib.dumps(data.get('event_config') or {})

            logger.info(f"Updated audit log channel for guild {guild_id} to {guild_record.log_channel_id}")
            db.commit()
            return JsonResponse({
                'success': True,
                'log_channel_id': str(guild_record.log_channel_id) if guild_record.log_channel_id else '',
                'audit_enabled': guild_record.audit_logging_enabled,
                'event_config': json_lib.loads(guild_record.audit_event_config or '{}')
            })

    except Exception as e:
        logger.error(f"Error updating audit config: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
@require_subscription_tier('pro', 'premium')
@ratelimit(key='user_or_ip', rate='10/h', method='GET', block=True)
def api_audit_export(request, guild_id):
    """GET /api/guild/<id>/audit/export/ - Export audit logs to CSV (Pro/Premium only, 10 req/hour)."""
    import csv
    import io
    from django.http import HttpResponse

    try:
        from .db import get_db_session
        from .models import AuditLog

        # Get filter params
        action_filter = request.GET.get('action', '')
        actor_filter = request.GET.get('actor', '')
        target_filter = request.GET.get('target', '')
        days = int(request.GET.get('days', 30))

        with get_db_session() as db:
            cutoff_time = int(time.time()) - (days * 86400)

            query = db.query(AuditLog).filter(
                AuditLog.guild_id == int(guild_id),
                AuditLog.timestamp >= cutoff_time
            )

            if action_filter:
                query = query.filter(AuditLog.action == action_filter)
            if actor_filter:
                query = query.filter(AuditLog.actor_name.ilike(f'%{actor_filter}%'))
            if target_filter:
                query = query.filter(AuditLog.target_name.ilike(f'%{target_filter}%'))

            logs = query.order_by(AuditLog.timestamp.desc()).limit(10000).all()

            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow(['Timestamp', 'Action', 'Actor', 'Target', 'Reason', 'Details'])

            # Write data
            for log in logs:
                from datetime import datetime
                dt = datetime.fromtimestamp(log.timestamp)
                writer.writerow([
                    dt.strftime('%Y-%m-%d %H:%M:%S'),
                    log.action.value if hasattr(log.action, 'value') else str(log.action),
                    log.actor_name or 'N/A',
                    log.target_name or 'N/A',
                    log.reason or '',
                    log.details or ''
                ])

            # Create HTTP response
            response = HttpResponse(output.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="audit_logs_{guild_id}_{int(time.time())}.csv"'
            return response

    except Exception as e:
        logger.error(f"Error exporting audit logs: {e}", exc_info=True)
        return JsonResponse({'error': 'Failed to export logs'}, status=500)


# Welcome/Goodbye Messages Dashboard

@discord_required
def guild_welcome(request, guild_id):
    """Welcome and goodbye message configuration page."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    # Fetch welcome config from database
    welcome_config = None
    guild_channels = []
    guild_record = None

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
                    'goodbye_channel_id': ''
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
                    'goodbye_channel_id': ''
                }

    except Exception as e:
        logger.warning(f"Could not fetch welcome config: {e}")
        welcome_config = {}

    # Check if guild has engagement module access
    has_engagement_module = has_module_access(guild_id, 'engagement')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'welcome_config': welcome_config,
        'has_engagement_module': has_engagement_module,
        'has_any_module': has_any_module,
        'active_page': 'welcome',
    }
    return render(request, 'questlog/welcome.html', context)


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
            if 'goodbye_channel_id' in data:
                config.goodbye_channel_id = int(data['goodbye_channel_id']) if data['goodbye_channel_id'] else None
            if 'auto_role_id' in data:
                config.auto_role_id = int(data['auto_role_id']) if data['auto_role_id'] else None

            # Update welcome channel in guild record
            if 'welcome_channel_id' in data:
                guild_record.welcome_channel_id = int(data['welcome_channel_id']) if data['welcome_channel_id'] else None

            config.updated_at = int(time.time())

            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
                    'xp_enabled': config.xp_enabled,
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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# Level-Up Messages Dashboard

@discord_required
def guild_levelup(request, guild_id):
    """Level-up message configuration page."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    levelup_config = None
    guild_record = None

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
                    'ping_on_role_only': config.ping_on_role_only,
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
                    'ping_on_role_only': False,
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

    # Check if guild has engagement module access
    has_engagement_module = has_module_access(guild_id, 'engagement')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'levelup_config': levelup_config,
        'has_engagement_module': has_engagement_module,
        'has_any_module': has_any_module,
        'active_page': 'levelup',
    }
    return render(request, 'questlog/levelup.html', context)


# Message System
@discord_required
def guild_messages(request, guild_id):
    """Message System dashboard (send/edit messages and embeds)."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])
    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    guild_record = None
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
    except Exception as e:
        logger.warning(f"Could not fetch guild record: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'active_page': 'messages',
    }
    return render(request, 'questlog/messages.html', context)


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
            if 'ping_on_role_only' in data:
                config.ping_on_role_only = bool(data['ping_on_role_only'])
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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_guild_channels(request, guild_id):
    """GET /api/guild/<id>/channels/ - Get guild channels (cached)."""
    try:
        from .discord_resources import get_guild_channels

        # Get force_refresh from query params
        force_refresh = request.GET.get('force_refresh', 'false').lower() == 'true'

        # Fetch channels with caching
        channels = get_guild_channels(guild_id, force_refresh=force_refresh)
        # Normalize IDs to strings to avoid JS precision loss
        norm_channels = []
        for c in channels:
            norm_channels.append({
                'id': str(c.get('id')),
                'name': c.get('name'),
                'type': c.get('type')
            })

        return JsonResponse({'channels': norm_channels})

    except Exception as e:
        logger.error(f"Failed to fetch channels for guild {guild_id}: {e}")
        return JsonResponse({'error': str(e), 'channels': []}, status=500)


@require_http_methods(["GET", "PATCH"])
@api_auth_required
def api_guild_roles(request, guild_id):
    """
    GET /api/guild/<id>/roles/ - Get guild roles (cached).
    PATCH /api/guild/<id>/roles/ - Update Discord role positions.
    """
    if request.method == 'GET':
        try:
            from .discord_resources import get_guild_roles

            # Get force_refresh from query params
            force_refresh = request.GET.get('force_refresh', 'false').lower() == 'true'

            # Fetch roles with caching
            roles = get_guild_roles(guild_id, force_refresh=force_refresh)

            # Add is_everyone flag for each role
            norm_roles = []
            for role in roles:
                norm_roles.append({
                    'id': str(role.get('id')),
                    'name': role.get('name'),
                    'position': role.get('position'),
                    'is_everyone': role.get('name') == '@everyone' or str(role.get('id')) == str(guild_id)
                })

            return JsonResponse({'success': True, 'roles': norm_roles})

        except Exception as e:
            logger.error(f"Failed to fetch roles for guild {guild_id}: {e}")
            return JsonResponse({'error': str(e), 'roles': []}, status=500)

    elif request.method == 'PATCH':
        try:
            import json

            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

            # Data should be an array of role position updates
            # Format: [{"id": "role_id", "position": 5}, ...]
            if not isinstance(data, list):
                return JsonResponse({'error': 'Expected array of role updates'}, status=400)

            bot_session = get_bot_session(int(guild_id))
            if not bot_session:
                return JsonResponse({'error': 'Bot session not available'}, status=500)

            # Update role positions via Discord API
            # NOTE: Discord may auto-adjust positions to prevent conflicts or enforce hierarchy rules
            resp = bot_session.patch(f'/guilds/{guild_id}/roles', json=data)

            if resp.status_code == 200:
                # Discord returns the updated roles array
                updated_roles = resp.json()
                logger.info(f"Discord accepted position update for guild {guild_id}. Response: {updated_roles}")

                # Check if Discord actually applied the requested position
                requested_role = data[0]  # We only send one role at a time
                actual_role = next((r for r in updated_roles if r['id'] == requested_role['id']), None)

                if actual_role and actual_role['position'] != requested_role['position']:
                    logger.warning(
                        f"Discord adjusted role position for {requested_role['id']} in guild {guild_id}: "
                        f"requested {requested_role['position']}, actual {actual_role['position']}"
                    )
                    return JsonResponse({
                        'success': True,
                        'updated': len(data),
                        'warning': f'Discord adjusted position to {actual_role["position"]} due to role hierarchy rules'
                    })

                return JsonResponse({'success': True, 'updated': len(data)})
            else:
                error_text = resp.text
                logger.error(f"Failed to update Discord role positions in guild {guild_id}: {resp.status_code} - {error_text}")
                return JsonResponse({'error': f'Discord API returned status {resp.status_code}: {error_text}'}, status=resp.status_code)

        except Exception as e:
            logger.error(f"Error updating Discord role positions in guild {guild_id}: {e}", exc_info=True)
            return JsonResponse({'error': 'An internal error occurred'}, status=500)

    else:
        return JsonResponse({'error': 'Method not allowed'}, status=405)


@require_http_methods(["GET"])
@api_auth_required
def api_guild_emojis(request, guild_id):
    """GET /api/guild/<id>/emojis/ - Get ALL guild custom emojis from database cache + standard emojis."""
    try:
        from .discord_resources import get_guild_emojis

        # Get force_refresh from query params
        force_refresh = request.GET.get('force_refresh', 'false').lower() == 'true'

        # Fetch ALL custom emojis from database (synced by bot)
        custom = get_guild_emojis(guild_id, force_refresh=force_refresh)

        # Standard emoji list (commonly used ones)
        standard = [
            {'name': '😀', 'id': None},
            {'name': '😁', 'id': None},
            {'name': '😂', 'id': None},
            {'name': '🤣', 'id': None},
            {'name': '😎', 'id': None},
            {'name': '😍', 'id': None},
            {'name': '👍', 'id': None},
            {'name': '👎', 'id': None},
            {'name': '🎉', 'id': None},
            {'name': '✅', 'id': None},
            {'name': '❌', 'id': None},
            {'name': '🔥', 'id': None},
            {'name': '⭐', 'id': None},
            {'name': '💎', 'id': None},
            {'name': '🎮', 'id': None},
            {'name': '🎯', 'id': None},
            {'name': '🏆', 'id': None},
            {'name': '💰', 'id': None},
            {'name': '🎁', 'id': None},
            {'name': '🎲', 'id': None},
        ]

        return JsonResponse({'success': True, 'standard': standard, 'custom': custom})

    except Exception as e:
        logger.error(f"Failed to fetch emojis for guild {guild_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e), 'standard': [], 'custom': []}, status=500)


# Admin/Server Settings Dashboard

@discord_required
def guild_settings(request, guild_id):
    """Server settings configuration page."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    settings = {}
    guild_record = None

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
                    'subscription_tier': guild_record.subscription_tier if guild_record.subscription_tier else 'free',
                    'billing_cycle': guild_record.billing_cycle,
                    'is_vip': guild_record.is_vip,
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
                    'billing_cycle': None,
                    'is_vip': False,
                }

    except Exception as e:
        logger.warning(f"Could not fetch settings: {e}")

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'settings': settings,
        'active_page': 'settings',
    }
    return render(request, 'questlog/settings.html', context)


@discord_required
def guild_billing(request, guild_id):
    """Billing and subscription management page."""
    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    guild_record = None
    try:
        from django.conf import settings
        from .db import get_db_session
        from .models import Guild as GuildModel, GuildModule
        from .modules_config import MODULES, BUNDLES, get_all_modules
        from .module_utils import get_guild_modules

        # Get all available modules
        all_modules = get_all_modules()

        # Get currently active modules for this guild
        active_modules = get_guild_modules(guild_id)

        # Check if guild has VIP status or Complete tier
        is_vip = False
        subscription_tier = 'free'
        has_all_modules = False
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if guild_record:
                is_vip = guild_record.is_vip
                subscription_tier = guild_record.subscription_tier if guild_record.subscription_tier else 'free'
                billing_cycle = guild_record.billing_cycle
                # VIP or Complete tier get all modules
                has_all_modules = is_vip or subscription_tier == 'complete' or billing_cycle == 'lifetime'
            else:
                billing_cycle = None

        # Build module data with active status
        modules_data = []
        for module_key, module_config in all_modules.items():
            modules_data.append({
                'key': module_key,
                'name': module_config['name'],
                'short_name': module_config['short_name'],
                'description': module_config['description'],
                'icon': module_config['icon'],
                'color': module_config['color'],
                'features': module_config['features'],
                'price_monthly': module_config['price_monthly'],
                'price_yearly': module_config['price_yearly'],
                'is_active': module_key in active_modules or has_all_modules,
            })

        # Calculate pricing (filter out None values for yearly since individual modules don't have yearly pricing)
        total_monthly = sum(m['price_monthly'] for m in modules_data if m['price_monthly'] is not None)
        total_yearly = sum(m['price_yearly'] for m in modules_data if m['price_yearly'] is not None)

        # Get Stripe subscription details if available
        subscription_data = None
        if guild_record and guild_record.stripe_subscription_id:
            # Skip if it's a lifetime subscription (not a real Stripe subscription ID)
            if not guild_record.stripe_subscription_id.startswith('lifetime_'):
                try:
                    import stripe
                    stripe.api_key = settings.STRIPE_SECRET_KEY
                    subscription = stripe.Subscription.retrieve(guild_record.stripe_subscription_id)

                    # Extract price info from subscription items using dict-style access
                    amount = 0
                    interval = 'month'
                    if 'items' in subscription and subscription['items'].get('data'):
                        items_data = subscription['items']['data']
                        if items_data and len(items_data) > 0:
                            price = items_data[0]['price']
                            amount = price['unit_amount'] / 100
                            interval = price.get('recurring', {}).get('interval', 'month')

                    subscription_data = {
                        'id': subscription.id,
                        'status': subscription.get('status', 'active'),
                        'current_period_end': subscription['items']['data'][0].get('current_period_end') if subscription.get('items', {}).get('data') else None,
                        'cancel_at_period_end': subscription.get('cancel_at_period_end', False),
                        'plan_name': subscription.get('metadata', {}).get('plan_name', 'Complete Suite'),
                        'amount': amount,
                        'interval': interval,
                    }
                    logger.info(f"Fetched subscription for guild {guild_id}: status={subscription_data['status']}, cancel_at_period_end={subscription_data['cancel_at_period_end']}, current_period_end={subscription_data['current_period_end']}")
                except Exception as e:
                    logger.error(f"Error fetching Stripe subscription: {e}", exc_info=True)

        context = {
            'discord_user': discord_user,
            'guild': guild,
            'guild_record': guild_record,
            'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
            'is_admin': True,
            'active_page': 'billing',
            'modules': modules_data,
            'bundles': BUNDLES,
            'active_modules': active_modules,
            'active_module_count': len(active_modules),
            'total_modules': len(all_modules),
            'total_monthly': total_monthly,
            'total_yearly': total_yearly,
            'is_vip': is_vip,
            'subscription_tier': subscription_tier,
            'billing_cycle': billing_cycle if 'billing_cycle' in locals() else None,
            'subscription': subscription_data,
        }
        return render(request, 'questlog/billing.html', context)

    except Exception as e:
        logger.error(f"Error loading billing page: {e}")
        messages.error(request, "Error loading billing information.")
        return redirect('guild_dashboard', guild_id=guild_id)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_settings_reset(request, guild_id):
    """POST /api/guild/<id>/settings/reset/ - Reset guild settings to defaults."""
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if guild_record:
                # Reset to defaults
                guild_record.bot_prefix = '!'
                guild_record.language = 'en'
                guild_record.timezone = 'UTC'
                guild_record.token_name = 'Hero Tokens'
                guild_record.token_emoji = ':coin:'
                guild_record.mod_log_channel_id = None

            return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Error resetting settings for guild {guild_id}: {e}")
        return JsonResponse({'error': 'Failed to reset settings'}, status=500)


# ============================================================================
# Stripe Integration Views
# ============================================================================

@require_http_methods(["POST"])
@api_auth_required
@ratelimit(key='user_or_ip', rate='5/m', method='POST', block=True)
def stripe_create_checkout(request, guild_id):
    """
    POST /api/guild/<id>/stripe/checkout/ - Create Stripe checkout session.

    Body: {
        "items": [{"type": "module", "key": "engagement"}],
        "billing_cycle": "monthly"  # or "yearly"
    }
    """
    try:
        from .stripe_utils import create_checkout_session
        import json
        from django.conf import settings

        data = json.loads(request.body)
        items = data.get('items', [])
        billing_cycle = data.get('billing_cycle', 'monthly')

        if not items:
            return JsonResponse({'error': 'No items specified'}, status=400)

        # Create URLs for success and cancel
        base_url = f"https://{request.get_host()}"
        success_url = f"{base_url}/questlog/guild/{guild_id}/billing/?success=true"
        cancel_url = f"{base_url}/questlog/guild/{guild_id}/billing/?cancelled=true"

        # Create checkout session
        session = create_checkout_session(
            guild_id=guild_id,
            items=items,
            billing_cycle=billing_cycle,
            success_url=success_url,
            cancel_url=cancel_url
        )

        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'checkout_url': session.url
        })

    except Exception as e:
        logger.error(f"Error creating checkout session: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@csrf_exempt  # Stripe webhook uses signature verification instead of CSRF
def stripe_webhook(request):
    """
    POST /webhooks/stripe/ - Handle Stripe webhook events.

    This endpoint is called by Stripe to notify us of subscription events.
    CSRF exempt because Stripe webhook signature verification is more secure.
    """
    try:
        from django.conf import settings
        from .stripe_utils import (
            handle_checkout_completed,
            handle_subscription_updated,
            handle_subscription_deleted
        )
        import stripe

        payload = request.body
        sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

        if not sig_header:
            return JsonResponse({'error': 'Missing signature'}, status=400)

        # Verify webhook signature
        try:
            event = stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            return JsonResponse({'error': 'Invalid payload'}, status=400)
        except stripe.error.SignatureVerificationError:
            return JsonResponse({'error': 'Invalid signature'}, status=400)

        # Handle the event
        event_type = event['type']
        event_data = event['data']['object']

        logger.info(f"Received Stripe webhook: {event_type}")

        if event_type == 'checkout.session.completed':
            handle_checkout_completed(event_data)
        elif event_type == 'customer.subscription.updated':
            handle_subscription_updated(event_data)
        elif event_type == 'customer.subscription.deleted':
            handle_subscription_deleted(event_data)
        elif event_type == 'invoice.payment_failed':
            # Handle failed payments (optional - could send notification)
            logger.warning(f"Payment failed for subscription: {event_data.get('subscription')}")

        return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def stripe_cancel_subscription(request, guild_id):
    """
    POST /api/guild/<id>/stripe/cancel/ - Cancel guild's subscription.
    """
    try:
        from .stripe_utils import cancel_subscription

        success, message = cancel_subscription(guild_id)

        if success:
            return JsonResponse({'success': True, 'message': message})
        else:
            return JsonResponse({'error': message}, status=400)

    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def stripe_subscription_status(request, guild_id):
    """
    GET /api/guild/<id>/stripe/status/ - Get subscription status.
    """
    try:
        from .stripe_utils import get_subscription_status

        status = get_subscription_status(guild_id)

        if status:
            return JsonResponse({'success': True, 'subscription': status})
        else:
            return JsonResponse({'success': True, 'subscription': None})

    except Exception as e:
        logger.error(f"Error fetching subscription status: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def stripe_billing_portal(request, guild_id):
    """
    POST /api/guild/<id>/stripe/portal/ - Create Stripe billing portal session.
    """
    try:
        from django.conf import settings
        from .db import get_db_session
        from .models import Guild as GuildModel
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        with get_db_session() as db:
            guild = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild or not guild.stripe_customer_id:
                return JsonResponse({'error': 'No active subscription found'}, status=404)

            # Create portal session
            # Construct return URL from request
            return_url = request.build_absolute_uri(f'/questlog/guild/{guild_id}/billing/?portal=success')
            portal_session = stripe.billing_portal.Session.create(
                customer=guild.stripe_customer_id,
                return_url=return_url
            )

            return JsonResponse({'success': True, 'portal_url': portal_session.url})

    except Exception as e:
        logger.error(f"Error creating billing portal: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def stripe_transfer_subscription(request, guild_id):
    """
    POST /api/guild/<id>/stripe/transfer/ - Transfer subscription to another guild.
    """
    try:
        import json
        from .db import get_db_session
        from .models import Guild as GuildModel, GuildModule

        data = json.loads(request.body)
        new_guild_id = data.get('new_guild_id')

        if not new_guild_id:
            return JsonResponse({'error': 'new_guild_id is required'}, status=400)

        with get_db_session() as db:
            # Get source guild
            source_guild = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not source_guild:
                return JsonResponse({'error': 'Source guild not found'}, status=404)

            # Get or create target guild
            target_guild = db.query(GuildModel).filter_by(guild_id=int(new_guild_id)).first()
            if not target_guild:
                target_guild = GuildModel(
                    guild_id=int(new_guild_id),
                    is_vip=False,
                    subscription_tier='free',
                )
                db.add(target_guild)
                db.flush()

            # Transfer subscription data
            target_guild.stripe_customer_id = source_guild.stripe_customer_id
            target_guild.stripe_subscription_id = source_guild.stripe_subscription_id
            target_guild.subscription_tier = source_guild.subscription_tier

            # Transfer all modules
            source_modules = db.query(GuildModule).filter_by(guild_id=int(guild_id)).all()
            for src_module in source_modules:
                # Check if target already has this module
                target_module = db.query(GuildModule).filter_by(
                    guild_id=int(new_guild_id),
                    module_name=src_module.module_name
                ).first()

                if target_module:
                    # Update existing
                    target_module.enabled = src_module.enabled
                    target_module.expires_at = src_module.expires_at
                    target_module.stripe_subscription_id = src_module.stripe_subscription_id
                else:
                    # Create new
                    new_module = GuildModule(
                        guild_id=int(new_guild_id),
                        module_name=src_module.module_name,
                        enabled=src_module.enabled,
                        expires_at=src_module.expires_at,
                        stripe_subscription_id=src_module.stripe_subscription_id,
                    )
                    db.add(new_module)

            # Clear source guild subscription
            source_guild.stripe_customer_id = None
            source_guild.stripe_subscription_id = None
            source_guild.subscription_tier = 'free'

            # Disable all source modules
            for src_module in source_modules:
                src_module.enabled = False

            db.commit()

            logger.info(f"Transferred subscription from guild {guild_id} to {new_guild_id}")
            return JsonResponse({'success': True, 'message': 'Subscription transferred successfully'})

    except Exception as e:
        logger.error(f"Error transferring subscription: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
@api_auth_required
@ratelimit(key='user_or_ip', rate='2/h', method='POST', block=True)
def api_settings_remove_data(request, guild_id):
    """POST /api/guild/<id>/settings/remove-data/ - Remove all guild data."""
    try:
        from .db import get_db_session
        from .models import Guild as GuildModel

        with get_db_session() as db:
            # Delete guild record (cascade will handle related data)
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if guild_record:
                db.delete(guild_record)
                logger.info(f"Removed all data for guild {guild_id}")

            return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Error removing data for guild {guild_id}: {e}")
        return JsonResponse({'error': 'Failed to remove data'}, status=500)


# Verification Configuration Dashboard

@discord_required
def guild_verification(request, guild_id):
    """Verification configuration page."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    verification_config = {}
    guild_record = None

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

    # Check if guild has moderation module access
    has_moderation_module = has_module_access(guild_id, 'moderation')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'verification_config': verification_config,
        'has_moderation_module': has_moderation_module,
        'has_any_module': has_any_module,
        'active_page': 'verification',
    }
    return render(request, 'questlog/verification.html', context)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# Moderation Dashboard

@discord_required
def guild_moderation(request, guild_id):
    """Moderation dashboard - warnings, bans, timeouts."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    mod_actions = []
    stats = {'total': 0, 'active': 0, 'week': 0}
    guild_record = None

    try:
        from .db import get_db_session
        from .models import Warning, ModAction, GuildMember, Guild
        import time
        from datetime import datetime

        with get_db_session() as db:
            guild_record = db.get(Guild, int(guild_id))

            # Get recent warnings
            recent_warnings = db.query(Warning).filter(
                Warning.guild_id == int(guild_id)
            ).order_by(Warning.issued_at.desc()).limit(100).all()

            # Get recent mod actions (timeouts, kicks, bans, etc.)
            # Only include user-facing moderation actions, not admin actions
            user_mod_actions = ['timeout', 'untimeout', 'kick', 'ban', 'unban', 'mute', 'unmute', 'jail', 'unjail']
            recent_mod_actions = db.query(ModAction).filter(
                ModAction.guild_id == int(guild_id),
                ModAction.action_type.in_(user_mod_actions)
            ).order_by(ModAction.timestamp.desc()).limit(100).all()

            # Combine warnings into mod_actions format
            for w in recent_warnings:
                # Get user info
                member = db.query(GuildMember).filter_by(
                    guild_id=int(guild_id),
                    user_id=w.user_id
                ).first()

                username = member.display_name or member.username or f'User {w.user_id}' if member else f'User {w.user_id}'
                formatted_date = datetime.fromtimestamp(w.issued_at).strftime('%b %d, %Y at %I:%M %p') if w.issued_at else 'Unknown'

                mod_actions.append({
                    'id': f'warning_{w.id}',
                    'action_type': 'warning',
                    'warning_id': w.id,
                    'user_id': str(w.user_id),
                    'username': username,
                    'warning_type': w.warning_type.value,
                    'reason': w.reason,
                    'severity': w.severity,
                    'moderator_id': str(w.issued_by) if w.issued_by else 'AutoMod',
                    'moderator_name': w.issued_by_name or 'AutoMod',
                    'timestamp': w.issued_at,
                    'formatted_date': formatted_date,
                    'is_active': w.is_active,
                    'pardoned': w.pardoned,
                    'duration': None,
                })

            # Add other mod actions
            for ma in recent_mod_actions:
                # Get target user info
                if ma.target_id:
                    member = db.query(GuildMember).filter_by(
                        guild_id=int(guild_id),
                        user_id=ma.target_id
                    ).first()
                    username = member.display_name or member.username or ma.target_name or f'User {ma.target_id}' if member else ma.target_name or f'User {ma.target_id}'
                else:
                    username = ma.target_name or 'Unknown'

                formatted_date = datetime.fromtimestamp(ma.timestamp).strftime('%b %d, %Y at %I:%M %p') if ma.timestamp else 'Unknown'

                # Determine if action is still active (for timeouts)
                is_active = True
                if ma.action_type in ['timeout']:
                    is_active = True  # We'll update this based on Discord API if needed
                elif ma.action_type in ['untimeout', 'kick', 'ban', 'unban', 'unjail', 'unmute']:
                    is_active = False

                mod_actions.append({
                    'id': f'action_{ma.id}',
                    'action_type': ma.action_type,
                    'mod_action_id': ma.id,
                    'user_id': str(ma.target_id) if ma.target_id else None,
                    'username': username,
                    'reason': ma.reason,
                    'moderator_id': str(ma.mod_id),
                    'moderator_name': ma.mod_name or f'Moderator {ma.mod_id}',
                    'timestamp': ma.timestamp,
                    'formatted_date': formatted_date,
                    'is_active': is_active,
                    'pardoned': False,
                    'duration': ma.duration,
                })

            # Sort all actions by timestamp descending
            mod_actions.sort(key=lambda x: x['timestamp'], reverse=True)

            # Stats - combine both warnings and mod actions
            week_ago = int(time.time()) - (7 * 24 * 60 * 60)
            warnings_count = db.query(Warning).filter(Warning.guild_id == int(guild_id)).count()
            actions_count = db.query(ModAction).filter(
                ModAction.guild_id == int(guild_id),
                ModAction.action_type.in_(user_mod_actions)
            ).count()

            stats['total'] = warnings_count + actions_count
            stats['active'] = db.query(Warning).filter(Warning.guild_id == int(guild_id), Warning.is_active == True).count()
            stats['week'] = (
                db.query(Warning).filter(Warning.guild_id == int(guild_id), Warning.issued_at >= week_ago).count() +
                db.query(ModAction).filter(
                    ModAction.guild_id == int(guild_id),
                    ModAction.action_type.in_(user_mod_actions),
                    ModAction.timestamp >= week_ago
                ).count()
            )

    except Exception as e:
        logger.warning(f"Could not fetch moderation data: {e}")
        guild_record = None

    # Check if guild has moderation module access
    has_moderation_module = has_module_access(guild_id, 'moderation')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'guild_record': guild_record,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'mod_actions': mod_actions,
        'stats': stats,
        'mod_enabled': bool(guild_record.mod_enabled) if guild_record else False,
        'has_moderation_module': has_moderation_module,
        'has_any_module': has_any_module,
        'active_page': 'moderation',
    }
    return render(request, 'questlog/moderation.html', context)


@discord_required
def guild_moderation_settings(request, guild_id):
    """Moderation settings - configure jail, mute, mod log."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    # Get guild settings from database
    settings = {}
    channels = []
    roles = []

    try:
        from .db import get_db_session
        from .models import Guild
        import json as json_lib

        with get_db_session() as db:
            db_guild = db.get(Guild, int(guild_id))
            if db_guild:
                settings = {
                    'mod_log_channel_id': str(db_guild.mod_log_channel_id) if db_guild.mod_log_channel_id else None,
                    'jail_channel_id': str(db_guild.jail_channel_id) if db_guild.jail_channel_id else None,
                    'jail_role_id': str(db_guild.jail_role_id) if db_guild.jail_role_id else None,
                    'muted_role_id': str(db_guild.muted_role_id) if db_guild.muted_role_id else None,
                    'mod_enabled': bool(db_guild.mod_enabled),
                }

                # Parse cached channels and roles
                if db_guild.cached_channels:
                    try:
                        channels = json_lib.loads(db_guild.cached_channels)
                    except:
                        channels = []

                if db_guild.cached_roles:
                    try:
                        roles = json_lib.loads(db_guild.cached_roles)
                    except:
                        roles = []

    except Exception as e:
        logger.warning(f"Could not fetch moderation settings: {e}")

    # Check if guild has moderation module access
    has_moderation_module = has_module_access(guild_id, 'moderation')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'settings': settings,
        'channels': channels,
        'roles': roles,
        'has_moderation_module': has_moderation_module,
        'has_any_module': has_any_module,
        'active_page': 'moderation_settings',
    }
    return render(request, 'questlog/moderation_settings.html', context)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_mod_untimeout(request, guild_id):
    """POST /api/guild/<id>/mod/untimeout/ - Remove timeout from a user."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    reason = data.get('reason', 'Timeout removed via web dashboard')

    if not user_id:
        return JsonResponse({'error': 'user_id is required'}, status=400)

    # Get requester's Discord ID from session
    discord_user = request.session.get('discord_user')
    requester_id = discord_user.get('id') if discord_user else None

    try:
        # Call Discord bot API to remove timeout
        response = requests.post(
            f"{DISCORD_BOT_API_URL}/mod/untimeout",
            json={
                'guild_id': guild_id,
                'user_id': user_id,
                'requester_id': requester_id,
                'reason': reason,
            },
            headers={'Authorization': f'Bearer {DISCORD_BOT_API_TOKEN}'},
            timeout=10
        )

        if response.status_code == 200:
            return JsonResponse({'success': True, 'message': 'Timeout removed successfully'})
        else:
            error_msg = response.json().get('error', 'Failed to remove timeout')
            return JsonResponse({'error': error_msg}, status=response.status_code)

    except Exception as e:
        logger.error(f"Error removing timeout: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_mod_kick(request, guild_id):
    """POST /api/guild/<id>/mod/kick/ - Kick a user from the server."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    reason = data.get('reason', 'Kicked via web dashboard')

    if not user_id:
        return JsonResponse({'error': 'user_id is required'}, status=400)

    # Get requester's Discord ID from session
    discord_user = request.session.get('discord_user')
    requester_id = discord_user.get('id') if discord_user else None

    try:
        # Call Discord bot API to kick user
        response = requests.post(
            f"{DISCORD_BOT_API_URL}/mod/kick",
            json={
                'guild_id': guild_id,
                'user_id': user_id,
                'requester_id': requester_id,
                'reason': reason,
            },
            headers={'Authorization': f'Bearer {DISCORD_BOT_API_TOKEN}'},
            timeout=10
        )

        if response.status_code == 200:
            return JsonResponse({'success': True, 'message': 'User kicked successfully'})
        else:
            error_msg = response.json().get('error', 'Failed to kick user')
            return JsonResponse({'error': error_msg}, status=response.status_code)

    except Exception as e:
        logger.error(f"Error kicking user: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
@ratelimit(key='user_or_ip', rate='10/m', method='POST', block=True)
def api_mod_ban(request, guild_id):
    """POST /api/guild/<id>/mod/ban/ - Ban a user from the server."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    reason = data.get('reason', 'Banned via web dashboard')

    if not user_id:
        return JsonResponse({'error': 'user_id is required'}, status=400)

    # Get requester's Discord ID from session
    discord_user = request.session.get('discord_user')
    requester_id = discord_user.get('id') if discord_user else None

    try:
        # Call Discord bot API to ban user
        response = requests.post(
            f"{DISCORD_BOT_API_URL}/mod/ban",
            json={
                'guild_id': guild_id,
                'user_id': user_id,
                'requester_id': requester_id,
                'reason': reason,
            },
            headers={'Authorization': f'Bearer {DISCORD_BOT_API_TOKEN}'},
            timeout=10
        )

        if response.status_code == 200:
            return JsonResponse({'success': True, 'message': 'User banned successfully'})
        else:
            error_msg = response.json().get('error', 'Failed to ban user')
            return JsonResponse({'error': error_msg}, status=response.status_code)

    except Exception as e:
        logger.error(f"Error banning user: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_mod_settings_update(request, guild_id):
    """POST /api/guild/<id>/moderation/settings/ - Update moderation settings."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import Guild

        with get_db_session() as db:
            db_guild = db.get(Guild, int(guild_id))
            if not db_guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Update settings
            if 'mod_log_channel_id' in data:
                db_guild.mod_log_channel_id = int(data['mod_log_channel_id']) if data['mod_log_channel_id'] else None

            if 'jail_channel_id' in data:
                db_guild.jail_channel_id = int(data['jail_channel_id']) if data['jail_channel_id'] else None

            if 'jail_role_id' in data:
                db_guild.jail_role_id = int(data['jail_role_id']) if data['jail_role_id'] else None

            if 'muted_role_id' in data:
                db_guild.muted_role_id = int(data['muted_role_id']) if data['muted_role_id'] else None

            if data.get('mod_enabled') is False:
                db_guild.mod_log_channel_id = None
                db_guild.jail_channel_id = None
                db_guild.jail_role_id = None
                db_guild.muted_role_id = None
                db_guild.mod_enabled = False
            elif data.get('mod_enabled') is True:
                db_guild.mod_enabled = True

            db.commit()

            logger.info(f"Updated moderation settings for guild {guild_id}")
            return JsonResponse({'success': True, 'message': 'Settings updated successfully'})

    except Exception as e:
        logger.error(f"Error updating moderation settings: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_mod_unban(request, guild_id):
    """POST /api/guild/<id>/mod/unban/ - Unban a user from the server."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    reason = data.get('reason', 'Unbanned via web dashboard')

    if not user_id:
        return JsonResponse({'error': 'user_id is required'}, status=400)

    # Get requester's Discord ID from session
    discord_user = request.session.get('discord_user')
    requester_id = discord_user.get('id') if discord_user else None

    try:
        # Call Discord bot API to unban user
        response = requests.post(
            f"{DISCORD_BOT_API_URL}/mod/unban",
            json={
                'guild_id': guild_id,
                'user_id': user_id,
                'requester_id': requester_id,
                'reason': reason,
            },
            headers={'Authorization': f'Bearer {DISCORD_BOT_API_TOKEN}'},
            timeout=10
        )

        if response.status_code == 200:
            return JsonResponse({'success': True, 'message': 'User unbanned successfully'})
        else:
            error_msg = response.json().get('error', 'Failed to unban user')
            return JsonResponse({'error': error_msg}, status=response.status_code)

    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_mod_unmute(request, guild_id):
    """POST /api/guild/<id>/mod/unmute/ - Unmute a user."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    reason = data.get('reason', 'Unmuted via web dashboard')

    if not user_id:
        return JsonResponse({'error': 'user_id is required'}, status=400)

    # Get requester's Discord ID from session
    discord_user = request.session.get('discord_user')
    requester_id = discord_user.get('id') if discord_user else None

    try:
        # Call Discord bot API to unmute user
        response = requests.post(
            f"{DISCORD_BOT_API_URL}/mod/unmute",
            json={
                'guild_id': guild_id,
                'user_id': user_id,
                'requester_id': requester_id,
                'reason': reason,
            },
            headers={'Authorization': f'Bearer {DISCORD_BOT_API_TOKEN}'},
            timeout=10
        )

        if response.status_code == 200:
            return JsonResponse({'success': True, 'message': 'User unmuted successfully'})
        else:
            error_msg = response.json().get('error', 'Failed to unmute user')
            return JsonResponse({'error': error_msg}, status=response.status_code)

    except Exception as e:
        logger.error(f"Error unmuting user: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_mod_unjail(request, guild_id):
    """POST /api/guild/<id>/mod/unjail/ - Unjail a user."""
    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    user_id = data.get('user_id')
    reason = data.get('reason', 'Unjailed via web dashboard')

    if not user_id:
        return JsonResponse({'error': 'user_id is required'}, status=400)

    # Get requester's Discord ID from session
    discord_user = request.session.get('discord_user')
    requester_id = discord_user.get('id') if discord_user else None

    try:
        # Call Discord bot API to unjail user
        response = requests.post(
            f"{DISCORD_BOT_API_URL}/mod/unjail",
            json={
                'guild_id': guild_id,
                'user_id': user_id,
                'requester_id': requester_id,
                'reason': reason,
            },
            headers={'Authorization': f'Bearer {DISCORD_BOT_API_TOKEN}'},
            timeout=10
        )

        if response.status_code == 200:
            return JsonResponse({'success': True, 'message': 'User unjailed successfully'})
        else:
            error_msg = response.json().get('error', 'Failed to unjail user')
            return JsonResponse({'error': error_msg}, status=response.status_code)

    except Exception as e:
        logger.error(f"Error unjailing user: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# Templates Dashboard (Channel & Role Templates)

@discord_required
def guild_templates(request, guild_id):
    """Templates dashboard for channel and role templates."""
    from .module_utils import has_module_access, has_any_module_access

    discord_user = request.session.get('discord_user', {})
    admin_guilds = request.session.get('discord_admin_guilds', [])

    guild = next((g for g in admin_guilds if g['id'] == guild_id), None)
    if not guild:
        messages.error(request, "You don't have admin access to this server.")
        return redirect('questlog_dashboard')

    channel_templates = []
    role_templates = []
    is_premium = False
    guild_record = None
    total_templates = 0

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

            # Calculate total templates (combined channel + role)
            total_templates = len(ch_templates) + len(r_templates)

    except Exception as e:
        logger.warning(f"Could not fetch templates: {e}")

    # Check if guild has roles module access
    has_roles_module = has_module_access(guild_id, 'roles')
    has_any_module = has_any_module_access(guild_id)

    context = {
        'discord_user': discord_user,
        'guild': guild,
        'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
        'is_admin': True,
        'channel_templates': channel_templates,
        'role_templates': role_templates,
        'is_premium': is_premium,
        'has_roles_module': has_roles_module,
        'has_any_module': has_any_module,
        'active_page': 'templates',
        'guild_record': guild_record,
        'total_templates': total_templates,
    }
    return render(request, 'questlog/templates.html', context)


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
        from .models import ChannelTemplate, RoleTemplate, Guild as GuildModel

        discord_user = request.session.get('discord_user', {})
        created_by = int(discord_user.get('id', 0))

        with get_db_session() as db:
            # Check tier limits
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Count existing templates (combined channel + role)
            channel_count = db.query(ChannelTemplate).filter_by(guild_id=int(guild_id)).count()
            role_count = db.query(RoleTemplate).filter_by(guild_id=int(guild_id)).count()
            total_templates = channel_count + role_count

            # Check limits (VIP and Complete = unlimited, Free = 5)
            if not guild_record.is_vip and guild_record.subscription_tier != 'complete':
                limit = 5
                if total_templates >= limit:
                    return JsonResponse({
                        'error': f'Template limit reached ({total_templates}/{limit} templates). Upgrade to Complete Suite for unlimited templates!'
                    }, status=403)

            template = ChannelTemplate(
                guild_id=int(guild_id),
                name=(data.get('name') or 'Untitled')[:100],
                description=(data.get('description') or '')[:500],
                template_data=json_lib.dumps(data.get('channels', [])),
                created_by=created_by,
            )
            db.add(template)
            db.flush()

            return JsonResponse({'success': True, 'id': template.id})

    except Exception as e:
        logger.error(f"Error creating channel template for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': f'An internal error occurred: {str(e)}'}, status=500)


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
        from .models import RoleTemplate, ChannelTemplate, Guild as GuildModel

        discord_user = request.session.get('discord_user', {})
        created_by = int(discord_user.get('id', 0))

        with get_db_session() as db:
            # Check tier limits
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Count existing templates (combined channel + role)
            channel_count = db.query(ChannelTemplate).filter_by(guild_id=int(guild_id)).count()
            role_count = db.query(RoleTemplate).filter_by(guild_id=int(guild_id)).count()
            total_templates = channel_count + role_count

            # Check limits (VIP and Complete = unlimited, Free = 5)
            if not guild_record.is_vip and guild_record.subscription_tier != 'complete':
                limit = 5
                if total_templates >= limit:
                    return JsonResponse({
                        'error': f'Template limit reached ({total_templates}/{limit} templates). Upgrade to Complete Suite for unlimited templates!'
                    }, status=403)

            template = RoleTemplate(
                guild_id=int(guild_id),
                name=(data.get('name') or 'Untitled')[:100],
                description=(data.get('description') or '')[:500],
                template_data=json_lib.dumps(data.get('roles', [])),
                created_by=created_by,
            )
            db.add(template)
            db.flush()

            return JsonResponse({'success': True, 'id': template.id})

    except Exception as e:
        logger.error(f"Error creating role template for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': f'An internal error occurred: {str(e)}'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
            db.commit()  # Commit the usage count increment

            return JsonResponse({'success': True, 'action_id': action_id})

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_template_detail(request, guild_id, template_type, template_id):
    """GET /api/guild/<id>/templates/<type>/<id>/ - Get template details."""
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

            return JsonResponse({
                'id': template.id,
                'name': template.name,
                'description': template.description,
                'template_data': template.template_data,
                'use_count': template.use_count,
                'created_at': template.created_at,
            })

    except Exception as e:
        logger.error(f"Error fetching template {template_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred.'}, status=500)


@require_http_methods(["PUT"])
@api_auth_required
def api_template_update(request, guild_id, template_type, template_id):
    """PUT /api/guild/<id>/templates/<type>/<id>/ - Update template."""
    try:
        from .db import get_db_session
        from .models import ChannelTemplate, RoleTemplate
        import json as json_lib

        data = json_lib.loads(request.body)

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

            # Update template fields
            template.name = (data.get('name') or 'Untitled')[:100]
            template.description = (data.get('description') or '')[:500]
            template.template_data = json_lib.dumps(
                data.get('channels' if template_type == 'channels' else 'roles', [])
            )

            db.commit()

            return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Error updating template {template_id}: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred.'}, status=500)


# Wrapper functions for specific template types - Channels
@api_auth_required
def api_channel_template_detail_update_delete(request, guild_id, template_id):
    """GET/PUT/DELETE /api/guild/<id>/templates/channels/<id>/ - Channel template operations."""
    if request.method == 'GET':
        return api_template_detail(request, guild_id, 'channels', template_id)
    elif request.method == 'PUT':
        return api_template_update(request, guild_id, 'channels', template_id)
    elif request.method == 'DELETE':
        return api_template_delete(request, guild_id, 'channels', template_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@require_http_methods(["POST"])
@api_auth_required
def api_channel_template_apply(request, guild_id, template_id):
    """POST /api/guild/<id>/templates/channels/<id>/apply/ - Apply channel template."""
    return api_template_apply(request, guild_id, 'channels', template_id)


# Wrapper functions for specific template types - Roles
@api_auth_required
def api_role_template_detail_update_delete(request, guild_id, template_id):
    """GET/PUT/DELETE /api/guild/<id>/templates/roles/<id>/ - Role template operations."""
    if request.method == 'GET':
        return api_template_detail(request, guild_id, 'roles', template_id)
    elif request.method == 'PUT':
        return api_template_update(request, guild_id, 'roles', template_id)
    elif request.method == 'DELETE':
        return api_template_delete(request, guild_id, 'roles', template_id)
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@require_http_methods(["POST"])
@api_auth_required
def api_role_template_apply(request, guild_id, template_id):
    """POST /api/guild/<id>/templates/roles/<id>/apply/ - Apply role template."""
    return api_template_apply(request, guild_id, 'roles', template_id)




# DISCOVERY / SELF-PROMO
@discord_required
def guild_discovery(request, guild_id):
    """Discovery/Self-Promo dashboard."""
    from .module_utils import has_module_access, has_any_module_access

    user_guilds = request.session.get('discord_admin_guilds', [])
    admin_guilds = user_guilds  # For sidebar navigation
    guild = next((g for g in user_guilds if str(g.get('id')) == str(guild_id)), None)

    if not guild:
        return redirect('questlog_dashboard')

    # Check admin permission
    permissions = int(guild.get('permissions', 0))
    is_admin = (permissions & 0x8) == 0x8 or (permissions & 0x20) == 0x20
    if not is_admin:
        return redirect('questlog_dashboard')

    try:
        from .db import get_db_session
        from .models import DiscoveryConfig, FeaturedPool, Guild, GuildMember, AnnouncedGame, GameSearchConfig
        import time
        import json as json_lib
        from datetime import datetime

        now = int(time.time())

        with get_db_session() as db:
            # Ensure guild exists first
            guild_db = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild_db:
                # Create guild record if it doesn't exist
                guild_db = Guild(
                    guild_id=int(guild_id),
                    guild_name=guild.get('name', 'Unknown'),
                    subscription_tier='free'
                )
                db.add(guild_db)
                db.flush()

            # Get or create discovery config
            discovery_config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not discovery_config:
                discovery_config = DiscoveryConfig(guild_id=int(guild_id))
                db.add(discovery_config)
                db.flush()

            # Get pool entries and enrich with user data
            pool_entries_raw = db.query(FeaturedPool).filter(
                FeaturedPool.guild_id == int(guild_id),
                FeaturedPool.was_selected == False,
                FeaturedPool.expires_at > now
            ).order_by(FeaturedPool.entered_at.desc()).all()

            # Enrich pool entries with user info and extract URLs
            import re
            from datetime import datetime, timezone
            now_dt = datetime.fromtimestamp(now, tz=timezone.utc)
            pool_entries = []
            for entry in pool_entries_raw:
                # Get user info
                member = db.query(GuildMember).filter_by(
                    guild_id=int(guild_id),
                    user_id=entry.user_id
                ).first()

                # Extract URLs from content
                extracted_links = []
                if entry.content:
                    # Better regex to capture full URLs
                    url_pattern = r'https?://[^\s<>"\']+'
                    # url_pattern = r'https?://\S+'
                    urls = re.findall(url_pattern, entry.content)
                    for full_url in urls:
                        # Identify platform based on domain
                        platform_name = None
                        icon = None
                        color = None
                        url_lower = full_url.lower()

                        if 'twitch.tv' in url_lower:
                            platform_name = 'Twitch'
                            icon = 'fab fa-twitch'
                            color = 'purple'
                        elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
                            platform_name = 'YouTube'
                            icon = 'fab fa-youtube'
                            color = 'red'
                        elif 'twitter.com' in url_lower or 'x.com' in url_lower:
                            platform_name = 'Twitter'
                            icon = 'fab fa-twitter'
                            color = 'sky'
                        elif 'tiktok.com' in url_lower:
                            platform_name = 'TikTok'
                            icon = 'fab fa-tiktok'
                            color = 'black'
                        elif 'instagram.com' in url_lower:
                            platform_name = 'Instagram'
                            icon = 'fab fa-instagram'
                            color = 'pink'
                        elif 'bsky.app' in url_lower:
                            platform_name = 'bsky'
                            icon = 'fab fa-bluesky'
                            color = 'teal'
                        elif 'facebook.com' in url_lower or 'fb.com' in url_lower:
                            platform_name = 'Facebook'
                            icon = 'fab fa-facebook'
                            color = 'blue'
                        elif 'kick.com' in url_lower:
                            platform_name = 'Kick'
                            icon = 'fas fa-video'
                            color = 'green'
                        else:
                            platform_name = 'Link'
                            icon = 'fas fa-external-link-alt'
                            color = 'gray'

                        extracted_links.append({
                            'url': full_url,
                            'platform': platform_name,
                            'icon': icon,
                            'color': color
                        })

                # Create clean content without URLs
                clean_content = entry.content
                if clean_content and extracted_links:
                    for link in extracted_links:
                        clean_content = clean_content.replace(link['url'], '')
                    # Clean up extra whitespace
                    clean_content = ' '.join(clean_content.split())

                # Generate avatar URL
                if member and member.avatar_hash:
                    avatar_url = f"https://cdn.discordapp.com/avatars/{entry.user_id}/{member.avatar_hash}.png?size=128"
                else:
                    # Default Discord avatar (matches Discord's new avatar system)
                    default_num = (int(entry.user_id) >> 22) % 6
                    avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_num}.png"

                # Format timestamp for human readability
                entered_dt = datetime.fromtimestamp(entry.entered_at, tz=timezone.utc)
                time_diff = (now_dt - entered_dt).total_seconds()

                # Generate relative time string
                if time_diff < 60:
                    time_ago = "just now"
                elif time_diff < 3600:
                    mins = int(time_diff / 60)
                    time_ago = f"{mins} min{'s' if mins != 1 else ''} ago"
                elif time_diff < 86400:
                    hours = int(time_diff / 3600)
                    time_ago = f"{hours} hour{'s' if hours != 1 else ''} ago"
                elif time_diff < 604800:
                    days = int(time_diff / 86400)
                    time_ago = f"{days} day{'s' if days != 1 else ''} ago"
                else:
                    weeks = int(time_diff / 604800)
                    time_ago = f"{weeks} week{'s' if weeks != 1 else ''} ago"

                pool_entries.append({
                    'id': entry.id,
                    'user_id': entry.user_id,
                    'display_name': member.display_name or member.username or f'User {entry.user_id}' if member else f'User {entry.user_id}',
                    'platform': entry.platform,
                    'content': entry.content,
                    'clean_content': clean_content,
                    'link_url': entry.link_url,
                    'entered_at': entry.entered_at,
                    'entered_at_formatted': entered_dt.strftime('%b %d, %Y at %I:%M %p UTC'),
                    'time_ago': time_ago,
                    'extracted_links': extracted_links,
                    'avatar_url': avatar_url,
                })

            # Get recent features and enrich with user data
            recent_features_raw = db.query(FeaturedPool).filter(
                FeaturedPool.guild_id == int(guild_id),
                FeaturedPool.was_selected == True
            ).order_by(FeaturedPool.selected_at.desc()).limit(10).all()

            # Enrich recent features with user info and formatted dates
            recent_features = []
            for feature in recent_features_raw:
                # Get user info
                member = db.query(GuildMember).filter_by(
                    guild_id=int(guild_id),
                    user_id=feature.user_id
                ).first()

                # Format timestamp
                formatted_date = datetime.fromtimestamp(feature.selected_at).strftime('%b %d, %Y at %I:%M %p') if feature.selected_at else 'Unknown'

                recent_features.append({
                    'user_id': feature.user_id,
                    'username': member.display_name or member.username or f'User {feature.user_id}' if member else f'User {feature.user_id}',
                    'selected_at': feature.selected_at,
                    'formatted_date': formatted_date,
                    'content': feature.content,
                    'link_url': feature.link_url,
                })

            # Check premium
            guild_record = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild_record.is_premium() if guild_record else False

            # Game Discovery Data - Comprehensive lists from IGDB
            available_genres = [
                "Pinball", "Adventure", "Indie", "Arcade", "Visual Novel",
                "Card & Board Game", "MOBA", "Point-and-click", "Fighting", "Shooter",
                "Music", "Platform", "Puzzle", "Racing", "Real Time Strategy (RTS)",
                "Role-playing (RPG)", "Simulator", "Sport", "Strategy",
                "Turn-based strategy (TBS)", "Tactical", "Hack and slash/Beat 'em up",
                "Quiz/Trivia"
            ]

            available_themes = [
                "Action", "Fantasy", "Science fiction", "Horror", "Thriller",
                "Survival", "Historical", "Stealth", "Comedy", "Business",
                "Drama", "Non-fiction", "Sandbox", "Educational", "Kids",
                "Open world", "Warfare", "Party", "4X (explore, expand, exploit, and exterminate)",
                "Erotic", "Mystery", "Romance"
            ]

            available_modes = [
                "Single player",
                "Multiplayer",
                "Co-operative",
                "Split screen",
                "Massively Multiplayer Online (MMO)",
                "Battle Royale",
            ]

            available_platforms = [
                "PC (Microsoft Windows)",
                "Mac",
                "Linux",
                "PlayStation 3",
                "PlayStation 4",
                "PlayStation 5",
                "Xbox 360",
                "Xbox One",
                "Xbox Series X|S",
                "Nintendo Switch",
                "Android",
                "iOS",
                "Web browser",
            ]

            # Parse selected filters from JSON
            selected_genres = json_lib.loads(discovery_config.game_genres) if discovery_config.game_genres else []
            selected_themes = json_lib.loads(discovery_config.game_themes) if discovery_config.game_themes else []
            selected_modes = json_lib.loads(discovery_config.game_modes) if discovery_config.game_modes else []
            selected_platforms = json_lib.loads(discovery_config.game_platforms) if discovery_config.game_platforms else []
            selected_tags = json_lib.loads(discovery_config.game_tags) if discovery_config.game_tags else []

            # Get recent game announcements (exclude private searches)
            recent_game_announcements_raw = db.query(AnnouncedGame).filter(
                AnnouncedGame.guild_id == int(guild_id),
                AnnouncedGame.game_name != '[PRIVATE]'  # Exclude private discoveries
            ).order_by(AnnouncedGame.announced_at.desc()).limit(10).all()

            recent_game_announcements = []
            for game in recent_game_announcements_raw:
                formatted_date = datetime.fromtimestamp(game.announced_at).strftime('%b %d, %Y') if game.announced_at else 'Unknown'
                genres_list = json_lib.loads(game.genres) if game.genres else []

                # Construct IGDB URL if slug exists
                igdb_url = f"https://www.igdb.com/games/{game.igdb_slug}" if game.igdb_slug else None

                recent_game_announcements.append({
                    'game_name': game.game_name,
                    'announced_at': game.announced_at,
                    'formatted_date': formatted_date,
                    'genres_list': genres_list,
                    'cover_url': game.cover_url,
                    'igdb_url': igdb_url,
                })

            # Count total announced games (exclude private searches)
            announced_games_count = db.query(AnnouncedGame).filter(
                AnnouncedGame.guild_id == int(guild_id),
                AnnouncedGame.game_name != '[PRIVATE]'  # Exclude private discoveries
            ).count()

            # Format last check time
            last_game_check = None
            if discovery_config.last_game_check_at:
                hours_ago = (now - discovery_config.last_game_check_at) // 3600
                last_game_check = f"{hours_ago}h ago" if hours_ago > 0 else "Just now"

            # Get game search configs
            search_configs_raw = db.query(GameSearchConfig).filter(
                GameSearchConfig.guild_id == int(guild_id)
            ).order_by(GameSearchConfig.created_at.desc()).all()

            # Process search configs for template
            search_configs = []
            for config in search_configs_raw:
                search_configs.append({
                    'id': config.id,
                    'name': config.name,
                    'enabled': config.enabled,
                    'days_ahead': config.days_ahead,
                    'genres_list': json_lib.loads(config.genres) if config.genres else [],
                    'themes_list': json_lib.loads(config.themes) if config.themes else [],
                    'modes_list': json_lib.loads(config.game_modes) if config.game_modes else [],
                    'platforms_list': json_lib.loads(config.platforms) if config.platforms else [],
                    'min_hype': config.min_hype,
                    'min_rating': config.min_rating,
                })

            # Check if guild has discovery module access
            has_discovery_module = has_module_access(guild_id, 'discovery')
            has_any_module = has_any_module_access(guild_id)

            context = {
                'guild': guild,
                'guild_record': guild_record,
                'discovery_config': discovery_config,
                'pool_entries': pool_entries,
                'pool_count': len(pool_entries),
                'recent_features': recent_features,
                'is_premium': is_premium,
                'is_admin': is_admin,
                # Game Discovery
                'available_genres': available_genres,
                'available_themes': available_themes,
                'available_modes': available_modes,
                'available_platforms': available_platforms,
                'selected_genres': selected_genres,
                'selected_themes': selected_themes,
                'selected_modes': selected_modes,
                'selected_platforms': selected_platforms,
                'selected_tags': selected_tags,
                'recent_game_announcements': recent_game_announcements,
                'announced_games_count': announced_games_count,
                'last_game_check': last_game_check,
                'search_configs': search_configs,
                'total_search_configs': len(search_configs),
                'has_discovery_module': has_discovery_module,
                'has_any_module': has_any_module,
                'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
                'active_page': 'discovery',
                'discovery_enabled': discovery_config.enabled if discovery_config else False,
            }

            return render(request, 'questlog/discovery.html', context)

    except Exception as e:
        # Check if guild has discovery module access (for error case too)
        has_discovery_module = has_module_access(guild_id, 'discovery')
        has_any_module = has_any_module_access(guild_id)

        return render(request, 'questlog/discovery.html', {
            'guild': guild,
            'error': str(e),
            'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
            'is_admin': is_admin,
            'has_discovery_module': has_discovery_module,
            'has_any_module': has_any_module,
            'active_page': 'discovery',
        })


@discord_required
def guild_discovery_network(request, guild_id):
    """Discovery Network dashboard - cross-server creator discovery."""
    from .module_utils import has_module_access, has_any_module_access

    # Serve Open Graph meta tags for social media crawlers (no auth required)
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    is_crawler = any(bot in user_agent for bot in [
        'facebookexternalhit', 'twitterbot', 'linkedinbot', 'discordbot',
        'slackbot', 'telegrambot', 'whatsapp', 'pinterest'
    ])

    if is_crawler:
        from django.http import HttpResponse
        og_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="QuestLog Dashboard - Casual Heroes">
    <meta property="og:description" content="Discover gaming communities, find groups, and connect with players across the Casual Heroes network. Manage your Discord server with powerful moderation, leveling, and discovery tools.">
    <meta property="og:image" content="https://dashboard.casual-heroes.com/static/img/siteassets/homepage/CHLogoFinal.png">
    <meta property="og:url" content="https://dashboard.casual-heroes.com/questlog/guild/{guild_id}/discovery-network/">
    <meta property="og:type" content="website">
    <meta property="article:author" content="Ryven">
    <meta name="author" content="Ryven">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="QuestLog Dashboard - Casual Heroes">
    <meta name="twitter:description" content="Discover gaming communities, find groups, and connect with players across the Casual Heroes network.">
    <meta name="twitter:image" content="https://dashboard.casual-heroes.com/static/img/siteassets/homepage/CHLogoFinal.png">
    <meta name="twitter:creator" content="@Ryven">
</head>
<body>
    <h1>QuestLog Dashboard - Casual Heroes</h1>
    <p>Visit <a href="https://dashboard.casual-heroes.com/">Casual Heroes</a> to explore gaming communities.</p>
</body>
</html>"""
        return HttpResponse(og_html)

    # Check if user is admin of this guild
    admin_guilds = request.session.get('discord_admin_guilds', [])
    guild = next((g for g in admin_guilds if str(g.get('id')) == str(guild_id)), None)

    is_admin = False
    if guild:
        permissions = int(guild.get('permissions', 0))
        is_admin = (permissions & 0x8) == 0x8 or (permissions & 0x20) == 0x20

    # If not admin, check if user is a member and guild is approved
    if not is_admin:
        all_guilds = request.session.get('discord_all_guilds', [])
        guild = next((g for g in all_guilds if str(g.get('id')) == str(guild_id)), None)

        if not guild:
            return redirect('questlog_dashboard')

        # Check if this guild is approved in Discovery Network
        from .db import get_db_session
        from .models import DiscoveryNetworkApplication

        with get_db_session() as db:
            application = db.query(DiscoveryNetworkApplication).filter_by(
                guild_id=int(guild_id),
                status='approved'
            ).first()

            if not application:
                # Not an admin and guild is not approved - redirect
                return redirect('questlog_dashboard')

    # Get guild owner ID from Discord
    guild_owner_id = guild.get('owner_id')
    user_id = request.session.get('discord_user', {}).get('id')
    is_owner = str(guild_owner_id) == str(user_id)

    # Check if user is bot owner (superadmin for Discovery Network)
    import os
    bot_owner_id = os.getenv('BOT_OWNER_ID')
    is_bot_owner = str(user_id) == str(bot_owner_id) if bot_owner_id else False

    try:
        from .db import get_db_session
        from .models import Guild, DiscoveryNetworkApplication, DiscoveryNetworkBan
        import time

        with get_db_session() as db:
            # Get guild record
            guild_record = db.query(Guild).filter_by(guild_id=int(guild_id)).first()

            # Check SERVER's network status (per-guild, not per-user)
            server_network_status = None
            application_date = None
            denial_reason = None
            ban_reason = None
            ban_violation_type = None
            ban_appeal_allowed = False
            ban_appeal_submitted = False
            ban_appeal_reviewed = False
            ban_appeal_approved = False

            # Check if user (owner) is banned from adding ANY servers
            ban = db.query(DiscoveryNetworkBan).filter_by(user_id=int(user_id)).first()
            if ban:
                server_network_status = 'banned'
                ban_reason = ban.reason
                ban_violation_type = ban.violation_type
                ban_appeal_allowed = ban.appeal_allowed
                ban_appeal_submitted = ban.appeal_submitted
                ban_appeal_reviewed = ban.appeal_reviewed
                ban_appeal_approved = ban.appeal_approved
            else:
                # Check application status FOR THIS SPECIFIC SERVER/GUILD
                application = db.query(DiscoveryNetworkApplication).filter_by(
                    guild_id=int(guild_id)
                ).order_by(DiscoveryNetworkApplication.applied_at.desc()).first()

                if application:
                    server_network_status = application.status
                    application_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(application.applied_at))
                    if application.status == 'denied':
                        denial_reason = application.denial_reason

            # Check module access
            has_discovery_module = has_module_access(guild_id, 'discovery')
            has_any_module = has_any_module_access(guild_id)

            # Get user's Discovery Network preferences
            from .models import DiscoveryNetworkPreferences
            user_prefs = db.query(DiscoveryNetworkPreferences).filter_by(
                user_id=int(user_id)
            ).first()

            # Default to all enabled if no preferences exist
            enable_lfg = user_prefs.enable_lfg if user_prefs else True
            enable_games = user_prefs.enable_games if user_prefs else True
            enable_creators = user_prefs.enable_creators if user_prefs else True
            enable_directory = user_prefs.enable_directory if user_prefs else True

            context = {
                'guild': guild,
                'guild_record': guild_record,
                'is_admin': is_admin,
                'is_owner': is_owner,
                'is_bot_owner': is_bot_owner,
                'admin_guilds': admin_guilds,
                'member_guilds': get_member_guilds(request),
                'discord_user': request.session.get('discord_user', {}),
                'active_page': 'discovery_network',
                'has_discovery_module': has_discovery_module,
                'has_any_module': has_any_module,
                'user_network_status': server_network_status,  # Renamed for clarity - this is SERVER status
                'application_date': application_date,
                'denial_reason': denial_reason,
                'ban_reason': ban_reason,
                'ban_violation_type': ban_violation_type,
                'ban_appeal_allowed': ban_appeal_allowed,
                'ban_appeal_submitted': ban_appeal_submitted,
                'ban_appeal_reviewed': ban_appeal_reviewed,
                'ban_appeal_approved': ban_appeal_approved,
                'enable_lfg': enable_lfg,
                'enable_games': enable_games,
                'enable_creators': enable_creators,
                'enable_directory': enable_directory,
            }

            return render(request, 'questlog/discovery_network.html', context)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return render(request, 'questlog/discovery_network.html', {
            'guild': guild,
            'error': str(e),
            'admin_guilds': admin_guilds,
            'member_guilds': get_member_guilds(request),
            'is_admin': is_admin,
            'is_owner': False,
            'has_discovery_module': False,
            'has_any_module': False,
            'active_page': 'discovery_network',
        })


# Discovery Network API Endpoints

@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_network_servers(request):
    """Get list of servers in the Discovery Network - ONLY APPROVED members."""
    try:
        from .db import get_db_session
        from .models import Guild, DiscoveryNetworkApplication

        with get_db_session() as db:
            # ONLY get SERVERS (guilds) with APPROVED applications
            # Applications are per-server, not per-user
            approved_applications = db.query(DiscoveryNetworkApplication).filter_by(
                status='approved'
            ).all()

            # If no approved applications, return empty list
            if not approved_applications:
                return JsonResponse({
                    'success': True,
                    'servers': []
                })

            # Get approved guild IDs (server-specific approvals)
            approved_guild_ids = [app.guild_id for app in approved_applications if app.guild_id]

            # Get guilds that have been approved
            guilds = db.query(Guild).filter(
                Guild.guild_id.in_(approved_guild_ids)
            ).limit(100).all()

            servers = []
            for guild in guilds:
                # Get the server's application to get bio/description
                guild_app = next((app for app in approved_applications if app.guild_id == guild.guild_id), None)

                # Parse tags from JSON
                tags = []
                if guild_app and guild_app.tags:
                    try:
                        import json as json_lib
                        tags = json_lib.loads(guild_app.tags)
                    except:
                        tags = []  # Empty if parsing fails
                # If no tags, leave empty array instead of defaults

                # Check if join is allowed - handle NULL values properly
                # If allow_join is None (NULL in DB), default to False for safety
                allow_join = bool(guild_app.allow_join) if (guild_app and guild_app.allow_join is not None) else False

                # Get actual member count from guild
                member_count = guild.member_count if guild.member_count else 0

                # Calculate activity level based on recent messages
                # You can enhance this logic based on your needs
                activity_level = 'Low'  # Default
                if hasattr(guild, 'total_messages') and guild.total_messages:
                    if guild.total_messages > 1000:
                        activity_level = 'High'
                    elif guild.total_messages > 100:
                        activity_level = 'Medium'

                # Get primary game from guild settings if available
                primary_game = None
                if hasattr(guild, 'primary_game') and guild.primary_game:
                    primary_game = guild.primary_game

                # Construct Discord CDN URL for guild icon
                icon_url = None
                if hasattr(guild, 'guild_icon_hash') and guild.guild_icon_hash:
                    # Discord CDN format: https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png
                    icon_url = f'https://cdn.discordapp.com/icons/{guild.guild_id}/{guild.guild_icon_hash}.png'

                # Get Discord invite URL (use invite_code from application if available)
                invite_url = None
                if guild_app and guild_app.invite_code and allow_join:
                    # Use invite code from the application (e.g., "abc123" -> "https://discord.gg/abc123")
                    invite_url = f'https://discord.gg/{guild_app.invite_code}'

                servers.append({
                    'id': str(guild.guild_id),
                    'name': guild.guild_name or 'QuestLog Community',
                    'description': guild_app.bio[:200] if guild_app and guild_app.bio else 'A QuestLog gaming community',
                    'icon_url': icon_url,  # Discord CDN URL or None
                    'member_count': member_count,  # From Guild model
                    'activity_level': activity_level,  # Calculated from guild activity
                    'primary_game': primary_game,  # From guild settings
                    'tags': tags,  # From application (empty if none selected)
                    'allow_join': allow_join,  # From application
                    'invite_url': invite_url,  # Discord invite URL (if available)
                })

            return JsonResponse({
                'success': True,
                'servers': servers
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_network_lfg(request):
    """Get cross-server LFG posts from Discovery Network guilds."""
    try:
        from .db import get_db_session
        from .models import LFGGroup, LFGGame, Guild, DiscoveryNetworkApplication
        from sqlalchemy import and_

        with get_db_session() as db:
            # Get all guilds in Discovery Network (approved applications)
            network_guilds = db.query(DiscoveryNetworkApplication.guild_id).filter(
                DiscoveryNetworkApplication.status == 'approved'
            ).all()
            network_guild_ids = [g[0] for g in network_guilds]

            if not network_guild_ids:
                return JsonResponse({
                    'success': True,
                    'posts': []
                })

            # Get active LFG groups from Discovery Network guilds
            active_groups = db.query(
                LFGGroup, LFGGame, Guild
            ).join(
                LFGGame, LFGGroup.game_id == LFGGame.id
            ).join(
                Guild, LFGGroup.guild_id == Guild.guild_id
            ).filter(
                and_(
                    LFGGroup.guild_id.in_(network_guild_ids),
                    LFGGroup.is_active == True,
                    LFGGroup.is_full == False
                )
            ).order_by(
                LFGGroup.created_at.desc()
            ).limit(100).all()

            posts = []
            for lfg_group, game, guild in active_groups:
                # Parse custom_data for additional details
                custom_data = {}
                if lfg_group.custom_data:
                    try:
                        import json as json_lib
                        custom_data = json_lib.loads(lfg_group.custom_data)
                    except:
                        custom_data = {}

                # Determine platform, activity, skill level, player_role from custom_data
                platform = custom_data.get('platform', 'PC')
                # Activity is now stored as an array, but we return it as-is for frontend to handle
                activity = custom_data.get('activity', ['casual'])
                # Ensure activity is always an array for consistency
                if not isinstance(activity, list):
                    activity = [activity] if activity else ['casual']
                skill_level = custom_data.get('skill_level', 'any')
                voice_required = custom_data.get('voice_required', False)
                player_role = custom_data.get('player_role', '')

                # Calculate start time
                start_time = 'now'
                if lfg_group.scheduled_time:
                    now = int(time.time())
                    time_diff = lfg_group.scheduled_time - now
                    if time_diff > 7200:  # More than 2 hours
                        start_time = 'custom'
                    elif time_diff > 3600:  # More than 1 hour
                        start_time = '2hours'
                    elif time_diff > 0:
                        start_time = 'hour'

                # Get members for this group with avatar info
                from .models import LFGMember, GuildMember
                members = db.query(LFGMember).filter(
                    LFGMember.group_id == lfg_group.id,
                    LFGMember.left_at == None
                ).all()

                members_list = []
                for member in members:
                    # Try to get avatar from GuildMember table
                    guild_member = db.query(GuildMember).filter(
                        GuildMember.guild_id == lfg_group.guild_id,
                        GuildMember.user_id == member.user_id
                    ).first()

                    if guild_member and guild_member.avatar_hash:
                        # Construct Discord CDN URL with custom avatar
                        avatar_url = f"https://cdn.discordapp.com/avatars/{member.user_id}/{guild_member.avatar_hash}.png"
                    else:
                        # Use Discord's default avatar (calculated from user ID)
                        # New Discord system uses (user_id >> 22) % 6 for default avatar index
                        default_avatar_index = (int(member.user_id) >> 22) % 6
                        avatar_url = f"https://cdn.discordapp.com/embed/avatars/{default_avatar_index}.png"

                    member_data = {
                        'user_id': str(member.user_id),
                        'display_name': member.display_name or 'Unknown',
                        'is_creator': member.is_creator,
                        'is_co_leader': member.is_co_leader,
                        'avatar_url': avatar_url
                    }
                    # Add role info if available
                    if member.selections:
                        try:
                            import json as json_lib
                            selections = json_lib.loads(member.selections)
                            if selections.get('player_role'):
                                member_data['player_role'] = selections['player_role']
                        except:
                            pass
                    members_list.append(member_data)

                # Get creator's avatar
                creator_guild_member = db.query(GuildMember).filter(
                    GuildMember.guild_id == lfg_group.guild_id,
                    GuildMember.user_id == lfg_group.creator_id
                ).first()

                if creator_guild_member and creator_guild_member.avatar_hash:
                    # Use custom avatar if available
                    creator_avatar = f"https://cdn.discordapp.com/avatars/{lfg_group.creator_id}/{creator_guild_member.avatar_hash}.png"
                else:
                    # Use Discord's default avatar (calculated from user ID)
                    default_avatar_index = (int(lfg_group.creator_id) >> 22) % 6
                    creator_avatar = f"https://cdn.discordapp.com/embed/avatars/{default_avatar_index}.png"

                posts.append({
                    'id': str(lfg_group.id),
                    'game': game.game_name if game else 'Unknown',
                    'title': lfg_group.thread_name or f"LFG for {game.game_name if game else 'game'}",
                    'description': lfg_group.description or '',
                    'platform': platform,
                    'activity': activity,
                    'skill_level': skill_level,
                    'spots_needed': (lfg_group.max_group_size or game.max_group_size or 5) - lfg_group.member_count,
                    'voice_required': voice_required,
                    'start_time': start_time,
                    'scheduled_time': lfg_group.scheduled_time if lfg_group.scheduled_time else None,
                    'created_at': lfg_group.created_at,
                    'user_id': str(lfg_group.creator_id),
                    'username': lfg_group.creator_name or 'Unknown',
                    'user_avatar': creator_avatar,
                    'server_name': guild.guild_name or 'Unknown Server',
                    'guild_id': str(guild.guild_id),
                    'player_role': player_role,
                    'member_count': lfg_group.member_count,
                    'max_group_size': lfg_group.max_group_size or game.max_group_size or 5,
                    'members': members_list,
                    'cover_url': game.cover_url if game else None,
                    'igdb_id': game.igdb_id if game else None,
                    'igdb_slug': game.igdb_slug if game else None,
                    'event_duration': lfg_group.event_duration,
                    'activity_type': activity
                })

            return JsonResponse({
                'success': True,
                'posts': posts
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def api_discovery_lfg_create(request):
    """Create a new Cross-Server LFG post in the Discovery Network."""
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import LFGGroup, LFGGame, Guild, DiscoveryNetworkApplication

        # Parse request body
        data = json_lib.loads(request.body)

        # Required fields
        guild_id = data.get('guild_id')
        game_name = data.get('game')
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()

        # Input length validation (prevent DoS)
        MAX_TITLE_LENGTH = 200
        MAX_DESCRIPTION_LENGTH = 2000
        MAX_GAME_NAME_LENGTH = 100

        if not guild_id or not game_name:
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields: guild_id and game'
            }, status=400)

        if not title:
            return JsonResponse({
                'success': False,
                'error': 'Title is required'
            }, status=400)

        if len(title) > MAX_TITLE_LENGTH:
            return JsonResponse({
                'success': False,
                'error': f'Title must be {MAX_TITLE_LENGTH} characters or less'
            }, status=400)

        if len(description) > MAX_DESCRIPTION_LENGTH:
            return JsonResponse({
                'success': False,
                'error': f'Description must be {MAX_DESCRIPTION_LENGTH} characters or less'
            }, status=400)

        if len(game_name) > MAX_GAME_NAME_LENGTH:
            return JsonResponse({
                'success': False,
                'error': f'Game name must be {MAX_GAME_NAME_LENGTH} characters or less'
            }, status=400)

        with get_db_session() as db:
            # Verify guild is in Discovery Network
            network_app = db.query(DiscoveryNetworkApplication).filter(
                DiscoveryNetworkApplication.guild_id == int(guild_id),
                DiscoveryNetworkApplication.status == 'approved'
            ).first()

            if not network_app:
                return JsonResponse({
                    'success': False,
                    'error': 'Your guild is not in the Discovery Network'
                }, status=403)

            # Get guild to check tier limits
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({
                    'success': False,
                    'error': 'Guild not found'
                }, status=404)

            # Check Discovery Network LFG posting limit
            can_post, current_count, limit, reset_date = check_discovery_lfg_post_limit(db, guild_id, guild)
            if not can_post:
                return JsonResponse({
                    'success': False,
                    'error': f'Monthly LFG posting limit reached. You have posted {current_count}/{limit} LFG posts this month. Limit resets on {reset_date}. Upgrade to the LFG Module or Complete Suite for unlimited posting!',
                    'limit_reached': True,
                    'current_count': current_count,
                    'limit': limit,
                    'reset_date': reset_date
                }, status=429)

            # Get or create LFGGame
            game = db.query(LFGGame).filter(
                LFGGame.guild_id == int(guild_id),
                LFGGame.game_name == game_name
            ).first()

            if not game:
                # Try to find IGDB data from another server's game entry
                from sqlalchemy import func
                existing_game_with_igdb = db.query(LFGGame).filter(
                    func.lower(LFGGame.game_name) == game_name.lower(),
                    LFGGame.igdb_id != None,
                    LFGGame.cover_url != None
                ).first()

                # Create new game entry for this guild
                game = LFGGame(
                    guild_id=int(guild_id),
                    game_name=game_name,
                    game_short=game_name.lower().replace(' ', '_')[:50],
                    enabled=True,
                    max_group_size=5,  # Default
                    # Copy IGDB data if found
                    igdb_id=existing_game_with_igdb.igdb_id if existing_game_with_igdb else None,
                    igdb_slug=existing_game_with_igdb.igdb_slug if existing_game_with_igdb else None,
                    cover_url=existing_game_with_igdb.cover_url if existing_game_with_igdb else None
                )
                db.add(game)
                db.flush()
            elif not game.cover_url or not game.igdb_id:
                # Game exists but is missing IGDB data - try to enrich it
                from sqlalchemy import func
                existing_game_with_igdb = db.query(LFGGame).filter(
                    func.lower(LFGGame.game_name) == game_name.lower(),
                    LFGGame.igdb_id != None,
                    LFGGame.cover_url != None
                ).first()

                if existing_game_with_igdb:
                    # Update existing game with IGDB data
                    if not game.igdb_id:
                        game.igdb_id = existing_game_with_igdb.igdb_id
                    if not game.igdb_slug:
                        game.igdb_slug = existing_game_with_igdb.igdb_slug
                    if not game.cover_url:
                        game.cover_url = existing_game_with_igdb.cover_url
                    db.flush()

            # Build custom_data JSON with player role/class/spec
            # Activity can now be an array (multi-select up to 3)
            activity_value = data.get('activity', 'casual')
            # If activity is a list, keep it as is; otherwise wrap single value in list for consistency
            if isinstance(activity_value, list):
                activity = activity_value
            else:
                activity = [activity_value] if activity_value else ['casual']

            custom_data = {
                'platform': data.get('platform', 'PC'),
                'activity': activity,  # Now stored as array
                'skill_level': data.get('skill_level', 'any'),
                'voice_required': data.get('voice_required', False)
            }

            # Add player role/class/spec info
            if data.get('player_role'):
                custom_data['player_role'] = data.get('player_role')
            if data.get('player_class'):
                custom_data['player_class'] = data.get('player_class')
            if data.get('player_spec'):
                custom_data['player_spec'] = data.get('player_spec')

            # Calculate scheduled_time from scheduled_time input (datetime-local from form)
            scheduled_time = None
            scheduled_time_input = data.get('scheduled_time', '').strip()

            if scheduled_time_input:
                # Parse datetime-local format: "2025-12-23T15:30"
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(scheduled_time_input)
                    scheduled_time = int(dt.timestamp())
                except:
                    # If parsing fails, default to now
                    scheduled_time = int(time.time())
            else:
                # No scheduled time provided, default to "now"
                scheduled_time = int(time.time())

            # Get user info from session (same pattern as api_lfg_browser_create)
            discord_user = request.session.get('discord_user', {})
            user_id = discord_user.get('id')
            user_name = discord_user.get('username', 'Unknown')

            if not user_id:
                return JsonResponse({
                    'success': False,
                    'error': 'You must be logged in to create LFG posts'
                }, status=401)

            # Create LFG group (using a placeholder thread_id since this is web-based)
            # The bot will need to create actual Discord threads when users join
            lfg_group = LFGGroup(
                guild_id=int(guild_id),
                game_id=game.id,
                thread_id=0,  # Placeholder - bot will create thread on first join
                thread_name=title,
                creator_id=int(user_id),
                creator_name=user_name,
                scheduled_time=scheduled_time,
                description=description,
                custom_data=json_lib.dumps(custom_data),
                max_group_size=int(data.get('group_size', game.max_group_size or 5)),
                event_duration=int(data.get('event_duration')) if data.get('event_duration') else None,
                is_active=True,
                is_full=False,
                member_count=1  # Creator counts as first member
            )

            db.add(lfg_group)
            db.flush()  # Get the group ID

            # Add creator as first member (leader)
            from .models import LFGMember

            # Build selections JSON for creator's class/spec/role
            creator_selections = {}
            if data.get('player_role'):
                creator_selections['player_role'] = data.get('player_role')

            creator_member = LFGMember(
                group_id=lfg_group.id,
                user_id=int(user_id),
                display_name=user_name,
                is_creator=True,
                is_co_leader=False,
                selections=json_lib.dumps(creator_selections) if creator_selections else None,
                joined_at=int(time.time())
            )

            db.add(creator_member)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'LFG post created successfully!',
                'post_id': lfg_group.id
            })

    except json_lib.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["POST"])
def api_discovery_lfg_join(request, post_id):
    """POST /api/discovery/lfg/<post_id>/join - Join a Discovery Network LFG post."""
    try:
        import json as json_lib
        import time
        from .db import get_db_session
        from .models import LFGGroup, LFGMember, Guild, DiscoveryNetworkApplication

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')
        username = discord_user.get('username', 'Unknown')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'You must be logged in to join LFG posts'
            }, status=401)

        # Parse request body for options (if provided)
        data = json_lib.loads(request.body) if request.body else {}
        options = data.get('options', {})

        with get_db_session() as db:
            # Get the LFG group
            group = db.query(LFGGroup).filter_by(id=int(post_id)).first()
            if not group:
                return JsonResponse({
                    'success': False,
                    'error': 'LFG post not found'
                }, status=404)

            if not group.is_active:
                return JsonResponse({
                    'success': False,
                    'error': 'This LFG post is no longer active'
                }, status=400)

            if group.is_full:
                return JsonResponse({
                    'success': False,
                    'error': 'This group is already full'
                }, status=400)

            # Check if user has any existing member record (active or left)
            existing = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id)
            ).first()

            # Extract rank if provided
            rank_value = options.get('rank')

            # Extract other selections (exclude 'rank' as it's stored separately)
            selections = {k: v for k, v in options.items() if k != 'rank'}
            selections_json = json_lib.dumps(selections) if selections else None

            if existing:
                # Check if they're currently in the group
                if existing.left_at is None:
                    return JsonResponse({
                        'success': False,
                        'error': 'You are already in this group'
                    }, status=400)

                # They left before, so rejoin them by updating their record
                existing.display_name = username
                existing.rank_value = rank_value
                existing.selections = selections_json
                existing.joined_at = int(time.time())
                existing.left_at = None  # Clear the left timestamp

                # Update group member count
                group.member_count += 1
                if group.member_count >= group.max_group_size:
                    group.is_full = True
            else:
                # Add new member
                new_member = LFGMember(
                    group_id=group.id,
                    user_id=int(user_id),
                    display_name=username,
                    is_creator=False,
                    rank_value=rank_value,
                    selections=selections_json,
                    joined_at=int(time.time())
                )
                db.add(new_member)

                # Update group member count
                group.member_count += 1
                if group.member_count >= group.max_group_size:
                    group.is_full = True

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Successfully joined the group!',
                'member_count': group.member_count
            })

    except json_lib.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["PATCH"])
def api_discovery_lfg_update(request, post_id):
    """PATCH /api/discovery/lfg/<post_id>/update - Update a Discovery Network LFG post."""
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import LFGGroup, LFGMember

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'You must be logged in'
            }, status=401)

        # Parse request body
        data = json_lib.loads(request.body)

        with get_db_session() as db:
            # Get the LFG group
            group = db.query(LFGGroup).filter_by(id=int(post_id)).first()
            if not group:
                return JsonResponse({
                    'success': False,
                    'error': 'LFG post not found'
                }, status=404)

            # Check if user is creator or co-leader
            is_creator = str(group.creator_id) == str(user_id)
            member = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id)
            ).filter(LFGMember.left_at == None).first()

            is_co_leader = member and member.is_co_leader if member else False

            if not is_creator and not is_co_leader:
                return JsonResponse({
                    'success': False,
                    'error': 'Only the creator or co-leaders can edit this post'
                }, status=403)

            # Update fields
            if 'title' in data:
                group.thread_name = data['title']
            if 'description' in data:
                group.description = data['description']
            if 'scheduled_time' in data:
                group.scheduled_time = data['scheduled_time']
            if 'event_duration' in data:
                group.event_duration = data['event_duration']
            if 'max_group_size' in data:
                group.max_group_size = data['max_group_size']
                # Update is_full status
                group.is_full = group.member_count >= group.max_group_size

            # Update custom_data (platform, activity, skill_level, voice_required)
            custom_data = json_lib.loads(group.custom_data) if group.custom_data else {}
            if 'platform' in data:
                custom_data['platform'] = data['platform']
            if 'activity_type' in data:
                custom_data['activity'] = data['activity_type']
            if 'skill_level' in data:
                custom_data['skill_level'] = data['skill_level']
            if 'voice_required' in data:
                custom_data['voice_required'] = data['voice_required']

            group.custom_data = json_lib.dumps(custom_data)

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'LFG post updated successfully'
            })

    except json_lib.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["PATCH"])
def api_discovery_lfg_update_class(request, post_id):
    """PATCH /api/discovery/lfg/<post_id>/update-class - Update member's class/role."""
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import LFGGroup, LFGMember

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'You must be logged in'
            }, status=401)

        # Parse request body
        data = json_lib.loads(request.body)
        player_role = data.get('player_role')

        if not player_role:
            return JsonResponse({
                'success': False,
                'error': 'Player role is required'
            }, status=400)

        with get_db_session() as db:
            # Get the LFG group
            group = db.query(LFGGroup).filter_by(id=int(post_id)).first()
            if not group:
                return JsonResponse({
                    'success': False,
                    'error': 'LFG post not found'
                }, status=404)

            # Get member record
            member = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id)
            ).filter(LFGMember.left_at == None).first()

            if not member:
                return JsonResponse({
                    'success': False,
                    'error': 'You are not a member of this group'
                }, status=403)

            # Update member's selections with player_role
            selections = json_lib.loads(member.selections) if member.selections else {}
            selections['player_role'] = player_role
            member.selections = json_lib.dumps(selections)

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Class updated successfully'
            })

    except json_lib.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON in request body'
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@require_http_methods(["DELETE"])
def api_discovery_lfg_delete(request, post_id):
    """DELETE /api/discovery/lfg/<post_id>/delete - Delete a Discovery Network LFG post."""
    try:
        from .db import get_db_session
        from .models import LFGGroup, LFGMember

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'You must be logged in'
            }, status=401)

        with get_db_session() as db:
            # Get the LFG group
            group = db.query(LFGGroup).filter_by(id=int(post_id)).first()
            if not group:
                return JsonResponse({
                    'success': False,
                    'error': 'LFG post not found'
                }, status=404)

            # Only creator can delete
            if str(group.creator_id) != str(user_id):
                return JsonResponse({
                    'success': False,
                    'error': 'Only the creator can delete this post'
                }, status=403)

            # Mark as inactive instead of deleting
            group.is_active = False
            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'LFG post deleted successfully'
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_network_games(request):
    """Get games from LFG settings across all Discovery Network servers (for Server Directory filtering)."""
    try:
        from .db import get_db_session
        from .models import LFGGame, DiscoveryNetworkApplication

        with get_db_session() as db:
            # Get all guilds in Discovery Network (approved applications)
            network_guilds = db.query(DiscoveryNetworkApplication.guild_id).filter(
                DiscoveryNetworkApplication.status == 'approved'
            ).all()
            network_guild_ids = [g[0] for g in network_guilds]

            if not network_guild_ids:
                return JsonResponse({
                    'success': True,
                    'games': []
                })

            # Get all unique games from LFG settings in Discovery Network
            lfg_games = db.query(LFGGame).filter(
                LFGGame.guild_id.in_(network_guild_ids)
            ).order_by(LFGGame.game_name).all()

            # Build unique games list
            game_set = set()
            games_list = []

            for game in lfg_games:
                if game.game_name and game.game_name not in game_set:
                    game_set.add(game.game_name)
                    games_list.append({
                        'name': game.game_name,
                        'slug': game.game_name.lower().replace(' ', '-').replace(':', '').replace("'", '')
                    })

            # Sort alphabetically
            games_list.sort(key=lambda x: x['name'])

            return JsonResponse({
                'success': True,
                'games': games_list
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_game_templates(request):
    """Get ALL custom templates for a specific game from Discovery Network servers."""
    try:
        from .db import get_db_session
        from .models import LFGGame, DiscoveryNetworkApplication
        import json as json_lib

        game_name = request.GET.get('game')
        if not game_name:
            return JsonResponse({
                'success': False,
                'error': 'Game name required'
            }, status=400)

        with get_db_session() as db:
            from sqlalchemy import and_, or_
            import logging
            logger = logging.getLogger(__name__)

            # Get all guilds in Discovery Network
            network_guilds = db.query(DiscoveryNetworkApplication.guild_id).filter(
                DiscoveryNetworkApplication.status == 'approved'
            ).all()
            network_guild_ids = [g[0] for g in network_guilds]
            logger.info(f"Found {len(network_guild_ids)} guilds in Discovery Network")

            # Find all LFG game configurations for this game across Discovery Network
            # Check both exact match and partial match for game name
            lfg_games = db.query(LFGGame).filter(
                and_(
                    or_(
                        LFGGame.game_name.ilike(f'%{game_name}%'),
                        LFGGame.game_name == game_name
                    ),
                    LFGGame.guild_id.in_(network_guild_ids) if network_guild_ids else True,
                    LFGGame.custom_options.isnot(None)
                )
            ).all()
            logger.info(f"Found {len(lfg_games)} LFG games matching '{game_name}'")

            # Collect all unique templates
            templates = []
            seen_template_names = set()

            for lfg_game in lfg_games:
                if not lfg_game.custom_options:
                    logger.debug(f"Game {lfg_game.game_name} has no custom_options")
                    continue

                try:
                    custom_options = json_lib.loads(lfg_game.custom_options)
                    logger.debug(f"Parsed custom_options for {lfg_game.game_name}: {type(custom_options)}")

                    # Handle both array format and dict format
                    options_list = []
                    if isinstance(custom_options, list):
                        # Direct array format: [{name: "Class", choices: [...]}]
                        options_list = custom_options
                        logger.debug(f"Found array format with {len(custom_options)} options")
                    elif isinstance(custom_options, dict) and 'options' in custom_options:
                        # Dict format: {options: [{name: "Class", choices: [...]}]}
                        options_list = custom_options['options']
                        logger.debug(f"Found dict format with {len(options_list)} options")
                    else:
                        logger.debug(f"custom_options structure invalid: {custom_options}")
                        continue

                    # Process the options
                    for option in options_list:
                        if not isinstance(option, dict):
                            continue
                        template_name = option.get('name', '')
                        if template_name and template_name not in seen_template_names:
                            seen_template_names.add(template_name)
                            template_data = {
                                'name': template_name,
                                'choices': option.get('choices', [])
                            }
                            # Include depends_on if it exists (for Class + Spec systems)
                            if 'depends_on' in option:
                                template_data['depends_on'] = option['depends_on']
                            templates.append(template_data)
                            logger.info(f"Added template: {template_name} with {len(option.get('choices', []) if isinstance(option.get('choices'), list) else option.get('choices', {}))} choices")
                except Exception as e:
                    logger.error(f"Failed to parse custom_options for {lfg_game.game_name}: {e}")
                    continue

            return JsonResponse({
                'success': True,
                'templates': templates
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_game_roles(request):
    """DEPRECATED: Use api_discovery_game_templates instead. Kept for backwards compatibility."""
    return api_discovery_game_templates(request)


@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_network_lfg_games(request):
    """Get games from LFG settings across all Discovery Network servers."""
    try:
        from .db import get_db_session
        from .models import LFGGame, Guild, DiscoveryNetworkApplication
        from sqlalchemy import and_

        with get_db_session() as db:
            # Get all guilds in Discovery Network (approved applications)
            network_guilds = db.query(DiscoveryNetworkApplication.guild_id).filter(
                DiscoveryNetworkApplication.status == 'approved'
            ).all()
            network_guild_ids = [g[0] for g in network_guilds]

            if not network_guild_ids:
                return JsonResponse({
                    'success': True,
                    'games': []
                })

            # Get all unique games from LFG settings in Discovery Network
            lfg_games = db.query(LFGGame).filter(
                LFGGame.guild_id.in_(network_guild_ids)
            ).order_by(LFGGame.game_name).all()

            # Build unique games list
            games_set = set()
            games_list = []

            for game in lfg_games:
                if game.game_name and game.game_name not in games_set:
                    games_set.add(game.game_name)
                    games_list.append({
                        'name': game.game_name,
                        'slug': game.game_name.lower().replace(' ', '-').replace(':', '').replace("'", '')
                    })

            # Sort alphabetically
            games_list.sort(key=lambda x: x['name'])

            return JsonResponse({
                'success': True,
                'games': games_list
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@discord_required
@require_http_methods(["GET"])
def api_discovery_network_lfg_activities(request):
    """Get all unique activity options from LFG games across Discovery Network."""
    try:
        from .db import get_db_session
        from .models import LFGGame, DiscoveryNetworkApplication
        import json

        with get_db_session() as db:
            # Get all guilds in Discovery Network (approved applications)
            network_guilds = db.query(DiscoveryNetworkApplication.guild_id).filter(
                DiscoveryNetworkApplication.status == 'approved'
            ).all()
            network_guild_ids = [g[0] for g in network_guilds]

            if not network_guild_ids:
                return JsonResponse({
                    'success': True,
                    'activities': []
                })

            # Get all LFG games from Discovery Network
            lfg_games = db.query(LFGGame).filter(
                LFGGame.guild_id.in_(network_guild_ids)
            ).all()

            # Extract all unique activity values from custom_options
            activities_set = set()

            for game in lfg_games:
                if not game.custom_options:
                    continue

                try:
                    custom_options = json.loads(game.custom_options)
                    for option in custom_options:
                        # Look for "Activity" field
                        if option.get('name', '').lower() == 'activity':
                            choices = option.get('choices', [])
                            # Handle both array and object-based choices
                            if isinstance(choices, list):
                                for choice in choices:
                                    if choice and isinstance(choice, str):
                                        activities_set.add(choice.strip())
                            elif isinstance(choices, dict):
                                # For conditional dropdowns, get all values
                                for values in choices.values():
                                    if isinstance(values, list):
                                        for v in values:
                                            if v and isinstance(v, str):
                                                activities_set.add(v.strip())
                except:
                    continue

            # Convert to list and sort
            activities_list = sorted(list(activities_set))

            return JsonResponse({
                'success': True,
                'activities': activities_list
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@discord_required
@require_http_methods(["GET"])
def api_discovery_game_config(request):
    """Get custom_options configuration for a specific game across Discovery Network."""
    try:
        from .db import get_db_session
        from .models import LFGGame, DiscoveryNetworkApplication
        import json

        game_name = request.GET.get('game_name')

        if not game_name:
            return JsonResponse({
                'success': False,
                'error': 'game_name parameter is required'
            }, status=400)

        with get_db_session() as db:
            # Get all guilds in Discovery Network (approved applications)
            network_guilds = db.query(DiscoveryNetworkApplication.guild_id).filter(
                DiscoveryNetworkApplication.status == 'approved'
            ).all()
            network_guild_ids = [g[0] for g in network_guilds]

            if not network_guild_ids:
                return JsonResponse({
                    'success': True,
                    'custom_options': []
                })

            # Find this game in any Discovery Network server
            # Try exact match first, then case-insensitive
            lfg_game = db.query(LFGGame).filter(
                LFGGame.guild_id.in_(network_guild_ids),
                LFGGame.game_name == game_name
            ).first()

            if not lfg_game:
                # Try case-insensitive match
                lfg_game = db.query(LFGGame).filter(
                    LFGGame.guild_id.in_(network_guild_ids),
                    LFGGame.game_name.ilike(game_name)
                ).first()

            if not lfg_game or not lfg_game.custom_options:
                return JsonResponse({
                    'success': True,
                    'custom_options': []
                })

            # Parse and return custom_options
            try:
                custom_options = json.loads(lfg_game.custom_options)
                return JsonResponse({
                    'success': True,
                    'custom_options': custom_options
                })
            except:
                return JsonResponse({
                    'success': True,
                    'custom_options': []
                })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@discord_required
@require_http_methods(["POST"])
def api_discovery_network_apply(request):
    """Submit application to join Discovery Network."""
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import DiscoveryNetworkApplication, DiscoveryNetworkBan
        import time

        data = json_lib.loads(request.body)
        user = request.session.get('discord_user', {})
        user_id = user.get('id')
        guild_id = data.get('guild_id')  # Get guild_id from form data

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        if not guild_id:
            return JsonResponse({
                'success': False,
                'error': 'Guild ID is required'
            }, status=400)

        with get_db_session() as db:
            # Check if user (owner) is banned from adding ANY servers
            ban = db.query(DiscoveryNetworkBan).filter_by(user_id=int(user_id)).first()
            if ban:
                return JsonResponse({
                    'success': False,
                    'error': 'You are banned from the Discovery Network'
                }, status=403)

            # Check for existing pending application FOR THIS SPECIFIC SERVER
            existing = db.query(DiscoveryNetworkApplication).filter_by(
                guild_id=int(guild_id),
                status='pending'
            ).first()

            if existing:
                return JsonResponse({
                    'success': False,
                    'error': 'This server already has a pending application'
                }, status=400)

            # Serialize tags to JSON
            tags = data.get('tags', [])
            tags_json = json_lib.dumps(tags) if tags else None

            # Create new application for this specific server
            application = DiscoveryNetworkApplication(
                user_id=int(user_id),
                guild_id=int(guild_id),  # Server-specific application
                bio=data.get('bio', ''),
                twitch_url=data.get('twitch_url'),
                youtube_url=data.get('youtube_url'),
                twitter_url=data.get('twitter_url'),
                tiktok_url=data.get('tiktok_url'),
                instagram_url=data.get('instagram_url'),
                bsky_url=data.get('bsky_url'),
                username=user.get('username', 'Unknown'),
                display_name=user.get('global_name'),
                avatar_url=f"https://cdn.discordapp.com/avatars/{user_id}/{user.get('avatar')}.png" if user.get('avatar') else None,
                account_created_at=int(time.time()),  # Would need actual Discord account creation time
                guidelines_accepted=data.get('guidelines_accepted', False),
                tos_accepted=data.get('tos_accepted', False),
                content_policy_accepted=data.get('content_policy_accepted', False),
                tags=tags_json,  # JSON array of tags
                allow_join=data.get('allow_join', False),  # Allow others to join
                status='pending',
                applied_at=int(time.time()),
                updated_at=int(time.time())
            )

            db.add(application)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Application submitted successfully'
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@discord_required
@require_http_methods(["GET", "POST"])
def api_discovery_network_preferences(request):
    """Get or update Discovery Network preferences for the current user."""
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import DiscoveryNetworkPreferences
        import time

        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        with get_db_session() as db:
            # GET - Load preferences
            if request.method == 'GET':
                prefs = db.query(DiscoveryNetworkPreferences).filter_by(user_id=int(user_id)).first()

                # Also get allow_join and invite_code from the server's application (server setting, not user pref)
                from .models import DiscoveryNetworkApplication
                guild_id = request.GET.get('guild_id') or request.session.get('guild_id')
                allow_join = False
                invite_code = None

                if guild_id:
                    application = db.query(DiscoveryNetworkApplication).filter_by(
                        guild_id=int(guild_id),
                        status='approved'
                    ).first()

                    if application:
                        allow_join = application.allow_join
                        invite_code = application.invite_code

                if not prefs:
                    # Return default preferences
                    return JsonResponse({
                        'success': True,
                        'preferences': {
                            'enable_lfg': True,
                            'enable_games': True,
                            'enable_creators': True,
                            'enable_directory': True,
                            'preferred_games': [],
                            'preferred_tags': [],
                            'preferred_activities': [],
                            'preferred_skill_levels': [],
                            'preferred_size': '',
                            'lfg_filter_games': False,
                            'lfg_filter_activities': False,
                            'lfg_filter_skill_levels': False,
                            'lfg_show_now': True,
                            'lfg_hide_voice': False,
                            'notify_lfg': False,
                            'notify_servers': False,
                            'notify_digest': False,
                            'privacy_show_profile': True,
                            'privacy_show_server': True,
                            'privacy_allow_dms': True,
                            'allow_join': allow_join,
                            'invite_code': invite_code
                        }
                    })

                # Parse JSON fields
                preferred_games = []
                preferred_tags = []
                preferred_activities = []
                preferred_skill_levels = []
                try:
                    if prefs.preferred_games:
                        preferred_games = json_lib.loads(prefs.preferred_games)
                    if prefs.preferred_tags:
                        preferred_tags = json_lib.loads(prefs.preferred_tags)
                    if prefs.preferred_activities:
                        preferred_activities = json_lib.loads(prefs.preferred_activities)
                    if prefs.preferred_skill_levels:
                        preferred_skill_levels = json_lib.loads(prefs.preferred_skill_levels)
                except:
                    pass

                return JsonResponse({
                    'success': True,
                    'preferences': {
                        'enable_lfg': prefs.enable_lfg,
                        'enable_games': prefs.enable_games,
                        'enable_creators': prefs.enable_creators,
                        'enable_directory': prefs.enable_directory,
                        'preferred_games': preferred_games,
                        'preferred_tags': preferred_tags,
                        'preferred_activities': preferred_activities,
                        'preferred_skill_levels': preferred_skill_levels,
                        'preferred_size': prefs.preferred_size or '',
                        'lfg_filter_games': prefs.lfg_filter_games,
                        'lfg_filter_activities': prefs.lfg_filter_activities,
                        'lfg_filter_skill_levels': prefs.lfg_filter_skill_levels,
                        'lfg_show_now': prefs.lfg_show_now,
                        'lfg_hide_voice': prefs.lfg_hide_voice,
                        'notify_lfg': prefs.notify_lfg,
                        'notify_servers': prefs.notify_servers,
                        'notify_digest': prefs.notify_digest,
                        'privacy_show_profile': prefs.privacy_show_profile,
                        'privacy_show_server': prefs.privacy_show_server,
                        'privacy_allow_dms': prefs.privacy_allow_dms,
                        'allow_join': allow_join,
                        'invite_code': invite_code
                    }
                })

            # POST - Save preferences
            elif request.method == 'POST':
                data = json_lib.loads(request.body)

                # Get or create preferences record
                prefs = db.query(DiscoveryNetworkPreferences).filter_by(user_id=int(user_id)).first()
                if not prefs:
                    prefs = DiscoveryNetworkPreferences(user_id=int(user_id))
                    db.add(prefs)

                # Update boolean fields
                if 'enable_lfg' in data:
                    prefs.enable_lfg = bool(data['enable_lfg'])
                if 'enable_games' in data:
                    prefs.enable_games = bool(data['enable_games'])
                if 'enable_creators' in data:
                    prefs.enable_creators = bool(data['enable_creators'])
                if 'enable_directory' in data:
                    prefs.enable_directory = bool(data['enable_directory'])

                # Update preference arrays (stored as JSON)
                if 'preferred_games' in data:
                    prefs.preferred_games = json_lib.dumps(data['preferred_games']) if data['preferred_games'] else None
                if 'preferred_tags' in data:
                    prefs.preferred_tags = json_lib.dumps(data['preferred_tags']) if data['preferred_tags'] else None
                if 'preferred_activities' in data:
                    prefs.preferred_activities = json_lib.dumps(data['preferred_activities']) if data['preferred_activities'] else None
                if 'preferred_skill_levels' in data:
                    prefs.preferred_skill_levels = json_lib.dumps(data['preferred_skill_levels']) if data['preferred_skill_levels'] else None
                if 'preferred_size' in data:
                    prefs.preferred_size = data['preferred_size'] or None

                # Update LFG preferences
                if 'lfg_filter_games' in data:
                    prefs.lfg_filter_games = bool(data['lfg_filter_games'])
                if 'lfg_filter_activities' in data:
                    prefs.lfg_filter_activities = bool(data['lfg_filter_activities'])
                if 'lfg_filter_skill_levels' in data:
                    prefs.lfg_filter_skill_levels = bool(data['lfg_filter_skill_levels'])
                if 'lfg_show_now' in data:
                    prefs.lfg_show_now = bool(data['lfg_show_now'])
                if 'lfg_hide_voice' in data:
                    prefs.lfg_hide_voice = bool(data['lfg_hide_voice'])

                # Update notification preferences
                if 'notify_lfg' in data:
                    prefs.notify_lfg = bool(data['notify_lfg'])
                if 'notify_servers' in data:
                    prefs.notify_servers = bool(data['notify_servers'])
                if 'notify_digest' in data:
                    prefs.notify_digest = bool(data['notify_digest'])

                # Update privacy preferences
                if 'privacy_show_profile' in data:
                    prefs.privacy_show_profile = bool(data['privacy_show_profile'])
                if 'privacy_show_server' in data:
                    prefs.privacy_show_server = bool(data['privacy_show_server'])
                if 'privacy_allow_dms' in data:
                    prefs.privacy_allow_dms = bool(data['privacy_allow_dms'])

                # Update timestamp
                prefs.updated_at = int(time.time())

                # ALSO UPDATE ALLOW_JOIN AND INVITE_CODE IN THE APPLICATION TABLE (SERVER SETTINGS)
                # These are server settings, not user preferences, so they need to update the application
                # ADMIN ONLY - only server admins can modify these settings
                if 'allow_join' in data or 'invite_code' in data:
                    # Check if user is admin
                    admin_guilds = request.session.get('discord_admin_guilds', [])
                    guild_id = request.GET.get('guild_id') or request.session.get('guild_id')
                    is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds) if guild_id else False

                    if not is_admin:
                        # Non-admins cannot modify server settings (allow_join, invite_code)
                        # Continue saving other preferences but ignore these fields
                        pass
                    else:
                        # Admin can update server settings
                        from .models import DiscoveryNetworkApplication

                        if guild_id:
                            # Find the server's application
                            application = db.query(DiscoveryNetworkApplication).filter_by(
                                guild_id=int(guild_id),
                                status='approved'
                            ).first()

                            if application:
                                if 'allow_join' in data:
                                    application.allow_join = bool(data['allow_join'])
                                if 'invite_code' in data:
                                    # Strip whitespace and set to None if empty
                                    invite_code_value = str(data['invite_code']).strip() if data['invite_code'] else None
                                    application.invite_code = invite_code_value if invite_code_value else None
                                application.updated_at = int(time.time())

                db.commit()

                return JsonResponse({
                    'success': True,
                    'message': 'Preferences saved successfully'
                })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@discord_required
@require_http_methods(["POST"])
def api_discovery_network_leave(request):
    """Leave the Discovery Network - keeps approval status so they can rejoin without reapplying. ADMIN ONLY."""
    try:
        from .db import get_db_session
        from .models import DiscoveryNetworkApplication
        import time

        user = request.session.get('discord_user', {})
        user_id = user.get('id')
        guild_id = request.GET.get('guild_id')  # Get from query params or session

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        if not guild_id:
            return JsonResponse({
                'success': False,
                'error': 'Guild ID required'
            }, status=400)

        # ADMIN CHECK - only admins can leave the network
        admin_guilds = request.session.get('discord_admin_guilds', [])
        is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)

        if not is_admin:
            return JsonResponse({
                'success': False,
                'error': 'Admin permission required to leave the Discovery Network'
            }, status=403)

        with get_db_session() as db:
            # Find the server's application
            application = db.query(DiscoveryNetworkApplication).filter_by(
                guild_id=int(guild_id),
                status='approved'
            ).first()

            if not application:
                return JsonResponse({
                    'success': False,
                    'error': 'No approved application found for this server'
                }, status=404)

            # Don't delete the application - just mark it as inactive
            # This way they keep their approved status and can rejoin anytime
            # We'll add a new field to track this
            # For now, we'll change status to 'left' (we can add this status)
            application.status = 'left'
            application.updated_at = int(time.time())

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Successfully left the Discovery Network. You can rejoin anytime.'
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@discord_required
@require_http_methods(["POST"])
def api_discovery_network_rejoin(request):
    """Rejoin the Discovery Network - restore approved status for servers who left within 90 days."""
    try:
        from .db import get_db_session
        from .models import DiscoveryNetworkApplication
        import time

        user = request.session.get('discord_user', {})
        user_id = user.get('id')
        guild_id = request.GET.get('guild_id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        if not guild_id:
            return JsonResponse({
                'success': False,
                'error': 'Guild ID required'
            }, status=400)

        with get_db_session() as db:
            # Find the server's application with 'left' status
            application = db.query(DiscoveryNetworkApplication).filter_by(
                guild_id=int(guild_id),
                status='left'
            ).first()

            if not application:
                return JsonResponse({
                    'success': False,
                    'error': 'No previous membership found. Please apply to join the network.'
                }, status=404)

            # Check if they left more than 90 days ago
            current_time = int(time.time())
            ninety_days_seconds = 90 * 24 * 60 * 60  # 90 days in seconds
            time_since_left = current_time - application.updated_at

            if time_since_left > ninety_days_seconds:
                # More than 90 days - they need to reapply
                return JsonResponse({
                    'success': False,
                    'error': 'reapply_required',
                    'message': 'It has been more than 90 days since you left the network. Please submit a new application.'
                }, status=400)

            # Restore to approved status (within 90 days)
            application.status = 'approved'
            application.updated_at = int(time.time())

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Welcome back to the Discovery Network!'
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_games_list(request):
    """
    GET /api/discovery/games-list - Get aggregated game list from Discovery Network.
    Aggregates games from announced_games and lfg_groups, showing counts and ratings.
    Query params: guild_id, search, genre, sort
    """
    try:
        from .db import get_db_session
        from .models import AnnouncedGame, LFGGroup, LFGGame, DiscoveryGameReview, Guild
        from sqlalchemy import func, case
        from collections import defaultdict

        guild_id = request.GET.get('guild_id')
        search_term = request.GET.get('search', '').strip().lower()
        genre_filter = request.GET.get('genre', '').strip().lower()
        sort_by = request.GET.get('sort', 'trending')  # trending, servers, recent, rating

        with get_db_session() as db:
            # Verify guild is in Discovery Network (approved application)
            from .models import DiscoveryNetworkApplication

            # Get all approved guilds (status='approved')
            approved_apps = db.query(DiscoveryNetworkApplication.guild_id).filter(
                DiscoveryNetworkApplication.status == 'approved'
            ).all()
            approved_guild_ids = [g[0] for g in approved_apps if g[0] is not None]

            # If checking specific guild, verify it's approved
            if guild_id:
                if int(guild_id) not in approved_guild_ids:
                    return JsonResponse({
                        'success': False,
                        'error': 'Guild is not a member of the Discovery Network. Please apply first!'
                    }, status=403)

            if not approved_guild_ids:
                return JsonResponse({
                    'success': True,
                    'games': []
                })

            # Aggregate game data from multiple sources
            games_data = defaultdict(lambda: {
                'name': '',
                'genre': None,
                'description': None,
                'release_date': None,
                'genres': None,
                'platforms': None,
                'server_count': 0,
                'server_guild_ids': set(),  # Track which servers announced this game
                'lfg_count': 0,
                'total_reviews': 0,
                'avg_rating': 0,
                'latest_timestamp': 0,
                'cover_url': None,
                'igdb_slug': None,
                'steam_id': None,
                'steam_url': None,
                'hypes': None,
                'shared_by_user_id': None,
                'shared_by_guild_id': None,
                'is_manual': False
            })

            # 1. Get games from announced_games (Found Games) - Fetch ALL instances to track guild IDs
            announced_games = db.query(
                AnnouncedGame.game_name,
                AnnouncedGame.guild_id,
                AnnouncedGame.genre,
                AnnouncedGame.description,
                AnnouncedGame.release_date,
                AnnouncedGame.genres,
                AnnouncedGame.platforms,
                AnnouncedGame.cover_url,
                AnnouncedGame.igdb_slug,
                AnnouncedGame.steam_id,
                AnnouncedGame.created_at
            ).filter(
                AnnouncedGame.guild_id.in_(approved_guild_ids)
            ).all()

            for game in announced_games:
                game_name_lower = game.game_name.lower()
                games_data[game_name_lower]['name'] = game.game_name  # Keep original casing
                games_data[game_name_lower]['genre'] = game.genre
                # Track which servers announced this game
                games_data[game_name_lower]['server_guild_ids'].add(game.guild_id)
                if game.created_at and game.created_at > games_data[game_name_lower]['latest_timestamp']:
                    games_data[game_name_lower]['latest_timestamp'] = game.created_at
                # Use first non-null values found
                if not games_data[game_name_lower]['cover_url'] and game.cover_url:
                    games_data[game_name_lower]['cover_url'] = game.cover_url
                if not games_data[game_name_lower]['igdb_slug'] and game.igdb_slug:
                    games_data[game_name_lower]['igdb_slug'] = game.igdb_slug
                if not games_data[game_name_lower]['steam_id'] and game.steam_id:
                    games_data[game_name_lower]['steam_id'] = game.steam_id
                if not games_data[game_name_lower]['description'] and game.description:
                    games_data[game_name_lower]['description'] = game.description
                if not games_data[game_name_lower]['release_date'] and game.release_date:
                    games_data[game_name_lower]['release_date'] = game.release_date
                if not games_data[game_name_lower]['genres'] and game.genres:
                    games_data[game_name_lower]['genres'] = game.genres
                if not games_data[game_name_lower]['platforms'] and game.platforms:
                    games_data[game_name_lower]['platforms'] = game.platforms

            # 2. Get games from found_games (has Steam URLs and rich IGDB data)
            # ONLY include games from public search configs (show_on_website=True)
            from .models import FoundGame, GameSearchConfig
            found_games = db.query(
                FoundGame.game_name,
                FoundGame.cover_url,
                FoundGame.igdb_slug,
                FoundGame.steam_url,
                FoundGame.release_date,
                FoundGame.summary,
                FoundGame.genres,
                FoundGame.platforms,
                FoundGame.hypes,
                FoundGame.rating,
                func.count(func.distinct(FoundGame.guild_id)).label('found_count')
            ).join(
                GameSearchConfig,
                FoundGame.search_config_id == GameSearchConfig.id
            ).filter(
                FoundGame.guild_id.in_(approved_guild_ids),
                GameSearchConfig.show_on_website == True  # ONLY public games
            ).group_by(
                FoundGame.game_name,
                FoundGame.cover_url,
                FoundGame.igdb_slug,
                FoundGame.steam_url,
                FoundGame.release_date,
                FoundGame.summary,
                FoundGame.genres,
                FoundGame.platforms,
                FoundGame.hypes,
                FoundGame.rating
            ).all()

            for game in found_games:
                game_name_lower = game.game_name.lower()
                if game_name_lower not in games_data:
                    games_data[game_name_lower]['name'] = game.game_name
                # Enrich with found_games data (prefer this over announced_games since it has Steam URLs)
                if not games_data[game_name_lower]['cover_url'] and game.cover_url:
                    games_data[game_name_lower]['cover_url'] = game.cover_url
                if not games_data[game_name_lower]['igdb_slug'] and game.igdb_slug:
                    games_data[game_name_lower]['igdb_slug'] = game.igdb_slug
                if game.steam_url:  # Steam URL from found_games
                    games_data[game_name_lower]['steam_url'] = game.steam_url
                if not games_data[game_name_lower]['release_date'] and game.release_date:
                    games_data[game_name_lower]['release_date'] = game.release_date
                if not games_data[game_name_lower]['description'] and game.summary:
                    games_data[game_name_lower]['description'] = game.summary
                if not games_data[game_name_lower]['genres'] and game.genres:
                    games_data[game_name_lower]['genres'] = game.genres
                if not games_data[game_name_lower]['platforms'] and game.platforms:
                    games_data[game_name_lower]['platforms'] = game.platforms
                if game.hypes:
                    games_data[game_name_lower]['hypes'] = game.hypes
                if game.rating and not games_data[game_name_lower]['avg_rating']:
                    games_data[game_name_lower]['avg_rating'] = game.rating

            # 3. Get active LFG count per game
            active_lfgs = db.query(
                LFGGame.game_name,
                LFGGame.cover_url,
                LFGGame.igdb_slug,
                func.count(func.distinct(LFGGroup.id)).label('lfg_count')
            ).join(
                LFGGroup, LFGGroup.game_id == LFGGame.id
            ).filter(
                LFGGame.guild_id.in_(approved_guild_ids),
                LFGGroup.is_active == True
            ).group_by(
                LFGGame.game_name,
                LFGGame.cover_url,
                LFGGame.igdb_slug
            ).all()

            for game in active_lfgs:
                if game.game_name:
                    game_name_lower = game.game_name.lower()
                    if game_name_lower not in games_data:
                        games_data[game_name_lower]['name'] = game.game_name
                    games_data[game_name_lower]['lfg_count'] = game.lfg_count
                    # Use LFG game cover if we don't have one yet
                    if not games_data[game_name_lower]['cover_url'] and game.cover_url:
                        games_data[game_name_lower]['cover_url'] = game.cover_url
                    if not games_data[game_name_lower]['igdb_slug'] and game.igdb_slug:
                        games_data[game_name_lower]['igdb_slug'] = game.igdb_slug

            # 3. Get review stats
            review_stats = db.query(
                func.lower(DiscoveryGameReview.game_name).label('game_name_lower'),
                func.avg(DiscoveryGameReview.rating).label('avg_rating'),
                func.count(DiscoveryGameReview.id).label('review_count')
            ).filter(
                DiscoveryGameReview.is_flagged == False
            ).group_by(
                func.lower(DiscoveryGameReview.game_name)
            ).all()

            for stat in review_stats:
                game_name_lower = stat.game_name_lower
                if game_name_lower in games_data:
                    games_data[game_name_lower]['avg_rating'] = float(stat.avg_rating) if stat.avg_rating else 0
                    games_data[game_name_lower]['total_reviews'] = stat.review_count

            # 4. Get ONE example manual share per game (for attribution)
            manual_shares = db.query(
                func.lower(AnnouncedGame.game_name).label('game_name_lower'),
                AnnouncedGame.shared_by_user_id,
                AnnouncedGame.guild_id,
                AnnouncedGame.is_manual
            ).filter(
                AnnouncedGame.is_manual == True,
                AnnouncedGame.shared_by_user_id.isnot(None),
                AnnouncedGame.guild_id.in_(approved_guild_ids)
            ).distinct(
                func.lower(AnnouncedGame.game_name)
            ).all()

            for share in manual_shares:
                game_name_lower = share.game_name_lower
                if game_name_lower in games_data:
                    games_data[game_name_lower]['shared_by_user_id'] = share.shared_by_user_id
                    games_data[game_name_lower]['shared_by_guild_id'] = share.guild_id
                    games_data[game_name_lower]['is_manual'] = True

            # Convert to list and apply filters
            games_list = []
            for game_key, data in games_data.items():
                # Apply search filter
                if search_term and search_term not in game_key:
                    continue

                # Apply genre filter
                if genre_filter and (not data['genre'] or data['genre'].lower() != genre_filter):
                    continue

                # Build IGDB URL
                igdb_url = None
                if data['igdb_slug']:
                    igdb_url = f"https://www.igdb.com/games/{data['igdb_slug']}"

                # Use steam_url from found_games if available, otherwise construct from steam_id
                steam_url = data['steam_url']  # Prefer full URL from found_games
                if not steam_url and data['steam_id']:
                    steam_url = f"https://store.steampowered.com/app/{data['steam_id']}"

                # Parse JSON fields
                import json
                genres_list = None
                platforms_list = None
                if data['genres']:
                    try:
                        genres_list = json.loads(data['genres']) if isinstance(data['genres'], str) else data['genres']
                    except:
                        pass
                if data['platforms']:
                    try:
                        platforms_list = json.loads(data['platforms']) if isinstance(data['platforms'], str) else data['platforms']
                    except:
                        pass

                # Format release date
                release_date_str = None
                if data['release_date']:
                    try:
                        from datetime import datetime
                        release_date_str = datetime.fromtimestamp(data['release_date']).strftime('%b %d, %Y')
                    except:
                        pass

                # Use description or fallback to summary from IGDB if available
                summary = data['description']

                # Get user and guild info for manual shares
                shared_by_user = None
                shared_by_server = None
                if data['is_manual'] and data['shared_by_user_id'] and data['shared_by_guild_id']:
                    # Get Discord user info via API
                    try:
                        # Get member from cache (no Discord API call!)
                        from .discord_resources import get_guild_member

                        member_data = get_guild_member(str(data["shared_by_guild_id"]), str(data["shared_by_user_id"]))
                        if member_data:
                            # Get display name from cached data
                            shared_by_user = member_data.get('display_name') or member_data.get('username', 'Unknown User')
                    except Exception as e:
                        logger.warning(f"Failed to fetch Discord user {data['shared_by_user_id']} from cache: {e}")

                    # Get guild name
                    sharing_guild = db.query(Guild).filter_by(guild_id=data['shared_by_guild_id']).first()
                    if sharing_guild:
                        shared_by_server = sharing_guild.guild_name

                # Get list of server names that announced this game
                server_names = []
                if data['server_guild_ids']:
                    guild_lookup = db.query(Guild.guild_id, Guild.guild_name).filter(
                        Guild.guild_id.in_(list(data['server_guild_ids']))
                    ).all()
                    server_names = [name for _, name in guild_lookup if name]

                games_list.append({
                    'id': game_key,  # Use lowercase name as ID
                    'name': data['name'],
                    'genre': data['genre'],
                    'summary': summary,
                    'release_date': release_date_str,
                    'genres': genres_list,
                    'platforms': platforms_list,
                    'server_count': len(data['server_guild_ids']),  # Use actual count from set
                    'server_names': server_names,  # List of server names that announced this game
                    'lfg_count': data['lfg_count'],
                    'rating': round(data['avg_rating'], 1) if data['avg_rating'] > 0 else None,
                    'review_count': data['total_reviews'],
                    'latest_timestamp': data['latest_timestamp'],
                    'cover_url': data['cover_url'],
                    'igdb_url': igdb_url,
                    'steam_url': steam_url,
                    'hypes': data['hypes'],
                    'is_manual': data['is_manual'],
                    'shared_by_user': shared_by_user,
                    'shared_by_server': shared_by_server
                })

            # Apply sorting
            if sort_by == 'servers':
                games_list.sort(key=lambda x: x['server_count'], reverse=True)
            elif sort_by == 'recent':
                games_list.sort(key=lambda x: x['latest_timestamp'], reverse=True)
            elif sort_by == 'rating':
                games_list.sort(key=lambda x: (x['rating'] or 0, x['review_count']), reverse=True)
            else:  # trending (default)
                # Trending = combination of server count, LFG count, and recency
                import time
                now = time.time()
                for game in games_list:
                    # Calculate trending score
                    recency_bonus = 1.0
                    if game['latest_timestamp'] > 0:
                        days_old = (now - game['latest_timestamp']) / 86400
                        recency_bonus = max(0.1, 1.0 - (days_old / 30))  # Decay over 30 days

                    game['trending_score'] = (
                        game['server_count'] * 10 +
                        game['lfg_count'] * 5 +
                        (game['rating'] or 0) * 3
                    ) * recency_bonus

                games_list.sort(key=lambda x: x['trending_score'], reverse=True)

            return JsonResponse({
                'success': True,
                'games': games_list
            })

    except Exception as e:
        import traceback
        import logging
        logger = logging.getLogger(__name__)

        # Log the full error for debugging
        logger.error(f"Error in api_discovery_games_list: {str(e)}")
        traceback.print_exc()

        # Return user-friendly error message
        return JsonResponse({
            'success': False,
            'error': 'Unable to load games at this time. Please try again later.'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_game_share_limit(request):
    """
    GET /api/discovery/game-share-limit - Check remaining game share limit for guild.
    Query params: guild_id
    """
    try:
        from .db import get_db_session
        from .models import Guild

        guild_id = request.GET.get('guild_id')
        if not guild_id:
            return JsonResponse({
                'success': False,
                'error': 'Guild ID is required'
            }, status=400)

        with get_db_session() as db:
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({
                    'success': False,
                    'error': 'Guild not found'
                }, status=404)

            # Check limit
            can_share, current_count, limit, reset_date = check_discovery_game_share_limit(db, guild_id, guild)

            if limit is None:
                # Unlimited
                return JsonResponse({
                    'success': True,
                    'unlimited': True,
                    'current': current_count,
                    'limit': None,
                    'remaining': None,
                    'reset_date': None
                })
            else:
                return JsonResponse({
                    'success': True,
                    'unlimited': False,
                    'current': current_count,
                    'limit': limit,
                    'remaining': max(0, limit - current_count),
                    'reset_date': reset_date,
                    'can_share': can_share
                })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_igdb_search(request):
    """
    GET /api/igdb/search - Search IGDB for games.
    Query params: query (search string)
    """
    try:
        from .utils.igdb import search_games
        import asyncio

        query = request.GET.get('query', '').strip()
        if not query or len(query) < 2:
            return JsonResponse({
                'success': False,
                'error': 'Query must be at least 2 characters'
            }, status=400)

        # Run async search in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            games = loop.run_until_complete(search_games(query, limit=10))
        finally:
            loop.close()

        # Convert to JSON-serializable format
        games_data = []
        for game in games:
            games_data.append({
                'id': game.id,
                'name': game.name,
                'slug': game.slug,
                'summary': game.summary,
                'cover_url': game.cover_url,
                'platforms': game.platforms,
                'release_year': game.release_year,
                'steam_id': game.steam_id
            })

        return JsonResponse({
            'success': True,
            'games': games_data
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': 'Failed to search IGDB. Please try again.'
        }, status=500)


@discord_required
@require_http_methods(["POST"])
def api_discovery_share_game(request):
    """
    POST /api/discovery/share-game - Manually share a game to Discovery Network.
    Now uses IGDB data instead of manual entry.
    Body: guild_id, igdb_id, igdb_slug, game_name, cover_url, summary, release_year, platforms, recommendation
    """
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import AnnouncedGame, Guild
        from sqlalchemy import func
        import time
        import html

        data = json_lib.loads(request.body)
        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        guild_id = data.get('guild_id')

        # IGDB data
        igdb_id = data.get('igdb_id')
        igdb_slug = data.get('igdb_slug', '').strip()
        game_name = data.get('game_name', '').strip()
        cover_url = data.get('cover_url', '').strip()
        summary = data.get('summary', '').strip()
        release_year = data.get('release_year')
        platforms = data.get('platforms', '[]')  # JSON string
        recommendation = data.get('recommendation', '').strip()
        steam_id = data.get('steam_id')  # Steam ID from IGDB

        # Validation
        if not guild_id or not game_name or not igdb_id:
            return JsonResponse({
                'success': False,
                'error': 'Guild ID, game name, and IGDB ID are required'
            }, status=400)

        if len(game_name) > 255:
            return JsonResponse({
                'success': False,
                'error': 'Game name must be 255 characters or less'
            }, status=400)

        if recommendation and len(recommendation) > 1000:
            return JsonResponse({
                'success': False,
                'error': 'Recommendation must be 1000 characters or less'
            }, status=400)

        # Sanitize inputs (prevent XSS)
        game_name = html.escape(game_name)
        recommendation = html.escape(recommendation) if recommendation else None

        with get_db_session() as db:
            # Verify guild exists and user has permission
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({
                    'success': False,
                    'error': 'Guild not found'
                }, status=404)

            # Check if guild is in Discovery Network (has approved application)
            from .models import DiscoveryNetworkApplication, DiscoveryNetworkPreferences
            network_app = db.query(DiscoveryNetworkApplication).filter(
                DiscoveryNetworkApplication.guild_id == int(guild_id),
                DiscoveryNetworkApplication.status == 'approved'
            ).first()

            if not network_app:
                return JsonResponse({
                    'success': False,
                    'error': 'Guild must be a member of the Discovery Network to share games'
                }, status=403)

            # Check if user is trying to share from a server that is NOT their main server (anti-abuse)
            user_prefs = db.query(DiscoveryNetworkPreferences).filter_by(user_id=int(user_id)).first()

            # If user has set a main server, they can ONLY share from that server
            if user_prefs and user_prefs.main_server_id:
                if user_prefs.main_server_id != int(guild_id):
                    return JsonResponse({
                        'success': False,
                        'error': 'You can only share games from your main server. This prevents multi-server promotion abuse. Change your main server in Profile Settings (30-day cooldown applies).'
                    }, status=403)

            # Check share limit
            can_share, current_count, limit, reset_date = check_discovery_game_share_limit(db, guild_id, guild)
            if not can_share:
                return JsonResponse({
                    'success': False,
                    'error': f'Monthly game sharing limit reached. You have shared {current_count}/{limit} games this month. Limit resets on {reset_date}. Upgrade to the Discovery Module or Complete Suite for unlimited sharing!',
                    'limit_reached': True,
                    'current_count': current_count,
                    'limit': limit,
                    'reset_date': reset_date
                }, status=429)

            # Check for duplicate - multiple checks needed:
            # 1. Check if THIS SERVER already has this game
            existing_in_server = db.query(AnnouncedGame).filter(
                AnnouncedGame.guild_id == int(guild_id)
            ).filter(
                (AnnouncedGame.igdb_id == igdb_id) |
                (func.lower(AnnouncedGame.game_name) == game_name.lower())
            ).first()

            if existing_in_server:
                # Determine if it was bot-discovered or manually shared
                source = "manually shared" if existing_in_server.is_manual else "automatically discovered by the bot"
                return JsonResponse({
                    'success': False,
                    'error': f'"{game_name}" was already {source} for your server',
                    'duplicate': True
                }, status=400)

            # 2. Check if THIS USER already shared this game from THIS SERVER (extra safety)
            user_already_shared = db.query(AnnouncedGame).filter(
                AnnouncedGame.guild_id == int(guild_id),
                AnnouncedGame.shared_by_user_id == int(user_id),
                AnnouncedGame.is_manual == True
            ).filter(
                (AnnouncedGame.igdb_id == igdb_id) |
                (func.lower(AnnouncedGame.game_name) == game_name.lower())
            ).first()

            if user_already_shared:
                return JsonResponse({
                    'success': False,
                    'error': f'You already shared "{game_name}" from this server',
                    'duplicate': True
                }, status=400)

            # Create the game entry with IGDB data
            current_time = int(time.time())
            new_game = AnnouncedGame(
                guild_id=int(guild_id),
                igdb_id=igdb_id,
                igdb_slug=igdb_slug,
                steam_id=steam_id,  # Steam ID from IGDB
                game_name=game_name,
                cover_url=cover_url or None,
                release_date=int(time.mktime(time.strptime(f"{release_year}-01-01", "%Y-%m-%d"))) if release_year else None,
                platforms=platforms,  # JSON string
                announced_at=current_time,  # Required field
                created_at=current_time,
                description=recommendation,  # User's recommendation goes in description
                is_manual=True,  # Flag to indicate manually shared
                shared_by_user_id=int(user_id)  # Track who shared it
            )

            db.add(new_game)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': f'Successfully shared "{game_name}" to the Discovery Network!',
                'game': {
                    'id': new_game.id,
                    'name': game_name,
                    'igdb_id': igdb_id,
                    'cover_url': cover_url
                }
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Never expose raw database errors to users
        return JsonResponse({
            'success': False,
            'error': 'An error occurred while sharing your game. Please try again or contact support if the issue persists.'
        }, status=500)


@discord_required
@require_http_methods(["GET"])
def api_discovery_user_main_server(request):
    """
    GET /api/discovery/user/main-server - Get user's main server settings.
    Returns main server ID, when it was set, and when it can be changed.
    """
    try:
        from .db import get_db_session
        from .models import DiscoveryNetworkPreferences, Guild
        import time

        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        with get_db_session() as db:
            # Get user preferences
            prefs = db.query(DiscoveryNetworkPreferences).filter_by(user_id=int(user_id)).first()

            if not prefs or not prefs.main_server_id:
                return JsonResponse({
                    'success': True,
                    'main_server': None,
                    'can_change': True,
                    'message': 'No main server set'
                })

            # Get guild info
            guild = db.query(Guild).filter_by(guild_id=prefs.main_server_id).first()

            # Auto-select next available server if main server no longer exists
            if not guild:
                # Main server was deleted - reset to None and allow immediate change
                prefs.main_server_id = None
                prefs.main_server_set_at = None
                prefs.main_server_can_change_at = None
                db.commit()

                return JsonResponse({
                    'success': True,
                    'main_server': None,
                    'can_change': True,
                    'message': 'Your main server was removed. Please select a new one.',
                    'auto_reset': True
                })

            # Check if user can change (30 days since last change)
            current_time = int(time.time())
            can_change = not prefs.main_server_can_change_at or current_time >= prefs.main_server_can_change_at

            days_remaining = 0
            if prefs.main_server_can_change_at and current_time < prefs.main_server_can_change_at:
                days_remaining = (prefs.main_server_can_change_at - current_time) // 86400

            return JsonResponse({
                'success': True,
                'main_server': {
                    'id': prefs.main_server_id,
                    'name': guild.guild_name,
                    'set_at': prefs.main_server_set_at,
                    'can_change_at': prefs.main_server_can_change_at
                },
                'can_change': can_change,
                'days_remaining': days_remaining
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': 'Failed to get main server settings'
        }, status=500)


@discord_required
@require_http_methods(["POST"])
def api_discovery_user_set_main_server(request):
    """
    POST /api/discovery/user/set-main-server - Set or change user's main server.
    Body: guild_id
    Enforces 30-day cooldown between changes.
    """
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import DiscoveryNetworkPreferences, Guild
        import time

        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        data = json_lib.loads(request.body)
        guild_id = data.get('guild_id')

        if not guild_id:
            return JsonResponse({
                'success': False,
                'error': 'Guild ID is required'
            }, status=400)

        with get_db_session() as db:
            # Verify guild exists
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({
                    'success': False,
                    'error': 'Guild not found'
                }, status=404)

            # Get or create user preferences
            prefs = db.query(DiscoveryNetworkPreferences).filter_by(user_id=int(user_id)).first()
            if not prefs:
                prefs = DiscoveryNetworkPreferences(user_id=int(user_id))
                db.add(prefs)

            current_time = int(time.time())

            # Check if user can change (30 days since last change)
            if prefs.main_server_can_change_at and current_time < prefs.main_server_can_change_at:
                days_remaining = (prefs.main_server_can_change_at - current_time) // 86400
                return JsonResponse({
                    'success': False,
                    'error': f'You can change your main server again in {days_remaining} days. This cooldown prevents abuse.',
                    'cooldown': True,
                    'days_remaining': days_remaining
                }, status=429)

            # Set the new main server
            prefs.main_server_id = int(guild_id)
            prefs.main_server_set_at = current_time
            # 30 days = 30 * 24 * 60 * 60 = 2592000 seconds
            prefs.main_server_can_change_at = current_time + 2592000
            prefs.updated_at = current_time

            db.commit()

            return JsonResponse({
                'success': True,
                'message': f'Main server set to "{guild.guild_name}". You can change it again in 30 days.',
                'main_server': {
                    'id': prefs.main_server_id,
                    'name': guild.guild_name,
                    'set_at': prefs.main_server_set_at,
                    'can_change_at': prefs.main_server_can_change_at
                }
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': 'Failed to set main server'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_discovery_creators_list(request):
    """
    GET /api/discovery/creators-list - Get featured creators from Discovery Network.
    TODO: This is a stub - Twitch/YouTube integration coming soon.
    """
    try:
        # For now, return empty list
        # TODO: Implement Twitch and YouTube discovery
        return JsonResponse({
            'success': True,
            'creators': [],
            'message': 'Creator discovery coming soon! Twitch and YouTube integration in progress.'
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_discovery_feature_creator(request):
    """
    POST /api/discovery/feature-creator - Feature a creator to Discovery Network.
    TODO: This is a stub - Twitch/YouTube integration coming soon.
    """
    try:
        return JsonResponse({
            'success': False,
            'error': 'Creator featuring coming soon! This feature requires Twitch/YouTube integration.'
        }, status=501)  # 501 Not Implemented
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@discord_required
@require_http_methods(["GET", "POST"])
def api_discovery_game_reviews(request, game_id):
    """
    GET/POST /api/discovery/games/<game_id>/reviews
    Get all reviews for a game or submit a new review.
    """
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import DiscoveryGameReview, Guild
        from sqlalchemy import func
        import time
        import html

        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        # Decode game_id (it's the lowercase game name)
        game_name = game_id.replace('_', ' ')

        if request.method == 'GET':
            # Get all reviews for this game
            with get_db_session() as db:
                reviews = db.query(DiscoveryGameReview).filter(
                    func.lower(DiscoveryGameReview.game_name) == game_name.lower(),
                    DiscoveryGameReview.is_flagged == False
                ).order_by(
                    DiscoveryGameReview.created_at.desc()
                ).all()

                reviews_data = []
                for review in reviews:
                    reviews_data.append({
                        'id': review.id,
                        'user_id': str(review.user_id),
                        'username': review.username,
                        'rating': review.rating,
                        'review_text': review.review_text,
                        'hours_played': review.hours_played,
                        'created_at': review.created_at,
                        'updated_at': review.updated_at
                    })

                # Calculate average rating
                avg_rating = db.query(func.avg(DiscoveryGameReview.rating)).filter(
                    func.lower(DiscoveryGameReview.game_name) == game_name.lower(),
                    DiscoveryGameReview.is_flagged == False
                ).scalar()

                return JsonResponse({
                    'success': True,
                    'reviews': reviews_data,
                    'average_rating': round(float(avg_rating), 1) if avg_rating else 0,
                    'total_reviews': len(reviews_data)
                })

        elif request.method == 'POST':
            # Submit a new review
            data = json_lib.loads(request.body)
            guild_id = data.get('guild_id')
            rating = data.get('rating')
            review_text = data.get('review_text', '').strip()
            hours_played = data.get('hours_played')

            # Validation
            if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
                return JsonResponse({
                    'success': False,
                    'error': 'Rating must be between 1 and 5 stars'
                }, status=400)

            if review_text and len(review_text) > 2000:
                return JsonResponse({
                    'success': False,
                    'error': 'Review text must be 2000 characters or less'
                }, status=400)

            # Sanitize inputs
            review_text = html.escape(review_text) if review_text else None

            with get_db_session() as db:
                # Get user's Discord username
                username = user.get('username', 'Unknown User')

                # Check if user already reviewed this game
                existing = db.query(DiscoveryGameReview).filter(
                    func.lower(DiscoveryGameReview.game_name) == game_name.lower(),
                    DiscoveryGameReview.user_id == int(user_id)
                ).first()

                if existing:
                    # Update existing review
                    existing.rating = rating
                    existing.review_text = review_text
                    existing.hours_played = hours_played
                    existing.updated_at = int(time.time())
                    db.commit()

                    return JsonResponse({
                        'success': True,
                        'message': 'Review updated successfully!',
                        'review': {
                            'id': existing.id,
                            'rating': rating,
                            'review_text': review_text,
                            'hours_played': hours_played
                        }
                    })
                else:
                    # Create new review
                    new_review = DiscoveryGameReview(
                        game_name=game_name,
                        user_id=int(user_id),
                        username=username,
                        guild_id=int(guild_id) if guild_id else None,
                        rating=rating,
                        review_text=review_text,
                        hours_played=hours_played,
                        created_at=int(time.time()),
                        updated_at=int(time.time())
                    )

                    db.add(new_review)
                    db.commit()

                    return JsonResponse({
                        'success': True,
                        'message': 'Review submitted successfully!',
                        'review': {
                            'id': new_review.id,
                            'rating': rating,
                            'review_text': review_text,
                            'hours_played': hours_played
                        }
                    })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@discord_required
@require_http_methods(["GET", "POST"])
def api_discovery_game_discussions(request, game_id):
    """
    GET/POST /api/discovery/games/<game_id>/discussions
    Get all discussions for a game or post a new comment.
    """
    try:
        import json as json_lib
        from .db import get_db_session
        from .models import DiscoveryGameDiscussion
        from sqlalchemy import func
        import time
        import html

        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        # Decode game_id
        game_name = game_id.replace('_', ' ')

        if request.method == 'GET':
            # Get all discussions for this game
            with get_db_session() as db:
                discussions = db.query(DiscoveryGameDiscussion).filter(
                    func.lower(DiscoveryGameDiscussion.game_name) == game_name.lower(),
                    DiscoveryGameDiscussion.is_deleted == False,
                    DiscoveryGameDiscussion.is_flagged == False
                ).order_by(
                    DiscoveryGameDiscussion.created_at.desc()
                ).all()

                discussions_data = []
                for disc in discussions:
                    discussions_data.append({
                        'id': disc.id,
                        'user_id': str(disc.user_id),
                        'username': disc.username,
                        'comment_text': disc.comment_text,
                        'parent_comment_id': disc.parent_comment_id,
                        'created_at': disc.created_at,
                        'updated_at': disc.updated_at,
                        'upvotes': disc.upvotes
                    })

                return JsonResponse({
                    'success': True,
                    'discussions': discussions_data,
                    'total_comments': len(discussions_data)
                })

        elif request.method == 'POST':
            # Post a new comment
            data = json_lib.loads(request.body)
            guild_id = data.get('guild_id')
            comment_text = data.get('comment_text', '').strip()
            parent_comment_id = data.get('parent_comment_id')

            # Validation
            if not comment_text:
                return JsonResponse({
                    'success': False,
                    'error': 'Comment text is required'
                }, status=400)

            if len(comment_text) > 2000:
                return JsonResponse({
                    'success': False,
                    'error': 'Comment must be 2000 characters or less'
                }, status=400)

            # Sanitize input
            comment_text = html.escape(comment_text)

            with get_db_session() as db:
                # Get user's Discord username
                username = user.get('username', 'Unknown User')

                # Create new comment
                new_comment = DiscoveryGameDiscussion(
                    game_name=game_name,
                    user_id=int(user_id),
                    username=username,
                    guild_id=int(guild_id) if guild_id else None,
                    comment_text=comment_text,
                    parent_comment_id=parent_comment_id,
                    created_at=int(time.time()),
                    updated_at=int(time.time())
                )

                db.add(new_comment)
                db.commit()

                return JsonResponse({
                    'success': True,
                    'message': 'Comment posted successfully!',
                    'comment': {
                        'id': new_comment.id,
                        'comment_text': comment_text,
                        'parent_comment_id': parent_comment_id,
                        'upvotes': 0
                    }
                })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@discord_required
@require_http_methods(["POST"])
def api_discovery_discussion_upvote(request, discussion_id):
    """
    POST /api/discovery/discussions/<discussion_id>/upvote
    Upvote a discussion comment.
    """
    try:
        from .db import get_db_session
        from .models import DiscoveryGameDiscussion

        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            return JsonResponse({
                'success': False,
                'error': 'Not authenticated'
            }, status=401)

        with get_db_session() as db:
            comment = db.query(DiscoveryGameDiscussion).filter_by(id=discussion_id).first()

            if not comment:
                return JsonResponse({
                    'success': False,
                    'error': 'Comment not found'
                }, status=404)

            # Increment upvote count
            comment.upvotes += 1
            db.commit()

            return JsonResponse({
                'success': True,
                'upvotes': comment.upvotes
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def api_discovery_network_admin_applications(request):
    """Get all applications for admin review (BOT OWNER ONLY)."""
    try:
        import os
        from .db import get_db_session
        from .models import DiscoveryNetworkApplication, DiscoveryNetworkBan, Guild

        user = request.session.get('discord_user', {})
        user_id = user.get('id')
        bot_owner_id = os.getenv('BOT_OWNER_ID')

        # Only bot owner can access this
        if str(user_id) != str(bot_owner_id):
            return JsonResponse({
                'success': False,
                'error': 'Unauthorized - Bot owner only'
            }, status=403)

        with get_db_session() as db:
            # Get all applications
            applications = db.query(DiscoveryNetworkApplication).order_by(
                DiscoveryNetworkApplication.applied_at.desc()
            ).all()

            # Get all bans
            bans = db.query(DiscoveryNetworkBan).all()

            # Format applications
            apps_data = []
            for app in applications:
                # Get guild info if guild_id exists
                guild_info = None
                if app.guild_id:
                    guild = db.query(Guild).filter_by(guild_id=app.guild_id).first()
                    if guild:
                        guild_info = {
                            'id': str(guild.guild_id),
                            'name': guild.guild_name or 'Unknown Server'
                        }

                apps_data.append({
                    'id': app.id,
                    'user_id': str(app.user_id),
                    'guild_id': str(app.guild_id) if app.guild_id else None,
                    'guild_info': guild_info,
                    'username': app.username,
                    'display_name': app.display_name,
                    'avatar_url': app.avatar_url,
                    'bio': app.bio,
                    'twitch_url': app.twitch_url,
                    'youtube_url': app.youtube_url,
                    'twitter_url': app.twitter_url,
                    'tiktok_url': app.tiktok_url,
                    'status': app.status,
                    'applied_at': app.applied_at,
                    'updated_at': app.updated_at,
                    'denial_reason': app.denial_reason,
                    'reviewed_by': str(app.reviewed_by) if app.reviewed_by else None
                })

            # Format bans
            bans_data = []
            for ban in bans:
                bans_data.append({
                    'id': ban.id,
                    'user_id': str(ban.user_id),
                    'reason': ban.reason,
                    'violation_type': ban.violation_type,
                    'banned_at': ban.banned_at,
                    'banned_by': str(ban.banned_by) if ban.banned_by else None,
                    'appeal_allowed': ban.appeal_allowed,
                    'appeal_submitted': ban.appeal_submitted
                })

            return JsonResponse({
                'success': True,
                'applications': apps_data,
                'bans': bans_data,
                'stats': {
                    'pending': len([a for a in applications if a.status == 'pending']),
                    'approved': len([a for a in applications if a.status == 'approved']),
                    'denied': len([a for a in applications if a.status == 'denied']),
                    'banned': len(bans)
                }
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def api_discovery_network_admin_approve(request, application_id):
    """Approve an application (BOT OWNER ONLY)."""
    try:
        import os
        import time
        from .db import get_db_session
        from .models import DiscoveryNetworkApplication

        user = request.session.get('discord_user', {})
        user_id = user.get('id')
        bot_owner_id = os.getenv('BOT_OWNER_ID')

        # Only bot owner can access this
        if str(user_id) != str(bot_owner_id):
            return JsonResponse({
                'success': False,
                'error': 'Unauthorized - Bot owner only'
            }, status=403)

        with get_db_session() as db:
            application = db.query(DiscoveryNetworkApplication).filter_by(id=application_id).first()

            if not application:
                return JsonResponse({
                    'success': False,
                    'error': 'Application not found'
                }, status=404)

            application.status = 'approved'
            application.reviewed_by = int(user_id)
            application.updated_at = int(time.time())

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Application approved'
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def api_discovery_network_admin_deny(request, application_id):
    """Deny an application (BOT OWNER ONLY)."""
    try:
        import os
        import time
        import json as json_lib
        from .db import get_db_session
        from .models import DiscoveryNetworkApplication

        user = request.session.get('discord_user', {})
        user_id = user.get('id')
        bot_owner_id = os.getenv('BOT_OWNER_ID')

        # Only bot owner can access this
        if str(user_id) != str(bot_owner_id):
            return JsonResponse({
                'success': False,
                'error': 'Unauthorized - Bot owner only'
            }, status=403)

        data = json_lib.loads(request.body)
        reason = data.get('reason', 'No reason provided')

        with get_db_session() as db:
            application = db.query(DiscoveryNetworkApplication).filter_by(id=application_id).first()

            if not application:
                return JsonResponse({
                    'success': False,
                    'error': 'Application not found'
                }, status=404)

            application.status = 'denied'
            application.denial_reason = reason
            application.reviewed_by = int(user_id)
            application.updated_at = int(time.time())

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Application denied'
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def api_discovery_network_admin_ban(request, application_id):
    """Ban a user from Discovery Network (BOT OWNER ONLY)."""
    try:
        import os
        import time
        import json as json_lib
        from .db import get_db_session
        from .models import DiscoveryNetworkApplication, DiscoveryNetworkBan

        user = request.session.get('discord_user', {})
        user_id = user.get('id')
        bot_owner_id = os.getenv('BOT_OWNER_ID')

        # Only bot owner can access this
        if str(user_id) != str(bot_owner_id):
            return JsonResponse({
                'success': False,
                'error': 'Unauthorized - Bot owner only'
            }, status=403)

        data = json_lib.loads(request.body)
        reason = data.get('reason', 'No reason provided')
        violation_type = data.get('violation_type', 'other')

        with get_db_session() as db:
            application = db.query(DiscoveryNetworkApplication).filter_by(id=application_id).first()

            if not application:
                return JsonResponse({
                    'success': False,
                    'error': 'Application not found'
                }, status=404)

            # Check if already banned
            existing_ban = db.query(DiscoveryNetworkBan).filter_by(user_id=application.user_id).first()
            if existing_ban:
                return JsonResponse({
                    'success': False,
                    'error': 'User is already banned'
                }, status=400)

            # Create ban
            ban = DiscoveryNetworkBan(
                user_id=application.user_id,
                reason=reason,
                violation_type=violation_type,
                banned_by=int(user_id),
                banned_at=int(time.time()),
                appeal_allowed=True,
                appeal_submitted=False
            )

            # Update application status
            application.status = 'denied'
            application.denial_reason = f'Banned: {reason}'
            application.reviewed_by = int(user_id)
            application.updated_at = int(time.time())

            db.add(ban)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'User banned from Discovery Network'
            })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@discord_required
def guild_found_games(request, guild_id):
    """GET /questlog/guild/<id>/found-games/ - View all games found in recent discovery checks."""
    from .module_utils import has_module_access, has_any_module_access
    import json as json_lib
    from datetime import datetime

    # Get guild from session - allow any guild member to view
    all_guilds = request.session.get('discord_all_guilds', [])
    admin_guilds = request.session.get('discord_admin_guilds', [])  # For sidebar navigation
    guild = next((g for g in all_guilds if str(g.get('id')) == str(guild_id)), None)

    if not guild:
        messages.error(request, "You are not a member of this server.")
        return redirect('questlog_dashboard')

    try:
        from .db import get_db_session
        from .models import Guild, FoundGame, GameSearchConfig

        with get_db_session() as db:
            # Get guild record for sidebar navigation
            guild_record = db.query(Guild).filter_by(guild_id=int(guild_id)).first()

            # Get filters from query params
            check_id = request.GET.get('check_id')  # Optional: filter to specific check
            search_id = request.GET.get('search_id')  # Optional: filter by search config
            mode_filters = request.GET.getlist('mode')  # Optional: filter by one or more game modes
            min_hype_param = request.GET.get('min_hype')
            min_hype = int(min_hype_param) if min_hype_param and min_hype_param.isdigit() else None

            # Get available search configs (only public ones shown on website)
            # Get ALL search configs for this guild (both public and private)
            available_searches = db.query(GameSearchConfig).filter(
                GameSearchConfig.guild_id == int(guild_id)
            ).all()

            # Query found games (ALL games, both public and private searches)
            query = db.query(FoundGame).filter(
                FoundGame.guild_id == int(guild_id)
            )

            if check_id:
                query = query.filter(FoundGame.check_id == check_id)
            if search_id:
                query = query.filter(FoundGame.search_config_id == int(search_id))

            # Pull a reasonable window for filtering and option building
            base_games_raw = query.order_by(FoundGame.found_at.desc()).limit(300).all()

            # Build available game mode options from the base set
            available_modes = set()
            for game in base_games_raw:
                game_modes = json_lib.loads(game.game_modes) if game.game_modes else []
                for mode in game_modes:
                    available_modes.add(mode)

            # Apply filters in Python (game_modes stored as JSON text)
            filtered_games = []
            for game in base_games_raw:
                game_modes = json_lib.loads(game.game_modes) if game.game_modes else []
                # Mode filter: require at least one selected mode to be present
                if mode_filters:
                    if not any(mode in game_modes for mode in mode_filters):
                        continue
                # Hype filter
                if min_hype is not None:
                    if game.hypes is None or game.hypes < min_hype:
                        continue
                filtered_games.append((game, game_modes))

            # Order already by found_at desc; trim to 100 for display
            filtered_games = filtered_games[:100]

            # Process games for template
            found_games = []
            for game, game_modes in filtered_games:
                genres = json_lib.loads(game.genres) if game.genres else []
                themes = json_lib.loads(game.themes) if game.themes else []
                platforms = json_lib.loads(game.platforms) if game.platforms else []

                # Format release date
                release_date_str = None
                if game.release_date:
                    release_dt = datetime.fromtimestamp(game.release_date)
                    release_date_str = release_dt.strftime('%B %d, %Y')

                # Format found date
                found_dt = datetime.fromtimestamp(game.found_at)
                found_date_str = found_dt.strftime('%B %d, %Y %I:%M %p')

                found_games.append({
                    'id': game.id,
                    'igdb_id': game.igdb_id,
                    'igdb_slug': game.igdb_slug,
                    'name': game.game_name,
                    'summary': game.summary[:300] + '...' if game.summary and len(game.summary) > 300 else game.summary,
                    'release_date': release_date_str,
                    'genres': genres,
                    'themes': themes,
                    'game_modes': game_modes,
                    'platforms': platforms,
                    'cover_url': game.cover_url,
                    'igdb_url': game.igdb_url,
                    'steam_url': game.steam_url,
                    'hypes': game.hypes,
                    'rating': round(game.rating, 1) if game.rating else None,
                    'found_at': found_date_str,
                    'check_id': game.check_id,
                })

            # Get stats
            total_count = len(found_games)
            with_steam = sum(1 for g in found_games if g['steam_url'])

            # Format search configs for dropdown
            search_configs = [
                {
                    'id': s.id,
                    'name': s.name,
                }
                for s in available_searches
            ]

            # Check if user is admin
            is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)

            # Check if guild has discovery module access
            has_discovery_module = has_module_access(guild_id, 'discovery')
            has_any_module = has_any_module_access(guild_id)

            # Use guild from session (already set at top of function)
            context = {
                'guild': guild,
                'guild_record': guild_record,  # Add for sidebar navigation
                'found_games': found_games,
                'total_count': total_count,
                'with_steam': with_steam,
                'check_id': check_id,
                'search_id': int(search_id) if search_id else None,
                'search_configs': search_configs,
                'available_modes': sorted(available_modes),
                'selected_modes': mode_filters,
                'selected_min_hype': min_hype if min_hype is not None else '',
                'has_discovery_module': has_discovery_module,
                'has_any_module': has_any_module,
                'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
                'is_admin': is_admin,
                'active_page': 'found_games',
            }

            return render(request, 'questlog/found_games.html', context)

    except Exception as e:
        # Check if user is admin
        is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)

        # Check if guild has discovery module access (for error case too)
        has_discovery_module = has_module_access(guild_id, 'discovery')
        has_any_module = has_any_module_access(guild_id)

        # Get guild_record for sidebar navigation
        guild_record = None
        try:
            with get_db_session() as db:
                guild_record = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
        except:
            pass

        # Use guild from session (already set at top of function)
        return render(request, 'questlog/found_games.html', {
            'guild': guild,
            'guild_record': guild_record,  # Add for sidebar navigation
            'error': str(e),
            'has_discovery_module': has_discovery_module,
            'has_any_module': has_any_module,
            'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
            'is_admin': is_admin,
            'active_page': 'found_games',
        })


@require_http_methods(["POST"])
@api_auth_required
def api_discovery_config_update(request, guild_id):
    """POST /api/guild/<id>/discovery/config/update/ - Update discovery config."""
    import json as json_lib

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
            if 'channel_enabled' in data:
                config.channel_enabled = bool(data['channel_enabled'])
            if 'forum_enabled' in data:
                config.forum_enabled = bool(data['forum_enabled'])
            if 'selfpromo_channel_id' in data:
                config.selfpromo_channel_id = int(data['selfpromo_channel_id']) if data['selfpromo_channel_id'] else None
            if 'selfpromo_quick_feature' in data:
                config.selfpromo_quick_feature = bool(data['selfpromo_quick_feature'])
            if 'feature_channel_id' in data:
                config.feature_channel_id = int(data['feature_channel_id']) if data['feature_channel_id'] else None
            if 'message_response_channel_id' in data:
                config.message_response_channel_id = int(data['message_response_channel_id']) if data['message_response_channel_id'] else None
            if 'reminder_schedule' in data:
                config.reminder_schedule = data['reminder_schedule']
            if 'intro_forum_channel_id' in data:
                config.intro_forum_channel_id = int(data['intro_forum_channel_id']) if data['intro_forum_channel_id'] else None
            if 'forum_feature_channel_id' in data:
                config.forum_feature_channel_id = int(data['forum_feature_channel_id']) if data['forum_feature_channel_id'] else None
            if 'test_channel_id' in data:
                config.test_channel_id = int(data['test_channel_id']) if data['test_channel_id'] else None
            if 'test_forum_id' in data:
                config.test_forum_id = int(data['test_forum_id']) if data['test_forum_id'] else None
            if 'cotw_enabled' in data:
                config.cotw_enabled = bool(data['cotw_enabled'])
            if 'cotw_channel_id' in data:
                config.cotw_channel_id = int(data['cotw_channel_id']) if data['cotw_channel_id'] else None
            if 'cotm_enabled' in data:
                config.cotm_enabled = bool(data['cotm_enabled'])
            if 'cotm_channel_id' in data:
                config.cotm_channel_id = int(data['cotm_channel_id']) if data['cotm_channel_id'] else None
            # Channel timing settings
            if 'channel_feature_interval_hours' in data:
                config.channel_feature_interval_hours = max(1, min(24, int(data['channel_feature_interval_hours'])))
            if 'channel_pool_entry_duration_hours' in data:
                config.channel_pool_entry_duration_hours = max(1, min(168, int(data['channel_pool_entry_duration_hours'])))
            if 'channel_entry_cooldown_hours' in data:
                config.channel_entry_cooldown_hours = max(1, min(168, int(data['channel_entry_cooldown_hours'])))
            if 'channel_feature_cooldown_hours' in data:
                config.channel_feature_cooldown_hours = max(0, min(168, int(data['channel_feature_cooldown_hours'])))

            # Forum timing settings
            if 'intro_scan_interval_hours' in data:
                config.intro_scan_interval_hours = max(1, min(24, int(data['intro_scan_interval_hours'])))
            if 'forum_resubmit_cooldown_days' in data:
                config.forum_resubmit_cooldown_days = max(1, min(365, int(data['forum_resubmit_cooldown_days'])))
            if 'forum_min_post_age_hours' in data:
                config.forum_min_post_age_hours = max(0, min(168, int(data['forum_min_post_age_hours'])))

            # Token costs (separate for channel and forum)
            if 'token_cost' in data:
                config.token_cost = max(0, int(data['token_cost']))
            if 'token_cost_forum' in data:
                config.token_cost_forum = max(0, int(data['token_cost_forum']))

            # Timing settings
            if 'feature_interval_hours' in data:
                config.feature_interval_hours = max(1, min(24, int(data['feature_interval_hours'])))
            if 'pool_entry_duration_hours' in data:
                config.pool_entry_duration_hours = max(1, min(168, int(data['pool_entry_duration_hours'])))
            if 'entry_cooldown_hours' in data:
                config.entry_cooldown_hours = max(0, min(168, int(data['entry_cooldown_hours'])))
            if 'feature_cooldown_hours' in data:
                config.feature_cooldown_hours = max(0, min(168, int(data['feature_cooldown_hours'])))

            # Messages and embeds
            if 'how_to_enter_response' in data:
                config.how_to_enter_response = data['how_to_enter_response'][:500]
            if 'post_response' in data:
                config.post_response = data['post_response'][:500]
            if 'feature_message' in data:
                config.feature_message = data['feature_message'][:500]
            if 'cooldown_message' in data:
                config.cooldown_message = data['cooldown_message'][:500]
            if 'use_embed' in data:
                config.use_embed = bool(data['use_embed'])
            if 'embed_color' in data:
                config.embed_color = int(data['embed_color'])

            # Other settings
            if 'require_tokens' in data:
                config.require_tokens = bool(data['require_tokens'])
            if 'require_tokens_forum' in data:
                config.require_tokens_forum = bool(data['require_tokens_forum'])
            if 'remove_after_feature' in data:
                config.remove_after_feature = bool(data['remove_after_feature'])

            config.updated_at = int(time.time())

            db.commit()
            return JsonResponse({'success': True})

    except Exception as e:
        logger.error(f"Error updating discovery config for guild {guild_id}: {e}", exc_info=True)
        return JsonResponse({'error': f'An internal error occurred: {str(e)}'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
                action_type=ActionType.FORCE_FEATURE,
                payload={
                    'triggered_by': triggered_by,
                },
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name,
                source='website'
            )

            return JsonResponse({'success': True, 'action_id': action_id, 'pool_count': entry_count})

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_discovery_clear_featured(request, guild_id):
    """POST /api/guild/<id>/discovery/clear/ - Clear the currently featured person."""
    try:
        from .db import get_db_session
        from .models import DiscoveryConfig
        from .actions import queue_clear_featured

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        with get_db_session() as db:
            config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                return JsonResponse({'error': 'Discovery is not configured'}, status=400)

            # Queue the action for the bot to process
            action_id = queue_clear_featured(
                guild_id=int(guild_id),
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name
            )

            return JsonResponse({
                'success': True,
                'action_id': action_id,
                'message': 'Clear action queued - check Discord in a few seconds'
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_discovery_test_channel_embed(request, guild_id):
    """POST /api/guild/<id>/discovery/test-channel-embed/ - Send test channel embed."""
    try:
        import json
        from .db import get_db_session
        from .models import DiscoveryConfig
        from .actions import queue_test_channel_embed

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        # Parse request body to get channel_id
        data = json.loads(request.body.decode('utf-8'))
        channel_id = data.get('channel_id')

        if not channel_id:
            return JsonResponse({'error': 'No channel selected. Please select a test channel first.'}, status=400)

        with get_db_session() as db:
            config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                return JsonResponse({'error': 'Discovery is not configured'}, status=400)

            # Queue the action for the bot to process with the selected channel
            action_id = queue_test_channel_embed(
                guild_id=int(guild_id),
                channel_id=int(channel_id),
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name
            )

            return JsonResponse({
                'success': True,
                'action_id': action_id,
                'message': 'Test channel embed queued - check Discord in a few seconds'
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_discovery_test_forum_embed(request, guild_id):
    """POST /api/guild/<id>/discovery/test-forum-embed/ - Send test forum embed."""
    try:
        import json
        from .db import get_db_session
        from .models import DiscoveryConfig
        from .actions import queue_test_forum_embed

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        # Parse request body to get channel_id
        data = json.loads(request.body.decode('utf-8'))
        channel_id = data.get('channel_id')

        if not channel_id:
            return JsonResponse({'error': 'No channel selected. Please select a test forum channel first.'}, status=400)

        with get_db_session() as db:
            config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                return JsonResponse({'error': 'Discovery is not configured'}, status=400)

            # Queue the action for the bot to process with the selected channel
            action_id = queue_test_forum_embed(
                guild_id=int(guild_id),
                channel_id=int(channel_id),
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name
            )

            return JsonResponse({
                'success': True,
                'action_id': action_id,
                'message': 'Test forum embed queued - check Discord and website in a few seconds'
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_game_discovery_config_update(request, guild_id):
    """POST /api/guild/<id>/discovery/game-config/update/ - Update game discovery config."""
    import json as json_lib

    try:
        data = json_lib.loads(request.body)
    except json_lib.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    try:
        from .db import get_db_session
        from .models import DiscoveryConfig

        with get_db_session() as db:
            config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                config = DiscoveryConfig(guild_id=int(guild_id))
                db.add(config)

            # Update game discovery settings
            if 'game_discovery_enabled' in data:
                config.game_discovery_enabled = bool(data['game_discovery_enabled'])

            if 'public_game_channel_id' in data:
                channel_id = data['public_game_channel_id']
                config.public_game_channel_id = int(channel_id) if channel_id else None

            if 'private_game_channel_id' in data:
                channel_id = data['private_game_channel_id']
                config.private_game_channel_id = int(channel_id) if channel_id else None

            if 'public_game_ping_role_id' in data:
                role_id = data['public_game_ping_role_id']
                config.public_game_ping_role_id = int(role_id) if role_id else None

            if 'private_game_ping_role_id' in data:
                role_id = data['private_game_ping_role_id']
                config.private_game_ping_role_id = int(role_id) if role_id else None

            if 'game_check_interval_hours' in data:
                config.game_check_interval_hours = int(data['game_check_interval_hours'])

            if 'game_days_ahead' in data:
                config.game_days_ahead = int(data['game_days_ahead'])

            if 'game_days_behind' in data:
                config.game_days_behind = int(data['game_days_behind'])

            if 'game_min_hype' in data:
                hype_value = data['game_min_hype']
                config.game_min_hype = int(hype_value) if hype_value else None

            if 'game_min_rating' in data:
                rating_value = data['game_min_rating']
                config.game_min_rating = float(rating_value) if rating_value else None

            # Update filters (stored as JSON)
            if 'game_genres' in data:
                genres = data['game_genres']
                config.game_genres = json_lib.dumps(genres) if genres else None

            if 'game_themes' in data:
                themes = data['game_themes']
                config.game_themes = json_lib.dumps(themes) if themes else None

            if 'game_modes' in data:
                modes = data['game_modes']
                config.game_modes = json_lib.dumps(modes) if modes else None

            if 'game_platforms' in data:
                platforms = data['game_platforms']
                config.game_platforms = json_lib.dumps(platforms) if platforms else None

            if 'game_tags' in data:
                tags = data['game_tags']
                config.game_tags = json_lib.dumps(tags) if tags else None

            db.commit()
            return JsonResponse({'success': True})

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_game_discovery_check(request, guild_id):
    """POST /api/guild/<id>/discovery/check-games/ - Manually trigger game discovery check."""
    try:
        from .db import get_db_session
        from .models import DiscoveryConfig, AnnouncedGame
        from .actions import queue_action, ActionType
        import time
        import os

        discord_user = request.session.get('discord_user', {})
        triggered_by = int(discord_user.get('id', 0))
        triggered_by_name = discord_user.get('global_name', discord_user.get('username'))

        with get_db_session() as db:
            config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            if not config or not config.game_discovery_enabled:
                return JsonResponse({'error': 'Game discovery is not enabled'}, status=400)

            if not config.public_game_channel_id and not config.private_game_channel_id:
                return JsonResponse({'error': 'No game discovery channels configured'}, status=400)

            # Check if IGDB is configured
            if not (os.getenv('IGDB_CLIENT_ID') and os.getenv('IGDB_CLIENT_SECRET')):
                return JsonResponse({
                    'error': 'IGDB is not configured. Please add IGDB_CLIENT_ID and TWITCH_CLIENT_SECRET to your .env file.'
                }, status=400)

            # Queue the action for the bot to process
            action_id = queue_action(
                guild_id=int(guild_id),
                action_type=ActionType.CHECK_GAMES,
                payload={
                    'triggered_by': triggered_by,
                },
                triggered_by=triggered_by,
                triggered_by_name=triggered_by_name,
                source='website'
            )

            return JsonResponse({
                'success': True,
                'action_id': action_id,
                'message': 'Game check queued using IGDB - results will appear in Discord shortly'
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_purge_announced_games(request, guild_id):
    """POST /api/guild/<id>/discovery/purge-announced-games/ - Clear all announced games for re-announcement."""
    try:
        from .db import get_db_session
        from .models import AnnouncedGame

        with get_db_session() as db:
            # Delete all announced games for this guild
            count = db.query(AnnouncedGame).filter_by(guild_id=int(guild_id)).delete()
            db.commit()

            return JsonResponse({
                'success': True,
                'count': count,
                'message': f'Purged {count} games from Discovery Network. These can now be re-announced.'
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_game_search_configs_list(request, guild_id):
    """GET /api/guild/<id>/discovery/searches/ - List all game search configurations."""
    try:
        from .db import get_db_session
        from .models import GameSearchConfig
        import json as json_lib

        with get_db_session() as db:
            searches = db.query(GameSearchConfig).filter_by(guild_id=int(guild_id)).order_by(GameSearchConfig.name).all()

            result = []
            for search in searches:
                result.append({
                    'id': search.id,
                    'name': search.name,
                    'enabled': search.enabled,
                    'genres': json_lib.loads(search.genres) if search.genres else [],
                    'themes': json_lib.loads(search.themes) if search.themes else [],
                    'game_modes': json_lib.loads(search.game_modes) if search.game_modes else [],
                    'platforms': json_lib.loads(search.platforms) if search.platforms else [],
                    'min_hype': search.min_hype,
                    'min_rating': search.min_rating,
                    'days_ahead': search.days_ahead,
                    'show_on_website': search.show_on_website,
                    'auto_join_role_id': search.auto_join_role_id,
                    'created_at': search.created_at,
                    'updated_at': search.updated_at,
                })

            return JsonResponse({'success': True, 'searches': result})

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_game_search_config_create(request, guild_id):
    """POST /api/guild/<id>/discovery/searches/ - Create a new game search configuration."""
    try:
        from .db import get_db_session
        from .models import GameSearchConfig, Guild as GuildModel, SubscriptionTier
        import json as json_lib
        import time

        data = json_lib.loads(request.body)

        # Check tier limits for search configurations
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Determine search limit based on tier
            # Check if guild has Discovery Module (grants unlimited searches)
            from .module_utils import has_module_access

            if has_module_access(guild_id, 'discovery') or guild_record.is_vip or guild_record.subscription_tier == SubscriptionTier.PREMIUM.value:
                max_searches = None  # Unlimited
            elif guild_record.subscription_tier == SubscriptionTier.PRO.value:
                max_searches = 5
            else:  # Free tier
                max_searches = 3

            # Count existing searches
            if max_searches is not None:
                existing_count = db.query(GameSearchConfig).filter_by(
                    guild_id=int(guild_id)
                ).count()

                if existing_count >= max_searches:
                    tier_name = 'Pro' if max_searches == 5 else 'Free'
                    return JsonResponse({
                        'error': f'{tier_name} tier limited to {max_searches} game discovery searches. You have {existing_count}/{max_searches}. Delete a search or upgrade to Premium for unlimited searches.',
                        'limit_exceeded': True,
                        'current_count': existing_count,
                        'max_allowed': max_searches
                    }, status=403)

        with get_db_session() as db:
            # Create new search config
            search = GameSearchConfig(
                guild_id=int(guild_id),
                name=data.get('name', 'New Search'),
                enabled=data.get('enabled', True),
                genres=json_lib.dumps(data.get('genres', [])) if data.get('genres') else None,
                themes=json_lib.dumps(data.get('themes', [])) if data.get('themes') else None,
                game_modes=json_lib.dumps(data.get('game_modes', [])) if data.get('game_modes') else None,
                platforms=json_lib.dumps(data.get('platforms', [])) if data.get('platforms') else None,
                min_hype=data.get('min_hype'),
                min_rating=data.get('min_rating'),
                days_ahead=data.get('days_ahead', 30),
                show_on_website=data.get('show_on_website', True),
                auto_join_role_id=data.get('auto_join_role_id'),
                created_at=int(time.time()),
                updated_at=int(time.time())
            )

            db.add(search)
            db.commit()

            return JsonResponse({
                'success': True,
                'search_id': search.id,
                'message': f"Search '{search.name}' created successfully"
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["PUT", "POST"])
@api_auth_required
def api_game_search_config_update(request, guild_id, search_id):
    """PUT /api/guild/<id>/discovery/searches/<search_id>/ - Update a game search configuration."""
    try:
        from .db import get_db_session
        from .models import GameSearchConfig
        import json as json_lib
        import time

        data = json_lib.loads(request.body)

        with get_db_session() as db:
            search = db.query(GameSearchConfig).filter_by(
                id=int(search_id),
                guild_id=int(guild_id)
            ).first()

            if not search:
                return JsonResponse({'error': 'Search configuration not found'}, status=404)

            # Update fields
            if 'name' in data:
                search.name = data['name']
            if 'enabled' in data:
                search.enabled = data['enabled']
            if 'genres' in data:
                search.genres = json_lib.dumps(data['genres']) if data['genres'] else None
            if 'themes' in data:
                search.themes = json_lib.dumps(data['themes']) if data['themes'] else None
            if 'game_modes' in data:
                search.game_modes = json_lib.dumps(data['game_modes']) if data['game_modes'] else None
            if 'platforms' in data:
                search.platforms = json_lib.dumps(data['platforms']) if data['platforms'] else None
            if 'min_hype' in data:
                search.min_hype = data['min_hype']
            if 'min_rating' in data:
                search.min_rating = data['min_rating']
            if 'days_ahead' in data:
                search.days_ahead = data['days_ahead']
            if 'show_on_website' in data:
                search.show_on_website = data['show_on_website']
            if 'auto_join_role_id' in data:
                search.auto_join_role_id = data['auto_join_role_id']

            search.updated_at = int(time.time())
            db.commit()

            return JsonResponse({
                'success': True,
                'message': f"Search '{search.name}' updated successfully"
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["DELETE", "POST"])
@api_auth_required
def api_game_search_config_delete(request, guild_id, search_id):
    """DELETE /api/guild/<id>/discovery/searches/<search_id>/ - Delete a game search configuration."""
    try:
        from .db import get_db_session
        from .models import GameSearchConfig

        with get_db_session() as db:
            search = db.query(GameSearchConfig).filter_by(
                id=int(search_id),
                guild_id=int(guild_id)
            ).first()

            if not search:
                return JsonResponse({'error': 'Search configuration not found'}, status=404)

            search_name = search.name
            db.delete(search)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': f"Search '{search_name}' deleted successfully"
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_action_status(request, guild_id, action_id):
    """GET /api/guild/<id>/action/<action_id>/status/ - Get status of a queued action."""
    try:
        from .db import get_db_session
        from .models import PendingAction
        import json

        with get_db_session() as db:
            action = db.query(PendingAction).filter_by(
                id=int(action_id),
                guild_id=int(guild_id)
            ).first()

            if not action:
                return JsonResponse({'error': 'Action not found'}, status=404)

            # Parse result JSON if it exists
            result_data = None
            if action.result:
                try:
                    result_data = json.loads(action.result)
                except:
                    result_data = None

            return JsonResponse({
                'id': action.id,
                'status': action.status.value,
                'created_at': action.created_at,  # Already a Unix timestamp
                'completed_at': action.completed_at,  # Already a Unix timestamp
                'error_message': action.error_message,
                'result': result_data
            })

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# LFG (Looking For Group) Dashboard

@discord_required
def guild_lfg(request, guild_id):
    """LFG dashboard."""
    from .module_utils import has_module_access, has_any_module_access
    import logging
    logger = logging.getLogger(__name__)

    user_guilds = request.session.get('discord_admin_guilds', [])
    logger.info(f"LFG: Looking for guild_id={guild_id}")
    logger.info(f"LFG: discord_admin_guilds has {len(user_guilds)} guilds")
    if user_guilds:
        logger.info(f"LFG: Guild IDs in session: {[str(g.get('id')) for g in user_guilds]}")

    guild = next((g for g in user_guilds if str(g.get('id')) == str(guild_id)), None)

    if not guild:
        logger.warning(f"LFG: Guild {guild_id} not found in session, redirecting to dashboard")
        return redirect('questlog_dashboard')

    # Check admin permission
    permissions = int(guild.get('permissions', 0))
    is_admin = (permissions & 0x8) == 0x8 or (permissions & 0x20) == 0x20

    if not is_admin:
        messages.error(request, 'You need Admin or Manage Server permission.')
        return redirect('questlog_dashboard')

    try:
        from .db import get_db_session
        from .models import Guild, LFGGame, LFGConfig

        with get_db_session() as db:
            guild_db = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild_db.is_premium() if guild_db else False
            is_pro_plus = guild_db and (guild_db.subscription_tier in ['pro', 'premium'] or guild_db.is_vip)

            games = db.query(LFGGame).filter_by(guild_id=int(guild_id)).all()

            # Get LFG Browser notification config
            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if not lfg_config and is_pro_plus:
                # Create default config for Pro+ servers
                lfg_config = LFGConfig(guild_id=int(guild_id))
                db.add(lfg_config)
                db.commit()
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
                    'custom_options': json.loads(game.custom_options) if game.custom_options else None,
                    'require_rank': game.require_rank,
                    'rank_label': game.rank_label,
                    'enabled': game.enabled,
                    'current_player_count': game.current_player_count or 0,  # Live player count
                })

        # Get channels and roles from Discord API using bot token
        import os
        bot_token = os.getenv('DISCORD_BOT_TOKEN')

        channels = []
        roles = []

        if bot_token and bot_token != 'your_bot_token_here':
            try:
                # Fetch guild channels from cache (no Discord API call!)
                from .discord_resources import get_guild_channels, get_guild_roles

                all_channels = get_guild_channels(str(guild_id))
                # Filter for text channels (type 0) and forum channels (type 15)
                channels = [
                    {'id': ch['id'], 'name': ch['name']}
                    for ch in all_channels
                    if ch.get('type') in [0, 15]  # Text and Forum channels
                ]
                channels.sort(key=lambda x: x['name'])
                logger.info(f"Found {len(channels)} text/forum channels from cache")

                # Fetch guild roles from cache (no Discord API call!)
                all_roles = get_guild_roles(str(guild_id))
                # Sort by position
                roles = [
                    {'id': r['id'], 'name': r['name'], 'position': r.get('position', 0)}
                    for r in all_roles
                ]
                roles.sort(key=lambda x: x['position'], reverse=True)
                logger.info(f"Found {len(roles)} roles from cache")

            except Exception as e:
                logger.error(f"Error fetching Discord channels/roles from cache: {e}")
        else:
            logger.warning("DISCORD_BOT_TOKEN not configured")

        # Check if user is admin or LFG Manager (for audit log access)
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')
        has_lfg_manager_role = check_lfg_manager_role(guild_id, user_id) if user_id else False
        is_admin_or_manager = is_admin or has_lfg_manager_role

        # Check if guild has LFG module access
        has_lfg_module = has_module_access(guild_id, 'lfg')
        has_engagement_module = has_module_access(guild_id, 'engagement')
        has_any_module = has_any_module_access(guild_id)

        return render(request, 'questlog/lfg.html', {
            'guild': guild,
            'guild_record': guild_db,
            'games': games_data,
            'channels': channels,
            'roles': roles,
            'is_premium': is_premium,
            'is_pro_plus': is_pro_plus,
            'lfg_config': lfg_config,
            'is_admin': True,
            'is_admin_or_manager': is_admin_or_manager,
            'has_lfg_module': has_lfg_module,
            'has_engagement_module': has_engagement_module,
            'has_any_module': has_any_module,
            'admin_guilds': user_guilds,
            'active_page': 'lfg',
            'total_lfg_games': len(games_data),
        })

    except Exception as e:
        messages.error(request, f'Error loading LFG: {e}')
        return redirect('guild_dashboard', guild_id=guild_id)


def guild_lfg_browser(request, guild_id):
    """
    LFG Browser - Browse and create LFG groups (All tiers).

    This view renders the LFG Browser interface where users can:
    - Browse active LFG groups
    - Create new groups
    - Join/leave groups
    - Manage groups (if they have permissions)

    Permission Levels:
    - Regular users: Can create/join groups, manage their own groups
    - LFG Managers: Can edit/delete ANY group (requires "LFG Manager" Discord role with CREATE_EVENTS + MANAGE_EVENTS permissions)
    - Admins: Full management access to all groups
    """
    from .module_utils import has_module_access, has_any_module_access
    import logging
    logger = logging.getLogger(__name__)

    # Get user's guilds and authentication info from Discord OAuth session
    admin_guilds = request.session.get('discord_admin_guilds', [])
    all_guilds = request.session.get('discord_all_guilds', [])
    user_id = request.session.get('discord_user', {}).get('id')
    discord_user = request.session.get('discord_user', {})

    # Verify user is a member of this guild
    guild = next((g for g in all_guilds if str(g['id']) == str(guild_id)), None)
    is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)

    if not guild:
        messages.error(request, "You are not a member of this server.")
        return redirect('questlog_dashboard')

    # Check if user has "LFG Manager" role (requires both CREATE_EVENTS and MANAGE_EVENTS permissions)
    has_lfg_manager_role = check_lfg_manager_role(guild_id, user_id)

    # Users can manage ANY group if they're admin OR have the LFG Manager role
    # Otherwise, they can only manage their own groups (enforced in individual endpoints)
    can_manage_groups = is_admin or has_lfg_manager_role

    try:
        from .db import get_db_session
        from .models import Guild, LFGGame

        with get_db_session() as db:
            guild_db = db.query(Guild).filter_by(guild_id=int(guild_id)).first()

            if not guild_db:
                messages.error(request, 'Server not found in database.')
                return redirect('questlog_dashboard')

            # Get all enabled games for this guild
            games = db.query(LFGGame).filter_by(
                guild_id=int(guild_id),
                enabled=True
            ).all()

            games_data = []
            for game in games:
                # Parse custom_options safely - ensure it's always an array
                custom_options = None
                if game.custom_options:
                    try:
                        parsed = json.loads(game.custom_options)
                        # Ensure custom_options is a list and each option has a choices array
                        if isinstance(parsed, list):
                            custom_options = []
                            for opt in parsed:
                                if isinstance(opt, dict) and 'name' in opt:
                                    # Build option object
                                    option_obj = {'name': opt['name']}

                                    # Add depends_on if present
                                    if 'depends_on' in opt:
                                        option_obj['depends_on'] = opt['depends_on']

                                    # Add choices (can be array or object for conditional dropdowns)
                                    choices = opt.get('choices', [])
                                    # Don't validate type for conditional dropdowns - can be object or array
                                    option_obj['choices'] = choices

                                    custom_options.append(option_obj)
                    except (json.JSONDecodeError, TypeError, KeyError) as e:
                        logger.warning(f"Failed to parse custom_options for game {game.id}: {e}")
                        custom_options = None

                games_data.append({
                    'id': game.id,
                    'game_name': game.game_name,
                    'game_short': game.game_short,
                    'game_emoji': game.game_emoji,
                    'cover_url': game.cover_url,
                    'max_group_size': game.max_group_size,
                    'require_rank': game.require_rank,
                    'rank_label': game.rank_label,
                    'rank_min': game.rank_min,
                    'rank_max': game.rank_max,
                    'custom_options': custom_options,
                    'current_player_count': game.current_player_count or 0,
                })

        # Pass games_data directly to template - will use json_script tag for safe JSON injection prevention
        # Check if guild has LFG module access
        has_lfg_module = has_module_access(guild_id, 'lfg')
        has_engagement_module = has_module_access(guild_id, 'engagement')
        has_any_module = has_any_module_access(guild_id)

        return render(request, 'questlog/lfg_browser.html', {
            'guild': guild,
            'guild_record': guild_db,
            'games': games_data,
            'games_data': games_data,  # Pass for json_script tag
            'discord_user': discord_user,
            'is_admin': is_admin,
            'can_manage_groups': can_manage_groups,  # Pass can_manage_groups for audit logs button
            'has_lfg_module': has_lfg_module,
            'has_engagement_module': has_engagement_module,
            'has_any_module': has_any_module,
            'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
            'active_page': 'lfg_browser',
        })

    except Exception as e:
        logger.error(f"Error loading LFG browser: {e}", exc_info=True)
        messages.error(request, f'Error loading LFG browser: {e}')
        return redirect('guild_dashboard', guild_id=guild_id)


def guild_attendance(request, guild_id):
    """LFG Attendance tracking dashboard - Admin/Raid Leader only (Premium feature)."""
    import logging
    logger = logging.getLogger(__name__)

    # Get user's guilds from session
    admin_guilds = request.session.get('discord_admin_guilds', [])
    all_guilds = request.session.get('discord_all_guilds', [])
    user_id = request.session.get('discord_user', {}).get('id')

    # Check if user is admin OR member of this guild
    is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)
    guild = next((g for g in all_guilds if str(g['id']) == str(guild_id)), None)

    if not guild:
        messages.error(request, "You are not a member of this server.")
        return redirect('questlog_dashboard')

    # Check permissions
    permissions = int(guild.get('permissions', 0))
    has_create_events = (permissions & 0x100000000) == 0x100000000  # CREATE_EVENTS permission
    has_manage_events = (permissions & 0x200000000) == 0x200000000  # MANAGE_EVENTS permission
    has_manage_messages = (permissions & 0x2000) == 0x2000  # MANAGE_MESSAGES permission (moderator)

    # User has permission
    is_member = True

    try:
        from .db import get_db_session
        from .models import Guild, LFGConfig, LFGGroup, LFGMember, LFGAttendance, LFGMemberStats

        with get_db_session() as db:
            guild_db = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            is_premium = guild_db.is_premium() if guild_db else False

            # Check if guild has premium (required for attendance tracking)
            if not is_premium:
                messages.error(request, 'Attendance tracking requires Premium or VIP subscription.')
                return redirect('guild_dashboard', guild_id=guild_id)

            # Get or create LFG config
            config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if not config:
                config = LFGConfig(guild_id=int(guild_id))
                db.add(config)
                db.flush()

            # Check for fixed "Raid Leader" role via Discord API
            has_raid_leader_role = False
            if user_id:
                try:
                    # Get guild roles from cache (no Discord API call!)
                    from .discord_resources import get_guild_roles, get_guild_member

                    roles = get_guild_roles(str(guild_id))

                    raid_leader_role_id = None
                    for role in roles:
                        if role.get('name') == 'Raid Leader':
                            raid_leader_role_id = role.get('id')
                            break

                    # Check if user has the Raid Leader role (from cache, no API call!)
                    if raid_leader_role_id:
                        member_data = get_guild_member(str(guild_id), str(user_id))
                        if member_data:
                            member_roles = member_data.get('roles', [])
                            if str(raid_leader_role_id) in member_roles:
                                has_raid_leader_role = True
                except Exception as e:
                    logger.error(f"Error checking Raid Leader role from cache: {e}")

            # Permission logic: Admin OR Moderator OR (Raid Leader + Create Events + Manage Events)
            has_raid_leader_full_perms = has_raid_leader_role and has_create_events and has_manage_events

            # Deny access if not authorized
            if not (is_admin or has_manage_messages or has_raid_leader_full_perms):
                messages.error(request, "You need admin, moderator, or Raid Leader role (with Create Events and Manage Events permissions) to access attendance tracking.")
                return redirect('guild_dashboard', guild_id=guild_id)

            # Determine if user can manage attendance (for UI)
            can_manage_attendance = is_admin or has_manage_messages or has_raid_leader_full_perms

            # Fetch member display names from cache (no Discord API call!)
            from .discord_resources import get_guild_members
            import requests
            member_names_cache = {}

            try:
                guild_members = get_guild_members(str(guild_id))
                for m in guild_members:
                    user_id = int(m['id'])
                    display_name = m.get('display_name') or m.get('username', 'Unknown')
                    member_names_cache[user_id] = display_name
                logger.info(f"Loaded {len(member_names_cache)} member names from cache")
            except Exception as e:
                logger.error(f"Error fetching guild members from cache: {e}")

            # Get recent groups (last 30 days) with attendance tracking
            import time
            thirty_days_ago = int(time.time()) - (30 * 24 * 3600)

            # Only show groups that have attendance records (meaning attendance was ON when created)
            groups = db.query(LFGGroup).filter(
                LFGGroup.guild_id == int(guild_id),
                LFGGroup.created_at >= thirty_days_ago,
                LFGGroup.id.in_(
                    db.query(LFGAttendance.group_id).distinct()
                )
            ).order_by(LFGGroup.scheduled_time.desc()).limit(50).all()

            groups_data = []
            for group in groups:
                # Get game info
                from .models import LFGGame
                game = db.query(LFGGame).filter_by(id=group.game_id).first()
                game_name = game.game_name if game else "Unknown Game"

                # Get attendance records
                attendance_records = db.query(LFGAttendance).filter_by(group_id=group.id).all()
                members = db.query(LFGMember).filter_by(group_id=group.id).all()

                # Create a map of user_id -> member for quick lookup
                members_map = {m.user_id: m for m in members}

                attendance_data = []
                for att in attendance_records:
                    # Try Discord API cache first, then GuildMember table, then fallback to user ID
                    display_name = member_names_cache.get(att.user_id)

                    if not display_name:
                        # Check GuildMember table for synced Discord member data
                        from .models import GuildMember
                        guild_member = db.query(GuildMember).filter_by(
                            guild_id=int(guild_id),
                            user_id=att.user_id
                        ).first()
                        display_name = guild_member.display_name if guild_member else f"User {att.user_id}"

                    # Get member stats to check blacklist status
                    member_stats = db.query(LFGMemberStats).filter_by(
                        guild_id=int(guild_id),
                        user_id=att.user_id
                    ).first()

                    # Get member's class/role selections
                    member = members_map.get(att.user_id)
                    selections = {}
                    if member and member.selections:
                        import json
                        try:
                            selections = json.loads(member.selections)
                        except:
                            selections = {}
                    elif not member:
                        # Fallback: If no member record for THIS group (manually added attendance),
                        # try to find their most recent selections from ANY other group
                        import json
                        recent_member = db.query(LFGMember).filter_by(user_id=att.user_id).order_by(LFGMember.joined_at.desc()).first()
                        if recent_member and recent_member.selections:
                            try:
                                selections = json.loads(recent_member.selections)
                            except:
                                selections = {}

                    attendance_data.append({
                        'user_id': att.user_id,
                        'display_name': display_name,
                        'status': att.status.value if att.status else 'pending',
                        'confirmed_at': att.confirmed_at,
                        'showed_at': att.showed_at,
                        'is_blacklisted': member_stats.is_blacklisted if member_stats else False,
                        'selections': selections,  # Class/role selections
                    })

                groups_data.append({
                    'id': group.id,
                    'thread_name': group.thread_name,
                    'game_name': game_name,
                    'creator_name': group.creator_name,
                    'scheduled_time': group.scheduled_time,
                    'is_active': group.is_active,
                    'member_count': len(attendance_data),
                    'attendance': attendance_data,
                })

            # Get warning threshold
            warn_threshold = config.warn_at_reliability

            # Get top reliable members (above the at-risk range)
            top_members = db.query(LFGMemberStats).filter(
                LFGMemberStats.guild_id == int(guild_id),
                LFGMemberStats.total_signups >= 3,  # Must have attended at least 3 events
                LFGMemberStats.reliability_score >= warn_threshold + 15,  # Well above warning
                LFGMemberStats.is_blacklisted == False
            ).order_by(LFGMemberStats.reliability_score.desc()).limit(10).all()

            # Get members nearing warning threshold (within 15% above warning)
            at_risk_members = db.query(LFGMemberStats).filter(
                LFGMemberStats.guild_id == int(guild_id),
                LFGMemberStats.total_signups >= 3,
                LFGMemberStats.reliability_score >= warn_threshold,
                LFGMemberStats.reliability_score < warn_threshold + 15,
                LFGMemberStats.is_blacklisted == False
            ).order_by(LFGMemberStats.reliability_score.asc()).limit(10).all()

            # Get members below warning threshold (need attention)
            warned_members = db.query(LFGMemberStats).filter(
                LFGMemberStats.guild_id == int(guild_id),
                LFGMemberStats.total_signups >= 3,
                LFGMemberStats.reliability_score < warn_threshold,
                LFGMemberStats.is_blacklisted == False
            ).order_by(LFGMemberStats.reliability_score.asc()).limit(10).all()

            # Get blacklisted members (always show for admin visibility)
            blacklisted_members = db.query(LFGMemberStats).filter(
                LFGMemberStats.guild_id == int(guild_id),
                LFGMemberStats.is_blacklisted == True
            ).order_by(LFGMemberStats.blacklisted_at.desc()).all()

            # Build leaderboard using the member_names_cache we already fetched
            leaderboard = []
            for stats in top_members:
                # Try to get display name from Discord API cache first
                display_name = member_names_cache.get(stats.user_id)

                # Fall back to LFGMember table
                if not display_name:
                    member = db.query(LFGMember).filter_by(
                        user_id=stats.user_id
                    ).order_by(LFGMember.joined_at.desc()).first()
                    display_name = member.display_name if member else f"Unknown User"

                leaderboard.append({
                    'user_id': stats.user_id,
                    'display_name': display_name,
                    'reliability_score': stats.reliability_score if stats.reliability_score is not None else 100,
                    'total_showed': stats.total_showed or 0,
                    'total_no_shows': stats.total_no_shows or 0,
                    'total_late': stats.total_late or 0,
                    'total_cancelled': stats.total_cancelled or 0,
                    'total_pardoned': stats.total_pardoned or 0,
                    'total_signups': stats.total_signups or 0,
                    'is_blacklisted': stats.is_blacklisted,
                })

            # Process at-risk members
            at_risk_list = []
            for stats in at_risk_members:
                # Try to get display name from Discord API cache first
                display_name = member_names_cache.get(stats.user_id)

                # Fall back to LFGMember table
                if not display_name:
                    member = db.query(LFGMember).filter_by(
                        user_id=stats.user_id
                    ).order_by(LFGMember.joined_at.desc()).first()
                    display_name = member.display_name if member else f"Unknown User"

                at_risk_list.append({
                    'user_id': stats.user_id,
                    'display_name': display_name,
                    'reliability_score': stats.reliability_score if stats.reliability_score is not None else 100,
                    'total_showed': stats.total_showed or 0,
                    'total_no_shows': stats.total_no_shows or 0,
                    'total_late': stats.total_late or 0,
                    'total_cancelled': stats.total_cancelled or 0,
                    'total_pardoned': stats.total_pardoned or 0,
                    'total_signups': stats.total_signups or 0,
                })

            # Process warned members
            warned_list = []
            for stats in warned_members:
                # Try to get display name from Discord API cache first
                display_name = member_names_cache.get(stats.user_id)

                # Fall back to LFGMember table
                if not display_name:
                    member = db.query(LFGMember).filter_by(
                        user_id=stats.user_id
                    ).order_by(LFGMember.joined_at.desc()).first()
                    display_name = member.display_name if member else f"Unknown User"

                warned_list.append({
                    'user_id': stats.user_id,
                    'display_name': display_name,
                    'reliability_score': stats.reliability_score if stats.reliability_score is not None else 0,
                    'total_showed': stats.total_showed or 0,
                    'total_no_shows': stats.total_no_shows or 0,
                    'total_late': stats.total_late or 0,
                    'total_cancelled': stats.total_cancelled or 0,
                    'total_pardoned': stats.total_pardoned or 0,
                    'total_signups': stats.total_signups or 0,
                })

            # Process blacklisted members
            blacklisted_list = []
            for stats in blacklisted_members:
                # Try to get display name from Discord API cache first
                display_name = member_names_cache.get(stats.user_id)

                # Fall back to LFGMember table
                if not display_name:
                    member = db.query(LFGMember).filter_by(
                        user_id=stats.user_id
                    ).order_by(LFGMember.joined_at.desc()).first()
                    display_name = member.display_name if member else f"Unknown User"

                blacklisted_list.append({
                    'user_id': stats.user_id,
                    'display_name': display_name,
                    'reliability_score': stats.reliability_score if stats.reliability_score is not None else 0,
                    'total_showed': stats.total_showed or 0,
                    'total_no_shows': stats.total_no_shows or 0,
                    'total_late': stats.total_late or 0,
                    'total_cancelled': stats.total_cancelled or 0,
                    'total_pardoned': stats.total_pardoned or 0,
                    'total_signups': stats.total_signups or 0,
                    'blacklist_reason': stats.blacklist_reason or 'No reason provided',
                    'blacklisted_at': stats.blacklisted_at,
                })

            # Get unique game names for filter dropdown
            unique_games = sorted(list(set(g['game_name'] for g in groups_data)))

        return render(request, 'questlog/attendance.html', {
            'guild': guild,
            'guild_record': guild_db,
            'config': {
                'auto_noshow_hours': config.auto_noshow_hours,
                'warn_at_reliability': config.warn_at_reliability,
                'min_reliability_score': config.min_reliability_score,
                'auto_blacklist_noshows': config.auto_blacklist_noshows,
            },
            'groups': groups_data,
            'unique_games': unique_games,
            'leaderboard': leaderboard,
            'at_risk': at_risk_list,
            'warned': warned_list,
            'blacklisted': blacklisted_list,
            'is_premium': is_premium,
            'is_admin': is_admin,
            'is_member': is_member,
            'can_manage_attendance': can_manage_attendance,
            'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
            'active_page': 'attendance',
        })

    except Exception as e:
        logger.error(f"Error loading attendance: {e}", exc_info=True)
        messages.error(request, f'Error loading attendance: {e}')
        return redirect('guild_dashboard', guild_id=guild_id)


@require_http_methods(["GET"])
@api_auth_required
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
        from .models import Guild, LFGGame, SubscriptionTier

        with get_db_session() as db:
            # Check tier limits for LFG games
            guild_record = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild_record:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Count existing LFG games
            current_count = db.query(LFGGame).filter_by(guild_id=int(guild_id)).count()

            # Check tier limits
            if guild_record.is_vip or guild_record.subscription_tier == SubscriptionTier.PREMIUM.value:
                # Unlimited for Premium/VIP
                pass
            elif guild_record.subscription_tier == SubscriptionTier.PRO.value:
                if current_count >= 10:
                    return JsonResponse({
                        'error': f'Pro tier limit reached: You can create up to 10 LFG games. Currently have {current_count} games.',
                        'limit': 10,
                        'current': current_count
                    }, status=403)
            else:  # Free tier
                if current_count >= 5:
                    return JsonResponse({
                        'error': f'Free tier limit reached: You can create up to 5 LFG games. Currently have {current_count} games. Upgrade to Pro for 10 games or Premium for unlimited.',
                        'limit': 5,
                        'current': current_count
                    }, status=403)

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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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

            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)

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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_lfg_stats(request, guild_id):
    """GET /api/guild/<id>/lfg/stats/ - Get member stats/leaderboard (Premium)."""
    try:
        from .db import get_db_session
        from .models import LFGMemberStats, Guild, GuildMember

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

            # Enrich with usernames
            enriched_members = []
            for m in members:
                # Get user info
                member = db.query(GuildMember).filter_by(
                    guild_id=int(guild_id),
                    user_id=m.user_id
                ).first()

                username = member.display_name or member.username or f'User {m.user_id}' if member else f'User {m.user_id}'

                enriched_members.append({
                    'user_id': str(m.user_id),
                    'display_name': username,
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
                })

            return JsonResponse({'success': True, 'stats': enriched_members})

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
def api_lfg_blacklist(request, guild_id):
    """GET /api/guild/<id>/lfg/blacklist/ - Get blacklisted members (Premium)."""
    try:
        from .db import get_db_session
        from .models import LFGMemberStats, Guild, GuildMember
        from datetime import datetime

        with get_db_session() as db:
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild or not guild.is_premium():
                return JsonResponse({'error': 'Premium required', 'members': []}, status=403)

            members = db.query(LFGMemberStats).filter(
                LFGMemberStats.guild_id == int(guild_id),
                LFGMemberStats.is_blacklisted == True
            ).all()

            # Enrich with usernames and format dates
            enriched_members = []
            for m in members:
                # Get user info
                member = db.query(GuildMember).filter_by(
                    guild_id=int(guild_id),
                    user_id=m.user_id
                ).first()

                username = member.display_name or member.username or f'User {m.user_id}' if member else f'User {m.user_id}'
                formatted_date = datetime.fromtimestamp(m.blacklisted_at).strftime('%b %d, %Y at %I:%M %p') if m.blacklisted_at else 'Unknown'

                enriched_members.append({
                    'user_id': str(m.user_id),
                    'username': username,
                    'reliability_score': m.reliability_score,
                    'total_no_shows': m.total_no_shows,
                    'blacklist_reason': m.blacklist_reason,
                    'blacklisted_at': m.blacklisted_at,
                    'formatted_date': formatted_date,
                    'blacklisted_by': str(m.blacklisted_by) if m.blacklisted_by else None,
                })

            return JsonResponse({'members': enriched_members})

    except Exception as e:
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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

            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


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
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
@require_subscription_tier('pro', 'premium')
@validate_json_schema({
    "type": "object",
    "properties": {
        "group_id": {"type": "integer", "minimum": 1},
        "user_id": {"type": "integer", "minimum": 1},
        "status": {"type": "string", "enum": ["showed", "no_show", "late", "cancelled", "confirmed", "pardoned"]}
    },
    "required": ["group_id", "user_id", "status"]
})
def api_lfg_attendance_update(request, guild_id):
    """POST /api/guild/<id>/lfg/attendance/update/ - Update attendance status (Pro/Premium only)."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGConfig, LFGGroup, LFGMember, LFGAttendance, LFGMemberStats
        import time
        import logging
        logger = logging.getLogger(__name__)

        # Get validated data
        data = request.validated_data
        group_id = data['group_id']
        user_id = data['user_id']
        status = data['status']

        with get_db_session() as db:
            # Tier check handled by @require_subscription_tier decorator
            # Check if attendance tracking is enabled
            config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if not config or not config.attendance_tracking_enabled:
                return JsonResponse({'error': 'Attendance tracking not enabled'}, status=403)

            # Verify group belongs to this guild
            group = db.query(LFGGroup).filter_by(
                id=int(group_id),
                guild_id=int(guild_id)
            ).first()

            if not group:
                return JsonResponse({'error': 'Group not found'}, status=404)

            # Check permissions - reuse same logic as guild_attendance view
            # Get user info from session
            session_user_id = request.session.get('discord_user', {}).get('id')
            admin_guilds = request.session.get('discord_admin_guilds', [])
            all_guilds = request.session.get('discord_all_guilds', [])

            is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)
            user_guild = next((g for g in all_guilds if str(g['id']) == str(guild_id)), None)

            # Check permissions
            has_permission = False
            if is_admin:
                has_permission = True
            elif user_guild:
                permissions = int(user_guild.get('permissions', 0))
                has_manage_messages = (permissions & 0x2000) == 0x2000
                has_create_events = (permissions & 0x100000000) == 0x100000000
                has_manage_events = (permissions & 0x200000000) == 0x200000000

                if has_manage_messages:
                    has_permission = True
                else:
                    # Check for Raid Leader role
                    try:
                        # Get guild roles from cache (no Discord API call!)
                        from .discord_resources import get_guild_roles, get_guild_member

                        if session_user_id:
                            roles = get_guild_roles(str(guild_id))

                            raid_leader_role_id = None
                            for role in roles:
                                if role.get('name') == 'Raid Leader':
                                    raid_leader_role_id = role.get('id')
                                    break

                            # Check if user has the Raid Leader role (from cache, no API call!)
                            if raid_leader_role_id:
                                member_data = get_guild_member(str(guild_id), str(session_user_id))
                                if member_data:
                                    member_roles = member_data.get('roles', [])
                                    if str(raid_leader_role_id) in member_roles:
                                        # Check if they have required permissions
                                        if has_create_events and has_manage_events:
                                            has_permission = True
                    except Exception as e:
                        logger.error(f"Error checking Raid Leader permissions from cache: {e}")

            if not has_permission:
                return JsonResponse({'error': 'Insufficient permissions'}, status=403)

            # Check if user is blacklisted (prevents joining new groups)
            user_stats = db.query(LFGMemberStats).filter_by(
                guild_id=int(guild_id),
                user_id=int(user_id)
            ).first()

            # Block blacklisted users from joining NEW groups
            # Check if they're trying to join a group they're not already in
            existing_attendance = db.query(LFGAttendance).filter_by(
                group_id=int(group_id),
                user_id=int(user_id)
            ).first()

            if user_stats and user_stats.is_blacklisted and not existing_attendance:
                return JsonResponse({
                    'error': 'User is blacklisted and cannot join new groups',
                    'is_blacklisted': True,
                    'blacklist_reason': user_stats.blacklist_reason
                }, status=403)

            # Update or create attendance record
            now = int(time.time())
            attendance = existing_attendance

            if attendance:
                # Update existing record
                attendance.status = status
                attendance.updated_at = now

                # Update timestamps based on status
                if status == 'showed':
                    attendance.showed_at = now
                elif status == 'no_show':
                    attendance.no_show_at = now
                elif status == 'late':
                    attendance.late_at = now
                elif status == 'cancelled':
                    attendance.cancelled_at = now
            else:
                # Create new record
                attendance = LFGAttendance(
                    group_id=int(group_id),
                    user_id=int(user_id),
                    status=status,
                    joined_at=now,
                    updated_at=now
                )

                if status == 'showed':
                    attendance.showed_at = now
                elif status == 'no_show':
                    attendance.no_show_at = now
                elif status == 'late':
                    attendance.late_at = now
                elif status == 'cancelled':
                    attendance.cancelled_at = now

                db.add(attendance)

            db.flush()  # Ensure attendance record is saved before recalculating stats

            # Get or create stats record FIRST (need to check pardon timestamp)
            stats = db.query(LFGMemberStats).filter_by(
                guild_id=int(guild_id),
                user_id=int(user_id)
            ).first()

            if not stats:
                stats = LFGMemberStats(
                    guild_id=int(guild_id),
                    user_id=int(user_id)
                )
                db.add(stats)

            # Get attendance records for recalculation
            # If user has been globally pardoned, ONLY count records AFTER the pardon timestamp
            # Historical records from before pardon are kept for admin reference but don't affect calculations
            all_attendance_query = db.query(LFGAttendance).filter_by(
                user_id=int(user_id)
            ).join(LFGGroup).filter(
                LFGGroup.guild_id == int(guild_id)
            )

            # If globally pardoned, exclude records from before the pardon
            if stats.blacklist_pardoned and stats.blacklist_pardoned_at:
                # Only count records created/updated AFTER the pardon timestamp
                # Use the latest timestamp available (updated_at, joined_at, or created_at)
                all_attendance_query = all_attendance_query.filter(
                    or_(
                        LFGAttendance.updated_at >= stats.blacklist_pardoned_at,
                        and_(
                            LFGAttendance.updated_at == None,
                            LFGAttendance.joined_at >= stats.blacklist_pardoned_at
                        )
                    )
                )

            all_attendance = all_attendance_query.all()

            # Recalculate from attendance records (excluding historical data if pardoned)
            # Global Pardon = fresh start, only NEW records count toward stats
            total_signups = len(all_attendance)
            total_showed = sum(1 for a in all_attendance if a.status == 'showed')
            total_no_shows = sum(1 for a in all_attendance if a.status == 'no_show')
            total_late = sum(1 for a in all_attendance if a.status == 'late')
            total_cancelled = sum(1 for a in all_attendance if a.status == 'cancelled')
            total_pardoned = sum(1 for a in all_attendance if a.status == 'pardoned')

            stats.total_signups = total_signups
            stats.total_showed = total_showed
            stats.total_no_shows = total_no_shows
            stats.total_late = total_late
            stats.total_cancelled = total_cancelled
            stats.total_pardoned = total_pardoned

            # Recalculate reliability score (0-100)
            # Pardoned counts as showed (100%), late counts 80%, no-show counts 0%, cancelled excluded
            total_counted = total_showed + total_pardoned + total_no_shows + total_late
            if total_counted > 0:
                # Pardoned = 100% (valid excuse, treat as showed), showed = 100%, late = 80%, no-show = 0%
                score = ((total_showed + total_pardoned) * 100 + (total_late * 80)) / total_counted
                stats.reliability_score = int(score)
            else:
                stats.reliability_score = 100

            # Update timestamps
            stats.updated_at = now
            if all_attendance:
                # Get all non-None timestamps
                timestamps = [a.updated_at or a.joined_at or a.created_at for a in all_attendance if (a.updated_at or a.joined_at or a.created_at)]
                if timestamps:
                    stats.last_event = max(timestamps)

                # Get first join timestamp
                join_times = [a.joined_at for a in all_attendance if a.joined_at]
                if join_times:
                    stats.first_event = min(join_times)
                elif timestamps:
                    stats.first_event = min(timestamps)

            # Check auto-blacklist threshold (always check, even for pardoned users)
            # Global Pardon is a fresh start, not permanent immunity - they can be blacklisted again
            if config.auto_blacklist_noshows > 0:
                if stats.total_no_shows >= config.auto_blacklist_noshows and not stats.is_blacklisted:
                    # Add to blacklist when threshold is reached
                    stats.is_blacklisted = True
                    stats.blacklisted_at = now
                    stats.blacklist_reason = f"Auto-blacklisted: {stats.total_no_shows} no-shows"
                elif stats.total_no_shows < config.auto_blacklist_noshows and stats.is_blacklisted and stats.blacklist_reason and "Auto-blacklisted" in stats.blacklist_reason:
                    # Remove from blacklist if no-show count drops below threshold (e.g., pardoned)
                    # Only remove if they were auto-blacklisted (not manually blacklisted)
                    stats.is_blacklisted = False
                    stats.blacklisted_at = None
                    stats.blacklist_reason = None

            db.commit()

            return JsonResponse({
                'success': True,
                'attendance': {
                    'status': status,
                    'reliability_score': stats.reliability_score
                },
                'stats': {
                    'total_showed': stats.total_showed,
                    'total_no_shows': stats.total_no_shows,
                    'total_late': stats.total_late,
                    'total_cancelled': stats.total_cancelled,
                    'total_pardoned': stats.total_pardoned,
                    'reliability_score': stats.reliability_score,
                    'is_blacklisted': stats.is_blacklisted or False
                }
            })

    except Exception as e:
        logger.error(f"Error updating attendance: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_auth_required
def api_lfg_blacklist_toggle(request, guild_id):
    """POST /api/guild/<id>/lfg/blacklist/toggle/ - Manually toggle blacklist status for a member."""
    import json
    try:
        from .db import get_db_session
        from .models import Guild, LFGConfig, LFGMemberStats

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        user_id = data.get('user_id')
        reason = data.get('reason', '')

        if not user_id:
            return JsonResponse({'error': 'Missing user_id'}, status=400)

        with get_db_session() as db:
            # Check permissions (admin, moderator, or raid leader)
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get LFG config
            config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if not config or not config.attendance_tracking_enabled:
                return JsonResponse({'error': 'Attendance tracking not enabled'}, status=403)

            # Get or create member stats
            stats = db.query(LFGMemberStats).filter_by(
                guild_id=int(guild_id),
                user_id=int(user_id)
            ).first()

            if not stats:
                return JsonResponse({'error': 'Member not found in LFG system'}, status=404)

            # Toggle blacklist status
            now = int(time.time())
            if stats.is_blacklisted:
                # Unblacklist
                stats.is_blacklisted = False
                stats.blacklisted_at = None
                stats.blacklist_reason = None
                action = 'unblacklisted'
            else:
                # Blacklist
                stats.is_blacklisted = True
                stats.blacklisted_at = now
                stats.blacklist_reason = f"Manually blacklisted by admin{': ' + reason if reason else ''}"
                action = 'blacklisted'

            db.commit()

            return JsonResponse({
                'success': True,
                'action': action,
                'is_blacklisted': stats.is_blacklisted,
                'blacklist_reason': stats.blacklist_reason
            })

    except Exception as e:
        logger.error(f"Error toggling blacklist: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


def api_lfg_pardon(request, guild_id):
    """POST /api/guild/<id>/lfg/pardon/ - Grant permanent pardon to a member, removing them from blacklist and preventing auto-blacklist."""
    import json
    try:
        from .db import get_db_session
        from .models import Guild, LFGConfig, LFGMemberStats

        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        user_id = data.get('user_id')

        if not user_id:
            return JsonResponse({'error': 'Missing user_id'}, status=400)

        with get_db_session() as db:
            # Check permissions (admin, moderator, or raid leader)
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get LFG config
            config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if not config or not config.attendance_tracking_enabled:
                return JsonResponse({'error': 'Attendance tracking not enabled'}, status=403)

            # Get or create member stats
            stats = db.query(LFGMemberStats).filter_by(
                guild_id=int(guild_id),
                user_id=int(user_id)
            ).first()

            if not stats:
                return JsonResponse({'error': 'Member not found in LFG system'}, status=404)

            # Grant pardon - RESET ALL counters for complete fresh start
            # Historical LFGAttendance records are kept for admin viewing but excluded from calculations
            now = int(time.time())
            stats.blacklist_pardoned = True
            stats.blacklist_pardoned_at = now

            # Reset ALL stats to 0 (complete fresh start)
            stats.total_showed = 0
            stats.total_no_shows = 0
            stats.total_cancelled = 0
            stats.total_late = 0
            stats.total_pardoned = 0
            stats.total_signups = 0
            stats.current_noshow_streak = 0
            stats.current_show_streak = 0
            stats.best_show_streak = 0
            stats.reliability_score = 100  # Reset to perfect score

            # If currently blacklisted, remove them from blacklist
            was_blacklisted = stats.is_blacklisted
            if stats.is_blacklisted:
                stats.is_blacklisted = False
                stats.blacklisted_at = None
                stats.blacklist_reason = None

            db.commit()

            return JsonResponse({
                'success': True,
                'pardoned': True,
                'was_blacklisted': was_blacklisted,
                'message': 'Member has been pardoned and will not be auto-blacklisted in the future'
            })

    except Exception as e:
        logger.error(f"Error pardoning member: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_auth_required
@require_subscription_tier('pro', 'premium')
@ratelimit(key='user_or_ip', rate='10/h', method='GET', block=True)
def api_lfg_attendance_export(request, guild_id):
    """GET /api/guild/<id>/lfg/attendance/export/ - Export attendance data as CSV (Pro/Premium only, 10 req/hour)."""
    import csv
    import io
    from django.http import HttpResponse

    try:
        from .db import get_db_session
        from .models import LFGConfig, LFGGroup, LFGAttendance, LFGMemberStats

        with get_db_session() as db:
            # Tier check handled by @require_subscription_tier decorator
            # Check if attendance tracking is enabled
            config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if not config or not config.attendance_tracking_enabled:
                return JsonResponse({'error': 'Attendance tracking not enabled'}, status=403)

            # Fetch member display names from Discord API (using bot token)
            import requests
            member_names_cache = {}

            # Fetch member names from cache (no Discord API call!)
            from .discord_resources import get_guild_members

            try:
                guild_members = get_guild_members(str(guild_id))
                for m in guild_members:
                    user_id = int(m['id'])
                    display_name = m.get('display_name') or m.get('username', 'Unknown')
                    member_names_cache[user_id] = display_name
                logger.info(f"Loaded {len(member_names_cache)} member names from cache for export")
            except Exception as e:
                logger.error(f"Error fetching guild members from cache for export: {e}")

            # Get all groups with attendance from last 90 days
            import time
            ninety_days_ago = int(time.time()) - (90 * 24 * 3600)

            groups = db.query(LFGGroup).filter(
                LFGGroup.guild_id == int(guild_id),
                LFGGroup.created_at >= ninety_days_ago
            ).order_by(LFGGroup.scheduled_time.desc()).all()

            # Create CSV
            output = io.StringIO()
            writer = csv.writer(output)

            # Write header
            writer.writerow([
                'Group Name',
                'Scheduled Date',
                'Member Name',
                'User ID',
                'Status',
                'Joined At',
                'Confirmed At',
                'Showed At',
                'Cancelled At',
                'Late At',
                'No Show At',
                'Reliability Score'
            ])

            # Write data
            for group in groups:
                attendance_records = db.query(LFGAttendance).filter_by(
                    group_id=group.id
                ).all()

                for att in attendance_records:
                    # Get member stats
                    stats = db.query(LFGMemberStats).filter_by(
                        guild_id=int(guild_id),
                        user_id=att.user_id
                    ).first()

                    # Get display name from Discord API cache first, then fallback to GuildMember table
                    display_name = member_names_cache.get(att.user_id)

                    if not display_name:
                        from .models import GuildMember
                        member = db.query(GuildMember).filter_by(
                            guild_id=int(guild_id),
                            user_id=att.user_id
                        ).first()
                        display_name = member.display_name if member else f"User {att.user_id}"

                    # Format timestamps
                    from datetime import datetime
                    scheduled_date = datetime.fromtimestamp(group.scheduled_time).strftime('%Y-%m-%d %H:%M') if group.scheduled_time else 'N/A'
                    joined_at = datetime.fromtimestamp(att.joined_at).strftime('%Y-%m-%d %H:%M') if att.joined_at else ''
                    confirmed_at = datetime.fromtimestamp(att.confirmed_at).strftime('%Y-%m-%d %H:%M') if att.confirmed_at else ''
                    showed_at = datetime.fromtimestamp(att.showed_at).strftime('%Y-%m-%d %H:%M') if att.showed_at else ''
                    cancelled_at = datetime.fromtimestamp(att.cancelled_at).strftime('%Y-%m-%d %H:%M') if att.cancelled_at else ''
                    late_at = datetime.fromtimestamp(att.late_at).strftime('%Y-%m-%d %H:%M') if att.late_at else ''
                    no_show_at = datetime.fromtimestamp(att.no_show_at).strftime('%Y-%m-%d %H:%M') if att.no_show_at else ''

                    writer.writerow([
                        group.thread_name or f"Group {group.id}",
                        scheduled_date,
                        display_name,
                        att.user_id,
                        att.status.value if hasattr(att.status, 'value') else att.status,
                        joined_at,
                        confirmed_at,
                        showed_at,
                        cancelled_at,
                        late_at,
                        no_show_at,
                        stats.reliability_score if stats else 'N/A'
                    ])

            # Return CSV
            response = HttpResponse(output.getvalue(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="attendance_guild_{guild_id}.csv"'
            return response

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error exporting attendance: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
def api_lfg_user_history(request, guild_id, user_id):
    """GET /api/guild/<id>/lfg/attendance/user/<user_id>/ - Get complete attendance history for a user (Premium)."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGConfig, LFGGroup, LFGAttendance, LFGMemberStats, GuildMember
        from datetime import datetime

        with get_db_session() as db:
            # Check if guild is premium
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild or not guild.is_premium():
                return JsonResponse({'error': 'Premium required'}, status=403)

            # Check if attendance tracking is enabled
            config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if not config or not config.attendance_tracking_enabled:
                return JsonResponse({'error': 'Attendance tracking not enabled'}, status=403)

            # Get user stats
            stats = db.query(LFGMemberStats).filter_by(
                guild_id=int(guild_id),
                user_id=int(user_id)
            ).first()

            # Get user display name
            member = db.query(GuildMember).filter_by(
                guild_id=int(guild_id),
                user_id=int(user_id)
            ).first()
            display_name = member.display_name if member else f"User {user_id}"

            # Get ALL attendance records for this user (including historical pre-pardon records)
            attendance_records = db.query(LFGAttendance).filter_by(
                user_id=int(user_id)
            ).join(LFGGroup).filter(
                LFGGroup.guild_id == int(guild_id)
            ).order_by(LFGGroup.scheduled_time.desc()).all()

            # Format attendance history
            history = []
            from .models import LFGGame
            for att in attendance_records:
                group = db.query(LFGGroup).filter_by(id=att.group_id).first()
                if not group:
                    continue

                # Get game name from LFGGame table
                game = db.query(LFGGame).filter_by(id=group.game_id).first()
                game_name = game.game_name if game else "Unknown Game"

                # Determine if this record is from before pardon
                is_pre_pardon = False
                if stats and stats.blacklist_pardoned and stats.blacklist_pardoned_at:
                    record_time = att.updated_at or att.joined_at or 0
                    if record_time < stats.blacklist_pardoned_at:
                        is_pre_pardon = True

                history.append({
                    'group_id': group.id,
                    'group_name': group.thread_name or f"Group {group.id}",
                    'game_name': game_name,
                    'scheduled_time': group.scheduled_time,
                    'scheduled_date': datetime.fromtimestamp(group.scheduled_time).strftime('%Y-%m-%d %H:%M') if group.scheduled_time else 'N/A',
                    'status': att.status,
                    'joined_at': att.joined_at,
                    'updated_at': att.updated_at,
                    'is_pre_pardon': is_pre_pardon,  # Flag to show in UI
                })

            return JsonResponse({
                'success': True,
                'user_id': user_id,
                'display_name': display_name,
                'stats': {
                    'total_signups': stats.total_signups if stats else 0,
                    'total_showed': stats.total_showed if stats else 0,
                    'total_no_shows': stats.total_no_shows if stats else 0,
                    'total_late': stats.total_late if stats else 0,
                    'total_cancelled': stats.total_cancelled if stats else 0,
                    'total_pardoned': stats.total_pardoned if stats else 0,
                    'reliability_score': stats.reliability_score if stats else 100,
                    'is_blacklisted': stats.is_blacklisted if stats else False,
                    'blacklist_reason': stats.blacklist_reason if stats else None,
                    'blacklist_pardoned': stats.blacklist_pardoned if stats else False,
                    'blacklist_pardoned_at': stats.blacklist_pardoned_at if stats else None,
                },
                'history': history,
                'total_events': len(history)
            })

    except Exception as e:
        logger.error(f"Error fetching user history: {e}")
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# ====== LFG Browser API Endpoints (All Tiers - Game limits enforced) ======

@require_http_methods(["GET"])
@api_member_auth_required
def api_lfg_manager_check(request, guild_id):
    """
    GET /api/guild/<id>/lfg/manager-check/ - Check if user has LFG Manager role (real-time).

    This endpoint is polled every 30 seconds by the frontend to detect permission changes
    in real-time without requiring a page refresh. This ensures that:
    - When a user is granted the "LFG Manager" role, Edit/Delete buttons appear immediately
    - When the role is revoked, the buttons disappear immediately
    - Role permission changes (adding/removing CREATE_EVENTS or MANAGE_EVENTS) are detected

    Returns:
        JSON with is_admin, has_lfg_manager_role, and can_manage flags
    """
    try:
        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        # Check if user is admin
        admin_guilds = request.session.get('discord_admin_guilds', [])
        is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)

        # Check for "LFG Manager" role with required permissions
        has_lfg_manager_role = check_lfg_manager_role(guild_id, user_id)

        can_manage = is_admin or has_lfg_manager_role

        return JsonResponse({
            'success': True,
            'is_admin': is_admin,
            'has_lfg_manager_role': has_lfg_manager_role,
            'can_manage': can_manage
        })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in LFG Manager check: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred'}, status=500)


@require_http_methods(["GET"])
def api_lfg_browser_groups(request, guild_id):
    """GET /api/guild/<id>/lfg/browser/groups/ - List active LFG groups with game info (Pro/Premium/VIP)."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, LFGGame, LFGMember
        import time

        with get_db_session() as db:
            # Get guild (LFG Browser now available to all tiers)
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get filter parameters
            game_id = request.GET.get('game_id')
            status_filter = request.GET.get('status', 'active')  # active, full, all

            # Build query
            query = db.query(LFGGroup).filter(
                LFGGroup.guild_id == int(guild_id),
                LFGGroup.is_active == True
            )

            # Filter by game
            if game_id:
                query = query.filter(LFGGroup.game_id == int(game_id))

            # Filter by status
            if status_filter == 'active':
                query = query.filter(LFGGroup.is_full == False)
            elif status_filter == 'full':
                query = query.filter(LFGGroup.is_full == True)

            # Get groups ordered by scheduled time (upcoming first)
            current_time = int(time.time())
            groups = query.order_by(LFGGroup.scheduled_time.asc()).all()

            # PERFORMANCE: Batch load all games and members to avoid N+1 queries
            group_ids = [g.id for g in groups]
            game_ids = list(set([g.game_id for g in groups]))

            # Single query for all games
            games_dict = {}
            if game_ids:
                games = db.query(LFGGame).filter(LFGGame.id.in_(game_ids)).all()
                games_dict = {g.id: g for g in games}

            # Single query for all members
            members_by_group = {}
            if group_ids:
                all_members = db.query(LFGMember).filter(
                    LFGMember.group_id.in_(group_ids),
                    LFGMember.left_at == None
                ).all()

                for member in all_members:
                    if member.group_id not in members_by_group:
                        members_by_group[member.group_id] = []
                    members_by_group[member.group_id].append(member)

            # Single query for all attendance records (if attendance tracking enabled and Pro/Premium/VIP)
            from .models import LFGConfig, LFGAttendance, AttendanceStatus
            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            attendance_by_group = {}
            # Attendance tracking only for Pro/Premium/VIP
            is_attendance_tier = guild.subscription_tier in ['pro', 'Pro', 'premium', 'Premium'] or guild.is_vip
            if lfg_config and lfg_config.attendance_tracking_enabled and is_attendance_tier and group_ids:
                all_attendance = db.query(LFGAttendance).filter(
                    LFGAttendance.group_id.in_(group_ids),
                    LFGAttendance.status == AttendanceStatus.CONFIRMED
                ).all()

                for attendance in all_attendance:
                    if attendance.group_id not in attendance_by_group:
                        attendance_by_group[attendance.group_id] = []
                    attendance_by_group[attendance.group_id].append(attendance)

            groups_data = []
            for group in groups:
                # Get game from pre-loaded dict
                game = games_dict.get(group.game_id)

                # Get members from pre-loaded dict
                members = members_by_group.get(group.id, [])

                # Populate display names if null (for legacy records)
                from .models import GuildMember as GuildMemberModel
                members_data = []
                for m in members:
                    display_name = m.display_name
                    if not display_name:
                        # Look up display name from GuildMember table
                        guild_member = db.query(GuildMemberModel).filter_by(
                            guild_id=int(guild_id),
                            user_id=m.user_id
                        ).first()
                        display_name = guild_member.display_name if guild_member else f'User {m.user_id}'
                        # Update the LFGMember record with the display name
                        m.display_name = display_name

                    members_data.append({
                        'user_id': str(m.user_id),
                        'display_name': display_name,
                        'rank_value': m.rank_value,
                        'is_creator': m.is_creator,
                        'is_co_leader': m.is_co_leader,
                        'selections': json_lib.loads(m.selections) if m.selections else {},
                        'joined_at': m.joined_at,
                    })

                # Commit any display name updates
                db.commit()

                # Determine if group is in the past, present, or future
                time_status = 'upcoming'
                if group.scheduled_time:
                    if group.scheduled_time < current_time - (2 * 3600):  # More than 2 hours ago
                        time_status = 'past'
                    elif group.scheduled_time < current_time + (1800):  # Within 30 minutes
                        time_status = 'active_now'

                # Get confirmed attendance for this group
                confirmed_attendance = attendance_by_group.get(group.id, [])
                confirmed_ids = [a.user_id for a in confirmed_attendance]

                groups_data.append({
                    'id': group.id,
                    'game_id': group.game_id,
                    'game_name': game.game_name if game else 'Unknown',
                    'game_short': game.game_short if game else '',
                    'game_emoji': game.game_emoji if game else '',
                    'cover_url': game.cover_url if game else None,
                    'thread_id': str(group.thread_id) if group.thread_id else None,
                    'thread_name': group.thread_name,
                    'creator_id': str(group.creator_id),
                    'creator_name': group.creator_name,
                    'scheduled_time': group.scheduled_time,
                    'description': group.description,
                    'max_group_size': group.max_group_size or (game.max_group_size if game else 4),
                    'is_active': group.is_active,
                    'is_full': group.is_full,
                    'member_count': group.member_count,
                    'members': members_data,
                    'created_at': group.created_at,
                    'time_status': time_status,
                    'confirmed_attendance_count': len(confirmed_ids),
                    'confirmed_attendance_ids': [str(uid) for uid in confirmed_ids],
                    'attendance_tracking_enabled': (lfg_config.attendance_tracking_enabled and is_attendance_tier) if lfg_config else False,
                })

            response = JsonResponse({
                'success': True,
                'groups': groups_data,
                'count': len(groups_data)
            })
            # No caching - always fetch fresh data for instant updates
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
            return response

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching LFG browser groups: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_member_auth_required
def api_lfg_browser_create(request, guild_id):
    """POST /api/guild/<id>/lfg/browser/create/ - Create LFG group from web (Pro/Premium/VIP)."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, LFGGame, LFGMember
        import time
        import logging
        logger = logging.getLogger(__name__)

        data = json.loads(request.body)
        game_id = data.get('game_id')
        title = data.get('title', '').strip()
        scheduled_time = data.get('scheduled_time')
        event_duration = data.get('event_duration')
        ping_role_id = data.get('ping_role_id')
        description = data.get('description', '')
        max_group_size = data.get('max_group_size')
        co_leader_ids = data.get('co_leader_ids', [])  # List of user IDs
        creator_options = data.get('creator_options', {})  # Creator's game-specific selections

        if not game_id:
            return JsonResponse({'error': 'Game ID required'}, status=400)

        if not title:
            return JsonResponse({'error': 'Group title required'}, status=400)

        if len(title) > 150:
            return JsonResponse({'error': 'Title must be 150 characters or less'}, status=400)

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')
        username = discord_user.get('username', 'Unknown')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        with get_db_session() as db:
            # Get guild (LFG Browser available to all tiers)
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get game
            game = db.query(LFGGame).filter_by(id=int(game_id), guild_id=int(guild_id)).first()
            if not game:
                return JsonResponse({'error': 'Game not found'}, status=404)

            # Create group (note: thread_id will be 0 for web-created groups until bot creates thread)
            new_group = LFGGroup(
                guild_id=int(guild_id),
                game_id=game.id,
                thread_id=0,  # Will be updated by bot when thread is created
                thread_name=title,
                ping_role_id=int(ping_role_id) if ping_role_id else None,
                creator_id=int(user_id),
                creator_name=username,
                scheduled_time=scheduled_time,
                event_duration=event_duration,
                description=description,
                max_group_size=max_group_size or game.max_group_size,
                is_active=True,
                is_full=False,
                member_count=1,
                created_at=int(time.time())
            )
            db.add(new_group)
            db.flush()  # Get the ID

            # Add creator as first member
            # Extract rank and selections from creator_options
            rank_value = creator_options.get('rank') if creator_options else None
            selections_dict = {k: v for k, v in creator_options.items() if k != 'rank'} if creator_options else {}

            creator_member = LFGMember(
                group_id=new_group.id,
                user_id=int(user_id),
                display_name=username,
                rank_value=rank_value,
                selections=json_lib.dumps(selections_dict) if selections_dict else None,
                is_creator=True,
                joined_at=int(time.time())
            )
            db.add(creator_member)

            # Add co-leaders as members
            from .models import GuildMember as GuildMemberModel
            co_leaders_added = []
            for co_leader_id in co_leader_ids:
                # Skip if co-leader is the creator themselves
                if str(co_leader_id) == str(user_id):
                    continue

                # Fetch display name from GuildMember table
                guild_member = db.query(GuildMemberModel).filter_by(
                    guild_id=int(guild_id),
                    user_id=int(co_leader_id)
                ).first()
                co_leader_display_name = guild_member.display_name if guild_member else f'User {co_leader_id}'

                co_leader_member = LFGMember(
                    group_id=new_group.id,
                    user_id=int(co_leader_id),
                    display_name=co_leader_display_name,
                    is_co_leader=True,
                    joined_at=int(time.time())
                )
                db.add(co_leader_member)
                new_group.member_count += 1
                co_leaders_added.append(int(co_leader_id))

            # Log audit entry for group creation
            log_lfg_audit(
                db=db,
                guild_id=guild_id,
                group_id=new_group.id,
                action='create',
                actor_id=user_id,
                actor_name=username,
                group_name=title,
                game_name=game.game_name
            )

            # Auto-confirm attendance for creator and co-leaders if attendance tracking is enabled (Pro/Premium/VIP only)
            from .models import LFGConfig
            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            is_attendance_tier = guild.subscription_tier in ['pro', 'Pro', 'premium', 'Premium'] or guild.is_vip
            if lfg_config and lfg_config.attendance_tracking_enabled and is_attendance_tier:
                from .models import LFGAttendance, AttendanceStatus

                now = int(time.time())

                # Auto-confirm creator
                creator_attendance = LFGAttendance(
                    group_id=new_group.id,
                    user_id=int(user_id),
                    status=AttendanceStatus.CONFIRMED,
                    confirmed_at=now,
                    joined_at=now
                )
                db.add(creator_attendance)

                # Auto-confirm co-leaders
                for co_leader_id in co_leaders_added:
                    co_leader_attendance = LFGAttendance(
                        group_id=new_group.id,
                        user_id=co_leader_id,
                        status=AttendanceStatus.CONFIRMED,
                        confirmed_at=now,
                        joined_at=now
                    )
                    db.add(co_leader_attendance)

            db.commit()

            # Send notifications (lfg_config already queried above for attendance)
            if not lfg_config:
                lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()

            if lfg_config:
                # Build notification embed with full group details
                scheduled_text = f"<t:{scheduled_time}:F>" if scheduled_time else "Now / Flexible"

                # Build members list with roles
                # Extract creator's role from selections if available
                creator_role = 'Leader'
                if creator_options:
                    for key, value in creator_options.items():
                        if key != 'rank' and value:
                            creator_role = value
                            break
                members_text = f"<@{user_id}> - {creator_role}"
                member_count = 1

                # Add co-leaders to members list
                for co_leader_id in co_leaders_added:
                    members_text += f"\n<@{co_leader_id}> - Co-Leader"
                    member_count += 1

                # Build confirmed attendance list (for premium guilds with attendance enabled)
                confirmed_attendance = ""
                if hasattr(lfg_config, 'attendance_tracking_enabled') and lfg_config.attendance_tracking_enabled:
                    # For now, creator is auto-confirmed
                    confirmed_attendance = f"<@{user_id}>"
                    for co_leader_id in co_leaders_added:
                        confirmed_attendance += f" <@{co_leader_id}>"

                # Format event duration
                duration_text = 'Not set'
                if new_group.event_duration:
                    duration_text = f"{new_group.event_duration} hour{'s' if new_group.event_duration != 1 else ''}"

                embed_data = {
                    'title': f"{game.game_emoji or '🎮'} {title}",
                    'description': f"Group by <@{user_id}>",
                    'color': 0x5865F2,  # Discord blurple
                    'fields': [
                        {'name': 'Scheduled Time', 'value': scheduled_text, 'inline': True},
                        {'name': 'Event Duration ⏱️', 'value': duration_text, 'inline': True},
                        {'name': 'Activity 🎮', 'value': 'No one currently playing', 'inline': True},
                        {'name': f'Members ({member_count}/{new_group.max_group_size})', 'value': members_text, 'inline': False},
                    ],
                    'footer': {'text': f'Group ID: {new_group.id}'},
                    'group_id': new_group.id,  # For bot action processing
                }

                if description:
                    embed_data['fields'].insert(3, {'name': '📝 Description', 'value': description[:1024], 'inline': False})

                # Add confirmed attendance if tracking is enabled
                if confirmed_attendance:
                    confirm_count = len(confirmed_attendance.split())
                    embed_data['fields'].append({
                        'name': f'📋 Confirmed Attendance ({confirm_count}/{member_count})',
                        'value': confirmed_attendance,
                        'inline': False
                    })

                # Queue bot action to create thread with interactive view
                if lfg_config.browser_notify_channel_id and lfg_config.notify_on_group_create:
                    from .models import PendingAction, ActionType, ActionStatus
                    import time as time_lib

                    action = PendingAction(
                        guild_id=int(guild_id),
                        action_type=ActionType.LFG_THREAD_CREATE,
                        payload=json.dumps({
                            'group_id': new_group.id,
                            'channel_id': str(lfg_config.browser_notify_channel_id)
                        }),
                        status=ActionStatus.PENDING,
                        priority=1,  # High priority
                        created_at=int(time_lib.time())
                    )
                    db.add(action)
                    logger.info(f"Queued LFG thread creation action for group {new_group.id}")

                # Send webhook notification if configured
                if lfg_config.webhook_url and lfg_config.notify_on_group_create:
                    send_lfg_webhook_notification(lfg_config.webhook_url, embed_data)

            return JsonResponse({
                'success': True,
                'message': 'LFG group created! Bot will create a Discord thread shortly.',
                'group': {
                    'id': new_group.id,
                    'game_name': game.game_name,
                    'scheduled_time': new_group.scheduled_time,
                    'co_leaders': co_leaders_added,
                }
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating LFG group: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_member_auth_required
def api_lfg_browser_join(request, guild_id, group_id):
    """POST /api/guild/<id>/lfg/browser/<group_id>/join/ - Join LFG group (Pro/Premium/VIP)."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, LFGMember
        import time

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')
        username = discord_user.get('username', 'Unknown')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        # Parse request body for options
        data = json.loads(request.body) if request.body else {}
        options = data.get('options', {})

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get group
            group = db.query(LFGGroup).filter_by(id=int(group_id), guild_id=int(guild_id)).first()
            if not group:
                return JsonResponse({'error': 'Group not found'}, status=404)

            if not group.is_active:
                return JsonResponse({'error': 'Group is no longer active'}, status=400)

            if group.is_full:
                return JsonResponse({'error': 'Group is full'}, status=400)

            # Check if user has any existing member record (active or left)
            existing = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id)
            ).first()

            # Extract rank if provided
            rank_value = options.get('rank')

            # Extract other selections (exclude 'rank' as it's stored separately)
            selections = {k: v for k, v in options.items() if k != 'rank'}
            selections_json = json.dumps(selections) if selections else None

            if existing:
                # Check if they're currently in the group
                if existing.left_at is None:
                    return JsonResponse({'error': 'You are already in this group'}, status=400)

                # They left before, so rejoin them by updating their record
                existing.display_name = username
                existing.rank_value = rank_value
                existing.selections = selections_json
                existing.joined_at = int(time.time())
                existing.left_at = None  # Clear the left timestamp

                # Update group member count
                group.member_count += 1
                if group.member_count >= group.max_group_size:
                    group.is_full = True
            else:
                # Add new member
                new_member = LFGMember(
                    group_id=group.id,
                    user_id=int(user_id),
                    display_name=username,
                    is_creator=False,
                    rank_value=rank_value,
                    selections=selections_json,
                    joined_at=int(time.time())
                )
                db.add(new_member)

                # Update group member count
                group.member_count += 1
                if group.member_count >= group.max_group_size:
                    group.is_full = True

            # Get game info for notifications (before commit)
            from .models import LFGGame
            game = db.query(LFGGame).filter_by(id=group.game_id).first()

            # Auto-confirm attendance if attendance tracking is enabled (Pro/Premium/VIP only)
            from .models import LFGConfig
            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            is_attendance_tier = guild.subscription_tier in ['pro', 'Pro', 'premium', 'Premium'] or guild.is_vip
            if lfg_config and lfg_config.attendance_tracking_enabled and is_attendance_tier:
                from .models import LFGAttendance, AttendanceStatus

                # Check if user already has an attendance record
                attendance = db.query(LFGAttendance).filter_by(
                    group_id=group.id,
                    user_id=int(user_id)
                ).first()

                now = int(time.time())
                if not attendance:
                    # Create new attendance record with CONFIRMED status
                    attendance = LFGAttendance(
                        group_id=group.id,
                        user_id=int(user_id),
                        status=AttendanceStatus.CONFIRMED,
                        confirmed_at=now,
                        joined_at=now
                    )
                    db.add(attendance)
                else:
                    # Update existing record to CONFIRMED
                    attendance.status = AttendanceStatus.CONFIRMED
                    attendance.confirmed_at = now
                    if not attendance.joined_at:
                        attendance.joined_at = now

            db.commit()

            # Queue bot action to update thread embed and add user to thread
            from .models import PendingAction, ActionType, ActionStatus
            import logging
            logger = logging.getLogger(__name__)

            if lfg_config and group.thread_id:
                import time as time_lib

                action = PendingAction(
                    guild_id=int(guild_id),
                    action_type=ActionType.LFG_THREAD_UPDATE,
                    payload=json.dumps({
                        'group_id': group.id,
                        'add_user_to_thread': int(user_id),  # Add this user to the thread
                    }),
                    status=ActionStatus.PENDING,
                    priority=2,
                    created_at=int(time_lib.time())
                )
                db.add(action)
                db.commit()
                logger.info(f"Queued LFG thread update action for join: user {user_id} to group {group.id}")

            return JsonResponse({
                'success': True,
                'message': 'Successfully joined the group!',
                'member_count': group.member_count
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error joining LFG group: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["DELETE"])
@api_member_auth_required
def api_lfg_browser_leave(request, guild_id, group_id):
    """DELETE /api/guild/<id>/lfg/browser/<group_id>/leave/ - Leave LFG group (Pro/Premium/VIP)."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, LFGMember
        import time

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get group
            group = db.query(LFGGroup).filter_by(id=int(group_id), guild_id=int(guild_id)).first()
            if not group:
                return JsonResponse({'error': 'Group not found'}, status=404)

            # Find membership
            member = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id)
            ).filter(LFGMember.left_at == None).first()

            if not member:
                return JsonResponse({'error': 'You are not in this group'}, status=400)

            if member.is_creator:
                return JsonResponse({'error': 'Group creator cannot leave. Delete the group instead.'}, status=400)

            # Mark as left
            member.left_at = int(time.time())

            # Update group member count
            group.member_count = max(1, group.member_count - 1)
            group.is_full = False

            # Get game info for notifications (before commit)
            from .models import LFGGame
            game = db.query(LFGGame).filter_by(id=group.game_id).first()

            db.commit()

            # Queue bot action to update thread embed (user will be removed from embed automatically)
            from .models import LFGConfig, PendingAction, ActionType, ActionStatus
            import logging
            logger = logging.getLogger(__name__)

            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if lfg_config and group.thread_id:
                import time as time_lib

                action = PendingAction(
                    guild_id=int(guild_id),
                    action_type=ActionType.LFG_THREAD_UPDATE,
                    payload=json.dumps({
                        'group_id': group.id,
                    }),
                    status=ActionStatus.PENDING,
                    priority=2,
                    created_at=int(time_lib.time())
                )
                db.add(action)
                db.commit()
                logger.info(f"Queued LFG thread update action for leave: user {user_id} from group {group.id}")

            return JsonResponse({
                'success': True,
                'message': 'Successfully left the group',
                'member_count': group.member_count
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error leaving LFG group: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_member_auth_required
def api_lfg_browser_remove_member(request, guild_id, group_id):
    """POST /api/guild/<id>/lfg/browser/<group_id>/remove-member/ - Remove a member from LFG group (Creator/Co-Leader only)."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, LFGMember
        import time

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        data = json.loads(request.body)
        target_user_id = data.get('user_id')

        if not target_user_id:
            return JsonResponse({'error': 'user_id is required'}, status=400)

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get group
            group = db.query(LFGGroup).filter_by(id=int(group_id), guild_id=int(guild_id)).first()
            if not group:
                return JsonResponse({'error': 'Group not found'}, status=404)

            # Check permissions: only creator or co-leaders can remove members
            requester_member = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id)
            ).filter(LFGMember.left_at == None).first()

            is_creator = requester_member and requester_member.is_creator
            is_co_leader = requester_member and requester_member.is_co_leader

            if not (is_creator or is_co_leader):
                return JsonResponse({'error': 'Permission denied. Only the creator or co-leaders can remove members.'}, status=403)

            # Find target member
            target_member = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(target_user_id)
            ).filter(LFGMember.left_at == None).first()

            if not target_member:
                return JsonResponse({'error': 'Member not found in group'}, status=404)

            # Cannot remove the creator
            if target_member.is_creator:
                return JsonResponse({'error': 'Cannot remove the group creator'}, status=400)

            # Mark as left
            target_member.left_at = int(time.time())
            target_display_name = target_member.display_name or f"User {target_user_id}"

            # Update group member count
            group.member_count = max(1, group.member_count - 1)
            group.is_full = False

            db.commit()

            # Queue bot action to remove user from thread and update embed
            from .models import LFGConfig, PendingAction, ActionType, ActionStatus
            import logging
            logger = logging.getLogger(__name__)

            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if lfg_config and group.thread_id:
                import time as time_lib

                action = PendingAction(
                    guild_id=int(guild_id),
                    action_type=ActionType.LFG_THREAD_UPDATE,
                    payload=json.dumps({
                        'group_id': group.id,
                        'remove_users_from_thread': [int(target_user_id)],  # Remove from thread
                    }),
                    status=ActionStatus.PENDING,
                    priority=2,
                    created_at=int(time_lib.time())
                )
                db.add(action)
                db.commit()
                logger.info(f"Queued LFG thread update action to remove user {target_user_id} from group {group.id}")

            return JsonResponse({
                'success': True,
                'message': f'Removed {target_display_name} from the group',
                'member_count': group.member_count
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error removing member from LFG group: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["POST"])
@api_member_auth_required
def api_lfg_browser_join_thread(request, guild_id, group_id):
    """POST /api/guild/<id>/lfg/browser/<group_id>/join-thread/ - Add user to Discord thread."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, PendingAction, ActionType, ActionStatus
        import time
        import logging
        logger = logging.getLogger(__name__)

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get group
            group = db.query(LFGGroup).filter_by(id=int(group_id), guild_id=int(guild_id)).first()
            if not group:
                return JsonResponse({'error': 'Group not found'}, status=404)

            if not group.thread_id:
                return JsonResponse({'error': 'This group does not have a Discord thread'}, status=400)

            # Queue bot action to add user to thread
            action = PendingAction(
                guild_id=int(guild_id),
                action_type=ActionType.LFG_THREAD_UPDATE,
                payload=json.dumps({
                    'group_id': group.id,
                    'add_user_to_thread': int(user_id),
                }),
                status=ActionStatus.PENDING,
                priority=2,
                created_at=int(time.time())
            )
            db.add(action)
            db.commit()

            logger.info(f"Queued action to add user {user_id} to thread {group.thread_id}")

            return JsonResponse({
                'success': True,
                'message': 'You will be added to the Discord thread shortly'
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error joining thread: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["DELETE"])
@api_member_auth_required
def api_lfg_browser_delete(request, guild_id, group_id):
    """
    DELETE /api/guild/<id>/lfg/browser/<group_id>/delete/ - Delete LFG group.

    Permission hierarchy (any of these grants delete access):
    1. Group creator (always can delete their own group)
    2. Co-leaders (designated by creator)
    3. LFG Managers (users with "LFG Manager" Discord role with proper permissions)
    4. Server admins

    Returns:
        200: Group deleted successfully
        403: Permission denied
        404: Group not found
    """
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, LFGMember

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        # Check if user is server admin
        admin_guilds = request.session.get('admin_guilds', [])
        is_admin = str(guild_id) in [str(g['id']) for g in admin_guilds]

        # Check if user has "LFG Manager" role (users with this role can manage ANY group)
        has_lfg_manager_role = check_lfg_manager_role(guild_id, user_id)

        can_manage = is_admin or has_lfg_manager_role

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get group
            group = db.query(LFGGroup).filter_by(id=int(group_id), guild_id=int(guild_id)).first()
            if not group:
                return JsonResponse({'error': 'Group not found'}, status=404)

            # Check permissions: creator, co-leader, or admin
            is_creator = group.creator_id == int(user_id)

            # Check if user is a co-leader
            is_co_leader = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id),
                is_co_leader=True
            ).filter(LFGMember.left_at == None).first() is not None

            if not (is_creator or is_co_leader or can_manage):
                return JsonResponse({'error': 'Permission denied. Only the creator, co-leaders, admins, or users with the LFG Manager role can delete this group.'}, status=403)

            # Capture group info before deletion for audit log
            from .models import LFGGame, LFGConfig, PendingAction, ActionType, ActionStatus
            import logging
            logger = logging.getLogger(__name__)

            game = db.query(LFGGame).filter_by(id=group.game_id).first()
            group_name_snapshot = group.thread_name
            game_name_snapshot = game.game_name if game else 'Unknown'
            game_emoji = game.game_emoji if game else '🎮'
            thread_id_snapshot = group.thread_id

            # Log audit entry for group deletion
            log_lfg_audit(
                db=db,
                guild_id=guild_id,
                group_id=group.id,
                action='delete',
                actor_id=user_id,
                actor_name=discord_user.get('username', 'Unknown'),
                group_name=group_name_snapshot,
                game_name=game_name_snapshot
            )

            # Queue bot action to delete thread and send cancellation notice
            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if lfg_config and lfg_config.browser_notify_channel_id and lfg_config.notify_on_group_delete:
                import time as time_lib

                action = PendingAction(
                    guild_id=int(guild_id),
                    action_type=ActionType.LFG_THREAD_DELETE,
                    payload=json.dumps({
                        'group_id': group.id,
                        'thread_id': str(thread_id_snapshot) if thread_id_snapshot else None,
                        'thread_name': group_name_snapshot,
                        'game_name': game_name_snapshot,
                        'game_emoji': game_emoji,
                        'deleted_by_id': user_id,
                        'channel_id': str(lfg_config.browser_notify_channel_id)
                    }),
                    status=ActionStatus.PENDING,
                    priority=1,  # High priority
                    created_at=int(time_lib.time())
                )
                db.add(action)
                db.commit()  # Commit action BEFORE deleting group so bot can process it
                logger.info(f"Queued LFG thread deletion action for group {group.id}")

            # Delete all members first
            db.query(LFGMember).filter_by(group_id=group.id).delete()

            # Delete the group
            db.delete(group)
            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Group deleted successfully'
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error deleting LFG group: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["PUT", "PATCH"])
@api_member_auth_required
def api_lfg_browser_update(request, guild_id, group_id):
    """
    PUT/PATCH /api/guild/<id>/lfg/browser/<group_id>/update/ - Update LFG group.

    Permission hierarchy (any of these grants edit access):
    1. Group creator (always can edit their own group)
    2. Co-leaders (designated by creator)
    3. LFG Managers (users with "LFG Manager" Discord role with proper permissions)
    4. Server admins

    Updatable fields:
    - description: Group description/notes
    - scheduled_time: Unix timestamp of when group is scheduled
    - max_group_size: Maximum number of members
    - co_leader_ids: List of user IDs to designate as co-leaders

    Returns:
        200: Group updated successfully with updated group data
        403: Permission denied
        404: Group not found
    """
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, LFGMember
        import time

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        # Check if user is server admin
        admin_guilds = request.session.get('admin_guilds', [])
        is_admin = str(guild_id) in [str(g['id']) for g in admin_guilds]

        # Check if user has "LFG Manager" role (users with this role can manage ANY group)
        has_lfg_manager_role = check_lfg_manager_role(guild_id, user_id)

        can_manage = is_admin or has_lfg_manager_role

        data = json.loads(request.body)
        description = data.get('description')
        scheduled_time = data.get('scheduled_time')
        max_group_size = data.get('max_group_size')
        co_leader_ids = data.get('co_leader_ids')

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get group
            group = db.query(LFGGroup).filter_by(id=int(group_id), guild_id=int(guild_id)).first()
            if not group:
                return JsonResponse({'error': 'Group not found'}, status=404)

            # Check permissions: creator, co-leader, or admin
            is_creator = group.creator_id == int(user_id)

            # Check if user is a co-leader
            is_co_leader = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id),
                is_co_leader=True
            ).filter(LFGMember.left_at == None).first() is not None

            if not (is_creator or is_co_leader or can_manage):
                return JsonResponse({'error': 'Permission denied. Only the creator, co-leaders, admins, or users with the LFG Manager role can update this group.'}, status=403)

            # Get game info for audit log
            from .models import LFGGame
            game = db.query(LFGGame).filter_by(id=group.game_id).first()
            group_name_snapshot = group.thread_name
            game_name_snapshot = game.game_name if game else 'Unknown'
            actor_name = discord_user.get('username', 'Unknown')

            # Update fields if provided and log changes
            if description is not None and group.description != description:
                log_lfg_audit(
                    db=db, guild_id=guild_id, group_id=group.id, action='update',
                    actor_id=user_id, actor_name=actor_name,
                    field_changed='description',
                    old_value=group.description, new_value=description,
                    group_name=group_name_snapshot, game_name=game_name_snapshot
                )
                group.description = description

            if scheduled_time is not None and group.scheduled_time != scheduled_time:
                log_lfg_audit(
                    db=db, guild_id=guild_id, group_id=group.id, action='update',
                    actor_id=user_id, actor_name=actor_name,
                    field_changed='scheduled_time',
                    old_value=str(group.scheduled_time), new_value=str(scheduled_time),
                    group_name=group_name_snapshot, game_name=game_name_snapshot
                )
                group.scheduled_time = scheduled_time

            if max_group_size is not None and group.max_group_size != max_group_size:
                log_lfg_audit(
                    db=db, guild_id=guild_id, group_id=group.id, action='update',
                    actor_id=user_id, actor_name=actor_name,
                    field_changed='max_group_size',
                    old_value=str(group.max_group_size), new_value=str(max_group_size),
                    group_name=group_name_snapshot, game_name=game_name_snapshot
                )
                group.max_group_size = max_group_size
                # Update is_full status based on new size
                group.is_full = group.member_count >= max_group_size

            # Track removed co-leaders for thread management
            removed_co_leader_ids = []

            # Update co-leaders if provided (only allow creator to modify co-leaders)
            if co_leader_ids is not None and is_creator:
                # Get existing co-leaders before removing them
                existing_co_leaders = db.query(LFGMember).filter_by(
                    group_id=group.id,
                    is_co_leader=True
                ).filter(LFGMember.left_at == None).all()

                # Track which co-leaders are being removed
                existing_co_leader_ids = [co.user_id for co in existing_co_leaders]
                new_co_leader_ids = [int(cid) for cid in co_leader_ids]
                removed_co_leader_ids = [cid for cid in existing_co_leader_ids if cid not in new_co_leader_ids and cid != group.creator_id]

                for co_leader in existing_co_leaders:
                    # Remove co-leader status
                    db.delete(co_leader)
                    group.member_count = max(1, group.member_count - 1)

                # Add new co-leaders
                for co_leader_id in co_leader_ids:
                    # Skip if co-leader is the creator themselves
                    if str(co_leader_id) == str(group.creator_id):
                        continue

                    # Check if they're already a regular member
                    existing_member = db.query(LFGMember).filter_by(
                        group_id=group.id,
                        user_id=int(co_leader_id)
                    ).filter(LFGMember.left_at == None).first()

                    if existing_member:
                        # Promote to co-leader
                        existing_member.is_co_leader = True
                    else:
                        # Fetch display name from GuildMember table
                        from .models import GuildMember as GuildMemberModel
                        guild_member = db.query(GuildMemberModel).filter_by(
                            guild_id=int(guild_id),
                            user_id=int(co_leader_id)
                        ).first()
                        co_leader_display_name = guild_member.display_name if guild_member else f'User {co_leader_id}'

                        # Add as new co-leader member
                        new_co_leader = LFGMember(
                            group_id=group.id,
                            user_id=int(co_leader_id),
                            display_name=co_leader_display_name,
                            is_co_leader=True,
                            joined_at=int(time.time())
                        )
                        db.add(new_co_leader)
                        group.member_count += 1

            # Update game-specific options if provided
            leader_options = data.get('leader_options')
            if leader_options:
                # Find the current user's member record
                current_user_member = db.query(LFGMember).filter_by(
                    group_id=group.id,
                    user_id=int(user_id)
                ).filter(LFGMember.left_at == None).first()

                if current_user_member:
                    # Extract rank and selections
                    rank_value = leader_options.get('rank') if leader_options else None
                    selections_dict = {k: v for k, v in leader_options.items() if k != 'rank'} if leader_options else {}

                    # Separate Activity (group-level) from personal options (Class, Spec, etc.)
                    activity_value = selections_dict.pop('Activity', None)

                    # Update current user's personal selections (Class, Spec, etc.)
                    current_user_member.rank_value = rank_value
                    current_user_member.selections = json_lib.dumps(selections_dict) if selections_dict else None

                    # Update Activity on the leader's record (group-level setting)
                    # This allows co-leaders to modify the group's activities
                    if activity_value is not None:
                        leader_member = db.query(LFGMember).filter_by(
                            group_id=group.id,
                            is_creator=True
                        ).filter(LFGMember.left_at == None).first()

                        if leader_member:
                            # Get leader's current selections
                            leader_selections = json_lib.loads(leader_member.selections) if leader_member.selections else {}
                            # Update Activity
                            leader_selections['Activity'] = activity_value
                            # Save back to leader
                            leader_member.selections = json_lib.dumps(leader_selections)

            db.commit()

            # Queue bot action to update the thread embed
            from .models import LFGConfig, PendingAction, ActionType, ActionStatus
            import logging
            logger = logging.getLogger(__name__)

            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if lfg_config and lfg_config.browser_notify_channel_id and lfg_config.notify_on_group_update:
                import time as time_lib

                action = PendingAction(
                    guild_id=int(guild_id),
                    action_type=ActionType.LFG_THREAD_UPDATE,
                    payload=json.dumps({
                        'group_id': group.id,
                        'remove_users_from_thread': removed_co_leader_ids,  # Remove ex-co-leaders from thread
                    }),
                    status=ActionStatus.PENDING,
                    priority=2,  # Medium priority
                    created_at=int(time_lib.time())
                )
                db.add(action)
                logger.info(f"Queued LFG thread update action for group {group.id}, removing {len(removed_co_leader_ids)} users from thread")

            return JsonResponse({
                'success': True,
                'message': 'Group updated successfully',
                'group': {
                    'id': group.id,
                    'description': group.description,
                    'scheduled_time': group.scheduled_time,
                    'max_group_size': group.max_group_size,
                    'member_count': group.member_count,
                }
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating LFG group: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET"])
@api_member_auth_required
def api_lfg_browser_audit_logs(request, guild_id):
    """
    GET /api/guild/<id>/lfg/browser/audit-logs/ - Get audit logs for LFG groups.

    Query parameters:
    - group_id (optional): Filter logs for specific group
    - limit (optional): Number of logs to return (default 50, max 200)
    - offset (optional): Pagination offset

    Access: Admins and LFG Managers only

    Returns:
        JSON with audit log entries including actor, action, changes, and timestamps
    """
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroupAuditLog

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        # Check if user is admin or LFG Manager
        admin_guilds = request.session.get('discord_admin_guilds', [])
        is_admin = any(str(g['id']) == str(guild_id) for g in admin_guilds)
        has_lfg_manager_role = check_lfg_manager_role(guild_id, user_id)

        if not (is_admin or has_lfg_manager_role):
            return JsonResponse({'error': 'Permission denied. Only admins and LFG Managers can view audit logs.'}, status=403)

        # Get query parameters
        group_id_filter = request.GET.get('group_id')
        limit = min(int(request.GET.get('limit', 50)), 200)
        offset = int(request.GET.get('offset', 0))

        with get_db_session() as db:
            # Check if guild exists
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Build query
            query = db.query(LFGGroupAuditLog).filter_by(guild_id=int(guild_id))

            if group_id_filter:
                query = query.filter_by(group_id=int(group_id_filter))

            # Order by most recent first
            query = query.order_by(LFGGroupAuditLog.created_at.desc())

            # Get total count
            total_count = query.count()

            # Apply pagination
            logs = query.offset(offset).limit(limit).all()

            # Format logs for response
            logs_data = []
            for log in logs:
                from datetime import datetime
                logs_data.append({
                    'id': log.id,
                    'group_id': log.group_id,
                    'action': log.action,
                    'actor_id': log.actor_id,
                    'actor_name': log.actor_name,
                    'field_changed': log.field_changed,
                    'old_value': log.old_value,
                    'new_value': log.new_value,
                    'group_name': log.group_name,
                    'game_name': log.game_name,
                    'created_at': log.created_at,
                    'created_at_formatted': datetime.fromtimestamp(log.created_at).strftime('%Y-%m-%d %H:%M:%S') if log.created_at else None
                })

            return JsonResponse({
                'success': True,
                'logs': logs_data,
                'total_count': total_count,
                'limit': limit,
                'offset': offset
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching audit logs: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["PATCH"])
@api_member_auth_required
def api_lfg_browser_update_class(request, guild_id, group_id):
    """PATCH /api/guild/<id>/lfg/browser/<group_id>/update-class/ - Update member's class/role selections."""
    try:
        from .db import get_db_session
        from .models import Guild, LFGGroup, LFGMember
        import time

        # Get Discord user from session
        discord_user = request.session.get('discord_user', {})
        user_id = discord_user.get('id')

        if not user_id:
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        data = json.loads(request.body)
        options = data.get('options', {})

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get group
            group = db.query(LFGGroup).filter_by(id=int(group_id), guild_id=int(guild_id)).first()
            if not group:
                return JsonResponse({'error': 'Group not found'}, status=404)

            # Find member
            member = db.query(LFGMember).filter_by(
                group_id=group.id,
                user_id=int(user_id)
            ).filter(LFGMember.left_at == None).first()

            if not member:
                return JsonResponse({'error': 'You are not in this group'}, status=400)

            # Extract rank and selections
            rank_value = options.get('rank')
            selections = {k: v for k, v in options.items() if k != 'rank'}
            selections_json = json_lib.dumps(selections) if selections else None

            # Update member's selections
            member.rank_value = rank_value
            member.selections = selections_json

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Class updated successfully'
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating member class: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


@require_http_methods(["GET", "POST"])
@discord_required
def api_lfg_browser_notifications(request, guild_id):
    """
    GET/POST /api/guild/<id>/lfg/browser-notifications/ - Get or save LFG Browser notification settings.

    Pro/Premium/VIP only feature.

    GET Returns:
        200: Current notification settings
        403: Not Pro/Premium/VIP or not admin

    POST Payload:
        browser_notify_channel_id: Channel ID for announcements (optional)
        notify_on_group_create: Announce new groups (bool)
        notify_on_group_update: Announce group updates (bool)
        notify_on_group_delete: Announce group deletions (bool)
        notify_on_member_join: Announce member joins (bool)
        notify_on_member_leave: Announce member leaves (bool)
        dm_members_on_update: DM members on group update (bool)
        dm_members_on_delete: DM members on group deletion (bool)
        webhook_url: Optional webhook URL for custom integrations

    POST Returns:
        200: Settings saved successfully
        403: Not Pro/Premium/VIP or not admin
    """
    try:
        from .db import get_db_session
        from .models import Guild, LFGConfig

        # Verify admin permission
        admin_guilds = request.session.get('discord_admin_guilds', [])
        is_admin = str(guild_id) in [str(g['id']) for g in admin_guilds]

        if not is_admin:
            return JsonResponse({'error': 'Admin permission required'}, status=403)

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # GET: Return current settings
            if request.method == 'GET':
                lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
                if not lfg_config:
                    # Return default settings
                    return JsonResponse({
                        'browser_notify_channel_id': None,
                        'notify_on_group_create': True,
                        'notify_on_group_update': False,
                        'notify_on_group_delete': False,
                        'notify_on_member_join': False,
                        'notify_on_member_leave': False,
                        'webhook_url': None
                    })

                return JsonResponse({
                    'browser_notify_channel_id': str(lfg_config.browser_notify_channel_id) if lfg_config.browser_notify_channel_id else None,
                    'notify_on_group_create': lfg_config.notify_on_group_create,
                    'notify_on_group_update': lfg_config.notify_on_group_update,
                    'notify_on_group_delete': lfg_config.notify_on_group_delete,
                    'notify_on_member_join': lfg_config.notify_on_member_join,
                    'notify_on_member_leave': lfg_config.notify_on_member_leave,
                    'webhook_url': lfg_config.webhook_url or ''
                })

        # POST: Save settings
        data = json.loads(request.body)

        with get_db_session() as db:
            # Get guild
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return JsonResponse({'error': 'Guild not found'}, status=404)

            # Get or create LFG config
            lfg_config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            if not lfg_config:
                lfg_config = LFGConfig(guild_id=int(guild_id))
                db.add(lfg_config)

            # Update notification settings
            lfg_config.browser_notify_channel_id = int(data.get('browser_notify_channel_id')) if data.get('browser_notify_channel_id') else None
            lfg_config.notify_on_group_create = data.get('notify_on_group_create', True)
            lfg_config.notify_on_group_update = data.get('notify_on_group_update', False)
            lfg_config.notify_on_group_delete = data.get('notify_on_group_delete', False)
            lfg_config.notify_on_member_join = data.get('notify_on_member_join', False)
            lfg_config.notify_on_member_leave = data.get('notify_on_member_leave', False)
            lfg_config.dm_members_on_update = data.get('dm_members_on_update', True)
            lfg_config.dm_members_on_delete = data.get('dm_members_on_delete', True)
            lfg_config.webhook_url = data.get('webhook_url')

            db.commit()

            return JsonResponse({
                'success': True,
                'message': 'Browser notification settings saved successfully'
            })

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error saving LFG Browser notification settings: {e}", exc_info=True)
        return JsonResponse({'error': 'An internal error occurred. Please try again later.'}, status=500)


# Bot Installation Callback
def bot_install_callback(request):
    """
    Handle bot installation callback from Discord.
    After user authorizes the bot, Discord redirects here.
    """
    # Get parameters from Discord
    guild_id = request.GET.get('guild_id')
    permissions = request.GET.get('permissions')
    error = request.GET.get('error')
    error_description = request.GET.get('error_description')

    # Handle authorization errors
    if error:
        messages.error(request, f'Bot authorization failed: {error_description or error}')
        return redirect('home')

    # Check if guild_id was provided
    if not guild_id:
        messages.warning(request, 'No server selected. Please try adding the bot again.')
        return redirect('home')

    try:
        from .db import get_db_session
        from .models import Guild as DBGuild

        # Check if guild exists in database
        with get_db_session() as db:
            guild_db = db.query(DBGuild).filter_by(guild_id=int(guild_id)).first()

            context = {
                'guild_id': guild_id,
                'guild_name': guild_db.guild_name if guild_db else 'Your Server',
                'bot_name': 'Wardenbot',
                'permissions': permissions,
                'is_premium': guild_db.is_premium() if guild_db else False,
            }

        messages.success(request, f'Wardenbot has been successfully added to your server!')
        return render(request, 'questlog/bot_install_success.html', context)

    except Exception as e:
        logger.error(f"Error in bot install callback: {e}", exc_info=True)
        messages.error(request, 'An error occurred. The bot should still be installed.')
        return redirect('home')


# ============================================================================
# FEATURED CREATORS - Hall of Fame
# ============================================================================

def guild_featured_creators(request, guild_id):
    """
    Featured Creators hall of fame page - PUBLIC (no login required).

    Anyone can view featured creators to discover content creators.
    Admin features (Discovery settings) still require authentication.
    """
    from .module_utils import has_module_access, has_any_module_access
    import logging
    logger = logging.getLogger(__name__)

    # Check if user is authenticated (optional for public view)
    all_guilds = request.session.get('discord_all_guilds', [])
    admin_guilds = request.session.get('discord_admin_guilds', [])
    is_authenticated = bool(request.session.get('discord_user'))

    # Try to get guild from session if authenticated
    guild_from_session = next((g for g in all_guilds if str(g.get('id')) == str(guild_id)), None)

    # Check if user is admin (only if authenticated)
    is_admin = is_authenticated and any(str(g.get('id')) == str(guild_id) for g in admin_guilds)
    show_admin_view = is_admin  # For template clarity

    try:
        from .db import get_db_session
        from .models import Guild as DBGuild, FeaturedCreator, DiscoveryConfig

        with get_db_session() as db:
            guild_db = db.query(DBGuild).filter_by(guild_id=int(guild_id)).first()

            if not guild_db:
                logger.warning(f"Featured Creators: Guild {guild_id} not found in database")
                messages.error(request, "Guild not found.")
                return redirect('home')

            # Build guild object for template (from DB or session)
            if guild_from_session:
                # Use session data if available (has icon, name, etc.)
                guild = guild_from_session
            else:
                # Build minimal guild object from database for public view
                guild = {
                    'id': str(guild_db.guild_id),
                    'name': guild_db.guild_name or f"Guild {guild_db.guild_id}",
                    'icon': None,  # We don't store icon in DB
                }

            # Get Discovery config to check if enabled
            discovery_config = db.query(DiscoveryConfig).filter_by(guild_id=int(guild_id)).first()
            discovery_enabled = discovery_config.enabled if discovery_config else False
            selfpromo_channel_id = discovery_config.selfpromo_channel_id if discovery_config else None

            # Get all active featured creators (global model - one per user)
            # Filter for those in this guild with active forum threads
            all_creators = db.query(FeaturedCreator).filter(
                FeaturedCreator.is_active == True,
                FeaturedCreator.source == 'forum',
                FeaturedCreator.forum_thread_id != None  # Only show if forum thread exists
            ).order_by(FeaturedCreator.last_featured_at.desc()).all()

            # Filter for creators who are in this guild
            import json
            creators = []
            for creator in all_creators:
                try:
                    guilds_list = json.loads(creator.guilds) if creator.guilds else []
                    if int(guild_id) in guilds_list:
                        creators.append(creator)
                except:
                    pass

            creators_data = []
            for creator in creators:
                # Get member XP data (level and flair)
                from .models import GuildMember
                member_data = db.query(GuildMember).filter_by(
                    guild_id=int(guild_id),
                    user_id=creator.user_id
                ).first()

                member_level = member_data.level if member_data else 0
                member_flair = member_data.flair if member_data else None

                # Parse Discord connections if available
                connections = {}
                if creator.discord_connections:
                    try:
                        connections = json.loads(creator.discord_connections)
                    except:
                        pass

                # Extract URLs from bio
                import re
                import html
                extracted_links = []
                clean_bio = creator.bio
                shown_platforms = set()  # Track platforms to avoid duplicates
                social_media_urls = []  # URLs to remove from bio

                if creator.bio:
                    url_pattern = r'https?://[^\s<>"\']+'
                    urls = re.findall(url_pattern, creator.bio)
                    for full_url in urls:
                        url_lower = full_url.lower()
                        platform_name = None
                        icon = None
                        color = None
                        is_social_media = False

                        if 'twitch.tv' in url_lower:
                            platform_name = 'Twitch'
                            icon = 'fab fa-twitch'
                            color = 'purple'
                            is_social_media = True
                        elif 'youtube.com' in url_lower or 'youtu.be' in url_lower:
                            platform_name = 'YouTube'
                            icon = 'fab fa-youtube'
                            color = 'red'
                            is_social_media = True
                        elif 'twitter.com' in url_lower or 'x.com' in url_lower:
                            platform_name = 'Twitter'
                            icon = 'fab fa-twitter'
                            color = 'sky'
                            is_social_media = True
                        elif 'tiktok.com' in url_lower:
                            platform_name = 'TikTok'
                            icon = 'fab fa-tiktok'
                            color = 'black'
                            is_social_media = True
                        elif 'instagram.com' in url_lower:
                            platform_name = 'Instagram'
                            icon = 'fab fa-instagram'
                            color = 'pink'
                            is_social_media = True
                        elif 'bsky.app' in url_lower:
                            platform_name = 'Bluesky'
                            icon = 'fab fa-bluesky'
                            color = 'teal'
                            is_social_media = True
                        elif 'facebook.com' in url_lower or 'fb.com' in url_lower:
                            platform_name = 'Facebook'
                            icon = 'fab fa-facebook'
                            color = 'blue'
                            is_social_media = True
                        elif 'kick.com' in url_lower:
                            platform_name = 'Kick'
                            icon = 'fas fa-video'
                            color = 'green'
                            is_social_media = True

                        if is_social_media:
                            extracted_links.append({
                                'url': full_url,
                                'platform': platform_name,
                                'icon': icon,
                                'color': color
                            })
                            shown_platforms.add(platform_name.lower())
                            social_media_urls.append(full_url)

                    # Convert Discord markdown to HTML while removing social media URLs
                    def discord_markdown_to_html(text):
                        # First, remove ONLY social media URLs
                        for url in social_media_urls:
                            text = text.replace(url, '')

                        # Escape HTML to prevent XSS
                        text = html.escape(text)

                        # Convert Discord markdown to HTML
                        # Bold: **text**
                        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
                        # Italic: *text* (but not ** which is already processed)
                        text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
                        # Underline: __text__
                        text = re.sub(r'__(.+?)__', r'<u>\1</u>', text)
                        # Strikethrough: ~~text~~
                        text = re.sub(r'~~(.+?)~~', r'<del>\1</del>', text)

                        # Convert remaining URLs to clickable links (these are NOT social media)
                        # Match URLs that weren't removed
                        text = re.sub(
                            r'(https?://[^\s<>&quot;]+)',
                            r'<a href="\1" target="_blank" rel="noopener noreferrer" class="text-blue-400 hover:text-blue-300 underline">\1</a>',
                            text
                        )

                        # Convert line breaks to <br> tags
                        text = text.replace('\n', '<br>')

                        return text

                    clean_bio = discord_markdown_to_html(clean_bio) if clean_bio else ''

                # SECURITY: Sanitize HTML to prevent XSS attacks
                import bleach
                ALLOWED_TAGS = ['b', 'i', 'u', 'strong', 'em', 'br', 'p', 'a', 'ul', 'ol', 'li', 'code', 'pre']
                ALLOWED_ATTRS = {'a': ['href', 'title', 'target', 'rel']}
                clean_bio = bleach.clean(
                    clean_bio,
                    tags=ALLOWED_TAGS,
                    attributes=ALLOWED_ATTRS,
                    strip=True
                ) if clean_bio else ''

                # Only include direct URLs if not already in bio links
                show_twitch = creator.twitch_url and 'twitch' not in shown_platforms
                show_youtube = creator.youtube_url and 'youtube' not in shown_platforms
                show_twitter = creator.twitter_url and 'twitter' not in shown_platforms
                show_tiktok = creator.tiktok_url and 'tiktok' not in shown_platforms
                show_instagram = creator.instagram_url and 'instagram' not in shown_platforms
                show_bsky = creator.bsky_url and 'bsky' not in shown_platforms

                if show_twitch:
                    shown_platforms.add('twitch')
                if show_youtube:
                    shown_platforms.add('youtube')
                if show_twitter:
                    shown_platforms.add('twitter')
                if show_tiktok:
                    shown_platforms.add('tiktok')
                if show_instagram:
                    shown_platforms.add('instagram')
                if show_bsky:
                    shown_platforms.add('bksy')

                # Filter discord connections to avoid duplicates
                filtered_connections = {}
                if connections:
                    for conn_type, conn_data in connections.items():
                        if conn_type not in shown_platforms:
                            filtered_connections[conn_type] = conn_data

                creators_data.append({
                    'user_id': creator.user_id,
                    'username': creator.username,
                    'display_name': creator.display_name,
                    'avatar_url': creator.avatar_url,
                    'bio': creator.bio,
                    'clean_bio': clean_bio,
                    'extracted_bio_links': extracted_links,
                    'times_featured': creator.times_featured_total,
                    'first_featured_at': creator.first_featured_at,
                    'last_featured_at': creator.last_featured_at,
                    'level': member_level,
                    'flair': member_flair,
                    'show_twitch': show_twitch,
                    'show_youtube': show_youtube,
                    'show_twitter': show_twitter,
                    'show_tiktok': show_tiktok,
                    'show_instagram': show_instagram,
                    'show_bsky': show_bsky,
                    'twitch_url': creator.twitch_url,
                    'youtube_url': creator.youtube_url,
                    'twitter_url': creator.twitter_url,
                    'tiktok_url': creator.tiktok_url,
                    'instagram_url': creator.instagram_url,
                    'bsky_url': creator.bsky_url,
                    'discord_connections': filtered_connections,
                    'forum_thread_id': creator.forum_thread_id,  # For clickable Discord links
                })

        # Check if guild has discovery module access
        has_discovery_module = has_module_access(guild_id, 'discovery')
        has_any_module = has_any_module_access(guild_id)

        return render(request, 'questlog/featured_creators.html', {
            'guild': guild,
            'guild_record': guild_db,
            'creators': creators_data,
            'total_creators': len(creators_data),
            'is_admin': is_admin,
            'show_admin_view': show_admin_view,
            'discovery_enabled': discovery_enabled,
            'selfpromo_channel_id': selfpromo_channel_id,
            'has_discovery_module': has_discovery_module,
            'has_any_module': has_any_module,
            'admin_guilds': admin_guilds,
        'member_guilds': get_member_guilds(request),
            'active_page': 'featured_creators',
        })

    except Exception as e:
        logger.error(f"Error loading featured creators: {e}", exc_info=True)
        messages.error(request, f'Error loading featured creators: {e}')
        return redirect('home')

def guild_cotw(request, guild_id):
    """Guild-specific Creator of the Week page (placeholder)."""
    # Redirect to global COTW page for now
    return redirect('creator_of_the_week')

def guild_cotm(request, guild_id):
    """Guild-specific Creator of the Month page (placeholder)."""
    # Redirect to global COTM page for now
    return redirect('creator_of_the_month')


def robots_txt(request):
    """Serve robots.txt with proper headers for social media and search engine crawlers."""
    from django.http import HttpResponse

    robots_content = """# Casual Heroes - robots.txt

# Allow social media crawlers (Discord, LinkedIn, Twitter, Facebook, etc.)
User-agent: Twitterbot
Allow: /

User-agent: facebookexternalhit
Allow: /

User-agent: LinkedInBot
Allow: /

User-agent: Discordbot
Allow: /

User-agent: Slackbot
Allow: /

User-agent: TelegramBot
Allow: /

# Allow search engines
User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /

# Block AI scrapers
User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: Claude-Web
Disallow: /

User-agent: cohere-ai
Disallow: /

# Default: Allow everything else except API endpoints
User-agent: *
Allow: /
Disallow: /api/admin/
Disallow: /admin/

Sitemap: https://dashboard.casual-heroes.com/sitemap.xml
"""

    return HttpResponse(robots_content, content_type='text/plain')
