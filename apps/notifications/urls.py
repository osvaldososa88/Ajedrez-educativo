from django.urls import path
from .views import notifications_list, mark_notification_read, mark_all_notifications_read

urlpatterns = [
    path('', notifications_list, name='notifications_list'),
    path('<uuid:notification_id>/read/', mark_notification_read, name='mark_notification_read'),
    path('mark-all-read/', mark_all_notifications_read, name='mark_all_notifications_read'),
]
