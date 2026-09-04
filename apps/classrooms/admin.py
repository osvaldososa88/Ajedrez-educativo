from django.contrib import admin
from .models import Classroom, ClassroomEnrollment, ClassroomInvitation, Activity, ActivityObjective


class ActivityObjectiveInline(admin.TabularInline):
    model = ActivityObjective
    extra = 1


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ('name', 'join_code', 'is_active', 'created_by', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'join_code')
    filter_horizontal = ('teachers',)


@admin.register(ClassroomEnrollment)
class ClassroomEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'classroom', 'is_active', 'joined_at')
    list_filter = ('is_active',)


@admin.register(ClassroomInvitation)
class ClassroomInvitationAdmin(admin.ModelAdmin):
    list_display = ('student', 'classroom', 'status', 'invited_by', 'created_at')
    list_filter = ('status',)


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('title', 'classroom', 'assigned_date', 'due_date', 'created_by')
    list_filter = ('classroom',)
    filter_horizontal = ('puzzles', 'assigned_students')
    inlines = [ActivityObjectiveInline]
