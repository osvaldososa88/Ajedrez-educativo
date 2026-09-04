import chess
import pytest
from django.urls import reverse
from apps.accounts.models import CustomUser
from apps.games.models import Game
from apps.analysis.models import AnalysisJob, MoveAnalysis
from apps.training.models import Puzzle, PuzzleAttempt, UserTrainingStats
from apps.personalization.models import DetectedGameError
from apps.personalization.error_classifier import classify_error
from apps.personalization.services import ErrorDetectionService, PersonalizationError
from apps.personalization.profile import StudentProfileService
from apps.personalization.recommendations import RecommendationService

OPENING_FEN = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
PAWN_ENDGAME_FEN = "8/8/8/4k3/8/4K3/4P3/8 w - - 0 40"
ROOK_ENDGAME_FEN = "8/8/8/4k3/8/4K3/4P3/3R4 w - - 0 40"
MIDDLEGAME_FEN = "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 4 15"


def make_user(username, role=CustomUser.Role.STUDENT):
    return CustomUser.objects.create_user(username=username, password='password123', role=role)


def make_game(white, black):
    return Game.objects.create(white_player=white, black_player=black, status=Game.Status.FINISHED)


def make_job(game, requester):
    return AnalysisJob.objects.create(game=game, user=requester, status=AnalysisJob.Status.COMPLETED)


def make_move_analysis(job, ply, fen_before, move_uci, move_san, quality):
    board = chess.Board(fen_before)
    board.push(chess.Move.from_uci(move_uci))
    return MoveAnalysis.objects.create(
        job=job, ply=ply, move_san=move_san, move_uci=move_uci,
        fen_before=fen_before, fen_after=board.fen(), quality=quality,
    )


# --- Error classifier (rule-based, unit level with contrived engine evals) ---

@pytest.mark.django_db
def test_classifier_detects_opening_phase():
    job = make_job(make_game(make_user('w1'), make_user('b1')), make_user('teacher1', role=CustomUser.Role.TEACHER))
    ma = make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)
    eval_before = {'best_move_uci': 'g1f3', 'best_move_san': 'Nf3', 'score_cp': 20, 'mate_in': None}

    result = classify_error(OPENING_FEN, ma, eval_before)
    assert result['category'] == Puzzle.Category.OPENINGS
    assert result['theme'] == Puzzle.Theme.OPENING_REPERTOIRE


@pytest.mark.django_db
def test_classifier_detects_pawn_endgame():
    job = make_job(make_game(make_user('w1'), make_user('b1')), make_user('teacher1', role=CustomUser.Role.TEACHER))
    ma = make_move_analysis(job, 79, PAWN_ENDGAME_FEN, 'e3d3', 'Kd3', MoveAnalysis.Quality.BLUNDER)
    eval_before = {'best_move_uci': 'e3f4', 'best_move_san': 'Kf4', 'score_cp': 300, 'mate_in': None}

    result = classify_error(PAWN_ENDGAME_FEN, ma, eval_before)
    assert result['category'] == Puzzle.Category.ENDGAME
    assert result['theme'] == Puzzle.Theme.PAWN_ENDGAME


@pytest.mark.django_db
def test_classifier_detects_rook_endgame():
    job = make_job(make_game(make_user('w1'), make_user('b1')), make_user('teacher1', role=CustomUser.Role.TEACHER))
    ma = make_move_analysis(job, 79, ROOK_ENDGAME_FEN, 'd1d5', 'Rd5+', MoveAnalysis.Quality.MISTAKE)
    eval_before = {'best_move_uci': 'd1a1', 'best_move_san': 'Ra1', 'score_cp': 300, 'mate_in': None}

    result = classify_error(ROOK_ENDGAME_FEN, ma, eval_before)
    assert result['category'] == Puzzle.Category.ENDGAME
    assert result['theme'] == Puzzle.Theme.ROOK_ENDGAME


@pytest.mark.django_db
def test_classifier_detects_missed_forced_mate():
    job = make_job(make_game(make_user('w1'), make_user('b1')), make_user('teacher1', role=CustomUser.Role.TEACHER))
    ma = make_move_analysis(job, 15, MIDDLEGAME_FEN, 'f3g5', 'Ng5', MoveAnalysis.Quality.BLUNDER)
    eval_before = {'best_move_uci': 'c4f7', 'best_move_san': 'Bxf7+', 'score_cp': None, 'mate_in': 3}

    result = classify_error(MIDDLEGAME_FEN, ma, eval_before)
    assert result['category'] == Puzzle.Category.TACTICS
    assert result['theme'] == Puzzle.Theme.MATE
    assert result['difficulty'] == Puzzle.Difficulty.BEGINNER


@pytest.mark.django_db
def test_classifier_defaults_to_generic_tactics_in_middlegame():
    job = make_job(make_game(make_user('w1'), make_user('b1')), make_user('teacher1', role=CustomUser.Role.TEACHER))
    ma = make_move_analysis(job, 15, MIDDLEGAME_FEN, 'f3g5', 'Ng5', MoveAnalysis.Quality.MISTAKE)
    eval_before = {'best_move_uci': 'c3d5', 'best_move_san': 'Nd5', 'score_cp': 50, 'mate_in': None}

    result = classify_error(MIDDLEGAME_FEN, ma, eval_before)
    assert result['category'] == Puzzle.Category.TACTICS
    assert result['theme'] == Puzzle.Theme.BEST_CONTINUATION


@pytest.mark.django_db
def test_classifier_blunder_is_graded_beginner_difficulty():
    job = make_job(make_game(make_user('w1'), make_user('b1')), make_user('teacher1', role=CustomUser.Role.TEACHER))
    ma = make_move_analysis(job, 15, MIDDLEGAME_FEN, 'f3g5', 'Ng5', MoveAnalysis.Quality.BLUNDER)
    eval_before = {'best_move_uci': 'c3d5', 'best_move_san': 'Nd5', 'score_cp': 50, 'mate_in': None}

    result = classify_error(MIDDLEGAME_FEN, ma, eval_before)
    assert result['difficulty'] == Puzzle.Difficulty.BEGINNER


# --- ErrorDetectionService: game -> training conversion ---

@pytest.mark.django_db
def test_generate_from_job_only_converts_significant_mistakes():
    white, black = make_user('white1'), make_user('black1')
    game = make_game(white, black)
    job = make_job(game, white)

    make_move_analysis(job, 1, chess.STARTING_FEN, 'e2e4', 'e4', MoveAnalysis.Quality.BEST)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)

    created = ErrorDetectionService.generate_from_job(job)
    assert len(created) == 1
    assert DetectedGameError.objects.count() == 1


@pytest.mark.django_db
def test_generate_from_job_attributes_error_to_correct_player_by_ply():
    white, black = make_user('white1'), make_user('black1')
    game = make_game(white, black)
    job = make_job(game, white)

    # ply 3 is odd -> White's move
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)
    created = ErrorDetectionService.generate_from_job(job)
    assert created[0].student == white


@pytest.mark.django_db
def test_generate_from_job_attributes_black_move_correctly():
    white, black = make_user('white1'), make_user('black1')
    game = make_game(white, black)
    job = make_job(game, white)

    # ply 4 is even -> Black's move
    board_after_g1h3 = chess.Board(OPENING_FEN)
    board_after_g1h3.push_uci('g1h3')
    fen_before_black = board_after_g1h3.fen()
    make_move_analysis(job, 4, fen_before_black, 'd8h4', 'Qh4', MoveAnalysis.Quality.BLUNDER)

    created = ErrorDetectionService.generate_from_job(job)
    assert created[0].student == black


@pytest.mark.django_db
def test_generate_from_job_creates_private_draft_puzzle():
    white, black = make_user('white1'), make_user('black1')
    game = make_game(white, black)
    job = make_job(game, white)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)

    created = ErrorDetectionService.generate_from_job(job)
    puzzle = created[0].generated_puzzle
    assert puzzle is not None
    assert puzzle.author == white
    assert puzzle.status == Puzzle.Status.DRAFT
    assert puzzle.initial_fen == OPENING_FEN
    assert puzzle.objective == Puzzle.Objective.BEST_CONTINUATION
    assert len(puzzle.solution_moves) == 1
    assert len(puzzle.hints) >= 1
    # The solution must never be spoiled in the visible description.
    assert puzzle.solution_moves[0] not in puzzle.description


@pytest.mark.django_db
def test_generate_from_job_is_idempotent():
    white, black = make_user('white1'), make_user('black1')
    game = make_game(white, black)
    job = make_job(game, white)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)

    first = ErrorDetectionService.generate_from_job(job)
    second = ErrorDetectionService.generate_from_job(job)
    assert len(first) == 1
    assert len(second) == 0
    assert DetectedGameError.objects.count() == 1


@pytest.mark.django_db
def test_generate_from_job_requires_completed_status():
    white, black = make_user('white1'), make_user('black1')
    game = make_game(white, black)
    job = AnalysisJob.objects.create(game=game, user=white, status=AnalysisJob.Status.PROCESSING)

    with pytest.raises(PersonalizationError):
        ErrorDetectionService.generate_from_job(job)


@pytest.mark.django_db
def test_generate_from_job_requires_linked_game():
    white = make_user('white1')
    job = AnalysisJob.objects.create(user=white, status=AnalysisJob.Status.COMPLETED, pgn_text="1. e4 e5")

    with pytest.raises(PersonalizationError):
        ErrorDetectionService.generate_from_job(job)


# --- Generated puzzle reuses existing solving flow (no answer leaked, retries allowed) ---

@pytest.mark.django_db
def test_generated_puzzle_is_solvable_via_existing_training_flow(client):
    white, black = make_user('white1'), make_user('black1')
    game = make_game(white, black)
    job = make_job(game, white)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)
    error = ErrorDetectionService.generate_from_job(job)[0]
    puzzle = error.generated_puzzle

    client.login(username='white1', password='password123')
    response = client.get(reverse('puzzle_detail', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200  # author can view own DRAFT puzzle


@pytest.mark.django_db
def test_generated_puzzle_is_private_to_the_student():
    white, black = make_user('white1'), make_user('black1')
    stranger = make_user('stranger1')
    game = make_game(white, black)
    job = make_job(game, white)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)
    error = ErrorDetectionService.generate_from_job(job)[0]
    puzzle = error.generated_puzzle

    assert not Puzzle.objects.filter(id=puzzle.id, status=Puzzle.Status.PUBLISHED).exists()
    assert puzzle.author != stranger


# --- View permissions ---

@pytest.mark.django_db
def test_participant_can_generate_training_from_job(client):
    white, black = make_user('white1'), make_user('black1')
    game = make_game(white, black)
    job = make_job(game, white)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)

    client.login(username='white1', password='password123')
    response = client.post(reverse('personalization_generate_from_job', kwargs={'job_id': job.id}))
    assert response.status_code == 302
    assert DetectedGameError.objects.count() == 1


@pytest.mark.django_db
def test_stranger_cannot_generate_training_from_job(client):
    white, black = make_user('white1'), make_user('black1')
    stranger = make_user('stranger1')
    game = make_game(white, black)
    job = make_job(game, white)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)

    client.login(username='stranger1', password='password123')
    response = client.post(reverse('personalization_generate_from_job', kwargs={'job_id': job.id}))
    assert response.status_code == 302  # redirected back with an error message
    assert DetectedGameError.objects.count() == 0


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse('personalization_dashboard'))
    assert response.status_code == 302


@pytest.mark.django_db
def test_dashboard_only_shows_requesting_users_data(client):
    student = make_user('estudiante1')
    other = make_user('estudiante2')
    game = make_game(student, other)
    job = make_job(game, student)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)
    ErrorDetectionService.generate_from_job(job)

    client.login(username='estudiante2', password='password123')
    response = client.get(reverse('personalization_dashboard'))
    assert response.status_code == 200
    # estudiante2 made no errors themself (ply 3 = white = estudiante1), so no recent_errors for them.
    profile = {row['category']: row for row in response.context['profile']}
    assert profile[Puzzle.Category.OPENINGS]['recent_errors'] == 0


@pytest.mark.django_db
def test_my_errors_view_scoped_to_own_user(client):
    student = make_user('estudiante1')
    other = make_user('estudiante2')
    game = make_game(student, other)
    job = make_job(game, student)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)
    ErrorDetectionService.generate_from_job(job)

    client.login(username='estudiante2', password='password123')
    response = client.get(reverse('personalization_my_errors'))
    assert response.status_code == 200
    assert list(response.context['errors']) == []


# --- Student profile indicators ---

@pytest.mark.django_db
def test_profile_indicator_none_without_any_data():
    student = make_user('estudiante1')
    profile = StudentProfileService.compute_profile(student)
    tactics_row = next(row for row in profile if row['category'] == Puzzle.Category.TACTICS)
    assert tactics_row['score'] is None


@pytest.mark.django_db
def test_profile_indicator_uses_success_rate_when_no_errors():
    student = make_user('estudiante1')
    UserTrainingStats.objects.create(
        user=student, category=Puzzle.Category.TACTICS, theme=Puzzle.Theme.FORK,
        total_attempts=10, successful_attempts=8,
    )
    profile = StudentProfileService.compute_profile(student)
    tactics_row = next(row for row in profile if row['category'] == Puzzle.Category.TACTICS)
    assert tactics_row['score'] == 80.0


@pytest.mark.django_db
def test_profile_indicator_penalizes_recent_errors():
    white, black = make_user('estudiante1'), make_user('estudiante2')
    game = make_game(white, black)
    job = make_job(game, white)
    make_move_analysis(job, 15, MIDDLEGAME_FEN, 'f3g5', 'Ng5', MoveAnalysis.Quality.MISTAKE)
    ErrorDetectionService.generate_from_job(job)

    UserTrainingStats.objects.create(
        user=white, category=Puzzle.Category.TACTICS, theme=Puzzle.Theme.FORK,
        total_attempts=10, successful_attempts=8,
    )
    profile = StudentProfileService.compute_profile(white)
    tactics_row = next(row for row in profile if row['category'] == Puzzle.Category.TACTICS)
    assert tactics_row['score'] == 75.0  # 80 - (1 error * 5 penalty)
    assert tactics_row['recent_errors'] == 1


@pytest.mark.django_db
def test_profile_score_never_goes_below_zero():
    student = make_user('estudiante1')
    UserTrainingStats.objects.create(
        user=student, category=Puzzle.Category.TACTICS, theme=Puzzle.Theme.FORK,
        total_attempts=10, successful_attempts=0,
    )
    for i in range(10):
        white, black = student, make_user(f'opp{i}')
        game = make_game(white, black)
        job = make_job(game, white)
        make_move_analysis(job, 15, MIDDLEGAME_FEN, 'f3g5', 'Ng5', MoveAnalysis.Quality.MISTAKE)
        ErrorDetectionService.generate_from_job(job)

    profile = StudentProfileService.compute_profile(student)
    tactics_row = next(row for row in profile if row['category'] == Puzzle.Category.TACTICS)
    assert tactics_row['score'] == 0.0


# --- Recommendations ---

@pytest.mark.django_db
def test_recommendations_empty_without_data():
    student = make_user('estudiante1')
    recommendations = RecommendationService.build_weekly_recommendations(student)
    assert recommendations == []


@pytest.mark.django_db
def test_recommendations_suggest_weak_theme_puzzles():
    student = make_user('estudiante1')
    author = make_user('docente1', role=CustomUser.Role.TEACHER)
    UserTrainingStats.objects.create(
        user=student, category=Puzzle.Category.TACTICS, theme=Puzzle.Theme.PIN,
        total_attempts=4, successful_attempts=1,  # 25% success rate -> weak
    )
    for i in range(3):
        Puzzle.objects.create(
            title=f"Clavada {i}", author=author, initial_fen=chess.STARTING_FEN,
            category=Puzzle.Category.TACTICS, theme=Puzzle.Theme.PIN,
            solution_moves=["e2e4"], status=Puzzle.Status.PUBLISHED,
        )

    recommendations = RecommendationService.build_weekly_recommendations(student)
    assert len(recommendations) == 1
    assert recommendations[0]['count'] == 3
    assert Puzzle.Theme.PIN.label in recommendations[0]['reason'] or 'Clavada' in recommendations[0]['reason']


@pytest.mark.django_db
def test_recommendations_exclude_already_solved_puzzles():
    student = make_user('estudiante1')
    author = make_user('docente1', role=CustomUser.Role.TEACHER)
    UserTrainingStats.objects.create(
        user=student, category=Puzzle.Category.TACTICS, theme=Puzzle.Theme.PIN,
        total_attempts=4, successful_attempts=1,
    )
    puzzle = Puzzle.objects.create(
        title="Clavada única", author=author, initial_fen=chess.STARTING_FEN,
        category=Puzzle.Category.TACTICS, theme=Puzzle.Theme.PIN,
        solution_moves=["e2e4"], status=Puzzle.Status.PUBLISHED,
    )
    PuzzleAttempt.objects.create(user=student, puzzle=puzzle, solved=True)

    recommendations = RecommendationService.build_weekly_recommendations(student)
    assert recommendations == []  # only solved puzzle was available, nothing left to suggest


@pytest.mark.django_db
def test_recommendations_include_own_error_puzzles_by_category():
    student = make_user('estudiante1')
    opponent = make_user('estudiante2')
    game = make_game(student, opponent)
    job = make_job(game, student)
    make_move_analysis(job, 15, MIDDLEGAME_FEN, 'f3g5', 'Ng5', MoveAnalysis.Quality.MISTAKE)
    ErrorDetectionService.generate_from_job(job)

    recommendations = RecommendationService.build_weekly_recommendations(student)
    assert len(recommendations) == 1
    assert recommendations[0]['category'] == Puzzle.Category.TACTICS


@pytest.mark.django_db
def test_recommendations_opening_items_use_dedicated_wording():
    student = make_user('estudiante1')
    opponent = make_user('estudiante2')
    game = make_game(student, opponent)
    job = make_job(game, student)
    make_move_analysis(job, 3, OPENING_FEN, 'g1h3', 'Nh3', MoveAnalysis.Quality.MISTAKE)
    ErrorDetectionService.generate_from_job(job)

    recommendations = RecommendationService.build_weekly_recommendations(student)
    opening_items = [r for r in recommendations if r['category'] == Puzzle.Category.OPENINGS]
    assert len(opening_items) == 1
    assert 'apertura' in opening_items[0]['reason']
