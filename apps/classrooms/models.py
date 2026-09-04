import uuid
import secrets
from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
from django.utils import timezone


def _generate_join_code():
    # Short, human-friendly code students can type in to enroll themselves.
    return secrets.token_hex(4).upper()


class Classroom(models.Model):
    """
    A teacher-owned classroom/group that persists across the school year.
    Students enroll via a join code or a direct invitation.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150, verbose_name="Nombre del Aula")
    description = models.TextField(blank=True, verbose_name="Descripción")

    teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='teaching_classrooms', blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_classrooms'
    )

    join_code = models.CharField(max_length=16, unique=True, default=_generate_join_code)
    is_active = models.BooleanField(default=True, verbose_name="Aula Activa")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def is_teacher(self, user):
        return bool(user and user.is_authenticated and (user.is_staff or self.teachers.filter(id=user.id).exists()))

    def is_member(self, user):
        if not user or not user.is_authenticated:
            return False
        return self.is_teacher(user) or self.enrollments.filter(student=user, is_active=True).exists()

    @property
    def active_students(self):
        from apps.accounts.models import CustomUser
        student_ids = self.enrollments.filter(is_active=True).values_list('student_id', flat=True)
        return CustomUser.objects.filter(id__in=student_ids)

    def regenerate_join_code(self):
        self.join_code = _generate_join_code()
        self.save(update_fields=['join_code'])


class ClassroomEnrollment(models.Model):
    """
    A student's membership in a classroom. Kept even when deactivated to preserve
    activity/progress history instead of hard-deleting the relationship.
    """
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='classroom_enrollments')
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['classroom', 'student']

    def __str__(self):
        return f"{self.student.username} en {self.classroom.name}"


class ClassroomInvitation(models.Model):
    """
    A direct, targeted invitation from a teacher to a specific student,
    as an alternative to self-enrollment via join code.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pendiente'
        ACCEPTED = 'ACCEPTED', 'Aceptada'
        DECLINED = 'DECLINED', 'Rechazada'
        CANCELLED = 'CANCELLED', 'Cancelada'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='invitations')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='classroom_invitations')
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sent_classroom_invitations'
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Invitación a {self.student.username} para {self.classroom.name} ({self.get_status_display()})"


class Activity(models.Model):
    """
    A time-boxed unit of work assigned by a teacher to a classroom (or a subset of it),
    e.g. "Semana 3 - Finales de peones". Concrete, measurable goals are stored as
    ActivityObjective rows so an activity is not limited to "solve N puzzles".
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='activities')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_activities'
    )

    title = models.CharField(max_length=200, verbose_name="Título")
    description = models.TextField(blank=True, verbose_name="Descripción")

    assigned_date = models.DateTimeField(default=timezone.now, verbose_name="Fecha de Asignación")
    due_date = models.DateTimeField(null=True, blank=True, verbose_name="Fecha Límite")

    # Optional curated set of specific problems attached to this activity.
    puzzles = models.ManyToManyField('training.Puzzle', related_name='activities', blank=True)

    # Optional subset of classroom students this activity targets; empty means "everyone enrolled".
    assigned_students = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='assigned_activities', blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-assigned_date']
        verbose_name_plural = 'Activities'

    def __str__(self):
        return f"{self.title} ({self.classroom.name})"

    def clean(self):
        super().clean()
        if self.due_date and self.assigned_date and self.due_date < self.assigned_date:
            raise ValidationError({'due_date': 'La fecha límite no puede ser anterior a la fecha de asignación.'})

    def target_students(self):
        """Students this activity applies to: the explicit subset, or every active enrollment."""
        if self.assigned_students.exists():
            return self.assigned_students.all()
        student_ids = self.classroom.enrollments.filter(is_active=True).values_list('student_id', flat=True)
        from apps.accounts.models import CustomUser
        return CustomUser.objects.filter(id__in=student_ids)

    def is_visible_to(self, user):
        if self.classroom.is_teacher(user):
            return True
        return self.target_students().filter(id=user.id).exists()


class ActivityObjective(models.Model):
    """
    A single measurable goal within an activity, e.g. "resolver 5 problemas".
    """
    class ObjectiveType(models.TextChoices):
        SOLVE_PUZZLES = 'SOLVE_PUZZLES', 'Resolver Problemas'
        PLAY_GAMES = 'PLAY_GAMES', 'Jugar Partidas'
        ANALYZE_GAME = 'ANALYZE_GAME', 'Analizar una Partida'
        CREATE_PUZZLE = 'CREATE_PUZZLE', 'Crear un Problema'

    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name='objectives')
    objective_type = models.CharField(max_length=20, choices=ObjectiveType.choices)
    target_count = models.PositiveIntegerField(default=1, verbose_name="Cantidad Objetivo")

    class Meta:
        ordering = ['id']

    def clean(self):
        super().clean()
        if self.target_count < 1:
            raise ValidationError({'target_count': 'La cantidad objetivo debe ser al menos 1.'})

    def __str__(self):
        return f"{self.get_objective_type_display()} x{self.target_count}"
