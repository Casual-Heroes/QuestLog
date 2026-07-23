"""
WSGI config for casualsite project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys

import requests as _requests_global
_orig_session_request = _requests_global.Session.request
def _default_timeout_request(self, method, url, **kwargs):
    kwargs.setdefault('timeout', 10)
    return _orig_session_request(self, method, url, **kwargs)
_requests_global.Session.request = _default_timeout_request

from django.core.wsgi import get_wsgi_application
from dotenv import load_dotenv

# Legacy production deployments still use this file. Explicit development or
# staging environments must never backfill missing variables from it.
if not os.getenv('QUESTLOG_ENV_FILE'):
    load_dotenv('/srv/secrets/ch_env/.env')

# Add project directory to Python path BEFORE loading Django
sys.path.insert(0, "/srv/ch-webserver")

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

application = get_wsgi_application()
