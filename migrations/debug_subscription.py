#!/usr/bin/env python3
"""Debug subscription object from Stripe."""

import os
import sys
sys.path.insert(0, '/srv/ch-webserver')

from dotenv import load_dotenv
load_dotenv('/srv/ch-webserver/.env')

import stripe
import json

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

subscription_id = 'sub_1ScZ3mCqgyN1IYjd3huIBShS'

print(f"Fetching subscription {subscription_id}...")
subscription = stripe.Subscription.retrieve(subscription_id)

# Print full subscription object
print("\n" + "="*80)
print("FULL SUBSCRIPTION OBJECT:")
print("="*80)
print(json.dumps(dict(subscription), indent=2, default=str))
