"""Custom template tags for LFG system."""
from django import template
from app.db import get_db_session
from app.models import LFGConfig, Guild

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


@register.simple_tag
def is_premium(guild_id):
    """Check if a guild has premium features (Premium tier or VIP)."""
    try:
        with get_db_session() as db:
            guild = db.query(Guild).filter_by(guild_id=int(guild_id)).first()
            if not guild:
                return False
            return guild.subscription_tier == 'premium' or guild.is_vip
    except Exception:
        return False
