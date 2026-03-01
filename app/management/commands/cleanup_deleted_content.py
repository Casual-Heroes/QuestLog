"""
Management command: cleanup_deleted_content
Hard-deletes soft-deleted posts and comments older than the retention window.

GDPR data minimization: soft-deleted content is hidden immediately but the
underlying data is purged after RETENTION_DAYS to ensure it isn't kept forever.

Recommended cron (run daily at 3 AM as www-data):
    0 3 * * * /srv/ch-webserver/chwebsiteprj/bin/python /srv/ch-webserver/manage.py cleanup_deleted_content >> /srv/ch-webserver/logs/cleanup.log 2>&1

Also purges:
  - Read notifications older than 3 days
  - Audit log entries older than 90 days
"""
import time
import logging

from django.core.management.base import BaseCommand

from app.db import get_db_session
from app.questlog_web.models import (
    WebPost, WebPostImage, WebComment, WebLike, WebCommentLike,
    WebNotification, AdminAuditLog,
)

logger = logging.getLogger(__name__)

# Soft-deleted posts/comments are hard-deleted after this many days
POST_RETENTION_DAYS = 90
COMMENT_RETENTION_DAYS = 90

# Read notifications are purged after this many days
NOTIFICATION_RETENTION_DAYS = 3

# Audit log entries are purged after this many days
AUDIT_LOG_RETENTION_DAYS = 90


class Command(BaseCommand):
    help = "Hard-delete soft-deleted posts/comments and prune old notifications/audit logs"

    def handle(self, *args, **options):
        now = int(time.time())
        post_cutoff = now - (POST_RETENTION_DAYS * 86400)
        comment_cutoff = now - (COMMENT_RETENTION_DAYS * 86400)
        notif_cutoff = now - (NOTIFICATION_RETENTION_DAYS * 86400)
        audit_cutoff = now - (AUDIT_LOG_RETENTION_DAYS * 86400)

        with get_db_session() as db:
            # --- Hard-delete old soft-deleted posts ---
            # Find posts marked deleted before the retention cutoff.
            # updated_at is stamped to deletion time in all user-facing delete paths.
            old_posts = db.query(WebPost).filter(
                WebPost.is_deleted == True,
                WebPost.updated_at < post_cutoff,
            ).all()

            post_ids = [p.id for p in old_posts]
            purged_posts = 0

            for post_id in post_ids:
                try:
                    # Remove child records first to avoid FK constraint errors
                    db.query(WebPostImage).filter_by(post_id=post_id).delete(synchronize_session=False)
                    db.query(WebLike).filter_by(post_id=post_id).delete(synchronize_session=False)
                    db.query(WebCommentLike).filter(
                        WebCommentLike.comment_id.in_(
                            db.query(WebComment.id).filter_by(post_id=post_id)
                        )
                    ).delete(synchronize_session=False)
                    db.query(WebComment).filter_by(post_id=post_id).delete(synchronize_session=False)
                    db.query(WebPost).filter_by(id=post_id).delete(synchronize_session=False)
                    db.commit()
                    purged_posts += 1
                except Exception as exc:
                    logger.error(f"cleanup: failed to purge post {post_id}: {exc}")
                    db.rollback()

            # --- Hard-delete old soft-deleted comments (not already removed above) ---
            old_comments = db.query(WebComment).filter(
                WebComment.is_deleted == True,
                WebComment.updated_at < comment_cutoff,
            ).all()

            purged_comments = 0
            for comment in old_comments:
                try:
                    db.query(WebCommentLike).filter_by(comment_id=comment.id).delete(synchronize_session=False)
                    db.delete(comment)
                    db.commit()
                    purged_comments += 1
                except Exception as exc:
                    logger.error(f"cleanup: failed to purge comment {comment.id}: {exc}")
                    db.rollback()

            # --- Purge read notifications past retention window ---
            purged_notifs = db.query(WebNotification).filter(
                WebNotification.is_read == True,
                WebNotification.created_at < notif_cutoff,
            ).delete(synchronize_session=False)
            db.commit()

            # --- Prune old audit log entries ---
            purged_audit = db.query(AdminAuditLog).filter(
                AdminAuditLog.created_at < audit_cutoff,
            ).delete(synchronize_session=False)
            db.commit()

        msg = (
            f"cleanup_deleted_content: purged {purged_posts} posts, "
            f"{purged_comments} comments, {purged_notifs} notifications, "
            f"{purged_audit} audit log entries"
        )
        logger.info(msg)
        self.stdout.write(self.style.SUCCESS(msg))
