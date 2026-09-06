from django.contrib import admin

from .models import RatingChange


@admin.register(RatingChange)
class RatingChangeAdmin(admin.ModelAdmin):
    """Read-only log: rating history must never be edited manually."""
    list_display = (
        'player', 'result', 'rating_before', 'rating_after', 'change',
        'opponent_username', 'game_mode', 'k_factor', 'created_at',
    )
    list_filter = ('game_mode', 'result', 'created_at')
    search_fields = ('player__username', 'opponent_username')
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
