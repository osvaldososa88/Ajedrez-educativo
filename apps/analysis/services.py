import io
import sys
import threading
import chess
import chess.pgn
from django.utils import timezone
from django.db import connections
from apps.core.stockfish_engine import StockfishEngine
from .models import AnalysisJob, PositionAnalysis, MoveAnalysis
from .review_engine import ReviewEngine

def start_async_analysis_job(job_id: str):
    """
    Launches non-blocking background thread worker to execute full game analysis.
    In pytest test runner, runs synchronously to prevent SQLite database locks.
    """
    if 'pytest' in sys.modules or 'test' in sys.argv:
        _run_analysis_job(job_id)
    else:
        thread = threading.Thread(target=_run_analysis_job, args=(job_id,), daemon=True)
        thread.start()

def _run_analysis_job(job_id: str):
    connections.close_all()
    try:
        job = AnalysisJob.objects.get(id=job_id)
    except AnalysisJob.DoesNotExist:
        return

    job.status = AnalysisJob.Status.PROCESSING
    job.progress_percent = 5
    job.save()

    try:
        pgn_source = job.pgn_text
        if not pgn_source and job.game:
            pgn_source = job.game.generate_pgn()

        if not pgn_source:
            job.status = AnalysisJob.Status.FAILED
            job.error_message = "No se proporcionó PGN válido para analizar."
            job.save()
            return

        game = chess.pgn.read_game(io.StringIO(pgn_source))
        if not game or not game.variations:
            job.status = AnalysisJob.Status.FAILED
            job.error_message = "Formato PGN inválido o sin movimientos."
            job.save()
            return

        # Collect moves and count total
        node = game
        moves_list = []
        while node.variations:
            next_node = node.variation(0)
            moves_list.append((next_node.move, next_node.san()))
            node = next_node

        total_moves = len(moves_list)
        if total_moves == 0:
            job.status = AnalysisJob.Status.FAILED
            job.error_message = "La partida PGN no contiene movimientos."
            job.save()
            return

        board = game.board()
        prev_score = 0
        move_summary_list = []

        for idx, (move, move_san) in enumerate(moves_list, start=1):
            fen_before = board.fen()
            move_uci = move.uci()

            # Position before eval
            eval_before = StockfishEngine.evaluate_position(fen_before, depth=job.target_depth)

            board.push(move)
            fen_after = board.fen()

            # Check cached position analysis or run Stockfish for fen_after
            pos_analysis, created = PositionAnalysis.objects.get_or_create(
                fen=fen_after,
                defaults={
                    'score_cp': None,
                    'mate_in': None,
                    'best_move_uci': None,
                    'best_move_san': None,
                    'pv_san': [],
                    'depth': job.target_depth,
                    'engine_name': 'Stockfish'
                }
            )

            if created or (pos_analysis.score_cp is None and pos_analysis.mate_in is None):
                eval_after = StockfishEngine.evaluate_position(fen_after, depth=job.target_depth)
                pos_analysis.score_cp = eval_after['score_cp']
                pos_analysis.mate_in = eval_after['mate_in']
                pos_analysis.best_move_uci = eval_after['best_move_uci']
                pos_analysis.best_move_san = eval_after['best_move_san']
                pos_analysis.pv_san = eval_after['pv_san']
                pos_analysis.engine_name = eval_after['engine_name']
                pos_analysis.save()
            else:
                eval_after = {
                    'score_cp': pos_analysis.score_cp,
                    'mate_in': pos_analysis.mate_in,
                    'best_move_uci': pos_analysis.best_move_uci,
                    'best_move_san': pos_analysis.best_move_san,
                    'pv_san': pos_analysis.pv_san
                }

            current_score = pos_analysis.score_cp if pos_analysis.score_cp is not None else 0
            cp_loss = max(0, prev_score - current_score) if (idx % 2 != 0) else max(0, current_score - prev_score)

            # Pedagogical review analysis
            review_data = ReviewEngine.analyze_move_pedagogically(
                fen_before=fen_before,
                move_uci=move_uci,
                move_san=move_san,
                fen_after=fen_after,
                eval_before=eval_before,
                eval_after=eval_after,
                cp_loss=cp_loss
            )

            quality = review_data['classification']

            MoveAnalysis.objects.create(
                job=job,
                ply=idx,
                move_san=move_san,
                move_uci=move_uci,
                fen_before=fen_before,
                fen_after=fen_after,
                position_analysis=pos_analysis,
                score_cp=pos_analysis.score_cp,
                mate_in=pos_analysis.mate_in,
                quality=quality,
                review_data=review_data
            )

            move_summary_list.append({
                'ply': idx,
                'quality': quality,
                'cp_loss': cp_loss
            })

            prev_score = current_score

            # Update progress percent
            progress = int((idx / total_moves) * 90) + 5
            job.progress_percent = progress
            job.save()

        # Calculate overall game review summary metrics
        summary_metrics = ReviewEngine.compute_game_summary_metrics(move_summary_list)
        job.accuracy_white = summary_metrics['accuracy_white']
        job.accuracy_black = summary_metrics['accuracy_black']
        job.estimated_elo_white = summary_metrics['estimated_elo_white']
        job.estimated_elo_black = summary_metrics['estimated_elo_black']
        job.summary_stats = summary_metrics

        job.status = AnalysisJob.Status.COMPLETED
        job.progress_percent = 100
        job.completed_at = timezone.now()
        job.save()

    except Exception as e:
        job.status = AnalysisJob.Status.FAILED
        job.error_message = str(e)
        job.save()

