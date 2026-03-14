# QuestLog Web - Billing views (Stripe Hero subscription)
#
# Endpoints:
#   GET  /ql/hero/              - Landing/upgrade page (hero_subscribe)
#   GET  /ql/hero/success/      - Post-checkout confirmation (hero_success)
#   POST /ql/api/billing/checkout/  - Create Stripe Checkout Session -> {url}
#   POST /ql/api/billing/webhook/   - Stripe webhook handler (CSRF-exempt)
#   POST /ql/api/billing/portal/    - Redirect to Stripe Customer Portal
#
# Perks activated/deactivated here:
#   - is_hero flag on WebUser
#   - hero_expires_at timestamp
#   - Fluxer Hero role via WebFluxerRoleUpdate queue ('set_hero'/'clear_hero')
#
# Setup checklist (one-time, before enabling):
#   1. Create "QuestLog Hero" product + $5/mo price in Stripe dashboard
#   2. Set STRIPE_HERO_PRICE_ID=price_xxx in /etc/casual-heroes/secrets.env
#   3. Set STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET in secrets.env
#   4. Configure Stripe webhook endpoint: https://casual-heroes.com/ql/api/billing/webhook/
#      Events: checkout.session.completed, invoice.payment_succeeded,
#              customer.subscription.deleted, customer.subscription.updated

import json
import time
import logging

import stripe
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from app.db import get_db_session
from .models import WebUser, WebSubscriptionEvent, WebFluxerRoleUpdate
from .helpers import web_login_required, add_web_user_context, award_xp

logger = logging.getLogger(__name__)

# How many seconds a monthly cycle adds to hero_expires_at (31 days with 1-day grace)
_MONTHLY_SECONDS = 31 * 24 * 3600
_YEARLY_SECONDS = 366 * 24 * 3600


def _stripe_client():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _queue_hero_role(db, web_user_id, action):
    """Queue a hero role update for Fluxer. action = 'set_hero' or 'clear_hero'."""
    db.add(WebFluxerRoleUpdate(
        web_user_id=web_user_id,
        action=action,
        flair_emoji=None,
        flair_name=None,
        created_at=int(time.time()),
    ))


# =============================================================================
# Public pages
# =============================================================================

@add_web_user_context
def hero_subscribe(request):
    """Champion subscription landing page."""
    from app.db import get_db_session
    from app.questlog_web.models import WebUser
    # Opted-in Champions (show_as_champion=1 and is_hero=1)
    with get_db_session() as db:
        champions = db.query(WebUser).filter(
            WebUser.is_hero == 1,
            WebUser.show_as_champion == 1,
            WebUser.is_banned == False,
            WebUser.is_disabled == False,
        ).order_by(WebUser.id.asc()).limit(50).all()
        champions_data = [
            {'username': c.username, 'avatar_url': c.avatar_url or c.steam_avatar or ''}
            for c in champions
        ]
    return render(request, 'questlog_web/hero.html', {
        'web_user': getattr(request, 'web_user', None),
        'active_page': 'hero',
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
        'stripe_test_mode': settings.STRIPE_TEST_MODE,
        'hero_price_id': settings.STRIPE_HERO_PRICE_ID,
        'champions': champions_data,
    })


def hero_return(request):
    """Stripe redirects here after checkout. Forward to home with success flag."""
    return redirect('/ql/?champion=1')


@add_web_user_context
def hero_success(request):
    """Post-checkout success confirmation page."""
    return render(request, 'questlog_web/hero_success.html', {})


# =============================================================================
# Checkout session
# =============================================================================

@web_login_required
@add_web_user_context
@require_http_methods(['POST'])
def api_hero_checkout(request):
    """
    Create a Stripe Checkout Session for the Hero monthly subscription.
    Returns {url} for client-side redirect.
    """
    if not settings.STRIPE_HERO_PRICE_ID:
        return JsonResponse({'error': 'Hero subscription is not yet available.'}, status=503)

    s = _stripe_client()
    user_id = request.web_user.id
    now = int(time.time())

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user:
            return JsonResponse({'error': 'User not found.'}, status=404)

        if user.is_hero and user.hero_expires_at and user.hero_expires_at > now:
            return JsonResponse({'error': 'You already have an active Hero subscription.'}, status=400)

        # Reuse existing Stripe customer if we have one
        customer_id = user.stripe_customer_id or None

    try:
        session_params = {
            'mode': 'subscription',
            'line_items': [{'price': settings.STRIPE_HERO_PRICE_ID, 'quantity': 1}],
            'success_url': request.build_absolute_uri('/ql/hero/return/') + '?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': request.build_absolute_uri('/ql/hero/'),
            'metadata': {'web_user_id': str(user_id)},
            'subscription_data': {'metadata': {'web_user_id': str(user_id)}},
        }
        if customer_id:
            session_params['customer'] = customer_id
        else:
            if user.email:
                session_params['customer_email'] = user.email

        session = s.checkout.Session.create(**session_params)

        # Log the checkout start
        with get_db_session() as db:
            db.add(WebSubscriptionEvent(
                user_id=user_id,
                event_type='checkout_started',
                stripe_event_id=None,
                amount_cents=None,
                created_at=now,
            ))
            db.commit()

        return JsonResponse({'url': session.url})

    except stripe.error.StripeError as e:
        logger.error(f"Stripe checkout error for user {user_id}: {e}")
        return JsonResponse({'error': 'Payment provider error. Please try again.'}, status=502)


# =============================================================================
# Customer Portal
# =============================================================================

@web_login_required
@add_web_user_context
@require_http_methods(['POST'])
def hero_portal(request):
    """
    Create a Stripe Billing Portal session and redirect user to it
    (manage/cancel subscription).
    """
    s = _stripe_client()
    user_id = request.web_user.id

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user or not user.stripe_customer_id:
            return JsonResponse({'error': 'No active subscription found.'}, status=400)
        customer_id = user.stripe_customer_id

    try:
        portal = s.billing_portal.Session.create(
            customer=customer_id,
            return_url=request.build_absolute_uri('/ql/hero/'),
        )
        return redirect(portal.url)
    except stripe.error.StripeError as e:
        logger.error(f"Stripe portal error for user {user_id}: {e}")
        return JsonResponse({'error': 'Could not open billing portal. Please try again.'}, status=502)


# =============================================================================
# Stripe Webhook
# =============================================================================

@csrf_exempt
@require_http_methods(['POST'])
def api_stripe_webhook(request):
    """
    Stripe webhook handler. CSRF-exempt - security via stripe signature verification.
    Configure in Stripe dashboard to send:
      - checkout.session.completed
      - invoice.payment_succeeded
      - customer.subscription.deleted
      - customer.subscription.updated
    """
    s = _stripe_client()
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    try:
        event = s.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        logger.warning("Stripe webhook: invalid payload")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError:
        logger.warning("Stripe webhook: invalid signature")
        return HttpResponse(status=400)

    event_id = event['id']
    event_type = event['type']
    event_obj = event['data']['object']

    # Idempotency check: skip if already processed
    with get_db_session() as db:
        already = db.query(WebSubscriptionEvent).filter_by(stripe_event_id=event_id).first()
        if already:
            return HttpResponse(status=200)

    logger.info(f"Stripe webhook: {event_type} ({event_id})")

    try:
        if event_type == 'checkout.session.completed':
            _handle_checkout_completed(event_obj, event_id)

        elif event_type == 'invoice.payment_succeeded':
            _handle_invoice_paid(event_obj, event_id)

        elif event_type == 'customer.subscription.deleted':
            _handle_subscription_deleted(event_obj, event_id)

        elif event_type == 'customer.subscription.updated':
            _handle_subscription_updated(event_obj, event_id)

        else:
            # Log receipt but no action needed
            _log_stripe_event(None, event_type, event_id, None)

    except Exception as e:
        logger.error(f"Stripe webhook handler error for {event_type} ({event_id}): {e}", exc_info=True)
        return HttpResponse(status=500)

    return HttpResponse(status=200)


# =============================================================================
# Webhook event handlers
# =============================================================================

def _get_user_id_from_metadata(obj):
    """Extract web_user_id from Stripe object metadata. Returns int or None."""
    meta = obj.get('metadata') or {}
    raw = meta.get('web_user_id')
    if raw:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    # Fall back to subscription metadata if this is an invoice
    sub_meta = (obj.get('subscription_details') or {}).get('metadata') or {}
    raw = sub_meta.get('web_user_id')
    if raw:
        try:
            return int(raw)
        except (ValueError, TypeError):
            pass
    return None


def _handle_checkout_completed(session_obj, event_id):
    """checkout.session.completed - subscription activated."""
    user_id = _get_user_id_from_metadata(session_obj)
    customer_id = session_obj.get('customer')
    subscription_id = session_obj.get('subscription')

    if not user_id:
        logger.warning(f"checkout.session.completed: no web_user_id in metadata (event={event_id})")
        return

    now = int(time.time())
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).with_for_update().first()
        if not user:
            logger.warning(f"checkout.session.completed: user {user_id} not found")
            return

        user.is_hero = 1
        user.hero_expires_at = now + _MONTHLY_SECONDS
        if customer_id:
            user.stripe_customer_id = customer_id
        if subscription_id:
            user.stripe_subscription_id = subscription_id

        _queue_hero_role(db, user_id, 'set_hero')
        db.add(WebSubscriptionEvent(
            user_id=user_id,
            event_type='activated',
            stripe_event_id=event_id,
            amount_cents=None,
            created_at=now,
        ))
        db.commit()

    # One-time XP bonus for becoming a Champion (ref_id=event_id prevents duplicate award)
    try:
        award_xp(user_id, 'champion_sub', ref_id=hash(event_id) % 2147483647)
    except Exception as e:
        logger.warning(f"Champion XP award failed for user {user_id}: {e}")

    logger.info(f"Hero subscription activated: user={user_id} customer={customer_id}")


def _handle_invoice_paid(invoice_obj, event_id):
    """invoice.payment_succeeded - renewal payment received."""
    # Look up user via customer_id stored on the user
    customer_id = invoice_obj.get('customer')
    amount_cents = invoice_obj.get('amount_paid')
    # Determine billing interval from the subscription lines
    interval = 'month'
    try:
        lines = invoice_obj.get('lines', {}).get('data', [])
        if lines:
            interval = lines[0].get('price', {}).get('recurring', {}).get('interval', 'month')
    except Exception:
        pass

    duration = _YEARLY_SECONDS if interval == 'year' else _MONTHLY_SECONDS
    now = int(time.time())

    with get_db_session() as db:
        user = None
        if customer_id:
            user = db.query(WebUser).filter_by(stripe_customer_id=customer_id).with_for_update().first()
        if not user:
            logger.warning(f"invoice.payment_succeeded: no user for customer={customer_id}")
            _log_stripe_event(None, 'renewed', event_id, amount_cents)
            return

        # Extend from current expiry or now, whichever is later
        base = max(user.hero_expires_at or now, now)
        user.hero_expires_at = base + duration
        user.is_hero = 1

        # Ensure Hero role is set (in case it was cleared somehow)
        _queue_hero_role(db, user.id, 'set_hero')
        db.add(WebSubscriptionEvent(
            user_id=user.id,
            event_type='renewed',
            stripe_event_id=event_id,
            amount_cents=amount_cents,
            created_at=now,
        ))
        db.commit()

    logger.info(f"Hero subscription renewed: user={user.id} amount={amount_cents}")


def _handle_subscription_deleted(sub_obj, event_id):
    """customer.subscription.deleted - cancelled/expired."""
    customer_id = sub_obj.get('customer')
    now = int(time.time())

    with get_db_session() as db:
        user = None
        if customer_id:
            user = db.query(WebUser).filter_by(stripe_customer_id=customer_id).with_for_update().first()
        if not user:
            logger.warning(f"subscription.deleted: no user for customer={customer_id}")
            _log_stripe_event(None, 'cancelled', event_id, None)
            return

        user.is_hero = 0
        user.hero_expires_at = None
        user.stripe_subscription_id = None

        _queue_hero_role(db, user.id, 'clear_hero')
        db.add(WebSubscriptionEvent(
            user_id=user.id,
            event_type='cancelled',
            stripe_event_id=event_id,
            amount_cents=None,
            created_at=now,
        ))
        db.commit()

    logger.info(f"Hero subscription cancelled: user={user.id}")


def _handle_subscription_updated(sub_obj, event_id):
    """customer.subscription.updated - catches plan changes, pause, etc."""
    status = sub_obj.get('status')
    customer_id = sub_obj.get('customer')
    now = int(time.time())

    # If subscription becomes inactive due to payment failure, etc.
    if status in ('past_due', 'unpaid', 'paused', 'incomplete_expired'):
        with get_db_session() as db:
            user = None
            if customer_id:
                user = db.query(WebUser).filter_by(stripe_customer_id=customer_id).with_for_update().first()
            if user:
                user.is_hero = 0
                _queue_hero_role(db, user.id, 'clear_hero')
                db.add(WebSubscriptionEvent(
                    user_id=user.id,
                    event_type='expired',
                    stripe_event_id=event_id,
                    amount_cents=None,
                    created_at=now,
                ))
                db.commit()
                logger.info(f"Hero subscription paused/expired: user={user.id} status={status}")


def _log_stripe_event(user_id, event_type, event_id, amount_cents):
    """Log a Stripe event with no other side effects."""
    try:
        with get_db_session() as db:
            db.add(WebSubscriptionEvent(
                user_id=user_id or 0,
                event_type=event_type,
                stripe_event_id=event_id,
                amount_cents=amount_cents,
                created_at=int(time.time()),
            ))
            db.commit()
    except Exception as e:
        logger.warning(f"_log_stripe_event failed: {e}")
