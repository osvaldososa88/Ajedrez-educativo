"""
Bot training services: progression/unlocks, game creation and bot replies.

All state-affecting operations are validated server-side; the client can only
say "play this bot" and "this color" — never unlock, difficulty or results.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.games.models import Game
from .engine import BotEngineManager
from .models import Bot, BotProgress, BotProfile

logger = logging.getLogger(__name__)


class BotError(Exception):
    """Raised for invalid bot actions (locked bot, inactive bot, etc.)."""


class BotService:
    # --- Identity ------------------------------------------------------------

    @staticmethod
    def is_bot_user(user) -> bool:
        return bool(user and getattr(user, 'is_authenticated', False) and user.is_bot_account)

    @staticmethod
    def bot_for_user(user):
        if not user:
            return None
        try:
            return user.bot_profile
        except Bot.DoesNotExist:
            return None

    @staticmethod
    def human_player(game: Game):
        """The human player of a bot game (None if not a bot game)."""
        if game.white_player.is_bot_account:
            return game.black_player
        if game.black_player.is_bot_account:
            return game.white_player
        return None

    @staticmethod
    def bot_for_game(game: Game):
        """The Bot object playing in a bot game (None if not a bot game)."""
        if not game.vs_bot:
            return None
        from apps.bots.models import Bot
        if game.white_player.is_bot_account:
            try:
                return game.white_player.bot_profile
            except Bot.DoesNotExist:
                return None
        if game.black_player.is_bot_account:
            try:
                return game.black_player.bot_profile
            except Bot.DoesNotExist:
                return None
        return None

    # --- Progression -----------------------------------------------------------

    @staticmethod
    def first_active_bot(category: str):
        return Bot.objects.filter(category=category, is_active=True).order_by('order', 'pk').first()

    @staticmethod
    def next_active_bot(bot: Bot):
        """Next ACTIVE bot in the same category after `bot` (skips deactivated ones)."""
        return Bot.objects.filter(
            category=bot.category, is_active=True, order__gt=bot.order,
        ).order_by('order', 'pk').first()

    @staticmethod
    def is_bot_unlocked(user, bot: Bot) -> bool:
        """
        A bot is unlocked when it is the first ACTIVE bot of its category
        (derived, no row needed) or has an explicit unlock row for this user.
        """
        if not user or not user.is_authenticated or user.is_bot_account:
            return False
        first = BotService.first_active_bot(bot.category)
        if first is not None and first.pk == bot.pk:
            return True
        return BotProgress.objects.filter(user=user, bot=bot, unlocked=True).exists()

    @classmethod
    def bot_states_for_user(cls, user, category: str = None):
        """
        Efficient listing: 1 query for bots (+profile) + 1 for progress rows.
        Returns {bot_id: {'unlocked': bool, 'defeated': bool}}.
        """
        bots = Bot.objects.filter(is_active=True).select_related('profile')
        if category:
            bots = bots.filter(category=category)
        first_per_category = {}
        for category_value, _label in Bot.Category.choices:
            first = cls.first_active_bot(category_value)
            if first:
                first_per_category[category_value] = first.pk

        progress = {
            p.bot_id: p
            for p in BotProgress.objects.filter(user=user, bot__in=bots)
        }
        states = {}
        for bot in bots:
            p = progress.get(bot.pk)
            unlocked = (first_per_category.get(bot.category) == bot.pk) or bool(p and p.unlocked)
            states[bot.pk] = {
                'unlocked': unlocked,
                'defeated': bool(p and p.defeated),
            }
        return states

    @classmethod
    def category_summary(cls, user, category: str) -> dict:
        """Counts used by the UI: total / unlocked / defeated / next opponent."""
        bots = list(
            Bot.objects.filter(category=category, is_active=True).select_related('profile')
        )
        states = cls.bot_states_for_user(user, category=category)
        defeated = [b for b in bots if states.get(b.pk, {}).get('defeated')]
        unlocked = [b for b in bots if states.get(b.pk, {}).get('unlocked')]
        next_opponent = next(
            (b for b in bots if not states.get(b.pk, {}).get('defeated')), None
        )
        return {
            'total': len(bots),
            'defeated_count': len(defeated),
            'unlocked_count': len(unlocked),
            'next_opponent': next_opponent,
        }

    # --- Game creation ---------------------------------------------------------

    @classmethod
    def start_game(cls, user, bot: Bot, color: str = 'random') -> Game:
        """
        Starts (or resumes) a training game against `bot`. Server-side checks:
        bot must exist, be active and be unlocked for this user. The color
        choice is validated here; 'random' shuffles like human challenges.
        """
        if user.is_bot_account:
            raise BotError("Los bots no pueden jugar entre sí.")
        if not bot.is_active:
            raise BotError("Este bot no está disponible actualmente.")
        if not cls.is_bot_unlocked(user, bot):
            raise BotError("Aún no has desbloqueado a este bot.")
        if color not in ('white', 'black', 'random'):
            raise BotError("Color inválido.")

        # Resume instead of stacking simultaneous games against the same bot.
        existing = Game.objects.filter(
            vs_bot=True,
            status=Game.Status.IN_PROGRESS,
            white_player__in=[user, bot.user],
            black_player__in=[user, bot.user],
        ).first()
        if existing:
            return existing

        if color == 'random':
            from random import shuffle
            players = [user, bot.user]
            shuffle(players)
            white_player, black_player = players
        elif color == 'white':
            white_player, black_player = user, bot.user
        else:
            white_player, black_player = bot.user, user

        # Bot games are untimed (the clock never starts for them; see
        # GameConsumer.process_move), thinking time is unlimited by design.
        time_ms = 10 * 60 * 1000
        return Game.objects.create(
            white_player=white_player,
            black_player=black_player,
            time_control_minutes=10,
            time_control_increment=0,
            white_time_left_ms=time_ms,
            black_time_left_ms=time_ms,
            status=Game.Status.IN_PROGRESS,
            is_competitive=False,  # never affects the competitive ELO
            vs_bot=True,
        )

    # --- Bot replies ----------------------------------------------------------

    @classmethod
    def prepare_bot_move(cls, game_id) -> dict:
        """
        Returns what the bot needs to move, or None when it is not the bot's
        turn. Pure DB work; the (blocking) engine call happens separately so
        the consumer can run it inside a worker thread.
        """
        try:
            game = Game.objects.select_related(
                'white_player', 'black_player',
                'white_player__bot_profile', 'black_player__bot_profile',
            ).get(pk=game_id)
        except Game.DoesNotExist:
            return None

        if game.status != Game.Status.IN_PROGRESS or not game.vs_bot:
            return None

        if game.turn == Game.Turn.WHITE:
            bot_user = game.white_player if game.white_player.is_bot_account else None
        else:
            bot_user = game.black_player if game.black_player.is_bot_account else None
        if bot_user is None:
            return None

        bot = getattr(bot_user, 'bot_profile', None)
        if bot is None or not bot.is_active:
            # Bot deactivated mid-game: the game simply waits (documented).
            return None

        return {'bot_user_id': bot_user.id, 'fen': game.fen_current, 'profile_id': bot.profile_id}

    @staticmethod
    def compute_uci(fen: str, profile_id: int) -> str:
        """Blocking engine call. Run inside a worker thread (GameConsumer)."""
        from apps.core.chess_engine import ChessEngine
        board = ChessEngine.get_board_from_fen(fen)
        profile = BotProfile.objects.get(pk=profile_id)
        return BotEngineManager.select_move(board, profile)

    # --- Finish handling ---------------------------------------------------------

    @classmethod
    def on_game_finished(cls, game: Game) -> dict:
        """
        Called once a game reaches a terminal state (idempotent).
        For bot games: when the human WINS, mark the bot defeated (first time
        only) and unlock the next ACTIVE bot of the same category, notifying
        the student. Losses and draws never unlock anything.
        """
        result = {'handled': False}
        if not game.vs_bot:
            return result
        if game.status == Game.Status.IN_PROGRESS or game.winner is None:
            return result

        human = cls.human_player(game)
        if human is None:
            return result
        bot_user = game.black_player if game.white_player_id == human.id else game.white_player
        if not bot_user.is_bot_account:
            return result

        try:
            bot = bot_user.bot_profile
        except Bot.DoesNotExist:
            return result

        human_is_winner = (
            (game.winner == Game.Winner.WHITE and game.white_player_id == human.id) or
            (game.winner == Game.Winner.BLACK and game.black_player_id == human.id)
        )
        if not human_is_winner:
            return result

        from apps.games.models import Notification

        with transaction.atomic():
            progress, created = BotProgress.objects.get_or_create(
                user=human, bot=bot,
                defaults={'unlocked': True, 'defeated': True, 'defeated_at': timezone.now()},
            )
            first_defeat = created or not progress.defeated
            if not created:
                progress.unlocked = True
                progress.defeated = True
                if progress.defeated_at is None:
                    progress.defeated_at = timezone.now()
                progress.save(update_fields=['unlocked', 'defeated', 'defeated_at', 'updated_at'])

            result.update({'handled': True, 'first_defeat': first_defeat})
            if not first_defeat:
                return result

            # Unlock the next ACTIVE bot in this category (skips deactivated).
            nxt = cls.next_active_bot(bot)
            if nxt:
                BotProgress.objects.update_or_create(
                    user=human, bot=nxt, defaults={'unlocked': True},
                )
                Notification.objects.create(
                    user=human,
                    message=(
                        f"🏆 ¡Le ganaste a {bot.display_name} ({bot.displayed_elo})! "
                        f"Desbloqueaste a {nxt.display_name} ({nxt.displayed_elo})."
                    ),
                    game=game,
                )
                result['unlocked'] = nxt.display_name
            else:
                Notification.objects.create(
                    user=human,
                    message=(
                        f"👑 ¡Completaste todos los bots de nivel "
                        f"{bot.get_category_display()} derrotando a {bot.display_name}!"
                    ),
                    game=game,
                )
        return result

    # --- Stats ---------------------------------------------------------------------

    @staticmethod
    def get_stats_summary(user) -> dict:
        """W/D/L against bots (kept separate from the competitive ELO stats)."""
        from django.db.models import Q
        games = Game.objects.filter(
            Q(vs_bot=True, white_player=user) | Q(vs_bot=True, black_player=user),
            status=Game.Status.FINISHED,
        )
        wins = draws = losses = 0
        for g in games:
            if g.winner == Game.Winner.DRAW:
                draws += 1
            elif (g.winner == Game.Winner.WHITE and g.white_player_id == user.id) or \
                 (g.winner == Game.Winner.BLACK and g.black_player_id == user.id):
                wins += 1
            else:
                losses += 1
        defeated_bots = BotProgress.objects.filter(user=user, defeated=True).count()
        return {
            'games': games.count(),
            'wins': wins,
            'draws': draws,
            'losses': losses,
            'defeated_bots': defeated_bots,
        }



