from django.apps import AppConfig


class GamesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.games'

    def ready(self):
        """Inicia el scheduler semanal del chat global junto con el servidor."""
        # Evitar arrancar durante comandos de management (migrations, collectstatic, etc.)
        import sys
        argv = sys.argv
        management_commands = {
            'makemigrations', 'migrate', 'collectstatic', 'test', 'shell',
            'dbshell', 'check', 'createsuperuser', 'loaddata', 'dumpdata',
            'cleanup_global_chat', 'flush', 'squashmigrations', 'showmigrations',
        }
        if len(argv) > 1 and argv[1] in management_commands:
            return

        from apps.games.scheduler import start_scheduler
        try:
            start_scheduler()
        except Exception:
            # No bloquear el arranque del servidor si el scheduler falla
            pass