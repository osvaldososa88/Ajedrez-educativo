import chess
from django.db import models
from apps.core.stockfish_engine import StockfishEngine
from .models import Puzzle, PuzzleAttempt, UserTrainingStats


class PuzzleValidationService:
    """
    Validates that a puzzle is ready to be submitted for moderation / published.
    These checks are mandatory gates; they do not require a Stockfish binary to run.
    """

    @staticmethod
    def validate_for_submission(puzzle: Puzzle) -> list:
        """Mandatory gates to allow a puzzle into moderation / publication."""
        errors = []

        try:
            board = chess.Board(puzzle.initial_fen)
        except ValueError:
            errors.append("El FEN inicial no es válido.")
            return errors

        if not board.is_valid():
            errors.append("La posición inicial no es una posición de ajedrez legal.")
            return errors

        expected_turn = chess.WHITE if puzzle.side_to_move == Puzzle.SideToMove.WHITE else chess.BLACK
        if board.turn != expected_turn:
            errors.append("El lado que juega seleccionado no coincide con el turno codificado en el FEN.")

        if not puzzle.title or not puzzle.title.strip():
            errors.append("El problema debe tener un título.")

        if puzzle.puzzle_type == Puzzle.PuzzleType.OBJECTIVE:
            errors.extend(_validate_objective_puzzle(puzzle, board))
            return errors

        # --- SEQUENCE validation (existing behavior, unchanged) --------------
        solution_moves = puzzle.solution_moves or []
        if not solution_moves:
            errors.append("El problema debe tener al menos una jugada en la solución.")
            return errors

        # Reproducibility: replay the full solution sequence from the initial position.
        replay_board = board.copy()
        for idx, uci_move in enumerate(solution_moves):
            try:
                move = chess.Move.from_uci(uci_move)
            except ValueError:
                errors.append(f"La jugada solución #{idx + 1} ('{uci_move}') no tiene formato UCI válido.")
                break
            if move not in replay_board.legal_moves:
                errors.append(f"La jugada solución #{idx + 1} ('{uci_move}') es ilegal en su posición correspondiente.")
                break
            replay_board.push(move)

        # Validate any accepted variations are legal at their respective ply.
        for ply_str, variation_list in (puzzle.variations_json or {}).items():
            try:
                ply_idx = int(ply_str)
            except (TypeError, ValueError):
                errors.append(f"Índice de variante inválido: '{ply_str}'.")
                continue

            if ply_idx < 0 or ply_idx >= len(solution_moves):
                errors.append(f"La variante en el ply {ply_str} no corresponde a ningún movimiento de la solución.")
                continue

            variation_board = board.copy()
            valid_prefix = True
            for prev_uci in solution_moves[:ply_idx]:
                try:
                    prev_move = chess.Move.from_uci(prev_uci)
                except ValueError:
                    valid_prefix = False
                    break
                if prev_move not in variation_board.legal_moves:
                    valid_prefix = False
                    break
                variation_board.push(prev_move)

            if not valid_prefix:
                continue  # already reported as a reproducibility error above

            for variant_uci in variation_list:
                try:
                    variant_move = chess.Move.from_uci(variant_uci)
                except ValueError:
                    errors.append(f"La variante '{variant_uci}' en el ply {ply_str} no tiene formato UCI válido.")
                    continue
                if variant_move not in variation_board.legal_moves:
                    errors.append(f"La variante '{variant_uci}' en el ply {ply_str} es ilegal en esa posición.")

        return errors

    @staticmethod
    def engine_sanity_check(puzzle: Puzzle) -> dict:
        """
        Optional, non-blocking Stockfish evaluation to help a moderator judge the puzzle:
        evaluates the initial position and the position after the first solution move.
        Falls back gracefully to the heuristic evaluator when no Stockfish binary is present.
        """
        try:
            board = chess.Board(puzzle.initial_fen)
        except ValueError:
            return {'available': False, 'reason': 'FEN inválido'}

        eval_before = StockfishEngine.evaluate_position(puzzle.initial_fen, depth=10, time_limit=0.3)

        eval_after_first_move = None
        solution_moves = puzzle.solution_moves or []
        if solution_moves:
            try:
                move = chess.Move.from_uci(solution_moves[0])
            except ValueError:
                move = None
            if move is not None and move in board.legal_moves:
                board.push(move)
                eval_after_first_move = StockfishEngine.evaluate_position(board.fen(), depth=10, time_limit=0.3)

        return {
            'available': True,
            'eval_before': eval_before,
            'eval_after_first_move': eval_after_first_move,
        }


class PuzzleService:
    @staticmethod
    def verify_move(puzzle: Puzzle, ply_index: int, uci_move: str):
        """
        Verifies student's move against puzzle solution tree or accepted variations.
        ply_index is the 0-indexed position in puzzle.solution_moves expected for student.
        """
        solution_moves = puzzle.solution_moves or []
        if ply_index >= len(solution_moves):
            return {
                'is_correct': False,
                'completed': True,
                'message': 'El problema ya ha sido completado.'
            }

        expected_move = solution_moves[ply_index]

        # Check main line move match or accepted variations
        is_correct = (uci_move == expected_move)

        if not is_correct and puzzle.variations_json:
            # Check variations for ply_index
            variations_at_ply = puzzle.variations_json.get(str(ply_index), [])
            if uci_move in variations_at_ply:
                is_correct = True

        if not is_correct:
            return {
                'is_correct': False,
                'completed': False,
                'message': 'Movimiento incorrecto. ¡Inténtalo de nuevo!'
            }

        # Correct move logic
        next_ply = ply_index + 1
        is_completed = (next_ply >= len(solution_moves))

        computer_move_uci = None
        computer_move_san = None
        next_student_ply = next_ply

        if not is_completed and next_ply < len(solution_moves):
            # Computer counter-move
            computer_move_uci = solution_moves[next_ply]
            next_student_ply = next_ply + 1
            if next_student_ply >= len(solution_moves):
                is_completed = True

        return {
            'is_correct': True,
            'completed': is_completed,
            'next_ply_index': next_student_ply,
            'computer_counter_move': computer_move_uci,
            'message': '¡Excelente jugada! Problema resuelto.' if is_completed else '¡Jugada correcta! Sigue adelante.'
        }

    @staticmethod
    def record_attempt(user, puzzle: Puzzle, solved: bool, time_taken_seconds: int = 0, hints_used: int = 0, attempts_count: int = 1):
        """
        Records attempt and updates adaptive statistics by category and theme.
        """
        attempt = PuzzleAttempt.objects.create(
            user=user,
            puzzle=puzzle,
            solved=solved,
            attempts_count=attempts_count,
            hints_used=hints_used,
            time_taken_seconds=time_taken_seconds
        )
        update_training_stats(user, puzzle, solved, time_taken_seconds)
        return attempt


def update_training_stats(user, puzzle: Puzzle, solved: bool, time_taken_seconds: int = 0):
    """Shared adaptive-stats update (used by SEQUENCE and OBJECTIVE attempts)."""
    stats, _ = UserTrainingStats.objects.get_or_create(
        user=user,
        category=puzzle.category,
        theme=puzzle.theme,
        defaults={
            'total_attempts': 0,
            'successful_attempts': 0,
            'total_time_seconds': 0
        }
    )
    stats.total_attempts += 1
    if solved:
        stats.successful_attempts += 1
    stats.total_time_seconds += time_taken_seconds
    stats.save()
    return stats
# ============================================================================
# PROBLEMAS POR OBJETIVO (OBJECTIVE puzzles)
# Los problemas SEQUENCE siguen usando PuzzleService.verify_move sin cambios.
# ============================================================================

PIECE_TOKEN = {
    chess.PAWN: 'P',
    chess.KNIGHT: 'N',
    chess.BISHOP: 'B',
    chess.ROOK: 'R',
    chess.QUEEN: 'Q',
    chess.KING: 'K',
}
PIECE_FROM_TOKEN = {code: pt for pt, code in PIECE_TOKEN.items()}

TOKEN_LABELS = {
    'WP': 'peón blanco', 'WN': 'caballo blanco', 'WB': 'alfil blanco',
    'WR': 'torre blanca', 'WQ': 'dama blanca', 'WK': 'rey blanco',
    'BP': 'peón negro', 'BN': 'caballo negro', 'BB': 'alfil negro',
    'BR': 'torre negra', 'BQ': 'dama negra', 'BK': 'rey negro',
}


def _validate_objective_puzzle(puzzle, board):
    """Objective-specific creation gates (no Stockfish required)."""
    errors = []
    if not puzzle.objective_type:
        errors.append('Debes elegir un objetivo (p. ej. Dar jaque mate) para un problema por objetivo.')
        return errors
    valid_objectives = [v for v, _ in Puzzle.ObjectiveType.choices]
    if puzzle.objective_type not in valid_objectives:
        errors.append('El objetivo seleccionado no es compatible con el sistema actual.')
        return errors

    if board.is_game_over():
        errors.append('La posición inicial ya está terminada (jaque mate/tablas). No se puede iniciar el problema.')

    if not board.pieces(chess.KING, chess.WHITE) or not board.pieces(chess.KING, chess.BLACK):
        errors.append('Ambos bandos deben tener su rey.')

    expected_turn = chess.WHITE if puzzle.side_to_move == Puzzle.SideToMove.WHITE else chess.BLACK
    if board.turn != expected_turn:
        errors.append('El lado que juega debe ser el mismo que el turno de la posición inicial.')

    if not list(board.legal_moves):
        errors.append('El bando que juega no tiene ninguna jugada legal.')

    for token in (puzzle.critical_pieces or []):
        if not isinstance(token, str) or len(token) != 2 or token[0] not in 'WB' or token[1] not in 'PNBRQK':
            errors.append("Token de pieza crítica inválido: '%s' (usa p. ej. WR, BQ)." % token)
        else:
            color = chess.WHITE if token[0] == 'W' else chess.BLACK
            ptype = PIECE_FROM_TOKEN.get(token[1])
            if ptype is None or not board.pieces(ptype, color):
                label = TOKEN_LABELS.get(token, token)
                errors.append('La pieza crítica (%s) no está presente en la posición inicial.' % label)
    return errors
class ObjectivePuzzleEngine:
    """
    Server-authoritative engine for OBJECTIVE puzzles.

    The student plays freely against an automatic strong defender. Success
    and failure are decided ONLY from the real game state (python-chess rules)
    and the puzzle configuration — never from the client, and never from a
    static solution sequence. Multiple valid paths can reach the objective.

    State is rebuilt from `attempt.movelog` on every request, which makes the
    endpoint naturally idempotent: a repeated submission of an already-applied
    move just returns the current state.
    """

    OUTCOME_IN_PROGRESS = 'in_progress'
    OUTCOME_SUCCESS = 'success'
    OUTCOME_FAILED = 'failed'

    @staticmethod
    def human_color(puzzle):
        return chess.WHITE if puzzle.side_to_move == Puzzle.SideToMove.WHITE else chess.BLACK

    @staticmethod
    def defender_color(puzzle):
        return chess.BLACK if ObjectivePuzzleEngine.human_color(puzzle) == chess.WHITE else chess.WHITE

    @staticmethod
    def build_board(puzzle, movelog):
        board = chess.Board(puzzle.initial_fen)
        for uci in movelog or []:
            try:
                move = chess.Move.from_uci(uci)
            except ValueError:
                raise ValueError('El historial de jugadas guardado es ilegible.')
            if move not in board.legal_moves:
                raise ValueError('El historial de jugadas guardado es inconsistente con la posición.')
            board.push(move)
        return board

    @staticmethod
    def token_counts(board):
        counts = {}
        for color, letter in ((chess.WHITE, 'W'), (chess.BLACK, 'B')):
            for ptype, code in PIECE_TOKEN.items():
                counts[letter + code] = len(board.pieces(ptype, color))
        return counts

    # --- Defender (Stockfish, fuerza máxima / sin errores artificiales) ------

    @staticmethod
    def select_defender_move(board, puzzle):
        """UCI del movimiento del defensor (Stockfish, defensa máxima)."""
        from apps.bots.engine import BotEngineManager
        return BotEngineManager.select_move(board, _StrongDefenseProfile())
# --- Verificación del objetivo -------------------------------------------

    @staticmethod
    def objective_achieved(board, puzzle):
        """
        True si el objetivo configurado se cumplió tras la jugada humana.

        CHECKMATE: `board.is_checkmate()` dice que el bando al que le toca
        mover está en jaque mate. Tras una jugada humana le toca al defensor,
        así que si hay mate es porque el humano completó el objetivo.
        """
        if puzzle.objective_type == Puzzle.ObjectiveType.CHECKMATE:
            return board.is_checkmate()
        return False

    @staticmethod
    def failure_condition(board, puzzle, initial_counts):
        """
        Devuelve (es_fallo, mensaje) tras la respuesta del defensor.
        Orden de comprobación:
          1) el humano está en jaque mate;
          2) tablas / material insuficiente (no se cumplió el objetivo);
          3) se perdió una pieza crítica (la capturó el defensor).
        """
        if board.is_checkmate():
            return True, 'El defensor te dio jaque mate. ❌'
        if board.is_stalemate() or board.is_insufficient_material():
            return True, 'La posición terminó en tablas antes de cumplir el objetivo. ❌'
        current_counts = ObjectivePuzzleEngine.token_counts(board)
        for token in (puzzle.critical_pieces or []):
            if current_counts.get(token, 0) < initial_counts.get(token, 0):
                label = TOKEN_LABELS.get(token, token)
                return True, 'Perdiste la %s: fue capturada por el defensor. ❌' % label
        return False, ''
# --- Flujo principal -------------------------------------------------------

    @classmethod
    def apply_human_move(cls, puzzle, attempt, uci_move):
        """Jugada del estudiante de forma atómica e idempotente.

        La vista debe envolver la llamada en una transacción con
        select_for_update sobre `attempt` para proteger la concurrencia.
        """
        human = cls.human_color(puzzle)
        initial_counts = cls.token_counts(chess.Board(puzzle.initial_fen))

        movelog = list(attempt.movelog or [])
        board = cls.build_board(puzzle, movelog)

        if attempt.status != PuzzleAttempt.Status.IN_PROGRESS:
            return cls._finished_response(puzzle, attempt, board)

        # Idempotencia: el mismo movimiento ya fue aplicado (doble clic).
        if movelog and len(movelog) >= 2 and movelog[-2] == uci_move and board.turn != human:
            return cls._in_progress_response(puzzle, attempt, board, human,
                                             'Esa jugada ya fue aplicada.')

        if board.turn != human:
            return {'type': 'objective_move', 'success': False, 'message': 'No es tu turno.'}

        try:
            move = chess.Move.from_uci(uci_move)
        except ValueError:
            return {'type': 'objective_move', 'success': False, 'message': 'Formato de jugada UCI inválido.'}
        if move not in board.legal_moves:
            return {'type': 'objective_move', 'success': False, 'message': 'Jugada ilegal en esta posición.'}

        # --- Jugada humana válida ---
        human_san = board.san(move)
        board.push(move)  # ahora juega el defensor
        movelog.append(uci_move)
        attempt.human_moves_count += 1

        # Objetivo cumplido con la jugada humana (el defensor quedó en mate).
        if cls.objective_achieved(board, puzzle):
            attempt.movelog = movelog
            attempt.solved = True
            attempt.status = PuzzleAttempt.Status.COMPLETED
            attempt.end_message = '🏆 ¡Problema resuelto! Conseguiste dar jaque mate.'
            attempt.save(update_fields=['movelog', 'human_moves_count', 'solved', 'status', 'end_message'])
            return cls._finished_response(puzzle, attempt, board, human_san=human_san)

        # --- Respuesta del defensor (Stockfish) ---
        bot_san = None
        try:
            defender_uci = cls.select_defender_move(board, puzzle)
        except Exception:
            defender_uci = None
        if defender_uci:
            try:
                d_move = chess.Move.from_uci(defender_uci)
            except ValueError:
                d_move = None
            if d_move is not None and d_move in board.legal_moves:
                bot_san = board.san(d_move)
                board.push(d_move)
                movelog.append(defender_uci)
# --- Respuestas ------------------------------------------------------------

    @staticmethod
    def _base_response(puzzle, attempt, board, human_san=None, bot_san=None):
        return {
            'type': 'objective_move',
            'success': True,
            'fen': board.fen(),
            'move_san': human_san,
            'bot_move_san': bot_san,
            'human_moves': attempt.human_moves_count,
            'max_moves': puzzle.max_moves or 0,
            'attempt_id': str(attempt.id),
        }

    @classmethod
    def _finished_response(cls, puzzle, attempt, board, human_san=None, bot_san=None):
        resp = cls._base_response(puzzle, attempt, board, human_san, bot_san)
        resp['outcome'] = cls.OUTCOME_SUCCESS if attempt.status == PuzzleAttempt.Status.COMPLETED else cls.OUTCOME_FAILED
        resp['solved'] = attempt.solved
        resp['message'] = attempt.end_message or 'Problema finalizado.'
        return resp

    @classmethod
    def _in_progress_response(cls, puzzle, attempt, board, human, human_san=None, bot_san=None):
        resp = cls._base_response(puzzle, attempt, board, human_san, bot_san)
        resp['outcome'] = cls.OUTCOME_IN_PROGRESS
        resp['solved'] = False
        if human_san is None:
            resp['message'] = 'Sigue jugando.'
        else:
            resp['message'] = 'Jugada aplicada. El defensor ha respondido.'
        return resp

    # --- Guardado / análisis ----------------------------------------------------

    @staticmethod
    def pgn_for_attempt(puzzle, attempt):
        import chess.pgn
        board = chess.Board(puzzle.initial_fen)
        game = chess.pgn.Game()
        human = ObjectivePuzzleEngine.human_color(puzzle)
        student_name = puzzle.author.username if puzzle.author else 'Estudiante'
        game.headers['Event'] = 'Problema por objetivo: %s' % puzzle.title
        game.headers['Site'] = 'Plataforma Ajedrez Educativo'
        game.headers['White'] = student_name if human == chess.WHITE else 'Defensor (Stockfish)'
        game.headers['Black'] = 'Defensor (Stockfish)' if human == chess.WHITE else student_name
        if attempt.solved:
            game.headers['Result'] = '1-0' if human == chess.WHITE else '0-1'
        elif attempt.status == PuzzleAttempt.Status.IN_PROGRESS:
            game.headers['Result'] = '*'
        else:
            game.headers['Result'] = '0-1' if human == chess.WHITE else '1-0'
        node = game
        for uci in (attempt.movelog or []):
            try:
                m = chess.Move.from_uci(uci)
            except Exception:
                break
            if m not in board.legal_moves:
                break
            node = node.add_variation(m)
            board.push(m)
        exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
        return game.accept(exporter)

    @staticmethod
    def create_analysis_job(user, puzzle, attempt):
        """Crea el AnalysisJob de la partida OBJECTIVE para revisarla después."""
        from apps.analysis.models import AnalysisJob
        return AnalysisJob.objects.create(
            user=user,
            pgn_text=ObjectivePuzzleEngine.pgn_for_attempt(puzzle, attempt),
            target_depth=12,
        )


class _StrongDefenseProfile:
    """Perfil ligero de DEFENSA MÁXIMA para problemas por objetivo.

    Fuerza técnica alta, sin errores artificiales, profundidad/tiempo
    generosos. No depende de la base de datos (los problemas OBJECTIVE
    siempre usan esta defensa óptima).
    """
    skill_level = 20
    uci_elo = None
    multipv = 1
    engine_depth = 18
    move_time_ms = 1000
    error_probability = 0.0
