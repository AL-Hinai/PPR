from django.contrib.auth.forms import AuthenticationForm

from apps.core.forms import StyledFormMixin


class LoginForm(StyledFormMixin, AuthenticationForm):
    pass
