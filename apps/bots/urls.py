from django.urls import path

from . import views

urlpatterns = [
    path('', views.BotListView.as_view(), name='bots_list'),
    path('bot/<int:bot_id>/', views.BotDetailView.as_view(), name='bot_detail'),
    path('bot/<int:bot_id>/play/', views.start_bot_game, name='bot_play'),
]
