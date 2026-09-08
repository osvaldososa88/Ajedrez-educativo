from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import AdminPasswordChangeForm
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('username', 'email', 'role', 'elo_rating', 'date_joined', 'last_login', 'is_active')
    list_filter = ('role', 'is_active', 'is_staff', 'date_joined')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('-date_joined',)

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'bio')}),
        ('Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )

    readonly_fields = ('last_login', 'date_joined')

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'email', 'role', 'password1', 'password2'),
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        """Use AdminPasswordChangeForm for password changes in admin."""
        if obj is not None and 'password' in kwargs.get('fields', self.get_fields(request, obj)):
            kwargs['form'] = AdminPasswordChangeForm
        return super().get_form(request, obj, **kwargs)
