import uuid
from django.db import models
from django.conf import settings


class Notification(models.Model):
    """
    Notificación para un usuario. Puede estar relacionada con una partida,
    un problema, un torneo, etc.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="Usuario destinatario"
    )
    type = models.CharField(
        max_length=50,
        verbose_name="Tipo",
        help_text="Ej: challenge_request, game_result, puzzle_published, etc."
    )
    title = models.CharField(max_length=200, verbose_name="Título")
    message = models.TextField(verbose_name="Mensaje")
    
    # Relación opcional con objetos del sistema
    game = models.ForeignKey(
        'games.Game',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name="Partida relacionada"
    )
    puzzle = models.ForeignKey(
        'training.Puzzle',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
        verbose_name="Problema relacionado"
    )
    
    is_read = models.BooleanField(default=False, verbose_name="Leída")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.get_type_display()} para {self.user.username}: {self.title[:50]}"
