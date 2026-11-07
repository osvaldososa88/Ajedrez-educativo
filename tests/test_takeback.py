"""
Tests del sistema de "deshacer" (takeback) y los corazones.

Regla de negocio: **un corazón por cada pulsación del botón**, nunca por jugada
deshecha. Contra un bot hay que retirar su respuesta Y la jugada propia para
devolver el turno, pero eso sigue siendo una sola pulsación y un solo corazón.
"""
import chess
import pytest

from apps.accounts.models import CustomUser
from apps.bots.models import Bot, BotProfile
from apps.games.models import Game, Move


def make_user(username):
    return CustomUser.objects.create_user(
        username=username, password='password123', role=CustomUser.Role.STUDENT
    )


def make_bot(name='Bot Test'):
    return Bot(
        user=Bot.create_bot_account(name),
        display_name=name,
        category=Bot.Category.BEGINNER,
        order=1,
        displayed_elo=700,
        profile=BotProfile.objects.create(
            name=f'Perfil {name}', engine_depth=2, move_time_ms=100,
            skill_level=3, multipv=1, error_probability=0,
        ),
        is_active=True,
    )


def nueva_partida(human, bot, con_corazones=7):
    return Game.objects.create(
        white_player=human,
        black_player=bot.user,
        status=Game.Status.IN_PROGRESS,
        turn=Game.Turn.WHITE,
        vs_bot=True,
        is_competitive=False,
        max_takebacks=con_corazones,
        takebacks_left=con_corazones,
    )


def jugar(game, jugador, uci):
    """Registra una jugada como lo haría el WebSocket."""
    board = chess.Board(game.fen_current)
    mov = chess.Move.from_uci(uci)
    san = board.san(mov)          # SAN ANTES de hacer la jugada
    board.push(mov)
    ply = game.moves.count() + 1
    Move.objects.create(
        game=game, player=jugador, uci=uci, san=san,
        ply=ply, fen_after=board.fen(),
    )
    game.fen_current = board.fen()
    game.turn = (
        Game.Turn.BLACK if board.turn == chess.WHITE else Game.Turn.WHITE
    )
    game.save()
    return board


# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestUnCorazonPorPulsacion:

    def test_una_pulsacion_cuesta_un_solo_corazon(self):
        """
        Regresión: la pulsación llamaba a `apply_takeback()` dos veces (respuesta
        del bot + jugada propia) y cada llamada descontaba un corazón, así que
        un clic gastaba 2.
        """
        human = make_user('alumno1')
        bot = make_bot()
        game = nueva_partida(human, bot, con_corazones=7)

        jugar(game, human, 'e2e4')      # jugada del alumno
        jugar(game, bot.user, 'e7e5')   # respuesta del bot

        assert game.moves.count() == 2
        assert game.takebacks_left == 7

        # Una única "pulsación": deshace 2 medias jugadas, gasta 1 corazón.
        ok, err = game.apply_takeback(plies=2)

        game.refresh_from_db()
        assert ok is True and err is None
        assert game.moves.count() == 0            # se fueron ambas jugadas
        assert game.takebacks_left == 6, 'un clic debe gastar UN corazón'
        assert game.turn == Game.Turn.WHITE       # vuelve a tocarle al alumno

    def test_repetir_presiones_gasta_un_corazon_por_presion(self):
        human = make_user('alumno2')
        bot = make_bot('Bot 2')
        game = nueva_partida(human, bot, con_corazones=7)

        for _ in range(3):
            jugar(game, human, 'e2e4')
            jugar(game, bot.user, 'e7e5')
            game.apply_takeback(plies=2)
            game.refresh_from_db()

        # 3 pulsaciones = 3 corazones, no 6.
        assert game.takebacks_left == 4

    def test_una_sola_media_jugada_tambien_cuesta_un_corazon(self):
        """Si solo queda la jugada propia, se deshace y cuesta 1 corazón."""
        human = make_user('alumno3')
        bot = make_bot('Bot 3')
        game = nueva_partida(human, bot, con_corazones=7)

        jugar(game, human, 'e2e4')
        ok, _ = game.apply_takeback(plies=2)   # pide 2, solo hay 1

        game.refresh_from_db()
        assert ok is True
        assert game.moves.count() == 0
        assert game.takebacks_left == 6

    def test_sin_movimientos_no_gasta_corazon(self):
        human = make_user('alumno4')
        bot = make_bot('Bot 4')
        game = nueva_partida(human, bot, con_corazones=7)

        ok, err = game.apply_takeback(plies=2)

        game.refresh_from_db()
        assert ok is False
        assert err
        assert game.takebacks_left == 7, 'sin jugadas no debe gastar corazones'

    def test_no_deja_coraciones_negativos(self):
        human = make_user('alumno5')
        bot = make_bot('Bot 5')
        game = nueva_partida(human, bot, con_corazones=1)

        jugar(game, human, 'e2e4')
        jugar(game, bot.user, 'e7e5')
        game.apply_takeback(plies=2)
        game.refresh_from_db()

        assert game.takebacks_left == 0
        assert game.can_takeback(human.id) is False

    def test_fen_y_turno_vuelven_al_estado_correcto(self):
        human = make_user('alumno6')
        bot = make_bot('Bot 6')
        game = nueva_partida(human, bot)

        jugar(game, human, 'e2e4')
        jugar(game, bot.user, 'e7e5')
        jugar(game, human, 'g1f3')
        jugar(game, bot.user, 'b8c6')

        # Sitúa el turno tras la jugada del bot; deshacemos esas dos.
        game.refresh_from_db()
        antes_fen = game.fen_current

        ok, _ = game.apply_takeback(plies=2)
        game.refresh_from_db()

        assert ok is True
        assert game.turn == Game.Turn.WHITE          # le toca al alumno otra vez
        assert game.moves.count() == 2
        # El tablero vuelve a estar tras 1.e4 e5, no donde estaba antes.
        esperado = chess.Board()
        esperado.push_uci('e2e4')
        esperado.push_uci('e7e5')
        assert game.fen_current.split()[0] == esperado.fen().split()[0]
        assert antes_fen != game.fen_current
