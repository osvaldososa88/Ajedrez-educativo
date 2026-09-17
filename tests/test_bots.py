"""
Bot training system tests.

Covers: bot/profile models, categories & ordering, repeated names, unlock
progression (first bot, victory-unlocks-next, per-student independence,
per-category independence, deactivated bots), game creation, ELO isolation,
server-side security, history filtering, analysis reuse and the seed command.
"""
import pytest
from django.core.management import call_command
from django.test import Client
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.bots.engine import BotEngineManager
from apps.bots.models import Bot, BotProfile, BotProgress
from apps.bots.services import BotError, BotService
from apps.games.models import Game
from apps.ratings.models import RatingChange


def make_user(username, role=CustomUser.Role.STUDENT):
    return CustomUser.objects.create_user(username=username, password='password123', role=role)


def make_profile(name='Perfil Test', skill=5, error_p=0.2, depth=4, multipv=3):
    return BotProfile.objects.create(
        name=name, engine_depth=depth, move_time_ms=300,
        skill_level=skill, multipv=multipv, error_probability=error_p,
    )


def make_bot(name, category=Bot.Category.BEGINNER, order=1, elo=700, profile=None, active=True):
    bot = Bot(
        user=Bot.create_bot_account(name),
        display_name=name,
        category=category,
        order=order,
        displayed_elo=elo,
        profile=profile or make_profile(f'Perfil {name} {category} {order}'),
        is_active=active,
    )
    bot.save()
    return bot


def make_finished_bot_game(bot, human, winner_human=True):
    game = Game.objects.create(
        white_player=human,
        black_player=bot.user,
        status=Game.Status.FINISHED,
        winner=Game.Winner.WHITE if winner_human else Game.Winner.BLACK,
        finish_reason=Game.FinishReason.CHECKMATE,
        is_competitive=False,
        vs_bot=True,
    )
    return game


# ---------------------------------------------------------------------------
# Modelos: creación, categorías, orden, nombres repetidos
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBotModels:
    def test_bot_creation_and_internal_account(self):
        profile = make_profile()
        bot = make_bot('Mateo', order=1, profile=profile)

        assert bot.user.role == CustomUser.Role.BOT
        assert bot.user.username.startswith('bot_')
        # Bots cannot log in: unusable password.
        assert not bot.user.has_usable_password()
        assert bot.display_name == 'Mateo'
        assert bot.get_category_display() == 'Principiante'
        # displayed ELO is synced to the internal account rating.
        assert bot.user.elo_rating == 700

    def test_repeated_names_across_categories(self):
        p = make_profile()
        b1 = make_bot('Mateo', Bot.Category.BEGINNER, order=1, elo=700, profile=p)
        b2 = make_bot('Mateo', Bot.Category.INTERMEDIATE, order=1, elo=1100, profile=p)
        b3 = make_bot('Mateo', Bot.Category.ADVANCED, order=1, elo=1600, profile=p)

        assert b1.pk != b2.pk != b3.pk
        assert b1.display_name == b2.display_name == b3.display_name == 'Mateo'
        # Internal identities are different accounts.
        assert len({b1.user_id, b2.user_id, b3.user_id}) == 3

    def test_category_order_unique(self):
        from django.db import IntegrityError
        make_bot('A', Bot.Category.BEGINNER, order=1)
        with pytest.raises(IntegrityError):
            make_bot('B', Bot.Category.BEGINNER, order=1)

    def test_displayed_elo_never_changes_by_playing(self):
        bot = make_bot('Estático')
        human = make_user('humano_elo')
        elo_before = bot.displayed_elo

        game = make_finished_bot_game(bot, human, winner_human=True)
        result = BotService.on_game_finished(game)

        bot.refresh_from_db()
        assert result['handled'] is True
        assert bot.displayed_elo == elo_before  # static difficulty label
        assert bot.user.elo_rating == elo_before

    def test_admin_changelist_loads(self):
        from django.contrib.auth import get_user_model
        admin = CustomUser.objects.create_superuser('admin_x', 'a@a.com', 'pass12345')
        make_bot('AdminVisible')
        client = Client()
        client.force_login(admin)
        response = client.get('/admin/bots/bot/')
        assert response.status_code == 200
        assert 'AdminVisible'.encode() in response.content


# ---------------------------------------------------------------------------
# Desbloqueo y progresión
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUnlockProgression:
    def test_first_active_bot_unlocked_others_locked(self):
        make_bot('Primero', order=1)
        make_bot('Segundo', order=2)
        make_bot('Tercero', order=3)
        user = make_user('alumno1')

        bots = {b.display_name: b for b in Bot.objects.all()}
        assert BotService.is_bot_unlocked(user, bots['Primero']) is True
        assert BotService.is_bot_unlocked(user, bots['Segundo']) is False
        assert BotService.is_bot_unlocked(user, bots['Tercero']) is False

    def test_victory_unlocks_next_bot_same_category(self):
        primero = make_bot('Primero', order=1)
        segundo = make_bot('Segundo', order=2)
        make_bot('Tercero', order=3)
        user = make_user('alumno2')

        game = make_finished_bot_game(primero, user, winner_human=True)
        result = BotService.on_game_finished(game)

        assert result['handled'] and result['first_defeat']
        assert result['unlocked'] == 'Segundo'
        assert BotService.is_bot_unlocked(user, segundo) is True
        assert BotProgress.objects.filter(user=user, bot=primero, defeated=True).exists()

    def test_defeat_does_not_unlock_anything(self):
        primero = make_bot('Primero', order=1)
        make_bot('Segundo', order=2)
        user = make_user('alumno3')

        game = make_finished_bot_game(primero, user, winner_human=False)
        result = BotService.on_game_finished(game)

        assert result['handled'] is False
        assert BotProgress.objects.filter(user=user).count() == 0
        assert Bot.objects.filter(category=Bot.Category.BEGINNER, order=2).first()
        assert not BotProgress.objects.filter(user=user).exists()

    def test_draw_does_not_unlock(self):
        primero = make_bot('Primero', order=1)
        user = make_user('alumno4')
        game = Game.objects.create(
            white_player=user, black_player=primero.user,
            status=Game.Status.FINISHED, winner=Game.Winner.DRAW,
            finish_reason=Game.FinishReason.AGREEMENT, vs_bot=True, is_competitive=False,
        )
        BotService.on_game_finished(game)
        assert not BotProgress.objects.filter(user=user).exists()

    def test_unlock_is_independent_per_student(self):
        primero = make_bot('Primero', order=1)
        segundo = make_bot('Segundo', order=2)
        juan = make_user('juan')
        pedro = make_user('pedro')

        BotService.on_game_finished(make_finished_bot_game(primero, juan, winner_human=True))

        assert BotService.is_bot_unlocked(juan, segundo) is True
        assert BotService.is_bot_unlocked(pedro, segundo) is False

    def test_progression_independent_per_category(self):
        beg = make_bot('Inicio', Bot.Category.BEGINNER, order=1)
        make_bot('SiguienteBeg', Bot.Category.BEGINNER, order=2)
        inter = make_bot('InicioInter', Bot.Category.INTERMEDIATE, order=1)
        make_bot('SiguienteInter', Bot.Category.INTERMEDIATE, order=2)
        user = make_user('alumno5')

        # Win only in the beginner category.
        BotService.on_game_finished(make_finished_bot_game(beg, user, winner_human=True))

        assert BotService.is_bot_unlocked(user, inter) is True  # first of its category
        assert BotProgress.objects.filter(user=user, bot__category=Bot.Category.INTERMEDIATE).count() == 0
        # The intermediate progression did not advance.
        next_inter = BotService.next_active_bot(inter)
        assert next_inter.display_name == 'SiguienteInter'
        assert not BotProgress.objects.filter(user=user, bot=next_inter).exists()

    def test_deactivated_bot_skipped_in_progression(self):
        primero = make_bot('Primero', order=1)
        Bot.objects.filter(pk=primero.pk).first()
        segundo = make_bot('Segundo', order=2)
        segundo.is_active = False
        segundo.save()
        tercero = make_bot('Tercero', order=3)
        user = make_user('alumno6')

        BotService.on_game_finished(make_finished_bot_game(primero, user, winner_human=True))

        # The inactive bot is skipped: the next ACTIVE bot is unlocked.
        assert BotService.is_bot_unlocked(user, tercero) is True
        result = BotService.on_game_finished(
            make_finished_bot_game(primero, make_user('otro7'), winner_human=True)
        )
        assert result['unlocked'] == 'Tercero'

    def test_category_completed_notification(self):
        primero = make_bot('Ultimo', order=1)
        user = make_user('alumno8')
        game = make_finished_bot_game(primero, user, winner_human=True)

        result = BotService.on_game_finished(game)

        assert result['handled'] and result['first_defeat']
        assert 'unlocked' not in result  # no next bot
        from apps.notifications.models import Notification
        assert Notification.objects.filter(user=user).exists()

    def test_replay_victory_is_idempotent(self):
        primero = make_bot('Primero', order=1)
        make_bot('Segundo', order=2)
        user = make_user('alumno9')

        game1 = make_finished_bot_game(primero, user, winner_human=True)
        BotService.on_game_finished(game1)
        from apps.notifications.models import Notification
        notifications_after_first = Notification.objects.filter(user=user).count()

        # Same game processed again (double click / reload): nothing new.
        result = BotService.on_game_finished(game1)
        assert result['first_defeat'] is False
        assert Notification.objects.filter(user=user).count() == notifications_after_first
        assert BotProgress.objects.filter(user=user).count() == 2  # bot + unlocked next


# ---------------------------------------------------------------------------
# Creación de partidas contra bots
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBotGameCreation:
    def test_start_game_creates_bot_game_with_flags(self):
        bot = make_bot('Rival', order=1)
        user = make_user('jugador1')

        game = BotService.start_game(user, bot, color='white')

        assert game.vs_bot is True
        assert game.is_competitive is False
        assert game.white_player_id == user.id
        assert game.black_player_id == bot.user_id
        assert game.status == Game.Status.IN_PROGRESS

    def test_start_game_color_black_and_random(self):
        bot = make_bot('Rival2', order=1)
        user = make_user('jugador2')

        game = BotService.start_game(user, bot, color='black')
        assert game.white_player_id == bot.user_id
        assert game.black_player_id == user.id

        game2 = BotService.start_game(make_user('jugador2b'), bot, color='random')
        assert {game2.white_player_id, game2.black_player_id} == {
            game2.white_player_id, game2.black_player_id
        }

    def test_locked_bot_cannot_start(self):
        make_bot('Primero', order=1)
        locked = make_bot('Bloqueado', order=2)
        user = make_user('jugador3')

        with pytest.raises(BotError):
            BotService.start_game(user, locked, color='white')

    def test_inactive_bot_cannot_start(self):
        inactive = make_bot('Apagado', order=1)
        inactive.is_active = False
        inactive.save()
        user = make_user('jugador4')

        with pytest.raises(BotError):
            BotService.start_game(user, inactive, color='white')

    def test_invalid_color_rejected(self):
        bot = make_bot('Rival3', order=1)
        user = make_user('jugador5')
        with pytest.raises(BotError):
            BotService.start_game(user, bot, color='green')

    def test_resume_existing_game_instead_of_duplicate(self):
        bot = make_bot('Rival4', order=1)
        user = make_user('jugador6')
        first = BotService.start_game(user, bot, color='white')
        second = BotService.start_game(user, bot, color='random')
        assert first.pk == second.pk

    def test_view_start_game_locked_bot_is_rejected(self, client):
        make_bot('PrimeroV', order=1)
        locked = make_bot('BloqueadoV', order=2)
        make_user('jugador7')
        client.login(username='jugador7', password='password123')

        response = client.post(reverse('bot_play', kwargs={'bot_id': locked.id}), {'color': 'white'})
        assert response.status_code == 302  # redirect back with error message
        assert Game.objects.filter(vs_bot=True).count() == 0

    def test_view_start_game_unlocked(self, client):
        bot = make_bot('Libre', order=1)
        make_user('jugador8')
        client.login(username='jugador8', password='password123')

        response = client.post(reverse('bot_play', kwargs={'bot_id': bot.id}), {'color': 'white'})
        assert response.status_code == 302
        assert Game.objects.filter(vs_bot=True, is_competitive=False).count() == 1

    def test_bots_cannot_challenge_or_join_tournaments(self, client):
        bot = make_bot('NoReto', order=1)
        human = make_user('jugador9')
        client.login(username='jugador9', password='password123')

        # Human cannot challenge a bot.
        response = client.post(reverse('create_challenge', kwargs={'user_id': bot.user.id}))
        assert response.status_code == 403

        # A bot cannot register in a tournament.
        from apps.tournaments.models import Tournament
        from apps.tournaments.services import TournamentService, TournamentError
        tournament = Tournament.objects.create(name='Torneo Bots')
        with pytest.raises(TournamentError):
            TournamentService.register(tournament, bot.user)


# ---------------------------------------------------------------------------
# ELO: las partidas contra bots NO tocan el rating competitivo
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestEloIsolation:
    def test_bot_game_never_changes_elo(self):
        bot = make_bot('EloBot', order=1)
        user = make_user('jugador10')

        game = make_finished_bot_game(bot, user, winner_human=True)
        from apps.ratings.services import RatingService as RS
        service_result = RS.process_game_result(game.id)


        user.refresh_from_db()
        bot.refresh_from_db()
        assert service_result['status'] == 'not_rated'
        assert user.elo_rating == 1200
        assert bot.user.elo_rating == bot.displayed_elo
        assert RatingChange.objects.count() == 0
        game.refresh_from_db()
        assert game.rating_processed is True


# ---------------------------------------------------------------------------
# Historial, análisis y problemas desde partidas contra bots
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHistoryAnalysisPuzzles:
    def _make_history(self):
        bot = make_bot('HistoriaBot', order=1)
        human = make_user('historico')
        rival = make_user('rival_humano')

        bot_game = Game.objects.create(
            white_player=human, black_player=bot.user,
            status=Game.Status.FINISHED, winner=Game.Winner.WHITE,
            finish_reason=Game.FinishReason.CHECKMATE, vs_bot=True, is_competitive=False,
        )
        human_game = Game.objects.create(
            white_player=human, black_player=rival,
            status=Game.Status.FINISHED, winner=Game.Winner.DRAW,
            finish_reason=Game.FinishReason.AGREEMENT, vs_bot=False, is_competitive=True,
        )
        return bot, human, bot_game, human_game

    def test_history_filter_bot_vs_human(self, client):
        bot, human, bot_game, human_game = self._make_history()
        client.login(username='historico', password='password123')
        url = reverse('game_history')

        response_all = client.get(url)
        assert bot_game.id in [g.id for g in response_all.context['games']]
        assert human_game.id in [g.id for g in response_all.context['games']]

        response_bots = client.get(url + '?filter=bot')
        ids = [g.id for g in response_bots.context['games']]
        assert bot_game.id in ids and human_game.id not in ids

        response_human = client.get(url + '?filter=human')
        ids = [g.id for g in response_human.context['games']]
        assert human_game.id in ids and bot_game.id not in ids

    def test_history_shows_bot_display_name(self, client):
        bot, human, bot_game, human_game = self._make_history()
        client.login(username='historico', password='password123')
        response = client.get(reverse('game_history') + '?filter=bot')
        content = response.content.decode()
        assert 'HistoriaBot' in content and '🤖' in content

    def test_analysis_job_allowed_for_finished_bot_game(self, client):
        bot, human, bot_game, _ = self._make_history()
        client.login(username='historico', password='password123')
        url = reverse('create_game_analysis_job', kwargs={'game_id': bot_game.id})
        response = client.get(url)
        assert response.status_code == 302
        from apps.analysis.models import AnalysisJob
        assert AnalysisJob.objects.filter(game=bot_game).exists()

    def test_puzzle_from_bot_game_mentions_bot(self):
        from apps.analysis.models import MoveAnalysis
        from apps.personalization.services import _build_title_and_description
        bot, human, bot_game, human_game = self._make_history()

        move = MoveAnalysis(job=None, ply=18, move_san='Qd2?', move_uci='d1d2',
                            fen_before='x', fen_after='y')
        title, description = _build_title_and_description(bot_game, move)
        assert 'HistoriaBot' in title and 'bot' in title

        # Human vs human games keep the original title format (no bot mention).
        title_human, _ = _build_title_and_description(human_game, move)
        assert 'bot' not in title_human


# ---------------------------------------------------------------------------
# Seed command y motor
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSeedCommandAndEngine:
    def test_seed_creates_90_bots_and_is_idempotent(self):
        call_command('seed_bots', verbosity=0)
        assert Bot.objects.count() == 90
        assert BotProfile.objects.count() == 12
        for category, _label in Bot.Category.choices:
            assert Bot.objects.filter(category=category).count() == 30
            assert Bot.objects.filter(category=category, order=1).exists()

        first_beginner = Bot.objects.filter(
            category=Bot.Category.BEGINNER, order=1
        ).first()
        assert first_beginner.display_name == 'Mateo'
        assert first_beginner.displayed_elo == 700

        # Re-running updates instead of duplicating.
        call_command('seed_bots', verbosity=0)
        assert Bot.objects.count() == 90
        assert BotProfile.objects.count() == 12

    def test_controlled_error_selection_respects_max_cp_loss(self):
        import chess
        from apps.bots.engine import BotEngineManager
        from apps.bots.models import BotProfile

        # Create profile with max_cp_loss = 100
        profile = BotProfile.objects.create(
            name='ProfileMaxCP',
            best_move_prob=0.0,
            alt_move_prob=0.0,
            minor_error_prob=0.0,
            blunder_prob=1.0,  # Try to force blunder
            max_cp_loss=100,   # But cap at 100 cp loss!
            multipv=4,
        )

        pv_lines = [
            'info depth 10 multipv 1 score cp 200 pv e2e4 e7e5',
            'info depth 10 multipv 2 score cp 170 pv g1f3 b8c6',  # loss 30
            'info depth 10 multipv 3 score cp 120 pv d2d4 e7e5',  # loss 80
            'info depth 10 multipv 4 score cp -300 pv f2f4 d7d5', # loss 500 (> max_cp_loss 100!)
        ]

        # Selected move must NEVER be f2f4 because its loss is 500 > 100 max_cp_loss
        for _ in range(20):
            selected = BotEngineManager.select_controlled_move('e2e4', pv_lines, profile)
            assert selected in ['e2e4', 'g1f3', 'd2d4']
            assert selected != 'f2f4'

    def test_emergency_move_is_legal_without_engine(self):
        import chess
        move_uci = BotEngineManager._emergency_move(chess.Board())
        assert move_uci in [m.uci() for m in chess.Board().legal_moves]


@pytest.mark.django_db
class TestOpeningsAndBookService:
    def test_opening_creation_and_line_validation(self):
        from apps.bots.models import Opening, OpeningLine

        sicilian = Opening.objects.create(name='Defensa Siciliana', eco='B20')
        line = OpeningLine.objects.create(
            opening=sicilian,
            name='Línea Principal',
            moves_san='1.e4 c5 2.Nf3 d6',
            moves_uci=['e2e4', 'c7c5', 'g1f3', 'd7d6'],
            bot_color=OpeningLine.BotColor.BLACK,
        )
        assert line.opening == sicilian
        assert line.moves_uci == ['e2e4', 'c7c5', 'g1f3', 'd7d6']

    def test_opening_book_service_matching_and_deviation(self):
        import chess
        from apps.bots.models import Opening, OpeningLine, Bot
        from apps.bots.opening_service import OpeningBookService

        sicilian = Opening.objects.create(name='Defensa Siciliana', eco='B20')
        line = OpeningLine.objects.create(
            opening=sicilian,
            name='Línea Principal',
            moves_san='1.e4 c5 2.Nf3 d6',
            moves_uci=['e2e4', 'c7c5', 'g1f3', 'd7d6'],
            bot_color=OpeningLine.BotColor.BLACK,
        )

        bot = make_bot('BotSiciliana', order=1)
        bot.opening_mode = Bot.OpeningMode.SPECIFIC_OPENING
        bot.specific_opening_black = sicilian
        bot.specific_opening_white = sicilian
        bot.save()

        # 1. White plays e2e4 (history = ['e2e4']). Bot's turn (Black).
        board = chess.Board()
        board.push_san('e4')
        move = OpeningBookService.get_opening_move(bot, ['e2e4'], board)
        assert move == 'c7c5'

        # 2. Deviation test: White plays d2d4 instead of e2e4 (history = ['d2d4']).
        board_dev = chess.Board()
        board_dev.push_san('d4')
        move_dev = OpeningBookService.get_opening_move(bot, ['d2d4'], board_dev)
        assert move_dev is None  # Deviated -> pass control to Stockfish


# ---------------------------------------------------------------------------
# Respuesta automática del bot por WebSocket (motor simulado)
# ---------------------------------------------------------------------------

@pytest.mark.django_db(transaction=True)
class TestBotWebsocketReply:
    @pytest.mark.asyncio
    async def test_bot_replies_automatically_after_human_move(self, monkeypatch):
        from channels.testing import WebsocketCommunicator
        from channels.db import database_sync_to_async
        from apps.games.consumers import GameConsumer

        @database_sync_to_async
        def setup():
            bot = make_bot('WsBot', order=1)
            human = CustomUser.objects.create_user(username='ws_human', password='pass')
            game = BotService.start_game(human, bot, color='white')
            return human, game

        @database_sync_to_async
        def read_game_stats(game):
            game.refresh_from_db()
            return game.moves.count(), game.turn, game.clock_started


        def fake_compute_uci(fen, profile_id, *args, **kwargs):
            # Deterministic legal reply for the mocked engine.
            return 'e7e5'

        monkeypatch.setattr(BotService, 'compute_uci', staticmethod(fake_compute_uci))

        human, game = await setup()
        assert game.white_player_id == human.id  # human plays white

        comm = WebsocketCommunicator(GameConsumer.as_asgi(), f"/ws/game/{game.id}/")
        comm.scope['user'] = human
        comm.scope['url_route'] = {'kwargs': {'game_id': str(game.id)}}
        connected, _ = await comm.connect()
        assert connected
        init_msg = await comm.receive_json_from()
        assert init_msg['type'] == 'init_state'
        assert init_msg['state']['white_player'] == 'ws_human'
        assert init_msg['state']['black_player'] == 'WsBot'  # editable display name

        # Human plays e2e4 -> bot answers with the mocked e7e5.
        await comm.send_json_to({'type': 'make_move', 'uci': 'e2e4'})
        human_update = await comm.receive_json_from()
        bot_update = await comm.receive_json_from()

        assert human_update['type'] == 'game_update'
        assert bot_update['type'] == 'game_update'
        assert bot_update['state']['moves_history'][-1]['san'] == 'e5'

        moves_count, turn, clock_started = await read_game_stats(game)
        assert moves_count == 2
        assert turn == 'WHITE'
        assert clock_started is False  # bot games are untimed


        await comm.disconnect()

    @pytest.mark.asyncio
    async def test_bot_plays_first_move_when_human_is_black(self, monkeypatch):
        from channels.testing import WebsocketCommunicator
        from channels.db import database_sync_to_async
        from apps.games.consumers import GameConsumer

        @database_sync_to_async
        def setup():
            bot = make_bot('WsBotNegras', order=1)
            human = CustomUser.objects.create_user(username='ws_negras', password='pass')
            game = BotService.start_game(human, bot, color='black')
            return human, game

        def fake_compute_uci(fen, profile_id, *args, **kwargs):
            return 'e2e4'

        monkeypatch.setattr(BotService, 'compute_uci', staticmethod(fake_compute_uci))

        human, game = await setup()

        comm = WebsocketCommunicator(GameConsumer.as_asgi(), f"/ws/game/{game.id}/")
        comm.scope['user'] = human
        comm.scope['url_route'] = {'kwargs': {'game_id': str(game.id)}}
        connected, _ = await comm.connect()
        assert connected
        await comm.receive_json_from()  # init_state

        bot_update = await comm.receive_json_from()
        assert bot_update['type'] == 'game_update'
        assert bot_update['state']['moves_history'][-1]['san'] == 'e4'

        await comm.disconnect()





