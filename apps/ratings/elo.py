"""
Pure ELO calculation logic.

This module intentionally has no Django imports so it can be unit-tested in
isolation and safely imported from any app (accounts, games, templates, ...).

Standard ELO with expectation-based updates:

    E_a = 1 / (1 + 10 ** ((R_b - R_a) / 400))      # expected score of player A
    S_a = 1 (win) | 0.5 (draw) | 0 (loss)          # actual score
    R_a' = R_a + K * (S_a - E_a)

The same is applied to both players (their expected scores are complementary),
so for two players with the same K factor the rating points exchanged sum to 0
(before per-player integer rounding).
"""
import math
from enum import Enum

# --- System constants -------------------------------------------------------

INITIAL_RATING = 1200   # every new user starts here
MIN_RATING = 100        # rating floor: never store anything below this
# No artificial maximum.

K_FACTOR_NEW = 40       # first competitive games -> converge quickly to real level
K_FACTOR_NORMAL = 20    # afterwards
NEW_PLAYER_GAMES = 20   # number of rated games that define a "new" player

# --- Core formula -----------------------------------------------------------


def expected_score(rating_a: float, rating_b: float) -> float:
    """Expected score (0..1) of player A against player B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def score_for_result(win: bool, draw: bool) -> float:
    """Actual score: win=1, draw=0.5, loss=0."""
    if win:
        return 1.0
    if draw:
        return 0.5
    return 0.0


def k_factor(rated_games_played: int) -> int:
    """
    Adaptive K factor based on how many RATED (competitive) games the player
    has already completed. Training/unrated games must never be counted here.
    """
    return K_FACTOR_NEW if rated_games_played < NEW_PLAYER_GAMES else K_FACTOR_NORMAL


def _round_half_up(value: float) -> int:
    """
    Classic ELO rounding: floor(value + 0.5).
    For complementary expected scores (E_a + E_b = 1) with the same K, this keeps
    the exchanged points perfectly antisymmetric (winner delta == -loser delta).
    """
    return math.floor(value + 0.5)


def compute_rating_change(rating: float, expected: float, score: float, k: int) -> int:
    """Signed integer rating delta for one player: K * (S - E), rounded half-up."""
    return _round_half_up(k * (score - expected))


def apply_rating_change(rating: int, change: int) -> int:
    """Apply a delta enforcing the rating floor (MIN_RATING). No maximum."""
    return max(MIN_RATING, rating + change)


def compute_new_rating(rating: int, opponent_rating: int, score: float, k: int) -> int:
    """One-shot helper: expected score -> delta -> floor. Used by tests/tools."""
    expected = expected_score(rating, opponent_rating)
    change = compute_rating_change(rating, expected, score, k)
    return apply_rating_change(rating, change)


# --- Player ranks (friendly representation of the ELO) ----------------------
# Ranks are ALWAYS derived from the current ELO, never stored as a second
# source of truth. If the ELO crosses a boundary, the rank changes instantly.

class PlayerRank(Enum):
    """Friendly rank tiers for students. Values: (label, min_elo, max_elo)."""

    NOVATO = ('Novato', 100, 799)
    APRENDIZ = ('Aprendiz', 800, 999)
    PRINCIPIANTE = ('Principiante', 1000, 1199)
    INTERMEDIO = ('Intermedio', 1200, 1399)
    AVANZADO = ('Avanzado', 1400, 1599)
    EXPERTO = ('Experto', 1600, 1799)
    MAESTRO = ('Maestro', 1800, None)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def min_elo(self) -> int:
        return self.value[1]

    @property
    def max_elo(self):
        return self.value[2]


_RANKS_DESC = list(PlayerRank)  # lowest -> highest


def rank_for_elo(elo: int) -> PlayerRank:
    """Map an ELO value to its PlayerRank. Values below the floor fall into NOVATO."""
    for rank in reversed(_RANKS_DESC):
        if elo >= rank.min_elo:
            return rank
    return PlayerRank.NOVATO


def next_rank_info(elo: int):
    """
    Returns (next_rank, points_to_reach_it) or (None, None) when the player is
    already at the top rank. Useful for positive-progress UI ("te faltan X").
    """
    current = rank_for_elo(elo)
    remaining = _RANKS_DESC[_RANKS_DESC.index(current) + 1:]
    if not remaining:
        return None, None
    nxt = remaining[0]
    return nxt, nxt.min_elo - elo
