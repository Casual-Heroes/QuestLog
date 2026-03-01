# QuestLog Web -- TOTP 2FA views

import json
import time
import secrets
import logging

import bcrypt
import pyotp

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .models import WebUser, WebUserTOTP
from app.db import get_db_session
from .helpers import web_login_required, get_web_user
from app.utils.encryption import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_backup_codes():
    """Return 8 plaintext backup codes in XXXXXXXX-XXXXXXXX format."""
    return [
        secrets.token_hex(4).upper() + '-' + secrets.token_hex(4).upper()
        for _ in range(8)
    ]


def _hash_backup_codes(codes):
    """Return list of bcrypt hashes for storage."""
    return [
        bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode()
        for c in codes
    ]


def _check_backup_code(submitted, hashed_list):
    """
    Check submitted code against list of bcrypt hashes.
    Returns (matched_index, True) or (-1, False).
    """
    code = submitted.strip().upper()
    for i, h in enumerate(hashed_list):
        if bcrypt.checkpw(code.encode(), h.encode()):
            return i, True
    return -1, False


def _verify_totp_code(rec, code):
    """
    Verify a 6-digit TOTP code against the stored (encrypted) secret.
    Returns True if valid.
    """
    try:
        secret = decrypt_token(rec.secret_enc)
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# totp_verify -- /ql/2fa/verify/
# ---------------------------------------------------------------------------

@ratelimit(key='ip', rate='10/h', block=True)
def totp_verify(request):
    """
    Shown after successful username/password auth when the user has 2FA enabled.
    Expects session keys: web_2fa_pending_user_id, web_2fa_pending_is_admin,
    web_2fa_pending_next.
    """
    pending_user_id = request.session.get('web_2fa_pending_user_id')
    if not pending_user_id:
        return redirect('/ql/login/')

    error = None
    use_backup = request.GET.get('backup') == '1' or request.POST.get('use_backup') == '1'

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        is_backup = request.POST.get('use_backup') == '1'

        with get_db_session() as db:
            rec = db.query(WebUserTOTP).filter_by(
                user_id=pending_user_id, is_enabled=True
            ).first()

            if not rec:
                # 2FA record disappeared — allow through
                _complete_2fa_login(request, pending_user_id, db)
                return redirect(request.session.pop('web_2fa_pending_next', '/ql/'))

            verified = False

            if is_backup:
                hashes = json.loads(rec.backup_codes or '[]')
                idx, verified = _check_backup_code(code, hashes)
                if verified:
                    hashes.pop(idx)
                    rec.backup_codes = json.dumps(hashes)
                    db.commit()
            else:
                verified = _verify_totp_code(rec, code)

            if verified:
                _complete_2fa_login(request, pending_user_id, db)
                next_url = request.session.pop('web_2fa_pending_next', '/ql/')
                # Clear pending keys
                request.session.pop('web_2fa_pending_user_id', None)
                request.session.pop('web_2fa_pending_is_admin', None)
                request.session.modified = True
                return redirect(next_url)
            else:
                logger.warning(f"2FA verify failed for user_id={pending_user_id} backup={is_backup}")
                error = "Invalid code. Please try again."
                use_backup = is_backup

    return render(request, 'questlog_web/2fa_verify.html', {
        'error': error,
        'use_backup': use_backup,
    })


def _complete_2fa_login(request, user_id, db):
    """Write the full session keys once 2FA passes."""
    user = db.query(WebUser).filter_by(id=user_id).first()
    if not user:
        return
    request.session['web_user_id']       = user.id
    request.session['web_user_name']     = user.username
    request.session['web_user_avatar']   = user.avatar_url or ''
    request.session['web_user_is_admin'] = bool(user.is_admin)
    request.session.modified = True


# ---------------------------------------------------------------------------
# totp_setup -- GET /ql/2fa/setup/
# ---------------------------------------------------------------------------

@web_login_required
def totp_setup(request):
    """
    Show the QR code / manual key setup page.
    Creates (or reuses) an un-enabled WebUserTOTP record with a fresh secret.
    """
    web_user = get_web_user(request)
    if not web_user:
        return redirect('/ql/login/')

    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=web_user['id']).first()
        rec = db.query(WebUserTOTP).filter_by(user_id=user.id).first()

        # Always generate a fresh secret on setup load (unless already enabled)
        if not rec:
            secret = pyotp.random_base32()
            rec = WebUserTOTP(
                user_id=user.id,
                secret_enc=encrypt_token(secret),
                is_enabled=False,
                backup_codes='[]',
                created_at=int(time.time()),
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
        elif rec.is_enabled:
            # Already enabled -- redirect to profile
            return redirect('/ql/profile/edit/#2fa')
        else:
            secret = decrypt_token(rec.secret_enc)

        issuer = 'CasualHeroes QuestLog'
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.username,
            issuer_name=issuer,
        )

    return render(request, 'questlog_web/2fa_setup.html', {
        'otpauth_uri': uri,
        'manual_secret': secret,
    })


# ---------------------------------------------------------------------------
# api_2fa_enable -- POST /ql/api/2fa/enable/
# ---------------------------------------------------------------------------

@web_login_required
@require_http_methods(['POST'])
def api_2fa_enable(request):
    """
    Verify first TOTP code and activate 2FA. Returns backup codes (shown once).
    """
    web_user = get_web_user(request)
    if not web_user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    code = request.POST.get('code', '').strip()
    if not code:
        return JsonResponse({'error': 'Code is required'}, status=400)

    with get_db_session() as db:
        rec = db.query(WebUserTOTP).filter_by(
            user_id=web_user['id'], is_enabled=False
        ).first()

        if not rec:
            return JsonResponse({'error': '2FA record not found. Visit /ql/2fa/setup/ first.'}, status=400)

        if not _verify_totp_code(rec, code):
            return JsonResponse({'error': 'Invalid code. Make sure your authenticator is synced.'}, status=400)

        # Generate backup codes
        plaintext_codes = _generate_backup_codes()
        rec.backup_codes = json.dumps(_hash_backup_codes(plaintext_codes))
        rec.is_enabled   = True
        rec.enabled_at   = int(time.time())
        db.commit()

    return JsonResponse({'success': True, 'backup_codes': plaintext_codes})


# ---------------------------------------------------------------------------
# api_2fa_disable -- POST /ql/api/2fa/disable/
# ---------------------------------------------------------------------------

@web_login_required
@require_http_methods(['POST'])
def api_2fa_disable(request):
    """Disable 2FA. Requires a valid current TOTP code to confirm."""
    web_user = get_web_user(request)
    if not web_user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    code = request.POST.get('code', '').strip()
    if not code:
        return JsonResponse({'error': 'Code is required'}, status=400)

    with get_db_session() as db:
        rec = db.query(WebUserTOTP).filter_by(
            user_id=web_user['id'], is_enabled=True
        ).first()

        if not rec:
            return JsonResponse({'error': '2FA is not enabled'}, status=400)

        if not _verify_totp_code(rec, code):
            return JsonResponse({'error': 'Invalid code'}, status=400)

        db.delete(rec)
        db.commit()

    return JsonResponse({'success': True})


# ---------------------------------------------------------------------------
# api_2fa_backup_codes -- POST /ql/api/2fa/regenerate-backup-codes/
# ---------------------------------------------------------------------------

@web_login_required
@require_http_methods(['POST'])
def api_2fa_backup_codes(request):
    """Regenerate backup codes. Requires a valid TOTP code."""
    web_user = get_web_user(request)
    if not web_user:
        return JsonResponse({'error': 'Not authenticated'}, status=401)

    code = request.POST.get('code', '').strip()
    if not code:
        return JsonResponse({'error': 'Code is required'}, status=400)

    with get_db_session() as db:
        rec = db.query(WebUserTOTP).filter_by(
            user_id=web_user['id'], is_enabled=True
        ).first()

        if not rec:
            return JsonResponse({'error': '2FA is not enabled'}, status=400)

        if not _verify_totp_code(rec, code):
            return JsonResponse({'error': 'Invalid code'}, status=400)

        plaintext_codes = _generate_backup_codes()
        rec.backup_codes = json.dumps(_hash_backup_codes(plaintext_codes))
        db.commit()

    return JsonResponse({'success': True, 'backup_codes': plaintext_codes})
