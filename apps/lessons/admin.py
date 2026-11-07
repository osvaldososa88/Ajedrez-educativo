from django.contrib import admin

from .models import Lesson, LessonChapter


class LessonChapterInline(admin.TabularInline):
    model = LessonChapter
    extra = 0
    fields = ['order', 'title', 'start_fen', 'source_url']
    readonly_fields = ['start_fen']


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['order', 'title', 'family', 'eco', 'color', 'is_published']
    # `order` es la primera columna: si fuese editable, AdminE124 pediría un
    # `list_display_links` explícito. Por eso solo se edita en el formulario.
    list_display_links = ['title']
    list_editable = ['is_published']
    list_filter = ['family', 'color', 'is_published']
    search_fields = ['title', 'summary', 'eco']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [LessonChapterInline]


@admin.register(LessonChapter)
class LessonChapterAdmin(admin.ModelAdmin):
    list_display = ['lesson', 'order', 'title', 'start_fen']
    list_display_links = ['title']
    list_filter = ['lesson']
    search_fields = ['title', 'intro']
    list_editable = ['order']