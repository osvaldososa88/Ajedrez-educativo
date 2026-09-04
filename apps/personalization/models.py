from django.db import models
from django.conf import settings
from apps.training.models import Puzzle


class DetectedGameError(models.Model):
    """
    A significant mistake (MISTAKE/BLUNDER per apps.analysis.MoveAnalysis.quality)
    found in a student's own played game, converted into a private training position.

    This is the bridge required by Phase 7: JUGAR -> ANALIZAR -> DETECTAR ERROR ->
    EXTRAER POSICIÓN -> CREAR EJERCICIO -> ENTRENAR. Nothing here duplicates the
    existing analysis pipeline: `move_analysis` is reused as-is (including its
    already-computed `quality` classification) and `generated_puzzle` is a plain
    `training.Puzzle` reusing the entire Phase 3/4 solving/attempt/hint machinery.
    """
    move_analysis = models.OneToOneField(
        'analysis.MoveAnalysis', on_delete=models.CASCADE, related_name='detected_error'
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='detected_errors'
    )
    game = models.ForeignKey(
        'games.Game', on_delete=models.SET_NULL, null=True, blank=True, related_name='detected_errors'
    )

    fen_before = models.CharField(max_length=100)
    student_move_uci = models.CharField(max_length=10)
    student_move_san = models.CharField(max_length=20)
    best_move_uci = models.CharField(max_length=10, blank=True)
    best_move_san = models.CharField(max_length=20, blank=True)

    score_cp_before = models.IntegerField(null=True, blank=True)
    mate_in_before = models.IntegerField(null=True, blank=True)

    # Reuses Puzzle's own taxonomy so a generated error slots into the same
    # categories/themes/difficulties a human-authored puzzle would use.
    category = models.CharField(max_length=20, choices=Puzzle.Category.choices)
    theme = models.CharField(max_length=30, choices=Puzzle.Theme.choices)
    difficulty = models.CharField(max_length=20, choices=Puzzle.Difficulty.choices)

    generated_puzzle = models.OneToOneField(
        Puzzle, on_delete=models.SET_NULL, null=True, blank=True, related_name='source_error'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Error de {self.student.username} ({self.get_category_display()}/{self.get_theme_display()})"


class GlobalChessConfig(models.Model):
    """
    Configuración global administrada por el Administrador de la plataforma.
    Determina las piezas y el tema de tablero por defecto, y si los jugadores
    pueden personalizar su propia apariencia visual.
    """
    default_piece_set = models.CharField(
        max_length=30,
        default='staunton',
        verbose_name="Set de piezas predeterminado"
    )
    default_board_theme = models.CharField(
        max_length=30,
        default='classic',
        verbose_name="Tema de tablero predeterminado"
    )
    allow_player_customization = models.BooleanField(
        default=True,
        verbose_name="Permitir personalización visual a los jugadores"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuración Global de Ajedrez"
        verbose_name_plural = "Configuración Global de Ajedrez"

    def __str__(self):
        return f"Config Global ({self.default_piece_set} / {self.default_board_theme})"

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class UserAppearancePreference(models.Model):
    """
    Preferencias personales de apariencia visual para un jugador.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='appearance_preference',
        verbose_name="Usuario"
    )
    piece_set = models.CharField(
        max_length=30,
        default='staunton',
        verbose_name="Set de piezas"
    )
    board_theme = models.CharField(
        max_length=30,
        default='classic',
        verbose_name="Tema de tablero"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Preferencia Visual de Jugador"
        verbose_name_plural = "Preferencias Visuales de Jugadores"

    def __str__(self):
        return f"Preferencia de {self.user.username} ({self.piece_set} / {self.board_theme})"

