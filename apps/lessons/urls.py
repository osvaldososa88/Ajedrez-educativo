from django.urls import path

from . import views

# Sin `app_name`: en este proyecto los nombres de URL son globales (así lo hacen
# el resto de apps), de modo que `{% url 'lesson_detail' %}` y
# `Lesson.get_absolute_url()` resuelven sin prefijo.

urlpatterns = [
    path('', views.lesson_index, name='lesson_index'),
    path('<slug:slug>/', views.lesson_detail, name='lesson_detail'),
    path('capitulo/<int:pk>/', views.chapter_detail, name='chapter_detail'),
    path('capitulo/<int:pk>/arbol/', views.chapter_tree, name='chapter_tree'),
    path('capitulo/<int:pk>/jugar/', views.chapter_play, name='chapter_play'),
]