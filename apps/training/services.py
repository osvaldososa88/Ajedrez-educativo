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

        # Update adaptive stats
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

        return attempt
