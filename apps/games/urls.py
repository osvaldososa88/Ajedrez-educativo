from django.urls import path
from .views import (
    ChallengeListView, create_challenge, accept_challenge, decline_challenge,
    GameDetailView, export_pgn, GameHistoryView, toggle_favorite_game, shared_game_view,
    global_chat_view, notification_list_api, notification_mark_read_api,
    notification_mark_all_read_api
)

urlpatterns = [
    path('challenges/', ChallengeListView.as_view(), name='challenges_list'),
    path('community-chat/', global_chat_view, name='global_chat'),
    path('challenges/create/<int:user_id>/', create_challenge, name='create_challenge'),
    path('challenges/<uuid:challenge_id>/accept/', accept_challenge, name='accept_challenge'),
    path('challenges/<uuid:challenge_id>/decline/', decline_challenge, name='decline_challenge'),
    path('history/', GameHistoryView.as_view(), name='game_history'),
    path('game/<uuid:game_id>/', GameDetailView.as_view(), name='game_detail'),
    path('game/<uuid:game_id>/pgn/', export_pgn, name='export_pgn'),
    path('game/<uuid:game_id>/favorite/', toggle_favorite_game, name='toggle_favorite_game'),
    path('share/<uuid:share_token>/', shared_game_view, name='shared_game'),
    # HTTP Notification endpoints (fallback when WebSocket is unavailable)
    path('api/notifications/', notification_list_api, name='notification_list_api'),
    path('api/notifications/<int:notification_id>/read/', notification_mark_read_api, name='notification_mark_read_api'),
    path('api/notifications/read-all/', notification_mark_all_read_api, name='notification_mark_all_read_api'),
]
