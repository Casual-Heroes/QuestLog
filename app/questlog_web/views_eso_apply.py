"""ESO Guild Application views."""
import json, time, logging
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from app.db import get_db_session
from sqlalchemy import text
from .models import WebEsoApplication, WebUser, WebNotification
from .helpers import web_login_required, add_web_user_context, web_admin_required, sanitize_text

logger = logging.getLogger(__name__)

# ESO has 7 classes, each with 3 subclasses (skill lines)
ESO_CLASSES = {
    'Dragonknight': ['Ardent Flame', 'Draconic Power', 'Earthen Heart'],
    'Sorcerer':     ['Dark Magic', 'Daedric Summoning', 'Storm Calling'],
    'Nightblade':   ['Assassination', 'Shadow', 'Siphoning'],
    'Templar':      ['Aedric Spear', 'Dawn\'s Wrath', 'Restoring Light'],
    'Warden':       ['Animal Companions', 'Green Balance', 'Winter\'s Embrace'],
    'Necromancer':  ['Grave Lord', 'Bone Tyrant', 'Living Death'],
    'Arcanist':     ['Herald of the Tome', 'Soldier of Apocrypha', 'Curative Runeforms'],
}

ALL_CLASSES = list(ESO_CLASSES.keys())

EXPERIENCE_LEVELS = [
    ('new',        'New to ESO - just starting out'),
    ('leveling',   'Leveling up - working through the story'),
    ('cp',         'CP grind - building Champion Points'),
    ('casual',     'Endgame casual - dungeons, trials, events'),
    ('vet',        'Veteran content - hard mode dungeons & trials'),
    ('raider',     'Trial raider - progression focused'),
    ('pvp',        'PvP player - Cyrodiil / Imperial City / BGs'),
    ('crafter',    'Master crafter - provisioner, enchanter, etc.'),
    ('collector',  'Collector - housing, cosmetics, achievements'),
]

CONTENT_INTERESTS = [
    'Normal Dungeons',
    'Veteran Dungeons',
    'Normal Trials',
    'Veteran Trials (Hard Mode)',
    'Arenas (Maelstrom / Vateshran)',
    'Cyrodiil (Large Scale PvP)',
    'Imperial City (PvP)',
    'Battlegrounds (PvP)',
    'Crafting & Trading',
    'Housing & Decorating',
    'Event Farming',
    'Achievement Hunting',
    'Exploring & Story',
    'Just vibing / social',
]

ROLES = [
    'Tank',
    'Healer',
    'Damage (DPS)',
    'Flexible / All roles',
]

AVAILABILITY_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

REFERRAL_OPTIONS = [
    'Friend / Guild member',
    'Discord / Fluxer',
    'Reddit',
    'ESO Forums / ZOS',
    'Search engine',
    'QuestLog website',
    'Other',
]


@add_web_user_context
@require_http_methods(["GET"])
def eso_apply(request):
    """ESO Guild application form page."""
    web_user = request.web_user
    existing = None
    if web_user:
        with get_db_session() as db:
            existing = db.query(WebEsoApplication).filter_by(
                web_user_id=web_user.id
            ).order_by(WebEsoApplication.submitted_at.desc()).first()
            if existing:
                existing = {
                    'id': existing.id,
                    'status': existing.status,
                    'character_name': existing.character_name,
                    'submitted_at': existing.submitted_at,
                    'admin_notes': existing.admin_notes or '',
                }

    return render(request, 'questlog_web/eso_apply.html', {
        'web_user': web_user,
        'active_page': 'eso_apply',
        'eso_classes': ESO_CLASSES,
        'all_classes': ALL_CLASSES,
        'experience_levels': EXPERIENCE_LEVELS,
        'content_interests': CONTENT_INTERESTS,
        'roles': ROLES,
        'availability_days': AVAILABILITY_DAYS,
        'referral_options': REFERRAL_OPTIONS,
        'existing': existing,
    })


@web_login_required
@add_web_user_context
@require_http_methods(["POST"])
def api_eso_apply(request):
    """Submit ESO Guild application."""
    web_user = request.web_user

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    character_name = sanitize_text(data.get('character_name', ''), max_length=100).strip()
    main_class     = data.get('main_class', '').strip()
    subclass       = data.get('subclass', '').strip()
    role_raw       = data.get('role', [])
    if isinstance(role_raw, str):
        role_raw = [role_raw] if role_raw.strip() else []
    role_raw = [r.strip() for r in role_raw if r.strip()]
    experience_raw = data.get('experience_level', [])
    if isinstance(experience_raw, str):
        experience_raw = [experience_raw] if experience_raw.strip() else []
    experience_raw = [e.strip() for e in experience_raw if e.strip()]
    interests      = data.get('content_interests', [])
    availability   = data.get('availability', [])
    why_join       = sanitize_text(data.get('why_join', ''), max_length=2000).strip()
    about_me       = sanitize_text(data.get('about_me', ''), max_length=1000).strip()
    referral       = sanitize_text(data.get('referral', ''), max_length=100).strip()

    # Validate
    if not character_name:
        return JsonResponse({'error': 'Character name is required.'}, status=400)
    if main_class not in ALL_CLASSES:
        return JsonResponse({'error': 'Please select a valid main class.'}, status=400)
    if subclass and subclass not in ALL_CLASSES:
        return JsonResponse({'error': 'Please select a valid sub class.'}, status=400)
    if subclass and main_class == subclass:
        return JsonResponse({'error': 'Main class and sub class cannot be the same.'}, status=400)

    valid_levels = set(dict(EXPERIENCE_LEVELS).keys())
    experience_raw = [e for e in experience_raw if e in valid_levels]
    if not experience_raw:
        return JsonResponse({'error': 'Please select at least one experience level.'}, status=400)
    experience = ','.join(experience_raw)

    role_raw = [r for r in role_raw if r in ROLES]
    if not role_raw:
        return JsonResponse({'error': 'Please select at least one role.'}, status=400)
    role = ','.join(role_raw)

    if not why_join or len(why_join) < 20:
        return JsonResponse({'error': 'Please tell us a bit more about why you want to join (at least 20 characters).'}, status=400)

    interests    = [i for i in interests if i in CONTENT_INTERESTS]
    availability = [d for d in availability if d in AVAILABILITY_DAYS]

    with get_db_session() as db:
        existing = db.query(WebEsoApplication).filter(
            WebEsoApplication.web_user_id == web_user.id,
            WebEsoApplication.status.in_(['pending', 'approved'])
        ).first()
        if existing:
            if existing.status == 'approved':
                return JsonResponse({'error': 'You already have an approved application.'}, status=400)
            return JsonResponse({'error': 'You already have a pending application. Please wait for a response.'}, status=400)

        app = WebEsoApplication(
            web_user_id       = web_user.id,
            character_name    = character_name,
            main_class        = main_class,
            subclass          = subclass,
            role              = role,
            experience_level  = experience,
            content_interests = json.dumps(interests),
            availability      = json.dumps(availability),
            why_join          = why_join,
            about_me          = about_me or None,
            referral          = referral or None,
            status            = 'pending',
            submitted_at      = int(time.time()),
        )
        db.add(app)
        db.flush()
        app_id = app.id
        db.commit()

    try:
        _notify_application(web_user.username, character_name, main_class, subclass, role, experience, app_id)
    except Exception as e:
        logger.error(f"ESO application Fluxer notify failed: {e}")

    try:
        _notify_admins_new_application(web_user.id, web_user.username, character_name, app_id)
    except Exception as e:
        logger.error(f"ESO application admin bell notify failed: {e}")

    return JsonResponse({'success': True, 'message': 'Application submitted! We will review it and get back to you.'})


def _notify_application(username, character_name, main_class, subclass, role, experience, app_id):
    from .fluxer_webhooks import _queue_notification, BRAND_COLOR, _fire_discord_guide_webhook
    from app.db import get_db_session
    from .models import WebFluxerWebhookConfig
    exp_map = dict(EXPERIENCE_LEVELS)
    exp_label = ', '.join(exp_map.get(e, e) for e in experience.split(',') if e)
    site_url = 'https://questlog.casual-heroes.com'
    embed_data = {
        'title': '\U0001f4dc New ESO Guild Application',
        'description': (
            f"**{character_name}**\n"
            f"QuestLog user: **{username}**\n\n"
            f"**Main Class:** {main_class}\n"
            f"**Sub Class:** {subclass}\n"
            f"**Role:** {role}\n"
            f"**Experience:** {exp_label}\n\n"
            f"[Review in Admin Panel]({site_url}/ql/admin/#eso-applications)"
        ),
        'footer': 'QuestLog - ESO Guild Applications',
    }
    _queue_notification('eso_application', embed_data, BRAND_COLOR)
    try:
        with get_db_session() as db:
            cfg = db.query(WebFluxerWebhookConfig).filter_by(
                event_type='eso_application', is_enabled=True
            ).first()
            if cfg and cfg.discord_webhook_url:
                _fire_discord_guide_webhook(cfg.discord_webhook_url, embed_data)
    except Exception as e:
        logger.error(f"ESO application Discord webhook failed: {e}")


def _notify_admins_new_application(applicant_id, username, character_name, app_id):
    with get_db_session() as db:
        staff = db.query(WebUser).filter(
            (WebUser.is_admin == True) | (WebUser.is_mod == True),
            WebUser.is_banned == False,
        ).all()
        now = int(time.time())
        for staff_member in staff:
            if staff_member.id == applicant_id:
                continue
            notif = WebNotification(
                user_id=staff_member.id,
                actor_id=applicant_id,
                notification_type='eso_app_new',
                target_type='eso_application',
                target_id=app_id,
                message=f"{username} ({character_name}) submitted an ESO guild application",
                is_read=False,
                created_at=now,
            )
            db.add(notif)
        db.commit()


def _notify_applicant_result(applicant_id, reviewer_id, action, app_id):
    if action == 'approved':
        message = "Your ESO guild application has been approved! Welcome to Casual Heroes."
    else:
        message = "Your ESO guild application was not approved at this time. Check the admin notes for details."
    with get_db_session() as db:
        notif = WebNotification(
            user_id=applicant_id,
            actor_id=reviewer_id,
            notification_type='eso_app_result',
            target_type='eso_application',
            target_id=app_id,
            message=message,
            is_read=False,
            created_at=int(time.time()),
        )
        db.add(notif)
        db.commit()


# -- Admin API ----------------------------------------------------------------

@web_admin_required
@add_web_user_context
@require_http_methods(["GET"])
def api_admin_eso_applications(request):
    """GET all ESO applications. ?status=pending|approved|denied"""
    status_filter = request.GET.get('status', 'pending')
    with get_db_session() as db:
        q = db.query(WebEsoApplication)
        if status_filter in ('pending', 'approved', 'denied'):
            q = q.filter_by(status=status_filter)
        apps = q.order_by(WebEsoApplication.submitted_at.desc()).limit(100).all()
        result = []
        for a in apps:
            result.append({
                'id': a.id,
                'web_user_id': a.web_user_id,
                'character_name': a.character_name,
                'main_class': a.main_class,
                'subclass': a.subclass,
                'skill_line': a.skill_line or '',
                'role': a.role,
                'experience_level': a.experience_level,
                'content_interests': json.loads(a.content_interests or '[]'),
                'availability': json.loads(a.availability or '[]'),
                'why_join': a.why_join,
                'about_me': a.about_me or '',
                'referral': a.referral or '',
                'status': a.status,
                'admin_notes': a.admin_notes or '',
                'submitted_at': a.submitted_at,
                'reviewed_at': a.reviewed_at,
            })
    return JsonResponse({'success': True, 'applications': result})


@web_admin_required
@add_web_user_context
@require_http_methods(["POST"])
def api_admin_eso_application_review(request, app_id):
    """POST to approve or deny an ESO application."""
    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action', '').strip()
    notes  = sanitize_text(data.get('notes', ''), max_length=500)

    if action not in ('approved', 'denied', 'pending'):
        return JsonResponse({'error': 'Invalid action.'}, status=400)

    applicant_user_id = None
    with get_db_session() as db:
        app = db.query(WebEsoApplication).filter_by(id=app_id).first()
        if not app:
            return JsonResponse({'error': 'Application not found.'}, status=404)
        applicant_user_id = app.web_user_id
        app.status      = action
        app.admin_notes = notes or None
        app.reviewed_at = int(time.time())
        app.reviewed_by = request.web_user.id
        db.commit()

    if applicant_user_id and action in ('approved', 'denied'):
        try:
            _notify_applicant_result(applicant_user_id, request.web_user.id, action, app_id)
        except Exception as e:
            logger.error(f"ESO application result notify failed: {e}")

    return JsonResponse({'success': True, 'status': action})
