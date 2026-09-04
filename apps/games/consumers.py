import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from apps.core.chess_engine import ChessEngine
from .models import Game, Move, Challenge
import chess

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
            'white_player': game.white_player.username,
            'black_player': game.black_player.username,
            'white_time_left_ms': game.white_time_left_ms,
            'black_time_left_ms': game.black_time_left_ms,
            'legal_moves': legal_moves,
            'is_check': board.is_check(),
            'moves_history': moves_history,
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

        # Deduct time elapsed before making move
        game.update_clocks()
        if game.status == Game.Status.FINISHED:
            game.save()
            # Game timed out during clock update
            board = ChessEngine.get_board_from_fen(game.fen_current)
            return {
                'success': True,
                'state': {
                    'game_id': str(game.id),
                    'status': game.status,
                    'winner': game.winner,
                    'finish_reason': game.get_finish_reason_display(),
                    'fen': game.fen_current,
                    'turn': game.turn,
                    'white_time_left_ms': game.white_time_left_ms,
                    'black_time_left_ms': game.black_time_left_ms,
                    'legal_moves': [],
                    'moves_history': list(game.moves.order_by('ply').values('ply', 'san', 'uci', 'player__username')),
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
                'white_time_left_ms': game.white_time_left_ms,
                'black_time_left_ms': game.black_time_left_ms,
                'legal_moves': legal_moves,
                'moves_history': moves_history,
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

        board = ChessEngine.get_board_from_fen(game.fen_current)
        return {
            'success': True,
            'state': {
                'game_id': str(game.id),
                'status': game.status,
                'winner': game.winner,
                'finish_reason': game.get_finish_reason_display(),
                'fen': game.fen_current,
                'turn': game.turn,
                'white_time_left_ms': game.white_time_left_ms,
                'black_time_left_ms': game.black_time_left_ms,
                'legal_moves': [],
                'moves_history': list(game.moves.order_by('ply').values('ply', 'san', 'uci', 'player__username')),
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

        return {
            'success': True,
            'state': {
                'game_id': str(game.id),
                'status': game.status,
                'winner': game.winner,
                'finish_reason': game.get_finish_reason_display(),
                'fen': game.fen_current,
                'turn': game.turn,
                'white_time_left_ms': game.white_time_left_ms,
                'black_time_left_ms': game.black_time_left_ms,
                'legal_moves': [],
                'moves_history': list(game.moves.order_by('ply').values('ply', 'san', 'uci', 'player__username')),
                'pgn': game.pgn_history
            }
        }
