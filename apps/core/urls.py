from django.urls import path
from . import views

urlpatterns = [
    path('sw.js', views.service_worker, name='service_worker'),
    path('manifest.json', views.manifest, name='manifest'),
]