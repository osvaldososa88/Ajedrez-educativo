import random
from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, View
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from apps.accounts.models import CustomUser
from .models import Game, Challenge, Move
import chess

class ChallengeListView(LoginRequiredMixin, ListView):
    model = Challenge
    template_name = 'games/challenges.html'
    context_object_name = 'received_challenges'

    def get_queryset(self):
        return Challenge.objects.filter(receiver=self.request.user, status=Challenge.Status.PENDING).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sent_challenges'] = Challenge.objects.filter(
            sender=self.request.user,
            status=Challenge.Status.PENDING
        ).order_by('-created_at')
        context['my_games'] = Game.objects.filter(
            status=Game.Status.IN_PROGRESS
        ).filter(
            models.Q(white_player=self.request.user) | models.Q(black_player=self.request.user)
        ).order_by('-updated_at')
        return context

@login_required
def create_challenge(request, user_id):
    if request.method == 'POST':
        receiver = get_object_or_404(CustomUser, id=user_id)
        if receiver == request.user:
            return HttpResponseForbidden("No puedes desafiarte a ti mismo.")

        time_control = int(request.POST.get('time_control_minutes', 10))
        increment = int(request.POST.get('time_control_increment', 0))

        challenge = Challenge.objects.create(
            sender=request.user,
            receiver=receiver,
            time_control_minutes=time_control,
            time_control_increment=increment
        )
        return redirect('challenges_list')
    return redirect('classmates')

@login_required
def accept_challenge(request, challenge_id):
    challenge = get_object_or_404(Challenge, id=challenge_id, receiver=request.user, status=Challenge.Status.PENDING)
    
    # Assign colors randomly
    players = [challenge.sender, challenge.receiver]
    random.shuffle(players)
    white_player, black_player = players[0], players[1]

    time_ms = challenge.time_control_minutes * 60 * 1000

    game = Game.objects.create(
        white_player=white_player,
        black_player=black_player,
        time_control_minutes=challenge.time_control_minutes,
        time_control_increment=challenge.time_control_increment,
        white_time_left_ms=time_ms,
        black_time_left_ms=time_ms,
        fen_current=chess.STARTING_FEN,
        status=Game.Status.IN_PROGRESS,
        last_move_at=timezone.now()
    )

    challenge.status = Challenge.Status.ACCEPTED
    challenge.game = game
    challenge.save()

    return redirect('game_detail', game_id=game.id)

@login_required
def decline_challenge(request, challenge_id):
    challenge = get_object_or_404(Challenge, id=challenge_id, receiver=request.user, status=Challenge.Status.PENDING)
    challenge.status = Challenge.Status.DECLINED
    challenge.save()
    return redirect('challenges_list')

class GameDetailView(LoginRequiredMixin, DetailView):
    model = Game
    template_name = 'games/game_detail.html'
    context_object_name = 'game'
    pk_url_kwarg = 'game_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        game = self.object
        user = self.request.user

        is_white = (user == game.white_player)
        is_black = (user == game.black_player)
        is_player = is_white or is_black

        context['is_player'] = is_player
        context['is_white'] = is_white
        context['is_black'] = is_black
        context['player_color'] = 'white' if is_white else ('black' if is_black else 'spectator')
        context['moves'] = game.moves.order_by('ply')
        return context

@login_required
def export_pgn(request, game_id):
    game = get_object_or_404(Game, id=game_id)
    pgn_content = game.generate_pgn()
    response = HttpResponse(pgn_content, content_type='application/x-chess-pgn')
    response['Content-Disposition'] = f'attachment; filename="partida_{game.id.hex[:8]}.pgn"'
    return response
