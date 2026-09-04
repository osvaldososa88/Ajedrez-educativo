import json
import chess
import pytest
from django.urls import reverse
from apps.accounts.models import CustomUser
from apps.games.models import Game
from apps.analysis.models import AnalysisJob
from apps.training.models import Puzzle, PuzzleAttempt
from apps.classrooms.models import Classroom, ClassroomEnrollment, ClassroomInvitation, Activity, ActivityObjective
from apps.classrooms.services import ActivityProgressService, ClassroomService, ClassroomAccessError


def make_user(username, role=CustomUser.Role.STUDENT):
    return CustomUser.objects.create_user(username=username, password='password123', role=role)


def make_classroom(teacher, **overrides):
    classroom = Classroom.objects.create(
        name=overrides.get('name', 'Aula de Prueba'),
        description=overrides.get('description', ''),
        created_by=teacher,
    )
    classroom.teachers.add(teacher)
    return classroom


def enroll(classroom, student, is_active=True):
    return ClassroomEnrollment.objects.create(classroom=classroom, student=student, is_active=is_active)


def make_published_puzzle(author):
    return Puzzle.objects.create(
        title="Problema del aula",
        author=author,
        initial_fen=chess.STARTING_FEN,
        solution_moves=["e2e4"],
        status=Puzzle.Status.PUBLISHED,
    )


# --- Classroom creation & permissions ---

@pytest.mark.django_db
def test_teacher_can_create_classroom(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    client.login(username='docente1', password='password123')

    response = client.post(reverse('classroom_create'), {'name': 'Ajedrez 5to A', 'description': 'Curso 2026'})
    assert response.status_code == 302

    classroom = Classroom.objects.get(name='Ajedrez 5to A')
    assert classroom.teachers.filter(id=teacher.id).exists()
    assert len(classroom.join_code) > 0


@pytest.mark.django_db
def test_student_cannot_create_classroom(client):
    make_user('estudiante1')
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('classroom_create'), {'name': 'Aula Falsa'})
    assert response.status_code == 403
    assert not Classroom.objects.filter(name='Aula Falsa').exists()


@pytest.mark.django_db
def test_classroom_create_requires_login(client):
    response = client.get(reverse('classroom_create'))
    assert response.status_code == 302


# --- Enrollment: join by code & invitations ---

@pytest.mark.django_db
def test_student_can_join_classroom_by_code(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('classroom_join'), {'join_code': classroom.join_code})
    assert response.status_code == 302
    assert ClassroomEnrollment.objects.filter(classroom=classroom, student=student, is_active=True).exists()


@pytest.mark.django_db
def test_join_with_invalid_code_does_not_enroll(client):
    make_user('estudiante1')
    client.login(username='estudiante1', password='password123')

    response = client.post(reverse('classroom_join'), {'join_code': 'NOEXISTE'})
    assert response.status_code == 302
    assert ClassroomEnrollment.objects.count() == 0


@pytest.mark.django_db
def test_teacher_can_invite_student_and_student_can_accept(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)

    client.login(username='docente1', password='password123')
    response = client.post(reverse('classroom_invite_student', kwargs={'classroom_id': classroom.id}), {'username': 'estudiante1'})
    assert response.status_code == 200
    assert response.json()['success'] is True
    invitation = ClassroomInvitation.objects.get(classroom=classroom, student=student)
    assert invitation.status == ClassroomInvitation.Status.PENDING

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('classroom_invitations'))
    assert response.status_code == 200
    assert invitation in response.context['invitations']

    response = client.get(reverse('classroom_invitation_accept', kwargs={'invitation_id': invitation.id}))
    assert response.status_code == 302
    invitation.refresh_from_db()
    assert invitation.status == ClassroomInvitation.Status.ACCEPTED
    assert ClassroomEnrollment.objects.filter(classroom=classroom, student=student, is_active=True).exists()


@pytest.mark.django_db
def test_student_can_decline_invitation(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    invitation = ClassroomInvitation.objects.create(classroom=classroom, student=student, invited_by=teacher)

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('classroom_invitation_decline', kwargs={'invitation_id': invitation.id}))
    assert response.status_code == 302
    invitation.refresh_from_db()
    assert invitation.status == ClassroomInvitation.Status.DECLINED
    assert not ClassroomEnrollment.objects.filter(classroom=classroom, student=student).exists()


@pytest.mark.django_db
def test_other_student_cannot_accept_foreign_invitation(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    other = make_user('estudiante2')
    classroom = make_classroom(teacher)
    invitation = ClassroomInvitation.objects.create(classroom=classroom, student=student, invited_by=teacher)

    with pytest.raises(ClassroomAccessError):
        ClassroomService.accept_invitation(invitation, other)


@pytest.mark.django_db
def test_non_teacher_cannot_invite_student(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    make_user('estudiante1')
    make_user('estudiante2')
    classroom = make_classroom(teacher)

    client.login(username='estudiante2', password='password123')
    response = client.post(reverse('classroom_invite_student', kwargs={'classroom_id': classroom.id}), {'username': 'estudiante1'})
    assert response.status_code == 403


@pytest.mark.django_db
def test_invite_already_enrolled_student_fails(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    client.login(username='docente1', password='password123')
    response = client.post(reverse('classroom_invite_student', kwargs={'classroom_id': classroom.id}), {'username': 'estudiante1'})
    assert response.status_code == 400


@pytest.mark.django_db
def test_teacher_can_remove_student(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    client.login(username='docente1', password='password123')
    response = client.post(reverse('classroom_remove_student', kwargs={'classroom_id': classroom.id, 'user_id': student.id}))
    assert response.status_code == 200
    assert not ClassroomEnrollment.objects.filter(classroom=classroom, student=student, is_active=True).exists()


@pytest.mark.django_db
def test_student_cannot_remove_another_student(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    other = make_user('estudiante2')
    classroom = make_classroom(teacher)
    enroll(classroom, student)
    enroll(classroom, other)

    client.login(username='estudiante2', password='password123')
    response = client.post(reverse('classroom_remove_student', kwargs={'classroom_id': classroom.id, 'user_id': student.id}))
    assert response.status_code == 403
    assert ClassroomEnrollment.objects.filter(classroom=classroom, student=student, is_active=True).exists()


# --- Classroom detail visibility ---

@pytest.mark.django_db
def test_non_member_cannot_view_classroom_detail(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    make_user('estudiante1')
    classroom = make_classroom(teacher)

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('classroom_detail', kwargs={'classroom_id': classroom.id}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_enrolled_student_can_view_classroom_detail_without_roster_management(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('classroom_detail', kwargs={'classroom_id': classroom.id}))
    assert response.status_code == 200
    assert response.context['is_teacher'] is False
    assert 'enrollments' not in response.context


# --- Activities: creation & visibility ---

@pytest.mark.django_db
def test_teacher_can_create_activity_with_objectives(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    client.login(username='docente1', password='password123')
    response = client.post(reverse('activity_create', kwargs={'classroom_id': classroom.id}), {
        'title': 'Semana 3 - Finales de peones',
        'description': 'Resolver 5 problemas, jugar 2 partidas',
        'objective_type': ['SOLVE_PUZZLES', 'PLAY_GAMES'],
        'objective_target': ['5', '2'],
    })
    assert response.status_code == 302

    activity = Activity.objects.get(title='Semana 3 - Finales de peones')
    assert activity.classroom == classroom
    objectives = list(activity.objectives.all())
    assert len(objectives) == 2
    assert {(o.objective_type, o.target_count) for o in objectives} == {
        ('SOLVE_PUZZLES', 5), ('PLAY_GAMES', 2)
    }


@pytest.mark.django_db
def test_non_teacher_cannot_create_activity(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    client.login(username='estudiante1', password='password123')
    response = client.post(reverse('activity_create', kwargs={'classroom_id': classroom.id}), {'title': 'Actividad falsa'})
    assert response.status_code == 403
    assert not Activity.objects.filter(title='Actividad falsa').exists()


@pytest.mark.django_db
def test_activity_visible_to_all_students_when_not_restricted(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)
    activity = Activity.objects.create(classroom=classroom, created_by=teacher, title='Actividad General')

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('activity_detail', kwargs={'classroom_id': classroom.id, 'activity_id': activity.id}))
    assert response.status_code == 200
    assert 'my_progress' in response.context


@pytest.mark.django_db
def test_activity_hidden_from_unassigned_student(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    other_student = make_user('estudiante2')
    classroom = make_classroom(teacher)
    enroll(classroom, student)
    enroll(classroom, other_student)

    activity = Activity.objects.create(classroom=classroom, created_by=teacher, title='Actividad Restringida')
    activity.assigned_students.add(student)  # only this student

    client.login(username='estudiante2', password='password123')
    response = client.get(reverse('activity_detail', kwargs={'classroom_id': classroom.id, 'activity_id': activity.id}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_activity_detail_teacher_sees_all_students_progress(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student1 = make_user('estudiante1')
    student2 = make_user('estudiante2')
    classroom = make_classroom(teacher)
    enroll(classroom, student1)
    enroll(classroom, student2)
    activity = Activity.objects.create(classroom=classroom, created_by=teacher, title='Actividad General')

    client.login(username='docente1', password='password123')
    response = client.get(reverse('activity_detail', kwargs={'classroom_id': classroom.id, 'activity_id': activity.id}))
    assert response.status_code == 200
    assert 'progress_by_student' in response.context
    assert len(response.context['progress_by_student']) == 2


# --- Progress computation ---

@pytest.mark.django_db
def test_progress_service_counts_solved_puzzles_and_games():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    puzzle = make_published_puzzle(teacher)
    activity = Activity.objects.create(classroom=classroom, created_by=teacher, title='Actividad Mixta')
    ActivityObjective.objects.create(activity=activity, objective_type=ActivityObjective.ObjectiveType.SOLVE_PUZZLES, target_count=2)
    ActivityObjective.objects.create(activity=activity, objective_type=ActivityObjective.ObjectiveType.PLAY_GAMES, target_count=1)

    PuzzleAttempt.objects.create(user=student, puzzle=puzzle, solved=True)
    opponent = make_user('estudiante2')
    Game.objects.create(white_player=student, black_player=opponent, status=Game.Status.FINISHED)

    progress = ActivityProgressService.compute_progress(activity, student)
    achieved = {row['objective'].objective_type: row['achieved'] for row in progress['objectives']}
    assert achieved['SOLVE_PUZZLES'] == 1
    assert achieved['PLAY_GAMES'] == 1
    assert progress['is_complete'] is False  # solve target is 2, only 1 achieved


@pytest.mark.django_db
def test_progress_service_marks_activity_complete_when_all_objectives_met():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    puzzle = make_published_puzzle(teacher)
    activity = Activity.objects.create(classroom=classroom, created_by=teacher, title='Actividad Simple')
    ActivityObjective.objects.create(activity=activity, objective_type=ActivityObjective.ObjectiveType.SOLVE_PUZZLES, target_count=1)

    PuzzleAttempt.objects.create(user=student, puzzle=puzzle, solved=True)

    progress = ActivityProgressService.compute_progress(activity, student)
    assert progress['is_complete'] is True


@pytest.mark.django_db
def test_progress_service_counts_created_puzzles_and_analyzed_games():
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    activity = Activity.objects.create(classroom=classroom, created_by=teacher, title='Actividad Creativa')
    ActivityObjective.objects.create(activity=activity, objective_type=ActivityObjective.ObjectiveType.CREATE_PUZZLE, target_count=1)
    ActivityObjective.objects.create(activity=activity, objective_type=ActivityObjective.ObjectiveType.ANALYZE_GAME, target_count=1)

    make_published_puzzle(student)  # student authors a puzzle
    AnalysisJob.objects.create(user=student, status=AnalysisJob.Status.COMPLETED)

    progress = ActivityProgressService.compute_progress(activity, student)
    assert progress['is_complete'] is True


# --- Stats & privacy ---

@pytest.mark.django_db
def test_classroom_stats_view_is_teacher_only(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('classroom_stats', kwargs={'classroom_id': classroom.id}))
    assert response.status_code == 403

    client.login(username='docente1', password='password123')
    response = client.get(reverse('classroom_stats', kwargs={'classroom_id': classroom.id}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_student_can_view_own_progress_detail(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    client.login(username='estudiante1', password='password123')
    response = client.get(reverse('classroom_student_progress', kwargs={'classroom_id': classroom.id, 'user_id': student.id}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_student_cannot_view_another_students_progress(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student1 = make_user('estudiante1')
    student2 = make_user('estudiante2')
    classroom = make_classroom(teacher)
    enroll(classroom, student1)
    enroll(classroom, student2)

    client.login(username='estudiante2', password='password123')
    response = client.get(reverse('classroom_student_progress', kwargs={'classroom_id': classroom.id, 'user_id': student1.id}))
    assert response.status_code == 403


@pytest.mark.django_db
def test_teacher_can_view_any_enrolled_students_progress(client):
    teacher = make_user('docente1', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom = make_classroom(teacher)
    enroll(classroom, student)

    client.login(username='docente1', password='password123')
    response = client.get(reverse('classroom_student_progress', kwargs={'classroom_id': classroom.id, 'user_id': student.id}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_teacher_from_other_classroom_cannot_view_unrelated_student_progress(client):
    teacher_a = make_user('docenteA', role=CustomUser.Role.TEACHER)
    teacher_b = make_user('docenteB', role=CustomUser.Role.TEACHER)
    student = make_user('estudiante1')
    classroom_a = make_classroom(teacher_a)
    classroom_b = make_classroom(teacher_b, name='Otra Aula')
    enroll(classroom_a, student)
    # student is NOT enrolled in classroom_b

    client.login(username='docenteB', password='password123')
    response = client.get(reverse('classroom_student_progress', kwargs={'classroom_id': classroom_b.id, 'user_id': student.id}))
    assert response.status_code == 403
