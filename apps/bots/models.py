from django.conf import settings
from django.db import models


class BotProfile(models.Model):
    """
    Strength / personality configuration shared by many bots.

    Separates WHO the bot is (see `Bot`) from HOW it plays. The real playing
    strength comes from these engine parameters; `Bot.displayed_elo` is only a
    human-friendly difficulty label.

    Weakness strategy (educational, never absurd moves):
      * `skill_level`   -> Stockfish "Skill Level" (0-20): native human-like play.
      * `engine_depth`  -> search depth cap: lower = weaker but sane.
      * `move_time_ms`  -> wall clock cap per move.
      * `multipv`       -> number of reasonable candidate moves considered.
      * `error_probability` -> chance of playing one of the runner-up candidates
        (top MultiPV lines) instead of the best one. Runner-ups are still
        reasonable moves, so mistakes look human, not random.
      * `uci_elo`       -> optional Stockfish UCI_Elo limit (1320-3190) for
        future EXPERTO bots; None = disabled.
    """

    name = models.CharField(max_length=80, unique=True, verbose_name="Nombre del perfil")
    description = models.TextField(blank=True, verbose_name="Descripción")

    engine_depth = models.PositiveIntegerField(default=6, verbose_name="Profundidad máx.")
    move_time_ms = models.PositiveIntegerField(default=600, verbose_name="Tiempo por jugada (ms)")
    skill_level = models.PositiveSmallIntegerField(
        default=5, help_text="Stockfish Skill Level 0-20", verbose_name="Skill Level"
    )
    multipv = models.PositiveSmallIntegerField(
        default=3, help_text="Candidatos razonables considerados (MultiPV)",
        verbose_name="MultiPV",
    )
    error_probability = models.FloatField(
        default=0.20,
        help_text="Probabilidad de jugar un candidato secundario en vez del mejor (0-1)",
        verbose_name="Probabilidad de error",
    )
    uci_elo = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Límite UCI_Elo de Stockfish (1320-3190). Vacío = desactivado",
        verbose_name="UCI Elo (opcional)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Perfil de Bot'
        verbose_name_plural = 'Perfiles de Bot'

    def __str__(self):
        return self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        super().clean()
        if not (0 <= self.skill_level <= 20):
            raise ValidationError({'skill_level': 'Skill Level debe estar entre 0 y 20.'})
        if not (0.0 <= self.error_probability <= 1.0):
            raise ValidationError({'error_probability': 'Debe estar entre 0 y 1.'})
        if self.multipv < 1:
            raise ValidationError({'multipv': 'MultiPV debe ser al menos 1.'})
        if self.uci_elo is not None and not (1320 <= self.uci_elo <= 3190):
            raise ValidationError({'uci_elo': 'UCI Elo de Stockfish admite 1320-3190 (o vacío).'})


class Bot(models.Model):
    """
    A training opponent. Identity (this row + its linked user account) is fully
    independent from the shown name, so the same name can exist in several
    categories ("Mateo" as beginner, intermediate and advanced are different
    bots). Names, nicknames, ELO label, order, etc. are all editable from
    Django Admin without touching code.
    """

    class Category(models.TextChoices):
        BEGINNER = 'BEGINNER', 'Principiante'
        INTERMEDIATE = 'INTERMEDIATE', 'Intermedio'
        ADVANCED = 'ADVANCED', 'Avanzado'
        # Futuro: EXPERTO, bots especiales, bots de profesores, eventos...

    class Meta:
        ordering = ['category', 'order', 'pk']
        unique_together = ('category', 'order')
        verbose_name = 'Bot'
        verbose_name_plural = 'Bots'

    # Internal identity: a real (non-loginable) user account so bot games are
    # regular games.Game instances usable by analysis/puzzles/history systems.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bot_profile',
        verbose_name="Cuenta de usuario interna",
    )

    display_name = models.CharField(max_length=60, verbose_name="Nombre mostrado")
    nickname = models.CharField(max_length=60, blank=True, verbose_name="Apodo")
    avatar = models.CharField(
        max_length=16, blank=True, default='🤖',
        help_text="Emoji/avatar de la primera versión (opcional)",
        verbose_name="Avatar",
    )
    description = models.TextField(blank=True, verbose_name="Descripción")
    quote = models.CharField(max_length=200, blank=True, verbose_name="Frase")

    category = models.CharField(max_length=15, choices=Category.choices, verbose_name="Categoría")
    order = models.PositiveIntegerField(
        help_text="Posición dentro de su categoría (1 = primer rival). Define la progresión.",
        verbose_name="Orden",
    )
    displayed_elo = models.PositiveIntegerField(
        help_text="ELO mostrado: etiqueta de dificultad, NUNCA se modifica por partidas.",
        verbose_name="ELO mostrado",
    )

    profile = models.ForeignKey(
        BotProfile, on_delete=models.PROTECT, related_name='bots', verbose_name="Perfil de fuerza",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Los bots inactivos no son seleccionables; la progresión salta al siguiente bot activo.",
        verbose_name="Activo",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.display_name} ({self.get_category_display()} · {self.displayed_elo})"

    @property
    def category_color(self):
        return {
            self.Category.BEGINNER: '#10b981',
            self.Category.INTERMEDIATE: '#f59e0b',
            self.Category.ADVANCED: '#ef4444',
        }.get(self.category, '#64748b')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Keep the linked account's rating in sync with the difficulty label so
        # any generic ELO display matches the bot card. It is never changed by
        # playing games (RatingService skips bot games).
        if self.user.elo_rating != self.displayed_elo:
            self.user.elo_rating = self.displayed_elo
            self.user.save(update_fields=['elo_rating'])

    @classmethod
    def create_bot_account(cls, display_name):
        """Create the internal, non-loginable user account for a bot."""
        from django.utils.crypto import get_random_string
        from django.contrib.auth import get_user_model
        User = get_user_model()
        username = f"bot_{get_random_string(12).lower()}"
        while User.objects.filter(username=username).exists():
            username = f"bot_{get_random_string(12).lower()}"
        return User.objects.create_user(
            username=username,
            password=None,  # unusable password: bots never log in
            role=User.Role.BOT,
        )


class BotProgress(models.Model):
    """
    Per-student progression state for one bot. Rows are created lazily:
    the first ACTIVE bot of each category is always unlocked (derived, no row
    needed); further rows appear when a bot is unlocked by defeating the
    previous one, or defeated. This keeps the table small while remaining
    fully per-student.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bot_progress',
    )
    bot = models.ForeignKey(Bot, on_delete=models.CASCADE, related_name='progress_entries')

    unlocked = models.BooleanField(default=False)
    defeated = models.BooleanField(default=False)
    defeated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'bot')
        ordering = ['user_id', 'bot__category', 'bot__order']
        verbose_name = 'Progreso de Bot'
        verbose_name_plural = 'Progresos de Bot'

    def __str__(self):
        flags = []
        if self.unlocked:
            flags.append('desbloqueado')
        if self.defeated:
            flags.append('derrotado')
        return f"{self.user.username} → {self.bot.display_name} [{', '.join(flags) or 'sin progreso'}]"

