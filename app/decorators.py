"""
Custom decorators for Warden web application.
Includes authentication, authorization, and subscription tier validation.
"""

from functools import wraps
from django.http import JsonResponse
import logging

logger = logging.getLogger(__name__)


def require_subscription_tier(*required_tiers):
    """
    Decorator to enforce subscription tier requirements on API endpoints.

    Usage:
        @require_subscription_tier('pro', 'premium')
        def my_premium_feature(request, guild_id):
            # Only accessible to Pro/Premium/VIP guilds
            ...

    Args:
        *required_tiers: Variable number of tier names ('free', 'pro', 'premium')

    Returns:
        403 error if guild doesn't meet tier requirements
        404 error if guild doesn't exist

    Note:
        VIP guilds bypass all tier checks (is_vip=True overrides tier requirement)
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, guild_id, *args, **kwargs):
            from .db import get_db_session
            from .models import Guild

            try:
                with get_db_session() as db:
                    guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()

                    if not guild:
                        logger.warning(f"Tier check failed: Guild {guild_id} not found")
                        return JsonResponse({'error': 'Guild not found'}, status=404)

                    # VIP guilds bypass all tier requirements
                    if guild.is_vip:
                        logger.debug(f"VIP guild {guild_id} bypassed tier check for {view_func.__name__}")
                        return view_func(request, guild_id, *args, **kwargs)

                    # Check if guild's tier matches any of the required tiers
                    guild_tier = guild.subscription_tier.lower() if guild.subscription_tier else 'free'

                    if guild_tier in [tier.lower() for tier in required_tiers]:
                        return view_func(request, guild_id, *args, **kwargs)

                    # Check if required tier is pro/premium and guild has Engagement Module
                    # Engagement Module grants access to all pro/premium XP and leveling features
                    if any(tier.lower() in ['pro', 'premium'] for tier in required_tiers):
                        from .module_utils import has_module_access
                        if has_module_access(guild_id, 'engagement'):
                            logger.debug(f"Guild {guild_id} granted access to {view_func.__name__} via Engagement Module")
                            return view_func(request, guild_id, *args, **kwargs)

                    # Tier requirement not met
                    logger.warning(
                        f"Tier check failed: Guild {guild_id} (tier: {guild_tier}) "
                        f"attempted to access {view_func.__name__} (requires: {'/'.join(required_tiers)})"
                    )

                    return JsonResponse({
                        'error': f'This feature requires {" or ".join(required_tiers).title()} subscription',
                        'current_tier': guild_tier,
                        'required_tiers': list(required_tiers),
                        'upgrade_url': f'/questlog/guild/{guild_id}/billing'
                    }, status=403)

            except Exception as e:
                logger.error(f"Error in tier validation for guild {guild_id}: {e}", exc_info=True)
                return JsonResponse({'error': 'An internal error occurred'}, status=500)

        return wrapped
    return decorator


def require_module_access(module_name):
    """
    Decorator to enforce modular subscription access (for specific premium modules).

    Usage:
        @require_module_access('advanced_analytics')
        def my_analytics_feature(request, guild_id):
            # Only accessible if guild has 'advanced_analytics' module enabled
            ...

    Args:
        module_name: Name of the required module (from guild_modules table)

    Returns:
        403 error if guild doesn't have the module enabled
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, guild_id, *args, **kwargs):
            from .db import get_db_session
            from .models import GuildModule

            try:
                with get_db_session() as db:
                    # Check if guild has this module enabled
                    module = db.query(GuildModule).filter_by(
                        guild_id=int(guild_id),
                        module_name=module_name,
                        enabled=True
                    ).first()

                    if module:
                        return view_func(request, guild_id, *args, **kwargs)

                    logger.warning(
                        f"Module check failed: Guild {guild_id} attempted to access {view_func.__name__} "
                        f"(requires module: {module_name})"
                    )

                    return JsonResponse({
                        'error': f'This feature requires the {module_name} module',
                        'module_name': module_name,
                        'upgrade_url': f'/questlog/guild/{guild_id}/billing'
                    }, status=403)

            except Exception as e:
                logger.error(f"Error in module validation for guild {guild_id}: {e}", exc_info=True)
                return JsonResponse({'error': 'An internal error occurred'}, status=500)

        return wrapped
    return decorator


def validate_json_schema(schema):
    """
    Decorator to validate JSON request body against a schema.

    Usage:
        from .decorators import validate_json_schema

        XP_UPDATE_SCHEMA = {
            "type": "object",
            "properties": {
                "xp": {"type": "integer", "minimum": -10000, "maximum": 1000000},
                "reason": {"type": "string", "maxLength": 500}
            },
            "required": ["xp"]
        }

        @validate_json_schema(XP_UPDATE_SCHEMA)
        def api_update_xp(request, guild_id, user_id):
            data = request.validated_data  # Already validated!
            ...

    Args:
        schema: JSON Schema dict following jsonschema specification

    Returns:
        400 error if validation fails
        Adds `request.validated_data` with validated JSON
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            import json
            try:
                import jsonschema
            except ImportError:
                logger.error("jsonschema library not installed. Run: pip install jsonschema")
                return JsonResponse({'error': 'Server configuration error'}, status=500)

            # Parse JSON body
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid JSON in request: {e}")
                return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)

            # Validate against schema
            try:
                jsonschema.validate(instance=data, schema=schema)
            except jsonschema.ValidationError as e:
                logger.warning(f"JSON validation failed: {e.message}")
                return JsonResponse({
                    'error': 'Validation error',
                    'message': e.message,
                    'field': list(e.absolute_path) if e.absolute_path else None
                }, status=400)

            # Add validated data to request object
            request.validated_data = data
            return view_func(request, *args, **kwargs)

        return wrapped
    return decorator


def log_security_event(event_type):
    """
    Decorator to log security-sensitive operations.

    Usage:
        @log_security_event('BULK_XP_IMPORT')
        def api_bulk_import_xp(request, guild_id):
            # Automatically logs this operation
            ...

    Args:
        event_type: String describing the security event (e.g., 'MANUAL_BAN', 'BULK_IMPORT')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user_id = request.session.get('discord_user', {}).get('id', 'unknown')
            guild_id = kwargs.get('guild_id', 'unknown')

            logger.warning(
                f"[SECURITY] {event_type} | User: {user_id} | Guild: {guild_id} | View: {view_func.__name__}",
                extra={
                    'user_id': user_id,
                    'guild_id': guild_id,
                    'event_type': event_type,
                    'view_name': view_func.__name__
                }
            )

            return view_func(request, *args, **kwargs)

        return wrapped
    return decorator


def bot_owner_required(view_func):
    """
    Decorator to restrict access to bot owner only.

    Usage:
        @bot_owner_required
        def api_admin_endpoint(request):
            # Only bot owner can access this
            ...

    Returns:
        401 error if user is not authenticated
        403 error if user is not the bot owner
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        import os

        # Check if user is authenticated
        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            logger.warning(
                f"[SECURITY] Bot owner check failed: No Discord session | "
                f"View: {view_func.__name__} | "
                f"IP: {request.META.get('REMOTE_ADDR')}"
            )
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        # Check if user is bot owner
        bot_owner_id = os.getenv('BOT_OWNER_ID')

        if str(user_id) != str(bot_owner_id):
            logger.warning(
                f"[SECURITY] Bot owner check failed: User {user_id} is not bot owner | "
                f"View: {view_func.__name__} | "
                f"IP: {request.META.get('REMOTE_ADDR')}"
            )
            return JsonResponse({
                'success': False,
                'error': 'Unauthorized - Bot owner only'
            }, status=403)

        logger.debug(f"Bot owner {user_id} accessed {view_func.__name__}")
        return view_func(request, *args, **kwargs)

    return wrapper


def server_owner_required(view_func):
    """
    Decorator to restrict access to Discord server owner ONLY.

    Use this for critical actions like:
    - Billing & Subscriptions
    - Leaving Discovery Network
    - Deleting server data
    - Other irreversible or financially impactful actions

    Returns:
        401 error if user is not authenticated
        403 error if user is not the server owner
    """
    @wraps(view_func)
    def wrapper(request, guild_id, *args, **kwargs):
        from django.http import JsonResponse

        # Check if user is authenticated
        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            logger.warning(
                f"[SECURITY] Server owner check failed: No Discord session | "
                f"View: {view_func.__name__} | "
                f"Guild: {guild_id} | "
                f"IP: {request.META.get('REMOTE_ADDR')}"
            )
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        # Check if user is the server owner
        admin_guilds = request.session.get('discord_admin_guilds', [])
        guild = next((g for g in admin_guilds if str(g['id']) == str(guild_id)), None)

        if not guild:
            logger.warning(
                f"[SECURITY] Server owner check failed: User {user_id} is not admin of guild {guild_id} | "
                f"View: {view_func.__name__} | "
                f"IP: {request.META.get('REMOTE_ADDR')}"
            )
            return JsonResponse({
                'success': False,
                'error': 'No access to this server'
            }, status=403)

        # Check if user is the actual owner (not just admin/custom role)
        is_owner = guild.get('owner', False)

        if not is_owner:
            logger.warning(
                f"[SECURITY] Server owner check failed: User {user_id} is not owner of guild {guild_id} | "
                f"View: {view_func.__name__} | "
                f"Owner required: True | "
                f"IP: {request.META.get('REMOTE_ADDR')}"
            )
            return JsonResponse({
                'success': False,
                'error': 'Server owner access required - This action can only be performed by the Discord server owner'
            }, status=403)

        logger.info(
            f"[SECURITY] Server owner {user_id} accessed {view_func.__name__} for guild {guild_id} | "
            f"IP: {request.META.get('REMOTE_ADDR')}"
        )
        return view_func(request, guild_id, *args, **kwargs)

    return wrapper


def discovery_approvers_required(view_func):
    """
    Decorator to restrict access to Discovery Network approvers.

    Approvers are defined in DISCOVERY_APPROVERS environment variable as a
    comma-separated list of Discord user IDs.

    Usage:
        @discovery_approvers_required
        def api_discovery_approve(request):
            # Only bot owner and approved users can access this
            ...

    Environment Variable:
        DISCOVERY_APPROVERS="123456789,987654321,555555555"

    Returns:
        401 error if user is not authenticated
        403 error if user is not an approved discovery approver
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        import os

        # Check if user is authenticated
        user = request.session.get('discord_user', {})
        user_id = user.get('id')

        if not user_id:
            logger.warning(
                f"[SECURITY] Discovery approver check failed: No Discord session | "
                f"View: {view_func.__name__} | "
                f"IP: {request.META.get('REMOTE_ADDR')}"
            )
            return JsonResponse({'error': 'Not authenticated'}, status=401)

        # Get bot owner ID (always has approval rights)
        bot_owner_id = os.getenv('BOT_OWNER_ID')

        # Get list of approved discovery approvers from environment
        approvers_env = os.getenv('DISCOVERY_APPROVERS', '')
        approved_ids = [id.strip() for id in approvers_env.split(',') if id.strip()]

        # Add bot owner to approved list
        if bot_owner_id:
            approved_ids.append(bot_owner_id)

        # Check if user is in approved list
        if str(user_id) not in approved_ids:
            logger.warning(
                f"[SECURITY] Discovery approver check failed: User {user_id} is not an approved discovery approver | "
                f"View: {view_func.__name__} | "
                f"Approved IDs: {len(approved_ids)} | "
                f"IP: {request.META.get('REMOTE_ADDR')}"
            )
            return JsonResponse({
                'success': False,
                'error': 'Unauthorized - Discovery approver access required'
            }, status=403)

        logger.info(
            f"[SECURITY] Discovery approver {user_id} accessed {view_func.__name__} | "
            f"IP: {request.META.get('REMOTE_ADDR')}"
        )
        return view_func(request, *args, **kwargs)

    return wrapper
