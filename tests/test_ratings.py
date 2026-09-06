"""
ELO rating system tests.

Covers the 12 required scenarios plus K-factor progression, rating floor,
rank tiers and profile statistics.
"""
import asyncio

import pytest
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async

from apps.accounts.models import CustomUser
from apps.games.models import Game, Challenge
from apps.ratings.elo import (
    expected_score,
    k_factor,
    compute_new_rating,
    rank_for_elo,
    next_rank_info,
    PlayerRank,
    INITIAL_RATING,
    MIN_RATING,
)
from apps.ratings.models import RatingChange
from apps.ratings.services import RatingService


def make_user(username, elo=None):
    kwargs = dict(username=username, password='password123')
    if elo is not None:
        kwargs['elo_rating'] = elo
    return CustomUser.objects.create_user(**kwargs)


def make_game(white, black, *, status=Game.Status.FINISHED, winner=Game.Winner.WHITE,
              finish_reason=Game.FinishReason.CHECKMATE, competitive=True):
    return Game.objects.create(
        white_player=white,
        black_player=black,
        status=status,
        winner=winner,
        finish_reason=finish_reason,
        is_competitive=competitive,
    )


def refresh(instance):
    instance.refresh_from_db()
    return instance


# ---------------------------------------------------------------------------
# Pure ELO math
# ---------------------------------------------------------------------------

class TestEloMath:
    def test_expected_score_symmetric_and_complementary(self):
        e1 = expected_score(1200, 1200)
        assert e1 == pytest.approx(0.5)
        assert expected_score(1600, 1000) + expected_score(1000, 1600) == pytest.approx(1.0)
        assert expected_score(1600, 1000) > 0.9
        assert expected_score(1000, 1600) < 0.1

    def test_k_factor_adaptive(self):
        assert k_factor(0) == 40
        assert k_factor(19) == 40
        assert k_factor(20) == 20
        assert k_factor(100) == 20

    def test_new_rating_floor(self):
        # Even a huge loss cannot go below MIN_RATING.
        assert compute_new_rating(105, 105, 0.0, 40) == MIN_RATING
        assert compute_new_rating(1200, 1200, 1.0, 40) == 1220
        assert compute_new_rating(1200, 1200, 0.0, 40) == 1180
        assert compute_new_rating(1200, 1200, 0.5, 40) == 1200

    def test_rank_tiers(self):
        assert rank_for_elo(99).label == 'Novato'
        assert rank_for_elo(100).label == 'Novato'
        assert rank_for_elo(799).label == 'Novato'
        assert rank_for_elo(800).label == 'Aprendiz'
        assert rank_for_elo(999).label == 'Aprendiz'
        assert rank_for_elo(1000).label == 'Principiante'
        assert rank_for_elo(1199).label == 'Principiante'
        assert rank_for_elo(1200).label == 'Intermedio'
        assert rank_for_elo(1399).label == 'Intermedio'
        assert rank_for_elo(1400).label == 'Avanzado'
        assert rank_for_elo(1599).label == 'Avanzado'
        assert rank_for_elo(1600).label == 'Experto'
        assert rank_for_elo(1799).label == 'Experto'
        assert rank_for_elo(1800).label == 'Maestro'
        assert rank_for_elo(2500).label == 'Maestro'

    def test_next_rank_info(self):
        nxt, points = next_rank_info(1372)
        assert nxt is PlayerRank.AVANZADO
        assert points == 28
        assert next_rank_info(1900) == (None, None)

    def test_user_rank_is_derived_not_stored(self):
        u = CustomUser(username='ranker', elo_rating=1372)  # no DB needed
        assert u.rank.label == 'Intermedio'
        u.elo_rating = 1400
        assert u.rank.label == 'Avanzado'  # derived instantly, no stored copy



# ---------------------------------------------------------------------------
# Casos 1-4: resultado, expectativa, sorpresa y tablas
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRatingApplication:
    def test_case_1_two_new_players_symmetric(self):
        a = make_user('jugador_a')
        b = make_user('jugador_b')
        game = make_game(a, b, winner=Game.Winner.WHITE)

        result = RatingService.process_game_result(game.id)

        assert result['status'] == 'processed'
        a, b = refresh(a), refresh(b)
        # Both new (K=40, E=0.5): winner +20, loser -20, perfectly symmetric.
        assert a.elo_rating == INITIAL_RATING + 20
        assert b.elo_rating == INITIAL_RATING - 20
        changes = result['changes']
        assert changes[0]['change'] + changes[1]['change'] == 0  # sum ~ 0
        assert RatingChange.objects.filter(game=game).count() == 2
        assert refresh(game).rating_processed is True

    def test_case_2_strong_beats_weak_small_change(self):
        a = make_user('fuerte', elo=1600)
        b = make_user('debil', elo=1000)
        game = make_game(a, b, winner=Game.Winner.WHITE)

        result = RatingService.process_game_result(game.id)
        a, b = refresh(a), refresh(b)

        # Favourite gains very few points, underdog loses very few.
        assert 0 < a.elo_rating - 1600 <= 2
        assert -2 <= b.elo_rating - 1000 < 0
        assert result['changes'][0]['change'] + result['changes'][1]['change'] == 0

    def test_case_3_upset_big_change(self):
        a = make_user('sorpresa', elo=1000)
        b = make_user('favorito', elo=1600)
        game = make_game(a, b, winner=Game.Winner.WHITE)

        result = RatingService.process_game_result(game.id)
        a, b = refresh(a), refresh(b)

        # Underdog beats favourite -> big gain / big loss (K=40 first games).
        assert a.elo_rating - 1000 >= 35
        assert 1600 - b.elo_rating >= 35
        assert result['changes'][0]['change'] + result['changes'][1]['change'] == 0

    def test_case_4_draw_between_unequal_players(self):
        a = make_user('debil_tablas', elo=1000)
        b = make_user('fuerte_tablas', elo=1600)
        game = make_game(a, b, winner=Game.Winner.DRAW,
                         finish_reason=Game.FinishReason.AGREEMENT)

        result = RatingService.process_game_result(game.id)
        a, b = refresh(a), refresh(b)

        # Draw helps the underdog and hurts the favourite.
        assert 15 <= a.elo_rating - 1000 <= 22
        assert -22 <= b.elo_rating - 1600 <= -15
        assert result['changes'][0]['result'] == RatingChange.Result.DRAW
        assert result['changes'][1]['result'] == RatingChange.Result.DRAW

    def test_rating_floor_enforced(self):
        a = make_user('piso_bajo', elo=110)
        b = make_user('piso_bajo_2', elo=110)
        game = make_game(a, b, winner=Game.Winner.BLACK)  # a loses

        RatingService.process_game_result(game.id)

        assert refresh(a).elo_rating == MIN_RATING  # raw 90 -> clamped to 100


# ---------------------------------------------------------------------------
# Casos 5, 12: entrenamiento / no competitivas nunca tocan el ELO
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUnratedGames:
    def test_case_5_training_game_never_changes_rating(self):
        a = make_user('entrena_a')
        b = make_user('entrena_b')
        game = make_game(a, b, winner=Game.Winner.WHITE, competitive=False)

        result = RatingService.process_game_result(game.id)

        assert result['status'] == 'not_rated'
        assert result['changes'] == []
        assert refresh(a).elo_rating == 1200
        assert refresh(b).elo_rating == 1200
        assert RatingChange.objects.count() == 0
        # Evaluated once; never reconsidered.
        assert refresh(game).rating_processed is True
        second = RatingService.process_game_result(game.id)
        assert second['status'] == 'already_processed'

    def test_case_12_unrated_stats_stay_zero(self):
        a = make_user('stats_a')
        b = make_user('stats_b')
        game = make_game(a, b, winner=Game.Winner.BLACK, competitive=False)

        RatingService.process_game_result(game.id)

        assert RatingService.rated_games_played(a) == 0
        stats = RatingService.get_profile_stats(a)
        assert stats['rated_games'] == 0
        assert stats['wins'] == stats['draws'] == stats['losses'] == 0
        assert stats['win_rate'] == 0.0
        assert stats['current_elo'] == 1200

    def test_in_progress_game_is_never_rated(self):
        a = make_user('en_curso_a')
        b = make_user('en_curso_b')
        game = make_game(a, b, status=Game.Status.IN_PROGRESS, winner=None,
                         finish_reason=None)

        result = RatingService.process_game_result(game.id)

        assert result['status'] == 'not_finished'
        assert refresh(a).elo_rating == 1200
        assert refresh(game).rating_processed is False  # still awaiting result


# ---------------------------------------------------------------------------
# Casos 6 y 7: desafíos y torneos sí afectan al ELO (individualmente)
# ---------------------------------------------------------------------------

def _finish(game, winner):
    game.status = Game.Status.FINISHED
    game.winner = winner
    game.save()
    return game


def _make_round_robin(usernames):
    from apps.tournaments.models import Tournament
    from apps.tournaments.services import TournamentService
    users = [make_user(name) for name in usernames]
    tournament = Tournament.objects.create(
        name='Torneo Test', format=Tournament.Format.ROUND_ROBIN
    )
    for u in users:
        TournamentService.register(tournament, u)
    TournamentService.start_tournament(tournament)
    return tournament, users


@pytest.mark.django_db
class TestCompetitiveModes:
    def test_case_6_challenge_game_updates_rating(self):
        a = make_user('retador')
        b = make_user('retado')
        challenge = Challenge.objects.create(sender=a, receiver=b)
        game = make_game(a, b)
        challenge.game = game
        challenge.status = Challenge.Status.ACCEPTED
        challenge.save()

        _finish(game, Game.Winner.WHITE)
        result = RatingService.process_game_result(game.id)

        assert result['status'] == 'processed'
        assert refresh(a).elo_rating == 1220
        assert refresh(b).elo_rating == 1180
        rows = RatingChange.objects.filter(game=game)
        assert rows.count() == 2
        assert rows.first().game_mode == RatingChange.GameMode.CHALLENGE

    def test_case_7_tournament_games_update_rating_individually(self):
        from apps.tournaments.models import Pairing
        from apps.tournaments.services import TournamentService

        tournament, (a, b) = _make_round_robin(['torneo_a', 'torneo_b'])
        pairing = Pairing.objects.filter(round__tournament=tournament, is_bye=False).first()
        game = pairing.game
        assert game.is_competitive is True

        _finish(game, Game.Winner.WHITE)
        result = RatingService.process_game_result(game.id)

        assert result['status'] == 'processed'
        assert refresh(a).elo_rating == 1220
        assert refresh(b).elo_rating == 1180
        row = RatingChange.objects.filter(player=a, game=game).first()
        assert row.game_mode == RatingChange.GameMode.TOURNAMENT

        TournamentService.close_round(tournament, pairing.round)
        assert refresh(a).elo_rating == 1220
        assert RatingChange.objects.filter(game=game).count() == 2


# ---------------------------------------------------------------------------
# Incidencias de torneo (ausencias) y red de seguridad de cierre de ronda
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTournamentIncidents:
    def test_forfeit_by_absence_updates_rating_once(self):
        from apps.tournaments.models import Pairing
        from apps.tournaments.services import TournamentService

        tournament, (a, b) = _make_round_robin(['ausente', 'presente'])
        pairing = Pairing.objects.filter(round__tournament=tournament, is_bye=False).first()
        game = pairing.game

        # 'a' no se presenta -> gana 'b' por ausencia -> ELO se aplica una vez.
        TournamentService.record_incident(pairing, white_absent=True)

        assert refresh(game).status == Game.Status.ABANDONED
        assert refresh(game).winner == Game.Winner.BLACK
        assert refresh(a).elo_rating == 1180
        assert refresh(b).elo_rating == 1220
        assert refresh(game).rating_processed is True
        assert RatingChange.objects.filter(game=game).count() == 2

        # Reprocesar (recarga, reintento...) no cambia nada.
        again = RatingService.process_game_result(game.id)
        assert again['status'] == 'already_processed'
        assert refresh(a).elo_rating == 1180

    def test_double_forfeit_no_rating(self):
        from apps.tournaments.models import Pairing
        from apps.tournaments.services import TournamentService

        tournament, (a, b) = _make_round_robin(['doble_a', 'doble_b'])
        pairing = Pairing.objects.filter(round__tournament=tournament, is_bye=False).first()
        game = pairing.game

        TournamentService.record_incident(pairing, white_absent=True, black_absent=True)

        # Sin ganador decidido -> el rating de nadie cambia.
        assert refresh(game).winner is None
        assert refresh(a).elo_rating == 1200
        assert refresh(b).elo_rating == 1200
        assert RatingChange.objects.count() == 0
        assert refresh(game).rating_processed is True

    def test_sync_finished_games_fills_rating_gaps(self):
        """Red de seguridad: una partida de torneo terminada cuyo rating nunca
        se aplicó (p. ej. falla del servidor) se procesa al cerrar la ronda —
        una sola vez."""
        from apps.tournaments.models import Pairing
        from apps.tournaments.services import TournamentService

        tournament, (a, b) = _make_round_robin(['gap_a', 'gap_b'])
        pairing = Pairing.objects.filter(round__tournament=tournament, is_bye=False).first()
        _finish(pairing.game, Game.Winner.WHITE)

        TournamentService.close_round(tournament, pairing.round)

        assert refresh(a).elo_rating == 1220
        assert refresh(b).elo_rating == 1180
        assert RatingChange.objects.filter(game=pairing.game).count() == 2


# ---------------------------------------------------------------------------
# Factor K adaptativo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestKFactorProgression:
    def test_k_factor_drops_after_20_rated_games(self):
        # El jugador 'a' completa 20 partidas rated (solo rated cuentan).
        a = make_user('veterano')
        for i in range(20):
            opponent = make_user(f'rival_{i}')
            game = make_game(a, opponent, winner=Game.Winner.WHITE)
            RatingService.process_game_result(game.id)
        assert RatingService.rated_games_played(a) == 20

        # 21ª partida contra rival de igual ELO: K=20 -> exactamente +10.
        a = refresh(a)
        equal = make_user('igual_veterano', elo=a.elo_rating)
        game = make_game(a, equal, winner=Game.Winner.WHITE)
        result = RatingService.process_game_result(game.id)

        assert result['changes'][0]['change'] == 10  # primeras 20 darían +20
        assert result['changes'][0]['k_factor'] == 20

    def test_training_games_do_not_count_for_k(self):
        a = make_user('k_entrena')
        # 20 partidas de entrenamiento: no cuentan para el K.
        for i in range(20):
            opponent = make_user(f'rival_train_{i}')
            game = make_game(a, opponent, winner=Game.Winner.WHITE, competitive=False)
            RatingService.process_game_result(game.id)
        assert RatingService.rated_games_played(a) == 0

        # Su primera partida rated aún usa K=40 -> +20 contra igual rating.
        equal = make_user('k_igual')
        game = make_game(a, equal, winner=Game.Winner.WHITE)
        result = RatingService.process_game_result(game.id)
        assert result['changes'][0]['change'] == 20
        assert result['changes'][0]['k_factor'] == 40


# ---------------------------------------------------------------------------
# Casos 8, 9, 11: idempotencia, recarga y tiempo
# ---------------------------------------------------------------------------

def build_state_via_consumer(game):
    """Simula lo que hace el navegador al abrir/recargar la página del tablero."""
    from apps.games.consumers import GameConsumer
    consumer = GameConsumer.__new__(GameConsumer)
    consumer.game_id = str(game.id)
    return asyncio.run(consumer.build_game_state_payload())


@pytest.mark.django_db(transaction=True)
class TestIdempotency:

    def test_case_8_double_processing(self):
        a = make_user('doble_a')
        b = make_user('doble_b')
        game = make_game(a, b, winner=Game.Winner.WHITE)

        first = RatingService.process_game_result(game.id)
        assert first['status'] == 'processed'
        elo_a_after_first = refresh(a).elo_rating

        second = RatingService.process_game_result(game.id)
        third = RatingService.process_game_result(game.id)

        assert second['status'] == 'already_processed'
        assert third['status'] == 'already_processed'
        assert second['changes'] == [] and third['changes'] == []
        assert refresh(a).elo_rating == elo_a_after_first
        assert RatingChange.objects.filter(game=game).count() == 2

    def test_case_9_page_reload_does_not_change_rating(self):
        from django.utils import timezone
        from datetime import timedelta

        a = make_user('reload_a')
        b = make_user('reload_b')
        game = Game.objects.create(
            white_player=a, black_player=b,
            status=Game.Status.IN_PROGRESS,
            clock_started=True,
            white_time_left_ms=1, black_time_left_ms=600000,
            last_move_at=timezone.now() - timedelta(seconds=5),
        )

        # Primera "recarga": el reloj expira y la partida termina -> ELO una vez.
        state1 = build_state_via_consumer(game)
        assert state1['status'] == Game.Status.FINISHED
        assert state1['finish_reason'] == 'Tiempo Agotado'
        assert len(state1['rating_changes']) == 2
        elo_after_first = refresh(a).elo_rating
        assert elo_after_first == 1180  # perdió por tiempo (K=40, E=0.5)

        # Recargas repetidas: nada vuelve a aplicarse.
        for _ in range(3):
            state = build_state_via_consumer(game)
            assert state['rating_changes'] == []
        assert refresh(a).elo_rating == elo_after_first
        assert RatingChange.objects.filter(game=game).count() == 2

    def test_case_11_timeout_finishes_game_and_updates_rating(self):
        from django.utils import timezone
        from datetime import timedelta

        a = make_user('timeout_a')
        b = make_user('timeout_b')
        game = Game.objects.create(
            white_player=a, black_player=b,
            status=Game.Status.IN_PROGRESS,
            clock_started=True,
            white_time_left_ms=500, black_time_left_ms=600000,
            last_move_at=timezone.now() - timedelta(seconds=10),
        )

        build_state_via_consumer(game)

        game = refresh(game)
        assert game.status == Game.Status.FINISHED
        assert game.finish_reason == Game.FinishReason.TIMEOUT
        assert game.winner == Game.Winner.BLACK
        assert refresh(a).elo_rating == 1180
        assert refresh(b).elo_rating == 1220
        assert game.rating_processed is True


# ---------------------------------------------------------------------------
# Caso 10: abandono vía WebSocket (flujo real del consumer) + perfil
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestResignationOverWebsocket:
    @pytest.mark.asyncio
    async def test_case_10_resignation_updates_rating_exactly_once(self):
        from apps.games.consumers import GameConsumer

        @database_sync_to_async
        def create_users():
            return (
                CustomUser.objects.create_user(username='ws_white', password='pass'),
                CustomUser.objects.create_user(username='ws_black', password='pass'),
            )

        @database_sync_to_async
        def create_game(white, black):
            return Game.objects.create(white_player=white, black_player=black)

        @database_sync_to_async
        def read_state(game, user):
            game.refresh_from_db()
            user.refresh_from_db()
            return game, user

        @database_sync_to_async
        def count_changes(game):
            return RatingChange.objects.filter(game=game).count()

        white, black = await create_users()
        game = await create_game(white, black)

        comm = WebsocketCommunicator(GameConsumer.as_asgi(), f"/ws/game/{game.id}/")
        comm.scope['user'] = white
        comm.scope['url_route'] = {'kwargs': {'game_id': str(game.id)}}
        connected, _ = await comm.connect()
        assert connected
        await comm.receive_json_from()  # init_state

        await comm.send_json_to({'type': 'resign'})
        update = await comm.receive_json_from()
        assert update['type'] == 'game_update'
        assert update['state']['status'] == Game.Status.FINISHED
        assert update['state']['finish_reason'] == 'Abandono'
        assert len(update['state']['rating_changes']) == 2

        game, white = await read_state(game, white)
        assert game.status == Game.Status.FINISHED
        assert game.finish_reason == Game.FinishReason.RESIGNATION
        assert game.winner == Game.Winner.BLACK
        assert white.elo_rating == 1180  # perdió por abandono

        # Un segundo abandono no vuelve a aplicar el ELO.
        await comm.send_json_to({'type': 'resign'})
        await asyncio.sleep(0.2)
        game, white = await read_state(game, white)
        assert white.elo_rating == 1180
        assert await count_changes(game) == 2

        await comm.disconnect()



# ---------------------------------------------------------------------------
# Estadísticas de perfil e historial
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestProfileStats:
    def test_profile_stats_and_history_content(self):
        a = make_user('perfil_a')
        b = make_user('perfil_b')

        # a gana, a gana, a pierde.
        RatingService.process_game_result(make_game(a, b).id)
        RatingService.process_game_result(make_game(a, b).id)
        RatingService.process_game_result(
            make_game(a, b, winner=Game.Winner.BLACK).id
        )

        stats = RatingService.get_profile_stats(a)
        assert stats['rated_games'] == 3
        assert stats['wins'] == 2
        assert stats['losses'] == 1
        assert stats['draws'] == 0
        assert stats['win_rate'] == 66.7
        assert stats['initial_elo'] == 1200
        assert stats['current_elo'] == a.elo_rating
        assert stats['best_elo'] >= stats['current_elo']
        assert stats['total_change'] == stats['current_elo'] - 1200
        assert len(stats['recent_changes']) == 3

        # El historial permite reconstruir qué pasó: rival, resultado, ratings.
        row = RatingChange.objects.filter(player=a).first()
        assert row.rating_before == 1200
        assert row.rating_after == row.rating_before + row.change
        assert row.opponent_username == 'perfil_b'
        assert row.opponent_rating == 1200
        assert row.result in [RatingChange.Result.WIN, RatingChange.Result.LOSS]
        assert row.k_factor == 40
        assert 0.0 <= row.expected_score <= 1.0
        assert row.game_mode == RatingChange.GameMode.COMPETITIVE

        # La vista de perfil arma el contexto sin errores.
        from django.test import Client
        from django.urls import reverse
        client = Client()
        client.force_login(a)
        response = client.get(reverse('profile_detail', kwargs={'username': a.username}))
        assert response.status_code == 200
        assert a.rank.label.encode() in response.content







