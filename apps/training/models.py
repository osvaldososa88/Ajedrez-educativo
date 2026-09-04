import uuid
import chess
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings

class Puzzle(models.Model):
    """
    Chess exercise / puzzle model covering Tactics, Endgames, Strategy, Openings, etc.
    """
    class Category(models.TextChoices):
        TACTICS = 'TACTICS', 'Táctica'
        CALCULATION = 'CALCULATION', 'Cálculo'
        STRATEGY = 'STRATEGY', 'Estrategia'
        OPENINGS = 'OPENINGS', 'Aperturas'
        MIDDLEGAME = 'MIDDLEGAME', 'Medio Juego'
        ENDGAME = 'ENDGAME', 'Finales'
        DEFENSE = 'DEFENSE', 'Defensa'
        ATTACK = 'ATTACK', 'Ataque'

    class Theme(models.TextChoices):
        FORK = 'FORK', 'Doble / Horquilla'
        PIN = 'PIN', 'Clavada'
        SKEWER = 'SKEWER', 'Ataque a la Descubierta / Enfilada'
        MATE = 'MATE', 'Jaque Mate'
        OPPOSITION = 'OPPOSITION', 'Oposición'
        PAWN_ENDGAME = 'PAWN_ENDGAME', 'Final de Peones'
        ROOK_ENDGAME = 'ROOK_ENDGAME', 'Final de Torres'
        MINOR_PIECES_ENDGAME = 'MINOR_PIECES_ENDGAME', 'Final de Piezas Menores'
        OPENING_REPERTOIRE = 'OPENING_REPERTOIRE', 'Repertorio de Apertura'
        DEFENSIVE_RESOURCE = 'DEFENSIVE_RESOURCE', 'Recurso Defensivo'
        BEST_CONTINUATION = 'BEST_CONTINUATION', 'Mejor Continuación'
        POSITION_RECOGNITION = 'POSITION_RECOGNITION', 'Reconocimiento Posicional'

    class Difficulty(models.TextChoices):
        BEGINNER = 'BEGINNER', 'Principiante (1000)'
        INTERMEDIATE = 'INTERMEDIATE', 'Intermedio (1400)'
        ADVANCED = 'ADVANCED', 'Avanzado (1800)'
        MASTER = 'MASTER', 'Maestro (2200+)'

    class Objective(models.TextChoices):
        FIND_MOVE = 'FIND_MOVE', 'Encontrar una Jugada'
        FIND_SEQUENCE = 'FIND_SEQUENCE', 'Encontrar una Secuencia'
        WIN = 'WIN', 'Ganar la Posición'
        DRAW = 'DRAW', 'Conseguir Tablas'
        DEFEND = 'DEFEND', 'Defender la Posición'
        BEST_CONTINUATION = 'BEST_CONTINUATION', 'Encontrar la Mejor Continuación'
        RECOGNIZE_IDEA = 'RECOGNIZE_IDEA', 'Reconocer una Idea'
        PRACTICE_OPENING = 'PRACTICE_OPENING', 'Practicar una Apertura'
        PRACTICE_ENDGAME = 'PRACTICE_ENDGAME', 'Practicar un Final'

    class SideToMove(models.TextChoices):
        WHITE = 'WHITE', 'Blancas'
        BLACK = 'BLACK', 'Negras'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Borrador'
        IN_REVIEW = 'IN_REVIEW', 'En Revisión'
        PUBLISHED = 'PUBLISHED', 'Publicado'
        REJECTED = 'REJECTED', 'Rechazado'
        ARCHIVED = 'ARCHIVED', 'Archivado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200, verbose_name="Título")
    description = models.TextField(blank=True, verbose_name="Descripción / Instrucción")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    initial_fen = models.CharField(max_length=100, default=chess.STARTING_FEN, verbose_name="FEN Inicial")
    side_to_move = models.CharField(max_length=10, choices=SideToMove.choices, default=SideToMove.WHITE)

    category = models.CharField(max_length=20, choices=Category.choices, default=Category.TACTICS)
    theme = models.CharField(max_length=30, choices=Theme.choices, default=Theme.FORK)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.BEGINNER)
    objective = models.CharField(max_length=30, choices=Objective.choices, default=Objective.WIN)

    # Solution moves sequence stored as JSON list of UCI strings e.g. ["e2e4", "e7e5", "g1f3"]
    # blank=True: a puzzle may be saved as DRAFT while still being authored, before a solution exists.
    # PuzzleValidationService enforces a non-empty solution before it can be submitted for review.
    solution_moves = models.JSONField(default=list, blank=True, verbose_name="Secuencia Solución (UCI)")
    variations_json = models.JSONField(default=dict, blank=True, verbose_name="Variantes Aceptadas")
    hints = models.JSONField(default=list, blank=True, verbose_name="Pistas de Ayuda")

    status = models.CharField(max_length=15, choices=Status.choices, default=Status.DRAFT)

    # Moderation metadata
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='moderated_puzzles', verbose_name="Moderado por"
    )
    moderation_notes = models.TextField(blank=True, verbose_name="Notas de Moderación / Motivo de Rechazo")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        try:
            board = chess.Board(self.initial_fen)
        except ValueError as exc:
            raise ValidationError({'initial_fen': f'FEN inválido: {exc}'}) from exc

        if not board.is_valid():
            raise ValidationError({'initial_fen': 'La posición FEN no es una posición de ajedrez válida.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.get_category_display()} - {self.get_difficulty_display()})"

    @staticmethod
    def _is_moderator(user):
        return bool(user and user.is_authenticated and (user.is_staff or getattr(user, 'role', None) in ['TEACHER', 'ADMIN']))

    def is_author(self, user):
        return bool(user and user.is_authenticated and self.author_id == user.id)

    def can_edit(self, user):
        """Moderators can always edit. Authors may only edit while the puzzle has not been decided on."""
        if self._is_moderator(user):
            return True
        return self.is_author(user) and self.status in [self.Status.DRAFT, self.Status.REJECTED]

    def can_delete(self, user):
        if self._is_moderator(user):
            return True
        return self.is_author(user) and self.status in [self.Status.DRAFT, self.Status.REJECTED]

    def can_submit_for_review(self, user):
        return self.is_author(user) and self.status in [self.Status.DRAFT, self.Status.REJECTED]

    @property
    def average_rating(self):
        agg = self.ratings.aggregate(avg=models.Avg('value'))
        return round(agg['avg'], 2) if agg['avg'] is not None else None

    @property
    def ratings_count(self):
        return self.ratings.count()


class PuzzleAttempt(models.Model):
    """
    Log of student attempts on a puzzle.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='puzzle_attempts')
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name='attempts')

    solved = models.BooleanField(default=False)
    attempts_count = models.PositiveIntegerField(default=1)
    hints_used = models.PositiveIntegerField(default=0)
    time_taken_seconds = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        status = "Resuelto" if self.solved else "Fallido"
        return f"{self.user.username} - {self.puzzle.title} [{status}]"


class UserTrainingStats(models.Model):
    """
    Adaptive performance stats per user, category, and theme.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='training_stats')
    category = models.CharField(max_length=20, choices=Puzzle.Category.choices)
    theme = models.CharField(max_length=30, choices=Puzzle.Theme.choices)

    total_attempts = models.PositiveIntegerField(default=0)
    successful_attempts = models.PositiveIntegerField(default=0)
    total_time_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ['user', 'category', 'theme']

    @property
    def success_rate(self):
        if self.total_attempts == 0:
            return 0.0
        return round((self.successful_attempts / self.total_attempts) * 100, 1)


class PuzzleFavorite(models.Model):
    """
    A student/teacher bookmarking a peer's (or their own) puzzle for later practice.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_puzzles')
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'puzzle']

    def __str__(self):
        return f"{self.user.username} ♥ {self.puzzle.title}"


class PuzzleRating(models.Model):
    """
    Simple 1-5 star educational-value rating a user gives to a puzzle after solving it.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='puzzle_ratings')
    puzzle = models.ForeignKey(Puzzle, on_delete=models.CASCADE, related_name='ratings')
    value = models.PositiveSmallIntegerField(verbose_name="Valoración (1-5)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'puzzle']

    def clean(self):
        super().clean()
        if not (1 <= self.value <= 5):
            raise ValidationError({'value': 'La valoración debe estar entre 1 y 5.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} -> {self.puzzle.title}: {self.value}★"
