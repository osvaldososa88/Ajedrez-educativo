import pytest
import uuid
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.games.models import Game, GameFavorite
from apps.analysis.models import AnalysisJob

User = get_user_model()

@pytest.mark.django_db
class TestAnalysisAndHistoryFeatures:

    @pytest.fixture(autouse=True)
    def setup_data(self):
        self.white_user = User.objects.create_user(username='white_player', password='password123')
        self.black_user = User.objects.create_user(username='black_player', password='password123')
        self.other_user = User.objects.create_user(username='other_player', password='password123')

        self.game = Game.objects.create(
            white_player=self.white_user,
            black_player=self.black_user,
            status=Game.Status.FINISHED,
            winner=Game.Winner.WHITE,
            finish_reason=Game.FinishReason.CHECKMATE
        )

        self.analysis_job = AnalysisJob.objects.create(
            game=self.game,
            user=self.white_user,
            status=AnalysisJob.Status.COMPLETED
        )

    def test_black_player_can_access_analysis_detail(self, client):
        """Verify Black player gets 200 OK (no 404) for game analysis detail."""
        client.login(username='black_player', password='password123')
        url = reverse('analysis_job_detail', kwargs={'job_id': self.analysis_job.id})
        response = client.get(url)
        assert response.status_code == 200
        assert response.context['job'] == self.analysis_job

    def test_unauthorized_user_cannot_access_analysis(self, client):
        """Verify unrelated user gets 404 for another game's analysis."""
        client.login(username='other_player', password='password123')
        url = reverse('analysis_job_detail', kwargs={'job_id': self.analysis_job.id})
        response = client.get(url)
        assert response.status_code == 404

    def test_toggle_favorite_game_and_max_limit(self, client):
        """Verify toggling favorites works and enforces 10 favorites max limit."""
        client.login(username='white_player', password='password123')
        url = reverse('toggle_favorite_game', kwargs={'game_id': self.game.id})

        # 1. Add favorite
        res = client.post(url)
        assert res.status_code == 200
        data = res.json()
        assert data['is_favorite'] is True

        # Create 9 more favorited games for white_user (total 10)
        for _ in range(9):
            g = Game.objects.create(
                white_player=self.white_user,
                black_player=self.black_user,
                status=Game.Status.FINISHED
            )
            GameFavorite.objects.create(user=self.white_user, game=g)

        assert GameFavorite.objects.filter(user=self.white_user).count() == 10

        # Try to favorite 11th game -> expect 400 Bad Request
        extra_game = Game.objects.create(
            white_player=self.white_user,
            black_player=self.black_user,
            status=Game.Status.FINISHED
        )
        url_extra = reverse('toggle_favorite_game', kwargs={'game_id': extra_game.id})
        res_extra = client.post(url_extra)
        assert res_extra.status_code == 400
        assert 'límite máximo de 10 partidas favoritas' in res_extra.json()['error']

    def test_prune_user_history_protects_favorites(self):
        """Verify prune_user_history keeps up to 50 games but protects favorited games from deletion."""
        # Create 60 finished games for white_user
        games = []
        for i in range(60):
            g = Game.objects.create(
                white_player=self.white_user,
                black_player=self.black_user,
                status=Game.Status.FINISHED
            )
            games.append(g)

        # Favorite the 1st game created (which would be oldest and normally pruned)
        oldest_game = games[0]
        GameFavorite.objects.create(user=self.white_user, game=oldest_game)

        # Prune history limit 50
        Game.prune_user_history(self.white_user, limit=50)

        # Oldest favorited game MUST still exist
        assert Game.objects.filter(id=oldest_game.id).exists() is True

    def test_shared_game_view_redirects_to_analysis(self, client):
        """Verify public share token view redirects to analysis detail page."""
        url = reverse('shared_game', kwargs={'share_token': self.game.share_token})
        response = client.get(url)
        assert response.status_code == 302
        assert reverse('analysis_job_detail', kwargs={'job_id': self.analysis_job.id}) in response.url

    def test_game_history_view_renders_successfully(self, client):
        """Verify GameHistoryView renders 200 OK without TemplateSyntaxError."""
        client.login(username='white_player', password='password123')
        url = reverse('game_history')
        response = client.get(url)
        assert response.status_code == 200
        assert b'Historial de Partidas' in response.content
