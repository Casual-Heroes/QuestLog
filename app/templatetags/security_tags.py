"""Custom template tags for security-related functionality."""
from django import template
from urllib.parse import urlparse

register = template.Library()

# Allowed URL schemes for safe rendering
ALLOWED_SCHEMES = {'http', 'https'}


@register.filter
def safe_url(url):
    """
    Filter that validates a URL has a safe scheme (http/https only).

    Prevents XSS attacks via javascript:, data:, vbscript:, etc. URLs.
    Returns empty string if URL is unsafe or invalid.

    Usage in templates:
        <a href="{{ article.link|safe_url }}">Link</a>
        {% if article.link|safe_url %}...{% endif %}
    """
    if not url:
        return ''

    url = str(url).strip()
    if not url:
        return ''

    try:
        parsed = urlparse(url)
    except Exception:
        return ''

    # Only allow http and https schemes
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return ''

    return url


@register.filter
def is_safe_url(url):
    """
    Filter that returns True if URL has a safe scheme, False otherwise.

    Usage in templates:
        {% if article.link|is_safe_url %}
            <a href="{{ article.link }}">Link</a>
        {% endif %}
    """
    return bool(safe_url(url))
