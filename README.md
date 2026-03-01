# Casual Heroes - QuestLog

A full-stack web platform for gaming communities. Includes a public-facing site, the QuestLog social platform (profiles, posts, communities, LFG, game discovery, XP/flair system), game server management via AMP, Discord bot integration, and admin tooling.

Built with Django 5.2 and SQLAlchemy on top of MySQL/MariaDB.

---

## Features

### QuestLog Social Platform (`/ql/`)
- Username/password registration with email verification
- Social feed - posts, image uploads (WebP, Pillow validated), video embeds (YouTube, Twitch, TikTok, Kick, X)
- Likes, comments, comment likes, follows, user blocking
- XP system, levels, rank titles, purchasable flairs
- Communities (Discovery Network) - create, join, admin approval workflow
- LFG (Looking for Group) - create and join groups by game
- Game discovery - Steam + IGDB integration
- Creator profiles with Twitch/YouTube integration
- Game server status and rotation voting polls
- Giveaways / raffles
- Optional Steam linking (game tracking, achievements, now playing - enrichment only, not auth)
- Optional Discord account linking
- 2FA (TOTP) for users
- GDPR data export, data summary, account deletion

### Main Site
- Game server status page (AMP/CubeCoders integration)
- Games we play, game suggestions, guides, hosting info
- RSS/article integration
- Markdown documentation viewer (selfhost guide)

### Admin Panel (`/ql/admin/`)
- 5-layer security: honeypot, timing check, Cloudflare Turnstile CAPTCHA, Django auth, WebUser admin check
- User management, ban/disable, audit log
- Community approval queue
- Creator COTW/COTM rotation
- Server polls, giveaway management
- Flair shop and rank title CRUD
- XP leaderboard
- RSS feed management
- Maintenance mode toggle

### Security
- CSRF protection on all state-changing requests
- Rate limiting (`django-ratelimit`) on all sensitive endpoints
- Cloudflare Turnstile CAPTCHA on registration and admin login
- Input sanitization (`bleach`, `Pillow`) on all user content
- SSRF protection on all outbound URL fetches
- Soft-delete with GDPR hard-delete after 90-day retention via management command
- Audit logging with hashed IPs (SHA-256) and truncated user-agents
- Secrets stored outside repo in `/etc/your-org/secrets.env`
- SRI on all fixed CDN resources (Alpine.js, Font Awesome, DOMPurify)
- Content-Security-Policy, HSTS, X-Frame-Options, X-Content-Type-Options headers

---

## Tech Stack

| Layer | Tech |
|---|---|
| Framework | Django 5.2 |
| ORM | SQLAlchemy 2.0 (not Django ORM) |
| Database | MySQL / MariaDB |
| Frontend | Tailwind CSS (dark theme), vanilla JS, Alpine.js |
| Images | Pillow (WebP conversion + validation) |
| Auth | Django built-in (username/password) |
| Rate limiting | django-ratelimit |
| Sanitization | bleach, Pillow |
| Encryption | cryptography (Fernet) for OAuth tokens |
| Captcha | Cloudflare Turnstile |
| Payments | Stripe (optional) |

---

## Related Repos

- [CasualHeroes/WardenBot](https://github.com/CasualHeroes/WardenBot) - Discord bot that pairs with this platform

---

## Quick Start

### Requirements

- Python 3.11+
- MySQL / MariaDB 8+
- A Cloudflare Turnstile site key (free) for CAPTCHA on registration/admin login

### 1. Clone and install

```bash
git clone https://github.com/CasualHeroes/platform.git
cd platform
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

For production, place secrets at `/etc/your-org/secrets.env` (loaded automatically if present). See [Environment Variables](#environment-variables) below.

### 3. Create databases

```bash
# Main Django/QuestLog database
mysql -u root -e "CREATE DATABASE questlog_web CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -e "CREATE USER 'ql_user'@'localhost' IDENTIFIED BY 'yourpassword';"
mysql -u root -e "GRANT ALL PRIVILEGES ON questlog_web.* TO 'ql_user'@'localhost';"

# Warden bot database (for Discord bot integration - skip if not using WardenBot)
mysql -u root -e "CREATE DATABASE warden CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -e "GRANT ALL PRIVILEGES ON warden.* TO 'ql_user'@'localhost';"
```

### 4. Run Django migrations

```bash
python manage.py migrate
```

### 5. Run SQLAlchemy migration scripts

These create the QuestLog-specific tables (SQLAlchemy models, not Django migrations):

```bash
python app/questlog_web/scripts/create_hero_points_tables.py
python app/questlog_web/scripts/create_referral_tables.py
python app/questlog_web/scripts/create_rss_feed_settings.py
python app/questlog_web/scripts/create_steam_now_playing.py
python app/questlog_web/scripts/create_user_totp_table.py
python app/questlog_web/scripts/create_xp_flair_tables.py
python app/questlog_web/scripts/create_server_poll_tables.py
python app/questlog_web/scripts/create_platform_types_update.py
python app/questlog_web/scripts/create_user_prefs_columns.py
```

### 6. Create a superuser

```bash
python manage.py createsuperuser
```

Then in the database, set `is_admin = 1` on your `web_users` row for the admin panel.

### 7. Run

```bash
python manage.py runserver
```

QuestLog is at `http://localhost:8000/ql/`.

---

## Environment Variables

Copy `.env.example` for the full list. Key variables:

### Required

| Variable | Description |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key. Generate: `python -c "import secrets; print(secrets.token_hex(50))"` |
| `ENCRYPTION_KEY` | Fernet key for OAuth token storage. Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `AUDIT_LOG_SALT` | Salt for IP hashing in audit logs. Generate: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DJANGO_DB_PASSWORD` | MySQL password for the Django/QuestLog database |

### Domain

| Variable | Default | Description |
|---|---|---|
| `BASE_DOMAIN` | `localhost` | Root domain (e.g. `example.com`) |
| `DASHBOARD_DOMAIN` | `dashboard.<BASE_DOMAIN>` | Dashboard subdomain |
| `EXTRA_ALLOWED_HOSTS` | *(empty)* | Comma-separated extra hosts |

### Database

| Variable | Default | Description |
|---|---|---|
| `DJANGO_DB_NAME` | `questlog_web` | Main DB name |
| `DJANGO_DB_USER` | *(empty)* | DB username |
| `DJANGO_DB_HOST` | `localhost` | DB host |
| `DJANGO_DB_PORT` | `3306` | DB port |
| `WARDEN_DB_NAME` | *(empty)* | WardenBot DB name |
| `WARDEN_DB_USER` | *(empty)* | WardenBot DB user |
| `WARDEN_DB_PASSWORD` | *(empty)* | WardenBot DB password |
| `WARDEN_DB_HOST` | *(empty)* | WardenBot DB host |

### Captcha (required for registration and admin login)

| Variable | Description |
|---|---|
| `TURNSTILE_SITE_KEY` | Cloudflare Turnstile site key (get at dash.cloudflare.com) |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret key |

### Site Config

| Variable | Description |
|---|---|
| `DISCORD_INVITE_URL` | Your Discord server invite (shown in sidebar and game listings) |
| `SITE_LOGO_URL` | Your site logo URL for Discord embed thumbnails |
| `GAME_SUGGESTION_WEBHOOK` | Discord webhook URL for game suggestions (server-side only) |

### Discord Bot Integration (WardenBot)

| Variable | Description |
|---|---|
| `DISCORD_BOT_TOKEN` | WardenBot bot token |
| `DISCORD_BOT_API_URL` | WardenBot local API URL (default: `http://localhost:8001`) |
| `DISCORD_BOT_API_TOKEN` | WardenBot API token for internal communication |
| `DISCORD_CLIENT_ID` | Discord OAuth2 client ID (for account linking) |
| `DISCORD_CLIENT_SECRET` | Discord OAuth2 client secret |
| `DISCORD_REDIRECT_URI_QL` | Discord OAuth2 callback URL for QuestLog linking |

### Optional Integrations

| Variable | Description |
|---|---|
| `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` | IGDB game database (Twitch dev credentials) |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe for donations/payments |
| `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` / `YOUTUBE_API_KEY` | YouTube OAuth for creator profiles |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Twitch OAuth for creator profiles |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | SMTP (Gmail app password) for verification emails |
| `AMP_URL` / `AMP_USER` / `AMP_PASSWORD` | AMP (CubeCoders) game server panel |
| `BOT_OWNER_ID` / `BOT_OWNER_MAIN_SERVER` | Discord bot owner config |

---

## Project Structure

```
platform/
- app/
  - questlog_web/          - QuestLog social platform app
    - models.py            - SQLAlchemy ORM models (all web_ prefixed tables)
    - helpers.py           - XP, flairs, audit logging, serialization
    - urls.py              - URL patterns (all under /ql/)
    - views_auth.py        - Registration, login, logout, 2FA, OAuth callbacks
    - views_pages.py       - Feed, home, game servers, polls
    - views_social.py      - Posts, comments, likes, follows, blocks, notifications
    - views_profile.py     - Profile editing, account deletion, GDPR export
    - views_admin.py       - Admin panel APIs
    - views_discovery.py   - Communities, LFG, creators, games, articles
    - views_uploads.py     - Image upload handling (Pillow + WebP)
    - amp_utils.py         - AMP game server panel utilities
    - steam_auth.py        - Steam OpenID (optional enrichment, not auth)
    - steam_search.py      - Steam game search
    - scripts/             - One-time SQLAlchemy migration scripts
    - templates/
      - questlog_web/      - All QuestLog HTML templates
        - partials/        - Shared components (sidebar, post card, custom select)
  - templates/             - Main site templates (non-QuestLog pages)
  - views.py               - Main site views (game servers, home, etc.)
  - urls.py                - Main site URL config
  - db.py                  - SQLAlchemy engine + session factory (get_db_session)
  - middleware.py           - Domain redirect middleware
  - security_middleware.py  - Maintenance mode middleware
  - rss_utils.py           - SSRF-protected RSS fetcher
- casualsite/
  - settings.py            - Django settings
  - urls.py                - Root URL config (includes /ql/ and main site)
- requirements.txt
- manage.py
- .env.example
```

---

## Architecture Notes

- **ORM**: SQLAlchemy for all QuestLog tables. Django ORM only for Django auth (sessions, users).
- **Timestamps**: Unix epoch `BigInteger` (`int(time.time())`) - not `DateTimeField`.
- **JSON columns**: Stored as `Text`, parsed with `json.loads()`.
- **DB access**: `with get_db_session() as db:` context manager.
- **Decorators**: `@web_login_required`, `@web_admin_required`, `@add_web_user_context`.
- **Rate limiting**: `django-ratelimit` on all write/auth endpoints.
- **Images**: Uploaded images are Pillow-validated, EXIF-stripped, and converted to WebP before saving to `media/uploads/`. Videos are embed-only (YouTube, Twitch, TikTok, Kick, X, Instagram).
- **Secrets**: Never in the repo. In development use `.env`. In production place at `/etc/your-org/secrets.env` (owner root, group www-data, mode 640).

---

## Cron Jobs

Add to crontab for GDPR data cleanup (hard-deletes soft-deleted posts/comments after 90 days, prunes old notifications and audit logs):

```
0 3 * * * /path/to/venv/bin/python /path/to/manage.py cleanup_deleted_content >> /path/to/logs/cleanup.log 2>&1
```

---

## Production Deployment

This project runs in production behind Nginx + Gunicorn. A typical setup:

- **Nginx**: Reverse proxy, SSL termination, static file serving
- **Gunicorn**: WSGI server (4-8 workers depending on CPU)
- **MariaDB**: Database (can run on same or separate host)
- **Cloudflare**: CDN, DDoS protection, Turnstile CAPTCHA
- **Let's Encrypt**: TLS certificates via Certbot

For game server management, [AMP by CubeCoders](https://cubecoders.com/AMP) manages individual game server instances. The platform reads server status via the AMP API.

### AMP vs Pterodactyl

This platform currently uses **AMP (CubeCoders)**. AMP is commercial (one-time license fee) but extremely feature-rich: native support for dozens of games, built-in scheduler, backups, console access, automatic updates, and a REST API. It is more capable out of the box than any open-source alternative for serious multi-game hosting.

**[Pterodactyl](https://pterodactyl.io/)** is the most popular open-source alternative. It is Docker-based, free, has a large community, and is widely adopted for Minecraft/general hosting. If you want to swap AMP out for Pterodactyl:

- Remove `app/questlog_web/amp_utils.py` and the AMP config from `app/views.py`
- Replace with Pterodactyl's API client (community Python SDKs available)
- Update the game server status views in `app/views.py` (`game_servers_ql`, `fetch_instance_data`) to call the Pterodactyl API instead

The game server voting/poll system in QuestLog (`WebServerPoll`) is completely independent of AMP/Pterodactyl and requires no changes.

**Why AMP was chosen for this project:**
AMP was selected for its ease of use. Installing a new game server in AMP is a few clicks - pick a game, configure ports, hit deploy. There is no Docker knowledge required, no writing custom "eggs" or container definitions, and no managing Wings nodes. For a community that rotates between many different games (7 Days to Die, Valheim, V Rising, Enshrouded, etc.), AMP's native support for dozens of games out of the box made it significantly faster to get servers up and running. The built-in web console, automated update scheduling, and one-click backup system also reduce operational overhead compared to Pterodactyl.

**Can every AMP feature be replicated in Pterodactyl?** Yes, but with more work:
- Game server instances - supported via Docker eggs (community-maintained)
- Console access - available in Pterodactyl's panel
- Automated updates - can be scripted via startup commands or install scripts
- Backups - available via Pterodactyl's backup system (local or S3)
- Scheduling - available via Pterodactyl's schedule manager
- REST API - Pterodactyl has a full application + client API

The platform integration (`amp_utils.py`) would need to be rewritten to use Pterodactyl's API, but all the QuestLog features (game server voting polls, server status display, game rotation) would work identically after the API swap.

**Trade-offs:**
| | AMP | Pterodactyl |
|---|---|---|
| Cost | Paid license | Free / open source |
| Game support | 100+ games natively | Community Docker eggs |
| Setup complexity | Low (wizard-based) | Higher (Docker, Wings nodes) |
| API | REST + WebSocket | REST |
| Backups | Built-in | Built-in |
| Update management | Built-in scheduler | Startup scripts |
| Best for | Ease of use, multi-game hosting | Open source, Docker-native setups |

---

## Auth Flow

Registration and login use Django's built-in username/password system. Email verification is required before login.

Steam is an **optional enrichment** feature only - users can link their Steam account after registration to unlock game tracking (hours played, achievements, now playing). Steam is never used for authentication.

Discord can optionally be linked for account features. The admin panel uses a separate hardened login flow with 5 security layers.

---

## License

See [LICENSE](LICENSE).
