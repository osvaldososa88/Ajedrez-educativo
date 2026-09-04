import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.personalization.models import GlobalChessConfig, UserAppearancePreference
from apps.personalization.chess_theme_registry import resolve_user_appearance

User = get_user_model()


@pytest.mark.django_db
class TestChessAppearanceSystem:

    def setup_method(self):
        self.student1 = User.objects.create_user(username='student1', password='password123')
        self.student2 = User.objects.create_user(username='student2', password='password123')
        self.global_config = GlobalChessConfig.get_solo()
        self.global_config.default_piece_set = 'staunton'
        self.global_config.default_board_theme = 'classic'
        self.global_config.allow_player_customization = True
        self.global_config.save()

    def test_fallback_unauthenticated_user(self):
        piece_set, board_theme, is_custom = resolve_user_appearance(None)
        assert piece_set == 'staunton'
        assert board_theme == 'classic'
        assert is_custom is False

    def test_fallback_user_without_preferences(self):
        piece_set, board_theme, is_custom = resolve_user_appearance(self.student1)
        assert piece_set == 'staunton'
        assert board_theme == 'classic'
        assert is_custom is False

    def test_user_custom_preferences(self):
        UserAppearancePreference.objects.create(
            user=self.student1,
            piece_set='cburnett',
            board_theme='wood_green'
        )

        piece_set, board_theme, is_custom = resolve_user_appearance(self.student1)
        assert piece_set == 'cburnett'
        assert board_theme == 'wood_green'
        assert is_custom is True

    def test_admin_disables_customization(self):
        UserAppearancePreference.objects.create(
            user=self.student1,
            piece_set='cburnett',
            board_theme='purple'
        )
        self.global_config.allow_player_customization = False
        self.global_config.save()

        piece_set, board_theme, is_custom = resolve_user_appearance(self.student1)
        assert piece_set == 'staunton'
        assert board_theme == 'classic'
        assert is_custom is False

    def test_appearance_settings_view_get(self, client):
        client.login(username='student1', password='password123')
        response = client.get(reverse('personalization_appearance'))
        assert response.status_code == 200
        assert 'piece_sets' in response.context
        assert 'board_themes' in response.context

    def test_appearance_settings_view_post_valid(self, client):
        client.login(username='student1', password='password123')
        response = client.post(reverse('personalization_appearance'), {
            'action': 'save',
            'piece_set': 'merida',
            'board_theme': 'walnut_brown'
        })
        assert response.status_code == 302
        pref = UserAppearancePreference.objects.get(user=self.student1)
        assert pref.piece_set == 'merida'
        assert pref.board_theme == 'walnut_brown'

    def test_appearance_settings_view_post_invalid(self, client):
        client.login(username='student1', password='password123')
        response = client.post(reverse('personalization_appearance'), {
            'action': 'save',
            'piece_set': 'malicious_set_path',
            'board_theme': 'invalid_theme'
        })
        assert response.status_code == 302
        assert not UserAppearancePreference.objects.filter(user=self.student1).exists()

    def test_appearance_settings_view_reset(self, client):
        UserAppearancePreference.objects.create(
            user=self.student1,
            piece_set='alpha',
            board_theme='dark_slate'
        )
        client.login(username='student1', password='password123')
        response = client.post(reverse('personalization_appearance'), {
            'action': 'reset'
        })
        assert response.status_code == 302
        assert not UserAppearancePreference.objects.filter(user=self.student1).exists()
