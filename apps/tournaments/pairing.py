"""
Pairing algorithms for tournament formats.

Each service exposes a common interface so `TournamentService` can resolve the
correct algorithm via `get_pairing_service(tournament)` without knowing the
concrete format. To add a new format: implement a class with the same two
methods and register it in `PAIRING_SERVICES`.
"""
from apps.tournaments.models import Tournament


class BasePairingService:
    """
    supports_all_rounds_upfront: True for formats where the full schedule can be
    computed before any game is played (e.g. Round Robin). False for formats where
    each round depends on previous results (e.g. Swiss).
    """
    supports_all_rounds_upfront = False

    @staticmethod
    def generate_schedule(participants):
        """
        Returns a list of rounds; each round is a list of (white, black_or_None)
        tuples of TournamentParticipant. Only implemented for formats where the
        whole schedule is known in advance.
        """
        raise NotImplementedError

    @staticmethod
    def generate_next_round_pairings(tournament, participants, standings, past_pairings):
        """
        Returns a single round's pairings: a list of (white, black_or_None) tuples.
        `standings` is a dict {participant_id: {'points': float, ...}}.
        `past_pairings` is a list of Pairing instances already played in the tournament.
        """
        raise NotImplementedError


class RoundRobinPairingService(BasePairingService):
    """
    Classic circle method. The whole schedule is deterministic and known before
    a single game is played, so all rounds/pairings are generated up front.
    """
    supports_all_rounds_upfront = True

    @staticmethod
    def generate_schedule(participants):
        players = sorted(participants, key=lambda p: (-p.seed_rating, p.user.username))
        if len(players) < 2:
            return []

        if len(players) % 2 == 1:
            players = players + [None]  # bye slot

        n = len(players)
        rounds_count = n - 1

        fixed = players[0]
        rotating = players[1:]

        schedule = []
        for round_idx in range(rounds_count):
            order = [fixed] + rotating
            round_pairings = []
            for i in range(n // 2):
                a = order[i]
                b = order[n - 1 - i]
                if a is None or b is None:
                    bye_player = a or b
                    round_pairings.append((bye_player, None))
                    continue
                # Alternate who gets white to roughly balance colors across rounds.
                if round_idx % 2 == 0:
                    round_pairings.append((a, b))
                else:
                    round_pairings.append((b, a))
            schedule.append(round_pairings)
            rotating = [rotating[-1]] + rotating[:-1]

        return schedule

    @staticmethod
    def generate_next_round_pairings(tournament, participants, standings, past_pairings):
        raise NotImplementedError("Round Robin schedules are generated entirely up front via generate_schedule().")


class SwissPairingService(BasePairingService):
    """
    Simplified Swiss pairing: groups players by current score (highest first),
    pairs sequentially while avoiding rematches when an alternative exists, and
    assigns a single-point bye to the lowest-ranked player who hasn't had one yet.

    This is intentionally simpler than the official FIDE Dutch system (no color
    "floaters" balancing across score groups, no accelerated pairings) — adequate
    for a school tournament, documented as a future extension point.
    """
    supports_all_rounds_upfront = False

    @staticmethod
    def generate_next_round_pairings(tournament, participants, standings, past_pairings):
        previous_opponent_pairs = set()
        previous_bye_ids = set()
        color_history = {p.id: {'white': 0, 'black': 0} for p in participants}

        for pairing in past_pairings:
            if pairing.is_bye:
                if pairing.white_player_id:
                    previous_bye_ids.add(pairing.white_player_id)
                continue
            if pairing.white_player_id and pairing.black_player_id:
                previous_opponent_pairs.add(frozenset({pairing.white_player_id, pairing.black_player_id}))
            if pairing.white_player_id in color_history:
                color_history[pairing.white_player_id]['white'] += 1
            if pairing.black_player_id in color_history:
                color_history[pairing.black_player_id]['black'] += 1

        ordered = sorted(
            participants,
            key=lambda p: (-standings.get(p.id, {}).get('points', 0.0), -p.seed_rating, p.user.username)
        )

        bye_player = None
        pairable = list(ordered)
        if len(pairable) % 2 == 1:
            for candidate in reversed(pairable):
                if candidate.id not in previous_bye_ids:
                    bye_player = candidate
                    break
            if bye_player is None:
                bye_player = pairable[-1]
            pairable.remove(bye_player)

        pairs = []
        remaining = list(pairable)
        while remaining:
            p1 = remaining.pop(0)
            match_idx = None
            for idx, p2 in enumerate(remaining):
                if frozenset({p1.id, p2.id}) not in previous_opponent_pairs:
                    match_idx = idx
                    break
            if match_idx is None:
                match_idx = 0  # forced rematch: no alternative left in the pool
            p2 = remaining.pop(match_idx)
            pairs.append((p1, p2))

        round_pairings = []
        for p1, p2 in pairs:
            white, black = SwissPairingService._assign_colors(p1, p2, color_history)
            round_pairings.append((white, black))

        if bye_player is not None:
            round_pairings.append((bye_player, None))

        return round_pairings

    @staticmethod
    def _assign_colors(p1, p2, color_history):
        h1 = color_history.get(p1.id, {'white': 0, 'black': 0})
        h2 = color_history.get(p2.id, {'white': 0, 'black': 0})
        # Whoever has played white less often gets white this round.
        if h1['white'] < h2['white']:
            return p1, p2
        if h2['white'] < h1['white']:
            return p2, p1
        # Tie: whoever has played black more recently/often gets white now.
        if h1['black'] >= h2['black']:
            return p1, p2
        return p2, p1


PAIRING_SERVICES = {
    Tournament.Format.ROUND_ROBIN: RoundRobinPairingService,
    Tournament.Format.SWISS: SwissPairingService,
}


def get_pairing_service(tournament: Tournament) -> BasePairingService:
    service = PAIRING_SERVICES.get(tournament.format)
    if service is None:
        raise ValueError(f"No hay servicio de emparejamiento registrado para el formato '{tournament.format}'.")
    return service
