from django.urls import path
from . import views

urlpatterns = [
    path('', views.TrainingDashboardView.as_view(), name='training_dashboard'),
    path('puzzle/<uuid:puzzle_id>/', views.PuzzleDetailView.as_view(), name='puzzle_detail'),
    path('api/puzzle/<uuid:puzzle_id>/submit/', views.submit_puzzle_move_api, name='submit_puzzle_move_api'),
    path('api/puzzle/<uuid:puzzle_id>/hint/', views.get_puzzle_hint_api, name='get_puzzle_hint_api'),

    # Creation & authoring
    path('create/', views.PuzzleCreateView.as_view(), name='puzzle_create'),
    path('puzzle/<uuid:puzzle_id>/edit/', views.PuzzleEditView.as_view(), name='puzzle_edit'),
    path('puzzle/<uuid:puzzle_id>/delete/', views.delete_puzzle, name='puzzle_delete'),
    path('my-puzzles/', views.MyPuzzlesListView.as_view(), name='my_puzzles'),

    # Moderation workflow
    path('puzzle/<uuid:puzzle_id>/submit-review/', views.submit_puzzle_for_review, name='puzzle_submit_review'),
    path('puzzle/<uuid:puzzle_id>/approve/', views.approve_puzzle, name='puzzle_approve'),
    path('puzzle/<uuid:puzzle_id>/reject/', views.reject_puzzle, name='puzzle_reject'),
    path('puzzle/<uuid:puzzle_id>/archive/', views.archive_puzzle, name='puzzle_archive'),
    path('moderation/', views.PuzzleModerationListView.as_view(), name='puzzle_moderation'),

    # Community
    path('puzzle/<uuid:puzzle_id>/favorite/', views.toggle_favorite_api, name='puzzle_toggle_favorite'),
    path('puzzle/<uuid:puzzle_id>/rate/', views.rate_puzzle_api, name='puzzle_rate'),
    path('favorites/', views.FavoritesListView.as_view(), name='puzzle_favorites'),
]
