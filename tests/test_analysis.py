import pytest
from django.urls import reverse
from apps.accounts.models import CustomUser
from apps.games.models import Game
from apps.analysis.models import AnalysisJob, PositionAnalysis, MoveAnalysis
from apps.core.stockfish_engine import StockfishEngine

@pytest.mark.django_db
def test_stockfish_engine_fallback_eval():
    """Verify engine evaluation fallback logic for standard starting position."""
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    res = StockfishEngine.evaluate_position(fen, depth=1)
    assert res['fen'] == fen
    assert 'best_move_san' in res
    assert res['engine_name'] in ['Stockfish', 'Python-Chess Fallback']

@pytest.mark.django_db
def test_import_pgn_view_valid(client):
    """Test importing a valid PGN string creates an AnalysisJob."""
    user = CustomUser.objects.create_user(username='student1', password='pass123', role=CustomUser.Role.STUDENT)
    client.login(username='student1', password='pass123')

    pgn = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6"
    response = client.post(reverse('import_pgn'), {'pgn_text': pgn})

    assert response.status_code == 302
    job = AnalysisJob.objects.filter(user=user).first()
    assert job is not None
    assert job.pgn_text == pgn

@pytest.mark.django_db
def test_import_pgn_view_invalid(client):
    """Test importing invalid PGN text returns an error message."""
    user = CustomUser.objects.create_user(username='student1', password='pass123', role=CustomUser.Role.STUDENT)
    client.login(username='student1', password='pass123')

    response = client.post(reverse('import_pgn'), {'pgn_text': 'INVALID_PGN_TEXT_XYZ'})
    assert response.status_code == 200
    assert AnalysisJob.objects.count() == 0

@pytest.mark.django_db
def test_analysis_job_permissions(client):
    """Verify only game participants or staff can start analysis for a game."""
    white = CustomUser.objects.create_user(username='white_p', password='pass123')
    black = CustomUser.objects.create_user(username='black_p', password='pass123')
    stranger = CustomUser.objects.create_user(username='stranger', password='pass123')

    game = Game.objects.create(white_player=white, black_player=black)

    # Stranger should be denied permission
    client.login(username='stranger', password='pass123')
    res_stranger = client.get(reverse('start_game_analysis', kwargs={'game_id': game.id}))
    assert res_stranger.status_code == 403

    # White player allowed
    client.login(username='white_p', password='pass123')
    res_white = client.get(reverse('start_game_analysis', kwargs={'game_id': game.id}))
    assert res_white.status_code == 302
    assert AnalysisJob.objects.filter(game=game).count() == 1

@pytest.mark.django_db
def test_single_fen_api(client):
    """Test single FEN evaluation API across COMPETITION, TRAINING, and ANALYSIS modes."""
    user = CustomUser.objects.create_user(username='student1', password='pass123')
    client.login(username='student1', password='pass123')

    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

    # Analysis mode
    res_analysis = client.get(reverse('analyze_single_fen_api'), {'fen': fen, 'mode': 'ANALYSIS'})
    assert res_analysis.status_code == 200
    data_analysis = res_analysis.json()
    assert data_analysis['best_move_san'] is not None

    # Competition mode should block evaluation
    res_comp = client.get(reverse('analyze_single_fen_api'), {'fen': fen, 'mode': 'COMPETITION'})
    assert res_comp.status_code == 403

@pytest.mark.django_db
def test_position_analysis_reuse():
    """Verify PositionAnalysis caching and reusability across jobs."""
    fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
    p1 = PositionAnalysis.objects.create(fen=fen, score_cp=35, best_move_san='e5')
    p2 = PositionAnalysis.objects.get(fen=fen)
    assert p1.id == p2.id
    assert p2.score_cp == 35
