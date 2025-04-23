"""
WSGI config for casualsite project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys

from django.core.wsgi import get_wsgi_application
from dotenv import load_dotenv

load_dotenv('/srv/secrets/ch_env/.env')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'casualsite.settings')

application = get_wsgi_application()
sys.path.append("/srv/ch-webserver")
