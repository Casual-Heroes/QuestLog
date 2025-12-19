"""
QuestLog - Module Utilities
Helper functions and decorators for checking module access.
"""

import time
from functools import wraps
from django.http import JsonResponse
from .db import get_db_session
from .models import GuildModule, Guild
from .modules_config import get_module, MODULES


def has_module_access(guild_id, module_name):
    """
    Check if a guild has access to a specific module.

    Args:
        guild_id: Discord guild ID
        module_name: Module identifier (e.g., 'lfg', 'discovery')

    Returns:
        bool: True if guild has active access to the module
    """
    try:
        with get_db_session() as db:
            # Check if guild has VIP status (gets everything for free)
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if guild and guild.is_vip:
                return True

            # Check if module exists in database and is active
            module = db.query(GuildModule).filter_by(
                guild_id=int(guild_id),
                module_name=module_name,
                enabled=True
            ).first()

            if not module:
                return False

            # Check expiration
            if module.expires_at and module.expires_at < int(time.time()):
                return False

            return True
    except Exception as e:
        print(f"Error checking module access: {e}")
        return False


def has_any_module_access(guild_id):
    """
    Check if a guild has access to ANY module.

    Args:
        guild_id: Discord guild ID

    Returns:
        bool: True if guild has active access to at least one module
    """
    try:
        with get_db_session() as db:
            # Check if guild has VIP status (gets everything for free)
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if guild and guild.is_vip:
                return True

            # Check if any module exists in database and is active
            modules = db.query(GuildModule).filter_by(
                guild_id=int(guild_id),
                enabled=True
            ).all()

            if not modules:
                return False

            # Check if at least one module is not expired
            current_time = int(time.time())
            for module in modules:
                if not module.expires_at or module.expires_at > current_time:
                    return True

            return False
    except Exception as e:
        print(f"Error checking any module access: {e}")
        return False


def get_guild_modules(guild_id):
    """
    Get all active modules for a guild.

    Args:
        guild_id: Discord guild ID

    Returns:
        list: List of active module names
    """
    try:
        with get_db_session() as db:
            modules = db.query(GuildModule).filter_by(
                guild_id=int(guild_id),
                enabled=True
            ).all()

            # Filter out expired modules
            current_time = int(time.time())
            active_modules = [
                m.module_name for m in modules
                if not m.expires_at or m.expires_at > current_time
            ]

            return active_modules
    except Exception as e:
        print(f"Error getting guild modules: {e}")
        return []


def get_missing_module_info(module_name):
    """
    Get information about a module for upgrade prompts.

    Args:
        module_name: Module identifier

    Returns:
        dict: Module information
    """
    module_config = get_module(module_name)
    if not module_config:
        return {
            'name': module_name.title(),
            'description': 'This feature requires a premium module.',
            'price_monthly': 0.00,
        }

    return {
        'name': module_config['name'],
        'short_name': module_config['short_name'],
        'description': module_config['description'],
        'price_monthly': module_config['price_monthly'],
        'price_yearly': module_config['price_yearly'],
        'features': module_config['features'],
        'icon': module_config.get('icon', 'fa-star'),
        'color': module_config.get('color', 'blue'),
    }


def module_required(module_name):
    """
    Decorator to require module access for a view.

    Usage:
        @module_required('lfg')
        @api_auth_required
        def my_api_view(request, guild_id):
            ...

    Args:
        module_name: Module identifier to check

    Returns:
        Decorator function
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, guild_id, *args, **kwargs):
            # Check if guild has access to this module
            if not has_module_access(guild_id, module_name):
                module_info = get_missing_module_info(module_name)
                return JsonResponse({
                    'error': f'This server does not have access to {module_info["name"]}',
                    'requires_upgrade': True,
                    'module': module_name,
                    'module_info': module_info,
                    'upgrade_url': f'/questlog/guild/{guild_id}/billing/'
                }, status=403)

            # Module access verified, proceed with view
            return view_func(request, guild_id, *args, **kwargs)
        return wrapper
    return decorator


def module_required_page(module_name):
    """
    Decorator to require module access for a page view (redirects to billing).

    Usage:
        @module_required_page('lfg')
        @discord_required
        def my_page_view(request, guild_id):
            ...

    Args:
        module_name: Module identifier to check

    Returns:
        Decorator function
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, guild_id, *args, **kwargs):
            from django.shortcuts import redirect
            from django.contrib import messages

            # Check if guild has access to this module
            if not has_module_access(guild_id, module_name):
                module_info = get_missing_module_info(module_name)
                messages.warning(
                    request,
                    f'The {module_info["name"]} module is not enabled for this server. '
                    f'Upgrade to unlock this feature!'
                )
                return redirect('guild_billing', guild_id=guild_id)

            # Module access verified, proceed with view
            return view_func(request, guild_id, *args, **kwargs)
        return wrapper
    return decorator


def grant_module_access(guild_id, module_name, expires_at=None, stripe_subscription_id=None, activated_by=None):
    """
    Grant a guild access to a module.

    Args:
        guild_id: Discord guild ID
        module_name: Module identifier
        expires_at: Unix timestamp when access expires (None for lifetime)
        stripe_subscription_id: Stripe subscription ID
        activated_by: User ID who activated the module

    Returns:
        bool: True if successful
    """
    try:
        with get_db_session() as db:
            # Check if module already exists
            module = db.query(GuildModule).filter_by(
                guild_id=int(guild_id),
                module_name=module_name
            ).first()

            if module:
                # Update existing module
                module.enabled = True
                module.expires_at = expires_at
                module.stripe_subscription_id = stripe_subscription_id
                if activated_by:
                    module.activated_by = int(activated_by)
            else:
                # Create new module access
                module = GuildModule(
                    guild_id=int(guild_id),
                    module_name=module_name,
                    enabled=True,
                    expires_at=expires_at,
                    stripe_subscription_id=stripe_subscription_id,
                    activated_by=int(activated_by) if activated_by else None
                )
                db.add(module)

            db.commit()
            return True
    except Exception as e:
        print(f"Error granting module access: {e}")
        return False


def revoke_module_access(guild_id, module_name):
    """
    Revoke a guild's access to a module.

    Args:
        guild_id: Discord guild ID
        module_name: Module identifier

    Returns:
        bool: True if successful
    """
    try:
        with get_db_session() as db:
            module = db.query(GuildModule).filter_by(
                guild_id=int(guild_id),
                module_name=module_name
            ).first()

            if module:
                module.enabled = False
                db.commit()

            return True
    except Exception as e:
        print(f"Error revoking module access: {e}")
        return False


def get_module_stats(guild_id):
    """
    Get statistics about module usage for a guild.

    Args:
        guild_id: Discord guild ID

    Returns:
        dict: Module statistics
    """
    try:
        with get_db_session() as db:
            modules = db.query(GuildModule).filter_by(
                guild_id=int(guild_id)
            ).all()

            active_count = sum(1 for m in modules if m.is_active())
            total_modules = len(MODULES)

            return {
                'active_modules': active_count,
                'total_modules': total_modules,
                'modules': [
                    {
                        'name': m.module_name,
                        'enabled': m.enabled,
                        'active': m.is_active(),
                        'expires_at': m.expires_at,
                        'activated_at': m.activated_at,
                    }
                    for m in modules
                ]
            }
    except Exception as e:
        print(f"Error getting module stats: {e}")
        return {
            'active_modules': 0,
            'total_modules': len(MODULES),
            'modules': []
        }
