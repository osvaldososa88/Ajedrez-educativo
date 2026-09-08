import io

p = r'f:\Ema\vibe coding\Juegos\Ajedrez educativo\apps\analysis\review_engine.py'
content = io.open(p, encoding='utf-8').read()

# Fix 1: Update classify_move signature and logic
start_marker = "    @classmethod\n    def classify_move("
end_marker = "        return 'BLUNDER', 'GRAN ERROR'"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)
if start_idx >= 0 and end_idx >= 0:
    end_idx += len(end_marker)
    
    new_method = '''    @classmethod
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
        if (player_mate_before is not None and player_mate_before > 0 and player_mate_after is None) or \\
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
        return 'BLUNDER', 'GRAN ERROR' '''

    content = content[:start_idx] + new_method + content[end_idx:]
    print('OK - classify_move updated')
else:
    print('NOT FOUND classify_move')
    print('start:', start_idx, 'end:', end_idx)

# Fix 2: Update analyze_move_pedagogically to pass is_white_move
old_call = "cp_loss=cp_loss\n            )"
new_call = "cp_loss=cp_loss,\n                is_white_move=is_white_move\n            )"

if old_call in content:
    content = content.replace(old_call, new_call, 1)
    print('OK - analyze_move_pedagogically call updated')
else:
    print('NOT FOUND analyze_move call')

io.open(p, 'w', encoding='utf-8').write(content)
print('Done')
