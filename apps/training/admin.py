from django.contrib import admin
from .models import Puzzle, PuzzleAttempt, UserTrainingStats, PuzzleFavorite, PuzzleRating

@admin.register(Puzzle)
class PuzzleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'theme', 'difficulty', 'objective', 'status', 'author', 'moderated_by', 'created_at')
    list_filter = ('category', 'theme', 'difficulty', 'objective', 'status')
    search_fields = ('title', 'description')
    actions = ['approve_puzzles', 'reject_puzzles', 'archive_puzzles']

    @admin.action(description='Aprobar y publicar problemas seleccionados')
    def approve_puzzles(self, request, queryset):
        from django.utils import timezone
        queryset.update(status=Puzzle.Status.PUBLISHED, moderated_by=request.user, reviewed_at=timezone.now())

    @admin.action(description='Rechazar problemas seleccionados')
    def reject_puzzles(self, request, queryset):
        from django.utils import timezone
        queryset.update(status=Puzzle.Status.REJECTED, moderated_by=request.user, reviewed_at=timezone.now())

    @admin.action(description='Archivar problemas seleccionados')
    def archive_puzzles(self, request, queryset):
        queryset.update(status=Puzzle.Status.ARCHIVED)

@admin.register(PuzzleAttempt)
class PuzzleAttemptAdmin(admin.ModelAdmin):
    list_display = ('user', 'puzzle', 'solved', 'attempts_count', 'hints_used', 'time_taken_seconds', 'completed_at')
    list_filter = ('solved',)

@admin.register(UserTrainingStats)
class UserTrainingStatsAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'theme', 'total_attempts', 'successful_attempts', 'success_rate')
    list_filter = ('category', 'theme')

@admin.register(PuzzleFavorite)
class PuzzleFavoriteAdmin(admin.ModelAdmin):
    list_display = ('user', 'puzzle', 'created_at')

@admin.register(PuzzleRating)
class PuzzleRatingAdmin(admin.ModelAdmin):
    list_display = ('user', 'puzzle', 'value', 'created_at')
    list_filter = ('value',)
