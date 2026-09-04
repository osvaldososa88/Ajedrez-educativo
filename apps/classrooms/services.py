from django.utils import timezone
from django.db.models import Q
from apps.games.models import Game
from apps.analysis.models import AnalysisJob
from apps.training.models import Puzzle, PuzzleAttempt, UserTrainingStats
from .models import Classroom, ClassroomEnrollment, ClassroomInvitation, Activity, ActivityObjective


class ClassroomAccessError(Exception):
    """Raised when an enrollment/invitation action is not permitted for the given users."""


class ClassroomService:
    @staticmethod
    def join_by_code(user, join_code: str) -> Classroom:
        try:
            classroom = Classroom.objects.get(join_code=join_code.strip().upper(), is_active=True)
        except Classroom.DoesNotExist as exc:
            raise ClassroomAccessError("Código de acceso inválido o aula inactiva.") from exc

        if classroom.is_teacher(user):
            raise ClassroomAccessError("Ya eres docente de esta aula.")

        enrollment, created = ClassroomEnrollment.objects.get_or_create(
            classroom=classroom, student=user, defaults={'is_active': True}
        )
        if not created and not enrollment.is_active:
            enrollment.is_active = True
            enrollment.save(update_fields=['is_active'])
        return classroom

    @staticmethod
    def invite_student(classroom: Classroom, invited_by, student) -> ClassroomInvitation:
        if classroom.enrollments.filter(student=student, is_active=True).exists():
            raise ClassroomAccessError("El estudiante ya está inscrito en esta aula.")
        if ClassroomInvitation.objects.filter(classroom=classroom, student=student, status=ClassroomInvitation.Status.PENDING).exists():
            raise ClassroomAccessError("Ya existe una invitación pendiente para este estudiante.")

        return ClassroomInvitation.objects.create(classroom=classroom, student=student, invited_by=invited_by)

    @staticmethod
    def accept_invitation(invitation: ClassroomInvitation, user):
        if invitation.student_id != user.id:
            raise ClassroomAccessError("Esta invitación no te pertenece.")
        if invitation.status != ClassroomInvitation.Status.PENDING:
            raise ClassroomAccessError("Esta invitación ya fue respondida.")

        invitation.status = ClassroomInvitation.Status.ACCEPTED
        invitation.responded_at = timezone.now()
        invitation.save()

        ClassroomEnrollment.objects.get_or_create(
            classroom=invitation.classroom, student=user, defaults={'is_active': True}
        )
        return invitation

    @staticmethod
    def decline_invitation(invitation: ClassroomInvitation, user):
        if invitation.student_id != user.id:
            raise ClassroomAccessError("Esta invitación no te pertenece.")
        if invitation.status != ClassroomInvitation.Status.PENDING:
            raise ClassroomAccessError("Esta invitación ya fue respondida.")

        invitation.status = ClassroomInvitation.Status.DECLINED
        invitation.responded_at = timezone.now()
        invitation.save()
        return invitation

    @staticmethod
    def remove_student(classroom: Classroom, student):
        enrollment = classroom.enrollments.filter(student=student).first()
        if not enrollment:
            raise ClassroomAccessError("El estudiante no está inscrito en esta aula.")
        enrollment.is_active = False
        enrollment.save(update_fields=['is_active'])
        return enrollment


class ActivityProgressService:
    """
    Computes a student's progress toward an activity's objectives by querying
    existing training/games/analysis records — no duplicated counters are stored.
    """

    @staticmethod
    def _period_filter(activity: Activity, field_name='created_at'):
        filters = Q(**{f'{field_name}__gte': activity.assigned_date})
        if activity.due_date:
            filters &= Q(**{f'{field_name}__lte': activity.due_date})
        return filters

    @staticmethod
    def count_solved_puzzles(activity: Activity, student) -> int:
        qs = PuzzleAttempt.objects.filter(user=student, solved=True)
        qs = qs.filter(ActivityProgressService._period_filter(activity, 'completed_at'))
        if activity.puzzles.exists():
            qs = qs.filter(puzzle__in=activity.puzzles.all())
        return qs.values('puzzle').distinct().count()

    @staticmethod
    def count_games_played(activity: Activity, student) -> int:
        qs = Game.objects.filter(
            Q(white_player=student) | Q(black_player=student),
            status=Game.Status.FINISHED,
        )
        qs = qs.filter(ActivityProgressService._period_filter(activity, 'created_at'))
        return qs.count()

    @staticmethod
    def count_games_analyzed(activity: Activity, student) -> int:
        qs = AnalysisJob.objects.filter(user=student, status=AnalysisJob.Status.COMPLETED)
        qs = qs.filter(ActivityProgressService._period_filter(activity, 'created_at'))
        return qs.count()

    @staticmethod
    def count_puzzles_created(activity: Activity, student) -> int:
        qs = Puzzle.objects.filter(author=student)
        qs = qs.filter(ActivityProgressService._period_filter(activity, 'created_at'))
        return qs.count()

    @classmethod
    def _count_for_objective(cls, objective: ActivityObjective, activity: Activity, student) -> int:
        objective_type = objective.objective_type
        if objective_type == ActivityObjective.ObjectiveType.SOLVE_PUZZLES:
            return cls.count_solved_puzzles(activity, student)
        if objective_type == ActivityObjective.ObjectiveType.PLAY_GAMES:
            return cls.count_games_played(activity, student)
        if objective_type == ActivityObjective.ObjectiveType.ANALYZE_GAME:
            return cls.count_games_analyzed(activity, student)
        if objective_type == ActivityObjective.ObjectiveType.CREATE_PUZZLE:
            return cls.count_puzzles_created(activity, student)
        return 0

    @classmethod
    def compute_progress(cls, activity: Activity, student) -> dict:
        """
        Returns {'objectives': [{objective, achieved, target, completed}], 'is_complete': bool}
        for a single student against a single activity.
        """
        objective_rows = []
        overall_complete = True

        for objective in activity.objectives.all():
            achieved = cls._count_for_objective(objective, activity, student)
            completed = achieved >= objective.target_count
            overall_complete = overall_complete and completed
            objective_rows.append({
                'objective': objective,
                'achieved': achieved,
                'target': objective.target_count,
                'completed': completed,
            })

        if not objective_rows:
            overall_complete = False

        return {'objectives': objective_rows, 'is_complete': overall_complete}


class ClassroomStatsService:
    """
    Builds per-student, individual progress summaries for a teacher's classroom view.
    Intentionally returns one dict per student (no ranking/sorting by performance) so
    templates present progress, not a public leaderboard comparing students.
    """

    @staticmethod
    def student_summary(student) -> dict:
        puzzles_solved = PuzzleAttempt.objects.filter(user=student, solved=True).values('puzzle').distinct().count()
        puzzle_attempts_failed = PuzzleAttempt.objects.filter(user=student, solved=False).count()

        games_played = Game.objects.filter(
            Q(white_player=student) | Q(black_player=student),
            status=Game.Status.FINISHED,
        ).count()

        weak_stats = UserTrainingStats.objects.filter(user=student)
        weak_themes = [s for s in weak_stats if s.total_attempts >= 2 and s.success_rate < 50.0]

        last_attempt = PuzzleAttempt.objects.filter(user=student).order_by('-completed_at').first()
        last_game = Game.objects.filter(
            Q(white_player=student) | Q(black_player=student)
        ).order_by('-updated_at').first()

        recent_dates = [d for d in [
            last_attempt.completed_at if last_attempt else None,
            last_game.updated_at if last_game else None,
        ] if d is not None]

        return {
            'student': student,
            'puzzles_solved': puzzles_solved,
            'puzzle_attempts_failed': puzzle_attempts_failed,
            'games_played': games_played,
            'weak_themes': weak_themes,
            'recent_activity_at': max(recent_dates) if recent_dates else None,
        }

    @staticmethod
    def classroom_summary(classroom: Classroom) -> list:
        # Ordered by username (not by score) to avoid framing this as a public ranking.
        students = classroom.active_students.order_by('username')
        return [ClassroomStatsService.student_summary(student) for student in students]
