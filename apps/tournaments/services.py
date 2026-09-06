import chess
from django.db import transaction
from django.utils import timezone
from apps.accounts.models import CustomUser
from apps.games.models import Game
from apps.ratings.services import RatingService
from .models import Tournament, TournamentParticipant, Round, Pairing

from .pairing import get_pairing_service
from .standings import StandingsService


class TournamentError(Exception):
    """Raised for invalid tournament lifecycle operations or permission issues."""


class TournamentService:
    # --- Registration ---

    @staticmethod
    def register(tournament: Tournament, user) -> TournamentParticipant:
        if tournament.status not in [Tournament.Status.DRAFT, Tournament.Status.REGISTRATION_OPEN]:
            raise TournamentError("Las inscripciones para este torneo ya están cerradas.")

        existing = TournamentParticipant.objects.filter(tournament=tournament, user=user).first()
        if existing:
            if existing.status == TournamentParticipant.Status.WITHDRAWN:
                existing.status = TournamentParticipant.Status.REGISTERED
                existing.save(update_fields=['status'])
                return existing
            raise TournamentError("Ya estás inscrito en este torneo.")

        return TournamentParticipant.objects.create(
            tournament=tournament, user=user, seed_rating=user.elo_rating
        )

    @staticmethod
    def withdraw(tournament: Tournament, user) -> TournamentParticipant:
        participant = TournamentParticipant.objects.filter(tournament=tournament, user=user).first()
        if not participant:
            raise TournamentError("No estás inscrito en este torneo.")
        if tournament.status == Tournament.Status.IN_PROGRESS:
            raise TournamentError("No puedes retirarte mientras el torneo está en curso; contacta al organizador.")
        participant.status = TournamentParticipant.Status.WITHDRAWN
        participant.save(update_fields=['status'])
        return participant

    # --- Lifecycle ---

    @staticmethod
    @transaction.atomic
    def start_tournament(tournament: Tournament) -> Tournament:
        if tournament.status not in [Tournament.Status.DRAFT, Tournament.Status.REGISTRATION_OPEN]:
            raise TournamentError("El torneo ya fue iniciado.")

        participants = list(tournament.active_participants)
        if len(participants) < 2:
            raise TournamentError("Se necesitan al menos 2 participantes inscritos para iniciar el torneo.")

        pairing_service = get_pairing_service(tournament)

        if pairing_service.supports_all_rounds_upfront:
            schedule = pairing_service.generate_schedule(participants)
            tournament.rounds_total = len(schedule)
            tournament.status = Tournament.Status.IN_PROGRESS
            tournament.save(update_fields=['rounds_total', 'status'])
            for round_number, round_pairings in enumerate(schedule, start=1):
                round_obj = Round.objects.create(tournament=tournament, number=round_number)
                TournamentService._persist_pairings(round_obj, round_pairings)
            TournamentService.open_round(tournament.rounds.get(number=1))
        else:
            if not tournament.rounds_total:
                raise TournamentError("Debes indicar la cantidad de rondas para un torneo suizo antes de iniciarlo.")
            tournament.status = Tournament.Status.IN_PROGRESS
            tournament.save(update_fields=['status'])
            TournamentService.generate_next_round(tournament)

        return tournament

    @staticmethod
    def _persist_pairings(round_obj: Round, round_pairings: list):
        for board_number, (white, black) in enumerate(round_pairings, start=1):
            is_bye = black is None
            pairing = Pairing(
                round=round_obj,
                board_number=board_number,
                white_player=white.user if white else None,
                black_player=black.user if black else None,
                is_bye=is_bye,
                result=Pairing.Result.BYE if is_bye else Pairing.Result.PENDING,
            )
            pairing.full_clean()
            pairing.save()
            if is_bye and white is not None:
                white.had_bye = True
                white.save(update_fields=['had_bye'])

    @staticmethod
    @transaction.atomic
    def generate_next_round(tournament: Tournament) -> Round:
        if tournament.status != Tournament.Status.IN_PROGRESS:
            raise TournamentError("El torneo debe estar en curso para generar una nueva ronda.")

        pairing_service = get_pairing_service(tournament)
        if pairing_service.supports_all_rounds_upfront:
            next_round = tournament.rounds.filter(status=Round.Status.PENDING).order_by('number').first()
            if not next_round:
                raise TournamentError("No quedan rondas pendientes; genera todas las rondas al iniciar el torneo.")
            return TournamentService.open_round(next_round)

        current_round = tournament.current_round
        if current_round is not None and current_round.status != Round.Status.COMPLETED:
            raise TournamentError("Debes cerrar la ronda actual antes de generar la siguiente.")

        next_number = (current_round.number + 1) if current_round else 1
        if tournament.rounds_total and next_number > tournament.rounds_total:
            raise TournamentError("Ya se generaron todas las rondas planificadas para este torneo.")

        participants = list(tournament.active_participants)
        standings = {row['participant'].id: row for row in StandingsService.compute_standings(tournament)}
        past_pairings = list(Pairing.objects.filter(round__tournament=tournament).select_related('white_player', 'black_player'))

        round_pairings = pairing_service.generate_next_round_pairings(tournament, participants, standings, past_pairings)

        round_obj = Round.objects.create(tournament=tournament, number=next_number)
        TournamentService._persist_pairings(round_obj, round_pairings)
        return TournamentService.open_round(round_obj)

    @staticmethod
    @transaction.atomic
    def open_round(round_obj: Round) -> Round:
        """Creates the actual games.Game rows for this round's non-bye pairings and marks it IN_PROGRESS."""
        if round_obj.status != Round.Status.PENDING:
            return round_obj

        tournament = round_obj.tournament
        time_ms = tournament.time_control_minutes * 60 * 1000

        for pairing in round_obj.pairings.filter(is_bye=False, game__isnull=True):
            game = Game.objects.create(
                white_player=pairing.white_player,
                black_player=pairing.black_player,
                time_control_minutes=tournament.time_control_minutes,
                time_control_increment=tournament.time_control_increment,
                white_time_left_ms=time_ms,
                black_time_left_ms=time_ms,
                fen_current=chess.STARTING_FEN,
                status=Game.Status.IN_PROGRESS,
                last_move_at=timezone.now(),
                is_competitive=True,
            )
            pairing.game = game
            pairing.save(update_fields=['game'])

        round_obj.status = Round.Status.IN_PROGRESS
        round_obj.started_at = timezone.now()
        round_obj.save(update_fields=['status', 'started_at'])
        return round_obj

    @staticmethod
    def sync_finished_games(tournament: Tournament):
        """Copies results from finished games.Game rows into their Pairing, so standings stay current."""
        pending = Pairing.objects.filter(
            round__tournament=tournament, result=Pairing.Result.PENDING, is_bye=False,
            game__status=Game.Status.FINISHED,
        ).select_related('game')

        for pairing in pending:
            winner = pairing.game.winner
            if winner == Game.Winner.WHITE:
                pairing.result = Pairing.Result.WHITE_WIN
            elif winner == Game.Winner.BLACK:
                pairing.result = Pairing.Result.BLACK_WIN
            elif winner == Game.Winner.DRAW:
                pairing.result = Pairing.Result.DRAW
            else:
                continue
            pairing.save(update_fields=['result'])
            # Safety net: make sure the finished game affected ratings exactly
            # once (normally this already happened in GameConsumer; this call is
            # idempotent and only fills gaps, never applies twice).
            RatingService.process_game_result(pairing.game.id)


    @staticmethod
    def record_incident(pairing: Pairing, *, white_absent=False, black_absent=False) -> Pairing:
        """Organizer-recorded absence/forfeit for a pairing that hasn't been decided yet."""
        if pairing.is_bye:
            raise TournamentError("Un bye no puede tener incidencias de ausencia.")
        if pairing.is_decided:
            raise TournamentError("Este emparejamiento ya tiene un resultado registrado.")

        pairing.white_absent = white_absent
        pairing.black_absent = black_absent

        if white_absent and black_absent:
            pairing.result = Pairing.Result.DOUBLE_FORFEIT
        elif white_absent:
            pairing.result = Pairing.Result.BLACK_WIN
        elif black_absent:
            pairing.result = Pairing.Result.WHITE_WIN
        else:
            raise TournamentError("Debes indicar al menos una ausencia.")

        pairing.save(update_fields=['white_absent', 'black_absent', 'result'])

        if pairing.game and pairing.game.status == Game.Status.IN_PROGRESS:
            pairing.game.status = Game.Status.ABANDONED
            pairing.game.finish_reason = Game.FinishReason.RESIGNATION
            if pairing.result == Pairing.Result.WHITE_WIN:
                pairing.game.winner = Game.Winner.WHITE
            elif pairing.result == Pairing.Result.BLACK_WIN:
                pairing.game.winner = Game.Winner.BLACK
            pairing.game.save(update_fields=['status', 'finish_reason', 'winner'])
            # Forfeit with a decided winner is a terminal competitive result:
            # apply ratings once (idempotent).
            RatingService.process_game_result(pairing.game.id)

        return pairing


    @staticmethod
    def set_manual_result(pairing: Pairing, result: str) -> Pairing:
        """Organizer override for correcting a result (e.g. after reviewing an incident)."""
        if pairing.is_bye:
            raise TournamentError("El resultado de un bye no puede modificarse manualmente.")
        if result not in [Pairing.Result.WHITE_WIN, Pairing.Result.BLACK_WIN, Pairing.Result.DRAW, Pairing.Result.DOUBLE_FORFEIT]:
            raise TournamentError("Resultado inválido.")
        pairing.result = result
        pairing.save(update_fields=['result'])
        return pairing

    @staticmethod
    def close_round(tournament: Tournament, round_obj: Round) -> Round:
        if round_obj.tournament_id != tournament.id:
            raise TournamentError("La ronda no pertenece a este torneo.")
        if round_obj.status != Round.Status.IN_PROGRESS:
            raise TournamentError("Solo se puede cerrar una ronda que esté en curso.")

        TournamentService.sync_finished_games(tournament)

        undecided = round_obj.pairings.filter(result=Pairing.Result.PENDING)
        if undecided.exists():
            raise TournamentError(
                "Hay emparejamientos sin resultado en esta ronda; regístralos (o una ausencia) antes de cerrarla."
            )

        round_obj.status = Round.Status.COMPLETED
        round_obj.closed_at = timezone.now()
        round_obj.save(update_fields=['status', 'closed_at'])
        return round_obj

    @staticmethod
    def finalize_tournament(tournament: Tournament) -> Tournament:
        if tournament.status != Tournament.Status.IN_PROGRESS:
            raise TournamentError("Solo un torneo en curso puede finalizarse.")

        unfinished_rounds = tournament.rounds.exclude(status=Round.Status.COMPLETED)
        if unfinished_rounds.exists():
            raise TournamentError("Todas las rondas generadas deben cerrarse antes de finalizar el torneo.")

        tournament.status = Tournament.Status.COMPLETED
        tournament.save(update_fields=['status'])
        return tournament

    @staticmethod
    def cancel_tournament(tournament: Tournament) -> Tournament:
        if tournament.status == Tournament.Status.COMPLETED:
            raise TournamentError("Un torneo finalizado no puede cancelarse.")
        tournament.status = Tournament.Status.CANCELLED
        tournament.save(update_fields=['status'])
        return tournament
