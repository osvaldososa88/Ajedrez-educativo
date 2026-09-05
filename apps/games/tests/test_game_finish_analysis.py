import pytest
from django.urls import reverse
from apps.accounts.models import CustomUser
from apps.games.models import Game, Move
from apps.analysis.models import AnalysisJob

@pytest.mark.django_db
class TestFinishedGameAnalysis:
    @pytest.fixture(autouse=True)
    def setup_users(self):
        self.white = CustomUser.objects.create_user(username='white_player', password='password123', role='STUDENT')
        self.black = CustomUser.objects.create_user(username='black_player', password='password123', role='STUDENT')
        self.outsider = CustomUser.objects.create_user(username='outsider', password='password123', role='STUDENT')
        self.teacher = CustomUser.objects.create_user(username='teacher', password='password123', role='TEACHER')

    def create_finished_game(self, winner=Game.Winner.WHITE, finish_reason=Game.FinishReason.CHECKMATE):
        game = Game.objects.create(
            white_player=self.white,
            black_player=self.black,
            status=Game.Status.FINISHED,
            winner=winner,
            finish_reason=finish_reason,
            fen_current="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
        )
        Move.objects.create(
            game=game,
            ply=1,
            san="e4",
            uci="e2e4",
            fen_after="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
            player=self.white
        )
        return game

    def test_analysis_access_after_checkmate(self, client):
        game = self.create_finished_game(Game.Winner.WHITE, Game.FinishReason.CHECKMATE)
        client.login(username='white_player', password='password123')

        url = reverse('create_game_analysis_job', kwargs={'game_id': game.id})
        response = client.get(url)

        assert response.status_code == 302
        assert 'analysis' in response.url
        assert AnalysisJob.objects.filter(game=game).exists()

    def test_analysis_access_after_draw(self, client):
        game = self.create_finished_game(Game.Winner.DRAW, Game.FinishReason.AGREEMENT)
        client.login(username='black_player', password='password123')

        url = reverse('create_game_analysis_job', kwargs={'game_id': game.id})
        response = client.get(url)

        assert response.status_code == 302
        assert AnalysisJob.objects.filter(game=game).exists()

    def test_analysis_access_after_resignation(self, client):
        game = self.create_finished_game(Game.Winner.WHITE, Game.FinishReason.RESIGNATION)
        client.login(username='white_player', password='password123')

        url = reverse('create_game_analysis_job', kwargs={'game_id': game.id})
        response = client.get(url)

        assert response.status_code == 302

    def test_analysis_access_after_timeout(self, client):
        game = self.create_finished_game(Game.Winner.BLACK, Game.FinishReason.TIMEOUT)
        client.login(username='black_player', password='password123')

        url = reverse('create_game_analysis_job', kwargs={'game_id': game.id})
        response = client.get(url)

        assert response.status_code == 302

    def test_outsider_cannot_analyze(self, client):
        game = self.create_finished_game(Game.Winner.WHITE, Game.FinishReason.CHECKMATE)
        client.login(username='outsider', password='password123')

        url = reverse('create_game_analysis_job', kwargs={'game_id': game.id})
        response = client.get(url)

        assert response.status_code == 403
        assert not AnalysisJob.objects.filter(game=game).exists()

    def test_teacher_can_analyze(self, client):
        game = self.create_finished_game(Game.Winner.WHITE, Game.FinishReason.CHECKMATE)
        client.login(username='teacher', password='password123')

        url = reverse('create_game_analysis_job', kwargs={'game_id': game.id})
        response = client.get(url)

        assert response.status_code == 302

    def test_analysis_does_not_mutate_finished_game(self, client):
        game = self.create_finished_game(Game.Winner.WHITE, Game.FinishReason.CHECKMATE)
        initial_fen = game.fen_current
        initial_status = game.status

        client.login(username='white_player', password='password123')
        url = reverse('create_game_analysis_job', kwargs={'game_id': game.id})
        client.get(url)

        game.refresh_from_db()
        assert game.fen_current == initial_fen
        assert game.status == initial_status

