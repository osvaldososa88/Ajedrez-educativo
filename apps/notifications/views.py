from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_GET
from .models import Notification


@login_required
@require_GET
def notifications_list(request):
    """
    Devuelve las notificaciones del usuario autenticado.
    Incluye el contador de no leídas y la lista paginada.
    """
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    notifications = Notification.objects.filter(user=request.user)[:20]
    
    data = {
        'unread_count': unread_count,
        'notifications': [
            {
                'id': str(n.id),
                'type': n.type,
                'title': n.title,
                'message': n.message,
                'game_id': n.game_id,
                'puzzle_id': n.puzzle_id,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifications
        ]
    }
    return JsonResponse(data)


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """
    Marca una notificación específica como leída.
    Solo el propietario puede leer sus propias notificaciones.
    """
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
    except Notification.DoesNotExist:
        return JsonResponse({'error': 'Notificación no encontrada'}, status=404)
    
    notification.is_read = True
    notification.save(update_fields=['is_read'])
    
    return JsonResponse({
        'success': True,
        'unread_count': Notification.objects.filter(user=request.user, is_read=False).count()
    })


@login_required
@require_POST
def mark_all_notifications_read(request):
    """
    Marca todas las notificaciones del usuario como leídas.
    """
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    
    return JsonResponse({
        'success': True,
        'unread_count': 0
    })
