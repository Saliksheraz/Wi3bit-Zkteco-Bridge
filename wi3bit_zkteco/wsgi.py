############ End Test Code ##################
from shared.wi3bit_sync_bridge import Wi3bitSyncBridge

bridge_inst = Wi3bitSyncBridge()
bridge_inst.update_local_attendance()


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
