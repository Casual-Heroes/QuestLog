# QuestLog Web

A web-native social platform for gamers built with Django. QuestLog lets players track games, connect with other gamers, join communities, and engage through a built-in social feed - all without any Discord dependency.

This is the public module extracted from the [Casual Heroes](https://casual-heroes.com) website. It is designed to drop into any Django project.

---

## Features

### Social Layer
- User posts with image uploads (WebP converted, Pillow validated) and video embeds (YouTube, Twitch, TikTok, Kick, X)
- Likes, comments, comment likes
- Follow/unfollow users
- User blocking
- Notification system

### Profiles
- Customizable banners and bios
- Favorite games, genres, gaming platforms, playstyle
- Steam integration (optional, enrichment only - not used for auth)
- Post history

### Communities (Discovery Network)
- Create and join gaming communities
- Admin approval workflow for new communities
- Community directory with tags and platform types (Matrix, TeamSpeak, Discord, Mumble, Guilded, and more)

### XP + Flair + Level System
- XP awarded for posts, comments, likes, follows, profile updates, and more
- Levels, rank titles (ARPG/soulslike themed by default), and purchasable flairs
- Leaderboard and admin management

### Game Server Voting
- Active server rotation polls
- One vote per user, changeable
- Admin tools to create polls and declare winners

### Security
- Django username/password auth (primary) with optional Steam linking (enrichment only)
- TOTP two-factor authentication
- Rate limiting on all sensitive endpoints via `django-ratelimit`
- CSRF protection on all state-changing requests
- Soft-delete with GDPR hard-delete after 90-day retention window
- Admin audit logging with hashed IPs
- Honeypot, CAPTCHA, and timing checks on admin login
- Maintenance mode with admin bypass
- Input sanitization via `bleach` and `Pillow`

### GDPR
- Data export endpoint
- Data deletion endpoint
- Data summary endpoint
- Automated cleanup management command (`cleanup_deleted_content`)

---

## Tech Stack

| Layer | Tech |
|---|---|
| Framework | Django 5.2 |
| ORM | SQLAlchemy (not Django ORM) |
| Database | MySQL / MariaDB |
| Frontend | Tailwind CSS (dark theme), vanilla JS |
| Images | Pillow (WebP conversion + validation) |
| Auth | Django built-in auth |
| Rate limiting | django-ratelimit |
| Sanitization | bleach |

---

## Directory Structure

```
questlog_web/
- models.py          - All SQLAlchemy models
- helpers.py         - XP, flair, audit, serialization helpers
- urls.py            - All URL patterns (base: /ql/)
- views_auth.py      - Registration, login, logout, 2FA
- views_pages.py     - Feed, profiles, polls, discovery
- views_social.py    - Posts, comments, likes, follows, blocks
- views_profile.py   - Profile editing, Steam linking
- views_admin.py     - Admin panel APIs
- views_uploads.py   - Image upload handling
- views_discovery.py - Community discovery and management
- amp_utils.py       - AMP game server panel integration
- steam_auth.py      - Steam OpenID auth (optional)
- steam_search.py    - Steam game search
```

---

## Setup

### Requirements

See `requirements.txt` in the parent project. Key dependencies:

```
Django>=5.2
SQLAlchemy
mysqlclient
Pillow
bleach
django-ratelimit
cryptography
```

### Environment Variables

Copy `.env.example` and fill in the required values:

```bash
cp .env.example .env
```

Required:
- `DJANGO_SECRET_KEY`
- `WARDEN_DB_*` - MySQL connection details
- `ENCRYPTION_KEY` - Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `AUDIT_LOG_SALT` - Generate with: `python -c "import secrets; print(secrets.token_hex(32))"`

Optional:
- `IGDB_CLIENT_ID` / `IGDB_CLIENT_SECRET` - Game database integration
- `DISCORD_BOT_TOKEN` - WardenBot integration
- `GAME_SUGGESTION_WEBHOOK` - Discord webhook for game suggestions (server-side only)
- `STRIPE_*` - Donation/payment integration
- `TWITCH_*` / `YOUTUBE_*` - Streaming integrations

### Database

Run the migration scripts in the project root to create all required tables:

```bash
python create_xp_flair_tables.py
python create_server_poll_tables.py
# etc.
```

### Cron Jobs

Add to crontab for GDPR data cleanup:

```
0 3 * * * /path/to/venv/bin/python /path/to/manage.py cleanup_deleted_content >> /path/to/logs/cleanup.log 2>&1
```

---

## License

See [LICENSE](../LICENSE).

---

## Related

- [Casual Heroes](https://casual-heroes.com) - The community this was built for
- [WardenBot](https://github.com/CasualHeroes/WardenBot) - The Discord bot that pairs with QuestLog
