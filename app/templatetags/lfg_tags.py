"""Custom template tags for LFG system."""
from django import template
from app.db import get_db_session
from app.models import LFGConfig

register = template.Library()


@register.simple_tag
def is_attendance_enabled(guild_id):
    """Check if attendance tracking is enabled for a guild."""
    try:
        with get_db_session() as db:
            config = db.query(LFGConfig).filter_by(guild_id=int(guild_id)).first()
            return config and config.attendance_tracking_enabled
    except Exception:
        return False
