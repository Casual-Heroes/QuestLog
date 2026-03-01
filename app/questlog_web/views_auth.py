# QuestLog Web — authentication & OAuth views

import re
import time
import json
import logging
import secrets
import requests as _requests

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
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

from .models import WebUser, WebCreatorProfile, WebReferral, WebSiteConfig, WebFlair, WebUserFlair
from app.db import get_db_session
from .helpers import (
    get_web_user, web_login_required, STEAM_API_KEY, safe_redirect_url,
    award_hero_points,
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
FOUNDING_FLAIR_LIMIT = 25


def _maybe_award_founding_flair(user, db):
    """Award the Founding Member flair to the first FOUNDING_FLAIR_LIMIT users to log in."""
    try:
        flair = db.query(WebFlair).filter_by(name=FOUNDING_FLAIR_NAME, enabled=True).first()
        if not flair:
            return
        already_has = db.query(WebUserFlair).filter_by(user_id=user.id, flair_id=flair.id).first()
        if already_has:
            return
        owner_count = db.query(WebUserFlair).filter_by(flair_id=flair.id).count()
        if owner_count >= FOUNDING_FLAIR_LIMIT:
            return
        db.add(WebUserFlair(user_id=user.id, flair_id=flair.id))
        # Auto-equip it if they have no flair set
        if not user.active_flair_id:
            user.active_flair_id = flair.id
        db.commit()
        logger.info('Founding Member flair awarded to user %s (%d/%d)', user.username, owner_count + 1, FOUNDING_FLAIR_LIMIT)
    except Exception as e:
        logger.error('_maybe_award_founding_flair failed for user %s: %s', user.username, e)


@ratelimit(key='ip', rate='20/m', block=True)
def ql_login(request):
    """Site login — username + password via Django auth."""
    if request.session.get('web_user_id'):
        return redirect(safe_redirect_url(request.GET.get('next', '/ql/')))

    with get_db_session() as db:
        cfg = db.query(WebSiteConfig).filter_by(key='logins_disabled').first()
        if cfg and cfg.value == '1':
            return render(request, 'questlog_web/login.html', {'logins_disabled': True})

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        next_url = safe_redirect_url(request.POST.get('next', '/ql/'))

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
                    })
            except DjangoUser.DoesNotExist:
                pass
            messages.error(request, "Invalid username or password.")
            return render(request, 'questlog_web/login.html', {'next': next_url})

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
                return render(request, 'questlog_web/login.html', {'next': next_url})

            if user.is_banned:
                django_logout(request)
                reason = f": {user.ban_reason}" if user.ban_reason else ""
                messages.error(request, f"This account has been banned{reason}.")
                return render(request, 'questlog_web/login.html', {'next': next_url})

            if not user.email_verified:
                django_logout(request)
                request.session['pending_verification_uid'] = django_user.pk
                request.session['pending_verification_email'] = django_user.email
                messages.warning(request, "Please verify your email before logging in. Check your inbox or request a new link below.")
                return render(request, 'questlog_web/login.html', {'next': next_url, 'pending_verification': django_user.email})

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

        # 2. Timing
        try:
            elapsed = int(time.time()) - int(request.POST.get('_ts', '0'))
            if 0 < elapsed < 3:
                logger.warning(f"Admin login timing check failed ({elapsed}s) from {_get_remote_ip(request)}")
                messages.error(request, "Invalid credentials.")
                return render(request, 'questlog_web/admin_login.html', ctx)
        except (ValueError, TypeError):
            pass

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


@ratelimit(key='ip', rate='5/h', block=True)
def ql_register(request):
    """Account registration — username + password via Django auth."""
    if request.session.get('web_user_id'):
        return redirect('/ql/')

    with get_db_session() as db:
        cfg = db.query(WebSiteConfig).filter_by(key='logins_disabled').first()
        if cfg and cfg.value == '1':
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
            })

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
        return redirect('questlog_web_settings')

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
        return redirect('questlog_web_settings')

    code  = request.GET.get('code',  '')
    state = request.GET.get('state', '')

    stored_state = request.session.pop('ql_discord_link_state', None)
    stored_ts    = request.session.pop('ql_discord_link_ts', 0)

    # CSRF state check
    if not state or state != stored_state:
        messages.error(request, "Invalid OAuth state. Please try again.")
        return redirect('questlog_web_settings')

    # Expire after 10 minutes
    if int(time.time()) - stored_ts > 600:
        messages.error(request, "OAuth session expired. Please try again.")
        return redirect('questlog_web_settings')

    if not code:
        messages.error(request, "No authorisation code received.")
        return redirect('questlog_web_settings')

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
        return redirect('questlog_web_settings')

    try:
        user_resp = _requests.get(f"{_DISCORD_API}/users/@me",
                                   headers={'Authorization': f'Bearer {access_token}'},
                                   timeout=10)
        user_resp.raise_for_status()
        discord_data = user_resp.json()
    except Exception as e:
        logger.error(f"discord_link_callback: user fetch failed: {e}")
        messages.error(request, "Failed to retrieve Discord profile. Please try again.")
        return redirect('questlog_web_settings')

    discord_id       = str(discord_data.get('id', ''))
    discord_username = discord_data.get('global_name') or discord_data.get('username', '')
    avatar_hash      = discord_data.get('avatar', '')

    if not discord_id:
        messages.error(request, "Could not read Discord ID. Please try again.")
        return redirect('questlog_web_settings')

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
            return redirect('questlog_web_settings')

        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        user.discord_id       = discord_id
        user.discord_username = discord_username
        user.updated_at       = int(time.time())
        db.commit()

    messages.success(request, f"Discord account @{discord_username} linked successfully!")
    return redirect('questlog_web_settings')


@require_http_methods(["POST"])
@web_login_required
def discord_unlink(request):
    """Remove the linked Discord account from the user's profile."""
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=request.web_user.id).first()
        if not user or not user.discord_id:
            messages.error(request, "No Discord account is linked.")
            return redirect('questlog_web_settings')

        user.discord_id       = None
        user.discord_username = None
        user.updated_at       = int(time.time())
        db.commit()

    messages.success(request, "Discord account disconnected.")
    return redirect('questlog_web_settings')


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
        profile.updated_at = now
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
        db.commit()

    messages.success(request, "YouTube account disconnected.")
    return redirect('questlog_web_creator_register')
