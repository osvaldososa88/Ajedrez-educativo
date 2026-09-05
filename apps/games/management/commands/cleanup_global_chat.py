"""
Limpieza semanal del chat global de la comunidad.

Elimina únicamente los mensajes del GlobalChatMessage con más de 7 días
(comienza una nueva semana con el chat limpio). Los chats de partidas
(ChatMessage) NO se ven afectados.

Ejecución:
  - Manual:        python manage.py cleanup_global_chat
  - Programada:    se ejecuta automáticamente cada domingo (ver
                   apps/games/scheduler.py, iniciado por GamesConfig.ready())
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.games.models import GlobalChatMessage, ChatMessage


class Command(BaseCommand):
    help = 'Elimina los mensajes del chat global de la comunidad con más de 7 días (limpieza semanal).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Muestra cuántos mensajes se eliminarían sin borrarlos.',
        )

    def handle(self, *args, **options):
        now = timezone.now()
        week_ago = now - timezone.timedelta(days=7)

        to_delete = GlobalChatMessage.objects.filter(created_at__lt=week_ago)
        count = to_delete.count()

        if options['dry_run']:
            self.stdout.write(
                f'[dry-run] Se eliminarían {count} mensajes del chat global.'
            )
        else:
            deleted, _ = to_delete.delete()
            self.stdout.write(
                self.style.SUCCESS(
                    f'Chat global limpiado: {deleted} mensajes eliminados (semana iniciada el {week_ago:%Y-%m-%d %H:%M}).'
                )
            )

        # Verificación de seguridad: los chats de partidas nunca se tocan aquí.
        game_chat_count = ChatMessage.objects.count()
        self.stdout.write(f'Mensajes de chats de partidas (sin cambios): {game_chat_count}')