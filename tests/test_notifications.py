"""
Tests for the notification system.

Covers:
  - WebSocket connection (authenticated vs anonymous)
  - Real-time delivery of a created notification
  - Marking a notification as read via WebSocket
  - HTTP fallback endpoints
  - Persistence: DB row is created even when WebSocket broadcast is skipped
  - Cross-user isolation
"""
import pytest
import asyncio
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.test import Client

from apps.accounts.models import CustomUser
from apps.games.models import Game, Notification
from apps.games.consumers import NotificationConsumer
from apps.games.services import send_notification


@database_sync_to_async
def make_user(username):
    return CustomUser.objects.create_user(username=username, password='password123')


@database_sync_to_async
def make_game(white, black):
    return Game.objects.create(white_player=white, black_player=black)


@database_sync_to_async
def get_unread_count(user):
    return Notification.objects.filter(user=user, is_read=False).count()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_notif_ws_connection_authenticated_receives_unread():
    u1 = await make_user('alice')
    await database_sync_to_async(Notification.objects.create)(
        user=u1, message='Test notif 1')
    await database_sync_to_async(Notification.objects.create)(
        user=u1, message='Test notif 2')

    comm = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/')
    comm.scope['user'] = u1
    connected, _ = await comm.connect()
    assert connected

    init = await comm.receive_json_from()
    assert init['type'] == 'unread_notifications'
    assert len(init['notifications']) == 2
    assert init['notifications'][0]['message'] == 'Test notif 2'
    assert init['notifications'][0]['is_read'] is False

    await comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_notif_ws_rejects_anonymous():
    comm = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/')
    comm.scope['user'] = None
    connected, _ = await comm.connect()
    assert not connected  # anonymous users are rejected

    # When the server closes the connection, calling disconnect() again raises
    # CancelledError — the important assertion above (not connected) is enough.


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_send_notification_delivers_via_websocket():
    u1 = await make_user('bob')
    comm = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/')
    comm.scope['user'] = u1
    connected, _ = await comm.connect()
    assert connected
    await comm.receive_json_from()  # consume init_state (empty list)

    await database_sync_to_async(send_notification)(
        u1, "¡Has desbloqueado al Bot 4!",
    )

    msg = await comm.receive_json_from()
    assert msg['type'] == 'notification'
    notif = msg['notification']
    assert notif['message'] == "¡Has desbloqueado al Bot 4!"
    assert notif['is_read'] is False
    assert notif['game_id'] is None

    db_count = await get_unread_count(u1)
    assert db_count == 1

    await comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_mark_notification_read_via_websocket():
    u1 = await make_user('carol')
    notif = await database_sync_to_async(Notification.objects.create)(
        user=u1, message='Marca leída')

    comm = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/')
    comm.scope['user'] = u1
    connected, _ = await comm.connect()
    assert connected
    await comm.receive_json_from()  # consume unread list

    await comm.send_json_to({
        'type': 'mark_read',
        'notification_id': str(notif.id),
    })

    ack = await comm.receive_json_from()
    assert ack['type'] == 'notification_read'
    assert ack['notification_id'] == str(notif.id)

    still_unread = await (database_sync_to_async(
        lambda: Notification.objects.filter(id=notif.id, is_read=False).exists()
    ))()
    assert not still_unread

    await comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_payload_structure():
    """The JSON payload received by the frontend must have all expected keys."""
    u1 = await make_user('dave')
    game = await make_game(u1, await make_user('eve'))

    comm = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/')
    comm.scope['user'] = u1
    connected, _ = await comm.connect()
    assert connected
    await comm.receive_json_from()  # empty init

    await database_sync_to_async(send_notification)(
        u1, "Partida de bots completada", game=game,
    )

    msg = await comm.receive_json_from()
    notif = msg['notification']
    expected_keys = {'id', 'message', 'game_id', 'is_read', 'created_at'}
    assert set(notif.keys()) == expected_keys
    assert notif['game_id'] is not None
    assert notif['is_read'] is False

    await comm.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_notification_isolation_between_users():
    """A notification sent to user A must never reach user B."""
    u1 = await make_user('frank')
    u2 = await make_user('grace')

    comm_b = WebsocketCommunicator(NotificationConsumer.as_asgi(), '/ws/notifications/')
    comm_b.scope['user'] = u2
    connected_b, _ = await comm_b.connect()
    assert connected_b
    await comm_b.receive_json_from()  # consume empty init

    # Send to u1, not u2
    await database_sync_to_async(send_notification)(
        u1, "Solo para frank",
    )

    # Give the channel layer a moment to (incorrectly) route it, then verify
    # nothing leaked into u2's socket queue.
    await asyncio.sleep(0.5)
    assert comm_b.output_queue.qsize() == 0  # nothing leaked to u2

    # u1 should have the notification in DB
    count = await get_unread_count(u1)
    assert count == 1

    await comm_b.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_send_notification_persists_even_if_websocket_unavailable():
    """The DB row must exist even if no WebSocket is connected."""
    u1 = await make_user('heidi')
    notif = await database_sync_to_async(send_notification)(
        u1, "Notificación offline",
    )
    assert notif.id is not None
    db_count = await get_unread_count(u1)
    assert db_count == 1


# ---- HTTP fallback tests ----

@pytest.mark.django_db
def test_http_notification_list_and_read():
    """HTTP fallback endpoints must work when WebSocket is unavailable."""
    u1 = CustomUser.objects.create_user(username='ivan', password='password123')
    client = Client()
    client.login(username='ivan', password='password123')

    Notification.objects.create(user=u1, message='HTTP test 1')
    Notification.objects.create(user=u1, message='HTTP test 2')

    resp = client.get('/games/api/notifications/')
    assert resp.status_code == 200
    data = resp.json()
    assert data['unread_count'] == 2
    assert len(data['notifications']) == 2

    notif_id = data['notifications'][0]['id']
    resp2 = client.post(f'/games/api/notifications/{notif_id}/read/')
    assert resp2.status_code == 200
    assert resp2.json()['unread_count'] == 1

    resp3 = client.post('/games/api/notifications/read-all/')
    assert resp3.status_code == 200
    assert resp3.json()['unread_count'] == 0


@pytest.mark.django_db
def test_http_notification_access_isolation():
    """A user must not be able to mark another user's notifications as read."""
    u1 = CustomUser.objects.create_user(username='judy', password='password123')
    u2 = CustomUser.objects.create_user(username='karl', password='password123')

    notif = Notification.objects.create(user=u2, message='Para karl')

    client = Client()
    client.login(username='judy', password='password123')

    resp = client.post(f'/games/api/notifications/{notif.id}/read/')
    assert resp.status_code == 404
    assert Notification.objects.filter(id=notif.id, is_read=False).exists()
