from django.contrib import admin
from .models import DetectedGameError, GlobalChessConfig, UserAppearancePreference
from .chess_theme_registry import get_piece_set_choices, get_board_theme_choices


@admin.register(DetectedGameError)
class DetectedGameErrorAdmin(admin.ModelAdmin):
    list_display = ('student', 'game', 'category', 'theme', 'difficulty', 'created_at')
    list_filter = ('category', 'theme', 'difficulty')
    search_fields = ('student__username',)


@admin.register(GlobalChessConfig)
class GlobalChessConfigAdmin(admin.ModelAdmin):
    """
    Configuración global predeterminada fijada por el Administrador.
    """
    list_display = ('default_piece_set', 'default_board_theme', 'allow_player_customization', 'updated_at')

    def has_add_permission(self, request):
        # Enforce singleton pattern in Django Admin
        if self.model.objects.exists():
            return False
        return super().has_add_permission(request)


@admin.register(UserAppearancePreference)
class UserAppearancePreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'piece_set', 'board_theme', 'updated_at')
    list_filter = ('piece_set', 'board_theme')
    search_fields = ('user__username',)

