"""
Scheduler interno para tareas programadas del chat global.

Ejecuta la limpieza semanal del chat de la comunidad cada domingo a las 23:59
(hora local del servidor). Corre como un hilo daemon dentro del proceso del
servidor (daphne/runserver), por lo que no requiere Celery, cron ni ninguna
infraestructura adicional. La limpieza NO depende de que un usuario abra la app.

Si prefieres ejecutarlo desde el cron del sistema, también puedes usar:
    python manage.py cleanup_global_chat
"""
import threading
import logging
from datetime import datetime, timedelta

from django.utils import timezone
from django.db import close_old_connections

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 60 * 30  # revisa cada 30 minutos


def _next_sunday_cleanup_time(now):
    """Calcula el próximo domingo a las 23:59:00 (hora local)."""
    days_until_sunday = (6 - now.weekday()) % 7  # Monday=0 ... Sunday=6
    target = (now + timedelta(days=days_until_sunday)).replace(
        hour=23, minute=59, second=0, microsecond=0
    )
    # Si hoy es domingo pero ya pasó la hora, programar para el próximo domingo
    if target <= now:
        target += timedelta(days=7)
    return target


def run_weekly_cleanup():
    """Ejecuta la limpieza semanal del chat global."""
    from apps.games.models import GlobalChatMessage

    week_ago = timezone.now() - timezone.timedelta(days=7)
    deleted, _ = GlobalChatMessage.objects.filter(created_at__lt=week_ago).delete()
    logger.info(f"[scheduler] Limpieza semanal del chat global: {deleted} mensajes eliminados.")


def _scheduler_loop():
    """Bucle del scheduler: espera al domingo y limpia."""
    next_cleanup = _next_sunday_cleanup_time(timezone.localtime())
    logger.info(f"[scheduler] Próxima limpieza del chat global: {next_cleanup}")

    while True:
        now = timezone.localtime()
        if now >= next_cleanup:
            try:
                close_old_connections()
                run_weekly_cleanup()
            except Exception as e:
                logger.exception(f"[scheduler] Error en limpieza semanal: {e}")
            finally:
                close_old_connections()
                next_cleanup = _next_sunday_cleanup_time(timezone.localtime())
                logger.info(f"[scheduler] Próxima limpieza del chat global: {next_cleanup}")
        threading.Event().wait(CHECK_INTERVAL_SECONDS)


def start_scheduler():
    """Inicia el scheduler en un hilo daemon (idempotente)."""
    if getattr(start_scheduler, '_started', False):
        return
    start_scheduler._started = True
    t = threading.Thread(target=_scheduler_loop, name='global-chat-scheduler', daemon=True)
    t.start()
    logger.info("[scheduler] Scheduler del chat global iniciado.")