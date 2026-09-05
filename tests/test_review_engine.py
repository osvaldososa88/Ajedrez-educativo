import pytest
import chess
from apps.analysis.review_engine import ReviewEngine
from apps.analysis.models import AnalysisJob, MoveAnalysis
from apps.accounts.models import CustomUser
from apps.games.models import Game, Move
from django.urls import reverse

@pytest.mark.django_db
class TestReviewEngine:

    def test_classify_opening_book(self):
        board_before = chess.Board()
        move = chess.Move.from_uci('e2e4')
        board_after = board_before.copy()
        board_after.push(move)

        code, display = ReviewEngine.classify_move(
            board_before, move, board_after,
            eval_before={'best_move_uci': 'e2e4', 'score_cp': 20},
            eval_after={'score_cp': 25},
            cp_loss=0
        )
        assert code == 'BOOK'
        assert display == 'LIBRO'

    def test_classify_best_move(self):
        board_before = chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
        move = chess.Move.from_uci('c7c5')
        board_after = board_before.copy()
        board_after.push(move)

        code, display = ReviewEngine.classify_move(
            board_before, move, board_after,
            eval_before={'best_move_uci': 'c7c5', 'score_cp': 20},
            eval_after={'score_cp': 20},
            cp_loss=0
        )
        assert code in ['BEST', 'BOOK']

    def test_classify_blunder(self):
        board_before = chess.Board("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1")
        move = chess.Move.from_uci('f7f6')
        board_after = board_before.copy()
        board_after.push(move)

        code, display = ReviewEngine.classify_move(
            board_before, move, board_after,
            eval_before={'best_move_uci': 'e7e5', 'score_cp': 30},
            eval_after={'score_cp': -350},
            cp_loss=380
        )
        assert code == 'BLUNDER'
        assert display == 'GRAN ERROR'

    def test_detect_fork(self):
        # Knight on c7 attacking King on e8 and Rook on a8
        fen_before = "r3k2r/ppp2ppp/8/8/3n4/8/PPPP1PPP/R1B1K2R b KQkq - 0 1"
        board_before = chess.Board(fen_before)
        move = chess.Move.from_uci('d4c2') # Knight to c2 attacks e1 king and a1 rook
        board_after = board_before.copy()
        board_after.push(move)

        res = ReviewEngine.analyze_move_pedagogically(
            fen_before=fen_before,
            move_uci='d4c2',
            move_san='Nc2+',
            fen_after=board_after.fen(),
            eval_before={'score_cp': 150, 'best_move_uci': 'd4c2'},
            eval_after={'score_cp': 300},
            cp_loss=0
        )
        assert res['tactical_theme'] in ['Tenedor', 'Jaque']
        assert res['classification'] in ['BEST', 'BRILLIANT', 'EXCELLENT']

    def test_summary_metrics_calculation(self):
        moves_data = [
            {'quality': 'BEST', 'cp_loss': 0},
            {'quality': 'GOOD', 'cp_loss': 40},
            {'quality': 'BOOK', 'cp_loss': 10},
            {'quality': 'INACCURACY', 'cp_loss': 90},
        ]
        metrics = ReviewEngine.compute_game_summary_metrics(moves_data)
        assert 'accuracy_white' in metrics
        assert 'accuracy_black' in metrics
        assert 'estimated_elo_white' in metrics
        assert 'estimated_elo_black' in metrics
        assert metrics['accuracy_white'] > 50
        assert metrics['estimated_elo_white'] > 800

@pytest.mark.django_db
def test_finished_game_analysis_job_creation(client):
    white = CustomUser.objects.create_user(username='player_w', password='password123')
    black = CustomUser.objects.create_user(username='player_b', password='password123')

    game = Game.objects.create(
        white_player=white,
        black_player=black,
        status=Game.Status.FINISHED,
        winner=Game.Winner.WHITE,
        finish_reason=Game.FinishReason.CHECKMATE
    )
    Move.objects.create(
        game=game,
        ply=1,
        san="e4",
        uci="e2e4",
        fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
        player=white
    )

    client.login(username='player_w', password='password123')
    url = reverse('create_game_analysis_job', kwargs={'game_id': game.id})
    response = client.get(url)

    assert response.status_code == 302
    job = AnalysisJob.objects.filter(game=game).first()
    assert job is not None
    assert job.status == AnalysisJob.Status.COMPLETED
    assert job.move_analyses.count() == 1
