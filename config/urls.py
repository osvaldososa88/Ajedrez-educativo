from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('classmates')
    return redirect('login')

urlpatterns = [
    path('', home_redirect, name='home'),
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('games/', include('apps.games.urls')),
    path('analysis/', include('apps.analysis.urls')),
    path('training/', include('apps.training.urls')),
    path('classrooms/', include('apps.classrooms.urls')),
    path('tournaments/', include('apps.tournaments.urls')),
    path('personalization/', include('apps.personalization.urls')),
    path('', include('apps.core.urls')),
]
