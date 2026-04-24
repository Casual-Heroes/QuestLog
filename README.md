# Casual Heroes - QuestLog

A full-stack web platform for gaming communities. Includes a public-facing site, the QuestLog social platform (profiles, posts, communities, LFG, game discovery, XP/flair system), game server management via AMP, multi-platform bot integration, a real-time chat system (QuestChat), and admin tooling.

Built with Django 5.2 and SQLAlchemy on top of MySQL/MariaDB.

---

## Features

### QuestLog Social Platform (`/ql/`)
- Username/password registration with email verification
- Social feed - posts, image uploads (WebP, Pillow validated), video embeds (YouTube, Twitch, TikTok, Kick, X)
- Likes, comments, comment likes, follows, user blocking
- XP system, levels, rank titles, Legacy tier progression, purchasable flairs
- Communities (Discovery Network) - create, join, admin approval workflow
- LFG (Looking for Group) - create and join groups by game with game-specific role templates
- Game discovery - Steam + IGDB integration
- Creator profiles with Twitch/YouTube/Kick integration
- Game server status and rotation voting polls
- Giveaways / raffles
- Champion (supporter) status with Stripe subscription
- Optional Steam linking (game tracking, achievements, now playing - enrichment only, not auth)
- Optional Discord and Fluxer account linking
- 2FA (TOTP) for users
- GDPR data export, data summary, account deletion

### QuestChat (`/ql/qc/` API + standalone React SPA)
- Real-time chat via WebSocket gateway (Go)
- JWT Bearer auth with auth-as-first-message (no token in URL)
- Server/channel model, DMs between friends
- Message edit, delete (soft), reactions, reply threading
- Hover action toolbar, inline edit, reply bar, reaction pills
- Unread indicators on channels and DM list
- Flair, Legacy tier, and display name synced from QuestLog profile
- Friends system: add, accept/decline, remove, cancel pending request
- Block and ignore with DM lockout
- Per-server welcome messages set by owners
- Server moderation: kick and ban from right-click member context menu
- XP awarded per chat message (60s cooldown), unified with QuestLog XP system
- User/DM reporting with categorized reason codes
- Platform bad-actor registry for cross-server abuse tracking

### Bot Dashboards
- **Fluxer bot dashboard** (`/ql/fluxer/`) - web panel for the QuestLog Fluxer bot (Fluxer platform)
  - XP, welcome messages, moderation, LFG, live alerts, reaction roles, verification, bridge config, raffles, scheduled messages, audit log, flair management
- **Discord bot dashboard** (`/ql/discord/`) - web panel for the QuestLog Discord bot (WardenBot)
- **Matrix dashboard** (`/ql/matrix/`) - web panel for the QuestLogMatrix bot
  - Room management, member list, XP, moderation, welcome config, ban lists, RSS feeds

### Discord-Fluxer-Matrix Bridge
- Real-time cross-platform chat relay between Discord, Fluxer, and Matrix
- Message map, edit sync, delete sync, reaction sync, typing relay
- Per-guild bridge configuration

### Main Site
- Game server status page (AMP/CubeCoders integration)
- Games we play, game suggestions, guides, hosting info
- RSS/article integration
- Markdown documentation viewer

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
- QuestChat bad-actor registry (add, bulk import CSV, list)

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
- Internal service endpoints gated by `QC_INTERNAL_SECRET` + loopback-only REMOTE_ADDR check

---

## Tech Stack

| Layer | Tech |
|---|---|
| Framework | Django 5.2 |
| ORM | SQLAlchemy 2.0 (not Django ORM) |
| Database | MySQL / MariaDB |
| Frontend | Tailwind CSS (dark theme), vanilla JS, Alpine.js |
| Chat SPA | React 18 + Vite |
| Chat Gateway | Go (WebSocket hub, goroutine per client) |
| Images | Pillow (WebP conversion + validation) |
| Auth | Django built-in (username/password) |
| Rate limiting | django-ratelimit |
| Sanitization | bleach, Pillow |
| Encryption | cryptography (Fernet) for OAuth tokens |
| Captcha | Cloudflare Turnstile |
| Payments | Stripe |
| Data | pandas, numpy (leaderboard, bulk imports) |
| JWT | PyJWT (QuestChat API tokens) |

---

## Related Repos

- [Casual-Heroes/QuestLog-Bot](https://github.com/Casual-Heroes/QuestLog-Bot) - Discord bot (WardenBot) that pairs with this platform

---

## Quick Start

### Requirements

- Python 3.11+
- MySQL / MariaDB 8+
- Go 1.21+ (for QuestChat gateway, optional)
- Node.js 18+ (for QuestChat React SPA, optional)
- A Cloudflare Turnstile site key (free) for CAPTCHA on registration/admin login

### 1. Clone and install

```bash
git clone https://github.com/Casual-Heroes/QuestLog.git
cd QuestLog
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

These create the QuestLog-specific tables (SQLAlchemy models, not Django migrations).
Run each with `venv/bin/python3 <script>` from the project root:

```bash
python create_hero_points_tables.py
python create_referral_tables.py
python create_rss_feed_settings.py
python create_steam_now_playing.py
python create_user_totp_table.py
python create_xp_flair_tables.py
python create_server_poll_tables.py
python create_platform_types_update.py
python create_user_prefs_columns.py
python create_fluxer_webhook_tables.py
python create_giveaway_tables.py
python create_early_access_codes.py
python create_community_bot_config_table.py
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

### 8. QuestChat (optional)

The chat system has two additional components, each in their own repo/directory:

**Go gateway** (WebSocket server):
```bash
cd questchat-server
go build ./...
QC_INTERNAL_SECRET=your-secret ./questchat-server
```

**React SPA** (chat frontend):
```bash
cd questchat-web
npm install
npm run build
# Serve dist/ behind your web server at questchat.yourdomain.com
```

Both require `QC_INTERNAL_SECRET` to match the value set in Django's environment.

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

### QuestChat

| Variable | Description |
|---|---|
| `QC_INTERNAL_SECRET` | Shared secret between Django and the Go gateway for internal service calls |

### Optional Integrations

| Variable | Description |
|---|---|
| `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` | IGDB game database (Twitch dev credentials) |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe for Champion subscriptions |
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
  - questlog_web/              - QuestLog social platform app
    - models.py                - SQLAlchemy ORM models (101 tables, all web_ prefixed)
    - helpers.py               - XP, flairs, audit logging, serialization, safe_int
    - urls.py                  - URL patterns (all under /ql/)
    - views_auth.py            - Registration, login, logout, 2FA, OAuth callbacks
    - views_pages.py           - Feed, home, LFG, game servers, polls
    - views_social.py          - Posts, comments, likes, follows, blocks, notifications
    - views_profile.py         - Profile editing, account deletion, GDPR export
    - views_admin.py           - Admin panel APIs
    - views_discovery.py       - Communities, LFG browse, creators, games, articles
    - views_uploads.py         - Image upload handling (Pillow + WebP)
    - views_billing.py         - Stripe Champion subscription
    - views_2fa.py             - TOTP two-factor auth
    - views_bot_dashboard.py   - Fluxer + Discord bot web dashboards
    - views_matrix_dashboard.py - Matrix (QuestChat) bot web dashboard
    - views_questchat.py       - QuestChat REST API (JWT Bearer, 34+ endpoints)
    - views_internal.py        - Internal APIs for bot-to-site communication
    - amp_utils.py             - AMP game server panel utilities
    - steam_auth.py            - Steam OpenID (optional enrichment, not auth)
    - steam_search.py          - Steam game search
    - scripts/                 - One-time SQLAlchemy migration scripts (run manually)
    - templates/
      - questlog_web/          - All QuestLog HTML templates
        - partials/            - Shared components (sidebar, post card, custom select)
  - templates/                 - Main site templates (non-QuestLog pages)
    - questlog/                - Bot dashboard templates
  - views.py                   - Main site views (game servers, home, etc.)
  - urls.py                    - Main site URL config
  - db.py                      - SQLAlchemy engine + session factory (get_db_session)
  - middleware.py               - Domain redirect middleware
  - security_middleware.py      - Maintenance mode middleware
  - rss_utils.py               - SSRF-protected RSS fetcher
- casualsite/
  - settings.py                - Django settings (gitignored)
  - urls.py                    - Root URL config
- create_*.py                  - SQLAlchemy migration scripts (run from project root)
- requirements.txt
- manage.py
- .env.example
```

---

## Architecture Notes

- **ORM**: SQLAlchemy for all QuestLog tables (101 models). Django ORM only for Django auth (sessions, users).
- **Timestamps**: Unix epoch `BigInteger` (`int(time.time())`) - not `DateTimeField`.
- **JSON columns**: Stored as `Text`, parsed with `json.loads()`.
- **IDs**: `Integer` autoincrement - no UUIDs.
- **DB access**: `with get_db_session() as db:` context manager.
- **Decorators**: `@web_login_required`, `@web_admin_required`, `@add_web_user_context`.
- **Rate limiting**: `django-ratelimit` on all write/auth endpoints.
- **Safe parsing**: `safe_int(value, default, min_val, max_val)` in `helpers.py` - use for all request params.
- **Images**: Pillow-validated, EXIF-stripped, converted to WebP, saved to `media/uploads/`. Videos are embed-only.
- **Secrets**: Never in the repo. In development use `.env`. In production place at `/etc/your-org/secrets.env` (owner root, group www-data, mode 640).
- **Template directories**: `settings.py` is gitignored. Ensure `casualsite/settings.py` has both paths in `DIRS`:
  ```python
  'DIRS': [
      os.path.join(BASE_DIR, 'app', 'templates'),
      os.path.join(BASE_DIR, 'app', 'questlog_web', 'templates'),
  ],
  ```
- **Two separate bots**: WardenBot = Discord bot. QuestLogFluxer = Fluxer bot. IDs are never interchangeable.
- **QuestChat gateway**: Go WebSocket server using hub pattern (goroutine per client). Auth via first-message token frame. Scales to multiple nodes via Redis pub/sub swap in `hub.go`.
- **Internal APIs**: Service-to-service calls (Go gateway -> Django XP, bot -> site) are gated by `QC_INTERNAL_SECRET` header + loopback REMOTE_ADDR check. Never exposed through Nginx.

---

## Cron Jobs

GDPR cleanup - hard-deletes soft-deleted content after 90 days, prunes old notifications and audit logs:

```
0 3 * * * /path/to/venv/bin/python /path/to/manage.py cleanup_deleted_content >> /path/to/logs/cleanup.log 2>&1
```

---

## Production Deployment

This project runs in production behind Nginx + Gunicorn. A typical setup:

- **Nginx**: Reverse proxy, SSL termination, static file serving, serves QuestChat SPA `dist/` folder
- **Gunicorn**: WSGI server (4-8 workers depending on CPU)
- **Go gateway**: Runs as a systemd service, proxied from Nginx at `/ws`
- **MariaDB**: Database (can run on same or separate host)
- **Cloudflare**: CDN, DDoS protection, Turnstile CAPTCHA
- **Let's Encrypt**: TLS certificates via Certbot

For game server management, [AMP by CubeCoders](https://cubecoders.com/AMP) manages individual game server instances. The platform reads server status via the AMP API.

### AMP vs Pterodactyl

This platform currently uses **AMP (CubeCoders)**. AMP is commercial (one-time license fee) but extremely feature-rich: native support for dozens of games, built-in scheduler, backups, console access, automatic updates, and a REST API.

**[Pterodactyl](https://pterodactyl.io/)** is the most popular open-source alternative. To swap AMP for Pterodactyl:

- Remove `app/questlog_web/amp_utils.py` and the AMP config from `app/views.py`
- Replace with Pterodactyl's API client (community Python SDKs available)
- Update the game server status views in `app/views.py` to call the Pterodactyl API

The game server voting/poll system (`WebServerPoll`) is independent of AMP/Pterodactyl and requires no changes.

| | AMP | Pterodactyl |
|---|---|---|
| Cost | Paid license | Free / open source |
| Game support | 100+ games natively | Community Docker eggs |
| Setup complexity | Low (wizard-based) | Higher (Docker, Wings nodes) |
| API | REST + WebSocket | REST |
| Best for | Ease of use, multi-game hosting | Open source, Docker-native setups |

---

## Auth Flow

Registration and login use Django's built-in username/password system. Email verification is required before login.

Steam is an **optional enrichment** feature only - users can link their Steam account after registration to unlock game tracking (hours played, achievements, now playing). Steam is never used for authentication.

Discord and Fluxer can optionally be linked for account features and bot integration. The admin panel uses a separate hardened login flow with 5 security layers.

QuestChat uses short-lived JWT Bearer tokens issued by `POST /ql/qc/auth/token/` after Django credential verification. Tokens are sent as the first WebSocket frame (not in the URL) to avoid log exposure.

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

This means you can use, modify, and self-host QuestLog freely. If you run a modified version as a network service, you must release your modifications under the same license. You may not sell or relicense this software under proprietary terms.

See [LICENSE](LICENSE) for the full license text.
