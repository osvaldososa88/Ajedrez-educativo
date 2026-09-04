"""
Rule-based classification of a detected error into the same taxonomy used by
`training.Puzzle` (category/theme/difficulty). No machine learning: every rule
below is a simple, explainable condition on the position and the engine
evaluation, documented in apps/personalization/README.md.
"""
import chess
from apps.core.stockfish_engine import StockfishEngine
from apps.training.models import Puzzle


def evaluate_best_continuation(fen_before: str, depth: int = 12) -> dict:
    """Evaluates the position BEFORE the student's move to recover what they should have played."""
    return StockfishEngine.evaluate_position(fen_before, depth=depth, time_limit=0.4)


def _endgame_theme(board: chess.Board) -> str:
    has_queen = bool(board.pieces(chess.QUEEN, chess.WHITE) or board.pieces(chess.QUEEN, chess.BLACK))
    has_rook = bool(board.pieces(chess.ROOK, chess.WHITE) or board.pieces(chess.ROOK, chess.BLACK))
    has_minor = bool(
        board.pieces(chess.BISHOP, chess.WHITE) or board.pieces(chess.BISHOP, chess.BLACK)
        or board.pieces(chess.KNIGHT, chess.WHITE) or board.pieces(chess.KNIGHT, chess.BLACK)
    )
    if not has_queen and not has_rook and not has_minor:
        return Puzzle.Theme.PAWN_ENDGAME
    if not has_queen and has_rook and not has_minor:
        return Puzzle.Theme.ROOK_ENDGAME
    if not has_queen and not has_rook and has_minor:
        return Puzzle.Theme.MINOR_PIECES_ENDGAME
    return Puzzle.Theme.BEST_CONTINUATION


def _is_endgame(board: chess.Board) -> bool:
    non_pawn_king_pieces = sum(
        len(board.pieces(pt, color))
        for color in (chess.WHITE, chess.BLACK)
        for pt in (chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT)
    )
    return non_pawn_king_pieces <= 6


def classify_error(fen_before: str, move_analysis, eval_before: dict) -> dict:
    """
    Returns {'category', 'theme', 'difficulty', 'best_move_uci', 'best_move_san',
    'score_cp_before', 'mate_in_before'} using only data already available from
    the engine evaluation and the position itself.
    """
    board = chess.Board(fen_before)

    missed_forced_mate = (
        eval_before.get('mate_in') is not None
        and eval_before.get('mate_in', 0) > 0
        and eval_before.get('best_move_uci') != move_analysis.move_uci
    )

    if missed_forced_mate:
        category = Puzzle.Category.TACTICS
        theme = Puzzle.Theme.MATE
        difficulty = Puzzle.Difficulty.BEGINNER
    elif board.fullmove_number <= 10:
        category = Puzzle.Category.OPENINGS
        theme = Puzzle.Theme.OPENING_REPERTOIRE
        difficulty = Puzzle.Difficulty.INTERMEDIATE
    elif _is_endgame(board):
        category = Puzzle.Category.ENDGAME
        theme = _endgame_theme(board)
        difficulty = Puzzle.Difficulty.INTERMEDIATE
    else:
        category = Puzzle.Category.TACTICS
        theme = Puzzle.Theme.BEST_CONTINUATION
        difficulty = Puzzle.Difficulty.INTERMEDIATE

    # A blunder is, by definition, a bigger swing — usually easier to spot once
    # you know where to look, so we grade it as more approachable to re-solve.
    if move_analysis.quality == move_analysis.Quality.BLUNDER:
        difficulty = Puzzle.Difficulty.BEGINNER

    return {
        'category': category,
        'theme': theme,
        'difficulty': difficulty,
        'best_move_uci': eval_before.get('best_move_uci') or '',
        'best_move_san': eval_before.get('best_move_san') or '',
        'score_cp_before': eval_before.get('score_cp'),
        'mate_in_before': eval_before.get('mate_in'),
    }
