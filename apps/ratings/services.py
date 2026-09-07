"""
Rating application service.

`RatingService.process_game_result` is the ONLY entry point that mutates player
ELO. It is called every time a game reaches a terminal state (see the hooks in
`apps.games.consumers` and `apps.tournaments.services`) and is safe to call any
number of times:

  * Runs inside a DB transaction and locks the game row (`select_for_update`).
  * `Game.rating_processed` flag + the DB-level unique constraint on
    (game, player) in RatingChange guarantee exactly ONE rating application per
    finished game per player, even under concurrent/repeated requests.

Rules implemented here:
  * Only games with `is_competitive=True` and a determined `winner` affect ELO.
  * Draw/timeout/resignation/checkmate all count (any terminal state).
  * Tournament forfeits (game ABANDONED with a winner) count too.
  * Games with no winner (e.g. DOUBLE_FORFEIT) are marked processed without
    changing any rating.
  * Rating floor: 100. No artificial maximum.
"""
import logging

from django.db import transaction, IntegrityError
from django.db.models import Max

from apps.games.models import Game
from .elo import (
    expected_score,
    k_factor,
    compute_rating_change,
    apply_rating_change,
    rank_for_elo,
    next_rank_info,
)
from .models import RatingChange

logger = logging.getLogger(__name__)


def _game_involves_bot(game) -> bool:
    """Bot training games never affect the competitive rating."""
    if game.vs_bot:
        return True
    from apps.bots.models import Bot
    return Bot.objects.filter(
        user_id__in=[game.white_player_id, game.black_player_id]
    ).exists()



class RatingService:
    # --- Game processing ----------------------------------------------------

    @staticmethod
    def game_mode(game: Game) -> str:
        """Classify where a competitive game came from (for history/rankings)."""
        if getattr(game, 'tournament_pairing', None) is not None:
            return RatingChange.GameMode.TOURNAMENT
        if getattr(game, 'originating_challenge', None) is not None:
            return RatingChange.GameMode.CHALLENGE
        return RatingChange.GameMode.COMPETITIVE

    @staticmethod
    def rated_games_played(user) -> int:
        """Number of RATED games the player has completed (never includes training)."""
        return RatingChange.objects.filter(player=user).count()

    @staticmethod
    def process_game_result(game_id) -> dict:
        """
        Apply ELO for a finished game exactly once. Idempotent and concurrent-safe.

        Returns {'status': ..., 'changes': [...]} where changes is a list of
        per-player dicts (only when ratings actually changed this call), so the
        caller can show the deltas in the UI without trusting the client.
        """
        try:
            with transaction.atomic():
                game = (
                    Game.objects.select_for_update()
                    .select_related('white_player', 'black_player')
                    .get(pk=game_id)
                )

                if game.status == Game.Status.IN_PROGRESS:
                    # Nothing decided yet: never rate, never mark.
                    return {'status': 'not_finished', 'changes': []}

                if game.rating_processed:
                    return {'status': 'already_processed', 'changes': []}

                # Terminal game. Decide whether it is rating-eligible.
                # Bot training games NEVER touch the competitive ELO (explicit
                # exclusion; they are also created with is_competitive=False).
                if not game.is_competitive or game.winner is None or _game_involves_bot(game):

                    # Unrated/training game, or no result (e.g. DOUBLE_FORFEIT):
                    # evaluate and mark so it is never reconsidered.
                    game.rating_processed = True
                    game.save(update_fields=['rating_processed'])
                    return {'status': 'not_rated', 'changes': []}

                changes = RatingService._apply_ratings(game)

                game.rating_processed = True
                game.save(update_fields=['rating_processed'])

                return {'status': 'processed', 'changes': changes}

        except IntegrityError:
            # Another concurrent process already inserted the history rows:
            # the game was processed first -> this call must be a no-op.
            logger.info("Rating for game %s was already processed concurrently.", game_id)
            return {'status': 'already_processed', 'changes': []}
        except Game.DoesNotExist:
            logger.warning("Rating requested for unknown game %s.", game_id)
            return {'status': 'not_found', 'changes': []}

    # --- Rating application ---------------------------------------------------

    @staticmethod
    def _apply_ratings(game: Game) -> list:
        """Compute + persist new ratings and history rows for both players."""
        white = game.white_player
        black = game.black_player

        if game.winner == Game.Winner.WHITE:
            white_score, black_score = 1.0, 0.0
        elif game.winner == Game.Winner.BLACK:
            white_score, black_score = 0.0, 1.0
        else:  # Game.Winner.DRAW
            white_score, black_score = 0.5, 0.5

        white_expected = expected_score(white.elo_rating, black.elo_rating)
        black_expected = 1.0 - white_expected

        # K depends ONLY on rated games completed before this one.
        white_k = k_factor(RatingService.rated_games_played(white))
        black_k = k_factor(RatingService.rated_games_played(black))

        white_delta = compute_rating_change(white.elo_rating, white_expected, white_score, white_k)
        black_delta = compute_rating_change(black.elo_rating, black_expected, black_score, black_k)

        white_before, black_before = white.elo_rating, black.elo_rating
        white_after = apply_rating_change(white_before, white_delta)
        black_after = apply_rating_change(black_before, black_delta)

        white.elo_rating = white_after
        white.save(update_fields=['elo_rating'])
        black.elo_rating = black_after
        black.save(update_fields=['elo_rating'])

        mode = RatingService.game_mode(game)
        RatingChange.objects.bulk_create([
            RatingService._history_row(
                game, mode, player=white, opponent=black,
                rating_before=white_before, rating_after=white_after,
                change=white_after - white_before, score=white_score,
                expected=white_expected, k=white_k, opponent_rating=black_before,
            ),
            RatingService._history_row(
                game, mode, player=black, opponent=white,
                rating_before=black_before, rating_after=black_after,
                change=black_after - black_before, score=black_score,
                expected=black_expected, k=black_k, opponent_rating=white_before,
            ),
        ])


        return [
            RatingService._change_payload(white, white_before, white_after, white_score, white_k),
            RatingService._change_payload(black, black_before, black_after, black_score, black_k),
        ]


    @staticmethod
    def _result_choice(score: float) -> str:
        if score == 1.0:
            return RatingChange.Result.WIN
        if score == 0.5:
            return RatingChange.Result.DRAW
        return RatingChange.Result.LOSS

    @staticmethod
    def _history_row(game, mode, *, player, opponent, rating_before, rating_after,
                     change, score, expected, k, opponent_rating) -> RatingChange:
        return RatingChange(
            player=player,
            opponent=opponent,
            opponent_username=opponent.username,
            opponent_rating=opponent_rating,
            game=game,
            game_mode=mode,
            rating_before=rating_before,
            rating_after=rating_after,
            change=change,
            result=RatingService._result_choice(score),
            k_factor=k,
            expected_score=expected,
        )


    @staticmethod
    def _change_payload(player, before, after, score, k) -> dict:
        return {
            'player_id': player.id,
            'username': player.username,
            'rating_before': before,
            'rating_after': after,
            'change': after - before,
            'result': RatingService._result_choice(score),
            'k_factor': k,
        }


    # --- Profile statistics ---------------------------------------------------

    @staticmethod
    def get_profile_stats(user) -> dict:
        """
        Aggregate stats for the profile page, derived from RatingChange (the
        rating-only history) so they are immune to old-game pruning.
        """
        current_elo = user.elo_rating
        changes = RatingChange.objects.filter(player=user)

        rated_games = changes.count()
        wins = changes.filter(result=RatingChange.Result.WIN).count()
        draws = changes.filter(result=RatingChange.Result.DRAW).count()
        losses = changes.filter(result=RatingChange.Result.LOSS).count()

        best_from_history = changes.aggregate(best=Max('rating_after'))['best']
        best_elo = max(best_from_history, current_elo) if best_from_history is not None else current_elo

        oldest = changes.order_by('created_at').first()
        initial_elo = oldest.rating_before if oldest else current_elo

        recent = list(changes.order_by('-created_at')[:10])

        rank = rank_for_elo(current_elo)
        next_rank, points_to_next = next_rank_info(current_elo)

        return {
            'current_elo': current_elo,
            'rank': rank,
            'next_rank': next_rank,
            'points_to_next_rank': points_to_next,
            'rated_games': rated_games,
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'win_rate': round((wins / rated_games) * 100, 1) if rated_games else 0.0,
            'initial_elo': initial_elo,
            'best_elo': best_elo,
            'total_change': current_elo - initial_elo,
            'recent_changes': recent,
        }

