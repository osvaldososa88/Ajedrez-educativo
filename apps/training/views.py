import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.http import JsonResponse, HttpResponseForbidden
from django.db.models import Count, Q, Avg
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib import messages
from .models import Puzzle, PuzzleAttempt, UserTrainingStats, PuzzleFavorite, PuzzleRating
from .services import PuzzleService, PuzzleValidationService


def _is_moderator(user):
    return bool(user.is_authenticated and (user.is_staff or user.role in ['TEACHER', 'ADMIN']))

class TrainingDashboardView(LoginRequiredMixin, ListView):
    """
    Dashboard presenting categorized chess exercises, user statistics, and weak area alerts.
    """
    model = Puzzle
    template_name = 'training/training_dashboard.html'
    context_object_name = 'puzzles'

    def get_queryset(self):
        category = self.request.GET.get('category')
        difficulty = self.request.GET.get('difficulty')
        qs = Puzzle.objects.filter(status=Puzzle.Status.PUBLISHED)
        if category:
            qs = qs.filter(category=category)
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # User performance stats grouped by category/theme
        user_stats = UserTrainingStats.objects.filter(user=user)
        weak_themes = [
            stat for stat in user_stats
            if stat.total_attempts >= 2 and stat.success_rate < 50.0
        ]

        total_solved = PuzzleAttempt.objects.filter(user=user, solved=True).values('puzzle').distinct().count()
        total_attempts = PuzzleAttempt.objects.filter(user=user).count()

        context['categories'] = Puzzle.Category.choices
        context['difficulties'] = Puzzle.Difficulty.choices
        context['selected_category'] = self.request.GET.get('category', '')
        context['selected_difficulty'] = self.request.GET.get('difficulty', '')
        context['user_stats'] = user_stats
        context['weak_themes'] = weak_themes
        context['total_solved'] = total_solved
        context['total_attempts'] = total_attempts
        if user.is_authenticated:
            context['favorite_puzzle_ids'] = set(
                PuzzleFavorite.objects.filter(user=user).values_list('puzzle_id', flat=True)
            )
        return context


class PuzzleDetailView(LoginRequiredMixin, DetailView):
    """
    Interactive exercise solver view.

    SEQUENCE puzzles use the classic solver (sequence comparison).
    OBJECTIVE puzzles open a free-play solver against an automatic strong
    defender, evaluated by the server from the real game state.
    """
    model = Puzzle
    template_name = 'training/puzzle_detail.html'
    context_object_name = 'puzzle'
    pk_url_kwarg = 'puzzle_id'

    def get_queryset(self):
        # Moderators see everything; authors may preview/solve their own puzzle at any status;
        # everyone else may only access PUBLISHED puzzles.
        user = self.request.user
        if _is_moderator(user):
            return Puzzle.objects.all()
        return Puzzle.objects.filter(Q(status=Puzzle.Status.PUBLISHED) | Q(author=user))

    def get_template_names(self):
        if self.object.puzzle_type == Puzzle.PuzzleType.OBJECTIVE:
            return ['training/puzzle_objective.html']
        return [self.template_name]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        puzzle = self.object
        user = self.request.user
        context['hints_count'] = len(puzzle.hints or [])
        context['is_favorited'] = PuzzleFavorite.objects.filter(user=user, puzzle=puzzle).exists()
        context['user_rating'] = PuzzleRating.objects.filter(user=user, puzzle=puzzle).first()
        context['can_edit'] = puzzle.can_edit(user)
        return context


class MyPuzzlesListView(LoginRequiredMixin, ListView):
    """
    Lists puzzles authored by the current user, across all statuses, for self-management.
    """
    model = Puzzle
    template_name = 'training/my_puzzles.html'
    context_object_name = 'puzzles'

    def get_queryset(self):
        return Puzzle.objects.filter(author=self.request.user)


class FavoritesListView(LoginRequiredMixin, ListView):
    """
    Lists puzzles the current user has bookmarked as favorites.
    """
    model = Puzzle
    template_name = 'training/favorites.html'
    context_object_name = 'puzzles'

    def get_queryset(self):
        favorite_ids = PuzzleFavorite.objects.filter(user=self.request.user).values_list('puzzle_id', flat=True)
        return Puzzle.objects.filter(id__in=favorite_ids)


class PuzzleModerationListView(LoginRequiredMixin, ListView):
    """
    Teacher/admin queue of puzzles pending review.
    """
    model = Puzzle
    template_name = 'training/moderation_queue.html'
    context_object_name = 'puzzles'

    def dispatch(self, request, *args, **kwargs):
        if not _is_moderator(request.user):
            return HttpResponseForbidden("Solo docentes o administradores pueden moderar problemas.")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return Puzzle.objects.filter(status=Puzzle.Status.IN_REVIEW)


def _puzzle_form_payload(request):
    """Extracts and JSON-decodes the puzzle creator/editor form fields from a POST request."""
    def parse_json_field(name, default):
        raw = request.POST.get(name, '')
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    return {
        'title': request.POST.get('title', '').strip(),
        'description': request.POST.get('description', '').strip(),
        'initial_fen': request.POST.get('initial_fen', '').strip(),
        'side_to_move': request.POST.get('side_to_move', Puzzle.SideToMove.WHITE),
        'category': request.POST.get('category', Puzzle.Category.TACTICS),
        'theme': request.POST.get('theme', Puzzle.Theme.FORK),
        'difficulty': request.POST.get('difficulty', Puzzle.Difficulty.BEGINNER),
        'objective': request.POST.get('objective', Puzzle.Objective.WIN),
        'puzzle_type': request.POST.get('puzzle_type', Puzzle.PuzzleType.SEQUENCE),
        'objective_type': request.POST.get('objective_type') or None,
        'critical_pieces': parse_json_field('critical_pieces', []),
        'solution_moves': parse_json_field('solution_moves', []),
        'variations_json': parse_json_field('variations_json', {}),
        'hints': parse_json_field('hints', []),
    }


class PuzzleCreatorContextMixin:
    def _get_bots(self):
        from apps.bots.models import Bot
        return Bot.objects.filter(is_active=True).select_related('profile').order_by(
            'category', 'order', 'display_name'
        )

    def creator_context(self):
        return {
            'categories': Puzzle.Category.choices,
            'themes': Puzzle.Theme.choices,
            'difficulties': Puzzle.Difficulty.choices,
            'objectives': Puzzle.Objective.choices,
            'puzzle_types': Puzzle.PuzzleType.choices,
            'objective_types': Puzzle.ObjectiveType.choices,
            'sides': Puzzle.SideToMove.choices,
            'available_bots': self._get_bots(),
        }


class PuzzleCreateView(LoginRequiredMixin, PuzzleCreatorContextMixin, View):
    """
    Board/position creator for authoring a new puzzle. Any authenticated user
    (student or teacher) may create a puzzle; it starts as DRAFT.
    """
    template_name = 'training/puzzle_creator.html'

    def get(self, request):
        context = self.creator_context()
        context['puzzle'] = None
        return render(request, self.template_name, context)

    def post(self, request):
        payload = _puzzle_form_payload(request)
        puzzle = Puzzle(author=request.user, status=Puzzle.Status.DRAFT, **payload)

        try:
            puzzle.save()
        except ValidationError as exc:
            context = self.creator_context()
            context['puzzle'] = None
            context['form_data'] = payload
            context['errors'] = _flatten_validation_errors(exc)
            return render(request, self.template_name, context, status=400)

        messages.success(request, 'Problema guardado como borrador.')
        return redirect('my_puzzles')


class PuzzleEditView(LoginRequiredMixin, PuzzleCreatorContextMixin, View):
    """
    Edit an existing puzzle. Authors may edit their own DRAFT/REJECTED puzzles;
    moderators (teacher/admin) may edit any puzzle regardless of status.
    """
    template_name = 'training/puzzle_creator.html'

    def get(self, request, puzzle_id):
        puzzle = get_object_or_404(Puzzle, id=puzzle_id)
        if not puzzle.can_edit(request.user):
            return HttpResponseForbidden("No tienes permiso para editar este problema.")
        context = self.creator_context()
        context['puzzle'] = puzzle
        return render(request, self.template_name, context)

    def post(self, request, puzzle_id):
        puzzle = get_object_or_404(Puzzle, id=puzzle_id)
        if not puzzle.can_edit(request.user):
            return HttpResponseForbidden("No tienes permiso para editar este problema.")

        payload = _puzzle_form_payload(request)
        for field, value in payload.items():
            setattr(puzzle, field, value)

        try:
            puzzle.save()
        except ValidationError as exc:
            context = self.creator_context()
            context['puzzle'] = puzzle
            context['errors'] = _flatten_validation_errors(exc)
            return render(request, self.template_name, context, status=400)

        messages.success(request, 'Problema actualizado correctamente.')
        return redirect('my_puzzles')


def _flatten_validation_errors(exc: ValidationError):
    if hasattr(exc, 'message_dict'):
        errors = []
        for field, msgs in exc.message_dict.items():
            errors.extend([f"{field}: {m}" for m in msgs])
        return errors
    return list(exc.messages)


@login_required
def delete_puzzle(request, puzzle_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    puzzle = get_object_or_404(Puzzle, id=puzzle_id)
    if not puzzle.can_delete(request.user):
        return HttpResponseForbidden("No tienes permiso para eliminar este problema.")

    puzzle.delete()
    messages.success(request, 'Problema eliminado.')
    return redirect('my_puzzles')


@login_required
def submit_puzzle_for_review(request, puzzle_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    puzzle = get_object_or_404(Puzzle, id=puzzle_id)
    if not puzzle.can_submit_for_review(request.user):
        return HttpResponseForbidden("No puedes enviar a revisión este problema.")

    errors = PuzzleValidationService.validate_for_submission(puzzle)
    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)

    puzzle.status = Puzzle.Status.IN_REVIEW
    puzzle.moderation_notes = ''
    puzzle.reviewed_at = None
    puzzle.save()

    return JsonResponse({'success': True, 'status': puzzle.status})


@login_required
def approve_puzzle(request, puzzle_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    if not _is_moderator(request.user):
        return HttpResponseForbidden("Solo docentes o administradores pueden aprobar problemas.")

    puzzle = get_object_or_404(Puzzle, id=puzzle_id)
    errors = PuzzleValidationService.validate_for_submission(puzzle)
    if errors:
        return JsonResponse({'success': False, 'errors': errors}, status=400)

    puzzle.status = Puzzle.Status.PUBLISHED
    puzzle.moderated_by = request.user
    puzzle.reviewed_at = timezone.now()
    puzzle.moderation_notes = request.POST.get('notes', '')
    puzzle.save()

    return JsonResponse({'success': True, 'status': puzzle.status})


@login_required
def reject_puzzle(request, puzzle_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    if not _is_moderator(request.user):
        return HttpResponseForbidden("Solo docentes o administradores pueden rechazar problemas.")

    puzzle = get_object_or_404(Puzzle, id=puzzle_id)
    reason = request.POST.get('reason', '').strip()
    if not reason:
        return JsonResponse({'success': False, 'errors': ['Debes indicar un motivo de rechazo.']}, status=400)

    puzzle.status = Puzzle.Status.REJECTED
    puzzle.moderated_by = request.user
    puzzle.reviewed_at = timezone.now()
    puzzle.moderation_notes = reason
    puzzle.save()

    return JsonResponse({'success': True, 'status': puzzle.status})


@login_required
def archive_puzzle(request, puzzle_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    puzzle = get_object_or_404(Puzzle, id=puzzle_id)
    if not (puzzle.is_author(request.user) or _is_moderator(request.user)):
        return HttpResponseForbidden("No tienes permiso para archivar este problema.")

    puzzle.status = Puzzle.Status.ARCHIVED
    puzzle.save()
    return JsonResponse({'success': True, 'status': puzzle.status})


@login_required
def toggle_favorite_api(request, puzzle_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    puzzle = get_object_or_404(Puzzle, id=puzzle_id, status=Puzzle.Status.PUBLISHED)
    favorite, created = PuzzleFavorite.objects.get_or_create(user=request.user, puzzle=puzzle)
    if not created:
        favorite.delete()
        return JsonResponse({'favorited': False})
    return JsonResponse({'favorited': True})


@login_required
def rate_puzzle_api(request, puzzle_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    puzzle = get_object_or_404(Puzzle, id=puzzle_id, status=Puzzle.Status.PUBLISHED)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    try:
        value = int(data.get('value'))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'La valoración debe ser un número entre 1 y 5.'}, status=400)

    try:
        rating, _created = PuzzleRating.objects.update_or_create(
            user=request.user, puzzle=puzzle, defaults={'value': value}
        )
    except ValidationError as exc:
        return JsonResponse({'error': _flatten_validation_errors(exc)}, status=400)

    return JsonResponse({
        'success': True,
        'average_rating': puzzle.average_rating,
        'ratings_count': puzzle.ratings_count,
    })


@login_required
def submit_puzzle_move_api(request, puzzle_id):
    """
    AJAX endpoint for move verification during puzzle execution.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    puzzle = get_object_or_404(Puzzle, id=puzzle_id)

    ply_index = int(data.get('ply_index', 0))
    uci_move = data.get('uci_move', '').strip()
    time_taken = int(data.get('time_taken_seconds', 0))
    hints_used = int(data.get('hints_used', 0))
    attempts_count = int(data.get('attempts_count', 1))

    if not uci_move:
        return JsonResponse({'error': 'Debe especificar la jugada UCI'}, status=400)

    result = PuzzleService.verify_move(puzzle, ply_index, uci_move)

    if result['completed'] or not result['is_correct']:
        # Log attempt if finished or if student completed attempt cycle
        solved = result['is_correct'] and result['completed']
        PuzzleService.record_attempt(
            user=request.user,
            puzzle=puzzle,
            solved=solved,
            time_taken_seconds=time_taken,
            hints_used=hints_used,
            attempts_count=attempts_count
        )

    return JsonResponse(result)


@login_required
def get_puzzle_hint_api(request, puzzle_id):
    """
    AJAX endpoint for progressive hint retrieval.
    """
    puzzle = get_object_or_404(Puzzle, id=puzzle_id)
    hint_index = int(request.GET.get('index', 0))

    hints = puzzle.hints or []
    if hint_index < 0 or hint_index >= len(hints):
        return JsonResponse({'error': 'No hay más pistas disponibles.'}, status=404)

    return JsonResponse({
        'hint_index': hint_index,
        'hint_text': hints[hint_index],
        'total_hints': len(hints)
    })
# ============================================================================
# PROBLEMAS POR OBJETIVO (OBJECTIVE) — APIs
# Todas las decisiones (objetivo, fallo, límite, jugadas del defensor) se
# validan en el servidor. El cliente nunca decide victorias/derrotas.
# ============================================================================

def _get_objective_attempt(user, puzzle):
    """Devuelve la sesión en curso (la más reciente) o crea una nueva."""
    attempt = (
        PuzzleAttempt.objects.filter(user=user, puzzle=puzzle)
        .order_by('-completed_at')
        .first()
    )
    if attempt is None or attempt.status != PuzzleAttempt.Status.IN_PROGRESS:
        attempt = PuzzleAttempt.objects.create(user=user, puzzle=puzzle)
    return attempt


@login_required
def submit_objective_move_api(request, puzzle_id):
    """Procesa una jugada del estudiante en un problema OBJECTIVE.

    Idempotente: replay desde `movelog` + select_for_update. Un reenvío de una
    jugada ya aplicada devuelve el estado actual sin volver a modificarlo.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        puzzle = Puzzle.objects.get(id=puzzle_id)
    except (Puzzle.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Problema no encontrado.'}, status=404)

    if puzzle.puzzle_type != Puzzle.PuzzleType.OBJECTIVE:
        return JsonResponse({'error': 'Este problema no es de tipo objetivo.'}, status=400)

    if not _is_moderator(request.user) and puzzle.status != Puzzle.Status.PUBLISHED and puzzle.author != request.user:
        return JsonResponse({'error': 'No tienes acceso a este problema.'}, status=403)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    uci_move = (data.get('uci_move') or '').strip()
    time_taken = int(data.get('time_taken_seconds', 0) or 0)
    if not uci_move:
        return JsonResponse({'error': 'Debe especificar la jugada UCI'}, status=400)

    from django.db import transaction
    from .services import ObjectivePuzzleEngine, update_training_stats

    with transaction.atomic():
        attempt = PuzzleAttempt.objects.select_for_update().get(id=_get_objective_attempt(request.user, puzzle).id)
        result = ObjectivePuzzleEngine.apply_human_move(puzzle, attempt, uci_move)

        # Estadísticas y análisis al terminar (una sola vez).
        if attempt.status != PuzzleAttempt.Status.IN_PROGRESS:
            update_training_stats(request.user, puzzle, attempt.solved, time_taken)
            job = ObjectivePuzzleEngine.create_analysis_job(request.user, puzzle, attempt)
            result['analysis_job_id'] = str(job.id)

    # Iniciar el análisis asíncrono del intento finalizado (fuera del lock).
    if 'analysis_job_id' in result:
        from apps.analysis.services import start_async_analysis_job
        start_async_analysis_job(result['analysis_job_id'])

    return JsonResponse(result)


@login_required
def reset_objective_puzzle_api(request, puzzle_id):
    """Reinicia un problema OBJECTIVE: devuelve la posición inicial e invalida
    la sesión en curso (no crea una nueva definición del problema)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        puzzle = Puzzle.objects.get(id=puzzle_id)
    except (Puzzle.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Problema no encontrado.'}, status=404)

    PuzzleAttempt.objects.filter(
        user=request.user, puzzle=puzzle, status=PuzzleAttempt.Status.IN_PROGRESS
    ).delete()

    return JsonResponse({
        'type': 'objective_reset',
        'fen': puzzle.initial_fen,
        'human_moves': 0,
        'max_moves': puzzle.max_moves or 0,
        'message': 'Problema reiniciado desde la posición inicial.',
    })


@login_required
def abandon_objective_puzzle_api(request, puzzle_id):
    """Abandona el problema OBJECTIVE: registra la derrota/abandono según las
    reglas existentes (PuzzleAttempt no resuelto) sin contarlo como victoria."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        puzzle = Puzzle.objects.get(id=puzzle_id)
    except (Puzzle.DoesNotExist, ValueError):
        return JsonResponse({'error': 'Problema no encontrado.'}, status=404)

    attempt = (
        PuzzleAttempt.objects.filter(user=request.user, puzzle=puzzle)
        .order_by('-completed_at')
        .first()
    )
    if attempt is not None and attempt.status == PuzzleAttempt.Status.IN_PROGRESS:
        attempt.status = PuzzleAttempt.Status.ABANDONED
        attempt.solved = False
        if not attempt.end_message:
            attempt.end_message = 'Abandonaste el problema.'
        attempt.save(update_fields=['status', 'solved', 'end_message'])
        from .services import update_training_stats
        update_training_stats(request.user, puzzle, False, 0)

    return JsonResponse({
        'type': 'objective_abandon',
        'solved': False,
        'message': 'Problema abandonado. No se cuenta como victoria.',
    })
