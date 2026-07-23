# Anti-scraping protection

QuestLog uses layered controls because `robots.txt` alone is voluntary and a
public page can never be made impossible to copy.

## Origin controls

`ScrapingProtectionMiddleware` protects the public directories and their JSON
APIs:

- known SEO, AI, and generic automation clients are denied;
- anonymous clients are limited to 30 directory requests per 60 seconds;
- authenticated QuestLog users and intentional search/social preview agents
  bypass that anonymous budget;
- all JSON GET responses receive `X-Robots-Tag: noindex, nofollow, nosnippet`;
- EldenTracker catalog sync, OBS overlays, live run polling, authentication, and
  ordinary site navigation are outside the protected route set.

The limits can be adjusted without code changes:

```env
SCRAPE_RATE_LIMIT=30
SCRAPE_RATE_WINDOW_SECONDS=60
```

The canonical policy is `static/robots.txt`. The `/robots.txt` Django route
serves that file directly so the live and repository policies cannot drift.

## Cloudflare controls

Origin enforcement is the fallback. Cloudflare should stop automation before it
uses application resources.

1. Enable **Bot Fight Mode** (or Super Bot Fight Mode when available).
2. Keep verified search-engine and social-preview bots allowed.
3. Enable AI crawler controls and block AI training.
4. Add a rate-limiting rule for the enumerable paths below, excluding verified
   bots, with a Managed Challenge after approximately 30 requests per minute:

   - `/api/gamers/`
   - `/api/creators/`
   - `/api/communities/`
   - `/api/soulslike/builds/`
   - `/gamers/`
   - `/creators/`
   - `/communities/`
   - `/u/`
   - `/soulslike/builds/`
   - `/soulslike/community-runs/`

5. Do not include `/api/soulslike/data/` or
   `/api/soulslike/session/` in that rule; the desktop catalog updater and live
   overlays intentionally use those endpoints.
6. Restrict the origin firewall to Cloudflare IP ranges. Otherwise a scraper can
   bypass Cloudflare and can spoof forwarding headers used for client-IP
   accounting.

Review Cloudflare Security Events after deployment and tune the rate only when
there is evidence of a human false positive.

## Personal contact information

QuestLog does not store or publish telephone numbers. The public contact page
uses role-based email addresses. When unsolicited sales messages contain a
private telephone number, check domain registration, trademark/business
filings, social profiles, and data-broker/enrichment services as separate
sources. Application anti-scraping controls cannot remove information already
held by those providers.
