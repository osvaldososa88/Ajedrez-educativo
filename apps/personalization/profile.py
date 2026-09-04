"""
Student practice profile: a small set of rule-based indicators, NOT an
absolute measurement of chess skill or intelligence. Every score is derived
transparently from two existing data sources:

  1. `training.UserTrainingStats` — success rate solving puzzles of that category.
  2. `personalization.DetectedGameError` — how often that category caused a
     significant mistake (MISTAKE/BLUNDER) in the student's own played games.

See apps/personalization/README.md for the full explanation of the formula.
"""
from django.utils import timezone
from datetime import timedelta
from apps.training.models import Puzzle, UserTrainingStats
from .models import DetectedGameError

# The six indicators explicitly requested for the student profile. Puzzle.Category
# has more values (STRATEGY, MIDDLEGAME) that simply aren't surfaced as headline
# indicators yet — they still work everywhere else (dashboard filters, puzzle authoring).
PROFILE_CATEGORIES = [
    Puzzle.Category.TACTICS,
    Puzzle.Category.CALCULATION,
    Puzzle.Category.OPENINGS,
    Puzzle.Category.ENDGAME,
    Puzzle.Category.DEFENSE,
    Puzzle.Category.ATTACK,
]

ERROR_LOOKBACK_DAYS = 60
ERROR_PENALTY_PER_MISTAKE = 5
MAX_ERROR_PENALTY = 30
NEUTRAL_BASELINE_WHEN_NO_ATTEMPTS = 50.0


class StudentProfileService:
    @staticmethod
    def compute_profile(user) -> list:
        cutoff = timezone.now() - timedelta(days=ERROR_LOOKBACK_DAYS)

        stats_by_category = {}
        for stat in UserTrainingStats.objects.filter(user=user):
            bucket = stats_by_category.setdefault(stat.category, {'attempts': 0, 'successes': 0})
            bucket['attempts'] += stat.total_attempts
            bucket['successes'] += stat.successful_attempts

        errors_by_category = {}
        error_qs = DetectedGameError.objects.filter(student=user, created_at__gte=cutoff)
        for row in error_qs.values('category'):
            errors_by_category[row['category']] = errors_by_category.get(row['category'], 0) + 1

        indicators = []
        for category in PROFILE_CATEGORIES:
            stats = stats_by_category.get(category)
            error_count = errors_by_category.get(category, 0)

            has_attempts = bool(stats and stats['attempts'] > 0)
            if not has_attempts and error_count == 0:
                indicators.append({
                    'category': category,
                    'label': Puzzle.Category(category).label,
                    'score': None,
                    'attempts': 0,
                    'recent_errors': 0,
                })
                continue

            success_rate = (
                round((stats['successes'] / stats['attempts']) * 100, 1)
                if has_attempts else NEUTRAL_BASELINE_WHEN_NO_ATTEMPTS
            )
            penalty = min(MAX_ERROR_PENALTY, error_count * ERROR_PENALTY_PER_MISTAKE)
            score = max(0.0, min(100.0, round(success_rate - penalty, 1)))

            indicators.append({
                'category': category,
                'label': Puzzle.Category(category).label,
                'score': score,
                'attempts': stats['attempts'] if stats else 0,
                'recent_errors': error_count,
            })

        return indicators
