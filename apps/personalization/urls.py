from django.urls import path
from . import views

urlpatterns = [
    path('', views.PersonalizationDashboardView.as_view(), name='personalization_dashboard'),
    path('my-errors/', views.MyDetectedErrorsListView.as_view(), name='personalization_my_errors'),
    path('jobs/<uuid:job_id>/generate/', views.generate_training_from_job, name='personalization_generate_from_job'),
    path('appearance/', views.AppearanceSettingsView.as_view(), name='personalization_appearance'),
]
