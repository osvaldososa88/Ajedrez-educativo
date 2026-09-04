from django.urls import path
from . import views

urlpatterns = [
    path('', views.TournamentListView.as_view(), name='tournament_list'),
    path('create/', views.TournamentCreateView.as_view(), name='tournament_create'),
    path('<uuid:tournament_id>/', views.TournamentDetailView.as_view(), name='tournament_detail'),
    path('<uuid:tournament_id>/register/', views.register, name='tournament_register'),
    path('<uuid:tournament_id>/withdraw/', views.withdraw, name='tournament_withdraw'),
    path('<uuid:tournament_id>/open-registration/', views.open_registration, name='tournament_open_registration'),
    path('<uuid:tournament_id>/start/', views.start_tournament, name='tournament_start'),
    path('<uuid:tournament_id>/next-round/', views.generate_next_round, name='tournament_next_round'),
    path('<uuid:tournament_id>/finalize/', views.finalize_tournament, name='tournament_finalize'),
    path('<uuid:tournament_id>/cancel/', views.cancel_tournament, name='tournament_cancel'),

    path('<uuid:tournament_id>/rounds/<int:round_id>/', views.RoundDetailView.as_view(), name='round_detail'),
    path('<uuid:tournament_id>/rounds/<int:round_id>/close/', views.close_round, name='round_close'),
    path('<uuid:tournament_id>/rounds/<int:round_id>/pairings/<int:pairing_id>/incident/', views.record_incident, name='pairing_record_incident'),
    path('<uuid:tournament_id>/rounds/<int:round_id>/pairings/<int:pairing_id>/result/', views.set_manual_result, name='pairing_set_result'),
]
