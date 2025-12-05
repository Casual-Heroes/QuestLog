"""
Stripe integration utilities for Warden Bot subscription management.
"""
import stripe
from django.conf import settings
from django.urls import reverse

from .modules_config import MODULES, BUNDLES
from .db import get_db_session
from .models import Guild as GuildModel, GuildModule

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_checkout_session(guild_id, items, billing_cycle='monthly', success_url=None, cancel_url=None):
    """
    Create a Stripe checkout session for module subscriptions.

    Args:
        guild_id: Discord guild ID
        items: List of dicts with 'type' ('module'|'bundle') and 'key' (module/bundle name)
        billing_cycle: 'monthly' or 'yearly'
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if payment is cancelled

    Returns:
        Stripe checkout session object
    """
    try:
        line_items = []

        for item in items:
            if item['type'] == 'module':
                module = MODULES.get(item['key'])
                if not module:
                    continue

                # Use the stripe price ID based on billing cycle
                price_id = module.get(f'stripe_price_{billing_cycle}_id')
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

                # For bundles, you'd need to create bundle products in Stripe
                # For now, we'll create a price on the fly (not recommended for production)
                # In production, create these in Stripe dashboard
                continue

        if not line_items:
            raise ValueError("No valid items to checkout")

        # Create checkout session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=line_items,
            mode='subscription',
            success_url=success_url or f"{settings.ALLOWED_HOSTS[0]}/warden/guild/{guild_id}/billing/?success=true",
            cancel_url=cancel_url or f"{settings.ALLOWED_HOSTS[0]}/warden/guild/{guild_id}/billing/?cancelled=true",
            client_reference_id=str(guild_id),
            metadata={
                'guild_id': str(guild_id),
                'billing_cycle': billing_cycle,
            },
            subscription_data={
                'metadata': {
                    'guild_id': str(guild_id),
                }
            },
        )

        return session

    except Exception as e:
        raise Exception(f"Failed to create checkout session: {str(e)}")


def handle_checkout_completed(session):
    """
    Handle successful checkout completion.
    Update database to activate purchased modules.
    """
    try:
        guild_id = int(session.get('client_reference_id') or session.get('metadata', {}).get('guild_id'))
        subscription_id = session.get('subscription')
        customer_id = session.get('customer')

        if not guild_id:
            raise ValueError("No guild_id in session metadata")

        # Get subscription details to see what was purchased
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

            # Store Stripe customer and subscription IDs
            guild_record.stripe_customer_id = customer_id
            guild_record.stripe_subscription_id = subscription_id

            # Activate modules based on subscription items
            for item in subscription['items']['data']:
                price_id = item['price']['id']

                # Find which module this price belongs to
                for module_key, module_config in MODULES.items():
                    if (module_config.get('stripe_price_monthly_id') == price_id or
                        module_config.get('stripe_price_yearly_id') == price_id):

                        # Check if module already exists
                        existing = db.query(GuildModule).filter_by(
                            guild_id=guild_id,
                            module_key=module_key
                        ).first()

                        if not existing:
                            # Create new module subscription
                            module = GuildModule(
                                guild_id=guild_id,
                                module_key=module_key,
                                is_active=True,
                                stripe_subscription_item_id=item['id'],
                            )
                            db.add(module)
                        else:
                            # Reactivate existing module
                            existing.is_active = True
                            existing.stripe_subscription_item_id = item['id']

            db.commit()

        return True

    except Exception as e:
        print(f"Error handling checkout completion: {e}")
        return False


def handle_subscription_updated(subscription):
    """
    Handle subscription update events (e.g., plan changes, renewals).
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

            # Sync module activations with subscription items
            active_price_ids = set()
            for item in subscription['items']['data']:
                active_price_ids.add(item['price']['id'])

            # Deactivate modules not in subscription
            for module_key, module_config in MODULES.items():
                monthly_id = module_config.get('stripe_price_monthly_id')
                yearly_id = module_config.get('stripe_price_yearly_id')

                is_active = monthly_id in active_price_ids or yearly_id in active_price_ids

                existing = db.query(GuildModule).filter_by(
                    guild_id=guild_id,
                    module_key=module_key
                ).first()

                if existing:
                    existing.is_active = is_active

            db.commit()

        return True

    except Exception as e:
        print(f"Error handling subscription update: {e}")
        return False


def handle_subscription_deleted(subscription):
    """
    Handle subscription cancellation/deletion.
    Deactivate all modules for this guild.
    """
    try:
        guild_id = int(subscription.get('metadata', {}).get('guild_id'))
        if not guild_id:
            return False

        with get_db_session() as db:
            # Deactivate all modules
            db.query(GuildModule).filter_by(guild_id=guild_id).update({'is_active': False})

            # Clear subscription info from guild
            guild_record = db.query(GuildModel).filter_by(guild_id=guild_id).first()
            if guild_record:
                guild_record.stripe_subscription_id = None
                # Keep customer_id for potential reactivation

            db.commit()

        return True

    except Exception as e:
        print(f"Error handling subscription deletion: {e}")
        return False


def cancel_subscription(guild_id):
    """
    Cancel a guild's Stripe subscription.
    """
    try:
        with get_db_session() as db:
            guild_record = db.query(GuildModel).filter_by(guild_id=guild_id).first()
            if not guild_record or not guild_record.stripe_subscription_id:
                return False, "No active subscription found"

            # Cancel the subscription in Stripe
            stripe.Subscription.delete(guild_record.stripe_subscription_id)

            return True, "Subscription cancelled successfully"

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
                'current_period_end': subscription['current_period_end'],
                'cancel_at_period_end': subscription['cancel_at_period_end'],
                'items': subscription['items']['data'],
            }

    except Exception as e:
        print(f"Error fetching subscription status: {e}")
        return None
