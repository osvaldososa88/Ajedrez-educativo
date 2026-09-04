import io
import chess
import chess.pgn
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from apps.games.models import Game
from apps.core.stockfish_engine import StockfishEngine
from .models import AnalysisJob, PositionAnalysis
from .services import start_async_analysis_job

@login_required
def create_game_analysis_job(request, game_id):
    """Create asynchronous Stockfish analysis job for an existing game."""
    game = get_object_or_404(Game, id=game_id)

    # Permission check: User must be white, black, teacher, or admin
    is_participant = (request.user == game.white_player or request.user == game.black_player)
    is_staff = request.user.role in ['TEACHER', 'ADMIN'] or request.user.is_staff

    if not (is_participant or is_staff):
        return HttpResponseForbidden("No tienes permiso para analizar esta partida.")

    # Tournament games are competitive play: analysis stays disabled while the
    # round is still being played, matching the "no analysis during competition" rule.
    if game.status == Game.Status.IN_PROGRESS and hasattr(game, 'tournament_pairing'):
        return HttpResponseForbidden("El análisis no está disponible mientras la partida de torneo está en curso.")

    # Check if existing job is already in progress or completed
    existing_job = AnalysisJob.objects.filter(game=game, status=AnalysisJob.Status.COMPLETED).order_by('-created_at').first()
    if existing_job:
        return redirect('analysis_job_detail', job_id=existing_job.id)

    job = AnalysisJob.objects.create(
        game=game,
        user=request.user,
        pgn_text=game.generate_pgn(),
        target_depth=12
    )

    start_async_analysis_job(str(job.id))
    return redirect('analysis_job_detail', job_id=job.id)

@login_required
def import_pgn_view(request):
    """View to import and analyze PGN text or .pgn file."""
    if request.method == 'POST':
        pgn_text = request.POST.get('pgn_text', '').strip()
        pgn_file = request.FILES.get('pgn_file')

        if pgn_file:
            pgn_text = pgn_file.read().decode('utf-8')

        if not pgn_text:
            messages.error(request, "Por favor ingresa texto PGN o sube un archivo .pgn válido.")
            return render(request, 'analysis/import_pgn.html')

        # Validate PGN using python-chess
        parsed_game = chess.pgn.read_game(io.StringIO(pgn_text))
        if not parsed_game or not parsed_game.variations:
            messages.error(request, "El formato PGN ingresado es inválido o no contiene jugadas.")
            return render(request, 'analysis/import_pgn.html')

        job = AnalysisJob.objects.create(
            user=request.user,
            pgn_text=pgn_text,
            target_depth=12
        )
        start_async_analysis_job(str(job.id))
        return redirect('analysis_job_detail', job_id=job.id)

    return render(request, 'analysis/import_pgn.html')

class AnalysisJobDetailView(LoginRequiredMixin, DetailView):
    """Interactive Game & Position Analysis Viewer."""
    model = AnalysisJob
    template_name = 'analysis/analysis_detail.html'
    context_object_name = 'job'
    pk_url_kwarg = 'job_id'

    def get_queryset(self):
        # Security check: User can only access their own jobs or staff
        if self.request.user.role in ['TEACHER', 'ADMIN'] or self.request.user.is_staff:
            return AnalysisJob.objects.all()
        return AnalysisJob.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        job = self.object

        move_analyses = list(job.move_analyses.select_related('position_analysis').values(
            'ply', 'move_san', 'move_uci', 'fen_before', 'fen_after',
            'score_cp', 'mate_in', 'quality',
            'position_analysis__best_move_san',
            'position_analysis__best_move_uci',
            'position_analysis__pv_san'
        ))

        context['move_analyses_json'] = move_analyses
        return context

@login_required
def job_status_api(request, job_id):
    """API endpoint to poll progress of an async analysis job."""
    job = get_object_or_404(AnalysisJob, id=job_id)

    # Permission check
    if job.user != request.user and not request.user.is_staff and request.user.role not in ['TEACHER', 'ADMIN']:
        return JsonResponse({'error': 'Acceso denegado.'}, status=403)

    return JsonResponse({
        'job_id': str(job.id),
        'status': job.status,
        'progress_percent': job.progress_percent,
        'error_message': job.error_message
    })

@login_required
def analyze_single_fen_api(request):
    """API endpoint for single-position on-demand evaluation (Training / Analysis mode)."""
    fen = request.GET.get('fen', chess.STARTING_FEN)
    mode = request.GET.get('mode', 'ANALYSIS') # COMPETITION, TRAINING, ANALYSIS

    if mode == 'COMPETITION':
        return JsonResponse({
            'mode': 'COMPETITION',
            'error': 'Motor de análisis deshabilitado en modo Competición.'
        }, status=403)

    # Check position validity with python-chess
    try:
        board = chess.Board(fen)
    except ValueError:
        return JsonResponse({'error': 'Posición FEN inválida.'}, status=400)

    # Check cached PositionAnalysis or calculate
    pos_analysis, created = PositionAnalysis.objects.get_or_create(
        fen=fen,
        defaults={
            'score_cp': None,
            'mate_in': None,
            'best_move_uci': None,
            'best_move_san': None,
            'pv_san': [],
            'depth': 12,
            'engine_name': 'Stockfish'
        }
    )

    if created or (pos_analysis.score_cp is None and pos_analysis.mate_in is None):
        eval_res = StockfishEngine.evaluate_position(fen, depth=12)
        pos_analysis.score_cp = eval_res['score_cp']
        pos_analysis.mate_in = eval_res['mate_in']
        pos_analysis.best_move_uci = eval_res['best_move_uci']
        pos_analysis.best_move_san = eval_res['best_move_san']
        pos_analysis.pv_san = eval_res['pv_san']
        pos_analysis.engine_name = eval_res['engine_name']
        pos_analysis.save()

    return JsonResponse({
        'fen': pos_analysis.fen,
        'score_cp': pos_analysis.score_cp,
        'mate_in': pos_analysis.mate_in,
        'best_move_san': pos_analysis.best_move_san if mode == 'ANALYSIS' else None,
        'pv_san': pos_analysis.pv_san if mode == 'ANALYSIS' else [],
        'engine_name': pos_analysis.engine_name,
        'mode': mode
    })
