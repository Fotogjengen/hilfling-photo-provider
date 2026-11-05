"""
WSGI config for hilfling_photo_provider project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hilfling_photo_provider.settings.prod')

application = get_wsgi_application()

# Load itkacl at startup, so a missing install fails the app load instead of the first lookup
from hilfling_photo_provider.utils.itk_auth import load_itkacl  # noqa: E402

load_itkacl()
