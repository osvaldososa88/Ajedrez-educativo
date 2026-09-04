import pytest
from django.urls import reverse
from apps.accounts.models import CustomUser
from apps.games.models import Game, Challenge, Move

@pytest.mark.django_db
def test_create_user_and_roles():
    u1 = CustomUser.objects.create_user(username='estudiante1', password='password123', role=CustomUser.Role.STUDENT)
    u2 = CustomUser.objects.create_user(username='docente1', password='password123', role=CustomUser.Role.TEACHER)

    assert u1.role == 'STUDENT'
    assert u2.role == 'TEACHER'
    assert u1.elo_rating == 1200

@pytest.mark.django_db
def test_challenge_and_game_creation(client):
    u1 = CustomUser.objects.create_user(username='estudiante1', password='password123')
    u2 = CustomUser.objects.create_user(username='estudiante2', password='password123')

    client.login(username='estudiante1', password='password123')
    response = client.post(reverse('create_challenge', kwargs={'user_id': u2.id}), {
        'time_control_minutes': 10,
        'time_control_increment': 0
    })
    assert response.status_code == 302 # Redirect to challenges_list

    challenge = Challenge.objects.get(sender=u1, receiver=u2)
    assert challenge.status == Challenge.Status.PENDING

    # Test challenge list view rendering
    response = client.get(reverse('challenges_list'))
    assert response.status_code == 200

    # Accept challenge as u2
    client.login(username='estudiante2', password='password123')
    response = client.post(reverse('accept_challenge', kwargs={'challenge_id': challenge.id}))
    assert response.status_code == 302 # Redirect to game_detail

    challenge.refresh_from_db()
    assert challenge.status == Challenge.Status.ACCEPTED
    assert challenge.game is not None
    assert challenge.game.status == Game.Status.IN_PROGRESS

    # Test challenge list view with active game
    response = client.get(reverse('challenges_list'))
    assert response.status_code == 200

@pytest.mark.django_db
def test_pgn_export_view(client):
    u1 = CustomUser.objects.create_user(username='estudiante1', password='password123')
    u2 = CustomUser.objects.create_user(username='estudiante2', password='password123')
    game = Game.objects.create(white_player=u1, black_player=u2)

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('export_pgn', kwargs={'game_id': game.id}))
    assert response.status_code == 200
    assert response['Content-Type'] == 'application/x-chess-pgn'
    assert b'estudiante1' in response.content
    assert b'estudiante2' in response.content
