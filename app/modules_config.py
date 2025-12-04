"""
Warden Bot - Module Configuration
Defines available modules, pricing, and features for modular subscription system.
"""

# Module Definitions
MODULES = {
    'engagement': {
        'name': 'Engagement Suite',
        'short_name': 'Engagement',
        'description': 'Complete member engagement system with XP, flairs, leaderboards, and automated messages',
        'icon': 'fa-fire',
        'color': 'orange',
        'features': [
            'Free: XP & Leveling, Leaderboards, Level-Up Messages, Welcome/Goodbye, Member Profiles, Flairs Store (basic)',
            'Unlock: XP bulk editing/importing',
            'Unlock: Custom Flairs & Rewards Store',
            'Unlock: XP Boost Events (temporary XP multipliers for events/roles/channels)',
        ],
        'price_monthly': 5.00,
        'price_yearly': 50.00,
        'stripe_product_id': None,
        'stripe_price_monthly_id': None,
        'stripe_price_yearly_id': None,
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
        'stripe_product_id': None,
        'stripe_price_monthly_id': None,
        'stripe_price_yearly_id': None,
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
        'stripe_product_id': None,
        'stripe_price_monthly_id': None,
        'stripe_price_yearly_id': None,
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
        'stripe_product_id': None,
        'stripe_price_monthly_id': None,
        'stripe_price_yearly_id': None,
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
        'stripe_product_id': None,
        'stripe_price_monthly_id': None,
        'stripe_price_yearly_id': None,
    },
}

# Bundle Pricing (discounted multi-module packages)
BUNDLES = {
    'pick_2': {
        'name': 'Pick 2 Bundle',
        'description': 'Choose any 2 modules',
        'module_count': 2,
        'price_monthly': 7.99,
        'price_yearly': 79.99,
        'savings': 2.00,
    },
    'pick_3': {
        'name': 'Pick 3 Bundle',
        'description': 'Choose any 3 modules',
        'module_count': 3,
        'price_monthly': 8.99,
        'price_yearly': 89.99,
        'savings': 5.00,
    },
    'complete': {
        'name': 'Complete Suite',
        'description': 'All modules included - Best Value!',
        'module_count': len(MODULES),
        'price_monthly': 9.99,
        'price_yearly': 99.99,
        'savings': 13.00,  # Total would be $23/month à la carte (5+4+5+5+4)
        'highlight': True,  # Featured bundle
    },
}

# Free tier limits
FREE_TIER_LIMITS = {
    'engagement': {
        'xp_max_users': 100,
        'flairs_max': 3,
        'description': 'XP for up to 100 members, 3 custom flairs',
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
    elif module_count >= 3:
        return BUNDLES['pick_3']
    elif module_count >= 2:
        return BUNDLES['pick_2']
    return None

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
