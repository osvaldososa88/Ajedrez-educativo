import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import View

from apps.accounts.models import CustomUser
from .models import Bot
from .services import BotError, BotService

logger = logging.getLogger(__name__)


class BotListView(LoginRequiredMixin, View):
    """
    "Jugar contra Bots": three category sections with a visual progression
    path per category, plus the student's bot stats (kept separate from the
    competitive ELO stats).
    """

    def get(self, request):
        categories = [
            {'value': Bot.Category.BEGINNER, 'label': 'Principiante', 'icon': '🟢', 'color': '#10b981'},
            {'value': Bot.Category.INTERMEDIATE, 'label': 'Intermedio', 'icon': '🟡', 'color': '#f59e0b'},
            {'value': Bot.Category.ADVANCED, 'label': 'Avanzado', 'icon': '🔴', 'color': '#ef4444'},
        ]
        states = BotService.bot_states_for_user(request.user)
        sections = []
        for cat in categories:
            bots = list(
                Bot.objects.filter(category=cat['value'], is_active=True).select_related('profile')
            )
            items = []
            for bot in bots:
                state = states.get(bot.pk, {'unlocked': False, 'defeated': False})
                items.append({
                    'bot': bot,
                    'unlocked': state['unlocked'],
                    'defeated': state['defeated'],
                })
            summary = BotService.category_summary(request.user, cat['value'])
            sections.append({
                **cat,
                'bots': items,
                'total': summary['total'],
                'defeated_count': summary['defeated_count'],
                'unlocked_count': summary['unlocked_count'],
                'next_opponent': summary['next_opponent'],
            })

        context = {
            'sections': sections,
            'bot_stats': BotService.get_stats_summary(request.user),
        }
        return render(request, 'bots/bot_list.html', context)


class BotDetailView(LoginRequiredMixin, View):
    """Bot profile card: identity + strength label + play actions."""

    def get(self, request, bot_id):
        bot = get_object_or_404(
            Bot.objects.select_related('profile', 'user'), pk=bot_id, is_active=True,
        )
        unlocked = BotService.is_bot_unlocked(request.user, bot)
        # Previous bot in the same category, to explain how to unlock this one.
        previous = Bot.objects.filter(
            category=bot.category, is_active=True, order__lt=bot.order,
        ).order_by('-order', '-pk').first()

        context = {
            'bot': bot,
            'unlocked': unlocked,
            'previous_bot': previous,
            'stats': BotService.get_stats_summary(request.user),
        }
        return render(request, 'bots/bot_detail.html', context)


def start_bot_game(request, bot_id):
    """
    POST-only: creates (or resumes) the game against the bot after validating
    unlock/active status server-side. The client can only choose the color.
    """
    if not request.user.is_authenticated:
        return redirect('login')
    if request.method != 'POST':
        return redirect('bots_list')

    bot = get_object_or_404(Bot, pk=bot_id)
    color = request.POST.get('color', 'random')
    try:
        game = BotService.start_game(request.user, bot, color=color)
    except BotError as exc:
        messages.error(request, str(exc))
        return redirect('bot_detail', bot_id=bot.id)

    return redirect('game_detail', game_id=game.id)
