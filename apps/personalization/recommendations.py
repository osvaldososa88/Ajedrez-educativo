"""
Rule-based weekly recommendations — no ML model. Each recommendation item is
produced by one explicit, human-readable rule over existing data (attempts,
detected errors), so a teacher or student can always see *why* something was
suggested. See apps/personalization/README.md for the full rule list and how
to evolve this into a more advanced model later.
"""
from datetime import timedelta
from django.utils import timezone
from apps.training.models import Puzzle, PuzzleAttempt, UserTrainingStats
from .models import DetectedGameError

RECENT_ERROR_WINDOW_DAYS = 30
WEAK_THEME_MIN_ATTEMPTS = 2
WEAK_THEME_SUCCESS_THRESHOLD = 50.0

TARGET_COUNTS = {
    'weak_theme': 3,
    'error_category': 2,
    'defense_or_attack': 1,
    'opening': 5,
}


def _solved_puzzle_ids(user):
    return set(PuzzleAttempt.objects.filter(user=user, solved=True).values_list('puzzle_id', flat=True))


class RecommendationService:
    @staticmethod
    def build_weekly_recommendations(user) -> list:
        solved_ids = _solved_puzzle_ids(user)
        recommendations = []

        recommendations.extend(RecommendationService._weak_theme_items(user, solved_ids))
        recommendations.extend(RecommendationService._error_category_items(user, solved_ids))
        recommendations.extend(RecommendationService._opening_items(user, solved_ids))
        recommendations.extend(RecommendationService._defense_attack_items(user, solved_ids))

        return recommendations

    @staticmethod
    def _weak_theme_items(user, solved_ids):
        weak_stats = [
            s for s in UserTrainingStats.objects.filter(user=user)
            if s.total_attempts >= WEAK_THEME_MIN_ATTEMPTS and s.success_rate < WEAK_THEME_SUCCESS_THRESHOLD
        ]
        weak_stats.sort(key=lambda s: s.success_rate)

        items = []
        for stat in weak_stats[:2]:
            target = TARGET_COUNTS['weak_theme']
            puzzles = list(
                Puzzle.objects.filter(status=Puzzle.Status.PUBLISHED, category=stat.category, theme=stat.theme)
                .exclude(id__in=solved_ids)[:target]
            )
            if not puzzles:
                continue
            items.append({
                'reason': (
                    f"Has acertado solo el {stat.success_rate}% de tus intentos en "
                    f"{Puzzle.Theme(stat.theme).label}: practica {len(puzzles)} más."
                ),
                'count': len(puzzles),
                'category': stat.category,
                'theme': stat.theme,
                'puzzles': puzzles,
            })
        return items

    @staticmethod
    def _error_category_items(user, solved_ids):
        cutoff = timezone.now() - timedelta(days=RECENT_ERROR_WINDOW_DAYS)
        # Openings, Defense and Attack each already have their own dedicated
        # recommendation item (below), so they're excluded here to avoid
        # suggesting the same category twice under two different labels.
        dedicated_categories = {Puzzle.Category.OPENINGS, Puzzle.Category.DEFENSE, Puzzle.Category.ATTACK}
        counts = {}
        for row in DetectedGameError.objects.filter(student=user, created_at__gte=cutoff).values('category'):
            if row['category'] in dedicated_categories:
                continue
            counts[row['category']] = counts.get(row['category'], 0) + 1

        ranked_categories = sorted(counts.items(), key=lambda pair: -pair[1])[:2]

        items = []
        for category, error_count in ranked_categories:
            target = TARGET_COUNTS['error_category']
            own_puzzle_ids = DetectedGameError.objects.filter(
                student=user, category=category, generated_puzzle__isnull=False
            ).values_list('generated_puzzle_id', flat=True)
            puzzles = list(
                Puzzle.objects.filter(id__in=own_puzzle_ids).exclude(id__in=solved_ids)[:target]
            )
            if not puzzles:
                continue
            items.append({
                'reason': (
                    f"Detectamos {error_count} error(es) de {Puzzle.Category(category).label} "
                    f"en tus partidas recientes: revisa {len(puzzles)} de esas posiciones."
                ),
                'count': len(puzzles),
                'category': category,
                'theme': None,
                'puzzles': puzzles,
            })
        return items

    @staticmethod
    def _opening_items(user, solved_ids):
        own_opening_puzzle_ids = DetectedGameError.objects.filter(
            student=user, category=Puzzle.Category.OPENINGS, generated_puzzle__isnull=False
        ).values_list('generated_puzzle_id', flat=True)
        target = TARGET_COUNTS['opening']
        puzzles = list(
            Puzzle.objects.filter(id__in=own_opening_puzzle_ids).exclude(id__in=solved_ids)[:target]
        )
        if not puzzles:
            return []
        return [{
            'reason': f"Tienes {len(puzzles)} posición(es) de tu propia apertura para repasar.",
            'count': len(puzzles),
            'category': Puzzle.Category.OPENINGS,
            'theme': None,
            'puzzles': puzzles,
        }]

    @staticmethod
    def _defense_attack_items(user, solved_ids):
        items = []
        for category in [Puzzle.Category.DEFENSE, Puzzle.Category.ATTACK]:
            own_puzzle_ids = DetectedGameError.objects.filter(
                student=user, category=category, generated_puzzle__isnull=False
            ).values_list('generated_puzzle_id', flat=True)
            target = TARGET_COUNTS['defense_or_attack']
            puzzles = list(
                Puzzle.objects.filter(id__in=own_puzzle_ids).exclude(id__in=solved_ids)[:target]
            )
            if not puzzles:
                continue
            items.append({
                'reason': f"Refuerza tu {Puzzle.Category(category).label.lower()} con {len(puzzles)} posición(es) propia(s).",
                'count': len(puzzles),
                'category': category,
                'theme': None,
                'puzzles': puzzles,
            })
        return items
