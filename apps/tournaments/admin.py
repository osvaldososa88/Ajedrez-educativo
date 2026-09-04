from django.contrib import admin
from .models import Tournament, TournamentParticipant, Round, Pairing


class PairingInline(admin.TabularInline):
    model = Pairing
    extra = 0


class RoundInline(admin.TabularInline):
    model = Round
    extra = 0


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('name', 'format', 'status', 'start_date', 'created_by')
    list_filter = ('format', 'status')
    search_fields = ('name',)
    filter_horizontal = ('organizers',)
    inlines = [RoundInline]


@admin.register(TournamentParticipant)
class TournamentParticipantAdmin(admin.ModelAdmin):
    list_display = ('user', 'tournament', 'status', 'seed_rating', 'had_bye')
    list_filter = ('status',)


@admin.register(Round)
class RoundAdmin(admin.ModelAdmin):
    list_display = ('tournament', 'number', 'status', 'started_at', 'closed_at')
    list_filter = ('status',)
    inlines = [PairingInline]


@admin.register(Pairing)
class PairingAdmin(admin.ModelAdmin):
    list_display = ('round', 'board_number', 'white_player', 'black_player', 'result', 'is_bye')
    list_filter = ('result', 'is_bye')
