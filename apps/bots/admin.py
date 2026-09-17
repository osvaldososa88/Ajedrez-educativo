from django.contrib import admin
from .models import Bot, BotProfile, BotProgress, Opening, OpeningLine


class OpeningLineInline(admin.TabularInline):
    model = OpeningLine
    extra = 1
    fields = ('name', 'moves_san', 'moves_uci', 'bot_color', 'priority', 'is_active')


@admin.register(Opening)
class OpeningAdmin(admin.ModelAdmin):
    list_display = ('name', 'eco', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'eco', 'description')
    inlines = [OpeningLineInline]


@admin.register(OpeningLine)
class OpeningLineAdmin(admin.ModelAdmin):
    list_display = ('opening', 'name', 'bot_color', 'priority', 'is_active')
    list_filter = ('opening', 'bot_color', 'is_active')
    search_fields = ('name', 'moves_san', 'opening__name')
    list_editable = ('priority', 'is_active')


@admin.register(BotProfile)
class BotProfileAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'engine_depth', 'skill_level', 'multipv',
        'best_move_prob', 'alt_move_prob', 'minor_error_prob', 'blunder_prob',
        'max_cp_loss', 'visual_delay_ms', 'animation_speed_ms',
    )
    search_fields = ('name', 'description')
    list_filter = ('skill_level', 'engine_depth')
    fieldsets = (
        ('Identidad del Perfil', {
            'fields': ('name', 'description')
        }),
        ('Fuerza Stockfish', {
            'fields': ('skill_level', 'engine_depth', 'move_time_ms', 'multipv', 'uci_elo'),
            'description': 'Parámetros técnicos de análisis de Stockfish.'
        }),
        ('Modelo de Error Controlado (Probabilidades)', {
            'fields': ('best_move_prob', 'alt_move_prob', 'minor_error_prob', 'blunder_prob', 'max_cp_loss'),
            'description': 'Distribución probabilística de selección de jugadas. La suma de probabilidades debe ser 1.0.'
        }),
        ('UX / Visualización', {
            'fields': ('visual_delay_ms', 'animation_speed_ms', 'error_probability'),
            'description': 'Configuración cosmética para la experiencia de usuario.'
        }),
    )


@admin.register(Bot)
class BotAdmin(admin.ModelAdmin):
    list_display = (
        'display_name', 'category', 'order', 'displayed_elo',
        'profile', 'opening_mode', 'specific_opening_white', 'specific_opening_black', 'is_active',
    )
    list_filter = ('category', 'opening_mode', 'is_active', 'profile')
    search_fields = ('display_name', 'nickname', 'description')
    list_editable = ('order', 'displayed_elo', 'is_active', 'opening_mode', 'specific_opening_white', 'specific_opening_black')
    ordering = ('category', 'order')
    filter_horizontal = ('repertoire_openings',)
    list_per_page = 50
    fieldsets = (
        ('Identidad del Bot', {
            'fields': ('display_name', 'nickname', 'avatar', 'description', 'quote', 'user')
        }),
        ('Nivel y Dificultad', {
            'fields': ('category', 'order', 'displayed_elo', 'profile', 'is_active')
        }),
        ('Configuración de Aperturas', {
            'fields': ('opening_mode', 'specific_opening_white', 'specific_opening_black', 'repertoire_openings'),
            'description': 'Define si el bot juega Stockfish puro, aperturas determinadas (blancas/negras) o un repertorio.'
        }),
    )

    @admin.display(description="Apertura con Blancas")
    def apertura_blancas(self, obj):
        return obj.get_openings_summary()['white']

    @admin.display(description="Apertura con Negras")
    def apertura_negras(self, obj):
        return obj.get_openings_summary()['black']


@admin.register(BotProgress)
class BotProgressAdmin(admin.ModelAdmin):
    list_display = ('user', 'bot', 'unlocked', 'defeated', 'defeated_at')
    list_filter = ('unlocked', 'defeated', 'bot__category')
    search_fields = ('user__username', 'bot__display_name')
    readonly_fields = ('created_at', 'updated_at')

