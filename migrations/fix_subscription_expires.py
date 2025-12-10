#!/usr/bin/env python3
"""Fix subscription_expires by fetching current_period_end from Stripe."""

import os
import sys
sys.path.insert(0, '/srv/ch-webserver')

# Load environment variables
from dotenv import load_dotenv
load_dotenv('/srv/ch-webserver/.env')

import stripe
from app.db import get_db_session
from app.models import Guild

# Configure Stripe
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

# Guild ID and subscription ID from database
guild_id = 1344148178655514718
subscription_id = 'sub_1ScZ3mCqgyN1IYjd3huIBShS'

print(f"Fetching subscription {subscription_id} from Stripe...")
subscription = stripe.Subscription.retrieve(subscription_id)

print(f"\nSubscription data:")
print(f"  Status: {subscription['status']}")
print(f"  Current period start: {subscription.get('current_period_start')}")
print(f"  Current period end: {subscription.get('current_period_end')}")
print(f"  Billing cycle: {subscription['items']['data'][0]['price']['recurring']}")

current_period_end = subscription.get('current_period_end')

if current_period_end:
    print(f"\n✅ Found current_period_end: {current_period_end}")

    # Update database
    with get_db_session() as db:
        guild = db.query(Guild).filter_by(guild_id=guild_id).first()
        if guild:
            guild.subscription_expires = current_period_end
            db.commit()
            print(f"✅ Updated database - subscription_expires set to {current_period_end}")
        else:
            print(f"❌ Guild not found in database")
else:
    print(f"❌ current_period_end not found in subscription")
