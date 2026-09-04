import json
import chess
import pytest
from django.urls import reverse
from apps.accounts.models import CustomUser
from apps.training.models import Puzzle, PuzzleFavorite, PuzzleRating
from apps.training.services import PuzzleValidationService

MATE_IN_1_FEN = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 1 3"


def make_user(username, role=CustomUser.Role.STUDENT):
    return CustomUser.objects.create_user(username=username, password='password123', role=role)


def create_draft_puzzle(author, **overrides):
    defaults = dict(
        title="Problema de prueba",
        description="Descripción",
        author=author,
        initial_fen=chess.STARTING_FEN,
        side_to_move=Puzzle.SideToMove.WHITE,
        category=Puzzle.Category.TACTICS,
        theme=Puzzle.Theme.FORK,
        difficulty=Puzzle.Difficulty.BEGINNER,
        objective=Puzzle.Objective.FIND_MOVE,
        solution_moves=["e2e4"],
        status=Puzzle.Status.DRAFT,
    )
    defaults.update(overrides)
    return Puzzle.objects.create(**defaults)


# --- Creation ---

@pytest.mark.django_db
def test_student_can_create_puzzle_as_draft(client):
    student = make_user('estudiante1')
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('puzzle_create'), {
        'title': 'Mi primer problema',
        'description': 'Encuentra la mejor jugada',
        'initial_fen': chess.STARTING_FEN,
        'side_to_move': 'WHITE',
        'category': Puzzle.Category.TACTICS,
        'theme': Puzzle.Theme.FORK,
        'difficulty': Puzzle.Difficulty.BEGINNER,
        'objective': Puzzle.Objective.FIND_MOVE,
        'solution_moves': json.dumps(['e2e4']),
        'variations_json': json.dumps({}),
        'hints': json.dumps(['Ataca el centro']),
    })
    assert response.status_code == 302

    puzzle = Puzzle.objects.get(title='Mi primer problema')
    assert puzzle.author == student
    assert puzzle.status == Puzzle.Status.DRAFT
    assert puzzle.solution_moves == ['e2e4']
    assert puzzle.hints == ['Ataca el centro']


@pytest.mark.django_db
def test_create_puzzle_with_invalid_fen_is_rejected(client):
    make_user('estudiante1')
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('puzzle_create'), {
        'title': 'Posición inválida',
        'initial_fen': 'no-es-un-fen',
        'side_to_move': 'WHITE',
        'category': Puzzle.Category.TACTICS,
        'theme': Puzzle.Theme.FORK,
        'difficulty': Puzzle.Difficulty.BEGINNER,
        'objective': Puzzle.Objective.FIND_MOVE,
        'solution_moves': json.dumps(['e2e4']),
    })
    assert response.status_code == 400
    assert not Puzzle.objects.filter(title='Posición inválida').exists()


@pytest.mark.django_db
def test_create_puzzle_requires_login(client):
    response = client.post(reverse('puzzle_create'), {'title': 'x'})
    assert response.status_code == 302  # redirected to login


# --- Validation service ---

@pytest.mark.django_db
def test_validation_fails_when_no_solution_moves():
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=[])
    errors = PuzzleValidationService.validate_for_submission(puzzle)
    assert any('solución' in e for e in errors)


@pytest.mark.django_db
def test_validation_fails_on_illegal_solution_move():
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e5'])  # illegal - blocked path
    errors = PuzzleValidationService.validate_for_submission(puzzle)
    assert any('ilegal' in e for e in errors)


@pytest.mark.django_db
def test_validation_fails_on_side_to_move_mismatch():
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, side_to_move=Puzzle.SideToMove.BLACK, solution_moves=['e2e4'])
    errors = PuzzleValidationService.validate_for_submission(puzzle)
    assert any('turno' in e for e in errors)


@pytest.mark.django_db
def test_validation_passes_for_reproducible_solution():
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4', 'e7e5', 'g1f3'])
    errors = PuzzleValidationService.validate_for_submission(puzzle)
    assert errors == []


@pytest.mark.django_db
def test_validation_flags_illegal_variation():
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], variations_json={"0": ["e2e5"]})
    errors = PuzzleValidationService.validate_for_submission(puzzle)
    assert any('variante' in e for e in errors)


# --- Submission for review ---

@pytest.mark.django_db
def test_submit_for_review_fails_without_valid_solution(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=[])
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('puzzle_submit_review', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 400
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.DRAFT


@pytest.mark.django_db
def test_submit_for_review_success(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'])
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('puzzle_submit_review', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.IN_REVIEW


@pytest.mark.django_db
def test_other_student_cannot_submit_foreign_puzzle_for_review(client):
    author = make_user('estudiante1')
    other = make_user('estudiante2')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'])
    client.login(username='estudiante2', password='password123')

    response = client.post(reverse('puzzle_submit_review', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 403


# --- Moderation: approve / reject ---

@pytest.mark.django_db
def test_teacher_can_approve_puzzle_in_review(client):
    author = make_user('estudiante1')
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.IN_REVIEW)

    client.login(username='docente1', password='password123')
    response = client.post(reverse('puzzle_approve', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.PUBLISHED
    assert puzzle.moderated_by == teacher
    assert puzzle.reviewed_at is not None


@pytest.mark.django_db
def test_student_cannot_approve_puzzle(client):
    author = make_user('estudiante1')
    other_student = make_user('estudiante2')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.IN_REVIEW)

    client.login(username='estudiante2', password='password123')
    response = client.post(reverse('puzzle_approve', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 403
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.IN_REVIEW


@pytest.mark.django_db
def test_approve_fails_if_puzzle_no_longer_valid(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=[], status=Puzzle.Status.IN_REVIEW)

    client.login(username='docente1', password='password123')
    response = client.post(reverse('puzzle_approve', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 400
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.IN_REVIEW


@pytest.mark.django_db
def test_teacher_can_reject_with_reason(client):
    author = make_user('estudiante1')
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.IN_REVIEW)

    client.login(username='docente1', password='password123')
    response = client.post(reverse('puzzle_reject', kwargs={'puzzle_id': puzzle.id}), {'reason': 'FEN poco claro'})
    assert response.status_code == 200
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.REJECTED
    assert puzzle.moderation_notes == 'FEN poco claro'
    assert puzzle.moderated_by == teacher


@pytest.mark.django_db
def test_reject_without_reason_fails(client):
    author = make_user('estudiante1')
    make_user('docente1', role=CustomUser.Role.TEACHER)
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.IN_REVIEW)

    client.login(username='docente1', password='password123')
    response = client.post(reverse('puzzle_reject', kwargs={'puzzle_id': puzzle.id}), {'reason': ''})
    assert response.status_code == 400
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.IN_REVIEW


@pytest.mark.django_db
def test_rejected_puzzle_can_be_edited_and_resubmitted(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.REJECTED, moderation_notes='Corrige el título')
    client.login(username='estudiante1', password='password123')

    response = client.get(reverse('puzzle_edit', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200

    response = client.post(reverse('puzzle_submit_review', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.IN_REVIEW


# --- Editing / deletion permissions ---

@pytest.mark.django_db
def test_author_can_edit_own_draft_puzzle(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author)
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('puzzle_edit', kwargs={'puzzle_id': puzzle.id}), {
        'title': 'Título Actualizado',
        'description': '',
        'initial_fen': chess.STARTING_FEN,
        'side_to_move': 'WHITE',
        'category': Puzzle.Category.TACTICS,
        'theme': Puzzle.Theme.FORK,
        'difficulty': Puzzle.Difficulty.BEGINNER,
        'objective': Puzzle.Objective.FIND_MOVE,
        'solution_moves': json.dumps(['e2e4']),
    })
    assert response.status_code == 302
    puzzle.refresh_from_db()
    assert puzzle.title == 'Título Actualizado'


@pytest.mark.django_db
def test_author_cannot_edit_puzzle_once_in_review(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.IN_REVIEW)
    client.login(username='estudiante1', password='password123')

    response = client.get(reverse('puzzle_edit', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_other_student_cannot_edit_foreign_puzzle(client):
    author = make_user('estudiante1')
    make_user('estudiante2')
    puzzle = create_draft_puzzle(author)
    client.login(username='estudiante2', password='password123')

    response = client.get(reverse('puzzle_edit', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_teacher_can_edit_any_puzzle_regardless_of_status(client):
    author = make_user('estudiante1')
    make_user('docente1', role=CustomUser.Role.TEACHER)
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='docente1', password='password123')

    response = client.get(reverse('puzzle_edit', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_author_can_delete_own_draft_puzzle(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author)
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('puzzle_delete', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 302
    assert not Puzzle.objects.filter(id=puzzle.id).exists()


@pytest.mark.django_db
def test_author_cannot_delete_published_puzzle(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('puzzle_delete', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 403
    assert Puzzle.objects.filter(id=puzzle.id).exists()


@pytest.mark.django_db
def test_other_student_cannot_delete_foreign_puzzle(client):
    author = make_user('estudiante1')
    make_user('estudiante2')
    puzzle = create_draft_puzzle(author)
    client.login(username='estudiante2', password='password123')

    response = client.post(reverse('puzzle_delete', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 403
    assert Puzzle.objects.filter(id=puzzle.id).exists()


@pytest.mark.django_db
def test_teacher_can_delete_any_puzzle(client):
    author = make_user('estudiante1')
    make_user('docente1', role=CustomUser.Role.TEACHER)
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='docente1', password='password123')

    response = client.post(reverse('puzzle_delete', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 302
    assert not Puzzle.objects.filter(id=puzzle.id).exists()


# --- Archiving ---

@pytest.mark.django_db
def test_author_can_archive_own_published_puzzle(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('puzzle_archive', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200
    puzzle.refresh_from_db()
    assert puzzle.status == Puzzle.Status.ARCHIVED


@pytest.mark.django_db
def test_other_student_cannot_archive_foreign_puzzle(client):
    author = make_user('estudiante1')
    make_user('estudiante2')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='estudiante2', password='password123')

    response = client.post(reverse('puzzle_archive', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 403


# --- Community: favorites & ratings ---

@pytest.mark.django_db
def test_toggle_favorite_adds_and_removes(client):
    author = make_user('estudiante1')
    other = make_user('estudiante2')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='estudiante2', password='password123')

    response = client.post(reverse('puzzle_toggle_favorite', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200
    assert response.json()['favorited'] is True
    assert PuzzleFavorite.objects.filter(user=other, puzzle=puzzle).exists()

    response2 = client.post(reverse('puzzle_toggle_favorite', kwargs={'puzzle_id': puzzle.id}))
    assert response2.json()['favorited'] is False
    assert not PuzzleFavorite.objects.filter(user=other, puzzle=puzzle).exists()


@pytest.mark.django_db
def test_favorites_list_view_shows_only_favorited(client):
    author = make_user('estudiante1')
    make_user('estudiante2')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='estudiante2', password='password123')
    client.post(reverse('puzzle_toggle_favorite', kwargs={'puzzle_id': puzzle.id}))

    response = client.get(reverse('puzzle_favorites'))
    assert response.status_code == 200
    assert puzzle in response.context['puzzles']


@pytest.mark.django_db
def test_rate_puzzle_updates_average(client):
    author = make_user('estudiante1')
    rater = make_user('estudiante2')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='estudiante2', password='password123')

    response = client.post(
        reverse('puzzle_rate', kwargs={'puzzle_id': puzzle.id}),
        data=json.dumps({'value': 4}),
        content_type='application/json'
    )
    assert response.status_code == 200
    assert response.json()['average_rating'] == 4.0
    assert PuzzleRating.objects.get(user=rater, puzzle=puzzle).value == 4


@pytest.mark.django_db
def test_rate_puzzle_invalid_value_rejected(client):
    author = make_user('estudiante1')
    make_user('estudiante2')
    puzzle = create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.PUBLISHED)
    client.login(username='estudiante2', password='password123')

    response = client.post(
        reverse('puzzle_rate', kwargs={'puzzle_id': puzzle.id}),
        data=json.dumps({'value': 9}),
        content_type='application/json'
    )
    assert response.status_code == 400
    assert not PuzzleRating.objects.filter(puzzle=puzzle).exists()


# --- Listings / permissions on views ---

@pytest.mark.django_db
def test_my_puzzles_lists_only_own(client):
    author = make_user('estudiante1')
    other = make_user('estudiante2')
    create_draft_puzzle(author)
    create_draft_puzzle(other)
    client.login(username='estudiante1', password='password123')

    response = client.get(reverse('my_puzzles'))
    assert response.status_code == 200
    assert response.context['puzzles'].count() == 1


@pytest.mark.django_db
def test_moderation_queue_requires_moderator(client):
    make_user('estudiante1')
    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('puzzle_moderation'))
    assert response.status_code == 403


@pytest.mark.django_db
def test_moderation_queue_lists_only_in_review(client):
    author = make_user('estudiante1')
    make_user('docente1', role=CustomUser.Role.TEACHER)
    create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.IN_REVIEW)
    create_draft_puzzle(author, solution_moves=['e2e4'], status=Puzzle.Status.DRAFT)
    client.login(username='docente1', password='password123')

    response = client.get(reverse('puzzle_moderation'))
    assert response.status_code == 200
    assert response.context['puzzles'].count() == 1


@pytest.mark.django_db
def test_draft_puzzle_not_visible_to_other_students_in_dashboard(client):
    author = make_user('estudiante1')
    other = make_user('estudiante2')
    create_draft_puzzle(author)  # DRAFT, not published
    client.login(username='estudiante2', password='password123')

    response = client.get(reverse('training_dashboard'))
    assert response.status_code == 200
    assert response.context['puzzles'].count() == 0


@pytest.mark.django_db
def test_author_can_preview_own_draft_puzzle_detail(client):
    author = make_user('estudiante1')
    puzzle = create_draft_puzzle(author)
    client.login(username='estudiante1', password='password123')

    response = client.get(reverse('puzzle_detail', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_other_student_cannot_preview_foreign_draft_puzzle_detail(client):
    author = make_user('estudiante1')
    make_user('estudiante2')
    puzzle = create_draft_puzzle(author)
    client.login(username='estudiante2', password='password123')

    response = client.get(reverse('puzzle_detail', kwargs={'puzzle_id': puzzle.id}))
    assert response.status_code == 404
