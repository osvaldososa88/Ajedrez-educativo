from django.urls import path
from .views import (
    ChallengeListView, create_challenge, accept_challenge, decline_challenge,
    GameDetailView, export_pgn, GameHistoryView, toggle_favorite_game, shared_game_view
)

urlpatterns = [
    path('challenges/', ChallengeListView.as_view(), name='challenges_list'),
    path('challenges/create/<int:user_id>/', create_challenge, name='create_challenge'),
    path('challenges/<uuid:challenge_id>/accept/', accept_challenge, name='accept_challenge'),
    path('challenges/<uuid:challenge_id>/decline/', decline_challenge, name='decline_challenge'),
    path('history/', GameHistoryView.as_view(), name='game_history'),
    path('game/<uuid:game_id>/', GameDetailView.as_view(), name='game_detail'),
    path('game/<uuid:game_id>/pgn/', export_pgn, name='export_pgn'),
    path('game/<uuid:game_id>/favorite/', toggle_favorite_game, name='toggle_favorite_game'),
    path('share/<uuid:share_token>/', shared_game_view, name='shared_game'),
]
