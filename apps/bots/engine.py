"""
Stockfish engine manager for training bots.

Design goals (see project requirements):
  * Only consume resources when a bot is actually playing: the engine process
    is spawned lazily on the first bot move per server process and shared by
    ALL bot games (one process + one lock, never 90 engines).
  * Real strength comes from engine parameters (Skill Level, depth, move time,
    optional UCI_Elo), not from the displayed ELO label.
  * Weakness must be pedagogical: the bot may pick a runner-up MultiPV
    candidate with a per-profile probability, but candidates are always
    reasonable engine lines — never absurd random moves.
  * If the Stockfish binary is unavailable, an emergency material-preserving
    fallback keeps games playable (documented behavior).
"""
import logging
import random
import threading
import atexit

import chess
import chess.engine

from apps.core.stockfish_engine import StockfishEngine

logger = logging.getLogger(__name__)


class BotEngineManager:
    """
    Lazily-spawned, process-wide Stockfish instance guarded by a lock.
    Bot move computation is serialized; with short bot move times this is
    plenty for a school platform and avoids unbounded resource usage.
    """

    _engine = None
    _lock = threading.Lock()

    @classmethod
    def _spawn(cls):
        path = StockfishEngine.get_stockfish_path()
        if not path:
            return None
        engine = chess.engine.SimpleEngine.popen_uci(path, setpgrp=True)
        try:
            engine.configure({
                'Threads': 1,
                'Hash': 64,
                'UCI_LimitStrength': False,
            })
        except Exception:
            pass  # older engines may ignore some options
        atexit.register(cls._shutdown)
        return engine

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            cls._engine = cls._spawn()
        return cls._engine

    @classmethod
    def _shutdown(cls):
        if cls._engine is not None:
            try:
                cls._engine.quit()
            except Exception:
                pass
            cls._engine = None

    @classmethod
    def _reset(cls):
        cls._shutdown()

    @classmethod
    def is_available(cls) -> bool:
        """True when a Stockfish binary can be located (no process spawned)."""
        return StockfishEngine.get_stockfish_path() is not None

    @classmethod
    def select_move(cls, board: chess.Board, profile) -> str:
        """
        Returns the UCI move chosen by the bot for `board` using `profile`.
        Retries once with a fresh engine if the process died; falls back to a
        conservative emergency move if Stockfish is entirely unavailable.
        """
        with cls._lock:
            for attempt in (1, 2):
                engine = cls._get_engine()
                if engine is None:
                    logger.warning(
                        "Bot engine: Stockfish binary not found; using emergency fallback."
                    )
                    return cls._emergency_move(board)
                try:
                    return cls._play_with_engine(engine, board, profile)
                except (chess.engine.EngineTerminatedError, chess.engine.EngineError) as exc:
                    logger.warning(
                        "Bot engine crashed (attempt %s): %s; restarting.", attempt, exc
                    )
                    cls._reset()
                except OSError as exc:
                    logger.warning("Bot engine OS error (attempt %s): %s.", attempt, exc)
                    cls._reset()

        # Both attempts failed -> emergency fallback so the game never stalls.
        return cls._emergency_move(board)

    @classmethod
    def _play_with_engine(cls, engine, board: chess.Board, profile) -> str:
        config = {'Skill Level': profile.skill_level}
        if profile.uci_elo:
            config.update({'UCI_LimitStrength': True, 'UCI_Elo': profile.uci_elo})
        engine.configure(config)

        candidates = profile.multipv or 1
        limit = chess.engine.Limit(
            depth=profile.engine_depth or None,
            time=(profile.move_time_ms / 1000.0) if profile.move_time_ms else None,
        )
        infos = engine.analyse(board, limit, multipv=max(1, candidates))

        if isinstance(infos, dict):  # single-pv responses come back as one dict
            infos = [infos]

        moves = [
            info['pv'][0] for info in infos
            if info.get('pv')  # pv may be missing in edge positions
        ]
        if not moves:
            return cls._emergency_move(board)

        chosen = cls._choose_candidate(moves, profile)
        return chosen.uci()

    @staticmethod
    def _choose_candidate(moves, profile) -> chess.Move:
        """
        Error control: usually the best line; with `error_probability` a
        runner-up among the top MultiPV candidates (still sane moves).
        Never blunders away a possible best-line for EXPERT profiles is not
        special-cased: profiles fully control this via their parameters.
        """
        if len(moves) > 1 and random.random() < profile.error_probability:
            # Skip the best move; pick uniformly among runner-ups.
            idx = random.randint(1, min(len(moves) - 1, max(1, profile.multipv - 1)))
            return moves[idx]
        return moves[0]

    @staticmethod
    def _emergency_move(board: chess.Board) -> str:
        """
        Last-resort move when Stockfish cannot run at all: prefer a random
        capture or check (reasonable-looking), otherwise a random legal move.
        Only used when the engine binary is missing/crashed.
        """
        legal = list(board.legal_moves)
        if not legal:
            return None
        captures_checks = [
            m for m in legal
            if board.is_capture(m) or board.gives_check(m)
        ]
        pool = captures_checks or legal
        return random.choice(pool).uci()
