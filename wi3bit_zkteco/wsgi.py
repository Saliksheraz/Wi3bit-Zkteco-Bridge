############ End Test Code ##################

############ Test Code Here ##################

"""
WSGI config for wi3bit_zkteco project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wi3bit_zkteco.settings')

application = get_wsgi_application()
