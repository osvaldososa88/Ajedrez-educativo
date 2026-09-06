from django.conf import settings
from django.db import models


class RatingChange(models.Model):
    """
    Immutable log of every rating change produced by a finished competitive game.

    This is the source of truth for:
      - rating history / evolution charts (reconstructable: before -> after -> delta)
      - how many RATED games a player has completed (drives the adaptive K factor)
      - W/D/L statistics and win rate for profiles
      - future leaderboards (filter by game_mode, opponent, date, ...)

    Idempotency: `game` + `player` is unique at the database level, so the same
    finished game can never be applied twice to the same player, even under
    concurrent processing. Rows survive game deletion (SET_NULL) thanks to the
    denormalized opponent/opponent_username/opponent_rating snapshot fields.
    """

    class GameMode(models.TextChoices):
        TOURNAMENT = 'TOURNAMENT', 'Torneo'
        CHALLENGE = 'CHALLENGE', 'Desafío'
        COMPETITIVE = 'COMPETITIVE', 'Competitiva'

    class Result(models.TextChoices):
        WIN = 'WIN', 'Victoria'
        DRAW = 'DRAW', 'Empate'
        LOSS = 'LOSS', 'Derrota'

    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rating_changes',
        verbose_name='Jugador',
    )
    opponent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rating_changes_against',
        verbose_name='Rival',
    )
    # Denormalized snapshot so history remains readable even if users/games are deleted.
    opponent_username = models.CharField(max_length=150, verbose_name='Rival (nombre)')
    opponent_rating = models.IntegerField(verbose_name='ELO del rival')

    game = models.ForeignKey(
        'games.Game',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='rating_changes',
    )
    game_mode = models.CharField(max_length=15, choices=GameMode.choices)

    rating_before = models.IntegerField(verbose_name='ELO anterior')
    rating_after = models.IntegerField(verbose_name='ELO nuevo')
    change = models.IntegerField(verbose_name='Variación')
    result = models.CharField(max_length=5, choices=Result.choices)
    k_factor = models.IntegerField(verbose_name='Factor K aplicado')
    expected_score = models.FloatField(verbose_name='Puntaje esperado')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        unique_together = ('game', 'player')
        verbose_name = 'Cambio de ELO'
        verbose_name_plural = 'Cambios de ELO'

    def __str__(self):
        return (
            f"{self.player.username}: {self.rating_before} → {self.rating_after} "
            f"({self.change:+d}) vs {self.opponent_username}"
        )
