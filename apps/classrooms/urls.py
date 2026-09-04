from django.urls import path
from . import views

urlpatterns = [
    path('', views.ClassroomListView.as_view(), name='classroom_list'),
    path('create/', views.ClassroomCreateView.as_view(), name='classroom_create'),
    path('join/', views.join_classroom, name='classroom_join'),

    path('invitations/', views.InvitationListView.as_view(), name='classroom_invitations'),
    path('invitations/<uuid:invitation_id>/accept/', views.accept_invitation, name='classroom_invitation_accept'),
    path('invitations/<uuid:invitation_id>/decline/', views.decline_invitation, name='classroom_invitation_decline'),

    path('<uuid:classroom_id>/', views.ClassroomDetailView.as_view(), name='classroom_detail'),
    path('<uuid:classroom_id>/invite/', views.invite_student, name='classroom_invite_student'),
    path('<uuid:classroom_id>/students/<int:user_id>/remove/', views.remove_student, name='classroom_remove_student'),
    path('<uuid:classroom_id>/students/<int:user_id>/progress/', views.StudentProgressDetailView.as_view(), name='classroom_student_progress'),
    path('<uuid:classroom_id>/stats/', views.ClassroomStatsView.as_view(), name='classroom_stats'),

    path('<uuid:classroom_id>/activities/create/', views.ActivityCreateView.as_view(), name='activity_create'),
    path('<uuid:classroom_id>/activities/<uuid:activity_id>/', views.ActivityDetailView.as_view(), name='activity_detail'),
]
