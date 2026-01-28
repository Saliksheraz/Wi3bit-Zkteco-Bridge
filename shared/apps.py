from django.apps import AppConfig


class SharedConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'shared'

    def ready(self):
        from .scheduler import start
        import os

        if os.getenv('DISABLE_SCHEDULER') == '1':
            return
        start()