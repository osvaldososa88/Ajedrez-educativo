import json
import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from apps.core.chess_engine import ChessEngine
from .models import Game, Move, Challenge, ChatMessage, GlobalChatMessage
from apps.ratings.services import RatingService
from apps.bots.services import BotService
import chess

logger = logging.getLogger(__name__)


def _process_game_finish(game):
    """
    Single post-terminal hook run by every finish path (mate, timeout,
    resignation, draw, forfeit): competitive ELO + bot progression.
    Both services are idempotent, so repeated calls are safe.
    """
    rating_result = RatingService.process_game_result(game.id)
    try:
        BotService.on_game_finished(game)

    except Exception:
        # Progression must never break the game flow; it can be repaired
        # by re-processing (both paths are idempotent).
        logger.exception("Bot progression failed for game %s", game.id)
    return rating_result



class GameConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.game_id = self.scope['url_route']['kwargs']['game_id']
        self.room_group_name = f'game_{self.game_id}'

        self.game = await self.get_game(self.game_id)
        if not self.game:
            await self.close()
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

        # Send full initial game state
        state = await self.build_game_state_payload()
        await self.send_json({
            'type': 'init_state',
            'state': state
        })

        # Bot games: if it is the bot's turn (e.g. the bot plays white, or the
        # human left before the bot replied), the bot moves now.
        await self.trigger_bot_move_if_needed()


    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        msg_type = content.get('type')

        if msg_type == 'make_move':
            uci = content.get('uci')
            if uci:
                await self.handle_make_move(uci)
        elif msg_type == 'resign':
            await self.handle_resign()
        elif msg_type == 'offer_draw':
            await self.handle_offer_draw()
        elif msg_type == 'accept_draw':
            await self.handle_accept_draw()
        elif msg_type == 'send_chat':
            message = content.get('message', '').strip()
            if message:
                await self.handle_send_chat(message)
        elif msg_type == 'get_chat_history':
            await self.handle_get_chat_history()

    async def handle_make_move(self, uci: str):
        # Perform move validation and execution in DB transaction / sync context
        result = await self.process_move(self.user.id, self.game_id, uci)

        if not result['success']:
            await self.send_json({
                'type': 'error',
                'message': result['error']
            })
            return

        # Broadcast update to group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_game_update',
                'state': result['state']
            }
        )

        # Bot games: if it is now the bot's turn, compute and apply its reply
        # (a second game_update reaches everyone right after this one).
        await self.trigger_bot_move_if_needed()

    # --- Bot reply flow -------------------------------------------------------

    async def trigger_bot_move_if_needed(self):
        """
        Runs the bot reply pipeline when it is the bot's turn:
        DB check -> (blocking) Stockfish computation in a worker thread ->
        apply through the same server-authoritative process_move used by humans.
        """
        try:
            prep = await self.prepare_bot_move_data(self.game_id)
            if not prep:
                return
            uci = await self.compute_bot_move(prep['fen'], prep['profile_id'])
            if not uci:
                return
            result = await self.process_move(prep['bot_user_id'], self.game_id, uci)
            if result.get('success'):
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'broadcast_game_update',
                        'state': result['state']
                    }
                )
        except Exception:
            # The bot never blocks the human's game: errors are logged and the
            # human can simply reload (the bot retries on the next trigger).
            logger.exception("Bot move failed for game %s", self.game_id)

    @database_sync_to_async
    def prepare_bot_move_data(self, game_id):
        """Pure DB check: is it the bot's turn? (engine runs separately)."""
        return BotService.prepare_bot_move(game_id)

    @database_sync_to_async
    def compute_bot_move(self, fen, profile_id):
        """Blocking Stockfish call, executed in the executor thread."""
        return BotService.compute_uci(fen, profile_id)


    async def handle_resign(self):
        result = await self.process_resignation(self.user.id, self.game_id)
        if result['success']:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_game_update',
                    'state': result['state']
                }
            )

    async def handle_offer_draw(self):
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_draw_offer',
                'offered_by': self.user.username
            }
        )

    async def handle_accept_draw(self):
        result = await self.process_draw_acceptance(self.user.id, self.game_id)
        if result['success']:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_game_update',
                    'state': result['state']
                }
            )

    async def broadcast_game_update(self, event):
        await self.send_json({
            'type': 'game_update',
            'state': event['state']
        })

    async def broadcast_draw_offer(self, event):
        await self.send_json({
            'type': 'draw_offer',
            'offered_by': event['offered_by']
        })

    # --- Chat handlers ---

    async def handle_send_chat(self, message):
        """Save a chat message and broadcast it to the game room."""
        # Only players in the game can chat
        is_player = await self.is_game_player(self.user.id, self.game_id)
        if not is_player:
            await self.send_json({
                'type': 'error',
                'message': 'No eres jugador de esta partida.'
            })
            return

        # Check if game is still active
        game = await self.get_game(self.game_id)
        if not game or game.status != Game.Status.IN_PROGRESS:
            await self.send_json({
                'type': 'error',
                'message': 'El chat está cerrado porque la partida finalizó.'
            })
            return

        saved = await self.save_chat_message(self.user.id, self.game_id, message)
        if saved:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'broadcast_chat_message',
                    'sender': self.user.username,
                    'content': message,
                    'timestamp': timezone.now().isoformat()
                }
            )

    async def handle_get_chat_history(self):
        """Send full chat history to the requesting player."""
        is_player = await self.is_game_player(self.user.id, self.game_id)
        if not is_player:
            await self.send_json({
                'type': 'error',
                'message': 'No eres jugador de esta partida.'
            })
            return

        messages = await self.get_chat_history(self.game_id)
        await self.send_json({
            'type': 'chat_history',
            'messages': messages
        })

    async def broadcast_chat_message(self, event):
        await self.send_json({
            'type': 'chat_message',
            'sender': event['sender'],
            'content': event['content'],
            'timestamp': event['timestamp']
        })

    # --- Chat database sync methods ---

    @database_sync_to_async
    def is_game_player(self, user_id, game_id):
        try:
            game = Game.objects.get(id=game_id)
            return user_id in [game.white_player.id, game.black_player.id]
        except Game.DoesNotExist:
            return False

    @database_sync_to_async
    def save_chat_message(self, user_id, game_id, content):
        try:
            game = Game.objects.get(id=game_id)
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.get(id=user_id)
            ChatMessage.objects.create(game=game, sender=user, content=content)
            return True
        except Exception:
            return False

    @database_sync_to_async
    def get_chat_history(self, game_id):
        try:
            game = Game.objects.get(id=game_id)
            messages = ChatMessage.objects.filter(game=game).order_by('created_at')
            return [
                {
                    'sender': m.sender.username,
                    'content': m.content,
                    'timestamp': m.created_at.isoformat()
                }
                for m in messages
            ]
        except Game.DoesNotExist:
            return []

    # --- Database sync methods ---

    @database_sync_to_async
    def get_game(self, game_id):
        try:
            return Game.objects.get(id=game_id)
        except Game.DoesNotExist:
            return None

    @database_sync_to_async
    def build_game_state_payload(self):
        game = Game.objects.get(id=self.game_id)
        game.update_clocks()
        game.save()

        # If this clock update just finished the game (timeout), apply ratings
        # exactly once; subsequent reloads/reconnects hit the idempotent path.
        rating_result = _process_game_finish(game)

        board = ChessEngine.get_board_from_fen(game.fen_current)
        legal_moves = ChessEngine.get_legal_moves(board)

        moves_history = list(game.moves.order_by('ply').values('ply', 'san', 'uci', 'player__username'))

        return {
            'game_id': str(game.id),
            'status': game.status,
            'winner': game.winner,
            'finish_reason': game.get_finish_reason_display() if game.finish_reason else None,
            'fen': game.fen_current,
            'turn': game.turn,
            'white_player': game.white_player.display_name,
            'black_player': game.black_player.display_name,

            'white_time_left_ms': game.white_time_left_ms,
            'black_time_left_ms': game.black_time_left_ms,
            'clock_started': game.clock_started,
            'legal_moves': legal_moves,
            'is_check': board.is_check(),
            'moves_history': moves_history,
            'rating_changes': rating_result['changes'],
            'pgn': game.generate_pgn()
        }


    @database_sync_to_async
    def process_move(self, user_id, game_id, uci_str):
        try:
            game = Game.objects.get(id=game_id)
        except Game.DoesNotExist:
            return {'success': False, 'error': 'Partida no encontrada.'}

        if game.status != Game.Status.IN_PROGRESS:
            return {'success': False, 'error': 'La partida ha finalizado.'}

        # Check turn authorization
        is_white_player = (user_id == game.white_player.id)
        is_black_player = (user_id == game.black_player.id)

        if not (is_white_player or is_black_player):
            return {'success': False, 'error': 'No eres jugador de esta partida.'}

        if game.turn == Game.Turn.WHITE and not is_white_player:
            return {'success': False, 'error': 'Es el turno de las piezas Blancas.'}

        if game.turn == Game.Turn.BLACK and not is_black_player:
            return {'success': False, 'error': 'Es el turno de las piezas Negras.'}

        # Deduct time elapsed before making move (only if clock has started)
        game.update_clocks()
        if game.status == Game.Status.FINISHED:
            game.save()
            # Game timed out during clock update
            rating_result = _process_game_finish(game)
            return {
                'success': True,
                'state': {
                    'game_id': str(game.id),
                    'status': game.status,
                    'winner': game.winner,
                    'finish_reason': game.get_finish_reason_display(),
                    'fen': game.fen_current,
                    'turn': game.turn,
                    'clock_started': game.clock_started,
                    'white_time_left_ms': game.white_time_left_ms,
                    'black_time_left_ms': game.black_time_left_ms,
                    'legal_moves': [],
                    'moves_history': list(game.moves.order_by('ply').values('ply', 'san', 'uci', 'player__username')),
                    'rating_changes': rating_result['changes'],
                    'pgn': game.generate_pgn()
                }
            }


        # Validate and execute move using python-chess
        try:
            eval_res = ChessEngine.execute_move(game.fen_current, uci_str)
        except ValueError as e:
            return {'success': False, 'error': str(e)}

        # Increment time control if configured
        if game.turn == Game.Turn.WHITE:
            game.white_time_left_ms += (game.time_control_increment * 1000)
        else:
            game.black_time_left_ms += (game.time_control_increment * 1000)

        # Update game state
        current_ply = game.moves.count() + 1
        player = game.white_player if is_white_player else game.black_player

        Move.objects.create(
            game=game,
            ply=current_ply,
            player=player,
            uci=uci_str,
            san=eval_res['last_move_san'],
            fen_after=eval_res['fen']
        )

        game.fen_current = eval_res['fen']
        game.turn = Game.Turn.BLACK if game.turn == Game.Turn.WHITE else Game.Turn.WHITE
        game.last_move_at = timezone.now()

        # Start the clock after the first move of the black player (ply 2)
        # This ensures both players have joined the board and black has received white's first move.
        # Bot training games are untimed: their clock never starts (unlimited thinking).
        if current_ply == 2 and not game.clock_started and not game.vs_bot:
            game.clock_started = True
            game.last_move_at = timezone.now()


        # Handle game over detection
        if eval_res['is_game_over']:
            game.status = Game.Status.FINISHED
            if eval_res['winner'] == 'white':
                game.winner = Game.Winner.WHITE
            elif eval_res['winner'] == 'black':
                game.winner = Game.Winner.BLACK
            else:
                game.winner = Game.Winner.DRAW

            if eval_res['finish_reason'] == 'CHECKMATE':
                game.finish_reason = Game.FinishReason.CHECKMATE
            elif eval_res['finish_reason'] == 'STALEMATE':
                game.finish_reason = Game.FinishReason.STALEMATE
            elif eval_res['finish_reason'] == 'INSUFFICIENT_MATERIAL':
                game.finish_reason = Game.FinishReason.INSUFFICIENT_MATERIAL
            elif eval_res['finish_reason'] in ['DRAW_50_MOVES', 'REPETITION', 'DRAW_RULES']:
                game.finish_reason = Game.FinishReason.DRAW_RULES

        game.pgn_history = game.generate_pgn()
        game.save()

        # Jaque mate / tablas: la partida acaba de terminar -> aplicar ELO una vez.
        rating_result = _process_game_finish(game)

        board = ChessEngine.get_board_from_fen(game.fen_current)
        legal_moves = ChessEngine.get_legal_moves(board) if game.status == Game.Status.IN_PROGRESS else []

        moves_history = list(game.moves.order_by('ply').values('ply', 'san', 'uci', 'player__username'))

        return {
            'success': True,
            'state': {
                'game_id': str(game.id),
                'status': game.status,
                'winner': game.winner,
                'finish_reason': game.get_finish_reason_display() if game.finish_reason else None,
                'fen': game.fen_current,
                'turn': game.turn,
                'last_move': {
                    'san': eval_res['last_move_san'],
                    'uci': uci_str,
                    'player': player.username
                },
                'is_check': eval_res['is_check'],
                'clock_started': game.clock_started,
                'white_time_left_ms': game.white_time_left_ms,
                'black_time_left_ms': game.black_time_left_ms,
                'legal_moves': legal_moves,
                'moves_history': moves_history,
                'rating_changes': rating_result['changes'],
                'pgn': game.pgn_history
            }
        }


    @database_sync_to_async
    def process_resignation(self, user_id, game_id):
        try:
            game = Game.objects.get(id=game_id)
        except Game.DoesNotExist:
            return {'success': False}

        if game.status != Game.Status.IN_PROGRESS:
            return {'success': False}

        if user_id == game.white_player.id:
            game.winner = Game.Winner.BLACK
        elif user_id == game.black_player.id:
            game.winner = Game.Winner.WHITE
        else:
            return {'success': False}

        game.status = Game.Status.FINISHED
        game.finish_reason = Game.FinishReason.RESIGNATION
        game.pgn_history = game.generate_pgn()
        game.save()

        # Abandono: resultado definitivo -> aplicar ELO exactamente una vez.
        rating_result = _process_game_finish(game)

        return {
            'success': True,
            'state': {
                'game_id': str(game.id),
                'status': game.status,
                'winner': game.winner,
                'finish_reason': game.get_finish_reason_display(),
                'fen': game.fen_current,
                'turn': game.turn,
                'clock_started': game.clock_started,
                'white_time_left_ms': game.white_time_left_ms,
                'black_time_left_ms': game.black_time_left_ms,
                'legal_moves': [],
                'moves_history': list(game.moves.order_by('ply').values('ply', 'san', 'uci', 'player__username')),
                'rating_changes': rating_result['changes'],
                'pgn': game.pgn_history
            }
        }


    @database_sync_to_async
    def process_draw_acceptance(self, user_id, game_id):
        try:
            game = Game.objects.get(id=game_id)
        except Game.DoesNotExist:
            return {'success': False}

        if game.status != Game.Status.IN_PROGRESS:
            return {'success': False}

        game.status = Game.Status.FINISHED
        game.winner = Game.Winner.DRAW
        game.finish_reason = Game.FinishReason.AGREEMENT
        game.pgn_history = game.generate_pgn()
        game.save()

        # Tablas por acuerdo: resultado definitivo -> aplicar ELO exactamente una vez.
        rating_result = _process_game_finish(game)

        return {
            'success': True,
            'state': {
                'game_id': str(game.id),
                'status': game.status,
                'winner': game.winner,
                'finish_reason': game.get_finish_reason_display(),
                'fen': game.fen_current,
                'turn': game.turn,
                'clock_started': game.clock_started,
                'white_time_left_ms': game.white_time_left_ms,
                'black_time_left_ms': game.black_time_left_ms,
                'legal_moves': [],
                'moves_history': list(game.moves.order_by('ply').values('ply', 'san', 'uci', 'player__username')),
                'rating_changes': rating_result['changes'],
                'pgn': game.pgn_history
            }
        }



class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket para notificaciones en tiempo real por usuario."""

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.user_group_name = f'notifications_{self.user.id}'

        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )
        await self.accept()

        # Send unread notifications on connect
        unread = await self.get_unread_notifications()
        await self.send_json({
            'type': 'unread_notifications',
            'notifications': unread
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group_name'):
            await self.channel_layer.group_discard(
                self.user_group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        msg_type = content.get('type')
        if msg_type == 'mark_read':
            notif_id = content.get('notification_id')
            if notif_id:
                await self.mark_notification_read(notif_id)

    async def send_notification(self, event):
        """Handler for notification_new group send."""
        await self.send_json({
            'type': 'notification',
            'notification': event['notification']
        })

    async def notification_read(self, event):
        """Handler for notification_mark_read."""
        await self.send_json({
            'type': 'notification_read',
            'notification_id': event['notification_id']
        })

    @database_sync_to_async
    def get_unread_notifications(self):
        from .models import Notification
        notifications = Notification.objects.filter(
            user=self.user,
            is_read=False
        ).order_by('-created_at')[:20]
        return [
            {
                'id': str(n.id),
                'message': n.message,
                'game_id': str(n.game_id) if n.game_id else None,
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat()
            }
            for n in notifications
        ]

    @database_sync_to_async
    def mark_notification_read(self, notif_id):
        from .models import Notification
        try:
            Notification.objects.filter(id=notif_id, user=self.user).update(is_read=True)
        except Exception:
            pass


class GlobalChatConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket del chat global de la comunidad."""

    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or not self.user.is_authenticated:
            await self.close()
            return

        self.group_name = 'global_chat'

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

        # Enviar los mensajes vigentes (ciclo semanal) al conectarse
        messages = await self.get_active_messages()
        await self.send_json({
            'type': 'chat_history',
            'messages': messages
        })

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive_json(self, content):
        msg_type = content.get('type')

        if msg_type == 'send_chat':
            message = (content.get('message') or '').strip()
            if message:
                await self.handle_send_chat(message)
        elif msg_type == 'get_chat_history':
            messages = await self.get_active_messages()
            await self.send_json({
                'type': 'chat_history',
                'messages': messages
            })

    async def handle_send_chat(self, message):
        # Limitar longitud del mensaje
        if len(message) > 500:
            message = message[:500]

        saved = await self.save_message(message)
        if saved:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'broadcast_chat_message',
                    'sender': self.user.username,
                    'content': message,
                    'timestamp': timezone.now().isoformat()
                }
            )

    async def broadcast_chat_message(self, event):
        await self.send_json({
            'type': 'chat_message',
            'sender': event['sender'],
            'content': event['content'],
            'timestamp': event['timestamp']
        })

    @database_sync_to_async
    def save_message(self, content):
        try:
            GlobalChatMessage.objects.create(sender=self.user, content=content)
            return True
        except Exception:
            return False

    @database_sync_to_async
    def get_active_messages(self):
        messages = GlobalChatMessage.objects.active_messages().order_by('created_at')
        return [
            {
                'sender': m.sender.username,
                'content': m.content,
                'timestamp': m.created_at.isoformat()
            }
            for m in messages
        ]
