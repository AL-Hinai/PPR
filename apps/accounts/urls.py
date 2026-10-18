from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.utils.translation import gettext_lazy as _

from . import views
from .forms import LoginForm

app_name = "accounts"

PAGE = "accounts/auth_page.html"


def _page(view, **context):
    return view.as_view(template_name=PAGE, extra_context=context)


urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            authentication_form=LoginForm,
            redirect_authenticated_user=True,
            extra_context={"sso_enabled": settings.SSO_ENABLED, "sso_label": settings.SSO_LABEL},
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name=PAGE,
            success_url=reverse_lazy("accounts:password_change_done"),
            extra_context={"heading": _("Change password"), "submit": _("Change password")},
        ),
        name="password_change",
    ),
    path(
        "password/change/done/",
        _page(auth_views.PasswordChangeDoneView, heading=_("Password changed"),
              intro=_("Your password has been changed."), next_url=reverse_lazy("core:dashboard"),
              next_label=_("Back to the dashboard")),
        name="password_change_done",
    ),
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name=PAGE,
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
            extra_context={
                "heading": _("Reset password"),
                "intro": _("Enter the email address of your account. We will send you a link to choose a new password."),
                "submit": _("Send reset link"),
            },
        ),
        name="password_reset",
    ),
    path(
        "password/reset/sent/",
        _page(auth_views.PasswordResetDoneView, heading=_("Check your email"),
              intro=_("If an account uses that address, a reset link is on its way. The link works once."),
              next_url=reverse_lazy("accounts:login"), next_label=_("Back to sign in")),
        name="password_reset_done",
    ),
    path(
        "password/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name=PAGE,
            success_url=reverse_lazy("accounts:password_reset_complete"),
            extra_context={"heading": _("Choose a new password"), "submit": _("Set password")},
        ),
        name="password_reset_confirm",
    ),
    path(
        "password/reset/done/",
        _page(auth_views.PasswordResetCompleteView, heading=_("Password set"),
              intro=_("Your new password is set. You can sign in with it now."),
              next_url=reverse_lazy("accounts:login"), next_label=_("Sign in")),
        name="password_reset_complete",
    ),
    path("reviewers/", views.reviewers, name="reviewers"),
]
