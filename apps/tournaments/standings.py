"""
Classification / standings computation.

Tiebreak used for both formats: Buchholz (sum of opponents' final points), then
total wins, then username for full determinism. This keeps the implementation
simple while remaining a widely recognized, legitimate chess tiebreak — other
systems (Sonneborn-Berger, direct encounter, progressive score) are documented
as future extensions in the module README rather than implemented now.
"""
from .models import Pairing


class StandingsService:
    @staticmethod
    def _decided_pairings(tournament):
        return list(
            Pairing.objects.filter(round__tournament=tournament)
            .exclude(result=Pairing.Result.PENDING)
            .select_related('white_player', 'black_player')
        )

    @classmethod
    def compute_standings(cls, tournament) -> list:
        participants = list(tournament.participants.select_related('user').all())
        pairings = cls._decided_pairings(tournament)

        raw = {
            p.id: {
                'participant': p,
                'points': 0.0,
                'wins': 0,
                'draws': 0,
                'losses': 0,
                'games_played': 0,
                'byes': 0,
                'opponent_ids': [],
            }
            for p in participants
        }

        # Map user_id -> participant.id for quick opponent lookups.
        user_to_participant_id = {p.user_id: p.id for p in participants}

        for pairing in pairings:
            if pairing.is_bye:
                pid = user_to_participant_id.get(pairing.white_player_id)
                if pid is not None:
                    raw[pid]['points'] += pairing.points_for(pairing.white_player_id) or 0.0
                    raw[pid]['byes'] += 1
                continue

            for user_id in [pairing.white_player_id, pairing.black_player_id]:
                pid = user_to_participant_id.get(user_id)
                if pid is None:
                    continue
                points = pairing.points_for(user_id) or 0.0
                raw[pid]['points'] += points
                raw[pid]['games_played'] += 1
                if points == 1.0:
                    raw[pid]['wins'] += 1
                elif points == 0.5:
                    raw[pid]['draws'] += 1
                else:
                    raw[pid]['losses'] += 1

                opponent_user_id = pairing.opponent_of(user_id)
                opponent_pid = user_to_participant_id.get(opponent_user_id)
                if opponent_pid is not None:
                    raw[pid]['opponent_ids'].append(opponent_pid)

        # Buchholz: sum of opponents' current total points.
        for pid, row in raw.items():
            row['buchholz'] = round(sum(raw[opp_id]['points'] for opp_id in row['opponent_ids'] if opp_id in raw), 2)

        ordered = sorted(
            raw.values(),
            key=lambda row: (-row['points'], -row['buchholz'], -row['wins'], row['participant'].user.username)
        )

        # Standard competition ranking (ties share a rank; next rank accounts for the gap).
        results = []
        previous_key = None
        rank = 0
        for idx, row in enumerate(ordered, start=1):
            key = (row['points'], row['buchholz'], row['wins'])
            if key != previous_key:
                rank = idx
            previous_key = key
            results.append({**row, 'rank': rank})

        return results
