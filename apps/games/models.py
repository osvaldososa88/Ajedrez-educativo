import uuid
import chess
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.core.chess_engine import ChessEngine

class Game(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = 'IN_PROGRESS', 'En juego'
        FINISHED = 'FINISHED', 'Finalizada'
        ABANDONED = 'ABANDONED', 'Abandonada'

    class Winner(models.TextChoices):
        WHITE = 'WHITE', 'Blancas'
        BLACK = 'BLACK', 'Negras'
        DRAW = 'DRAW', 'Tablas'

    class FinishReason(models.TextChoices):
        CHECKMATE = 'CHECKMATE', 'Jaque Mate'
        STALEMATE = 'STALEMATE', 'Tablas por Ahogado'
        TIMEOUT = 'TIMEOUT', 'Tiempo Agotado'
        RESIGNATION = 'RESIGNATION', 'Abandono'
        AGREEMENT = 'AGREEMENT', 'Mutuo Acuerdo'
        DRAW_RULES = 'DRAW_RULES', 'Tablas por Regla (50 jugadas/Repetición/Insuficiencia)'
        INSUFFICIENT_MATERIAL = 'INSUFFICIENT_MATERIAL', 'Material Insuficiente'
        REPETITION = 'REPETITION', 'Repetición de Posición'

    class Turn(models.TextChoices):
        WHITE = 'WHITE', 'Blancas'
        BLACK = 'BLACK', 'Negras'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    white_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='games_as_white'
    )
    black_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='games_as_black'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS
    )
    winner = models.CharField(
        max_length=10,
        choices=Winner.choices,
        null=True,
        blank=True
    )
    finish_reason = models.CharField(
        max_length=30,
        choices=FinishReason.choices,
        null=True,
        blank=True
    )
    fen_current = models.CharField(
        max_length=100,
        default=chess.STARTING_FEN
    )
    pgn_history = models.TextField(blank=True, default='')

    time_control_minutes = models.IntegerField(default=10)
    time_control_increment = models.IntegerField(default=0)

    white_time_left_ms = models.IntegerField(default=600000) # 10 mins in ms
    black_time_left_ms = models.IntegerField(default=600000)

    last_move_at = models.DateTimeField(default=timezone.now)
    turn = models.CharField(
        max_length=5,
        choices=Turn.choices,
        default=Turn.WHITE
    )
    is_competitive = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Partida {self.id.hex[:8]} - {self.white_player.username} vs {self.black_player.username}"

    def update_clocks(self):
        """
        Deducts elapsed time since `last_move_at` from the active player's clock.
        If time expires, finishes the game.
        """
        if self.status != self.Status.IN_PROGRESS:
            return

        now = timezone.now()
        elapsed_ms = int((now - self.last_move_at).total_seconds() * 1000)

        if self.turn == self.Turn.WHITE:
            self.white_time_left_ms = max(0, self.white_time_left_ms - elapsed_ms)
            if self.white_time_left_ms <= 0:
                self.status = self.Status.FINISHED
                self.winner = self.Winner.BLACK
                self.finish_reason = self.FinishReason.TIMEOUT
        else:
            self.black_time_left_ms = max(0, self.black_time_left_ms - elapsed_ms)
            if self.black_time_left_ms <= 0:
                self.status = self.Status.FINISHED
                self.winner = self.Winner.WHITE
                self.finish_reason = self.FinishReason.TIMEOUT

        self.last_move_at = now

    def generate_pgn(self) -> str:
        moves = list(self.moves.order_by('ply').values_list('uci', flat=True))
        result_str = "*"
        if self.winner == self.Winner.WHITE:
            result_str = "1-0"
        elif self.winner == self.Winner.BLACK:
            result_str = "0-1"
        elif self.winner == self.Winner.DRAW:
            result_str = "1/2-1/2"

        return ChessEngine.generate_pgn(
            white_name=self.white_player.username,
            black_name=self.black_player.username,
            uci_moves=moves,
            result=result_str,
            date_str=self.created_at.strftime("%Y.%m.%d")
        )

class Challenge(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        ACCEPTED = 'ACCEPTED', 'Aceptado'
        DECLINED = 'DECLINED', 'Rechazado'
        CANCELLED = 'CANCELLED', 'Cancelado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_challenges'
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_challenges'
    )
    time_control_minutes = models.IntegerField(default=10)
    time_control_increment = models.IntegerField(default=0)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING
    )
    game = models.OneToOneField(
        Game,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='originating_challenge'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Desafío de {self.sender.username} a {self.receiver.username} ({self.get_status_display()})"

class Move(models.Model):
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='moves')
    ply = models.PositiveIntegerField()
    player = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    uci = models.CharField(max_length=10)
    san = models.CharField(max_length=15)
    fen_after = models.CharField(max_length=100)
    time_spent_ms = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['ply']

    def __str__(self):
        return f"Ply {self.ply}: {self.san} por {self.player.username}"
