"""
Shared game-related service helpers.
Currently exposes a unified notification helper so every code path that
creates a Notification also broadcasts it over the WebSocket channel layer
to ``notifications_<user_id>``, keeping real-time and stored notifications
in sync.
"""
import logging

logger = logging.getLogger(__name__)


def send_notification(user, message, title="Notificación", notif_type="system", game=None, puzzle=None):
    """
    Create a Notification for ``user`` and immediately broadcast it via
    Channels to the user's notification WebSocket group.
    """
    from apps.notifications.models import Notification
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    notification = Notification.objects.create(
        user=user,
        type=notif_type,
        title=title,
        message=message,
        game=game,
        puzzle=puzzle,
    )

    notif_payload = {
        'id': str(notification.id),
        'message': notification.message,
        'game_id': str(game.id) if game else None,
        'is_read': False,
        'created_at': notification.created_at.isoformat(),
    }

    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'notifications_{user.id}',
            {
                'type': 'send_notification',
                'notification': notif_payload,
            }
        )
    except Exception:
        # WebSocket broadcast is best-effort. The DB notification will
        # still be picked up by the HTTP fallback in notifications.js.
        logger.debug(
            "WebSocket broadcast failed for notification %s to user %s; "
            "HTTP fallback will deliver it.",
            notification.id, user.id, exc_info=True,
        )

    return notification
