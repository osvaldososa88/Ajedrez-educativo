from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, View
from django.contrib import messages

from apps.analysis.models import AnalysisJob
from .models import DetectedGameError
from .services import ErrorDetectionService, PersonalizationError
from .profile import StudentProfileService
from .recommendations import RecommendationService


class PersonalizationDashboardView(LoginRequiredMixin, View):
    """
    A student's own practice profile and weekly recommendations. Always scoped to
    `request.user` — there is no route that takes another user's id, so a student
    can never load a classmate's indicators through this view.
    """
    template_name = 'personalization/dashboard.html'

    def get(self, request):
        context = {
            'profile': StudentProfileService.compute_profile(request.user),
            'recommendations': RecommendationService.build_weekly_recommendations(request.user),
        }
        return render(request, self.template_name, context)


class MyDetectedErrorsListView(LoginRequiredMixin, ListView):
    model = DetectedGameError
    template_name = 'personalization/my_errors.html'
    context_object_name = 'errors'

    def get_queryset(self):
        return DetectedGameError.objects.filter(student=self.request.user).select_related('generated_puzzle', 'game')


@login_required
def generate_training_from_job(request, job_id):
    job = get_object_or_404(AnalysisJob, id=job_id)

    is_participant = job.game is not None and request.user in [job.game.white_player, job.game.black_player]
    is_staff = request.user.is_staff or request.user.role in ['TEACHER', 'ADMIN']
    if not (is_participant or is_staff or job.user_id == request.user.id):
        messages.error(request, "No tienes permiso para generar entrenamiento a partir de este análisis.")
        return redirect('analysis_job_detail', job_id=job.id)

    try:
        created = ErrorDetectionService.generate_from_job(job)
    except PersonalizationError as exc:
        messages.error(request, str(exc))
        return redirect('analysis_job_detail', job_id=job.id)

    if created:
        messages.success(request, f"Se generaron {len(created)} posición(es) de entrenamiento a partir de tus errores.")
    else:
        messages.info(request, "No se encontraron errores nuevos para convertir en entrenamiento.")
    return redirect('analysis_job_detail', job_id=job.id)


class AppearanceSettingsView(LoginRequiredMixin, View):
    """
    Sección de Configuración / Apariencia visual del jugador.
    Muestra galerías con previews de piezas y tableros en tiempo real,
    permite guardar preferencias en BD o restaurar los valores predeterminados del Administrador.
    """
    template_name = 'personalization/appearance.html'

    def get(self, request):
        from .models import UserAppearancePreference, GlobalChessConfig
        from .chess_theme_registry import PIECE_SETS, BOARD_THEMES, resolve_user_appearance

        global_config = GlobalChessConfig.get_solo()
        current_piece_set, current_board_theme, is_custom = resolve_user_appearance(request.user)

        context = {
            'piece_sets': PIECE_SETS,
            'board_themes': BOARD_THEMES,
            'current_piece_set': current_piece_set,
            'current_board_theme': current_board_theme,
            'is_custom': is_custom,
            'allow_customization': global_config.allow_player_customization,
            'admin_piece_set': global_config.default_piece_set,
            'admin_board_theme': global_config.default_board_theme,
        }
        return render(request, self.template_name, context)

    def post(self, request):
        from .models import UserAppearancePreference, GlobalChessConfig
        from .chess_theme_registry import VALID_PIECE_SETS, VALID_BOARD_THEMES

        global_config = GlobalChessConfig.get_solo()
        if not global_config.allow_player_customization:
            messages.error(request, "El Administrador ha deshabilitado la personalización visual individual.")
            return redirect('personalization_appearance')

        action = request.POST.get('action', 'save')

        if action == 'reset':
            UserAppearancePreference.objects.filter(user=request.user).delete()
            messages.success(request, "Se ha restaurado la apariencia predeterminada del administrador.")
            return redirect('personalization_appearance')

        piece_set = request.POST.get('piece_set')
        board_theme = request.POST.get('board_theme')

        if piece_set not in VALID_PIECE_SETS or board_theme not in VALID_BOARD_THEMES:
            messages.error(request, "Las opciones seleccionadas no son válidas.")
            return redirect('personalization_appearance')

        pref, _ = UserAppearancePreference.objects.get_or_create(user=request.user)
        pref.piece_set = piece_set
        pref.board_theme = board_theme
        pref.save()

        messages.success(request, "¡Preferencias de apariencia visual guardadas correctamente!")
        return redirect('personalization_appearance')

