import shutil
import os
from typing import Dict, Any, List, Optional
import chess
import chess.engine
from django.conf import settings

PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 20000
}

class StockfishEngine:
    """
    Wrapper for Stockfish engine integration using python-chess UCI interface.
    Includes fallback python-chess evaluator if stockfish executable is not available on host.
    """

    @classmethod
    def get_stockfish_path(cls) -> Optional[str]:
        configured_path = getattr(settings, 'STOCKFISH_PATH', None)
        if configured_path and os.path.exists(configured_path):
            return configured_path
        return shutil.which('stockfish') or shutil.which('stockfish.exe')

    @classmethod
    def evaluate_position(cls, fen: str, depth: int = 15, time_limit: float = 0.5) -> Dict[str, Any]:
        board = chess.Board(fen)
        stockfish_path = cls.get_stockfish_path()

        if stockfish_path:
            try:
                engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
                info = engine.analyse(board, chess.engine.Limit(depth=depth, time=time_limit))
                engine.quit()

                score_obj = info.get("score", None)
                cp_val = None
                mate_val = None

                if score_obj:
                    pov_score = score_obj.pov(board.turn)
                    if pov_score.is_mate():
                        mate_val = pov_score.mate()
                    else:
                        cp_val = pov_score.score()

                pv_moves = info.get("pv", [])
                best_move_uci = pv_moves[0].uci() if pv_moves else None
                best_move_san = board.san(pv_moves[0]) if pv_moves else None

                # Convert PV moves to SAN list
                pv_san_list = []
                temp_board = board.copy()
                for move in pv_moves[:5]:
                    pv_san_list.append(temp_board.san(move))
                    temp_board.push(move)

                return {
                    'fen': fen,
                    'score_cp': cp_val,
                    'mate_in': mate_val,
                    'best_move_uci': best_move_uci,
                    'best_move_san': best_move_san,
                    'pv_san': pv_san_list,
                    'depth': info.get("depth", depth),
                    'engine_name': 'Stockfish'
                }
            except Exception:
                pass # Fallback below if engine invocation fails

        # Fallback Python-Chess evaluation if Stockfish binary is unavailable
        return cls._fallback_python_eval(board, fen, depth)

    @classmethod
    def _fallback_python_eval(cls, board: chess.Board, fen: str, depth: int) -> Dict[str, Any]:
        """Simple material & mobility heuristic evaluation when Stockfish binary is absent."""
        if board.is_checkmate():
            return {
                'fen': fen,
                'score_cp': None,
                'mate_in': 0,
                'best_move_uci': None,
                'best_move_san': None,
                'pv_san': [],
                'depth': 1,
                'engine_name': 'Python-Chess Fallback'
            }

        # Calculate centipawn material balance from current turn perspective
        white_mat = sum(len(board.pieces(pt, chess.WHITE)) * PIECE_VALUES[pt] for pt in PIECE_VALUES)
        black_mat = sum(len(board.pieces(pt, chess.BLACK)) * PIECE_VALUES[pt] for pt in PIECE_VALUES)

        turn_cp = (white_mat - black_mat) if board.turn == chess.WHITE else (black_mat - white_mat)

        legal_moves = list(board.legal_moves)
        best_move_uci = legal_moves[0].uci() if legal_moves else None
        best_move_san = board.san(legal_moves[0]) if legal_moves else None

        return {
            'fen': fen,
            'score_cp': turn_cp,
            'mate_in': None,
            'best_move_uci': best_move_uci,
            'best_move_san': best_move_san,
            'pv_san': [best_move_san] if best_move_san else [],
            'depth': 1,
            'engine_name': 'Python-Chess Fallback'
        }

    @classmethod
    def classify_move_quality(cls, cp_loss: int) -> str:
        """Classify move quality based on centipawn loss."""
        if cp_loss <= 20:
            return 'BEST'
        elif cp_loss <= 50:
            return 'GOOD'
        elif cp_loss <= 100:
            return 'INACCURACY'
        elif cp_loss <= 250:
            return 'MISTAKE'
        else:
            return 'BLUNDER'
