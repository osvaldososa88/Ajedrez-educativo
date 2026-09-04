import pytest
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from apps.accounts.models import CustomUser
from apps.games.models import Game
from apps.games.consumers import GameConsumer

@database_sync_to_async
def create_test_user(username):
    return CustomUser.objects.create_user(username=username, password='pass')

@database_sync_to_async
def create_test_game(white, black):
    return Game.objects.create(white_player=white, black_player=black)

@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_websocket_game_flow():
    u1 = await create_test_user('white_player')
    u2 = await create_test_user('black_player')
    u3 = await create_test_user('spectator')

    game = await create_test_game(u1, u2)

    # 1. White player connects
    communicator_w = WebsocketCommunicator(GameConsumer.as_asgi(), f"/ws/game/{game.id}/")
    communicator_w.scope['user'] = u1
    communicator_w.scope['url_route'] = {'kwargs': {'game_id': str(game.id)}}

    connected, _ = await communicator_w.connect()
    assert connected

    init_msg = await communicator_w.receive_json_from()
    assert init_msg['type'] == 'init_state'
    assert init_msg['state']['turn'] == 'WHITE'

    # 2. Black player connects
    communicator_b = WebsocketCommunicator(GameConsumer.as_asgi(), f"/ws/game/{game.id}/")
    communicator_b.scope['user'] = u2
    communicator_b.scope['url_route'] = {'kwargs': {'game_id': str(game.id)}}

    connected_b, _ = await communicator_b.connect()
    assert connected_b
    await communicator_b.receive_json_from() # consume init_state

    # 3. Black tries to move on White's turn -> should fail
    await communicator_b.send_json_to({'type': 'make_move', 'uci': 'e7e5'})
    err_msg = await communicator_b.receive_json_from()
    assert err_msg['type'] == 'error'
    assert 'Es el turno' in err_msg['message']

    # 4. White makes legal move 1. e4
    await communicator_w.send_json_to({'type': 'make_move', 'uci': 'e2e4'})

    update_w = await communicator_w.receive_json_from()
    update_b = await communicator_b.receive_json_from()

    assert update_w['type'] == 'game_update'
    assert update_b['type'] == 'game_update'
    assert update_w['state']['turn'] == 'BLACK'
    assert update_w['state']['last_move']['san'] == 'e4'

    # 5. Spectator tries to move -> should fail
    communicator_s = WebsocketCommunicator(GameConsumer.as_asgi(), f"/ws/game/{game.id}/")
    communicator_s.scope['user'] = u3
    communicator_s.scope['url_route'] = {'kwargs': {'game_id': str(game.id)}}

    await communicator_s.connect()
    await communicator_s.receive_json_from()

    await communicator_s.send_json_to({'type': 'make_move', 'uci': 'e7e5'})
    spec_err = await communicator_s.receive_json_from()
    assert spec_err['type'] == 'error'

    await communicator_w.disconnect()
    await communicator_b.disconnect()
    await communicator_s.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_draw_offer_is_delivered_to_opponent():
    u1 = await create_test_user('white_offer')
    u2 = await create_test_user('black_receiver')

    game = await create_test_game(u1, u2)

    communicator_w = WebsocketCommunicator(GameConsumer.as_asgi(), f"/ws/game/{game.id}/")
    communicator_w.scope['user'] = u1
    communicator_w.scope['url_route'] = {'kwargs': {'game_id': str(game.id)}}
    connected_w, _ = await communicator_w.connect()
    assert connected_w
    await communicator_w.receive_json_from()  # consume init_state

    communicator_b = WebsocketCommunicator(GameConsumer.as_asgi(), f"/ws/game/{game.id}/")
    communicator_b.scope['user'] = u2
    communicator_b.scope['url_route'] = {'kwargs': {'game_id': str(game.id)}}
    connected_b, _ = await communicator_b.connect()
    assert connected_b
    await communicator_b.receive_json_from()  # consume init_state

    # White offers a draw; both sockets belong to the same room group.
    await communicator_w.send_json_to({'type': 'offer_draw'})

    offer_to_white = await communicator_w.receive_json_from()
    offer_to_black = await communicator_b.receive_json_from()

    assert offer_to_white['type'] == 'draw_offer'
    assert offer_to_white['offered_by'] == 'white_offer'
    assert offer_to_black['type'] == 'draw_offer'
    assert offer_to_black['offered_by'] == 'white_offer'

    await communicator_w.disconnect()
    await communicator_b.disconnect()
