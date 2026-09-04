from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages

from apps.accounts.models import CustomUser
from .models import Tournament, TournamentParticipant, Round, Pairing
from .services import TournamentService, TournamentError
from .standings import StandingsService


def _is_organizer_role(user):
    return bool(user.is_authenticated and (user.is_staff or user.role in ['TEACHER', 'ADMIN']))


class TournamentListView(LoginRequiredMixin, ListView):
    model = Tournament
    template_name = 'tournaments/tournament_list.html'
    context_object_name = 'tournaments'

    def get_queryset(self):
        return Tournament.objects.exclude(status=Tournament.Status.CANCELLED)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['can_create'] = _is_organizer_role(self.request.user)
        return context


class TournamentCreateView(LoginRequiredMixin, View):
    template_name = 'tournaments/tournament_form.html'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # LoginRequiredMixin redirects to login
        if not _is_organizer_role(request.user):
            return HttpResponseForbidden("Solo docentes o administradores pueden crear torneos.")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, self.template_name, {'formats': Tournament.Format.choices})

    def post(self, request):
        name = request.POST.get('name', '').strip()
        if not name:
            messages.error(request, 'El torneo debe tener un nombre.')
            return render(request, self.template_name, {'formats': Tournament.Format.choices}, status=400)

        tournament_format = request.POST.get('format', Tournament.Format.ROUND_ROBIN)
        rounds_total = request.POST.get('rounds_total') or None

        tournament = Tournament.objects.create(
            name=name,
            description=request.POST.get('description', '').strip(),
            created_by=request.user,
            format=tournament_format,
            time_control_minutes=int(request.POST.get('time_control_minutes', 15)),
            time_control_increment=int(request.POST.get('time_control_increment', 0)),
            rounds_total=int(rounds_total) if rounds_total else None,
        )
        tournament.organizers.add(request.user)
        messages.success(request, f'Torneo "{tournament.name}" creado.')
        return redirect('tournament_detail', tournament_id=tournament.id)


class TournamentDetailView(LoginRequiredMixin, DetailView):
    model = Tournament
    template_name = 'tournaments/tournament_detail.html'
    context_object_name = 'tournament'
    pk_url_kwarg = 'tournament_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tournament = self.object
        user = self.request.user

        TournamentService.sync_finished_games(tournament)

        context['is_organizer'] = tournament.is_organizer(user)
        context['standings'] = StandingsService.compute_standings(tournament)
        context['rounds'] = tournament.rounds.prefetch_related('pairings').all()
        context['my_participation'] = tournament.participants.filter(user=user).first()
        context['can_register'] = (
            tournament.status in [Tournament.Status.DRAFT, Tournament.Status.REGISTRATION_OPEN]
            and not tournament.is_organizer(user)
        )
        return context


@login_required
def register(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    try:
        TournamentService.register(tournament, request.user)
    except TournamentError as exc:
        messages.error(request, str(exc))
    return redirect('tournament_detail', tournament_id=tournament.id)


@login_required
def withdraw(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    try:
        TournamentService.withdraw(tournament, request.user)
    except TournamentError as exc:
        messages.error(request, str(exc))
    return redirect('tournament_detail', tournament_id=tournament.id)


@login_required
def open_registration(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not tournament.is_organizer(request.user):
        return HttpResponseForbidden("Solo el organizador puede abrir las inscripciones.")
    if tournament.status != Tournament.Status.DRAFT:
        messages.error(request, "Solo un torneo en borrador puede abrir inscripciones.")
        return redirect('tournament_detail', tournament_id=tournament.id)

    tournament.status = Tournament.Status.REGISTRATION_OPEN
    tournament.save(update_fields=['status'])
    return redirect('tournament_detail', tournament_id=tournament.id)


@login_required
def start_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not tournament.is_organizer(request.user):
        return HttpResponseForbidden("Solo el organizador puede iniciar el torneo.")

    try:
        TournamentService.start_tournament(tournament)
    except TournamentError as exc:
        messages.error(request, str(exc))
    return redirect('tournament_detail', tournament_id=tournament.id)


@login_required
def generate_next_round(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not tournament.is_organizer(request.user):
        return HttpResponseForbidden("Solo el organizador puede generar rondas.")

    try:
        TournamentService.generate_next_round(tournament)
    except TournamentError as exc:
        messages.error(request, str(exc))
    return redirect('tournament_detail', tournament_id=tournament.id)


@login_required
def finalize_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not tournament.is_organizer(request.user):
        return HttpResponseForbidden("Solo el organizador puede finalizar el torneo.")

    try:
        TournamentService.finalize_tournament(tournament)
        messages.success(request, 'Torneo finalizado.')
    except TournamentError as exc:
        messages.error(request, str(exc))
    return redirect('tournament_detail', tournament_id=tournament.id)


@login_required
def cancel_tournament(request, tournament_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    if not tournament.is_organizer(request.user):
        return HttpResponseForbidden("Solo el organizador puede cancelar el torneo.")

    TournamentService.cancel_tournament(tournament)
    messages.success(request, 'Torneo cancelado.')
    return redirect('tournament_detail', tournament_id=tournament.id)


class RoundDetailView(LoginRequiredMixin, DetailView):
    model = Round
    template_name = 'tournaments/round_detail.html'
    context_object_name = 'round'
    pk_url_kwarg = 'round_id'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)
        self.tournament = get_object_or_404(Tournament, id=kwargs['tournament_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return get_object_or_404(Round, id=self.kwargs['round_id'], tournament=self.tournament)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        TournamentService.sync_finished_games(self.tournament)
        context['tournament'] = self.tournament
        context['is_organizer'] = self.tournament.is_organizer(self.request.user)
        context['pairings'] = self.object.pairings.select_related('white_player', 'black_player', 'game').all()
        return context


@login_required
def close_round(request, tournament_id, round_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    round_obj = get_object_or_404(Round, id=round_id, tournament=tournament)
    if not tournament.is_organizer(request.user):
        return HttpResponseForbidden("Solo el organizador puede cerrar la ronda.")

    try:
        TournamentService.close_round(tournament, round_obj)
        messages.success(request, f'Ronda {round_obj.number} cerrada.')
    except TournamentError as exc:
        messages.error(request, str(exc))
    return redirect('round_detail', tournament_id=tournament.id, round_id=round_obj.id)


@login_required
def record_incident(request, tournament_id, round_id, pairing_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    round_obj = get_object_or_404(Round, id=round_id, tournament=tournament)
    pairing = get_object_or_404(Pairing, id=pairing_id, round=round_obj)

    if not tournament.is_organizer(request.user):
        return JsonResponse({'error': 'Solo el organizador puede corregir incidencias.'}, status=403)

    white_absent = request.POST.get('white_absent') == 'true'
    black_absent = request.POST.get('black_absent') == 'true'

    try:
        TournamentService.record_incident(pairing, white_absent=white_absent, black_absent=black_absent)
    except TournamentError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'success': True, 'result': pairing.result})


@login_required
def set_manual_result(request, tournament_id, round_id, pairing_id):
    tournament = get_object_or_404(Tournament, id=tournament_id)
    round_obj = get_object_or_404(Round, id=round_id, tournament=tournament)
    pairing = get_object_or_404(Pairing, id=pairing_id, round=round_obj)

    if not tournament.is_organizer(request.user):
        return JsonResponse({'error': 'Solo el organizador puede corregir resultados.'}, status=403)

    result = request.POST.get('result', '')
    try:
        TournamentService.set_manual_result(pairing, result)
    except TournamentError as exc:
        return JsonResponse({'success': False, 'error': str(exc)}, status=400)

    return JsonResponse({'success': True, 'result': pairing.result})
