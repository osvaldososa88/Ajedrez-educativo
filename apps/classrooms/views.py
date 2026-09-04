import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.core.exceptions import ValidationError

from apps.accounts.models import CustomUser
from apps.training.models import Puzzle
from .models import Classroom, ClassroomEnrollment, ClassroomInvitation, Activity, ActivityObjective
from .services import ClassroomService, ClassroomAccessError, ActivityProgressService, ClassroomStatsService


def _is_teacher_role(user):
    return bool(user.is_authenticated and (user.is_staff or user.role in ['TEACHER', 'ADMIN']))


class ClassroomListView(LoginRequiredMixin, ListView):
    """
    Teachers see the classrooms they teach (plus a create option).
    Students see the classrooms they're enrolled in (plus a join-by-code form).
    """
    model = Classroom
    template_name = 'classrooms/classroom_list.html'
    context_object_name = 'classrooms'

    def get_queryset(self):
        user = self.request.user
        if _is_teacher_role(user):
            return Classroom.objects.filter(teachers=user)
        enrolled_ids = ClassroomEnrollment.objects.filter(student=user, is_active=True).values_list('classroom_id', flat=True)
        return Classroom.objects.filter(id__in=enrolled_ids)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_teacher'] = _is_teacher_role(self.request.user)
        context['pending_invitations'] = ClassroomInvitation.objects.filter(
            student=self.request.user, status=ClassroomInvitation.Status.PENDING
        )
        return context


class ClassroomCreateView(LoginRequiredMixin, View):
    template_name = 'classrooms/classroom_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # LoginRequiredMixin redirects to login
        if not _is_teacher_role(request.user):
            return HttpResponseForbidden("Solo docentes o administradores pueden crear aulas.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, 'El aula debe tener un nombre.')
            return render(request, self.template_name, {'name': name, 'description': description}, status=400)

        classroom = Classroom.objects.create(name=name, description=description, created_by=request.user)
        classroom.teachers.add(request.user)
        messages.success(request, f'Aula "{classroom.name}" creada. Código de acceso: {classroom.join_code}')
        return redirect('classroom_detail', classroom_id=classroom.id)


class ClassroomDetailView(LoginRequiredMixin, DetailView):
    model = Classroom
    template_name = 'classrooms/classroom_detail.html'
    context_object_name = 'classroom'
    pk_url_kwarg = 'classroom_id'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # LoginRequiredMixin redirects to login
        self.classroom = get_object_or_404(Classroom, id=kwargs['classroom_id'])
        if not self.classroom.is_member(request.user):
            return HttpResponseForbidden("No perteneces a esta aula.")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.classroom

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_teacher = self.classroom.is_teacher(user)
        context['is_teacher'] = is_teacher
        context['activities'] = [a for a in self.classroom.activities.all() if a.is_visible_to(user)]

        if is_teacher:
            context['enrollments'] = self.classroom.enrollments.filter(is_active=True).select_related('student')
            context['pending_invitations'] = self.classroom.invitations.filter(status=ClassroomInvitation.Status.PENDING)
        return context


@login_required
def join_classroom(request):
    if request.method != 'POST':
        return redirect('classroom_list')

    join_code = request.POST.get('join_code', '')
    try:
        classroom = ClassroomService.join_by_code(request.user, join_code)
    except ClassroomAccessError as exc:
        messages.error(request, str(exc))
        return redirect('classroom_list')

    messages.success(request, f'Te has inscrito en el aula "{classroom.name}".')
    return redirect('classroom_detail', classroom_id=classroom.id)


@login_required
def invite_student(request, classroom_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    classroom = get_object_or_404(Classroom, id=classroom_id)
    if not classroom.is_teacher(request.user):
        return HttpResponseForbidden("Solo los docentes del aula pueden invitar estudiantes.")

    username = request.POST.get('username', '').strip()
    student = CustomUser.objects.filter(username=username).first()
    if not student:
        return JsonResponse({'success': False, 'error': 'No existe un usuario con ese nombre de usuario.'}, status=404)

    try:
        invitation = ClassroomService.invite_student(classroom, request.user, student)
    except ClassroomAccessError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'success': True, 'invitation_id': str(invitation.id)})


@login_required
def remove_student(request, classroom_id, user_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    classroom = get_object_or_404(Classroom, id=classroom_id)
    if not classroom.is_teacher(request.user):
        return HttpResponseForbidden("Solo los docentes del aula pueden quitar estudiantes.")

    student = get_object_or_404(CustomUser, id=user_id)
    try:
        ClassroomService.remove_student(classroom, student)
    except ClassroomAccessError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'success': True})


class InvitationListView(LoginRequiredMixin, ListView):
    model = ClassroomInvitation
    template_name = 'classrooms/invitation_list.html'
    context_object_name = 'invitations'

    def get_queryset(self):
        return ClassroomInvitation.objects.filter(
            student=self.request.user, status=ClassroomInvitation.Status.PENDING
        )


@login_required
def accept_invitation(request, invitation_id):
    invitation = get_object_or_404(ClassroomInvitation, id=invitation_id)
    try:
        ClassroomService.accept_invitation(invitation, request.user)
    except ClassroomAccessError as exc:
        messages.error(request, str(exc))
        return redirect('classroom_invitations')

    messages.success(request, f'Te has unido al aula "{invitation.classroom.name}".')
    return redirect('classroom_detail', classroom_id=invitation.classroom_id)


@login_required
def decline_invitation(request, invitation_id):
    invitation = get_object_or_404(ClassroomInvitation, id=invitation_id)
    try:
        ClassroomService.decline_invitation(invitation, request.user)
    except ClassroomAccessError as exc:
        messages.error(request, str(exc))
    return redirect('classroom_invitations')


class ActivityCreateView(LoginRequiredMixin, View):
    template_name = 'classrooms/activity_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # LoginRequiredMixin redirects to login
        self.classroom = get_object_or_404(Classroom, id=kwargs['classroom_id'])
        if not self.classroom.is_teacher(request.user):
            return HttpResponseForbidden("Solo los docentes del aula pueden crear actividades.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, classroom_id):
        context = {
            'classroom': self.classroom,
            'objective_types': ActivityObjective.ObjectiveType.choices,
            'published_puzzles': Puzzle.objects.filter(status=Puzzle.Status.PUBLISHED).order_by('-created_at')[:100],
            'students': self.classroom.active_students.order_by('username'),
        }
        return render(request, self.template_name, context)

    def post(self, request, classroom_id):
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        due_date = request.POST.get('due_date') or None
        puzzle_ids = request.POST.getlist('puzzle_ids')
        student_ids = request.POST.getlist('student_ids')

        if not title:
            messages.error(request, 'La actividad debe tener un título.')
            return redirect('activity_create', classroom_id=self.classroom.id)

        activity = Activity(
            classroom=self.classroom,
            created_by=request.user,
            title=title,
            description=description,
            due_date=due_date,
        )
        try:
            activity.full_clean()
        except ValidationError as exc:
            messages.error(request, f'No se pudo crear la actividad: {exc.messages[0] if exc.messages else exc}')
            return redirect('activity_create', classroom_id=self.classroom.id)
        activity.save()

        if puzzle_ids:
            activity.puzzles.set(Puzzle.objects.filter(id__in=puzzle_ids, status=Puzzle.Status.PUBLISHED))
        if student_ids:
            activity.assigned_students.set(CustomUser.objects.filter(id__in=student_ids))

        try:
            objective_types = request.POST.getlist('objective_type')
            objective_targets = request.POST.getlist('objective_target')
            for obj_type, obj_target in zip(objective_types, objective_targets):
                if not obj_type:
                    continue
                objective = ActivityObjective(
                    activity=activity, objective_type=obj_type, target_count=int(obj_target or 1)
                )
                objective.full_clean()
                objective.save()
        except (ValidationError, ValueError) as exc:
            activity.delete()
            messages.error(request, f'No se pudo crear la actividad: {exc}')
            return redirect('activity_create', classroom_id=self.classroom.id)

        messages.success(request, f'Actividad "{activity.title}" creada.')
        return redirect('activity_detail', classroom_id=self.classroom.id, activity_id=activity.id)


class ActivityDetailView(LoginRequiredMixin, DetailView):
    model = Activity
    template_name = 'classrooms/activity_detail.html'
    context_object_name = 'activity'
    pk_url_kwarg = 'activity_id'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # LoginRequiredMixin redirects to login
        self.classroom = get_object_or_404(Classroom, id=kwargs['classroom_id'])
        self.activity = get_object_or_404(Activity, id=kwargs['activity_id'], classroom=self.classroom)
        if not self.activity.is_visible_to(request.user):
            return HttpResponseForbidden("Esta actividad no está asignada a tu usuario.")
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.activity

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_teacher = self.classroom.is_teacher(user)
        context['classroom'] = self.classroom
        context['is_teacher'] = is_teacher

        if is_teacher:
            context['progress_by_student'] = [
                {'student': student, **ActivityProgressService.compute_progress(self.activity, student)}
                for student in self.activity.target_students().order_by('username')
            ]
        else:
            context['my_progress'] = ActivityProgressService.compute_progress(self.activity, user)
        return context


class ClassroomStatsView(LoginRequiredMixin, View):
    """
    Teacher-only aggregate view: individual progress per student, never a public
    comparison/leaderboard, and never accessible by students (own progress is
    already visible via their own dashboards elsewhere).
    """
    template_name = 'classrooms/classroom_stats.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # LoginRequiredMixin redirects to login
        self.classroom = get_object_or_404(Classroom, id=kwargs['classroom_id'])
        if not self.classroom.is_teacher(request.user):
            return HttpResponseForbidden("Solo los docentes del aula pueden ver las estadísticas.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, classroom_id):
        context = {
            'classroom': self.classroom,
            'summaries': ClassroomStatsService.classroom_summary(self.classroom),
        }
        return render(request, self.template_name, context)


class StudentProgressDetailView(LoginRequiredMixin, View):
    """
    Detailed, individual progress for one student within a classroom.
    Accessible to: the classroom's teachers, or the student themself (never other students).
    """
    template_name = 'classrooms/student_progress_detail.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # LoginRequiredMixin redirects to login
        self.classroom = get_object_or_404(Classroom, id=kwargs['classroom_id'])
        self.student = get_object_or_404(CustomUser, id=kwargs['user_id'])

        is_teacher = self.classroom.is_teacher(request.user)
        is_self = (request.user.id == self.student.id)
        if not (is_teacher or is_self):
            return HttpResponseForbidden("No puedes consultar las estadísticas de otro estudiante.")

        # Even a teacher may only inspect students actually enrolled in THEIR classroom,
        # never an arbitrary user's data by guessing an id.
        is_enrolled_here = self.classroom.enrollments.filter(student=self.student, is_active=True).exists()
        if not is_enrolled_here:
            return HttpResponseForbidden("Este estudiante no pertenece a esta aula.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, classroom_id, user_id):
        activities = [a for a in self.classroom.activities.all() if self.student in a.target_students()]
        activity_progress = [
            {'activity': activity, **ActivityProgressService.compute_progress(activity, self.student)}
            for activity in activities
        ]
        context = {
            'classroom': self.classroom,
            'student': self.student,
            'summary': ClassroomStatsService.student_summary(self.student),
            'activity_progress': activity_progress,
        }
        return render(request, self.template_name, context)
