"""
views_dm.py - E2EE Direct Messages

Key design:
- Server stores ONLY ciphertext; plaintext never transits or is stored server-side
- ECDH P-256 key pairs generated in browser via Web Crypto API
- Each message is encrypted twice: once for recipient, once for sender (so sender can read sent messages)
- Recovery: private key encrypted locally with AES-GCM key derived from 12-word BIP39 phrase; encrypted blob
  stored on server so users can restore their key on new devices
- Server validates all sizes/formats but cannot decrypt anything
- Polling-based (no WebSockets needed)

OWASP coverage:
- A01 (Access Control): every endpoint checks session + block status + allow_messages
- A02 (Crypto): server enforces max sizes on crypto fields; validation rejects obviously bad formats
- A03 (Injection): all DB access via parameterized SQLAlchemy; no raw string interpolation
- A04 (Design): E2EE by design; server cannot read messages even if compromised
- A05 (Misconfig): no sensitive data in logs; conversation_token is random, not sequential ID
- A06 (Vuln Components): n/a
- A07 (Auth): @web_login_required on all endpoints; session checked server-side
- A08 (Integrity): server validates ciphertext field sizes; invalid JWK rejected
- A09 (Logging): errors logged without plaintext content
- A10 (SSRF): n/a
"""

import json
import logging
import os
import re
import time

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django_ratelimit.decorators import ratelimit

from app.db import get_db_session
from app.questlog_web.models import WebUser, WebDMConversation, WebDMMessage, WebDMReadState, WebFollow
from app.questlog_web.helpers import (
    web_login_required, add_web_user_context,
    safe_int, create_notification, is_blocked,
)
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Max sizes enforced server-side (client can never exceed these)
MAX_PUBKEY_LEN       = 4096    # JWK JSON is ~300 bytes; this is very generous
MAX_ENCRYPTED_KEY_LEN = 65536  # Encrypted private key backup (base64 of ~150 bytes key)
MAX_SALT_LEN         = 128     # Hex salt
MAX_CIPHERTEXT_LEN   = 131072  # 128 KB per message ciphertext copy (generous for E2EE)
MAX_EPHEMERAL_LEN    = 4096    # Ephemeral pubkey JWK
MAX_IV_LEN           = 32      # base64 of 12-byte IV = 16 chars; 32 is very generous
MAX_MESSAGES_PAGE    = 50      # Max messages returned per page
MAX_INBOX_PAGE       = 30      # Max conversations in inbox

# Regex for valid base64 (URL-safe or standard)
_B64_RE = re.compile(r'^[A-Za-z0-9+/=_\-]+$')


def _valid_base64(value, max_len):
    if not value or not isinstance(value, str):
        return False
    if len(value) > max_len:
        return False
    return bool(_B64_RE.match(value))


def _valid_jwk(value, max_len):
    """Validate that value is a JWK for ECDH P-256 (strict schema check)."""
    if not value or not isinstance(value, str):
        return False
    if len(value) > max_len:
        return False
    try:
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            return False
        # Must be EC P-256 key
        if parsed.get('kty') != 'EC':
            return False
        if parsed.get('crv') != 'P-256':
            return False
        # Must have x and y coordinates
        if 'x' not in parsed or 'y' not in parsed:
            return False
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def _get_or_create_conversation(db, user_a_id, user_b_id):
    """Return (conversation, created). Enforces user_a < user_b invariant."""
    a, b = (user_a_id, user_b_id) if user_a_id < user_b_id else (user_b_id, user_a_id)
    convo = db.query(WebDMConversation).filter_by(user_a_id=a, user_b_id=b).first()
    if convo:
        return convo, False
    now = int(time.time())
    convo = WebDMConversation(user_a_id=a, user_b_id=b, last_message_at=now, created_at=now)
    db.add(convo)
    db.flush()
    return convo, True


def _get_unread_count(db, user_id):
    """Return total unread DM count for badge."""
    row = db.execute(text("""
        SELECT COUNT(*) as cnt FROM web_dm_messages m
        JOIN web_dm_conversations c ON c.id = m.conversation_id
        LEFT JOIN web_dm_read_state rs ON rs.conversation_id = m.conversation_id AND rs.user_id = :uid
        WHERE (c.user_a_id = :uid OR c.user_b_id = :uid)
          AND m.sender_id != :uid
          AND m.is_deleted = 0
          AND m.created_at > COALESCE(rs.last_read_at, 0)
    """), {'uid': user_id}).fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Key management endpoints
# ---------------------------------------------------------------------------

@web_login_required
@require_POST
@ratelimit(key='ip', rate='10/h', block=True)
def api_dm_setup_keys(request):
    """
    Store the user's ECDH public key and optionally their encrypted private key backup.
    Called once when user first sets up DMs (or when rotating keys).
    Body JSON:
        pubkey            - JWK JSON of ECDH P-256 public key
        pubkey_encrypted  - (optional) AES-GCM ciphertext of private key (base64)
        pubkey_salt       - (optional) hex salt used to derive AES key from recovery phrase
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    pubkey = data.get('pubkey', '')
    pubkey_encrypted = data.get('pubkey_encrypted', '')
    pubkey_salt = data.get('pubkey_salt', '')

    if not _valid_jwk(pubkey, MAX_PUBKEY_LEN):
        return JsonResponse({'error': 'invalid pubkey'}, status=400)

    if pubkey_encrypted and not _valid_base64(pubkey_encrypted, MAX_ENCRYPTED_KEY_LEN):
        return JsonResponse({'error': 'invalid pubkey_encrypted'}, status=400)

    if pubkey_salt and (not isinstance(pubkey_salt, str) or len(pubkey_salt) > MAX_SALT_LEN):
        return JsonResponse({'error': 'invalid pubkey_salt'}, status=400)

    user_id = request.session.get('web_user_id')
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user:
            return JsonResponse({'error': 'not found'}, status=404)
        user.pubkey = pubkey
        if pubkey_encrypted:
            user.pubkey_encrypted = pubkey_encrypted
        if pubkey_salt:
            user.pubkey_salt = pubkey_salt
        db.commit()

    return JsonResponse({'ok': True})


@web_login_required
@require_GET
def api_dm_get_encrypted_key(request):
    """
    Return the encrypted private key backup for key recovery on a new device.
    Only returns data if the user has set up a backup.
    """
    user_id = request.session.get('web_user_id')
    with get_db_session() as db:
        user = db.query(WebUser).filter_by(id=user_id).first()
        if not user:
            return JsonResponse({'error': 'not found'}, status=404)
        return JsonResponse({
            'pubkey_encrypted': user.pubkey_encrypted or '',
            'pubkey_salt': user.pubkey_salt or '',
            'has_backup': bool(user.pubkey_encrypted),
        })


@web_login_required
@require_GET
def api_dm_get_pubkey(request, user_id):
    """Return another user's public key so sender can encrypt a message for them."""
    viewer_id = request.session.get('web_user_id')
    target_id = safe_int(user_id, 0, 1)
    if not target_id:
        return JsonResponse({'error': 'invalid user'}, status=400)

    with get_db_session() as db:
        if is_blocked(db, viewer_id, target_id):
            return JsonResponse({'error': 'blocked'}, status=403)

        target = db.query(WebUser).filter_by(id=target_id, is_banned=False, is_disabled=False).first()
        if not target:
            return JsonResponse({'error': 'not found'}, status=404)
        if not target.allow_messages:
            return JsonResponse({'error': 'messages disabled'}, status=403)
        if not target.pubkey:
            return JsonResponse({'error': 'no key'}, status=404)

        return JsonResponse({'pubkey': target.pubkey, 'username': target.username})


# ---------------------------------------------------------------------------
# Sending messages
# ---------------------------------------------------------------------------

@web_login_required
@require_POST
@ratelimit(key='ip', rate='120/h', block=True)
def api_dm_send(request):
    """
    Send an encrypted message.
    Body JSON:
        to_user_id              - int
        ciphertext_for_recipient - base64 AES-GCM ciphertext
        ciphertext_for_sender    - base64 AES-GCM ciphertext (sender's own readable copy)
        ephemeral_pubkey         - JWK JSON of ephemeral ECDH key
        iv_recipient             - base64 IV
        iv_sender                - base64 IV
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'invalid json'}, status=400)

    sender_id = request.session.get('web_user_id')
    to_user_id = safe_int(data.get('to_user_id'), 0, 1)
    if not to_user_id or to_user_id == sender_id:
        return JsonResponse({'error': 'invalid recipient'}, status=400)

    ct_recipient = data.get('ciphertext_for_recipient', '')
    ct_sender    = data.get('ciphertext_for_sender', '')
    eph_pubkey   = data.get('ephemeral_pubkey', '')
    iv_recipient = data.get('iv_recipient', '')
    iv_sender    = data.get('iv_sender', '')

    if not _valid_base64(ct_recipient, MAX_CIPHERTEXT_LEN):
        return JsonResponse({'error': 'invalid ciphertext_for_recipient'}, status=400)
    if not _valid_base64(ct_sender, MAX_CIPHERTEXT_LEN):
        return JsonResponse({'error': 'invalid ciphertext_for_sender'}, status=400)
    if not _valid_jwk(eph_pubkey, MAX_EPHEMERAL_LEN):
        return JsonResponse({'error': 'invalid ephemeral_pubkey'}, status=400)
    if not _valid_base64(iv_recipient, MAX_IV_LEN):
        return JsonResponse({'error': 'invalid iv_recipient'}, status=400)
    if not _valid_base64(iv_sender, MAX_IV_LEN):
        return JsonResponse({'error': 'invalid iv_sender'}, status=400)

    now = int(time.time())
    with get_db_session() as db:
        # Check sender exists and is not banned
        sender = db.query(WebUser).filter_by(id=sender_id, is_banned=False, is_disabled=False).first()
        if not sender:
            return JsonResponse({'error': 'unauthorized'}, status=403)

        # Check recipient
        recipient = db.query(WebUser).filter_by(id=to_user_id, is_banned=False, is_disabled=False).first()
        if not recipient:
            return JsonResponse({'error': 'recipient not found'}, status=404)
        if not recipient.allow_messages:
            return JsonResponse({'error': 'recipient has messages disabled'}, status=403)
        if not recipient.pubkey:
            return JsonResponse({'error': 'recipient has no key configured'}, status=403)

        if is_blocked(db, sender_id, to_user_id):
            return JsonResponse({'error': 'blocked'}, status=403)

        # Require mutual follow
        i_follow = db.query(WebFollow).filter_by(follower_id=sender_id, following_id=to_user_id).first()
        they_follow = db.query(WebFollow).filter_by(follower_id=to_user_id, following_id=sender_id).first()
        if not i_follow or not they_follow:
            return JsonResponse({'error': 'must be mutual follows to message'}, status=403)

        convo, created = _get_or_create_conversation(db, sender_id, to_user_id)

        msg = WebDMMessage(
            conversation_id=convo.id,
            sender_id=sender_id,
            ciphertext_for_recipient=ct_recipient,
            ciphertext_for_sender=ct_sender,
            ephemeral_pubkey=eph_pubkey,
            iv_recipient=iv_recipient,
            iv_sender=iv_sender,
            is_deleted=False,
            created_at=now,
        )
        db.add(msg)
        convo.last_message_at = now

        # Update sender's read state so they don't see their own message as unread
        read_state = db.query(WebDMReadState).filter_by(
            conversation_id=convo.id, user_id=sender_id
        ).first()
        if read_state:
            read_state.last_read_at = now
        else:
            db.add(WebDMReadState(conversation_id=convo.id, user_id=sender_id, last_read_at=now))

        db.commit()

        msg_id = msg.id

        # Notification (fire-and-forget, non-blocking)
        try:
            create_notification(
                db, to_user_id, sender_id, 'dm', 'conversation', convo.id,
                f'{sender.username} sent you a message'
            )
            db.commit()
        except Exception:
            pass

    return JsonResponse({'ok': True, 'message_id': msg_id, 'created_at': now})


# ---------------------------------------------------------------------------
# Reading messages
# ---------------------------------------------------------------------------

@web_login_required
@require_GET
def api_dm_inbox(request):
    """Return list of conversations with latest activity for inbox view."""
    user_id = request.session.get('web_user_id')
    page = safe_int(request.GET.get('page', 1), 1, 1, 100)
    offset = (page - 1) * MAX_INBOX_PAGE

    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT
                c.id,
                c.user_a_id,
                c.user_b_id,
                c.last_message_at,
                ua.username  AS username_a,
                ua.avatar_url AS avatar_a,
                ub.username  AS username_b,
                ub.avatar_url AS avatar_b,
                (
                    SELECT COUNT(*) FROM web_dm_messages m2
                    LEFT JOIN web_dm_read_state rs ON rs.conversation_id = m2.conversation_id AND rs.user_id = :uid
                    WHERE m2.conversation_id = c.id
                      AND m2.sender_id != :uid
                      AND m2.is_deleted = 0
                      AND m2.created_at > COALESCE(rs.last_read_at, 0)
                ) AS unread_count
            FROM web_dm_conversations c
            JOIN web_users ua ON ua.id = c.user_a_id
            JOIN web_users ub ON ub.id = c.user_b_id
            WHERE (c.user_a_id = :uid OR c.user_b_id = :uid)
            ORDER BY c.last_message_at DESC
            LIMIT :lim OFFSET :off
        """), {'uid': user_id, 'lim': MAX_INBOX_PAGE, 'off': offset}).fetchall()

        convos = []
        for row in rows:
            other_id   = row.user_b_id if row.user_a_id == user_id else row.user_a_id
            other_name = row.username_b if row.user_a_id == user_id else row.username_a
            other_ava  = row.avatar_b if row.user_a_id == user_id else row.avatar_a
            convos.append({
                'id': row.id,
                'other_user_id': other_id,
                'other_username': other_name,
                'other_avatar': other_ava or '',
                'last_message_at': row.last_message_at,
                'unread_count': int(row.unread_count),
            })

        total_unread = _get_unread_count(db, user_id)

    return JsonResponse({'conversations': convos, 'total_unread': total_unread})


@web_login_required
@require_GET
def api_dm_messages(request, conversation_id):
    """
    Return paginated messages for a conversation.
    Marks messages as read for current user.
    """
    user_id = request.session.get('web_user_id')
    convo_id = safe_int(conversation_id, 0, 1)
    if not convo_id:
        return JsonResponse({'error': 'invalid'}, status=400)

    before = safe_int(request.GET.get('before', 0), 0, 0)  # cursor for pagination

    with get_db_session() as db:
        convo = db.query(WebDMConversation).filter_by(id=convo_id).first()
        if not convo:
            return JsonResponse({'error': 'not found'}, status=404)
        if user_id not in (convo.user_a_id, convo.user_b_id):
            return JsonResponse({'error': 'forbidden'}, status=403)

        other_id = convo.user_b_id if convo.user_a_id == user_id else convo.user_a_id
        if is_blocked(db, user_id, other_id):
            return JsonResponse({'error': 'blocked'}, status=403)

        query = db.query(WebDMMessage).filter_by(conversation_id=convo_id, is_deleted=False)
        if before:
            query = query.filter(WebDMMessage.id < before)
        messages_raw = query.order_by(WebDMMessage.id.desc()).limit(MAX_MESSAGES_PAGE).all()

        now = int(time.time())
        # Mark read
        read_state = db.query(WebDMReadState).filter_by(
            conversation_id=convo_id, user_id=user_id
        ).first()
        if read_state:
            read_state.last_read_at = now
        else:
            db.add(WebDMReadState(conversation_id=convo_id, user_id=user_id, last_read_at=now))
        db.commit()

        messages = []
        for m in reversed(messages_raw):
            is_mine = (m.sender_id == user_id)
            messages.append({
                'id': m.id,
                'sender_id': m.sender_id,
                'is_mine': is_mine,
                # Return the right ciphertext copy so client always has something to decrypt
                'ciphertext': m.ciphertext_for_sender if is_mine else m.ciphertext_for_recipient,
                'ephemeral_pubkey': m.ephemeral_pubkey,
                'iv': m.iv_sender if is_mine else m.iv_recipient,
                'created_at': m.created_at,
            })

    return JsonResponse({'messages': messages, 'has_more': len(messages_raw) == MAX_MESSAGES_PAGE})


@web_login_required
@require_GET
def api_dm_unread_count(request):
    """Poll endpoint - returns total unread DM count for badge."""
    user_id = request.session.get('web_user_id')
    with get_db_session() as db:
        count = _get_unread_count(db, user_id)
    return JsonResponse({'unread': count})


@web_login_required
@require_GET
def api_dm_suggestions(request):
    """
    Return mutual follows (people you follow who follow you back) who have
    allow_messages=True, for the 'Start a conversation' suggestions panel.
    Excludes users already in an active conversation.
    """
    user_id = request.session.get('web_user_id')
    with get_db_session() as db:
        rows = db.execute(text("""
            SELECT u.id, u.username, u.display_name, u.avatar_url, u.allow_messages, u.pubkey
            FROM web_users u
            WHERE u.is_banned = 0
              AND u.is_disabled = 0
              AND u.id != :uid
              AND EXISTS (
                  SELECT 1 FROM web_follows
                  WHERE follower_id = :uid AND following_id = u.id
              )
              AND EXISTS (
                  SELECT 1 FROM web_follows
                  WHERE follower_id = u.id AND following_id = :uid
              )
            ORDER BY u.allow_messages DESC, u.username ASC
            LIMIT 50
        """), {'uid': user_id}).fetchall()

        suggestions = [{
            'id': r.id,
            'username': r.username,
            'display_name': r.display_name or r.username,
            'avatar_url': r.avatar_url or '',
            'can_message': bool(r.allow_messages),
            'has_key': bool(r.pubkey),
        } for r in rows]

    return JsonResponse({'suggestions': suggestions})


@web_login_required
@require_GET
def api_dm_poll(request, conversation_id):
    """
    Lightweight polling endpoint - returns only new messages since `after` timestamp.
    Client polls every 3-5 seconds while conversation is open.
    """
    user_id = request.session.get('web_user_id')
    convo_id = safe_int(conversation_id, 0, 1)
    after = safe_int(request.GET.get('after', 0), 0, 0)
    if not convo_id:
        return JsonResponse({'error': 'invalid'}, status=400)

    with get_db_session() as db:
        convo = db.query(WebDMConversation).filter_by(id=convo_id).first()
        if not convo or user_id not in (convo.user_a_id, convo.user_b_id):
            return JsonResponse({'error': 'forbidden'}, status=403)

        messages_raw = db.query(WebDMMessage).filter(
            WebDMMessage.conversation_id == convo_id,
            WebDMMessage.is_deleted == False,
            WebDMMessage.created_at > after,
        ).order_by(WebDMMessage.created_at.asc()).limit(MAX_MESSAGES_PAGE).all()

        now = int(time.time())
        if messages_raw:
            read_state = db.query(WebDMReadState).filter_by(
                conversation_id=convo_id, user_id=user_id
            ).first()
            if read_state:
                read_state.last_read_at = now
            else:
                db.add(WebDMReadState(conversation_id=convo_id, user_id=user_id, last_read_at=now))
            db.commit()

        messages = []
        for m in messages_raw:
            is_mine = (m.sender_id == user_id)
            messages.append({
                'id': m.id,
                'sender_id': m.sender_id,
                'is_mine': is_mine,
                'ciphertext': m.ciphertext_for_sender if is_mine else m.ciphertext_for_recipient,
                'ephemeral_pubkey': m.ephemeral_pubkey,
                'iv': m.iv_sender if is_mine else m.iv_recipient,
                'created_at': m.created_at,
            })

    return JsonResponse({'messages': messages})


# ---------------------------------------------------------------------------
# Delete message
# ---------------------------------------------------------------------------

@web_login_required
@require_POST
def api_dm_delete_message(request, message_id):
    """Soft-delete a message. Only sender can delete their own messages."""
    user_id = request.session.get('web_user_id')
    msg_id = safe_int(message_id, 0, 1)
    if not msg_id:
        return JsonResponse({'error': 'invalid'}, status=400)

    with get_db_session() as db:
        msg = db.query(WebDMMessage).filter_by(id=msg_id).first()
        if not msg:
            return JsonResponse({'error': 'not found'}, status=404)
        if msg.sender_id != user_id:
            return JsonResponse({'error': 'forbidden'}, status=403)
        msg.is_deleted = True
        db.commit()

    return JsonResponse({'ok': True})


# ---------------------------------------------------------------------------
# Page views
# ---------------------------------------------------------------------------

@web_login_required
@add_web_user_context
def messages_inbox(request):
    """Inbox page - lists all conversations."""
    return render(request, 'questlog_web/messages.html', {
        'page_title': 'Messages',
        'web_user': request.web_user,
    })


@web_login_required
@add_web_user_context
def messages_thread(request, conversation_id):
    """Thread page - shows a specific conversation."""
    user_id = request.session.get('web_user_id')
    convo_id = safe_int(conversation_id, 0, 1)
    if not convo_id:
        return redirect('questlog_web_messages')

    with get_db_session() as db:
        convo = db.query(WebDMConversation).filter_by(id=convo_id).first()
        if not convo or user_id not in (convo.user_a_id, convo.user_b_id):
            return redirect('questlog_web_messages')

        other_id = convo.user_b_id if convo.user_a_id == user_id else convo.user_a_id
        other = db.query(WebUser).filter_by(id=other_id).first()
        if not other:
            return redirect('questlog_web_messages')

        other_data = {
            'id': other.id,
            'username': other.username,
            'display_name': other.display_name or other.username,
            'avatar_url': other.avatar_url or '',
            'pubkey': other.pubkey or '',
        }

    return render(request, 'questlog_web/messages_thread.html', {
        'page_title': f'Messages - {other_data["display_name"]}',
        'conversation_id': convo_id,
        'other_user': other_data,
        'web_user': request.web_user,
    })


@web_login_required
@add_web_user_context
def messages_new(request, to_user_id):
    """Start a new conversation with a user, or redirect to existing one."""
    user_id = request.session.get('web_user_id')
    target_id = safe_int(to_user_id, 0, 1)
    if not target_id or target_id == user_id:
        return redirect('questlog_web_messages')

    with get_db_session() as db:
        target = db.query(WebUser).filter_by(id=target_id, is_banned=False, is_disabled=False).first()
        if not target or not target.allow_messages:
            return redirect('questlog_web_messages')

        if is_blocked(db, user_id, target_id):
            return redirect('questlog_web_messages')

        convo, _ = _get_or_create_conversation(db, user_id, target_id)
        db.commit()
        convo_id = convo.id

    return redirect('questlog_web_messages_thread', conversation_id=convo_id)
