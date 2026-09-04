import pytest
import chess
from apps.core.chess_engine import ChessEngine

def test_initial_board():
    board = ChessEngine.create_initial_board()
    assert board.fen() == chess.STARTING_FEN
    state = ChessEngine.evaluate_board_state(board)
    assert state['turn'] == 'white'
    assert not state['is_check']
    assert not state['is_game_over']

def test_legal_moves_count():
    board = ChessEngine.create_initial_board()
    moves = ChessEngine.get_legal_moves(board)
    assert len(moves) == 20  # 16 pawn moves + 4 knight moves

def test_execute_legal_and_illegal_move():
    fen = chess.STARTING_FEN
    # Legal move 1. e4
    result = ChessEngine.execute_move(fen, 'e2e4')
    assert result['last_move_san'] == 'e4'
    assert result['turn'] == 'black'

    # Illegal move e2e4 on black's turn or invalid move
    with pytest.raises(ValueError):
        ChessEngine.execute_move(result['fen'], 'e2e4')

def test_scholars_checkmate():
    fen = chess.STARTING_FEN
    moves = ['e2e4', 'e7e5', 'f1c4', 'b8c6', 'd1h5', 'g8f6', 'h5f7']
    current_fen = fen
    res = None
    for m in moves:
        res = ChessEngine.execute_move(current_fen, m)
        current_fen = res['fen']

    assert res['is_game_over'] is True
    assert res['winner'] == 'white'
    assert res['finish_reason'] == 'CHECKMATE'

def test_stalemate():
    # Known stalemate position: White King c6, Queen c7, Black King a8
    stalemate_fen = 'k7/2Q5/2K5/8/8/8/8/8 b - - 0 1'
    board = ChessEngine.get_board_from_fen(stalemate_fen)
    res = ChessEngine.evaluate_board_state(board)
    assert res['is_game_over'] is True
    assert res['winner'] == 'draw'
    assert res['finish_reason'] == 'STALEMATE'

def test_castling():
    # Position where White can castle kingside (e1g1) and queenside (e1c1)
    castling_fen = 'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'
    moves = ChessEngine.get_legal_moves(castling_fen)
    ucis = [m['uci'] for m in moves]
    assert 'e1g1' in ucis # O-O
    assert 'e1c1' in ucis # O-O-O

    # Execute kingside castle
    res = ChessEngine.execute_move(castling_fen, 'e1g1')
    assert res['last_move_san'] == 'O-O'

def test_pawn_promotion():
    # White pawn on e7 about to promote
    promotion_fen = '8/4P3/8/8/8/8/8/4K2k w - - 0 1'
    # Promote to Queen
    res = ChessEngine.execute_move(promotion_fen, 'e7e8q')
    assert 'Q' in res['last_move_san'] or '=' in res['last_move_san']
    assert res['turn'] == 'black'

def test_en_passant():
    # Position where en passant is available
    ep_fen2 = 'rnbqkbnr/pp1ppppp/8/2pP4/8/8/PPP1PPPP/RNBQKBNR w KQkq c6 0 2'
    moves = ChessEngine.get_legal_moves(ep_fen2)
    ucis = [m['uci'] for m in moves]
    assert 'd5c6' in ucis

    res = ChessEngine.execute_move(ep_fen2, 'd5c6')
    assert 'x' in res['last_move_san']

def test_pgn_generation():
    pgn = ChessEngine.generate_pgn('Jugador1', 'Jugador2', ['e2e4', 'e7e5', 'g1f3'], '1/2-1/2')
    assert 'Jugador1' in pgn
    assert 'Jugador2' in pgn
    assert 'e4' in pgn
    assert 'e5' in pgn
    assert 'Nf3' in pgn
