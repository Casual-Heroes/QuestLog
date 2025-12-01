# warden/webhook_server.py - Stripe Webhook Server
"""
Simple aiohttp web server for Stripe webhooks.

Run alongside your bot or as a separate process.

Usage:
    python -m warden.webhook_server

Or import and run in your bot:
    from warden.webhook_server import start_webhook_server
    await start_webhook_server(bot, port=8080)
"""

import os
import asyncio
from aiohttp import web

from warden.config import logger, STRIPE_WEBHOOK_SECRET


async def create_webhook_app(bot=None):
    """Create the aiohttp web application."""
    app = web.Application()

    async def health_check(request):
        """Health check endpoint."""
        return web.json_response({"status": "ok", "service": "warden-webhooks"})

    async def stripe_webhook(request):
        """Handle Stripe webhook events."""
        payload = await request.read()
        sig_header = request.headers.get("Stripe-Signature")

        if not sig_header:
            return web.json_response(
                {"error": "Missing Stripe-Signature header"},
                status=400
            )

        # Get billing cog from bot
        if bot:
            billing_cog = bot.get_cog("BillingCog")
            if billing_cog:
                result = await billing_cog.handle_stripe_webhook(payload, sig_header)
                if result["success"]:
                    return web.json_response(result)
                else:
                    return web.json_response(result, status=400)

        # If no bot/cog, handle directly
        try:
            import stripe
            from warden.config import STRIPE_API_KEY
            stripe.api_key = STRIPE_API_KEY

            event = stripe.Webhook.construct_event(
                payload, sig_header, STRIPE_WEBHOOK_SECRET
            )

            logger.info(f"Received Stripe event: {event['type']}")

            # Basic handling without bot
            return web.json_response({
                "success": True,
                "message": f"Received {event['type']}",
                "note": "Bot not connected - event logged only"
            })

        except ValueError as e:
            return web.json_response({"error": "Invalid payload"}, status=400)
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return web.json_response({"error": str(e)}, status=400)

    # Routes
    app.router.add_get("/health", health_check)
    app.router.add_post("/webhooks/stripe", stripe_webhook)

    return app


async def start_webhook_server(bot=None, host="0.0.0.0", port=8080):
    """
    Start the webhook server.

    Args:
        bot: Discord bot instance (to access BillingCog)
        host: Host to bind to
        port: Port to listen on
    """
    app = await create_webhook_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()

    site = web.TCPSite(runner, host, port)
    await site.start()

    logger.info(f"Webhook server started on http://{host}:{port}")
    logger.info(f"Stripe webhook endpoint: http://{host}:{port}/webhooks/stripe")

    return runner


async def main():
    """Run webhook server standalone."""
    port = int(os.getenv("WEBHOOK_PORT", 8080))
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")

    runner = await start_webhook_server(host=host, port=port)

    try:
        # Keep running
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
