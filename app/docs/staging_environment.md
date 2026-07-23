# QuestLog development and staging environment

QuestLog development must never run with the production environment file.
Both Django's ORM database and the SQLAlchemy QuestLog database must be
isolated.

## Required environment

The private development environment file must contain at least:

```dotenv
QUESTLOG_ENVIRONMENT=development
DJANGO_SECRET_KEY=<development-only value>
ENCRYPTION_KEY=<development-only Fernet key>
BOT_INTERNAL_SECRET=<development-only value>

DJANGO_DB_NAME=django_webapp_test
DJANGO_DB_USER=<test-only user>
DJANGO_DB_PASSWORD=<test-only password>
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=3306

WARDEN_DB_NAME=questlog_test
WARDEN_DB_USER=<test-only user>
WARDEN_DB_PASSWORD=<test-only password>
WARDEN_DB_HOST=localhost
WARDEN_DB_PORT=3306
```

Database names are required to include `dev`, `test`, or `staging`. Django
refuses to start otherwise.

Do not add AMP, bot, production OAuth, SMTP, webhook, or Stripe credentials.
Non-production settings blank those credentials as defense in depth.

## Local development server

```bash
QUESTLOG_ENV_FILE=/absolute/path/to/.env.dev \
DJANGO_SETTINGS_MODULE=casualsite.settings_dev \
python manage.py runserver 127.0.0.1:8001
```

Use an SSH tunnel from the development workstation:

```bash
ssh -L 8001:127.0.0.1:8001 <user>@<server>
```

Then visit `http://127.0.0.1:8001/`.

## Promotion

1. Develop on a feature branch.
2. Merge the feature into `dev`.
3. Deploy `dev` to the isolated staging worktree.
4. Run tests and browser acceptance checks.
5. Merge the tested commit into `main`.
6. Deploy `main` to production.
