"""
Stripe integration utilities for QuestLog subscription management.
"""
import logging
import stripe
from django.conf import settings
from django.urls import reverse

from .modules_config import MODULES, BUNDLES
from .db import get_db_session
from .models import Guild as GuildModel, GuildModule

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

logger = logging.getLogger(__name__)


def create_checkout_session(guild_id, items, billing_cycle='monthly', success_url=None, cancel_url=None):
    """
    Create a Stripe checkout session for module subscriptions.

    Args:
        guild_id: Discord guild ID
        items: List of dicts with 'type' ('module'|'bundle') and 'key' (module/bundle name)
        billing_cycle: 'monthly', 'yearly', or 'lifetime'
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if payment is cancelled

    Returns:
        Stripe checkout session object
    """
    try:
        line_items = []
        is_lifetime = billing_cycle == 'lifetime'

        for item in items:
            if item['type'] == 'module':
                module = MODULES.get(item['key'])
                if not module:
                    continue

                # Use the stripe price ID based on billing cycle
                price_id = module.get(f'stripe_price_{billing_cycle}_id') \
                           or module.get('stripe_price_monthly_id') \
                           or module.get('stripe_price_yearly_id')
                if not price_id:
                    # If no Stripe price ID configured, skip
                    # In production, you'd want to create these in Stripe dashboard first
                    continue

                line_items.append({
                    'price': price_id,
                    'quantity': 1,
                })

            elif item['type'] == 'bundle':
                bundle = BUNDLES.get(item['key'])
                if not bundle:
                    continue

                price_id = bundle.get(f'stripe_price_{billing_cycle}_id') \
                           or bundle.get('stripe_price_monthly_id') \
                           or bundle.get('stripe_price_yearly_id')
                if not price_id:
                    continue

                line_items.append({
                    'price': price_id,
                    'quantity': 1,
                })

        if not line_items:
            raise ValueError("No valid items to checkout")

        # Create checkout session
        session_params = {
            'payment_method_types': ['card'],
            'line_items': line_items,
            'mode': 'payment' if is_lifetime else 'subscription',
            'success_url': success_url or f"{settings.ALLOWED_HOSTS[0]}/questlog/guild/{guild_id}/billing/?success=true",
            'cancel_url': cancel_url or f"{settings.ALLOWED_HOSTS[0]}/questlog/guild/{guild_id}/billing/?cancelled=true",
            'client_reference_id': str(guild_id),
            'metadata': {
                'guild_id': str(guild_id),
                'billing_cycle': billing_cycle,
                'is_lifetime': 'true' if is_lifetime else 'false',
            },
        }

        # Only add subscription_data for recurring subscriptions
        if not is_lifetime:
            session_params['subscription_data'] = {
                'metadata': {
                    'guild_id': str(guild_id),
                }
            }

        session = stripe.checkout.Session.create(**session_params)

        return session

    except stripe.error.InvalidRequestError as e:
        # Handle specific Stripe errors like inactive products
        error_msg = str(e)
        if 'not active' in error_msg.lower():
            raise Exception("One or more products are not activated in Stripe. Please contact support or activate the products in your Stripe dashboard.")
        elif 'no such price' in error_msg.lower():
            raise Exception("The selected pricing plan is not configured. Please contact support.")
        else:
            raise Exception(f"Stripe configuration error: {error_msg}")
    except Exception as e:
        raise Exception(f"Failed to create checkout session: {str(e)}")


def handle_checkout_completed(session):
    """
    Handle successful checkout completion.
    Update database to activate purchased modules.
    """
    try:
        logger.info(f"Processing checkout completion webhook")

        guild_id = int(session.get('client_reference_id') or session.get('metadata', {}).get('guild_id'))
        subscription_id = session.get('subscription')
        customer_id = session.get('customer')
        is_lifetime = session.get('metadata', {}).get('is_lifetime') == 'true'
        billing_cycle_meta = session.get('metadata', {}).get('billing_cycle')

        logger.info(f"Checkout for guild {guild_id}: subscription={subscription_id}, lifetime={is_lifetime}, cycle={billing_cycle_meta}")

        if not guild_id:
            raise ValueError("No guild_id in session metadata")

        # For lifetime purchases, there's no subscription - it's a one-time payment
        if is_lifetime:
            payment_intent_id = session.get('payment_intent')

            with get_db_session() as db:
                # Update guild record
                guild_record = db.query(GuildModel).filter_by(guild_id=guild_id).first()
                if not guild_record:
                    guild_record = GuildModel(
                        guild_id=guild_id,
                        is_vip=False,
                        subscription_tier='complete',
                        billing_cycle='lifetime',
                    )
                    db.add(guild_record)
                    db.flush()

                # Store customer ID and mark as lifetime
                guild_record.stripe_customer_id = customer_id
                guild_record.stripe_subscription_id = f'lifetime_{payment_intent_id}'  # Special marker
                guild_record.subscription_tier = 'complete'
                guild_record.billing_cycle = 'lifetime'

                # Activate ALL modules for lifetime purchase
                for module_key in MODULES.keys():
                    existing = db.query(GuildModule).filter_by(
                        guild_id=guild_id,
                        module_name=module_key
                    ).first()

                    if not existing:
                        module = GuildModule(
                            guild_id=guild_id,
                            module_name=module_key,
                            enabled=True,
                            stripe_subscription_id=f'lifetime_{payment_intent_id}',
                        )
                        db.add(module)
                    else:
                        existing.enabled = True
                        existing.stripe_subscription_id = f'lifetime_{payment_intent_id}'

                db.commit()

            return True

        # Get subscription details to see what was purchased (recurring subscriptions)
        logger.info(f"Retrieving subscription {subscription_id} from Stripe")
        subscription = stripe.Subscription.retrieve(subscription_id)

        with get_db_session() as db:
            # Update guild record
            guild_record = db.query(GuildModel).filter_by(guild_id=guild_id).first()
            if not guild_record:
                # Create guild record if it doesn't exist
                guild_record = GuildModel(
                    guild_id=guild_id,
                    is_vip=False,
                    subscription_tier='free',
                )
                db.add(guild_record)
                db.flush()
            else:

            # Store Stripe customer and subscription IDs
            guild_record.stripe_customer_id = customer_id
            guild_record.stripe_subscription_id = subscription_id

            # Determine billing cycle from Stripe subscription interval
            # Map Stripe intervals to our billing_cycle enum
            interval = subscription['items']['data'][0]['price']['recurring']['interval']
            interval_count = subscription['items']['data'][0]['price']['recurring'].get('interval_count', 1)


            if interval == 'month':
                if interval_count == 1:
                    billing_cycle = 'monthly'
                elif interval_count == 3:
                    billing_cycle = '3month'
                elif interval_count == 6:
                    billing_cycle = '6month'
                else:
                    billing_cycle = 'monthly'  # Default to monthly
            elif interval == 'year':
                billing_cycle = 'yearly'
            else:
                billing_cycle = 'monthly'  # Default


            # Activate modules based on subscription items
            is_complete_bundle = False
            for item in subscription['items']['data']:
                price_id = item['price']['id']
                modules_to_activate = []


                # Check if this is a bundle purchase
                bundle_found = False
                for bundle_key, bundle_config in BUNDLES.items():

                    if (bundle_config.get('stripe_price_monthly_id') == price_id or
                        bundle_config.get('stripe_price_3month_id') == price_id or
                        bundle_config.get('stripe_price_6month_id') == price_id or
                        bundle_config.get('stripe_price_yearly_id') == price_id or
                        bundle_config.get('stripe_price_lifetime_id') == price_id):
                        # Bundle purchase - activate all modules
                        if bundle_key == 'complete':
                            # Complete Suite: activate ALL modules
                            modules_to_activate = list(MODULES.keys())
                            is_complete_bundle = True
                        else:
                            # Other bundles: would need custom logic (not implemented yet)
                            # For now, treat as complete suite
                            modules_to_activate = list(MODULES.keys())
                            is_complete_bundle = True
                        bundle_found = True
                        break

                if not bundle_found:

                # If not a bundle, check individual modules
                if not bundle_found:
                    for module_key, module_config in MODULES.items():
                        if (module_config.get('stripe_price_monthly_id') == price_id or
                            module_config.get('stripe_price_yearly_id') == price_id):
                            modules_to_activate.append(module_key)
                            break

                # Activate all identified modules
                for module_key in modules_to_activate:
                    # Check if module already exists
                    existing = db.query(GuildModule).filter_by(
                        guild_id=guild_id,
                        module_name=module_key
                    ).first()

                    if not existing:
                        # Create new module subscription
                        module = GuildModule(
                            guild_id=guild_id,
                            module_name=module_key,
                            enabled=True,
                            stripe_subscription_id=subscription['id'],
                        )
                        db.add(module)
                    else:
                        # Reactivate existing module
                        existing.enabled = True
                        existing.stripe_subscription_id = subscription['id']

            # Update subscription tier and billing cycle on guild record
            if is_complete_bundle:
                guild_record.subscription_tier = 'complete'
                guild_record.billing_cycle = billing_cycle
                # Get current_period_end from subscription items (not top-level subscription object)
                current_period_end = subscription['items']['data'][0].get('current_period_end')
                guild_record.subscription_expires = current_period_end
            else:
                # Individual module subscription - keep tier as 'free'
                # Module access is tracked in guild_modules table
                guild_record.subscription_tier = 'free'
                guild_record.billing_cycle = billing_cycle
                # Get current_period_end from subscription items
                current_period_end = subscription['items']['data'][0].get('current_period_end')
                guild_record.subscription_expires = current_period_end

            db.commit()

        logger.info(f"Successfully processed checkout for guild")
        return True

    except Exception as e:
        logger.error(f"Error handling checkout completion: {e}")
        import traceback
        traceback.print_exc()
        return False


def handle_subscription_updated(subscription):
    """
    Handle subscription update events (e.g., plan changes, renewals, cancellations).
    """
    try:
        guild_id = int(subscription.get('metadata', {}).get('guild_id'))
        if not guild_id:
            return False

        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=guild_id).first()
            if not guild_record:
                return False

            # Update subscription status
            guild_record.stripe_subscription_id = subscription['id']
            guild_record.stripe_customer_id = subscription['customer']

            # Get current_period_end from subscription items
            current_period_end = subscription['items']['data'][0].get('current_period_end') if subscription.get('items', {}).get('data') else None

            # Handle cancellation - if cancel_at_period_end is true, keep access until expiration
            if subscription.get('cancel_at_period_end', False):
                guild_record.subscription_expires = current_period_end
            else:
                # Subscription is active, update expiration to current period end
                guild_record.subscription_expires = current_period_end

            # Sync module activations with subscription items
            active_price_ids = set()
            for item in subscription['items']['data']:
                active_price_ids.add(item['price']['id'])

            # Determine which modules should be active based on subscription
            modules_should_be_active = set()

            # Check if any active price belongs to a bundle
            for price_id in active_price_ids:
                bundle_found = False
                for bundle_key, bundle_config in BUNDLES.items():
                    if (bundle_config.get('stripe_price_monthly_id') == price_id or
                        bundle_config.get('stripe_price_3month_id') == price_id or
                        bundle_config.get('stripe_price_6month_id') == price_id or
                        bundle_config.get('stripe_price_yearly_id') == price_id or
                        bundle_config.get('stripe_price_lifetime_id') == price_id):
                        # Bundle subscription - all modules should be active
                        if bundle_key == 'complete':
                            modules_should_be_active.update(MODULES.keys())
                        else:
                            # Other bundles would need custom logic
                            modules_should_be_active.update(MODULES.keys())
                        bundle_found = True
                        break

                # If not a bundle, check individual modules
                if not bundle_found:
                    for module_key, module_config in MODULES.items():
                        monthly_id = module_config.get('stripe_price_monthly_id')
                        yearly_id = module_config.get('stripe_price_yearly_id')
                        if price_id in (monthly_id, yearly_id):
                            modules_should_be_active.add(module_key)

            # Update module activation status
            for module_key in MODULES.keys():
                is_active = module_key in modules_should_be_active

                existing = db.query(GuildModule).filter_by(
                    guild_id=guild_id,
                    module_name=module_key
                ).first()

                if existing:
                    existing.enabled = is_active
                    # If cancelled but still in paid period, set expiration
                    if is_active and subscription.get('cancel_at_period_end', False):
                        existing.expires_at = current_period_end
                    # If active subscription (not cancelled), clear expiration
                    elif is_active:
                        existing.expires_at = None
                elif is_active:
                    # Create module if it should be active but doesn't exist
                    # If cancelled, set expiration; otherwise leave it None (no expiration)
                    expires_at = current_period_end if subscription.get('cancel_at_period_end', False) else None
                    module = GuildModule(
                        guild_id=guild_id,
                        module_name=module_key,
                        enabled=True,
                        stripe_subscription_id=subscription['id'],
                        expires_at=expires_at,
                    )
                    db.add(module)

            db.commit()

        return True

    except Exception as e:
        return False


def handle_subscription_deleted(subscription):
    """
    Handle subscription cancellation/deletion.
    Deactivate all modules and revert to free tier.
    """
    try:
        guild_id = int(subscription.get('metadata', {}).get('guild_id'))
        if not guild_id:
            return False

        with get_db_session() as db:
            # Deactivate all modules
            db.query(GuildModule).filter_by(guild_id=guild_id).update({'enabled': False})

            # Clear subscription info from guild and revert to free tier
            guild_record = db.query(GuildModel).filter_by(guild_id=guild_id).first()
            if guild_record:
                guild_record.stripe_subscription_id = None
                guild_record.subscription_tier = 'free'
                guild_record.billing_cycle = None
                guild_record.subscription_expires = None
                # Keep customer_id for potential reactivation

            db.commit()

        return True

    except Exception as e:
        return False


def cancel_subscription(guild_id):
    """
    Cancel a guild's Stripe subscription at the end of the billing period.
    """
    try:
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=guild_id).first()
            if not guild_record or not guild_record.stripe_subscription_id:
                return False, "No active subscription found"

            # Skip if it's a lifetime subscription (no actual Stripe subscription)
            if guild_record.stripe_subscription_id.startswith('lifetime_'):
                return False, "Cannot cancel lifetime subscription"

            # Cancel the subscription at period end (not immediately)
            stripe.Subscription.modify(
                guild_record.stripe_subscription_id,
                cancel_at_period_end=True
            )

            # Fetch updated subscription to get current_period_end
            subscription = stripe.Subscription.retrieve(guild_record.stripe_subscription_id)
            current_period_end = subscription['items']['data'][0].get('current_period_end')

            # Update database to reflect cancellation
            guild_record.subscription_expires = current_period_end

            # Set expires_at on all active modules
            db.query(GuildModule).filter_by(
                guild_id=guild_id,
                enabled=True
            ).update({'expires_at': current_period_end})

            db.commit()

            # Format the date for the success message
            from datetime import datetime
            expiry_date = datetime.fromtimestamp(current_period_end).strftime('%B %d, %Y')

            return True, f"Subscription cancelled. You'll retain access until {expiry_date}."

    except Exception as e:
        return False, f"Error cancelling subscription: {str(e)}"


def get_subscription_status(guild_id):
    """
    Get the current subscription status for a guild.
    """
    try:
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=guild_id).first()
            if not guild_record or not guild_record.stripe_subscription_id:
                return None

            # Fetch from Stripe
            subscription = stripe.Subscription.retrieve(guild_record.stripe_subscription_id)

            return {
                'id': subscription['id'],
                'status': subscription['status'],
                'current_period_end': subscription['items']['data'][0].get('current_period_end'),
                'cancel_at_period_end': subscription['cancel_at_period_end'],
                'items': subscription['items']['data'],
            }

    except Exception as e:
        return None
