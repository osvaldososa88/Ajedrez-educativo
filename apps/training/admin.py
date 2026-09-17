from django.contrib import admin
from .models import Puzzle, PuzzleAttempt, UserTrainingStats, PuzzleFavorite, PuzzleRating

@admin.register(Puzzle)
class PuzzleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'theme', 'difficulty', 'objective', 'status', 'author', 'moderated_by', 'created_at')
    list_filter = ('category', 'theme', 'difficulty', 'objective', 'status', 'puzzle_type', 'objective_type')
    search_fields = ('title', 'description')
    actions = ['approve_puzzles', 'reject_puzzles', 'archive_puzzles']
    
    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'author', 'status')
        }),
        ('Configuración del Problema', {
            'fields': ('initial_fen', 'side_to_move', 'category', 'theme', 'difficulty', 'objective', 'puzzle_type', 'objective_type')
        }),
        ('Opciones Específicas', {
            'fields': ('bot_profile', 'bot_opponent', 'bot_side', 'max_moves', 'allow_bot_opponent', 'critical_pieces'),
            'classes': ('collapse',),
            'description': 'Configuración para problemas OBJECTIVE y bot opponents'
        }),
        ('Solución (solo tipos secuenciales)', {
            'fields': ('solution_moves', 'variations_json', 'hints'),
            'classes': ('collapse',),
            'description': 'Usado cuando puzzle_type = SEQUENCE'
        }),
        ('Moderación', {
            'fields': ('moderated_by', 'moderation_notes', 'reviewed_at'),
            'classes': ('collapse',)
        }),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.fieldsets
            
        if obj.puzzle_type == Puzzle.PuzzleType.SEQUENCE:
            return (
                (None, {
                    'fields': ('title', 'description', 'author', 'status')
                }),
                ('Configuración del Problema', {
                    'fields': ('initial_fen', 'side_to_move', 'category', 'theme', 'difficulty', 'objective', 'puzzle_type', 'objective_type')
                }),
                ('Solución (tipo secuencial)', {
                    'fields': ('solution_moves', 'variations_json', 'hints')
                }),
                ('Moderación', {
                    'fields': ('moderated_by', 'moderation_notes', 'reviewed_at'),
                    'classes': ('collapse',)
                }),
            )
        else:
            return self.fieldsets

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return ('reviewed_at',)

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
