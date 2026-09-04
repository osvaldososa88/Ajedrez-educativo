import pytest
from django.urls import reverse
from apps.accounts.models import CustomUser
from apps.games.models import Game
from apps.tournaments.models import Tournament, TournamentParticipant, Round, Pairing
from apps.tournaments.pairing import RoundRobinPairingService, SwissPairingService
from apps.tournaments.standings import StandingsService
from apps.tournaments.services import TournamentService, TournamentError


def make_user(username, elo=1200, role=CustomUser.Role.STUDENT):
    return CustomUser.objects.create_user(username=username, password='password123', role=role, elo_rating=elo)


def make_tournament(organizer, fmt=Tournament.Format.ROUND_ROBIN, rounds_total=None, **overrides):
    tournament = Tournament.objects.create(
        name=overrides.get('name', 'Torneo de Prueba'),
        created_by=organizer,
        format=fmt,
        rounds_total=rounds_total,
        status=overrides.get('status', Tournament.Status.REGISTRATION_OPEN),
    )
    tournament.organizers.add(organizer)
    return tournament


def add_participant(tournament, user):
    return TournamentParticipant.objects.create(tournament=tournament, user=user, seed_rating=user.elo_rating)


# --- Round Robin pairing algorithm ---

@pytest.mark.django_db
def test_round_robin_schedule_even_participants_everyone_plays_everyone():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    users = [make_user(f'p{i}') for i in range(4)]
    participants = [add_participant(tournament, u) for u in users]

    schedule = RoundRobinPairingService.generate_schedule(participants)
    assert len(schedule) == 3  # n-1 rounds for even n

    played_pairs = set()
    for round_pairings in schedule:
        seen_this_round = set()
        for white, black in round_pairings:
            assert black is not None  # even count: no byes
            assert white.id not in seen_this_round
            assert black.id not in seen_this_round
            seen_this_round.add(white.id)
            seen_this_round.add(black.id)
            played_pairs.add(frozenset({white.id, black.id}))
        assert len(seen_this_round) == 4  # everyone plays every round

    # Every possible pair (4 choose 2 = 6) plays exactly once.
    expected_pairs = {frozenset({a.id, b.id}) for i, a in enumerate(participants) for b in participants[i + 1:]}
    assert played_pairs == expected_pairs


@pytest.mark.django_db
def test_round_robin_schedule_odd_participants_uses_byes():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    users = [make_user(f'p{i}') for i in range(5)]
    participants = [add_participant(tournament, u) for u in users]

    schedule = RoundRobinPairingService.generate_schedule(participants)
    assert len(schedule) == 5  # n participants + bye slot = 6 -> 5 rounds

    bye_counts = {p.id: 0 for p in participants}
    for round_pairings in schedule:
        byes_this_round = [w for w, b in round_pairings if b is None]
        assert len(byes_this_round) == 1  # exactly one bye per round with odd participants
        bye_counts[byes_this_round[0].id] += 1

    # Every participant gets exactly one bye across the whole schedule.
    assert all(count == 1 for count in bye_counts.values())


@pytest.mark.django_db
def test_round_robin_schedule_single_participant_is_empty():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    user = make_user('solo')
    participants = [add_participant(tournament, user)]
    assert RoundRobinPairingService.generate_schedule(participants) == []


# --- Swiss pairing algorithm ---

@pytest.mark.django_db
def test_swiss_round_one_pairs_by_rating_with_no_history():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher, fmt=Tournament.Format.SWISS, rounds_total=3)
    users = [make_user(f'p{i}', elo=1000 + i * 100) for i in range(4)]
    participants = [add_participant(tournament, u) for u in users]
    standings = {p.id: {'points': 0.0} for p in participants}

    pairings = SwissPairingService.generate_next_round_pairings(tournament, participants, standings, [])
    assert len(pairings) == 2
    for white, black in pairings:
        assert black is not None


@pytest.mark.django_db
def test_swiss_avoids_rematches_when_possible():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher, fmt=Tournament.Format.SWISS, rounds_total=3)
    users = [make_user(f'p{i}', elo=1200) for i in range(4)]
    participants = [add_participant(tournament, u) for u in users]

    round1 = Round.objects.create(tournament=tournament, number=1, status=Round.Status.COMPLETED)
    p0, p1, p2, p3 = participants
    pairing_a = Pairing.objects.create(round=round1, board_number=1, white_player=p0.user, black_player=p1.user, result=Pairing.Result.WHITE_WIN)
    pairing_b = Pairing.objects.create(round=round1, board_number=2, white_player=p2.user, black_player=p3.user, result=Pairing.Result.DRAW)

    standings = {row['participant'].id: row for row in StandingsService.compute_standings(tournament)}
    past_pairings = [pairing_a, pairing_b]

    next_pairings = SwissPairingService.generate_next_round_pairings(tournament, participants, standings, past_pairings)
    played_pairs = {frozenset({w.id, b.id}) for w, b in next_pairings if b is not None}
    assert frozenset({p0.id, p1.id}) not in played_pairs
    assert frozenset({p2.id, p3.id}) not in played_pairs


@pytest.mark.django_db
def test_swiss_bye_goes_to_lowest_scorer_without_previous_bye():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher, fmt=Tournament.Format.SWISS, rounds_total=3)
    users = [make_user(f'p{i}', elo=1200 - i * 10) for i in range(5)]
    participants = [add_participant(tournament, u) for u in users]
    standings = {p.id: {'points': 0.0} for p in participants}

    pairings = SwissPairingService.generate_next_round_pairings(tournament, participants, standings, [])
    bye_entries = [w for w, b in pairings if b is None]
    assert len(bye_entries) == 1
    # Lowest rated participant (last by seed) should receive the bye.
    assert bye_entries[0].id == participants[-1].id


@pytest.mark.django_db
def test_swiss_does_not_give_same_player_two_byes():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher, fmt=Tournament.Format.SWISS, rounds_total=3)
    users = [make_user(f'p{i}', elo=1200 - i * 10) for i in range(5)]
    participants = [add_participant(tournament, u) for u in users]

    round1 = Round.objects.create(tournament=tournament, number=1, status=Round.Status.COMPLETED)
    lowest = participants[-1]
    bye_pairing = Pairing.objects.create(round=round1, board_number=1, white_player=lowest.user, is_bye=True, result=Pairing.Result.BYE)

    standings = {row['participant'].id: row for row in StandingsService.compute_standings(tournament)}
    past_pairings = [bye_pairing]

    pairings = SwissPairingService.generate_next_round_pairings(tournament, participants, standings, past_pairings)
    bye_entries = [w for w, b in pairings if b is None]
    assert len(bye_entries) == 1
    assert bye_entries[0].id != lowest.id


@pytest.mark.django_db
def test_swiss_color_assignment_balances_white_count():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher, fmt=Tournament.Format.SWISS, rounds_total=3)
    p0_user = make_user('alice', elo=1300)
    p1_user = make_user('bob', elo=1200)
    p0 = add_participant(tournament, p0_user)
    p1 = add_participant(tournament, p1_user)

    round1 = Round.objects.create(tournament=tournament, number=1, status=Round.Status.COMPLETED)
    # alice already played white once; bob has not played white yet.
    Pairing.objects.create(round=round1, board_number=1, white_player=p0.user, black_player=p1.user, result=Pairing.Result.DRAW)

    color_history = {p0.id: {'white': 1, 'black': 0}, p1.id: {'white': 0, 'black': 1}}
    white, black = SwissPairingService._assign_colors(p0, p1, color_history)
    assert white.id == p1.id  # bob should get white this time
    assert black.id == p0.id


# --- Standings / classification ---

@pytest.mark.django_db
def test_standings_points_wins_draws_losses():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    u1, u2, u3 = make_user('a'), make_user('b'), make_user('c')
    p1, p2, p3 = add_participant(tournament, u1), add_participant(tournament, u2), add_participant(tournament, u3)

    round1 = Round.objects.create(tournament=tournament, number=1, status=Round.Status.COMPLETED)
    Pairing.objects.create(round=round1, board_number=1, white_player=u1, black_player=u2, result=Pairing.Result.WHITE_WIN)
    Pairing.objects.create(round=round1, board_number=2, white_player=u3, black_player=None, is_bye=True, result=Pairing.Result.BYE)

    standings = {row['participant'].id: row for row in StandingsService.compute_standings(tournament)}
    assert standings[p1.id]['points'] == 1.0
    assert standings[p1.id]['wins'] == 1
    assert standings[p2.id]['points'] == 0.0
    assert standings[p2.id]['losses'] == 1
    assert standings[p3.id]['points'] == 1.0  # full point bye
    assert standings[p3.id]['byes'] == 1


@pytest.mark.django_db
def test_standings_draw_awards_half_point_each():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    u1, u2 = make_user('a'), make_user('b')
    p1, p2 = add_participant(tournament, u1), add_participant(tournament, u2)
    round1 = Round.objects.create(tournament=tournament, number=1, status=Round.Status.COMPLETED)
    Pairing.objects.create(round=round1, board_number=1, white_player=u1, black_player=u2, result=Pairing.Result.DRAW)

    standings = {row['participant'].id: row for row in StandingsService.compute_standings(tournament)}
    assert standings[p1.id]['points'] == 0.5
    assert standings[p2.id]['points'] == 0.5
    assert standings[p1.id]['draws'] == 1


@pytest.mark.django_db
def test_standings_buchholz_sums_opponents_points():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    u1, u2, u3, u4 = make_user('a'), make_user('b'), make_user('c'), make_user('d')
    p1, p2, p3, p4 = [add_participant(tournament, u) for u in [u1, u2, u3, u4]]

    round1 = Round.objects.create(tournament=tournament, number=1, status=Round.Status.COMPLETED)
    # a beats b; c beats d
    Pairing.objects.create(round=round1, board_number=1, white_player=u1, black_player=u2, result=Pairing.Result.WHITE_WIN)
    Pairing.objects.create(round=round1, board_number=2, white_player=u3, black_player=u4, result=Pairing.Result.WHITE_WIN)

    round2 = Round.objects.create(tournament=tournament, number=2, status=Round.Status.COMPLETED)
    # a beats c (a's opponents: b(0 pts), c(1 pt at time of calc) -> buchholz uses final totals)
    Pairing.objects.create(round=round2, board_number=1, white_player=u1, black_player=u3, result=Pairing.Result.WHITE_WIN)
    Pairing.objects.create(round=round2, board_number=2, white_player=u2, black_player=u4, result=Pairing.Result.DRAW)

    standings = {row['participant'].id: row for row in StandingsService.compute_standings(tournament)}
    # a: 2 wins = 2.0 points; opponents were b (0.5 total) and c (1.0 total) -> buchholz = 1.5
    assert standings[p1.id]['points'] == 2.0
    assert standings[p1.id]['buchholz'] == 1.5


@pytest.mark.django_db
def test_standings_ranking_orders_by_points_then_buchholz_then_wins():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    u1, u2 = make_user('a'), make_user('b')
    p1, p2 = add_participant(tournament, u1), add_participant(tournament, u2)
    round1 = Round.objects.create(tournament=tournament, number=1, status=Round.Status.COMPLETED)
    Pairing.objects.create(round=round1, board_number=1, white_player=u1, black_player=u2, result=Pairing.Result.WHITE_WIN)

    standings = StandingsService.compute_standings(tournament)
    assert standings[0]['participant'].id == p1.id
    assert standings[0]['rank'] == 1
    assert standings[1]['rank'] == 2


@pytest.mark.django_db
def test_standings_tied_players_share_rank():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    u1, u2, u3 = make_user('a'), make_user('b'), make_user('c')
    for u in [u1, u2, u3]:
        add_participant(tournament, u)
    # No games played: everyone tied at 0 points, 0 buchholz, 0 wins -> all rank 1.
    standings = StandingsService.compute_standings(tournament)
    assert all(row['rank'] == 1 for row in standings)


# --- Lifecycle: registration, start, rounds, incidents, finalize ---

@pytest.mark.django_db
def test_student_can_register_and_withdraw():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    tournament = make_tournament(teacher)

    participant = TournamentService.register(tournament, student)
    assert participant.status == TournamentParticipant.Status.REGISTERED

    TournamentService.withdraw(tournament, student)
    participant.refresh_from_db()
    assert participant.status == TournamentParticipant.Status.WITHDRAWN


@pytest.mark.django_db
def test_cannot_register_twice():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    tournament = make_tournament(teacher)
    TournamentService.register(tournament, student)
    with pytest.raises(TournamentError):
        TournamentService.register(tournament, student)


@pytest.mark.django_db
def test_cannot_start_with_fewer_than_two_participants():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    student = make_user('estudiante1')
    TournamentService.register(tournament, student)
    with pytest.raises(TournamentError):
        TournamentService.start_tournament(tournament)


@pytest.mark.django_db
def test_start_round_robin_creates_all_rounds_and_opens_first_with_games():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    students = [make_user(f'e{i}') for i in range(4)]
    for s in students:
        TournamentService.register(tournament, s)

    TournamentService.start_tournament(tournament)
    tournament.refresh_from_db()
    assert tournament.status == Tournament.Status.IN_PROGRESS
    assert tournament.rounds.count() == 3
    round1 = tournament.rounds.get(number=1)
    assert round1.status == Round.Status.IN_PROGRESS
    assert round1.pairings.filter(game__isnull=False).count() == 2
    for pairing in round1.pairings.all():
        assert pairing.game.is_competitive is True
        assert pairing.game.status == Game.Status.IN_PROGRESS

    round2 = tournament.rounds.get(number=2)
    assert round2.status == Round.Status.PENDING
    assert round2.pairings.filter(game__isnull=False).count() == 0  # games not created until opened


@pytest.mark.django_db
def test_swiss_requires_rounds_total_before_starting():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher, fmt=Tournament.Format.SWISS, rounds_total=None)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    with pytest.raises(TournamentError):
        TournamentService.start_tournament(tournament)


@pytest.mark.django_db
def test_close_round_requires_all_results_decided():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    round1 = tournament.rounds.get(number=1)

    with pytest.raises(TournamentError):
        TournamentService.close_round(tournament, round1)


@pytest.mark.django_db
def test_close_round_succeeds_after_recording_result():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    round1 = tournament.rounds.get(number=1)
    pairing = round1.pairings.first()
    TournamentService.record_incident(pairing, white_absent=True)

    TournamentService.close_round(tournament, round1)
    round1.refresh_from_db()
    assert round1.status == Round.Status.COMPLETED


@pytest.mark.django_db
def test_record_incident_single_absence_awards_win_to_present_player():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    pairing = tournament.rounds.get(number=1).pairings.first()

    TournamentService.record_incident(pairing, black_absent=True)
    pairing.refresh_from_db()
    assert pairing.result == Pairing.Result.WHITE_WIN
    assert pairing.black_absent is True


@pytest.mark.django_db
def test_record_incident_double_absence():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    pairing = tournament.rounds.get(number=1).pairings.first()

    TournamentService.record_incident(pairing, white_absent=True, black_absent=True)
    pairing.refresh_from_db()
    assert pairing.result == Pairing.Result.DOUBLE_FORFEIT


@pytest.mark.django_db
def test_cannot_record_incident_twice():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    pairing = tournament.rounds.get(number=1).pairings.first()
    TournamentService.record_incident(pairing, white_absent=True)

    with pytest.raises(TournamentError):
        TournamentService.record_incident(pairing, black_absent=True)


@pytest.mark.django_db
def test_finalize_requires_all_rounds_completed():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)

    with pytest.raises(TournamentError):
        TournamentService.finalize_tournament(tournament)

    pairing = tournament.rounds.get(number=1).pairings.first()
    TournamentService.record_incident(pairing, white_absent=True)
    TournamentService.close_round(tournament, tournament.rounds.get(number=1))
    TournamentService.finalize_tournament(tournament)
    tournament.refresh_from_db()
    assert tournament.status == Tournament.Status.COMPLETED


@pytest.mark.django_db
def test_sync_finished_games_updates_pairing_result():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    pairing = tournament.rounds.get(number=1).pairings.first()

    game = pairing.game
    game.status = Game.Status.FINISHED
    game.winner = Game.Winner.WHITE
    game.save()

    TournamentService.sync_finished_games(tournament)
    pairing.refresh_from_db()
    assert pairing.result == Pairing.Result.WHITE_WIN


# --- View-level permissions ---

@pytest.mark.django_db
def test_non_organizer_cannot_create_tournament(client):
    make_user('estudiante1')
    client.login(username='estudiante1', password='password123')
    response = client.post(reverse('tournament_create'), {'name': 'Torneo Falso'})
    assert response.status_code == 403
    assert not Tournament.objects.filter(name='Torneo Falso').exists()


@pytest.mark.django_db
def test_teacher_can_create_tournament(client):
    make_user('docente1', role=CustomUser.Role.TEACHER)
    client.login(username='docente1', password='password123')
    response = client.post(reverse('tournament_create'), {
        'name': 'Copa Escolar', 'format': Tournament.Format.ROUND_ROBIN,
        'time_control_minutes': 15, 'time_control_increment': 0,
    })
    assert response.status_code == 302
    assert Tournament.objects.filter(name='Copa Escolar').exists()


@pytest.mark.django_db
def test_non_organizer_cannot_start_tournament(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    other_teacher = make_user('docente2', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))

    client.login(username='docente2', password='password123')
    response = client.post(reverse('tournament_start', kwargs={'tournament_id': tournament.id}))
    assert response.status_code == 403
    tournament.refresh_from_db()
    assert tournament.status != Tournament.Status.IN_PROGRESS


@pytest.mark.django_db
def test_organizer_can_start_tournament_via_view(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))

    client.login(username='docente1', password='password123')
    response = client.post(reverse('tournament_start', kwargs={'tournament_id': tournament.id}))
    assert response.status_code == 302
    tournament.refresh_from_db()
    assert tournament.status == Tournament.Status.IN_PROGRESS


@pytest.mark.django_db
def test_student_can_register_via_view(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    make_user('estudiante1')
    tournament = make_tournament(teacher)

    client.login(username='estudiante1', password='password123')
    response = client.post(reverse('tournament_register', kwargs={'tournament_id': tournament.id}))
    assert response.status_code == 302
    assert TournamentParticipant.objects.filter(tournament=tournament, user__username='estudiante1').exists()


@pytest.mark.django_db
def test_non_organizer_cannot_record_incident(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    pairing = tournament.rounds.get(number=1).pairings.first()
    round1 = tournament.rounds.get(number=1)

    client.login(username='estudiante1', password='password123')
    response = client.post(
        reverse('pairing_record_incident', kwargs={'tournament_id': tournament.id, 'round_id': round1.id, 'pairing_id': pairing.id}),
        {'white_absent': 'true', 'black_absent': 'false'}
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_analysis_blocked_during_in_progress_tournament_game(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    pairing = tournament.rounds.get(number=1).pairings.first()

    client.login(username='e0', password='password123')
    response = client.get(reverse('start_game_analysis', kwargs={'game_id': pairing.game.id}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_analysis_allowed_after_tournament_game_finishes(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    tournament = make_tournament(teacher)
    for i in range(2):
        TournamentService.register(tournament, make_user(f'e{i}'))
    TournamentService.start_tournament(tournament)
    pairing = tournament.rounds.get(number=1).pairings.first()

    game = pairing.game
    game.status = Game.Status.FINISHED
    game.winner = Game.Winner.WHITE
    game.save()

    client.login(username='e0', password='password123')
    response = client.get(reverse('start_game_analysis', kwargs={'game_id': game.id}))
    assert response.status_code == 302
