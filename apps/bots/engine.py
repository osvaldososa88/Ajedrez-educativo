"""Stockfish engine manager for training bots (synchronous subprocess).

Design goals:
  - One shared Stockfish process for ALL bot moves in the server process,
    guarded by a lock.
  - Real strength comes from engine parameters (Skill Level, depth, move
    time, UCI_Elo), not from ELO labels.
  - Weakness is pedagogical & controlled: candidate moves are categorized by
    centipawn loss (cp_loss) and selected probabilistically while respecting
    a strict max_cp_loss cap so advanced/intermediate bots never make absurd blunders.
  - Uses synchronous subprocess.Popen (no asyncio subprocess exec) which is
    reliable under Django on Windows.
  - If Stockfish is unavailable, an emergency material-preserving fallback
    keeps games playable.
"""

import logging
import os
import random
import threading
import subprocess

import chess

from apps.core.stockfish_engine import StockfishEngine

logger = logging.getLogger(__name__)


class _SyncEngine:
    """Stockfish engine managed via subprocess.Popen (no asyncio)."""

    def __init__(self, path):
        self.path = path
        self.proc = None
        self._lock = threading.Lock()
        self._config = {}

    def configure(self, config):
        self._config.update(config)

    def _ensure_started(self):
        if self.proc is not None and self.proc.poll() is None:
            return True
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                return True
            try:
                self.proc = subprocess.Popen(
                    [os.path.abspath(self.path)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                )
                self._uci_handshake()
                return True
            except BaseException:
                if self.proc is not None:
                    try:
                        self.proc.kill()
                    except BaseException:
                        pass
                self.proc = None
                raise

    def _uci_handshake(self):
        assert self.proc is not None
        self._send_line('uci')
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError('Stockfish cerró la conexión UCI')
            line = line.strip()
            if line == 'uciok':
                break
        for name, value in self._config.items():
            self._send_line('setoption name %s value %s' % (name, value))
        self._send_line('isready')
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError('Stockfish cerró la conexión durante isready')
            line = line.strip()
            if line == 'readyok':
                break

    def _send_line(self, line):
        if self.proc is None or self.proc.poll() is not None:
            raise RuntimeError('Stockfish no está corriendo')
        try:
            self.proc.stdin.write(line + '\n')
            self.proc.stdin.flush()
        except BaseException:
            raise RuntimeError('No se pudo escribir en stdin de Stockfish')

    def _read_until(self, sentinel, max_lines=300):
        if self.proc is None or self.proc.poll() is not None:
            raise RuntimeError('Stockfish no está corriendo')
        for _ in range(max_lines):
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError('Stockfish cerró la conexión UCI')
            line = line.strip()
            if line == sentinel:
                return

    def analyse(self, board, *, depth=None, time_s=None, multipv=None):
        if depth is None and time_s is None:
            depth = 15
        if multipv is None:
            multipv = 1
        self._ensure_started()
        self._send_line('setoption name MultiPV value %d' % multipv)
        self._send_line('position fen %s' % board.fen())
        self._send_line('isready')
        self._read_until('readyok')
        go_parts = []
        if depth is not None:
            go_parts.append('depth %d' % depth)
        if time_s is not None:
            go_parts.append('movetime %d' % int(time_s * 1000))
        self._send_line('go %s' % ' '.join(go_parts))
        bestmove = None
        pv_lines = []
        attempts = 0
        while attempts < 3 and bestmove is None:
            attempts += 1
            while True:
                line = self.proc.stdout.readline()
                if not line:
                    if attempts == 1:
                        self._recover_and_reissue(board, depth, time_s, multipv)
                        break
                    raise RuntimeError('Stockfish cerró la conexión durante go')
                line = line.strip()
                if line.startswith('info '):
                    pv_lines.append(line)
                if line.startswith('bestmove '):
                    parts = line.split()
                    if len(parts) >= 2:
                        bestmove = parts[1]
                    break
        if bestmove is None:
            raise RuntimeError('Stockfish no respondió con bestmove')
        return chess.Move.from_uci(bestmove), pv_lines

    def _recover_and_reissue(self, board, depth, time_s, multipv):
        try:
            if self.proc is not None:
                try:
                    self.proc.kill()
                except BaseException:
                    pass
        finally:
            self.proc = None
        self._ensure_started()
        self._send_line('setoption name MultiPV value %d' % (multipv or 1))
        self._send_line('position fen %s' % board.fen())
        for name, value in self._config.items():
            self._send_line('setoption name %s value %s' % (name, value))
        self._send_line('isready')
        self._read_until('readyok')
        go_parts = []
        if depth is not None:
            go_parts.append('depth %d' % depth)
        if time_s is not None:
            go_parts.append('movetime %d' % int(time_s * 1000))
        self._send_line('go %s' % ' '.join(go_parts))

    def quit(self):
        if self.proc is not None:
            try:
                try:
                    self.proc.stdin.write('quit\n')
                    self.proc.stdin.flush()
                except BaseException:
                    pass
                try:
                    if self.proc.poll() is None:
                        self.proc.kill()
                except BaseException:
                    pass
                try:
                    self.proc.wait(timeout=5)
                except BaseException:
                    try:
                        self.proc.kill()
                    except BaseException:
                        pass
                    try:
                        self.proc.wait(timeout=1)
                    except BaseException:
                        pass
            finally:
                self.proc = None

    def __del__(self):
        try:
            self.quit()
        except BaseException:
            pass


class BotEngineManager:
    _engine = None
    _lock = threading.Lock()

    @classmethod
    def _spawn(cls):
        path = StockfishEngine.get_stockfish_path()
        if not path:
            return None
        engine = _SyncEngine(path)
        engine.configure({'Threads': 1, 'Hash': 64, 'UCI_LimitStrength': False})
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
            except BaseException:
                pass
            cls._engine = None

    @classmethod
    def _reset(cls):
        cls._shutdown()

    @classmethod
    def is_available(cls) -> bool:
        return StockfishEngine.get_stockfish_path() is not None

    @classmethod
    def parse_multipv_candidates(cls, pv_lines):
        """
        Parses MultiPV lines from Stockfish into candidate dictionaries:
        [{'move': 'e2e4', 'multipv': 1, 'score_cp': 35}, ...]
        """
        candidates = {}
        for line in pv_lines:
            tokens = line.split()
            if 'multipv' not in tokens or 'pv' not in tokens:
                continue
            try:
                mpv_idx = tokens.index('multipv')
                mpv_val = int(tokens[mpv_idx + 1])
                pv_idx = tokens.index('pv')
                move_uci = tokens[pv_idx + 1]

                score_cp = 0
                if 'score' in tokens:
                    s_idx = tokens.index('score')
                    if s_idx + 2 < len(tokens):
                        stype = tokens[s_idx + 1]
                        sval = int(tokens[s_idx + 2])
                        if stype == 'cp':
                            score_cp = sval
                        elif stype == 'mate':
                            score_cp = 10000 if sval > 0 else -10000

                candidates[mpv_val] = {
                    'move': move_uci,
                    'multipv': mpv_val,
                    'score_cp': score_cp
                }
            except (ValueError, IndexError):
                continue

        sorted_candidates = [candidates[k] for k in sorted(candidates.keys())]
        return sorted_candidates

    @classmethod
    def select_controlled_move(cls, bestmove_uci, pv_lines, profile):
        """
        Controlled Error Selection Model:
        Categorizes MultiPV candidate moves by centipawn loss relative to the best move,
        respects profile.max_cp_loss, and selects candidate probabilistically based on ELO.
        """
        candidates = cls.parse_multipv_candidates(pv_lines)
        if not candidates:
            return bestmove_uci

        best_score = candidates[0]['score_cp']

        best_bucket = []
        alt_bucket = []
        minor_bucket = []
        blunder_bucket = []

        max_cp_loss = getattr(profile, 'max_cp_loss', 300)
        displayed_elo = getattr(profile, 'displayed_elo', None)

        if displayed_elo is not None:
            if displayed_elo < 400:
                best_p, alt_p, minor_p, blunder_p, max_cp_loss = 0.20, 0.30, 0.30, 0.20, 600
            elif displayed_elo < 700:
                best_p, alt_p, minor_p, blunder_p, max_cp_loss = 0.35, 0.35, 0.20, 0.10, 400
            elif displayed_elo < 1000:
                best_p, alt_p, minor_p, blunder_p, max_cp_loss = 0.50, 0.30, 0.15, 0.05, 300
            elif displayed_elo < 1300:
                best_p, alt_p, minor_p, blunder_p, max_cp_loss = 0.65, 0.25, 0.08, 0.02, 200
            elif displayed_elo < 1600:
                best_p, alt_p, minor_p, blunder_p, max_cp_loss = 0.80, 0.15, 0.04, 0.01, 150
            elif displayed_elo < 1900:
                best_p, alt_p, minor_p, blunder_p, max_cp_loss = 0.90, 0.08, 0.02, 0.00, 80
            elif displayed_elo < 2200:
                best_p, alt_p, minor_p, blunder_p, max_cp_loss = 0.97, 0.03, 0.00, 0.00, 40
            else:
                best_p, alt_p, minor_p, blunder_p, max_cp_loss = 1.00, 0.00, 0.00, 0.00, 0
        else:
            best_p = getattr(profile, 'best_move_prob', 0.75)
            alt_p = getattr(profile, 'alt_move_prob', 0.20)
            minor_p = getattr(profile, 'minor_error_prob', 0.04)
            blunder_p = getattr(profile, 'blunder_prob', 0.01)

        for cand in candidates:
            cp_loss = max(0, best_score - cand['score_cp'])
            cand['cp_loss'] = cp_loss

            if cp_loss == 0:
                best_bucket.append(cand)
            elif cp_loss <= 50:
                alt_bucket.append(cand)
            elif cp_loss <= 150:
                if cp_loss <= max_cp_loss:
                    minor_bucket.append(cand)
            else:
                if cp_loss <= max_cp_loss:
                    blunder_bucket.append(cand)

        r = random.random()
        target_bucket = None
        bucket_name = 'best'

        if r < best_p:
            target_bucket = best_bucket
            bucket_name = 'best'
        elif r < best_p + alt_p:
            target_bucket = alt_bucket or best_bucket
            bucket_name = 'alt' if alt_bucket else 'best_fallback'
        elif r < best_p + alt_p + minor_p:
            target_bucket = minor_bucket or alt_bucket or best_bucket
            bucket_name = 'minor' if minor_bucket else ('alt_fallback' if alt_bucket else 'best_fallback')
        else:
            target_bucket = blunder_bucket or minor_bucket or alt_bucket or best_bucket
            bucket_name = 'blunder' if blunder_bucket else ('minor_fallback' if minor_bucket else 'best_fallback')

        selected = random.choice(target_bucket) if target_bucket else candidates[0]

        logger.info(
            "Bot move chosen: profile=%s, displayed_elo=%s, best_move=%s, selected_move=%s, category=%s, cp_loss=%s, max_cp_loss=%s",
            getattr(profile, 'name', str(profile)), displayed_elo, bestmove_uci, selected['move'], bucket_name, selected.get('cp_loss', 0), max_cp_loss
        )

        return selected['move']

    @classmethod
    def select_move(cls, board, profile):
        with cls._lock:
            displayed_elo = getattr(profile, 'displayed_elo', None)
            skill_level = getattr(profile, 'skill_level', 5)
            engine_depth = getattr(profile, 'engine_depth', 6)

            if displayed_elo is not None:
                if displayed_elo < 400:
                    skill_level, engine_depth = 0, 1
                elif displayed_elo < 700:
                    skill_level, engine_depth = 2, 2
                elif displayed_elo < 1000:
                    skill_level, engine_depth = 5, 3
                elif displayed_elo < 1300:
                    skill_level, engine_depth = 8, 5
                elif displayed_elo < 1600:
                    skill_level, engine_depth = 12, 8
                elif displayed_elo < 1900:
                    skill_level, engine_depth = 16, 12
                elif displayed_elo < 2200:
                    skill_level, engine_depth = 20, 16
                else:
                    skill_level, engine_depth = 20, 20

            for attempt in range(1, 3):
                engine = cls._get_engine()
                if engine is None:
                    logger.warning('Bot engine: Stockfish binary not found; using emergency fallback.')
                    return cls._emergency_move(board)
                try:
                    engine.configure({'Skill Level': skill_level})
                    bestmove, pv_lines = engine.analyse(
                        board,
                        depth=engine_depth,
                        time_s=(profile.move_time_ms / 1000.0 if profile.move_time_ms else None),
                        multipv=max(3, profile.multipv or 3),
                    )
                    bestmove_uci = bestmove.uci() if hasattr(bestmove, 'uci') else str(bestmove)
                    return cls.select_controlled_move(bestmove_uci, pv_lines, profile)

                except Exception as exc:
                    logger.warning('Bot engine crashed (attempt %s): %s; reiniciando.', attempt, repr(exc)[:120])
                    cls._shutdown()
            logger.warning('Ambos intentos fallaron; usando fallback de emergencia.')
            return cls._emergency_move(board)

    @staticmethod
    def _emergency_move(board):
        legal = list(board.legal_moves)
        if not legal:
            return None
        captures_checks = [m for m in legal if board.is_capture(m) or board.gives_check(m)]
        pool = captures_checks or legal
        return random.choice(pool).uci()
