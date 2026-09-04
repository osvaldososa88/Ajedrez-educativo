import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.utils import timezone


class Tournament(models.Model):
    """
    A school tournament. The pairing algorithm is selected via `format` and resolved
    at runtime through `apps.tournaments.pairing.get_pairing_service`, so new formats
    can be added later without changing this model.
    """
    class Format(models.TextChoices):
        ROUND_ROBIN = 'ROUND_ROBIN', 'Todos contra Todos'
        SWISS = 'SWISS', 'Sistema Suizo'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Borrador'
        REGISTRATION_OPEN = 'REGISTRATION_OPEN', 'Inscripción Abierta'
        IN_PROGRESS = 'IN_PROGRESS', 'En Curso'
        COMPLETED = 'COMPLETED', 'Finalizado'
        CANCELLED = 'CANCELLED', 'Cancelado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, verbose_name="Nombre del Torneo")
    description = models.TextField(blank=True, verbose_name="Descripción")

    organizers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='organized_tournaments', blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_tournaments'
    )

    format = models.CharField(max_length=20, choices=Format.choices, default=Format.ROUND_ROBIN)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    start_date = models.DateTimeField(default=timezone.now, verbose_name="Fecha")

    # For Swiss, the organizer decides the number of rounds; for Round Robin it is
    # computed automatically from the participant count once the tournament starts.
    rounds_total = models.PositiveIntegerField(null=True, blank=True, verbose_name="Cantidad de Rondas")

    time_control_minutes = models.IntegerField(default=15)
    time_control_increment = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return f"{self.name} ({self.get_format_display()})"

    def is_organizer(self, user):
        return bool(user and user.is_authenticated and (user.is_staff or self.organizers.filter(id=user.id).exists()))

    @property
    def active_participants(self):
        return self.participants.filter(status=TournamentParticipant.Status.REGISTERED)

    @property
    def current_round(self):
        return self.rounds.order_by('-number').first()


class TournamentParticipant(models.Model):
    """
    A player's registration in a tournament. `seed_rating` snapshots the user's ELO
    at registration time so later rating changes don't retroactively alter seeding.
    """
    class Status(models.TextChoices):
        REGISTERED = 'REGISTERED', 'Inscrito'
        WITHDRAWN = 'WITHDRAWN', 'Retirado'
        DISQUALIFIED = 'DISQUALIFIED', 'Descalificado'

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tournament_entries')
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.REGISTERED)
    seed_rating = models.IntegerField(default=1200)
    had_bye = models.BooleanField(default=False, verbose_name="Ya recibió un bye")
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-seed_rating', 'user__username']
        unique_together = ['tournament', 'user']

    def __str__(self):
        return f"{self.user.username} en {self.tournament.name}"


class Round(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        IN_PROGRESS = 'IN_PROGRESS', 'En Curso'
        COMPLETED = 'COMPLETED', 'Cerrada'

    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='rounds')
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    started_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['number']
        unique_together = ['tournament', 'number']

    def __str__(self):
        return f"Ronda {self.number} - {self.tournament.name}"


class Pairing(models.Model):
    """
    One board's match-up within a round. `game` links to the existing `games.Game`
    model so a tournament game is played through the same board/consumer/rules as
    any other game — nothing about Game itself is modified.
    """
    class Result(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        WHITE_WIN = 'WHITE_WIN', 'Ganan Blancas'
        BLACK_WIN = 'BLACK_WIN', 'Ganan Negras'
        DRAW = 'DRAW', 'Tablas'
        DOUBLE_FORFEIT = 'DOUBLE_FORFEIT', 'Doble Ausencia'
        BYE = 'BYE', 'Bye (Descanso)'

    round = models.ForeignKey(Round, on_delete=models.CASCADE, related_name='pairings')
    board_number = models.PositiveIntegerField()

    white_player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tournament_pairings_as_white'
    )
    black_player = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tournament_pairings_as_black'
    )

    game = models.OneToOneField(
        'games.Game', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tournament_pairing'
    )

    result = models.CharField(max_length=20, choices=Result.choices, default=Result.PENDING)
    is_bye = models.BooleanField(default=False)
    white_absent = models.BooleanField(default=False, verbose_name="Ausencia de Blancas")
    black_absent = models.BooleanField(default=False, verbose_name="Ausencia de Negras")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['board_number']

    def __str__(self):
        if self.is_bye:
            return f"Bye: {self.white_player.username if self.white_player else '?'}"
        black_name = self.black_player.username if self.black_player else '?'
        white_name = self.white_player.username if self.white_player else '?'
        return f"Tablero {self.board_number}: {white_name} vs {black_name}"

    def clean(self):
        super().clean()
        if not self.is_bye and (self.white_player_id is None or self.black_player_id is None):
            raise ValidationError("Un emparejamiento normal requiere jugador de blancas y de negras.")
        if self.is_bye and self.black_player_id is not None:
            raise ValidationError("Un bye no puede tener jugador de negras.")

    @property
    def is_decided(self):
        return self.result != self.Result.PENDING

    def points_for(self, user_id):
        """Points awarded to `user_id` from this pairing's recorded result, or None if undecided."""
        if self.result == self.Result.PENDING:
            return None
        if self.is_bye:
            return 1.0 if self.white_player_id == user_id else None
        if self.result == self.Result.DRAW:
            return 0.5
        if self.result == self.Result.WHITE_WIN:
            return 1.0 if self.white_player_id == user_id else 0.0
        if self.result == self.Result.BLACK_WIN:
            return 1.0 if self.black_player_id == user_id else 0.0
        if self.result == self.Result.DOUBLE_FORFEIT:
            return 0.0
        return None

    def opponent_of(self, user_id):
        if self.is_bye:
            return None
        if self.white_player_id == user_id:
            return self.black_player_id
        if self.black_player_id == user_id:
            return self.white_player_id
        return None
