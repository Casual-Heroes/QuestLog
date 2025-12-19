"""
QuestLog - Module Configuration
Defines available modules, pricing, and features for modular subscription system.
"""

# Module Definitions
MODULES = {
    'engagement': {
        'name': 'Engagement Suite',
        'short_name': 'Engagement',
        'description': 'Complete member engagement system with XP, flairs, leaderboards, raffles, and automated messages',
        'icon': 'fa-fire',
        'color': 'orange',
        'features': [
            'Free: XP & Leveling, Leaderboards, Level-Up Messages, Welcome/Goodbye, Member Profiles, Flairs Store (basic), Up to 3 Raffles with Entry Requirements',
            'Unlock: XP bulk editing/importing',
            'Unlock: Custom Flairs & Rewards Store',
            'Unlock: XP Boost Events (temporary XP multipliers for events/roles/channels)',
            'Unlock: Unlimited Raffles with scheduled auto-draw, multiple winners, prize tiers & analytics',
        ],
        'price_monthly': 5.00,
        'price_yearly': 50.00,
        'stripe_product_id': 'prod_TZclRkRQ3gPpqM',
        'stripe_price_monthly_id': 'price_1ScTWHCqgyN1IYjdTxFykzCH',
        'stripe_price_yearly_id': 'price_1ScTWHCqgyN1IYjdTxFykzCH',  # Update with yearly ID when created
    },
    'roles': {
        'name': 'Role Management',
        'short_name': 'Roles',
        'description': 'Advanced role management with bulk operations, reaction roles, and templates',
        'icon': 'fa-user-tag',
        'color': 'purple',
        'features': [
            'Advanced Role Manager (bulk create, edit, delete)',
            'Role Import/Export (CSV)',
            'Unlimited Reaction Role Menus',
            'Role & Channel Templates',
            'Permission Template Presets',
            'Quick Server Setup',
        ],
        'price_monthly': 4.00,
        'price_yearly': 40.00,
        'stripe_product_id': 'prod_TZcmPFcIcFQbkS',
        'stripe_price_monthly_id': 'price_1ScTWnCqgyN1IYjdjR6CjPdT',
        'stripe_price_yearly_id': 'price_1ScTWnCqgyN1IYjdjR6CjPdT',  # Update with yearly ID when created
    },
    'moderation': {
        'name': 'Moderation & Security',
        'short_name': 'Moderation',
        'description': 'Comprehensive moderation tools with verification, audit logs, and anti-raid protection',
        'icon': 'fa-shield-alt',
        'color': 'red',
        'features': [
            'Warning System with Auto-Escalation',
            'Temporary & Permanent Bans',
            'User Jailing & Timeout Management',
            'Comprehensive Audit Logs',
            'Verification System (CAPTCHA, Account Age)',
            'Anti-Raid Protection',
            'Bulk Moderation Tools',
        ],
        'price_monthly': 5.00,
        'price_yearly': 50.00,
        'stripe_product_id': 'prod_TZcmue3k5Gd9n1',
        'stripe_price_monthly_id': 'price_1ScTX9CqgyN1IYjdICJkXc4L',
        'stripe_price_yearly_id': 'price_1ScTX9CqgyN1IYjdICJkXc4L',  # Update with yearly ID when created
    },
    'discovery': {
        'name': 'Discovery & Promotion',
        'short_name': 'Discovery',
        'description': 'Game and creator discovery with automated featuring and self-promotion management',
        'icon': 'fa-star',
        'color': 'yellow',
        'features': [
            'Game & Creator Discovery System',
            'Creator of the Week (COTW) Auto-Featuring',
            'Creator of the Month (COTM) Voting',
            'Found Games Tracking with IGDB',
            'Self-Promo Channel Management',
            'Featured Pool with Token Costs',
            'Customizable Schedules & Cooldowns',
        ],
        'price_monthly': 5.00,
        'price_yearly': 50.00,
        'stripe_product_id': 'prod_TZcnweCmkz1XER',
        'stripe_price_monthly_id': 'price_1ScTYMCqgyN1IYjdwgYA0lpS',
        'stripe_price_yearly_id': 'price_1ScTYMCqgyN1IYjdwgYA0lpS',  # Update with yearly ID when created
    },
    'lfg': {
        'name': 'Events & Attendance',
        'short_name': 'LFG',
        'description': 'LFG system with attendance tracking, blacklist management, and event trackers',
        'icon': 'fa-calendar-check',
        'color': 'blue',
        'features': [
            'LFG Event Creation & Management',
            'Attendance Tracking (Check-in/Check-out)',
            'Blacklist & Reliability System',
            'Event History & Analytics',
            'Custom Event Trackers',
            'Attendance Export & Reports',
            'Global Pardon System',
        ],
        'price_monthly': 4.00,
        'price_yearly': 40.00,
        'stripe_product_id': 'prod_TZcoiL7fpIHIfC',
        'stripe_price_monthly_id': 'price_1ScTYhCqgyN1IYjdBxbQpD35',
        'stripe_price_yearly_id': 'price_1ScTYhCqgyN1IYjdBxbQpD35',  # Update with yearly ID when created
    },
}

# Bundle Pricing (discounted multi-module packages)
BUNDLES = {
    'complete': {
        'name': 'Complete Suite',
        'description': 'All modules included - Best Value!',
        'module_count': len(MODULES),
        'price_monthly': 12.99,
        'price_3month': 27.00,   # $9/month - save 31%
        'price_6month': 42.00,   # $7/month - save 46%
        'price_yearly': 49.99,   # $4.17/month - save 68%
        'price_lifetime': 99.99,
        'sale_price_monthly': None,  # Set to enable sale (e.g., 9.99)
        'sale_price_3month': None,
        'sale_price_6month': None,
        'sale_price_yearly': None,
        'sale_price_lifetime': None,
        'savings': 10.00,  # Total would be $23/month à la carte (5+4+5+5+4)
        'highlight': True,  # Featured bundle
        'stripe_product_id': 'prod_TZgyYIHP0dbMpP',  # Complete Suite product
        'stripe_price_monthly_id': 'price_1ScXaQCqgyN1IYjdLGIog2SW',  # Monthly $12.99
        'stripe_price_3month_id': 'price_1ScTUlCqgyN1IYjd9qbkfE6G',
        'stripe_price_6month_id': 'price_1ScTU0CqgyN1IYjdzMWY02Og',
        'stripe_price_yearly_id': 'price_1ScTVuCqgyN1IYjdn76QEcx1',
        'stripe_price_lifetime_id': 'price_1ScTVOCqgyN1IYjddB9jx6Br',
        # Sale price IDs (create in Stripe when running promotions)
        'stripe_sale_price_monthly_id': None,
        'stripe_sale_price_3month_id': None,
        'stripe_sale_price_6month_id': None,
        'stripe_sale_price_yearly_id': None,
        'stripe_sale_price_lifetime_id': None,
    },
    # Promotional bundles - Enable/disable for limited-time offers
    'pick_2': {
        'name': 'Pick 2 Bundle',
        'description': 'Choose any 2 modules',
        'module_count': 2,
        'price_monthly': 7.99,
        'price_yearly': 79.99,
        'savings': 2.00,
        'enabled': False,  # Set to True to show on billing page
        'stripe_product_id': 'prod_TYBMJk1BjeqfFA',
        'stripe_price_monthly_id': 'price_1Sb4zZCqgyN1IYjdpiTNIksA',
        'stripe_price_yearly_id': 'price_1Sb4zaCqgyN1IYjdoybQoYzP',
    },
    'pick_3': {
        'name': 'Pick 3 Bundle',
        'description': 'Choose any 3 modules',
        'module_count': 3,
        'price_monthly': 8.99,
        'price_yearly': 89.99,
        'savings': 5.00,
        'enabled': False,  # Set to True to show on billing page
        'stripe_product_id': 'prod_TYBMGHfOv3apqb',
        'stripe_price_monthly_id': 'price_1Sb4zaCqgyN1IYjdvXqbkU7I',
        'stripe_price_yearly_id': 'price_1Sb4zbCqgyN1IYjdmKPJ8qJc',
    },
}

# Free tier limits
FREE_TIER_LIMITS = {
    'engagement': {
        'xp_max_users': None,  # No limit - all members gain XP regardless of tier
        'flairs_max': 0,  # Cannot create custom flairs (paid feature only)
        'raffles_max': 3,  # Up to 3 active raffles
        'description': 'XP for all members, basic flairs store, up to 3 raffles',
    },
    'roles': {
        'reaction_role_max_menus': 2,
        'templates_max': 3,
        'description': 'Up to 2 reaction role menus, 3 templates',
    },
    'moderation': {
        'audit_retention_days': 7,
        'description': 'Audit logs kept for 7 days',
    },
}

# Helper functions
def get_module(module_name):
    """Get module configuration by name."""
    return MODULES.get(module_name)

def get_all_modules():
    """Get all module configurations."""
    return MODULES

def get_module_price(module_name, billing_cycle='monthly'):
    """Get price for a specific module."""
    module = get_module(module_name)
    if not module:
        return None
    return module.get(f'price_{billing_cycle}', 0.0)

def calculate_total_price(module_names, billing_cycle='monthly'):
    """Calculate total price for a list of modules."""
    total = 0.0
    for module_name in module_names:
        price = get_module_price(module_name, billing_cycle)
        if price:
            total += price
    return total

def get_best_bundle(module_count):
    """Get the best bundle for a given number of modules."""
    if module_count >= len(MODULES):
        return BUNDLES['complete']
    elif module_count >= 3 and BUNDLES.get('pick_3', {}).get('enabled'):
        return BUNDLES['pick_3']
    elif module_count >= 2 and BUNDLES.get('pick_2', {}).get('enabled'):
        return BUNDLES['pick_2']
    return None

def get_active_price(bundle_or_module, billing_cycle='monthly'):
    """
    Get the active price for a bundle or module, considering sales.
    Returns the sale price if available, otherwise returns regular price.
    """
    sale_key = f'sale_price_{billing_cycle}'
    regular_key = f'price_{billing_cycle}'

    # Check if sale price exists and is set
    if sale_key in bundle_or_module and bundle_or_module[sale_key] is not None:
        return bundle_or_module[sale_key]

    # Return regular price
    return bundle_or_module.get(regular_key, 0.0)

def get_enabled_bundles():
    """Get all bundles that are enabled for display."""
    return {k: v for k, v in BUNDLES.items() if v.get('enabled', True)}

def calculate_savings(module_names, billing_cycle='monthly'):
    """Calculate savings compared to à la carte pricing."""
    module_count = len(module_names)
    if module_count < 2:
        return 0.0

    a_la_carte = calculate_total_price(module_names, billing_cycle)
    bundle = get_best_bundle(module_count)

    if bundle:
        bundle_price = bundle.get(f'price_{billing_cycle}', 0.0)
        return max(0.0, a_la_carte - bundle_price)

    return 0.0
