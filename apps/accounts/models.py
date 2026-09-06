from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'ADMIN', 'Administrador'
        TEACHER = 'TEACHER', 'Docente'
        STUDENT = 'STUDENT', 'Estudiante'

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STUDENT,
        verbose_name="Rol de usuario"
    )
    elo_rating = models.IntegerField(default=1200, verbose_name="Puntuación ELO")
    bio = models.TextField(blank=True, verbose_name="Biografía")

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def rank(self):
        """
        Friendly rank derived from the current ELO (never stored: the ELO is the
        single source of truth). Crossing a rating boundary updates it instantly.
        """
        from apps.ratings.elo import rank_for_elo
        return rank_for_elo(self.elo_rating)

