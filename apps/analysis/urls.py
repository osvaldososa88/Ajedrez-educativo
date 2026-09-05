from django.urls import path
from . import views

urlpatterns = [
    path('import/', views.import_pgn_view, name='import_pgn'),
    path('game/<uuid:game_id>/start/', views.create_game_analysis_job, name='create_game_analysis_job'),
    path('game/<uuid:game_id>/start-alias/', views.create_game_analysis_job, name='start_game_analysis'),
    path('job/<uuid:job_id>/', views.AnalysisJobDetailView.as_view(), name='analysis_job_detail'),
    path('job/<uuid:job_id>/status/', views.job_status_api, name='analysis_job_status_api'),
    path('api/fen-eval/', views.analyze_single_fen_api, name='analyze_single_fen_api'),
]
