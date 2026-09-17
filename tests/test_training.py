import json
import chess
import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from apps.accounts.models import CustomUser
from apps.training.models import Puzzle, PuzzleAttempt, UserTrainingStats
from apps.training.services import PuzzleService


def make_user(username, role=CustomUser.Role.STUDENT):
    return CustomUser.objects.create_user(username=username, password='password123', role=role)


def make_mate_in_1_puzzle(author=None, status=Puzzle.Status.PUBLISHED):
    # Fool's mate position: Black to move plays Qh4# against White.
    fen = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"
    return Puzzle.objects.create(
        title="Mate en 1 - Ataque de Legal",
        description="Encuentra el jaque mate en una jugada.",
        author=author,
        initial_fen=fen,
        side_to_move=Puzzle.SideToMove.BLACK,
        category=Puzzle.Category.TACTICS,
        theme=Puzzle.Theme.MATE,
        difficulty=Puzzle.Difficulty.BEGINNER,
        objective=Puzzle.Objective.FIND_MOVE,
        solution_moves=["h4f2"],
        hints=["Busca un jaque que no pueda ser bloqueado.", "La dama puede llegar a f2."],
        status=status,
    )


# --- Model / position validation tests ---

@pytest.mark.django_db
def test_valid_puzzle_position_is_saved():
    puzzle = make_mate_in_1_puzzle()
    assert puzzle.pk is not None
    board = chess.Board(puzzle.initial_fen)
    assert board.is_valid()


@pytest.mark.django_db
def test_invalid_fen_string_is_rejected():
    puzzle = Puzzle(
        title="Posición inválida",
        initial_fen="esto-no-es-un-fen",
        solution_moves=["e2e4"],
    )
    with pytest.raises(ValidationError):
        puzzle.save()


@pytest.mark.django_db
def test_illegal_chess_position_is_rejected():
    # Two white kings: syntactically FEN-like but not a legal chess position.
    puzzle = Puzzle(
        title="Dos reyes blancos",
        initial_fen="8/8/8/4K3/8/8/4K3/8 w - - 0 1",
        solution_moves=["e5e6"],
    )
    with pytest.raises(ValidationError):
        puzzle.save()


# --- Solution / attempt verification tests ---

@pytest.mark.django_db
def test_verify_move_correct_and_completed():
    puzzle = make_mate_in_1_puzzle()
    result = PuzzleService.verify_move(puzzle, 0, "h4f2")
    assert result['is_correct'] is True
    assert result['completed'] is True


@pytest.mark.django_db
def test_verify_move_incorrect_does_not_reveal_solution():
    puzzle = make_mate_in_1_puzzle()
    result = PuzzleService.verify_move(puzzle, 0, "h4h5")
    assert result['is_correct'] is False
    assert result['completed'] is False
    assert "h4f2" not in result['message']


@pytest.mark.django_db
def test_verify_move_accepts_listed_variation():
    puzzle = make_mate_in_1_puzzle()
    puzzle.variations_json = {"0": ["h4g4"]}
    puzzle.save()
    result = PuzzleService.verify_move(puzzle, 0, "h4g4")
    assert result['is_correct'] is True


@pytest.mark.django_db
def test_verify_move_multi_ply_sequence_advances_and_returns_computer_reply():
    puzzle = make_mate_in_1_puzzle()
    puzzle.solution_moves = ["e2e4", "e7e5", "g1f3"]
    puzzle.save()

    result = PuzzleService.verify_move(puzzle, 0, "e2e4")
    assert result['is_correct'] is True
    assert result['completed'] is False
    assert result['computer_counter_move'] == "e7e5"
    assert result['next_ply_index'] == 2

    result2 = PuzzleService.verify_move(puzzle, 2, "g1f3")
    assert result2['is_correct'] is True
    assert result2['completed'] is True


@pytest.mark.django_db
def test_verify_move_after_completion_returns_completed_message():
    puzzle = make_mate_in_1_puzzle()
    result = PuzzleService.verify_move(puzzle, 1, "anything")
    assert result['completed'] is True
    assert result['is_correct'] is False


# --- Attempt recording / scoring tests ---

@pytest.mark.django_db
def test_record_attempt_creates_log_and_updates_stats():
    user = make_user('estudiante1')
    puzzle = make_mate_in_1_puzzle()

    PuzzleService.record_attempt(user, puzzle, solved=True, time_taken_seconds=42, hints_used=1, attempts_count=2)

    attempt = PuzzleAttempt.objects.get(user=user, puzzle=puzzle)
    assert attempt.solved is True
    assert attempt.time_taken_seconds == 42
    assert attempt.hints_used == 1
    assert attempt.attempts_count == 2

    stats = UserTrainingStats.objects.get(user=user, category=puzzle.category, theme=puzzle.theme)
    assert stats.total_attempts == 1
    assert stats.successful_attempts == 1
    assert stats.success_rate == 100.0


@pytest.mark.django_db
def test_stats_detect_weak_theme_after_repeated_failures():
    user = make_user('estudiante1')
    puzzle = make_mate_in_1_puzzle()

    PuzzleService.record_attempt(user, puzzle, solved=False, time_taken_seconds=10)
    PuzzleService.record_attempt(user, puzzle, solved=False, time_taken_seconds=10)
    PuzzleService.record_attempt(user, puzzle, solved=True, time_taken_seconds=10)

    stats = UserTrainingStats.objects.get(user=user, category=puzzle.category, theme=puzzle.theme)
    assert stats.total_attempts == 3
    assert stats.successful_attempts == 1
    assert stats.success_rate < 50.0  # weak theme threshold used by dashboard view


# --- Hint API tests ---

@pytest.mark.django_db
def test_hint_api_returns_progressive_hints(client):
    user = make_user('estudiante1')
    puzzle = make_mate_in_1_puzzle()
    client.login(username='estudiante1', password='password123')

    response = client.get(reverse('get_puzzle_hint_api', kwargs={'puzzle_id': puzzle.id}), {'index': 0})
    assert response.status_code == 200
    data = response.json()
    assert data['hint_text'] == puzzle.hints[0]

    response2 = client.get(reverse('get_puzzle_hint_api', kwargs={'puzzle_id': puzzle.id}), {'index': 1})
    assert response2.json()['hint_text'] == puzzle.hints[1]


@pytest.mark.django_db
def test_hint_api_out_of_range_returns_404(client):
    user = make_user('estudiante1')
    puzzle = make_mate_in_1_puzzle()
    client.login(username='estudiante1', password='password123')

    response = client.get(reverse('get_puzzle_hint_api', kwargs={'puzzle_id': puzzle.id}), {'index': 99})
    assert response.status_code == 404


# --- Submit move API tests (full request/response flow) ---

@pytest.mark.django_db
def test_submit_move_api_correct_move_records_attempt(client):
    user = make_user('estudiante1')
    puzzle = make_mate_in_1_puzzle()
    client.login(username='estudiante1', password='password123')

    response = client.post(
        reverse('submit_puzzle_move_api', kwargs={'puzzle_id': puzzle.id}),
        data=json.dumps({'ply_index': 0, 'uci_move': 'h4f2', 'time_taken_seconds': 5}),
        content_type='application/json'
    )
    assert response.status_code == 200
    data = response.json()
    assert data['is_correct'] is True
    assert data['completed'] is True

    assert PuzzleAttempt.objects.filter(user=user, puzzle=puzzle, solved=True).exists()


@pytest.mark.django_db
def test_submit_move_api_requires_authentication(client):
    puzzle = make_mate_in_1_puzzle()
    response = client.post(
        reverse('submit_puzzle_move_api', kwargs={'puzzle_id': puzzle.id}),
        data=json.dumps({'ply_index': 0, 'uci_move': 'h4f2'}),
        content_type='application/json'
    )
    assert response.status_code == 302  # redirected to login


@pytest.mark.django_db
def test_submit_move_api_rejects_get(client):
    user = make_user('estudiante1')
    puzzle = make_mate_in_1_puzzle()
    client.login(username='estudiante1', password='password123')

    response = client.get(reverse('submit_puzzle_move_api', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 405


# --- Permission tests ---

@pytest.mark.django_db
def test_draft_puzzle_hidden_from_students_in_dashboard(client):
    student = make_user('estudiante1')
    draft_puzzle = make_mate_in_1_puzzle(status=Puzzle.Status.DRAFT)

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('training_dashboard'))
    assert response.status_code == 200
    assert draft_puzzle not in response.context['puzzles']


@pytest.mark.django_db
def test_draft_puzzle_detail_forbidden_for_student(client):
    student = make_user('estudiante1')
    draft_puzzle = make_mate_in_1_puzzle(status=Puzzle.Status.DRAFT)

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('puzzle_detail', kwargs={'puzzle_id': draft_puzzle.id}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_draft_puzzle_detail_visible_for_teacher(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    draft_puzzle = make_mate_in_1_puzzle(status=Puzzle.Status.DRAFT)

    client.login(username='docente1', password='password123')
    response = client.get(reverse('puzzle_detail', kwargs={'puzzle_id': draft_puzzle.id}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_training_dashboard_requires_login(client):
    response = client.get(reverse('training_dashboard'))
    assert response.status_code == 302
# ============================================================================
# PROBLEMAS POR OBJETIVO (OBJECTIVE)
# Validación dinámica: NO se exige secuencia fija; se evalúa el estado del
# tablero (dar jaque mate, etc.). El estudiante puede llegar por distintos
# caminos y sin límite artificial de movimientos si así se configura.
# ============================================================================

from apps.training.services import ObjectivePuzzleEngine  # noqa: E402


def make_objective_checkmate_puzzle(author=None, status=Puzzle.Status.PUBLISHED, max_moves=0):
    """Problema abierto con mate en 1: blancas mueven y b1b7 (o b1b8) da mate.

    Posición: k a8, K c7, Q b1. La dama da mate moviendo a b7/b8
    (controla a7, b8 y el rey cubre el resto de escapes).
    """
    return Puzzle.objects.create(
        title="Jaque mate abierto",
        description="Da jaque mate. Hay varios caminos válidos.",
        author=author,
        initial_fen="k7/2K5/8/8/8/8/8/1Q6 w - - 0 1",
        side_to_move=Puzzle.SideToMove.WHITE,
        category=Puzzle.Category.TACTICS,
        theme=Puzzle.Theme.MATE,
        difficulty=Puzzle.Difficulty.BEGINNER,
        objective=Puzzle.Objective.WIN,
        puzzle_type=Puzzle.PuzzleType.OBJECTIVE,
        objective_type=Puzzle.ObjectiveType.CHECKMATE,
        max_moves=max_moves,
        status=status,
    )


@pytest.mark.django_db
def test_objective_puzzle_no_solution_sequence_required():
    """Un problema por objetivo NO exige `solution_moves` (no hay secuencia)."""
    puzzle = make_objective_checkmate_puzzle()
    assert puzzle.solution_moves == []  # sin secuencia fija
    # La validación de publicación acepta problemas OBJECTIVE sin secuencia.
    errors = __import__('apps.training.services', fromlist=['PuzzleValidationService']).PuzzleValidationService.validate_for_submission(puzzle)
    assert errors == []


@pytest.mark.django_db
def test_objective_normal_move_stays_in_progress():
    """Una jugada que NO da mate NO resuelve el problema."""
    user = make_user('obj_normal')
    puzzle = make_objective_checkmate_puzzle()
    attempt = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)

    result = ObjectivePuzzleEngine.apply_human_move(puzzle, attempt, "c7d8")
    assert result['outcome'] == ObjectivePuzzleEngine.OUTCOME_IN_PROGRESS
    assert result['solved'] is False
    assert attempt.status == PuzzleAttempt.Status.IN_PROGRESS

@pytest.mark.django_db
def test_objective_checkmate_move_marks_solved():
    """Dar jaque mate al defensor resuelve el problema (dinámicamente)."""
    user = make_user('obj_mate')
    puzzle = make_objective_checkmate_puzzle()
    attempt = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)

    result = ObjectivePuzzleEngine.apply_human_move(puzzle, attempt, "b1b7")
    assert result['outcome'] == ObjectivePuzzleEngine.OUTCOME_SUCCESS
    assert result['solved'] is True
    assert attempt.status == PuzzleAttempt.Status.COMPLETED
    assert attempt.solved is True
    assert 'jaque mate' in attempt.end_message.lower()


@pytest.mark.django_db
def test_objective_different_valid_solutions_accepted():
    """No importa el camino: dos mates distintos resuelven igual."""
    user = make_user('obj_variantes')
    puzzle = make_objective_checkmate_puzzle()

    # Camino A
    PuzzleAttempt.objects.filter(user=user, puzzle=puzzle).delete()
    att_a = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)
    ra = ObjectivePuzzleEngine.apply_human_move(puzzle, att_a, "b1b8")
    assert ra['outcome'] == ObjectivePuzzleEngine.OUTCOME_SUCCESS

    # Camino B (otra jugada que también da mate)
    PuzzleAttempt.objects.filter(user=user, puzzle=puzzle).delete()
    att_b = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)
    rb = ObjectivePuzzleEngine.apply_human_move(puzzle, att_b, "b1b7")
    assert rb['outcome'] == ObjectivePuzzleEngine.OUTCOME_SUCCESS


@pytest.mark.django_db
def test_objective_no_move_limit_when_max_moves_zero():
    """Con max_moves=0 NO hay límite artificial de movimientos."""
    user = make_user('obj_sinlimite')
    puzzle = make_objective_checkmate_puzzle(max_moves=0)
    attempt = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)

    # Varias jugadas legales (sin dar mate) desde la posición resultante:
    # el problema sigue en progreso y no hay límite artificial.
    current_board = chess.Board(puzzle.initial_fen)
    for _ in range(3):
        legales = [m.uci() for m in current_board.legal_moves]
        # elegir una jugada humana que no dé mate
        uci = None
        for cand in legales:
            nb = current_board.copy()
            nb.push(chess.Move.from_uci(cand))
            if not nb.is_checkmate():
                uci = cand
                break
        assert uci is not None, 'no hay jugadas no-mate disponibles'
        result = ObjectivePuzzleEngine.apply_human_move(puzzle, attempt, uci)
        assert result['outcome'] == ObjectivePuzzleEngine.OUTCOME_IN_PROGRESS, uci
        # sincronizar con la posición que devolvió el servidor (humano + defensor)
        current_board = chess.Board(result['fen'])
    assert attempt.human_moves_count == 3
    assert result['max_moves'] == 0


@pytest.mark.django_db
def test_objective_move_limit_is_respected_when_set():
    """Si el creador configura un límite, se respeta tras agotarlo."""
    user = make_user('obj_limite')
    puzzle = make_objective_checkmate_puzzle(max_moves=1)
    attempt = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)

    result = ObjectivePuzzleEngine.apply_human_move(puzzle, attempt, "c7d8")
    assert result['outcome'] == ObjectivePuzzleEngine.OUTCOME_FAILED
    assert result['solved'] is False
    assert attempt.status == PuzzleAttempt.Status.COMPLETED
    assert 'límite' in attempt.end_message.lower()


@pytest.mark.django_db
def test_objective_reset_allows_retry():
    """Tras reiniciar (borrar intentos) se puede volver a intentar limpio."""
    user = make_user('obj_reset')
    puzzle = make_objective_checkmate_puzzle()

    # Primer intento: mate -> resuelto
    att = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)
    r = ObjectivePuzzleEngine.apply_human_move(puzzle, att, "b1b7")
    assert r['outcome'] == ObjectivePuzzleEngine.OUTCOME_SUCCESS

    # Reset: se eliminan los intentos -> nuevo intento desde el inicio
    PuzzleAttempt.objects.filter(user=user, puzzle=puzzle).delete()
    att2 = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)
    r2 = ObjectivePuzzleEngine.apply_human_move(puzzle, att2, "c7d8")
    assert r2['outcome'] == ObjectivePuzzleEngine.OUTCOME_IN_PROGRESS
    assert att2.human_moves_count == 1
    assert att2.status == PuzzleAttempt.Status.IN_PROGRESS