import chess
from apps.analysis.models import AnalysisJob, MoveAnalysis
from apps.games.models import Game
from apps.training.models import Puzzle
from .models import DetectedGameError
from .error_classifier import classify_error, evaluate_best_continuation


class PersonalizationError(Exception):
    """Raised for invalid error-detection requests."""


def _student_for_ply(game: Game, ply: int):
    # Convention shared with apps.games.models.Move and the analysis job builder:
    # ply 1 is White's first move, so odd plies were played by White.
    return game.white_player if ply % 2 == 1 else game.black_player


def _build_hints(classification: dict, board: chess.Board) -> list:
    """Progressive, non-revealing hints: a category nudge, then a piece-type nudge."""
    hints = [f"Piensa en un recurso típico de {Puzzle.Category(classification['category']).label}."]

    best_uci = classification.get('best_move_uci')
    if best_uci and len(best_uci) >= 2:
        try:
            from_square = chess.parse_square(best_uci[:2])
            piece = board.piece_at(from_square)
        except ValueError:
            piece = None
        if piece:
            piece_names = {
                chess.PAWN: 'peón', chess.KNIGHT: 'caballo', chess.BISHOP: 'alfil',
                chess.ROOK: 'torre', chess.QUEEN: 'dama', chess.KING: 'rey',
            }
            hints.append(f"La mejor continuación involucra a tu {piece_names.get(piece.piece_type, 'pieza')}.")
    return hints


def _build_title_and_description(game: Game, move_analysis: MoveAnalysis) -> tuple:
    date_str = game.created_at.strftime('%d/%m/%Y') if game and game.created_at else ''
    title = f"Corrige tu error — partida del {date_str} (jugada {move_analysis.ply})".strip()
    description = (
        f"En esta posición jugaste {move_analysis.move_san}, pero había una continuación mejor. "
        "Antes de mover, pregúntate: ¿qué amenazas hay en el tablero?, ¿alguna pieza está en peligro?, "
        "¿hay algún jaque o captura forzada que no estás viendo? Encuentra la mejor jugada."
    )
    return title, description


class ErrorDetectionService:
    """
    Converts significant mistakes (MISTAKE/BLUNDER) from a completed AnalysisJob
    into private training puzzles for the student who made them. Idempotent:
    calling it again on the same job only processes moves not yet converted.
    """

    SIGNIFICANT_QUALITIES = [MoveAnalysis.Quality.MISTAKE, MoveAnalysis.Quality.BLUNDER]

    @classmethod
    def generate_from_job(cls, job: AnalysisJob) -> list:
        if job.status != AnalysisJob.Status.COMPLETED:
            raise PersonalizationError("El análisis debe estar completo para generar entrenamiento.")
        if job.game is None:
            raise PersonalizationError("Solo se puede generar entrenamiento a partir de partidas jugadas en la plataforma.")

        game = job.game
        candidate_moves = job.move_analyses.filter(
            quality__in=cls.SIGNIFICANT_QUALITIES,
            detected_error__isnull=True,
        )

        created = []
        for move_analysis in candidate_moves:
            student = _student_for_ply(game, move_analysis.ply)
            if student is None:
                continue
            created.append(cls._convert_move(game, student, move_analysis))
        return created

    @classmethod
    def _convert_move(cls, game: Game, student, move_analysis: MoveAnalysis) -> DetectedGameError:
        eval_before = evaluate_best_continuation(move_analysis.fen_before)
        classification = classify_error(move_analysis.fen_before, move_analysis, eval_before)

        board = chess.Board(move_analysis.fen_before)
        side_to_move = Puzzle.SideToMove.WHITE if board.turn == chess.WHITE else Puzzle.SideToMove.BLACK
        title, description = _build_title_and_description(game, move_analysis)

        generated_puzzle = None
        if classification['best_move_uci']:
            generated_puzzle = Puzzle(
                title=title,
                description=description,
                author=student,
                initial_fen=move_analysis.fen_before,
                side_to_move=side_to_move,
                category=classification['category'],
                theme=classification['theme'],
                difficulty=classification['difficulty'],
                objective=Puzzle.Objective.BEST_CONTINUATION,
                solution_moves=[classification['best_move_uci']],
                hints=_build_hints(classification, board),
                status=Puzzle.Status.DRAFT,
            )
            generated_puzzle.save()

        return DetectedGameError.objects.create(
            move_analysis=move_analysis,
            student=student,
            game=game,
            fen_before=move_analysis.fen_before,
            student_move_uci=move_analysis.move_uci,
            student_move_san=move_analysis.move_san,
            best_move_uci=classification['best_move_uci'],
            best_move_san=classification['best_move_san'],
            score_cp_before=classification['score_cp_before'],
            mate_in_before=classification['mate_in_before'],
            category=classification['category'],
            theme=classification['theme'],
            difficulty=classification['difficulty'],
            generated_puzzle=generated_puzzle,
        )
