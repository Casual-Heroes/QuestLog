#!/usr/bin/env python3
"""
Stripe Product Setup Script

This script creates all necessary products and prices in Stripe for the modular subscription system.
Run this once to set up your Stripe account with all module products.

Usage:
    python setup_stripe_products.py

Requirements:
    - STRIPE_SECRET_KEY environment variable must be set
    - Stripe API key must have write permissions
"""
import os
import sys

# Add project directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')
import django
django.setup()

from django.conf import settings
import stripe

from app.modules_config import MODULES, BUNDLES

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

def create_module_products():
    """Create Stripe products and prices for all modules."""
    print("=" * 60)
    print("Creating Stripe Products for Warden Bot Modules")
    print("=" * 60)
    print()

    if not stripe.api_key:
        print("❌ Error: STRIPE_SECRET_KEY not configured!")
        print("Please set the STRIPE_SECRET_KEY environment variable in your .env file.")
        return False

    print(f"Using Stripe API key: {stripe.api_key[:12]}...")
    print(f"Test mode: {settings.STRIPE_TEST_MODE}")
    print()

    products_created = []

    def find_existing_product(meta_key, meta_value, fallback_name):
        # Try to locate an existing product by metadata or name
        try:
            products = stripe.Product.list(limit=100)
            for p in products.auto_paging_iter():
                if p.metadata.get(meta_key) == meta_value:
                    return p
                if p.name == fallback_name:
                    return p
        except Exception:
            return None
        return None

    def find_existing_price(product_id, amount_cents, interval):
        try:
            prices = stripe.Price.list(product=product_id, active=True, limit=100)
            for price in prices.auto_paging_iter():
                if (
                    price.unit_amount == amount_cents and
                    price.recurring and price.recurring.get('interval') == interval
                ):
                    return price
        except Exception:
            return None
        return None

    # Create module products
    print("Creating module products...")
    print("-" * 60)

    for module_key, module_config in MODULES.items():
        try:
            print(f"\n📦 Ensuring product: {module_config['name']}")

            # Locate existing or create product
            product = find_existing_product('module_key', module_key, module_config['name'])
            if product:
                print(f"   • Reusing product: {product.id}")
            else:
                product = stripe.Product.create(
                    name=module_config['name'],
                    description=module_config['description'],
                    metadata={
                        'module_key': module_key,
                        'type': 'module',
                    }
                )
                print(f"   ✓ Product created: {product.id}")

            # Monthly price
            monthly_cents = int(module_config['price_monthly'] * 100)
            price_monthly = find_existing_price(product.id, monthly_cents, 'month')
            if price_monthly:
                print(f"   • Reusing monthly price: {price_monthly.id}")
            else:
                price_monthly = stripe.Price.create(
                    product=product.id,
                    unit_amount=monthly_cents,
                    currency='usd',
                    recurring={'interval': 'month'},
                    metadata={
                        'module_key': module_key,
                        'billing_cycle': 'monthly',
                    }
                )
                print(f"   ✓ Monthly price created: {price_monthly.id} (${module_config['price_monthly']}/month)")

            # Yearly price
            yearly_cents = int(module_config['price_yearly'] * 100)
            price_yearly = find_existing_price(product.id, yearly_cents, 'year')
            if price_yearly:
                print(f"   • Reusing yearly price: {price_yearly.id}")
            else:
                price_yearly = stripe.Price.create(
                    product=product.id,
                    unit_amount=yearly_cents,
                    currency='usd',
                    recurring={'interval': 'year'},
                    metadata={
                        'module_key': module_key,
                        'billing_cycle': 'yearly',
                    }
                )
                print(f"   ✓ Yearly price created: {price_yearly.id} (${module_config['price_yearly']}/year)")

            products_created.append({
                'module_key': module_key,
                'product_id': product.id,
                'price_monthly_id': price_monthly.id,
                'price_yearly_id': price_yearly.id,
            })

        except Exception as e:
            print(f"   ❌ Error creating {module_key}: {e}")

    # Create bundle products
    print("\n" + "-" * 60)
    print("Creating bundle products...")
    print("-" * 60)

    for bundle_key, bundle_config in BUNDLES.items():
        try:
            print(f"\n📦 Ensuring bundle: {bundle_config['name']}")

            product_name = f"Warden Bot - {bundle_config['name']}"
            product = find_existing_product('bundle_key', bundle_key, product_name)
            if product:
                print(f"   • Reusing product: {product.id}")
            else:
                product = stripe.Product.create(
                    name=product_name,
                    description=bundle_config['description'],
                    metadata={
                        'bundle_key': bundle_key,
                        'type': 'bundle',
                    }
                )
                print(f"   ✓ Product created: {product.id}")

            # Monthly price
            monthly_cents = int(bundle_config['price_monthly'] * 100)
            price_monthly = find_existing_price(product.id, monthly_cents, 'month')
            if price_monthly:
                print(f"   • Reusing monthly price: {price_monthly.id}")
            else:
                price_monthly = stripe.Price.create(
                    product=product.id,
                    unit_amount=monthly_cents,
                    currency='usd',
                    recurring={'interval': 'month'},
                    metadata={
                        'bundle_key': bundle_key,
                        'billing_cycle': 'monthly',
                    }
                )
                print(f"   ✓ Monthly price created: {price_monthly.id} (${bundle_config['price_monthly']}/month)")

            # Yearly price
            yearly_cents = int(bundle_config['price_yearly'] * 100)
            price_yearly = find_existing_price(product.id, yearly_cents, 'year')
            if price_yearly:
                print(f"   • Reusing yearly price: {price_yearly.id}")
            else:
                price_yearly = stripe.Price.create(
                    product=product.id,
                    unit_amount=yearly_cents,
                    currency='usd',
                    recurring={'interval': 'year'},
                    metadata={
                        'bundle_key': bundle_key,
                        'billing_cycle': 'yearly',
                    }
                )
                print(f"   ✓ Yearly price created: {price_yearly.id} (${bundle_config['price_yearly']}/year)")

            products_created.append({
                'bundle_key': bundle_key,
                'product_id': product.id,
                'price_monthly_id': price_monthly.id,
                'price_yearly_id': price_yearly.id,
            })

        except Exception as e:
            print(f"   ❌ Error creating {bundle_key}: {e}")

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"\n✅ Created {len(products_created)} products in Stripe")
    print("\n📋 Next steps:")
    print("1. Update app/modules_config.py with the following IDs:")
    print()

    for item in products_created:
        if 'module_key' in item:
            print(f"  '{item['module_key']}': {{")
            print(f"    'stripe_product_id': '{item['product_id']}',")
            print(f"    'stripe_price_monthly_id': '{item['price_monthly_id']}',")
            print(f"    'stripe_price_yearly_id': '{item['price_yearly_id']}',")
            print(f"  }},")
        elif 'bundle_key' in item:
            print(f"  '{item['bundle_key']}': {{")
            print(f"    'stripe_product_id': '{item['product_id']}',")
            print(f"    'stripe_price_monthly_id': '{item['price_monthly_id']}',")
            print(f"    'stripe_price_yearly_id': '{item['price_yearly_id']}',")
            print(f"  }},")

    print()
    print("2. Set up webhook endpoint in Stripe dashboard:")
    print(f"   URL: https://your-domain.com/webhooks/stripe/")
    print("   Events to listen for:")
    print("   - checkout.session.completed")
    print("   - customer.subscription.updated")
    print("   - customer.subscription.deleted")
    print("   - invoice.payment_failed")
    print()
    print("3. Copy the webhook signing secret to your .env file:")
    print("   STRIPE_WEBHOOK_SECRET=whsec_...")
    print()
    print("4. Restart your web server")
    print()

    return True


if __name__ == "__main__":
    try:
        success = create_module_products()
        if success:
            print("✅ Stripe setup completed successfully!")
            sys.exit(0)
        else:
            print("❌ Stripe setup failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
