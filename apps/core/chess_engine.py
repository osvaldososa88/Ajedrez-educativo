import chess
import chess.pgn
import io
from datetime import datetime

class ChessEngine:
    """
    Wrapper around python-chess to enforce server-authoritative rules,
    legal move validation, special moves (castling, en passant, promotion),
    and game status evaluations.
    """

    @staticmethod
    def create_initial_board() -> chess.Board:
        return chess.Board()

    @staticmethod
    def get_board_from_fen(fen: str) -> chess.Board:
        try:
            return chess.Board(fen)
        except ValueError:
            return chess.Board()

    @staticmethod
    def get_legal_moves(board_or_fen) -> list:
        if isinstance(board_or_fen, str):
            board = ChessEngine.get_board_from_fen(board_or_fen)
        else:
            board = board_or_fen

        moves = []
        for move in board.legal_moves:
            from_sq = chess.square_name(move.from_square)
            to_sq = chess.square_name(move.to_square)
            promotion = chess.piece_symbol(move.promotion) if move.promotion else None
            san = board.san(move)
            moves.append({
                'from': from_sq,
                'to': to_sq,
                'uci': move.uci(),
                'san': san,
                'promotion': promotion
            })
        return moves

    @staticmethod
    def evaluate_board_state(board: chess.Board) -> dict:
        is_check = board.is_check()
        is_checkmate = board.is_checkmate()
        is_stalemate = board.is_stalemate()
        is_insufficient = board.is_insufficient_material()
        is_seventyfive = board.is_seventyfive_moves()
        is_fivefold = board.is_fivefold_repetition()

        is_game_over = board.is_game_over()

        winner = None
        finish_reason = None

        if is_checkmate:
            # The player whose turn it is is checkmated, so the previous player won.
            winner = 'black' if board.turn == chess.WHITE else 'white'
            finish_reason = 'CHECKMATE'
        elif is_stalemate:
            winner = 'draw'
            finish_reason = 'STALEMATE'
        elif is_insufficient:
            winner = 'draw'
            finish_reason = 'INSUFFICIENT_MATERIAL'
        elif is_seventyfive or board.is_fifty_moves():
            winner = 'draw'
            finish_reason = 'DRAW_50_MOVES'
        elif is_fivefold or board.is_repetition(3):
            winner = 'draw'
            finish_reason = 'REPETITION'
        elif is_game_over:
            winner = 'draw'
            finish_reason = 'DRAW_RULES'

        return {
            'fen': board.fen(),
            'turn': 'white' if board.turn == chess.WHITE else 'black',
            'is_check': is_check,
            'is_game_over': is_game_over,
            'winner': winner,
            'finish_reason': finish_reason,
            'fullmove_number': board.fullmove_number,
            'halfmove_clock': board.halfmove_clock,
        }

    @staticmethod
    def execute_move(fen: str, uci_str: str) -> dict:
        """
        Validates and executes a move given in UCI format (e.g. 'e2e4' or 'e7e8q').
        Returns dict containing updated board state, SAN notation, and move details.
        Raises ValueError if move is illegal.
        """
        board = ChessEngine.get_board_from_fen(fen)

        try:
            move = chess.Move.from_uci(uci_str)
        except ValueError as e:
            raise ValueError(f"Formato de movimiento inválido: {uci_str}") from e

        if move not in board.legal_moves:
            raise ValueError(f"Movimiento ilegal en esta posición: {uci_str}")

        san = board.san(move)
        board.push(move)
        state = ChessEngine.evaluate_board_state(board)
        state['last_move_san'] = san
        state['last_move_uci'] = uci_str
        return state

    @staticmethod
    def generate_pgn(white_name: str, black_name: str, uci_moves: list, result: str = "*", date_str: str = None) -> str:
        """
        Generates a standardized PGN string from a list of UCI move strings.
        """
        game = chess.pgn.Game()
        game.headers["Event"] = "Partida Escolar de Ajedrez"
        game.headers["Site"] = "Plataforma Ajedrez Educativo"
        game.headers["Date"] = date_str or datetime.now().strftime("%Y.%m.%d")
        game.headers["Round"] = "1"
        game.headers["White"] = white_name
        game.headers["Black"] = black_name
        game.headers["Result"] = result

        node = game
        temp_board = chess.Board()
        for uci in uci_moves:
            try:
                move = chess.Move.from_uci(uci)
                if move in temp_board.legal_moves:
                    node = node.add_variation(move)
                    temp_board.push(move)
            except Exception:
                break

        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        return game.accept(exporter)
