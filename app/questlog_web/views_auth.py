# QuestLog Web — authentication & OAuth views

import re
import time
import json
import hmac
import logging
import secrets
import requests as _requests

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django_ratelimit.decorators import ratelimit
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.models import User as DjangoUser
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.core import signing
from django.core.mail import send_mail
from django.conf import settings as django_settings

from sqlalchemy import text as sa_text
from .models import WebUser, WebCreatorProfile, WebReferral, WebSiteConfig, WebFlair, WebUserFlair, WebEarlyAccessCode, WebXpEvent, WebHeroPointEvent
from app.db import get_db_session
from .fluxer_webhooks import notify_new_member as _fluxer_new_member
from .helpers import (
    get_web_user, web_login_required, STEAM_API_KEY, safe_redirect_url,
    award_hero_points, XP_TO_HP_THRESHOLD, HP_PER_THRESHOLD, HP_PER_LEVEL, _get_level_for_xp,
)
from .steam_auth import (
    get_steam_login_url,
    verify_steam_login,
    get_steam_user_profile,
)

logger = logging.getLogger(__name__)

# Discord OAuth constants for the QuestLog account-linking flow.
# Uses a dedicated redirect URI separate from the bot-dashboard OAuth flow.
_DISCORD_CLIENT_ID     = django_settings.DISCORD_CLIENT_ID
_DISCORD_CLIENT_SECRET = django_settings.DISCORD_CLIENT_SECRET
_DISCORD_REDIRECT_URI_QL = django_settings.DISCORD_REDIRECT_URI_QL  # e.g. https://casual-heroes.com/ql/auth/discord/link/callback/
_DISCORD_AUTH_URL  = 'https://discord.com/api/oauth2/authorize'
_DISCORD_TOKEN_URL = 'https://discord.com/api/oauth2/token'
_DISCORD_API       = 'https://discord.com/api/v10'

# Fluxer OAuth constants for QuestLog account linking.
_FLUXER_CLIENT_ID       = django_settings.FLUXER_CLIENT_ID
_FLUXER_CLIENT_SECRET   = django_settings.FLUXER_CLIENT_SECRET
_FLUXER_REDIRECT_URI_QL = django_settings.FLUXER_REDIRECT_URI_QL
_FLUXER_AUTH_URL        = 'https://web.fluxer.app/oauth2/authorize'
_FLUXER_TOKEN_URL       = 'https://api.fluxer.app/v1/oauth2/token'
_FLUXER_USERINFO_URL    = 'https://api.fluxer.app/v1/oauth2/userinfo'


def _get_remote_ip(request):
    """Return the real client IP, honouring Cloudflare headers."""
    xff = request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('HTTP_X_FORWARDED_FOR')
    return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')


def _verify_turnstile(token: str, remote_ip: str) -> bool:
    """Server-side verify a Cloudflare Turnstile token. Returns True if valid."""
    secret = django_settings.TURNSTILE_SECRET_KEY
    if not secret:
        return True  # Not configured (dev/test) — don't block
    if not token:
        return False
    try:
        resp = _requests.post(
            'https://challenges.cloudflare.com/turnstile/v0/siteverify',
            data={'secret': secret, 'response': token, 'remoteip': remote_ip},
            timeout=5,
        )
        return bool(resp.json().get('success'))
    except Exception:
        logger.warning("Turnstile verification request failed")
        return False  # Fail closed


# --- Email verification helpers ---

VERIFY_SALT = 'email-verify'
VERIFY_MAX_AGE = 60 * 60 * 24 * 3  # 3 days

RESET_SALT = 'password-reset'
RESET_MAX_AGE = 60 * 60  # 1 hour


def _make_verify_token(user_id):
    """Create a signed, time-limited verification token."""
    return signing.dumps({'uid': user_id}, salt=VERIFY_SALT)


def _send_verification_email(request, django_user):
    """Send account verification email."""
    token = _make_verify_token(django_user.pk)
    verify_url = request.build_absolute_uri(f'/verify-email/{token}/')
    try:
        send_mail(
            subject='Verify your QuestLog account',
            message=(
                f"Hi {django_user.username},\n\n"
                f"Click the link below to verify your email and activate your account:\n\n"
                f"{verify_url}\n\n"
                f"This link expires in 3 days.\n\n"
                f"If you didn't create this account, you can ignore this email.\n\n"
                f"— QuestLog at Casual Heroes"
            ),
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[django_user.email],
            fail_silently=False,
        )
        logger.info(f"Verification email sent to {django_user.username}")
    except Exception as e:
        logger.error(f"Failed to send verification email to {django_user.username}: {e}")


FOUNDING_FLAIR_NAME = 'Founding Member'
FOUNDING_FLAIR_LIMIT = 999999  # No hard cap - time-gated instead (available_until on the flair row)


def _maybe_award_founding_flair(user, db):
    """
    Award the Founding Member flair on first login during the eligibility window.

    Early Access (now - June 3):  flair.available_from not yet reached, but early
    access users get it immediately regardless (they earned it).

    Open Beta (June 6 - July 6):  flair.available_from <= now <= flair.available_until
    - any new registration qualifies.

    Outside the window: skip silently.
    """
    import time as _time
    try:
        flair = db.query(WebFlair).filter_by(name=FOUNDING_FLAIR_NAME, enabled=True).first()
        if not flair:
            return
        already_has = db.query(WebUserFlair).filter_by(user_id=user.id, flair_id=flair.id).first()
        if already_has:
            return

        now_ts = int(_time.time())
        # During early access: award regardless of available_from (early access users earn it)
        # During open beta window: award if within available_from / available_until
        # After window closes: don't award
        if flair.available_until and now_ts > flair.available_until:
            return  # Window closed
        # If available_from is set and we're before it, only award if user has an early access code
        if flair.available_from and now_ts < flair.available_from:
            # Check if this user registered with an early-access invite code
            has_early_access = db.execute(
                sa_text("SELECT 1 FROM web_early_access_codes WHERE used_by_user_id=:uid LIMIT 1"),
                {'uid': user.id}
            ).fetchone()
            if not has_early_access:
                return  # Not in early access, and open beta hasn't started yet

        db.add(WebUserFlair(user_id=user.id, flair_id=flair.id))
        if not user.active_flair_id:
            user.active_flair_id = flair.id
        db.commit()
        owner_count = db.query(WebUserFlair).filter_by(flair_id=flair.id).count()
        logger.info('Founding Member flair awarded to user %s (total owners: %d)', user.username, owner_count)
    except Exception as e:
        logger.error('_maybe_award_founding_flair failed for user %s: %s', user.username, e)


@ratelimit(key='ip', rate='20/m', block=True)
def ql_login(request, early_access_bypass=False):
    """Site login — username + password via Django auth."""
    if request.session.get('web_user_id'):
        return redirect(safe_redirect_url(request.GET.get('next', '/ql/')))

    if not early_access_bypass:
        with get_db_session() as db:
            cfg = db.query(WebSiteConfig).filter_by(key='logins_disabled').first()
            if cfg and cfg.value == '1':
                return render(request, 'questlog_web/login.html', {'logins_disabled': True})

    turnstile_site_key = getattr(django_settings, 'TURNSTILE_SITE_KEY', '')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        next_url = safe_redirect_url(request.POST.get('next', '/ql/'))

        # Turnstile check on early access login
        if early_access_bypass and turnstile_site_key:
            if not _verify_turnstile(request.POST.get('cf-turnstile-response', ''), _get_remote_ip(request)):
                logger.warning("Turnstile failed on early access login from %s", _get_remote_ip(request))
                messages.error(request, "Security check failed. Please try again.")
                return render(request, 'questlog_web/login.html', {
                    'next': next_url,
                    'early_access_bypass': True,
                    'turnstile_site_key': turnstile_site_key,
                })

        django_user = authenticate(request, username=username, password=password)
        if django_user is None:
            logger.warning("Failed login attempt from %s", _get_remote_ip(request))
            # Check if this is an unverified account (inactive but correct password)
            try:
                pending = DjangoUser.objects.get(username__iexact=username)
                if not pending.is_active and pending.check_password(password):
                    messages.warning(request, 'Your email is not yet verified. Check your inbox or use the resend link below.')
                    return render(request, 'questlog_web/login.html', {
                        'next': next_url,
                        'pending_verification': pending.email,
                        'early_access_bypass': early_access_bypass,
                        'turnstile_site_key': turnstile_site_key,
                    })
            except DjangoUser.DoesNotExist:
                pass
            messages.error(request, "Invalid username or password.")
            return render(request, 'questlog_web/login.html', {
                'next': next_url,
                'early_access_bypass': early_access_bypass,
                'turnstile_site_key': turnstile_site_key,
            })

        django_login(request, django_user)
        request.session.cycle_key()

        with get_db_session() as db:
            user = db.query(WebUser).filter_by(username=django_user.username).first()
            if not user:
                now  = int(time.time())
                user = WebUser(
                    username     = django_user.username,
                    display_name = django_user.get_full_name() or django_user.username,
                    created_at   = now,
                    updated_at   = now,
                    last_login_at= now,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            else:
                user.last_login_at = int(time.time())
                user.updated_at    = int(time.time())
                db.commit()
                db.refresh(user)

            if user.is_disabled:
                django_logout(request)
                messages.error(request, "This account has been disabled. Contact support if you believe this is an error.")
                return render(request, 'questlog_web/login.html', {
                    'next': next_url,
                    'early_access_bypass': early_access_bypass,
                    'turnstile_site_key': turnstile_site_key,
                })

            if user.is_banned:
                django_logout(request)
                reason = f": {user.ban_reason}" if user.ban_reason else ""
                messages.error(request, f"This account has been banned{reason}.")
                return render(request, 'questlog_web/login.html', {
                    'next': next_url,
                    'early_access_bypass': early_access_bypass,
                    'turnstile_site_key': turnstile_site_key,
                })

            if not user.email_verified:
                django_logout(request)
                request.session['pending_verification_uid'] = django_user.pk
                request.session['pending_verification_email'] = django_user.email
                messages.warning(request, "Please verify your email before logging in. Check your inbox or request a new link below.")
                return render(request, 'questlog_web/login.html', {
                    'next': next_url,
                    'pending_verification': django_user.email,
                    'early_access_bypass': early_access_bypass,
                    'turnstile_site_key': turnstile_site_key,
                })

            _maybe_award_founding_flair(user, db)

            request.session['web_user_id']       = user.id
            request.session['web_user_name']     = user.username
            request.session['web_user_avatar']   = user.avatar_url or ''
            request.session['web_user_is_admin'] = bool(user.is_admin)
            request.session.modified = True

        messages.success(request, f"Welcome back, {user.display_name or user.username}!")
        return redirect(safe_redirect_url(next_url))

    next_url = safe_redirect_url(request.GET.get('next', '/ql/'))
    pending_email = request.session.get('pending_verification_email', '')
    return render(request, 'questlog_web/login.html', {
        'next': next_url,
        'pending_verification': pending_email,
        'early_access_bypass': early_access_bypass,
        'turnstile_site_key': turnstile_site_key,
    })


# Usernames that could impersonate staff or cause confusion
_RESERVED_USERNAMES = frozenset({
    'admin', 'administrator', 'root', 'superuser', 'moderator', 'mod',
    'staff', 'support', 'help', 'info', 'contact', 'system', 'service',
    'questlog', 'questlogbot', 'casualheroes', 'casual_heroes',
    'bot', 'api', 'null', 'undefined', 'anonymous', 'guest', 'official',
})

# Known disposable email domains — block spam/throwaway registrations
_DISPOSABLE_EMAIL_DOMAINS = frozenset({
    'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'throwaway.email',
    'sharklasers.com', 'guerrillamailblock.com', 'grr.la', 'guerrillamail.info',
    'spam4.me', 'trashmail.com', 'trashmail.me', 'dispostable.com',
    'yopmail.com', 'maildrop.cc', 'discard.email', 'fakeinbox.com',
    'mailnull.com', 'spamgourmet.com', 'spamgourmet.net', 'spamgourmet.org',
    'checkyourform.xyz', 'tempr.email', 'getnada.com', 'mailnesia.com',
    'mailnull.com', 'spamfree24.org', 'mohmal.com', 'temp-mail.org',
    'tempinbox.com', 'spamevader.com', 'shieldemail.com',
})


@ratelimit(key='ip', rate='10/h', block=True)
def ql_admin_login(request):
    """
    Admin-only login gate — hardened with Turnstile, honeypot, and timing check.
    Only accounts with is_admin=True in WebUser can ever authenticate here.
    No hints are given if a non-admin account attempts access.
    """
    if request.session.get('web_user_id') and request.session.get('web_user_is_admin'):
        return redirect('/ql/admin/')

    ctx = {'turnstile_site_key': django_settings.TURNSTILE_SITE_KEY}

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        # 1. Honeypot
        if request.POST.get('website', ''):
            logger.warning(f"Admin login honeypot triggered from {_get_remote_ip(request)}")
            messages.error(request, "Invalid credentials.")
            return render(request, 'questlog_web/admin_login.html', ctx)

        # 2. Timing - missing or malformed _ts is rejected (fail closed, not silently skipped)
        _ts_raw = request.POST.get('_ts', '').strip()
        if not _ts_raw:
            logger.warning(f"Admin login missing _ts from {_get_remote_ip(request)}")
            messages.error(request, "Invalid credentials.")
            return render(request, 'questlog_web/admin_login.html', ctx)
        try:
            elapsed = int(time.time()) - int(_ts_raw)
            if elapsed < 3:
                logger.warning(f"Admin login timing check failed ({elapsed}s) from {_get_remote_ip(request)}")
                messages.error(request, "Invalid credentials.")
                return render(request, 'questlog_web/admin_login.html', ctx)
        except (ValueError, TypeError):
            logger.warning(f"Admin login malformed _ts '{_ts_raw}' from {_get_remote_ip(request)}")
            messages.error(request, "Invalid credentials.")
            return render(request, 'questlog_web/admin_login.html', ctx)

        # 3. Turnstile
        if not _verify_turnstile(request.POST.get('cf-turnstile-response', ''), _get_remote_ip(request)):
            logger.warning(f"Admin login Turnstile failed from {_get_remote_ip(request)}")
            messages.error(request, "Security check failed. Please try again.")
            return render(request, 'questlog_web/admin_login.html', ctx)

        # Authenticate
        django_user = authenticate(request, username=username, password=password)
        if django_user is None:
            logger.warning(f"Admin login auth failed from {_get_remote_ip(request)}")
            messages.error(request, "Invalid credentials.")
            return render(request, 'questlog_web/admin_login.html', ctx)

        # Admin check — always return same error to avoid oracle
        with get_db_session() as db:
            user = db.query(WebUser).filter_by(username=django_user.username).first()
            if not user or not user.is_admin or user.is_banned or user.is_disabled:
                logger.warning(f"Non-admin/banned account blocked at admin login from {_get_remote_ip(request)}")
                messages.error(request, "Invalid credentials.")
                return render(request, 'questlog_web/admin_login.html', ctx)

            django_login(request, django_user)
            request.session.cycle_key()
            user.last_login_at = int(time.time())
            user.updated_at    = int(time.time())
            db.commit()
            db.refresh(user)

            request.session['web_user_id']       = user.id
            request.session['web_user_name']     = user.username
            request.session['web_user_avatar']   = user.avatar_url or ''
            request.session['web_user_is_admin'] = True
            request.session.modified = True

        logger.info(f"Admin login successful: '{username}' from {_get_remote_ip(request)}")
        return redirect('/ql/admin/')

    return render(request, 'questlog_web/admin_login.html', ctx)


@require_http_methods(['POST'])
@ratelimit(key='ip', rate='15/m', block=True)
def api_check_invite(request):
    """
    POST /ql/api/register/check-invite/
    Validates an invite code without marking it used.
    Returns {valid: true, redirect: '/ql/register/?invite=CODE'} or {valid: false, error: '...'}.
    Used by the early access gate on the registration page.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'valid': False, 'error': 'Invalid request.'}, status=400)

    code = str(data.get('code', '')).strip().upper()
    if not code:
        return JsonResponse({'valid': False, 'error': 'Enter an invite code.'})

    with get_db_session() as db:
        obj = db.query(WebEarlyAccessCode).filter_by(
            code=code, is_revoked=False
        ).filter(WebEarlyAccessCode.used_by_user_id == None).first()
        if not obj:
            return JsonResponse({'valid': False, 'error': 'That code is invalid or has already been used.'})

    return JsonResponse({'valid': True, 'redirect': f'/ql/register/?invite={code}'})


@ratelimit(key='ip', rate='5/h', block=True)
def ql_register(request):
    """Account registration — username + password via Django auth."""
    if request.session.get('web_user_id'):
        return redirect('/ql/')

    # Check for invite code bypass (from ?invite=CODE query param)
    invite_param = request.GET.get('invite', '').strip().upper() if request.method == 'GET' else ''
    invite_bypass = False
    if invite_param:
        with get_db_session() as db:
            pre_check = db.query(WebEarlyAccessCode).filter_by(
                code=invite_param, is_revoked=False
            ).filter(WebEarlyAccessCode.used_by_user_id == None).first()
            invite_bypass = bool(pre_check)

    with get_db_session() as db:
        cfg = db.query(WebSiteConfig).filter_by(key='logins_disabled').first()
        if cfg and cfg.value == '1' and not invite_bypass:
            return render(request, 'questlog_web/register.html', {'registrations_disabled': True})

    # Capture referral code from URL on first GET so it survives form re-renders
    if request.method == 'GET' and request.GET.get('ref'):
        ref = request.GET['ref'].strip()[:16]
        if ref.isalnum() or all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for c in ref):
            request.session['pending_referral_code'] = ref

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        errors = []

        # --- Anti-bot pre-checks (before any DB work) ---

        # 1. Honeypot: legitimate browsers leave this blank; bots fill every field
        if request.POST.get('website', ''):
            logger.warning(f"Honeypot triggered on registration from {_get_remote_ip(request)}")
            messages.success(request, "Account created! Check your email for a verification link.")
            return redirect('questlog_web_login')

        # 2. Timing: humans take >3 s to read and fill the form
        try:
            elapsed = int(time.time()) - int(request.POST.get('_ts', '0'))
            if 0 < elapsed < 3:
                logger.warning(f"Registration timing check failed ({elapsed}s) from {_get_remote_ip(request)}")
                errors.append("Form submitted too quickly. Please try again.")
        except (ValueError, TypeError):
            pass  # Missing/malformed timestamp — don't block

        # 3. Cloudflare Turnstile
        if not _verify_turnstile(request.POST.get('cf-turnstile-response', ''), _get_remote_ip(request)):
            logger.warning(f"Turnstile failed on registration from {_get_remote_ip(request)}")
            errors.append("Security check failed. Please complete the challenge and try again.")

        # Bail early if any pre-check failed
        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'questlog_web/register.html', {
                'username': username, 'email': email,
                'turnstile_site_key': django_settings.TURNSTILE_SITE_KEY,
                'early_access_mode': getattr(django_settings, 'EARLY_ACCESS_ENABLED', False),
                'invite_code': request.POST.get('invite_code', ''),
            })

        # 4. Early access invite code gate
        _invite_code_obj = None
        _raw_invite = request.POST.get('invite_code', '').strip().upper()
        if getattr(django_settings, 'EARLY_ACCESS_ENABLED', False):
            if not _raw_invite:
                errors.append("An invite code is required during Early Access. Get one in our Fluxer or Discord community.")
            else:
                with get_db_session() as _idb:
                    _invite_code_obj = _idb.query(WebEarlyAccessCode).filter_by(
                        code=_raw_invite, is_revoked=False
                    ).filter(WebEarlyAccessCode.used_by_user_id == None).first()
                if not _invite_code_obj:
                    errors.append("That invite code is invalid or has already been used.")
        elif _raw_invite:
            # Not in early access mode but user submitted a code - look it up to mark as used
            with get_db_session() as _idb:
                _invite_code_obj = _idb.query(WebEarlyAccessCode).filter_by(
                    code=_raw_invite, is_revoked=False
                ).filter(WebEarlyAccessCode.used_by_user_id == None).first()

        # Validation
        if not username:
            errors.append("Username is required.")
        elif len(username) < 3 or len(username) > 30:
            errors.append("Username must be 3–30 characters.")
        elif not re.match(r'^[a-zA-Z0-9_-]+$', username):
            errors.append("Username can only contain letters, numbers, hyphens, and underscores.")
        elif username.lower() in _RESERVED_USERNAMES:
            errors.append("That username is not available.")

        if not email:
            errors.append("Email is required.")
        elif not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            errors.append("Please enter a valid email address.")
        elif email.split('@')[-1].lower() in _DISPOSABLE_EMAIL_DOMAINS:
            errors.append("Disposable email addresses are not allowed. Please use a real email.")

        if not password:
            errors.append("Password is required.")
        elif password != password2:
            errors.append("Passwords do not match.")

        if not errors:
            try:
                validate_password(password)
            except ValidationError as e:
                errors.extend(e.messages)

        if not errors and DjangoUser.objects.filter(username__iexact=username).exists():
            errors.append("That username is already taken.")

        if not errors and DjangoUser.objects.filter(email__iexact=email).exists():
            # Anti-enumeration: do not reveal whether the email is already registered.
            # Show the same success message as a real registration so attackers
            # cannot probe which email addresses have accounts.
            messages.success(
                request,
                "Account created! Check your email for a verification link."
            )
            return redirect('questlog_web_login')

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'questlog_web/register.html', {
                'username': username, 'email': email,
                'turnstile_site_key': django_settings.TURNSTILE_SITE_KEY,
            })

        # Account stays inactive until email verified.
        # Wrapped in atomic to prevent race condition between email uniqueness check and insert.
        try:
            with transaction.atomic():
                django_user = DjangoUser.objects.create_user(
                    username=username, email=email, password=password
                )
                django_user.is_active = False
                django_user.save()
        except IntegrityError:
            # Another request registered this email/username between our check and insert.
            # Anti-enumeration: return same success message so attacker can't enumerate.
            messages.success(request, "Account created! Check your email for a verification link.")
            return redirect('questlog_web_login')

        with get_db_session() as db:
            now = int(time.time())
            user = WebUser(
                username=django_user.username,
                display_name=django_user.username,
                email=email,
                email_verified=False,
                created_at=now,
                updated_at=now,
                last_login_at=now,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Mark early-access invite code as used
            if getattr(django_settings, 'EARLY_ACCESS_ENABLED', False) and _invite_code_obj:
                try:
                    code_in_session = db.query(WebEarlyAccessCode).filter_by(
                        id=_invite_code_obj.id, is_revoked=False
                    ).filter(WebEarlyAccessCode.used_by_user_id == None).first()
                    if code_in_session:
                        code_in_session.used_by_user_id = user.id
                        code_in_session.used_at = now
                        db.commit()
                        logger.info(f"Early access code {code_in_session.code} used by user {user.id}")
                except Exception as e:
                    logger.error(f"Failed to mark invite code as used: {e}")

            # Link pending referral if a valid invite code was stored in session
            ref_code = request.session.get('pending_referral_code', '').strip()
            if ref_code:
                referrer = db.query(WebUser).filter_by(invite_code=ref_code).first()
                if referrer and referrer.id != user.id:
                    referral = WebReferral(
                        referrer_id=referrer.id,
                        invited_user_id=user.id,
                        status='pending',
                        created_at=now,
                    )
                    db.add(referral)
                    db.commit()
                    logger.info(f"Referral recorded: referrer={referrer.id} invited={user.id}")

        _send_verification_email(request, django_user)

        # Keep uid in session so the login page can offer a "resend" link
        request.session['pending_verification_uid'] = django_user.pk
        request.session['pending_verification_email'] = email

        messages.success(
            request,
            "Account created! Check your email for a verification link."
        )
        return redirect('questlog_web_login')

    return render(request, 'questlog_web/register.html', {
        'turnstile_site_key': django_settings.TURNSTILE_SITE_KEY,
        'early_access_mode': getattr(django_settings, 'EARLY_ACCESS_ENABLED', False),
        'invite_code': invite_param if invite_bypass else '',
    })


def verify_email(request, token):
    """Verify email from the link sent during registration."""
    try:
        data = signing.loads(token, salt=VERIFY_SALT, max_age=VERIFY_MAX_AGE)
    except signing.BadSignature:
        messages.error(request, "Invalid or expired verification link.")
        return redirect('questlog_web_login')

    user_id = data.get('uid')
    try:
        django_user = DjangoUser.objects.get(pk=user_id)
    except DjangoUser.DoesNotExist:
        messages.error(request, "Account not found.")
        return redirect('questlog_web_login')

    if django_user.is_active:
        messages.info(request, "Your email is already verified. You can log in.")
        return redirect('questlog_web_login')

    django_user.is_active = True
    django_user.save()

    referrer_id_to_reward = None
    with get_db_session() as db:
        web_user = db.query(WebUser).filter_by(username=django_user.username).first()
        if web_user:
            web_user.email_verified = True
            web_user.updated_at = int(time.time())

            # Complete any pending referral for this user
            referral = db.query(WebReferral).filter_by(
                invited_user_id=web_user.id, status='pending'
            ).first()
            if referral:
                referral.status = 'completed'
                referral.completed_at = int(time.time())
                referrer = db.query(WebUser).filter_by(id=referral.referrer_id).first()
                if referrer:
                    referrer.referral_count = (referrer.referral_count or 0) + 1
                    referrer_id_to_reward = referrer.id

            db.commit()

    # Award HP outside the session (award_hero_points opens its own session)
    if referrer_id_to_reward:
        award_hero_points(referrer_id_to_reward, 'invite', ref_id=str(web_user.id))
        logger.info(f"Referral completed: referrer={referrer_id_to_reward} new_user={web_user.id} +50 HP")

    # Notify Fluxer channel of new verified member
    if web_user:
        _fluxer_new_member(
            username=web_user.username,
            profile_url=f"https://casual-heroes.com/ql/profile/{web_user.username}/",
        )

    # Clear pending verification state
    request.session.pop('pending_verification_uid', None)
    request.session.pop('pending_verification_email', None)
    request.session.pop('pending_referral_code', None)

    messages.success(request, "Email verified! You can now log in.")
    return redirect('questlog_web_login')


@ratelimit(key='ip', rate='5/h', block=True)
def resend_verification(request):
    """Resend verification email — works from login page or standalone."""
    if request.method == 'POST':
        # Session uid is set during registration; email is a fallback for the standalone form
        uid = request.session.get('pending_verification_uid')
        email = request.POST.get('email', '').strip().lower()

        django_user = None
        if uid:
            try:
                django_user = DjangoUser.objects.get(pk=uid)
            except DjangoUser.DoesNotExist:
                pass
        if not django_user and email:
            try:
                django_user = DjangoUser.objects.get(email__iexact=email)
            except DjangoUser.DoesNotExist:
                pass

        if django_user and not django_user.is_active:
            _send_verification_email(request, django_user)
            request.session['pending_verification_uid'] = django_user.pk
            request.session['pending_verification_email'] = django_user.email

        messages.success(request, "Verification email resent! Check your inbox.")
        return redirect('questlog_web_login')

    return render(request, 'questlog_web/resend_verification.html')


def check_email(request):
    """Post-registration page — check your email + resend button."""
    email = request.session.get('pending_verification_email', '')
    uid = request.session.get('pending_verification_uid')

    if not uid:
        return redirect('questlog_web_login')

    if request.method == 'POST':
        try:
            django_user = DjangoUser.objects.get(pk=uid)
            if not django_user.is_active:
                _send_verification_email(request, django_user)
                messages.success(request, "Verification email resent!")
            else:
                messages.info(request, "Your account is already verified.")
                return redirect('questlog_web_login')
        except DjangoUser.DoesNotExist:
            pass
        return render(request, 'questlog_web/check_email.html', {'email': email})

    return render(request, 'questlog_web/check_email.html', {'email': email})


def logout(request):
    """Clear the QuestLog session and Django session, send user home."""
    # Drain any pending messages so they don't leak to the login page
    storage = messages.get_messages(request)
    for _ in storage:
        pass
    django_logout(request)
    for key in ('web_user_id', 'web_user_name', 'web_user_avatar'):
        request.session.pop(key, None)
    messages.info(request, "You've been logged out.")
    return redirect('/')


# --- Steam linking (optional connection — unlocks game features) -------------

@web_login_required
def steam_link(request):
    """Start Steam OpenID so the user can link their Steam account."""
    return_url = request.build_absolute_uri('/ql/auth/steam/callback/')
    realm      = request.build_absolute_uri('/').rstrip('/')
    return redirect(get_steam_login_url(return_url, realm))


@web_login_required
def steam_link_callback(request):
    """Verify Steam and attach the steam_id to the existing Matrix account."""
    success, steam_id = verify_steam_login(request.GET.dict())
    if not success or not steam_id:
        messages.error(request, "Steam verification failed. Please try again.")
        return redirect('questlog_web_settings')

    profile = get_steam_user_profile(steam_id, STEAM_API_KEY) if STEAM_API_KEY else None

    with get_db_session() as db:
        existing = db.query(WebUser).filter(
            WebUser.steam_id == steam_id,
            WebUser.id != request.web_user.id,
        ).first()
        if existing:
            messages.error(request, "That Steam account is already linked to another QuestLog account.")  # One Steam ID per account
            return redirect('questlog_web_settings')

        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        user.steam_id          = steam_id
        user.steam_username    = profile.get('username')    if profile else None
        user.steam_avatar      = profile.get('avatar')      if profile else None
        user.steam_profile_url = profile.get('profile_url') if profile else None
        if profile and not user.avatar_url:
            user.avatar_url = profile.get('avatar')
        user.updated_at = int(time.time())
        db.commit()

    messages.success(request, "Steam account linked! Full QuestLog features are now unlocked.")
    return redirect('questlog_web_settings')


@require_http_methods(["POST"])
@web_login_required
def steam_unlink(request):
    """Remove the linked Steam account from the user's profile."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user or not user.steam_id:
            messages.error(request, "No Steam account is linked.")
            return redirect('questlog_web_settings')

        user.steam_id = None
        user.steam_username = None
        user.steam_avatar = None
        user.steam_profile_url = None
        user.updated_at = int(time.time())
        db.commit()

    messages.success(request, "Steam account disconnected.")
    return redirect('questlog_web_settings')


# --- Discord linking (optional — connects Discord identity to QuestLog account) ---

@web_login_required
def discord_link(request):
    """Start Discord OAuth2 to link a Discord account to the current QuestLog user."""
    if not _DISCORD_CLIENT_ID or not _DISCORD_REDIRECT_URI_QL:
        messages.error(request, "Discord linking is not configured on this server.")
        return redirect('questlog_web_profile')

    state = secrets.token_urlsafe(32)
    request.session['ql_discord_link_state'] = state
    request.session['ql_discord_link_ts']    = int(time.time())

    from urllib.parse import urlencode
    params = {
        'client_id':     _DISCORD_CLIENT_ID,
        'redirect_uri':  _DISCORD_REDIRECT_URI_QL,
        'response_type': 'code',
        'scope':         'identify',  # identify only — no guilds, no email
        'state':         state,
        'prompt':        'none',      # skip consent screen if already authorized
    }
    return redirect(f"{_DISCORD_AUTH_URL}?{urlencode(params)}")


@web_login_required
@ratelimit(key='user', rate='10/h', block=True)
def discord_link_callback(request):
    """Discord redirects here after the user authorises. Save discord_id to WebUser."""
    error = request.GET.get('error')
    if error:
        messages.error(request, f"Discord authorisation failed: {error}")
        return redirect('questlog_web_profile')

    code  = request.GET.get('code',  '')
    state = request.GET.get('state', '')

    stored_state = request.session.pop('ql_discord_link_state', None)
    stored_ts    = request.session.pop('ql_discord_link_ts', 0)

    # CSRF state check
    if not state or state != stored_state:
        messages.error(request, "Invalid OAuth state. Please try again.")
        return redirect('questlog_web_profile')

    # Expire after 10 minutes
    if int(time.time()) - stored_ts > 600:
        messages.error(request, "OAuth session expired. Please try again.")
        return redirect('questlog_web_profile')

    if not code:
        messages.error(request, "No authorisation code received.")
        return redirect('questlog_web_profile')

    # Exchange code for access token
    try:
        token_resp = _requests.post(_DISCORD_TOKEN_URL, data={
            'client_id':     _DISCORD_CLIENT_ID,
            'client_secret': _DISCORD_CLIENT_SECRET,
            'grant_type':    'authorization_code',
            'code':          code,
            'redirect_uri':  _DISCORD_REDIRECT_URI_QL,
        }, headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
        token_resp.raise_for_status()
        access_token = token_resp.json().get('access_token')
    except Exception as e:
        logger.error(f"discord_link_callback: token exchange failed: {e}")
        messages.error(request, "Failed to connect to Discord. Please try again.")
        return redirect('questlog_web_profile')

    try:
        user_resp = _requests.get(f"{_DISCORD_API}/users/@me",
                                   headers={'Authorization': f'Bearer {access_token}'},
                                   timeout=10)
        user_resp.raise_for_status()
        discord_data = user_resp.json()
    except Exception as e:
        logger.error(f"discord_link_callback: user fetch failed: {e}")
        messages.error(request, "Failed to retrieve Discord profile. Please try again.")
        return redirect('questlog_web_profile')

    discord_id       = str(discord_data.get('id', ''))
    discord_username = discord_data.get('global_name') or discord_data.get('username', '')
    avatar_hash      = discord_data.get('avatar', '')

    if not discord_id:
        messages.error(request, "Could not read Discord ID. Please try again.")
        return redirect('questlog_web_profile')

    # Build CDN avatar URL
    if avatar_hash:
        ext = 'gif' if avatar_hash.startswith('a_') else 'png'
        discord_avatar_url = f"https://cdn.discordapp.com/avatars/{discord_id}/{avatar_hash}.{ext}?size=256"
    else:
        discord_avatar_url = f"https://cdn.discordapp.com/embed/avatars/{int(discord_id) % 5}.png"

    with get_db_session() as db:
        # One Discord account per QuestLog account
        existing = db.query(WebUser).filter(
            WebUser.discord_id == discord_id,
            WebUser.id != request.web_user.id,
        ).first()
        if existing:
            messages.error(request, "That Discord account is already linked to another QuestLog account.")
            return redirect('questlog_web_profile')

        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        user.discord_id       = discord_id
        user.discord_username = discord_username
        user.updated_at       = int(time.time())
        db.commit()
        web_user_id = user.id
        current_web_xp = user.web_xp or 0
        current_hp = user.hero_points or 0

    # One-time XP merge: for every opted-in guild this Discord user has XP in,
    # take MAX(discord_xp, web_xp) as the new unified XP (no inflation),
    # write into web_unified_leaderboard, and zero out guild_members.
    try:
        with get_db_session() as db2:
            now = int(time.time())

            # Find all opted-in guilds where this Discord user has XP
            guild_rows = db2.execute(sa_text(
                "SELECT gm.guild_id, gm.xp, gm.hero_tokens, gm.message_count, "
                "       gm.voice_minutes, gm.reaction_count, gm.media_count, gm.last_active "
                "FROM guild_members gm "
                "JOIN web_communities wc ON wc.platform='discord' "
                "    AND CAST(wc.platform_id AS UNSIGNED) = gm.guild_id "
                "    AND wc.site_xp_to_guild=1 AND wc.network_status='approved' AND wc.is_active=1 "
                "WHERE gm.user_id = :did AND gm.xp > 0"
            ), {"did": int(discord_id)}).fetchall()

            if guild_rows:
                # Take the highest XP across all guilds as the unified value
                max_discord_xp = max(int(r[1] or 0) for r in guild_rows)
                new_web_xp = max(current_web_xp, max_discord_xp)
                new_level = _get_level_for_xp(new_web_xp, db2)

                # HP: add discord HP only if discord had more XP than site (wasn't already synced)
                discord_hp = sum(int(r[2] or 0) for r in guild_rows)
                new_hp = current_hp + discord_hp if max_discord_xp > current_web_xp else current_hp

                # Update web_users
                db2.execute(sa_text(
                    "UPDATE web_users SET web_xp=:xp, web_level=:lvl, hero_points=:hp WHERE id=:uid"
                ), {"xp": new_web_xp, "lvl": new_level, "hp": new_hp, "uid": web_user_id})

                for r in guild_rows:
                    # cols: guild_id, xp, hero_tokens, message_count, voice_minutes,
                    #       reaction_count, media_count, last_active
                    guild_id_int = int(r[0])
                    guild_id_str = str(guild_id_int)
                    msg   = int(r[3] or 0)
                    voice = int(r[4] or 0)
                    react = int(r[5] or 0)
                    media = int(r[6] or 0)
                    la    = int(r[7] or now)

                    # Upsert into unified leaderboard
                    db2.execute(sa_text("""
                        INSERT INTO web_unified_leaderboard
                            (user_id, guild_id, platform, messages, voice_mins, reactions,
                             media_count, xp_total, last_active, updated_at)
                        VALUES
                            (:uid, :gid, 'discord', :msg, :voice, :react,
                             :media, :xp, :la, :now)
                        ON DUPLICATE KEY UPDATE
                            messages=:msg, voice_mins=:voice, reactions=:react,
                            media_count=:media, xp_total=:xp, last_active=:la, updated_at=:now
                    """), {"uid": web_user_id, "gid": guild_id_str,
                           "msg": msg, "voice": voice, "react": react,
                           "media": media, "xp": new_web_xp, "la": la, "now": now})

                    # Zero out guild_members so bot writes to unified going forward
                    db2.execute(sa_text(
                        "UPDATE guild_members SET xp=0, level=1, hero_tokens=0 "
                        "WHERE guild_id=:gid AND user_id=:did"
                    ), {"gid": guild_id_int, "did": int(discord_id)})

                db2.commit()
                logger.info(f"discord_link: merged XP for user {web_user_id} discord_id={discord_id} "
                            f"new_web_xp={new_web_xp} level={new_level}")
    except Exception as e:
        logger.error(f"discord_link: XP merge failed for user {web_user_id}: {e}", exc_info=True)

    # Redirect to profile so the user sees Connected status and My Servers
    from django.http import HttpResponseRedirect
    from django.urls import reverse
    return HttpResponseRedirect(reverse('questlog_web_profile') + '?linked=discord')


@require_http_methods(["POST"])
@web_login_required
def discord_unlink(request):
    """Remove the linked Discord account from the user's profile."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user or not user.discord_id:
            messages.error(request, "No Discord account is linked.")
            return redirect('questlog_web_profile')

        user.discord_id       = None
        user.discord_username = None
        user.updated_at       = int(time.time())
        db.commit()

    messages.success(request, "Discord account disconnected.")
    return redirect('questlog_web_profile')


# --- Fluxer OAuth (account linking) -----------------------------------------

@web_login_required
@ratelimit(key='user', rate='10/h', block=True)
def fluxer_link(request):
    """Start Fluxer OAuth2 to link a Fluxer account to the current QuestLog user."""
    if not _FLUXER_CLIENT_ID or not _FLUXER_REDIRECT_URI_QL:
        messages.error(request, "Fluxer linking is not configured on this server.")
        return redirect('questlog_web_profile')

    state = secrets.token_urlsafe(32)
    request.session['ql_fluxer_link_state'] = state
    request.session['ql_fluxer_link_ts']    = int(time.time())

    from urllib.parse import urlencode
    params = {
        'client_id':     _FLUXER_CLIENT_ID,
        'redirect_uri':  _FLUXER_REDIRECT_URI_QL,
        'response_type': 'code',
        'scope':         'identify',
        'state':         state,
    }
    return redirect(f"{_FLUXER_AUTH_URL}?{urlencode(params)}")


@web_login_required
@ratelimit(key='user', rate='10/h', block=True)
def fluxer_link_callback(request):
    """Fluxer redirects here after the user authorises. Save fluxer_id to WebUser."""
    error = request.GET.get('error')
    if error:
        messages.error(request, f"Fluxer authorisation failed: {error}")
        return redirect('questlog_web_profile')

    code  = request.GET.get('code',  '')
    state = request.GET.get('state', '')

    stored_state = request.session.pop('ql_fluxer_link_state', None)
    stored_ts    = request.session.pop('ql_fluxer_link_ts', 0)

    if not state or state != stored_state:
        messages.error(request, "Invalid OAuth state. Please try again.")
        return redirect('questlog_web_profile')

    if int(time.time()) - stored_ts > 600:
        messages.error(request, "OAuth session expired. Please try again.")
        return redirect('questlog_web_profile')

    if not code:
        messages.error(request, "No authorisation code received.")
        return redirect('questlog_web_profile')

    # Exchange code for access token (multipart/form-data per Fluxer spec)
    try:
        token_resp = _requests.post(_FLUXER_TOKEN_URL, data={
            'grant_type':    'authorization_code',
            'code':          code,
            'redirect_uri':  _FLUXER_REDIRECT_URI_QL,
            'client_id':     _FLUXER_CLIENT_ID,
            'client_secret': _FLUXER_CLIENT_SECRET,
        }, timeout=10)
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token   = token_data.get('access_token')
        refresh_token  = token_data.get('refresh_token')
        expires_in     = int(token_data.get('expires_in', 0) or 0)
        token_expires_at = int(time.time()) + expires_in if expires_in else None
    except Exception as e:
        logger.error(f"fluxer_link_callback: token exchange failed: {e}")
        messages.error(request, "Failed to connect to Fluxer. Please try again.")
        return redirect('questlog_web_profile')

    # Get user info
    try:
        user_resp = _requests.get(
            _FLUXER_USERINFO_URL,
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10,
        )
        user_resp.raise_for_status()
        fluxer_data = user_resp.json()
    except Exception as e:
        logger.error(f"fluxer_link_callback: user info fetch failed: {e}")
        messages.error(request, "Failed to retrieve Fluxer profile. Please try again.")
        return redirect('questlog_web_profile')

    fluxer_id       = str(fluxer_data.get('id', ''))
    fluxer_username = fluxer_data.get('global_name') or fluxer_data.get('username', '')

    if not fluxer_id:
        messages.error(request, "Could not read Fluxer ID. Please try again.")
        return redirect('questlog_web_profile')

    with get_db_session() as db:
        # One Fluxer account per QuestLog account
        existing = db.query(WebUser).filter(
            WebUser.fluxer_id == fluxer_id,
            WebUser.id != request.web_user.id,
        ).first()
        if existing:
            messages.error(request, "That Fluxer account is already linked to another QuestLog account.")
            return redirect('questlog_web_profile')

        from app.utils.encryption import encrypt_token as _enc
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        user.fluxer_id       = fluxer_id
        user.fluxer_username = fluxer_username
        user.updated_at      = int(time.time())
        # Store tokens encrypted so custom-status sync can use them without re-auth
        if access_token:
            user.fluxer_access_token_enc  = _enc(access_token)
        if refresh_token:
            user.fluxer_refresh_token_enc = _enc(refresh_token)
        user.fluxer_token_expires_at = token_expires_at
        db.commit()
        web_user_id = user.id
        already_migrated = bool(user.fluxer_xp_migrated)

    # One-time migration: transfer accumulated bot XP to the site profile in a single transaction
    if not already_migrated:
        try:
            with get_db_session() as db2:
                xp_row = db2.execute(sa_text(
                    "SELECT COALESCE(SUM(xp), 0) AS total_xp FROM fluxer_member_xp WHERE user_id = :uid"
                ), {"uid": int(fluxer_id)}).fetchone()
                accumulated_xp = int(xp_row.total_xp) if xp_row else 0
                # Use MAX(accumulated, current web_xp) to avoid double-counting dual-write
                user2_xp_check = db2.execute(sa_text(
                    "SELECT web_xp FROM web_users WHERE id=:uid"
                ), {"uid": web_user_id}).scalar() or 0
                migration_xp = max(accumulated_xp, user2_xp_check) - user2_xp_check

                if migration_xp > 0:
                    now = int(time.time())
                    user2 = db2.query(WebUser).filter_by(id=web_user_id).with_for_update().first()
                    if user2:
                        old_xp = user2.web_xp or 0
                        new_xp = old_xp + migration_xp

                        db2.add(WebXpEvent(
                            user_id=web_user_id,
                            action_type='fluxer_migration',
                            xp=migration_xp,
                            source='fluxer',
                            ref_id=f'migrate_{fluxer_id}',
                            created_at=now,
                        ))
                        user2.web_xp = new_xp

                        # Award HP for every 50-XP threshold crossed
                        thresholds_crossed = (new_xp // XP_TO_HP_THRESHOLD) - (old_xp // XP_TO_HP_THRESHOLD)
                        if thresholds_crossed > 0:
                            hp_from_xp = thresholds_crossed * HP_PER_THRESHOLD
                            user2.hero_points = (user2.hero_points or 0) + hp_from_xp
                            db2.add(WebHeroPointEvent(
                                user_id=web_user_id, action_type='xp_conversion',
                                points=hp_from_xp, source='fluxer',
                                ref_id=f'xp_{new_xp}', created_at=now,
                            ))

                        # Level-up check
                        old_level = user2.web_level or 1
                        new_level = _get_level_for_xp(new_xp, db2)
                        if new_level > old_level:
                            user2.web_level = new_level
                            hp_from_level = (new_level - old_level) * HP_PER_LEVEL
                            user2.hero_points = (user2.hero_points or 0) + hp_from_level
                            db2.add(WebHeroPointEvent(
                                user_id=web_user_id, action_type='level_up',
                                points=hp_from_level, source='fluxer',
                                ref_id=f'level_{new_level}', created_at=now,
                            ))

                # Always mark migrated (even if 0 XP, so we never retry)
                db2.execute(sa_text(
                    "UPDATE web_users SET fluxer_xp_migrated = 1 WHERE id = :uid"
                ), {"uid": web_user_id})
                db2.commit()
        except Exception as e:
            logger.error(f"Fluxer XP migration failed for user {web_user_id}: {e}")

    messages.success(request, f"Fluxer account @{fluxer_username} linked successfully!")
    return redirect('questlog_web_profile')


@require_http_methods(["POST"])
@web_login_required
def fluxer_unlink(request):
    """Remove the linked Fluxer account from the user's profile."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user or not user.fluxer_id:
            messages.error(request, "No Fluxer account is linked.")
            return redirect('questlog_web_profile')

        user.fluxer_id                = None
        user.fluxer_username          = None
        user.fluxer_access_token_enc  = None
        user.fluxer_refresh_token_enc = None
        user.fluxer_token_expires_at  = None
        user.fluxer_sync_custom_status = False
        user.updated_at               = int(time.time())
        db.commit()

    messages.success(request, "Fluxer account disconnected.")
    return redirect('questlog_web_profile')


# --- Twitch OAuth (creator profile) -----------------------------------------

@web_login_required
def twitch_oauth_initiate(request):
    """Start Twitch OAuth to link Twitch account to creator profile."""
    state = secrets.token_urlsafe(32)
    request.session['twitch_oauth_state'] = state
    request.session['twitch_oauth_ts'] = int(time.time())

    redirect_uri = django_settings.TWITCH_REDIRECT_URI_QL
    client_id = django_settings.TWITCH_CLIENT_ID
    if not client_id:
        messages.error(request, "Twitch integration is not configured.")
        return redirect('questlog_web_creator_register')

    scopes = 'user:read:email channel:read:subscriptions'
    auth_url = (
        f"https://id.twitch.tv/oauth2/authorize?"
        f"client_id={client_id}&redirect_uri={redirect_uri}"
        f"&response_type=code&scope={scopes}&state={state}&force_verify=true"
    )
    return redirect(auth_url)


@web_login_required
def twitch_oauth_callback(request):
    """Handle Twitch OAuth callback — store encrypted tokens on creator profile."""
    from app.utils.encryption import encrypt_token

    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')

    if error or not code:
        messages.error(request, "Twitch authorization was cancelled or failed.")
        return redirect('questlog_web_creator_register')

    saved_state = request.session.pop('twitch_oauth_state', None)
    saved_ts = request.session.pop('twitch_oauth_ts', None)
    if not saved_state or state != saved_state:
        messages.error(request, "Invalid OAuth state. Please try again.")
        return redirect('questlog_web_creator_register')
    if saved_ts and (int(time.time()) - saved_ts) > 1800:
        messages.error(request, "OAuth session expired. Please try again.")
        return redirect('questlog_web_creator_register')

    try:
        from app.services.twitch_service import TwitchService
        svc = TwitchService()
        redirect_uri = django_settings.TWITCH_REDIRECT_URI_QL
        token_data = _requests.post(
            'https://id.twitch.tv/oauth2/token',
            data={
                'client_id': svc.client_id,
                'client_secret': svc.client_secret,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri,
            },
            timeout=10,
        ).json()

        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        if not access_token:
            messages.error(request, "Failed to get Twitch access token.")
            return redirect('questlog_web_creator_register')

        user_info = svc.get_user_info(access_token)
        channel_info = svc.get_channel_info(access_token, user_info['id'])
    except Exception as e:
        logger.error(f"Twitch OAuth callback error: {e}")
        messages.error(request, "Failed to connect Twitch account.")
        return redirect('questlog_web_creator_register')

    now = int(time.time())
    with get_db_session() as db:
        profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
        if not profile:
            profile = WebCreatorProfile(
                user_id=request.web_user.id,
                display_name=request.web_user.display_name or request.web_user.username,
                allow_discovery=False,  # User must explicitly opt in on the creator form
                created_at=now,
                updated_at=now,
            )
            db.add(profile)

        profile.twitch_user_id = user_info['id']
        profile.twitch_display_name = user_info['display_name']
        profile.twitch_access_token = encrypt_token(access_token)
        profile.twitch_refresh_token = encrypt_token(refresh_token) if refresh_token else None
        profile.twitch_token_expires = now + token_data.get('expires_in', 3600)
        profile.twitch_follower_count = channel_info.get('follower_count', 0)
        profile.twitch_url = f"https://twitch.tv/{user_info['login']}"
        profile.twitch_last_synced = now
        # Auto-populate avatar from Twitch if not already set
        if not profile.avatar_url and user_info.get('profile_image_url'):
            profile.avatar_url = user_info['profile_image_url']
        profile.updated_at = now
        db.commit()

    messages.success(request, f"Twitch account connected: {user_info['display_name']}")
    return redirect('questlog_web_creator_register')


@require_http_methods(["POST"])
@web_login_required
def twitch_disconnect(request):
    """Disconnect Twitch from creator profile, revoke tokens."""
    from app.utils.encryption import decrypt_token

    with get_db_session() as db:
        profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
        if not profile or not profile.twitch_user_id:
            messages.error(request, "No Twitch account connected.")
            return redirect('questlog_web_creator_register')

        if profile.twitch_access_token:
            try:
                token = decrypt_token(profile.twitch_access_token)
                _requests.post(
                    'https://id.twitch.tv/oauth2/revoke',
                    data={'client_id': django_settings.TWITCH_CLIENT_ID, 'token': token},
                    timeout=10,
                )
            except Exception:
                pass  # Best-effort revocation

        profile.twitch_user_id = None
        profile.twitch_display_name = None
        profile.twitch_access_token = None
        profile.twitch_refresh_token = None
        profile.twitch_token_expires = None
        profile.twitch_follower_count = 0
        profile.twitch_url = None
        profile.twitch_last_synced = None
        profile.updated_at = int(time.time())
        db.commit()

    messages.success(request, "Twitch account disconnected.")
    return redirect('questlog_web_creator_register')


# --- YouTube OAuth (creator profile) ----------------------------------------

@web_login_required
def youtube_oauth_initiate(request):
    """Start YouTube OAuth to link YouTube account to creator profile."""
    state = secrets.token_urlsafe(32)
    request.session['youtube_oauth_state'] = state
    request.session['youtube_oauth_ts'] = int(time.time())

    client_id = django_settings.YOUTUBE_CLIENT_ID
    redirect_uri = django_settings.YOUTUBE_REDIRECT_URI_QL
    if not client_id:
        messages.error(request, "YouTube integration is not configured.")
        return redirect('questlog_web_creator_register')

    scopes = ' '.join(django_settings.YOUTUBE_OAUTH_SCOPES)
    from urllib.parse import urlencode
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode({
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': scopes,
            'access_type': 'offline',
            'prompt': 'consent',
            'state': state,
        })
    )
    return redirect(auth_url)


@web_login_required
def youtube_oauth_callback(request):
    """Handle YouTube OAuth callback — store encrypted tokens on creator profile."""
    from app.utils.encryption import encrypt_token

    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')

    if error or not code:
        messages.error(request, "YouTube authorization was cancelled or failed.")
        return redirect('questlog_web_creator_register')

    saved_state = request.session.pop('youtube_oauth_state', None)
    saved_ts = request.session.pop('youtube_oauth_ts', None)
    if not saved_state or state != saved_state:
        messages.error(request, "Invalid OAuth state. Please try again.")
        return redirect('questlog_web_creator_register')
    if saved_ts and (int(time.time()) - saved_ts) > 1800:
        messages.error(request, "OAuth session expired. Please try again.")
        return redirect('questlog_web_creator_register')

    try:
        redirect_uri = django_settings.YOUTUBE_REDIRECT_URI_QL
        token_resp = _requests.post(
            'https://oauth2.googleapis.com/token',
            data={
                'code': code,
                'client_id': django_settings.YOUTUBE_CLIENT_ID,
                'client_secret': django_settings.YOUTUBE_CLIENT_SECRET,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            },
            timeout=10,
        )
        token_data = token_resp.json()

        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        if not access_token:
            logger.error(f"YouTube token exchange failed: {token_data}")
            messages.error(request, "Failed to get YouTube access token.")
            return redirect('questlog_web_creator_register')

        from app.services.youtube_service import YouTubeService
        svc = YouTubeService()
        channel_info = svc.get_channel_info(access_token)
    except Exception as e:
        logger.error(f"YouTube OAuth callback error: {e}")
        messages.error(request, "Failed to connect YouTube account.")
        return redirect('questlog_web_creator_register')

    now = int(time.time())
    with get_db_session() as db:
        profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
        if not profile:
            profile = WebCreatorProfile(
                user_id=request.web_user.id,
                display_name=request.web_user.display_name or request.web_user.username,
                allow_discovery=False,  # User must explicitly opt in on the creator form
                created_at=now,
                updated_at=now,
            )
            db.add(profile)

        custom_url = channel_info.get('custom_url', '')
        profile.youtube_channel_id = channel_info['id']
        profile.youtube_channel_name = channel_info.get('title', '')
        profile.youtube_access_token = encrypt_token(access_token)
        profile.youtube_refresh_token = encrypt_token(refresh_token) if refresh_token else None
        profile.youtube_token_expires = now + token_data.get('expires_in', 3600)
        profile.youtube_subscriber_count = channel_info.get('subscriber_count', 0)
        profile.youtube_video_count = channel_info.get('video_count', 0)
        if custom_url:
            profile.youtube_url = f"https://youtube.com/{custom_url}"
        elif channel_info.get('id'):
            profile.youtube_url = f"https://youtube.com/channel/{channel_info['id']}"
        profile.youtube_last_synced = now
        # Auto-populate banner from YouTube if not already set
        if not profile.banner_url and channel_info.get('banner_url'):
            profile.banner_url = channel_info['banner_url']
        # Auto-populate avatar from YouTube thumbnail if not already set
        if not profile.avatar_url and channel_info.get('thumbnail_url'):
            profile.avatar_url = channel_info['thumbnail_url']
        profile.updated_at = now

        # Sync channel ID to WebUser so check_live_status cron can find this user
        user = db.query(WebUser).filter_by(id=web_user_id).first()
        if user:
            user.youtube_channel_id = channel_info['id']

        db.commit()

    messages.success(request, f"YouTube channel connected: {channel_info.get('title', 'Unknown')}")
    return redirect('questlog_web_creator_register')


@require_http_methods(["POST"])
@web_login_required
def youtube_disconnect(request):
    """Disconnect YouTube from creator profile."""
    with get_db_session() as db:
        profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
        if not profile or not profile.youtube_channel_id:
            messages.error(request, "No YouTube account connected.")
            return redirect('questlog_web_creator_register')

        profile.youtube_channel_id = None
        profile.youtube_channel_name = None
        profile.youtube_access_token = None
        profile.youtube_refresh_token = None
        profile.youtube_token_expires = None
        profile.youtube_subscriber_count = 0
        profile.youtube_video_count = 0
        profile.youtube_url = None
        profile.youtube_last_synced = None
        profile.updated_at = int(time.time())

        # Clear from WebUser too
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if user:
            user.youtube_channel_id = None
        db.commit()

    messages.success(request, "YouTube account disconnected.")
    return redirect('questlog_web_creator_register')


# --- Kick OAuth (creator profile) --------------------------------------------

@web_login_required
def kick_oauth_initiate(request):
    """Start Kick OAuth to link Kick account to creator profile."""
    state = secrets.token_urlsafe(32)
    request.session['kick_oauth_state'] = state
    request.session['kick_oauth_ts'] = int(time.time())

    client_id = getattr(django_settings, 'KICK_CLIENT_ID', '')
    redirect_uri = getattr(django_settings, 'KICK_REDIRECT_URI_QL', '')
    if not client_id:
        messages.error(request, "Kick integration is not configured.")
        return redirect('questlog_web_creator_register')

    from urllib.parse import urlencode
    auth_url = (
        "https://id.kick.com/oauth/authorize?"
        + urlencode({
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'user:read channel:read',
            'state': state,
        })
    )
    return redirect(auth_url)


@web_login_required
def kick_oauth_callback(request):
    """Handle Kick OAuth callback - store encrypted tokens on creator profile."""
    from app.utils.encryption import encrypt_token

    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')

    if error or not code:
        messages.error(request, "Kick authorization was cancelled or failed.")
        return redirect('questlog_web_creator_register')

    saved_state = request.session.pop('kick_oauth_state', None)
    saved_ts = request.session.pop('kick_oauth_ts', None)
    if not saved_state or state != saved_state:
        messages.error(request, "Invalid OAuth state. Please try again.")
        return redirect('questlog_web_creator_register')
    if saved_ts and (int(time.time()) - saved_ts) > 1800:
        messages.error(request, "OAuth session expired. Please try again.")
        return redirect('questlog_web_creator_register')

    client_id = getattr(django_settings, 'KICK_CLIENT_ID', '')
    client_secret = getattr(django_settings, 'KICK_CLIENT_SECRET', '')
    redirect_uri = getattr(django_settings, 'KICK_REDIRECT_URI_QL', '')

    try:
        token_resp = _requests.post(
            'https://id.kick.com/oauth/token',
            data={
                'code': code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

        access_token = token_data.get('access_token')
        refresh_token = token_data.get('refresh_token')
        if not access_token:
            messages.error(request, "Failed to get Kick access token.")
            return redirect('questlog_web_creator_register')

        # Fetch user info
        user_resp = _requests.get(
            'https://api.kick.com/public/v1/users',
            headers={'Authorization': f'Bearer {access_token}', 'Client-Id': client_id},
            timeout=10,
        )
        user_resp.raise_for_status()
        user_data = user_resp.json().get('data', [{}])[0]
        kick_user_id = str(user_data.get('user_id', '') or user_data.get('id', ''))
        kick_username = user_data.get('username', '') or user_data.get('name', '')
        kick_display_name = user_data.get('name', '') or kick_username

        # Fetch channel info to get slug
        channel_resp = _requests.get(
            'https://api.kick.com/public/v1/channels',
            params={'broadcaster_user_id': kick_user_id} if kick_user_id else {},
            headers={'Authorization': f'Bearer {access_token}', 'Client-Id': client_id},
            timeout=10,
        )
        kick_slug = kick_username  # fallback to username as slug
        kick_follower_count = 0
        if channel_resp.ok:
            ch_data = channel_resp.json().get('data', [{}])
            if ch_data:
                kick_slug = ch_data[0].get('slug', kick_username) or kick_username
                kick_follower_count = ch_data[0].get('followers_count', 0) or 0

    except Exception as e:
        logger.error(f"Kick OAuth callback error: {e}")
        messages.error(request, "Failed to connect Kick account.")
        return redirect('questlog_web_creator_register')

    now = int(time.time())
    with get_db_session() as db:
        profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
        if not profile:
            profile = WebCreatorProfile(
                user_id=request.web_user.id,
                display_name=request.web_user.display_name or request.web_user.username,
                allow_discovery=False,
                created_at=now,
                updated_at=now,
            )
            db.add(profile)

        profile.kick_user_id = kick_user_id
        profile.kick_display_name = kick_display_name
        profile.kick_access_token = encrypt_token(access_token)
        profile.kick_refresh_token = encrypt_token(refresh_token) if refresh_token else None
        profile.kick_token_expires = now + token_data.get('expires_in', 3600)
        profile.kick_slug = kick_slug
        profile.kick_follower_count = kick_follower_count
        profile.kick_url = f"https://kick.com/{kick_slug}"
        profile.kick_last_synced = now
        profile.updated_at = now
        db.commit()

    messages.success(request, f"Kick account connected: {kick_display_name or kick_slug}")
    return redirect('questlog_web_creator_register')


@require_http_methods(["POST"])
@web_login_required
def kick_disconnect(request):
    """Disconnect Kick from creator profile."""
    with get_db_session() as db:
        profile = db.query(WebCreatorProfile).filter_by(user_id=request.web_user.id).first()
        if not profile or not profile.kick_user_id:
            messages.error(request, "No Kick account connected.")
            return redirect('questlog_web_creator_register')

        profile.kick_user_id = None
        profile.kick_display_name = None
        profile.kick_access_token = None
        profile.kick_refresh_token = None
        profile.kick_token_expires = None
        profile.kick_slug = None
        profile.kick_follower_count = 0
        profile.kick_url = None
        profile.kick_last_synced = None
        profile.updated_at = int(time.time())
        db.commit()

    messages.success(request, "Kick account disconnected.")
    return redirect('questlog_web_creator_register')


# =============================================================================
# PASSWORD RESET
# =============================================================================

@ratelimit(key='ip', rate='5/h', block=True)
@require_http_methods(["GET", "POST"])
def password_reset_request(request):
    """Step 1: User enters their email to request a reset link."""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        # Always show success to avoid email enumeration
        if email:
            try:
                django_user = DjangoUser.objects.filter(email__iexact=email, is_active=True).first()
                if django_user:
                    # Include last 8 chars of password hash so token is invalidated after use
                    token = signing.dumps({
                        'uid': django_user.pk,
                        'ph': (django_user.password or '')[-8:],
                    }, salt=RESET_SALT)
                    reset_url = request.build_absolute_uri(f'/ql/password-reset/confirm/{token}/')
                    send_mail(
                        subject='Reset your QuestLog password',
                        message=(
                            f"Hi {django_user.username},\n\n"
                            f"Someone requested a password reset for your QuestLog account.\n\n"
                            f"Click the link below to set a new password:\n\n"
                            f"{reset_url}\n\n"
                            f"This link expires in 1 hour.\n\n"
                            f"If you didn't request this, you can safely ignore this email.\n\n"
                            f"— QuestLog at Casual Heroes"
                        ),
                        from_email=django_settings.DEFAULT_FROM_EMAIL,
                        recipient_list=[django_user.email],
                        fail_silently=True,
                    )
                    logger.info(f"Password reset email sent for {django_user.username}")
            except Exception as e:
                logger.error(f"Password reset request error: {e}")
        return render(request, 'questlog_web/password_reset_request.html', {'sent': True})

    return render(request, 'questlog_web/password_reset_request.html', {})


@ratelimit(key='ip', rate='10/h', block=True)
@require_http_methods(["GET", "POST"])
def password_reset_confirm(request, token):
    """Step 2: User clicks link, sets new password."""
    error = None
    try:
        data = signing.loads(token, salt=RESET_SALT, max_age=RESET_MAX_AGE)
        uid = data.get('uid')
        pw_hash_snippet = data.get('ph', '')
        django_user = DjangoUser.objects.get(pk=uid, is_active=True)
        # Invalidate token if password has already been changed since it was issued.
        # We store the last 8 chars of the password hash in the token - if they
        # no longer match, the token has already been used or the password changed.
        if not pw_hash_snippet or not hmac.compare_digest(
            pw_hash_snippet, (django_user.password or '')[-8:]
        ):
            return render(request, 'questlog_web/password_reset_confirm.html', {'invalid': True})
    except signing.SignatureExpired:
        return render(request, 'questlog_web/password_reset_confirm.html', {'expired': True})
    except Exception:
        return render(request, 'questlog_web/password_reset_confirm.html', {'invalid': True})

    if request.method == 'POST':
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        if password1 != password2:
            error = "Passwords do not match."
        else:
            try:
                validate_password(password1, django_user)
            except ValidationError as e:
                error = " ".join(e.messages)

        if not error:
            django_user.set_password(password1)
            django_user.save()
            # Invalidate all other sessions so stolen sessions can't persist after reset
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, django_user)
            logger.info(f"Password reset completed for {django_user.username}")
            return render(request, 'questlog_web/password_reset_confirm.html', {'success': True})

    return render(request, 'questlog_web/password_reset_confirm.html', {
        'token': token,
        'username': django_user.username,
        'error': error,
    })


# =========================================================================
# MATRIX ACCOUNT LINKING (MAS OAuth)
# =========================================================================
# Flow:
#   1. User clicks "Connect" on profile page -> matrix_link_initiate
#   2. Redirect to MAS authorize endpoint with PKCE state
#   3. User logs in / authorizes on MAS
#   4. MAS redirects to /ql/auth/matrix/callback/ with ?code=
#   5. Exchange code for token, fetch userinfo, store matrix_id on web_users
#   6. /ql/auth/matrix/unlink/ clears the fields

_MAS_CLIENT_ID     = getattr(django_settings, 'MAS_CLIENT_ID', '')
_MAS_CLIENT_SECRET = getattr(django_settings, 'MAS_CLIENT_SECRET', '')
_MAS_REDIRECT_URI  = getattr(django_settings, 'MAS_REDIRECT_URI', '')
_MAS_ISSUER        = getattr(django_settings, 'MAS_ISSUER', 'https://sso.casual-heroes.com')
_MAS_INTERNAL_URL  = getattr(django_settings, 'MAS_INTERNAL_URL', 'http://localhost:8181')
_MAS_AUTH_URL      = f'{_MAS_ISSUER}/authorize'
# Token + userinfo use internal URL to bypass Cloudflare on server-to-server calls
_MAS_TOKEN_URL     = f'{_MAS_INTERNAL_URL}/oauth2/token'
_MAS_USERINFO_URL  = f'{_MAS_INTERNAL_URL}/oauth2/userinfo'


@web_login_required
def matrix_link_initiate(request):
    """Redirect user to MAS OAuth authorize endpoint."""
    if not _MAS_CLIENT_ID or not _MAS_CLIENT_SECRET:
        messages.error(request, "Matrix linking is not configured on this server.")
        return redirect('questlog_web_profile')

    state = secrets.token_urlsafe(32)
    request.session['ql_matrix_link_state'] = state
    request.session['ql_matrix_link_ts']    = int(time.time())

    from urllib.parse import urlencode
    params = {
        'client_id':     _MAS_CLIENT_ID,
        'redirect_uri':  _MAS_REDIRECT_URI,
        'response_type': 'code',
        'scope':         'openid',
        'state':         state,
    }
    return redirect(f"{_MAS_AUTH_URL}?{urlencode(params)}")


@web_login_required
@ratelimit(key='user', rate='10/h', block=True)
def matrix_link_verify(request):
    """MAS redirects here after authorization. Save matrix_id to WebUser."""
    error = request.GET.get('error')
    if error:
        messages.error(request, f"Matrix authorization failed: {error}")
        return redirect('questlog_web_profile')

    code  = request.GET.get('code', '')
    state = request.GET.get('state', '')

    stored_state = request.session.pop('ql_matrix_link_state', None)
    stored_ts    = request.session.pop('ql_matrix_link_ts', 0)

    if not state or state != stored_state:
        messages.error(request, "Invalid OAuth state. Please try again.")
        return redirect('questlog_web_profile')

    if int(time.time()) - stored_ts > 600:
        messages.error(request, "OAuth session expired. Please try again.")
        return redirect('questlog_web_profile')

    if not code:
        messages.error(request, "No authorization code received.")
        return redirect('questlog_web_profile')

    # Exchange code for token
    try:
        token_resp = _requests.post(_MAS_TOKEN_URL, data={
            'grant_type':   'authorization_code',
            'code':         code,
            'redirect_uri': _MAS_REDIRECT_URI,
        }, auth=(_MAS_CLIENT_ID, _MAS_CLIENT_SECRET),
           headers={'Content-Type': 'application/x-www-form-urlencoded'}, timeout=10)
        token_resp.raise_for_status()
        access_token = token_resp.json().get('access_token')
    except Exception as e:
        logger.error(f"matrix_link_verify: token exchange failed: {e}")
        messages.error(request, "Failed to connect to Matrix. Please try again.")
        return redirect('questlog_web_profile')

    # Fetch userinfo to get Matrix ID
    try:
        userinfo_resp = _requests.get(_MAS_USERINFO_URL,
                                      headers={'Authorization': f'Bearer {access_token}'},
                                      timeout=10)
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
    except Exception as e:
        logger.error(f"matrix_link_verify: userinfo fetch failed: {e}")
        messages.error(request, "Failed to retrieve Matrix profile. Please try again.")
        return redirect('questlog_web_profile')

    logger.info(f"matrix_link_verify: userinfo fields: {list(userinfo.keys())} sub={userinfo.get('sub')} username={userinfo.get('username')} preferred_username={userinfo.get('preferred_username')}")
    # MAS sub is internal user ID - construct Matrix ID from username + homeserver
    mas_username = userinfo.get('username') or userinfo.get('preferred_username') or ''
    matrix_id = userinfo.get('matrix_user_id') or (f'@{mas_username}:{_MAS_ISSUER.split("//")[-1].split("/")[0].replace("sso.", "")}' if mas_username else '')
    matrix_username = mas_username

    if not matrix_id:
        messages.error(request, "Could not read Matrix ID. Please try again.")
        return redirect('questlog_web_profile')

    with get_db_session() as db:
        from .models import WebUser as _WebUser
        existing = db.query(_WebUser).filter(
            _WebUser.matrix_id == matrix_id,
            _WebUser.id != request.web_user.id,
        ).first()
        if existing:
            messages.error(request, "That Matrix account is already linked to another QuestLog account.")
            return redirect('questlog_web_profile')

        u = db.query(_WebUser).filter_by(id=request.web_user.id).first()
        if u:
            u.matrix_id       = matrix_id
            u.matrix_username = matrix_username
            u.updated_at      = int(time.time())
            db.commit()

    logger.info(f"Matrix account linked: user={request.web_user.id} matrix_id={matrix_id}")
    messages.success(request, f"Matrix account linked! Welcome, {matrix_username}.")
    return redirect('questlog_web_profile')


@require_http_methods(["POST"])
@web_login_required
def matrix_unlink(request):
    """Unlink Matrix account."""
    with get_db_session() as db:
        from .models import WebUser as _WebUser
        u = db.query(_WebUser).filter_by(id=request.web_user.id).first()
        if u:
            u.matrix_id       = None
            u.matrix_username = None
            u.updated_at      = int(time.time())
            db.commit()
    logger.info(f"Matrix account unlinked: user={request.web_user.id}")
    messages.success(request, "Matrix account disconnected.")
    return redirect('questlog_web_profile')
