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
    best_move_prob = models.FloatField(
        default=0.75,
        help_text="Probabilidad de jugar el mejor movimiento (0-1)",
        verbose_name="Prob. Mejor Jugada",
    )
    alt_move_prob = models.FloatField(
        default=0.20,
        help_text="Probabilidad de jugar una alternativa cercana 1-50 cp (0-1)",
        verbose_name="Prob. Alternativa",
    )
    minor_error_prob = models.FloatField(
        default=0.04,
        help_text="Probabilidad de cometer un error menor 51-150 cp (0-1)",
        verbose_name="Prob. Error Menor",
    )
    blunder_prob = models.FloatField(
        default=0.01,
        help_text="Probabilidad de cometer un error grave >150 cp acotado por max_cp_loss (0-1)",
        verbose_name="Prob. Error Grave",
    )
    max_cp_loss = models.PositiveIntegerField(
        default=300,
        help_text="Pérdida máxima de centipeones permitida en cualquier error (ej. 300 = 3 peones)",
        verbose_name="Límite Máx. Pérdida Centipeones",
    )
    uci_elo = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Límite UCI_Elo de Stockfish (1320-3190). Vacío = desactivado",
        verbose_name="UCI Elo (opcional)",
    )

    # Visual delay: how long the UI waits before showing the bot's move.
    # This is purely cosmetic — it does NOT affect engine thinking time.
    visual_delay_ms = models.PositiveIntegerField(
        default=800,
        help_text="Delay visual antes de mostrar la jugada del bot (ms). Solo afecta la UX, no el cálculo.",
        verbose_name="Delay visual (ms)",
    )
    animation_speed_ms = models.PositiveIntegerField(
        default=220,
        help_text="Velocidad de la animación de deslizamiento de la pieza (ms). Configurable desde Admin.",
        verbose_name="Velocidad de Animación (ms)",
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
        
        # Validation for probabilities
        total_prob = round(self.best_move_prob + self.alt_move_prob + self.minor_error_prob + self.blunder_prob, 4)
        if not (0.99 <= total_prob <= 1.01):
            raise ValidationError({'best_move_prob': f'La suma de las probabilidades debe ser 1.0 (actual: {total_prob}).'})
        for field, name in [('best_move_prob', 'Prob. Mejor Jugada'), ('alt_move_prob', 'Prob. Alternativa'), ('minor_error_prob', 'Prob. Error Menor'), ('blunder_prob', 'Prob. Error Grave')]:
            val = getattr(self, field, 0)
            if val is None or not (0.0 <= val <= 1.0):
                raise ValidationError({field: f'{name} debe estar entre 0.0 y 1.0.'})


class Opening(models.Model):
    """
    Chess Opening definition (e.g. Sicilian Defense, Ruy Lopez).
    """
    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre de la Apertura")
    eco = models.CharField(max_length=10, blank=True, verbose_name="Código ECO (ej. B20)")
    description = models.TextField(blank=True, verbose_name="Descripción educativa")
    initial_fen = models.CharField(
        max_length=100,
        default="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        verbose_name="Posición FEN Inicial"
    )
    is_active = models.BooleanField(default=True, verbose_name="Activa")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Apertura"
        verbose_name_plural = "Aperturas"

    def __str__(self):
        return f"{self.name} ({self.eco})" if self.eco else self.name

    def clean(self):
        from django.core.exceptions import ValidationError
        import chess
        try:
            b = chess.Board(self.initial_fen)
            if not b.is_valid():
                raise ValidationError({'initial_fen': 'El FEN no es una posición válida.'})
        except ValueError:
            raise ValidationError({'initial_fen': 'Formato FEN inválido.'})


class OpeningLine(models.Model):
    """
    A specific variation / line of an opening.
    """
    class BotColor(models.TextChoices):
        ANY = 'ANY', 'Cualquier Color'
        WHITE = 'WHITE', 'Blancas'
        BLACK = 'BLACK', 'Negras'

    opening = models.ForeignKey(Opening, on_delete=models.CASCADE, related_name='lines', verbose_name="Apertura")
    name = models.CharField(max_length=100, verbose_name="Nombre de la línea / Variante")
    moves_san = models.TextField(help_text="Secuencia en notación SAN (ej. 1.e4 c5 2.Nf3 d6 3.d4 cxd4)", verbose_name="Movimientos (SAN)")
    moves_uci = models.JSONField(default=list, help_text="Lista de movimientos UCI (ej. [\"e2e4\", \"c7c5\", \"g1f3\"])", verbose_name="Movimientos (UCI)")
    bot_color = models.CharField(max_length=10, choices=BotColor.choices, default=BotColor.ANY, verbose_name="Color asignado al Bot")
    priority = models.IntegerField(default=1, verbose_name="Prioridad")
    is_active = models.BooleanField(default=True, verbose_name="Activa")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['opening', '-priority', 'id']
        verbose_name = "Línea de Apertura"
        verbose_name_plural = "Líneas de Apertura"

    def __str__(self):
        return f"{self.opening.name} - {self.name}"

    def clean(self):
        from django.core.exceptions import ValidationError
        import chess
        if not self.moves_uci or not isinstance(self.moves_uci, list):
            raise ValidationError({'moves_uci': 'Debe ser una lista de jugadas UCI no vacía.'})

        board = chess.Board(self.opening.initial_fen)
        for idx, uci in enumerate(self.moves_uci):
            try:
                move = chess.Move.from_uci(uci)
            except ValueError:
                raise ValidationError({'moves_uci': f"Jugada #{idx+1} ('{uci}') formato UCI inválido."})
            if move not in board.legal_moves:
                raise ValidationError({'moves_uci': f"Jugada #{idx+1} ('{uci}') es ilegal en la secuencia."})
            board.push(move)


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

    class OpeningMode(models.TextChoices):
        PURE_STOCKFISH = 'PURE_STOCKFISH', 'Stockfish Puro'
        SPECIFIC_OPENING = 'SPECIFIC_OPENING', 'Apertura Determinada'
        REPERTOIRE = 'REPERTOIRE', 'Repertorio'

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

    opening_mode = models.CharField(
        max_length=20,
        choices=OpeningMode.choices,
        default=OpeningMode.PURE_STOCKFISH,
        verbose_name="Modo de Apertura",
    )
    specific_opening_white = models.ForeignKey(
        Opening,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bots_specific_white',
        verbose_name="Apertura con Blancas",
    )
    specific_opening_black = models.ForeignKey(
        Opening,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bots_specific_black',
        verbose_name="Apertura con Negras",
    )
    repertoire_openings = models.ManyToManyField(
        Opening,
        blank=True,
        related_name='bots_repertoire',
        verbose_name="Repertorio de Aperturas",
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

    def update_profile_from_elo(self):
        """Sincroniza dinámicamente los parámetros de Stockfish del BotProfile según el ELO mostrado del Bot."""
        if not self.profile_id:
            return

        elo = self.displayed_elo
        prof = self.profile

        if elo < 400:
            prof.skill_level = 0
            prof.engine_depth = 1
            prof.best_move_prob = 0.20
            prof.alt_move_prob = 0.30
            prof.minor_error_prob = 0.30
            prof.blunder_prob = 0.20
            prof.max_cp_loss = 600
        elif elo < 700:
            prof.skill_level = 2
            prof.engine_depth = 2
            prof.best_move_prob = 0.35
            prof.alt_move_prob = 0.35
            prof.minor_error_prob = 0.20
            prof.blunder_prob = 0.10
            prof.max_cp_loss = 400
        elif elo < 1000:
            prof.skill_level = 5
            prof.engine_depth = 3
            prof.best_move_prob = 0.50
            prof.alt_move_prob = 0.30
            prof.minor_error_prob = 0.15
            prof.blunder_prob = 0.05
            prof.max_cp_loss = 300
        elif elo < 1300:
            prof.skill_level = 8
            prof.engine_depth = 5
            prof.best_move_prob = 0.65
            prof.alt_move_prob = 0.25
            prof.minor_error_prob = 0.08
            prof.blunder_prob = 0.02
            prof.max_cp_loss = 200
        elif elo < 1600:
            prof.skill_level = 12
            prof.engine_depth = 8
            prof.best_move_prob = 0.80
            prof.alt_move_prob = 0.15
            prof.minor_error_prob = 0.04
            prof.blunder_prob = 0.01
            prof.max_cp_loss = 150
        elif elo < 1900:
            prof.skill_level = 16
            prof.engine_depth = 12
            prof.best_move_prob = 0.90
            prof.alt_move_prob = 0.08
            prof.minor_error_prob = 0.02
            prof.blunder_prob = 0.00
            prof.max_cp_loss = 80
        elif elo < 2200:
            prof.skill_level = 20
            prof.engine_depth = 16
            prof.best_move_prob = 0.97
            prof.alt_move_prob = 0.03
            prof.minor_error_prob = 0.00
            prof.blunder_prob = 0.00
            prof.max_cp_loss = 40
        else: # 2200+
            prof.skill_level = 20
            prof.engine_depth = 20
            prof.best_move_prob = 1.00
            prof.alt_move_prob = 0.00
            prof.minor_error_prob = 0.00
            prof.blunder_prob = 0.00
            prof.max_cp_loss = 0

        prof.save()

    @property
    def category_color(self):
        return {
            self.Category.BEGINNER: '#10b981',
            self.Category.INTERMEDIATE: '#f59e0b',
            self.Category.ADVANCED: '#ef4444',
        }.get(self.category, '#64748b')

    def get_openings_summary(self):
        """Devuelve las aperturas de Blancas y Negras configuradas para el bot."""
        from .models import OpeningLine
        white_lines = []
        black_lines = []

        if self.specific_opening_white and self.specific_opening_white.is_active:
            lines = list(self.specific_opening_white.lines.filter(is_active=True))
            if lines:
                for line in lines:
                    white_lines.append(f"{self.specific_opening_white.name}: {line.name} ({line.moves_san})" if line.moves_san else f"{self.specific_opening_white.name}: {line.name}")
            else:
                white_lines.append(self.specific_opening_white.name)

        if self.specific_opening_black and self.specific_opening_black.is_active:
            lines = list(self.specific_opening_black.lines.filter(is_active=True))
            if lines:
                for line in lines:
                    black_lines.append(f"{self.specific_opening_black.name}: {line.name} ({line.moves_san})" if line.moves_san else f"{self.specific_opening_black.name}: {line.name}")
            else:
                black_lines.append(self.specific_opening_black.name)

        if self.opening_mode == self.OpeningMode.REPERTOIRE or (not white_lines and not black_lines):
            for op in self.repertoire_openings.filter(is_active=True):
                for line in op.lines.filter(is_active=True):
                    info = f"{op.name}: {line.name}" if line.name and line.name != op.name else op.name
                    if line.moves_san:
                        info += f" ({line.moves_san})"
                    if line.bot_color in [OpeningLine.BotColor.WHITE, OpeningLine.BotColor.ANY] and info not in white_lines:
                        white_lines.append(info)
                    if line.bot_color in [OpeningLine.BotColor.BLACK, OpeningLine.BotColor.ANY] and info not in black_lines:
                        black_lines.append(info)

        return {
            'white': ' / '.join(white_lines) if white_lines else 'Stockfish adaptativo (Control del centro)',
            'black': ' / '.join(black_lines) if black_lines else 'Stockfish adaptativo (Estructura sólida)',
        }

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.profile_id:
            try:
                self.update_profile_from_elo()
            except Exception:
                pass
        # Keep the linked account's rating in sync with the difficulty label so
        # any generic ELO display matches the bot card. It is never changed by
        # playing games (RatingService skips bot games).
        if hasattr(self, 'user') and self.user and self.user.elo_rating != self.displayed_elo:
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

