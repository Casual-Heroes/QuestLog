"""
Security Middleware - Block suspicious requests and path traversal attacks
"""
from django.http import HttpResponseNotFound
import logging

logger = logging.getLogger(__name__)

# List of suspicious file patterns that should never be accessible
BLOCKED_PATTERNS = [
    '.env', '.git', '.svn', '.hg', '.DS_Store',
    'web.config', 'htaccess', 'htpasswd',
    '.bak', '.backup', '.old', '.save', '.swp', '.tmp',
    'config.php', 'wp-config.php', 'configuration.php',
    'credentials', 'secrets', 'password',
    '.npmrc', '.dockerenv', 'docker-compose',
    'id_rsa', 'id_dsa', 'authorized_keys',
    'database.yml', 'settings.py.bak',
]

# Blocked directory traversal patterns
BLOCKED_DIRS = [
    '../', '..\\', '%2e%2e/', '%2e%2e\\',
    '..%2f', '..%5c', '%252e%252e',
]

class SecurityMiddleware:
    """
    Custom security middleware to block access to sensitive files and
    detect path traversal attacks.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Get the request path
        path = request.path.lower()

        # Check for blocked file patterns
        for pattern in BLOCKED_PATTERNS:
            if pattern in path:
                logger.warning(
                    f"Blocked suspicious request from {self.get_client_ip(request)}: {request.path}"
                )
                return HttpResponseNotFound()

        # Check for path traversal attempts
        for pattern in BLOCKED_DIRS:
            if pattern in request.path or pattern in request.path.lower():
                logger.warning(
                    f"Blocked path traversal attempt from {self.get_client_ip(request)}: {request.path}"
                )
                return HttpResponseNotFound()

        # Continue processing request
        response = self.get_response(request)
        return response

    @staticmethod
    def get_client_ip(request):
        """Get the client's real IP address."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
