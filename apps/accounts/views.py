from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.views import LoginView
from django.contrib.auth.decorators import login_required
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth.forms import PasswordChangeForm
from .models import CustomUser
from .forms import CustomUserCreationForm, ProfileEditForm

class RegisterView(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('login')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return redirect('classmates')

class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

class ClassmateListView(LoginRequiredMixin, ListView):
    model = CustomUser
    template_name = 'accounts/classmates.html'
    context_object_name = 'classmates'

    def get_queryset(self):
        # Return all users except the current user and bot accounts
        # (bots are training opponents, not classmates/rankings entries).
        return CustomUser.objects.exclude(id=self.request.user.id).exclude(
            role=CustomUser.Role.BOT
        ).order_by('-elo_rating', 'username')


class ProfileView(LoginRequiredMixin, DetailView):
    model = CustomUser
    template_name = 'accounts/profile.html'
    context_object_name = 'profile_user'

    def get_object(self, queryset=None):
        username = self.kwargs.get('username')
        if username:
            return get_object_or_404(CustomUser, username=username)
        return self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.ratings.services import RatingService
        context['rating_stats'] = RatingService.get_profile_stats(self.object)
        return context


class ProfileEditView(LoginRequiredMixin, UpdateView):
    model = CustomUser
    form_class = ProfileEditForm
    template_name = 'accounts/profile_edit.html'

    def get_object(self, queryset=None):
        return self.request.user

    def form_valid(self, form):
        messages.success(self.request, "Tu perfil fue actualizado correctamente.")
        return redirect('profile')


class PasswordChangeViewCustom(LoginRequiredMixin, CreateView):
    template_name = 'accounts/password_change.html'
    form_class = PasswordChangeForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.save()
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "Tu contraseña fue cambiada exitosamente.")
        return redirect('profile')

