import math
import chess
from typing import Dict, Any, List, Optional, Tuple

PIECE_NAMES_ES = {
    chess.PAWN: 'peón',
    chess.KNIGHT: 'caballo',
    chess.BISHOP: 'alfil',
    chess.ROOK: 'torre',
    chess.QUEEN: 'dama',
    chess.KING: 'rey'
}

PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0
}

# Recognized common opening moves (SAN) in standard positions
COMMON_OPENING_MOVES = {
    'e4', 'd4', 'Nf3', 'c4', 'e5', 'c5', 'e6', 'c6', 'd5', 'Nf6', 'Nc3', 'Nc6',
    'g3', 'b3', 'f4', 'd3', 'g6', 'b6', 'Bg5', 'Bb5', 'Bc4', 'Nbd2', 'O-O'
}

class ReviewEngine:
    """
    Pedagogical Explanation & Review Engine for chess games.
    Analyzes position before/after a move, stockfish evaluation, piece material,
    tactical motifs, and king safety to generate structured explanations in Spanish.
    """

    @classmethod
    def classify_move(
        cls,
        board_before: chess.Board,
        move: chess.Move,
        board_after: chess.Board,
        eval_before: Dict[str, Any],
        eval_after: Dict[str, Any],
        cp_loss: int,
        is_white_move: bool = True
    ) -> Tuple[str, str]:
        """
        Classifies move quality according to Spanish standards:
        BOOK (LIBRO), BRILLIANT (BRILLANTE), BEST (MEJOR), EXCELLENT (EXCELENTE),
        GOOD (BUENA), INACCURACY (INEXACTITUD), MISTAKE (ERROR),
        BLUNDER (GRAN ERROR), MISS (OPORTUNIDAD PERDIDA).

        All Stockfish scores are from White's perspective. is_white_move
        determines whose perspective we use for threshold comparisons.
        """
        best_uci = eval_before.get('best_move_uci')
        score_before = eval_before.get('score_cp') or 0
        score_after = eval_after.get('score_cp') or 0
        mate_before = eval_before.get('mate_in')
        mate_after = eval_after.get('mate_in')
        fullmove = board_before.fullmove_number

        # Convert to player's perspective for threshold comparisons
        # For White: positive = good. For Black: negative = good (invert).
        if is_white_move:
            player_score_before = score_before
            player_score_after = score_after
            player_mate_before = mate_before
            player_mate_after = mate_after
        else:
            player_score_before = -score_before
            player_score_after = -score_after
            player_mate_before = -mate_before if mate_before is not None else None
            player_mate_after = -mate_after if mate_after is not None else None

        # 1. BOOK: Opening move theory
        if fullmove <= 5 and board_before.san(move) in COMMON_OPENING_MOVES and cp_loss <= 25:
            return 'BOOK', 'LIBRO'

        # 2. MISS: Missed forced mate or huge winning opportunity
        if (player_mate_before is not None and player_mate_before > 0 and player_mate_after is None) or \
           (player_score_before >= 300 and cp_loss >= 180):
            return 'MISS', 'OPORTUNIDAD PERDIDA'

        # 3. BLUNDER: Lost winning position or fell into losing one
        if player_mate_before is not None and player_mate_before > 0 and player_mate_after is not None and player_mate_after < 0:
            return 'BLUNDER', 'GRAN ERROR'
        if player_score_before >= 200 and player_score_after <= -200:
            return 'BLUNDER', 'GRAN ERROR'

        # 4. BRILLIANT: Sacrifice or exceptional tactic with strong evaluation retained
        moving_piece = board_before.piece_at(move.from_square)
        captured_piece = board_before.piece_at(move.to_square)
        if moving_piece and captured_piece:
            mat_diff = PIECE_VALUES.get(moving_piece.piece_type, 0) - PIECE_VALUES.get(captured_piece.piece_type, 0)
        elif moving_piece:
            mat_diff = PIECE_VALUES.get(moving_piece.piece_type, 0)
        else:
            mat_diff = 0

        # Check if piece is sacrificed into capture square, but eval remains winning/equal
        is_sacrificed = mat_diff >= 3 and board_after.is_attacked_by(not board_before.turn, move.to_square)
        if is_sacrificed and cp_loss <= 20 and player_score_after >= -50:
            return 'BRILLIANT', 'BRILLANTE'

        # 5. BEST: Matches Stockfish top choice or cp_loss < 10
        if (best_uci and move.uci() == best_uci) or cp_loss < 10:
            return 'BEST', 'MEJOR'

        # 6. EXCELLENT: 10 <= cp_loss <= 30
        if cp_loss <= 30:
            return 'EXCELLENT', 'EXCELENTE'

        # 7. GOOD: 30 < cp_loss <= 75
        if cp_loss <= 75:
            return 'GOOD', 'BUENA'

        # 8. INACCURACY: 75 < cp_loss <= 150
        if cp_loss <= 150:
            return 'INACCURACY', 'INEXACTITUD'

        # 9. MISTAKE: 150 < cp_loss <= 300
        if cp_loss <= 300:
            return 'MISTAKE', 'ERROR'

        # 10. BLUNDER: cp_loss > 300
        return 'BLUNDER', 'GRAN ERROR' 
        if player_score_before >= 200 and player_score_after <= -200:
            return 'BLUNDER', 'GRAN ERROR'

        # 4. BRILLIANT: Sacrifice or exceptional tactic with strong evaluation retained
        moving_piece = board_before.piece_at(move.from_square)
        captured_piece = board_before.piece_at(move.to_square)
        if moving_piece and captured_piece:
            mat_diff = PIECE_VALUES.get(moving_piece.piece_type, 0) - PIECE_VALUES.get(captured_piece.piece_type, 0)
        elif moving_piece:
            mat_diff = PIECE_VALUES.get(moving_piece.piece_type, 0)
        else:
            mat_diff = 0

        # Check if piece is sacrificed into capture square, but eval remains winning/equal
        is_sacrificed = mat_diff >= 3 and board_after.is_attacked_by(not board_before.turn, move.to_square)
        if is_sacrificed and cp_loss <= 20 and player_score_after >= -50:
            return 'BRILLIANT', 'BRILLANTE'

        # 5. BEST: Matches Stockfish top choice or cp_loss < 10
        if (best_uci and move.uci() == best_uci) or cp_loss < 10:
            return 'BEST', 'MEJOR'

        # 6. EXCELLENT: 10 <= cp_loss <= 30
        if cp_loss <= 30:
            return 'EXCELLENT', 'EXCELENTE'

        # 7. GOOD: 30 < cp_loss <= 75
        if cp_loss <= 75:
            return 'GOOD', 'BUENA'

        # 8. INACCURACY: 75 < cp_loss <= 150
        if cp_loss <= 150:
            return 'INACCURACY', 'INEXACTITUD'

        # 9. MISTAKE: 150 < cp_loss <= 300
        if cp_loss <= 300:
            return 'MISTAKE', 'ERROR'

        # 10. BLUNDER: cp_loss > 300
        return 'BLUNDER', 'GRAN ERROR'

    @classmethod
    def analyze_move_pedagogically(
        cls,
        fen_before: str,
        move_uci: str,
        move_san: str,
        fen_after: str,
        eval_before: Dict[str, Any],
        eval_after: Dict[str, Any],
        cp_loss: int,
        is_white_move: bool = True
    ) -> Dict[str, Any]:
        """
        Executes comprehensive pedagogical analysis on a move.
        Returns detailed ReviewMove structure.
        """
        board_before = chess.Board(fen_before)
        move = chess.Move.from_uci(move_uci)
        board_after = chess.Board(fen_after)
        moving_color = board_before.turn

        quality_code, quality_label_es = cls.classify_move(
            board_before, move, board_after, eval_before, eval_after, cp_loss,
            is_white_move=is_white_move
        )

        moving_piece = board_before.piece_at(move.from_square)
        piece_type = moving_piece.piece_type if moving_piece else chess.PAWN
        piece_name = PIECE_NAMES_ES.get(piece_type, 'pieza')

        # Detectors
        opening_info = cls._detect_opening_concepts(board_before, move, board_after)
        material_info = cls._detect_material_concepts(board_before, move, board_after)
        tactical_info = cls._detect_tactical_concepts(board_before, move, board_after)
        king_info = cls._detect_king_concepts(board_before, move, board_after)

        # Primary theme & description selection
        tactical_theme = "Posicional"
        explanation_type = "GENERAL"
        explanation_text = f"Movimiento con {piece_name} a {chess.square_name(move.to_square)}."
        coach_emotion = "NEUTRAL"
        arrows = []
        highlighted_squares = []
        hints = []

        # Best move arrow (green)
        best_uci = eval_before.get('best_move_uci')
        if best_uci:
            try:
                bm = chess.Move.from_uci(best_uci)
                arrows.append({
                    "from": chess.square_name(bm.from_square),
                    "to": chess.square_name(bm.to_square),
                    "color": "green",
                    "label": "Mejor jugada"
                })
            except ValueError:
                pass

        # Played move arrow (blue if good/best, orange/red if bad)
        played_arrow_color = "blue" if quality_code in ['BOOK', 'BRILLIANT', 'BEST', 'EXCELLENT'] else ("orange" if quality_code in ['GOOD', 'INACCURACY'] else "red")
        arrows.append({
            "from": chess.square_name(move.from_square),
            "to": chess.square_name(move.to_square),
            "color": played_arrow_color,
            "label": "Jugada realizada"
        })

        # Process detected motifs
        if quality_code == 'BRILLIANT':
            tactical_theme = "Sacrificio Brillante"
            explanation_type = "BRILLIANT"
            explanation_text = f"¡Excelente sacrificio! Entregas material táctico para lograr un ataque decisivo."
            coach_emotion = "EXCITED"
        elif tactical_info.get('has_fork'):
            tactical_theme = "Tenedor"
            explanation_type = "FORK"
            explanation_text = f"♞ ¡Tenedor! Tu {piece_name} en {chess.square_name(move.to_square)} ataca dos piezas enemigas al mismo tiempo."
            coach_emotion = "HAPPY"
            for sq in tactical_info.get('fork_targets', []):
                highlighted_squares.append({"square": chess.square_name(sq), "color": "yellow"})
        elif tactical_info.get('has_pin'):
            tactical_theme = "Clavada"
            explanation_type = "PIN"
            explanation_text = f"🎯 ¡Clavada! Restringes el movimiento de la pieza enemiga en {chess.square_name(move.to_square)}."
            coach_emotion = "HAPPY"
        elif tactical_info.get('has_discovered_check'):
            tactical_theme = "Jaque Descubierto"
            explanation_type = "DISCOVERED_CHECK"
            explanation_text = f"⚡ ¡Jaque descubierto! Al mover tu {piece_name}, abres la línea de ataque directamente contra el rey rival."
            coach_emotion = "HAPPY"
        elif king_info.get('is_checkmate'):
            tactical_theme = "Jaque Mate"
            explanation_type = "CHECKMATE"
            explanation_text = f"🏆 ¡Jaque mate! La partida finaliza con la victoria."
            coach_emotion = "HAPPY"
        elif king_info.get('is_check'):
            tactical_theme = "Jaque"
            explanation_type = "CHECK"
            explanation_text = f"⚠️ Colocas al rey enemigo en jaque con tu {piece_name}."
            coach_emotion = "HAPPY"
        elif material_info.get('hanging_piece_lost'):
            tactical_theme = "Pieza Indefensa"
            explanation_type = "HANGING_PIECE"
            explanation_text = f"⚠️ Cuidado: Tu {piece_name} ha quedado indefensa o expuesta a ser capturada sin suficiente compensación."
            coach_emotion = "WARNING"
            highlighted_squares.append({"square": chess.square_name(move.to_square), "color": "red"})
            hints.append(f"Observa si la casilla {chess.square_name(move.to_square)} cuenta con la defensa de otra pieza.")
        elif material_info.get('captured_piece'):
            cap_name = PIECE_NAMES_ES.get(material_info['captured_piece'].piece_type, 'pieza')
            tactical_theme = "Ganancia de Material" if quality_code in ['BEST', 'EXCELLENT', 'GOOD'] else "Captura"
            explanation_text = f"⚔️ Capturas la {cap_name} enemiga en {chess.square_name(move.to_square)}."
            coach_emotion = "HAPPY" if quality_code in ['BEST', 'EXCELLENT', 'GOOD'] else "NEUTRAL"
        elif opening_info.get('is_opening'):
            tactical_theme = "Apertura & Desarrollo"
            explanation_text = opening_info.get('description', f"Desarrollas el {piece_name} hacia la casilla {chess.square_name(move.to_square)}.")
            coach_emotion = "NEUTRAL"

        if quality_code in ['MISTAKE', 'BLUNDER', 'MISS']:
            if not hints:
                best_san = eval_before.get('best_move_san', '')
                hints.append(f"Considera si tenías una mejor opción como {best_san if best_san else 'mover otra pieza'}.")
            coach_emotion = "WARNING" if quality_code == 'MISTAKE' else "SURPRISED"

        coach_message = cls._generate_coach_message(quality_code, piece_name, chess.square_name(move.to_square))

        return {
            'classification': quality_code,
            'classification_display': quality_label_es,
            'explanation_type': explanation_type,
            'explanation_text': explanation_text,
            'tactical_theme': tactical_theme,
            'score_before': eval_before.get('score_cp'),
            'score_after': eval_after.get('score_cp'),
            'mate_before': eval_before.get('mate_in'),
            'mate_after': eval_after.get('mate_in'),
            'best_move_san': eval_before.get('best_move_san'),
            'best_move_uci': eval_before.get('best_move_uci'),
            'hints': hints,
            'arrows': arrows,
            'highlighted_squares': highlighted_squares,
            'coach_emotion': coach_emotion,
            'coach_message': coach_message
        }

    @classmethod
    def _detect_opening_concepts(cls, board_before: chess.Board, move: chess.Move, board_after: chess.Board) -> Dict[str, Any]:
        if board_before.fullmove_number > 10:
            return {'is_opening': False}

        to_sq = chess.square_name(move.to_square)
        piece = board_before.piece_at(move.from_square)

        if to_sq in ['e4', 'd4', 'e5', 'd5']:
            return {
                'is_opening': True,
                'description': f"📚 Ocupas y controlas casillas del centro estratégico con {to_sq}."
            }
        if piece and piece.piece_type in [chess.KNIGHT, chess.BISHOP]:
            return {
                'is_opening': True,
                'description': f"📖 Desarrollas el {PIECE_NAMES_ES[piece.piece_type]} hacia una casilla activa."
            }
        if board_after.is_castling(move):
            return {
                'is_opening': True,
                'description': "🏰 Enroque completado: pones a resguardo a tu rey y conectas las torres."
            }
        return {'is_opening': True}

    @classmethod
    def _detect_material_concepts(cls, board_before: chess.Board, move: chess.Move, board_after: chess.Board) -> Dict[str, Any]:
        captured = board_before.piece_at(move.to_square)
        is_attacked_after = board_after.is_attacked_by(not board_before.turn, move.to_square)
        is_defended_after = board_after.is_attacked_by(board_before.turn, move.to_square)

        return {
            'captured_piece': captured,
            'hanging_piece_lost': is_attacked_after and not is_defended_after and not captured
        }

    @classmethod
    def _detect_tactical_concepts(cls, board_before: chess.Board, move: chess.Move, board_after: chess.Board) -> Dict[str, Any]:
        targets = []
        color = board_before.turn
        piece = board_before.piece_at(move.from_square)

        # Fork detection: Attacks 2 or more valuable enemy pieces simultaneously
        if piece:
            attacked_squares = board_after.attacks(move.to_square)
            for sq in attacked_squares:
                target_piece = board_after.piece_at(sq)
                if target_piece and target_piece.color != color and target_piece.piece_type in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]:
                    targets.append(sq)

        has_fork = len(targets) >= 2
        has_pin = board_after.is_pinned(not color, move.to_square) if board_after.piece_at(move.to_square) else False
        has_discovered_check = board_after.is_check() and not board_after.is_attacked_by(color, board_after.king(not color))

        return {
            'has_fork': has_fork,
            'fork_targets': targets,
            'has_pin': has_pin,
            'has_discovered_check': has_discovered_check
        }

    @classmethod
    def _detect_king_concepts(cls, board_before: chess.Board, move: chess.Move, board_after: chess.Board) -> Dict[str, Any]:
        return {
            'is_check': board_after.is_check(),
            'is_checkmate': board_after.is_checkmate()
        }

    @classmethod
    def _generate_coach_message(cls, quality_code: str, piece_name: str, target_sq: str) -> str:
        if quality_code == 'BRILLIANT':
            return "¡Una jugada genial e inspiradora!"
        if quality_code == 'BOOK':
            return "Conocimiento teórico sólido de la apertura."
        if quality_code == 'BEST':
            return f"¡Excelente decisión con el {piece_name}!"
        if quality_code == 'EXCELLENT':
            return f"Muy buena jugada táctica a {target_sq}."
        if quality_code == 'GOOD':
            return "Buena jugada para mantener la posición."
        if quality_code == 'INACCURACY':
            return "Había una alternativa un poco más fuerte."
        if quality_code == 'MISTAKE':
            return "Ten cuidado, esta jugada concede una ventaja al rival."
        if quality_code == 'BLUNDER':
            return "¡Atención! Un error grave que pierde material o posición."
        if quality_code == 'MISS':
            return "Se dejó pasar una oportunidad táctica importante."
        return "Continúa analizando la posición."

    @classmethod
    def compute_game_summary_metrics(cls, move_analyses_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculates White & Black global accuracy %, estimated Elo, and move counts.
        """
        counts_white = {q: 0 for q in ['BOOK', 'BRILLIANT', 'BEST', 'EXCELLENT', 'GOOD', 'INACCURACY', 'MISTAKE', 'BLUNDER', 'MISS']}
        counts_black = {q: 0 for q in ['BOOK', 'BRILLIANT', 'BEST', 'EXCELLENT', 'GOOD', 'INACCURACY', 'MISTAKE', 'BLUNDER', 'MISS']}

        cp_losses_white = []
        cp_losses_black = []

        for idx, ma in enumerate(move_analyses_data, start=1):
            is_white = (idx % 2 != 0)
            quality = ma.get('quality', 'GOOD')
            cp_loss = ma.get('cp_loss', 0)

            target_counts = counts_white if is_white else counts_black
            target_cp = cp_losses_white if is_white else cp_losses_black

            if quality in target_counts:
                target_counts[quality] += 1
            target_cp.append(cp_loss)

        avg_loss_w = (sum(cp_losses_white) / len(cp_losses_white)) if cp_losses_white else 15
        avg_loss_b = (sum(cp_losses_black) / len(cp_losses_black)) if cp_losses_black else 15

        accuracy_w = round(max(5.0, min(100.0, 100.0 * math.exp(-0.0035 * avg_loss_w))), 1)
        accuracy_b = round(max(5.0, min(100.0, 100.0 * math.exp(-0.0035 * avg_loss_b))), 1)

        elo_w = int(round(500 + (accuracy_w / 100.0) * 1700))
        elo_b = int(round(500 + (accuracy_b / 100.0) * 1700))

        return {
            'accuracy_white': accuracy_w,
            'accuracy_black': accuracy_b,
            'estimated_elo_white': elo_w,
            'estimated_elo_black': elo_b,
            'counts_white': counts_white,
            'counts_black': counts_black
        }
