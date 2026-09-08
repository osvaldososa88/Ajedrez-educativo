from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from .models import CustomUser

class CustomUserCreationForm(UserCreationForm):
    # 'BOT' is an internal role for training bots; it must never be selectable
    # at registration time.
    human_roles = [
        (value, label) for value, label in CustomUser.Role.choices if value != CustomUser.Role.BOT
    ]
    role = forms.ChoiceField(
        choices=human_roles,
        required=True,
        widget=forms.Select(attrs={'class': 'form-select'})
    )


    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'role')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})

class CustomUserChangeForm(UserChangeForm):
    class Meta:
        model = CustomUser
        fields = ('username', 'email', 'bio')


class ProfileEditForm(forms.ModelForm):
    """Form for users to edit their own profile. Role is NOT editable here."""

    class Meta:
        model = CustomUser
        fields = ('first_name', 'last_name', 'email', 'bio')
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-input'}),
            'last_name': forms.TextInput(attrs={'class': 'form-input'}),
            'email': forms.EmailInput(attrs={'class': 'form-input'}),
            'bio': forms.Textarea(attrs={'class': 'form-input', 'rows': 4}),
        }
