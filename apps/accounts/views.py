from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.applications.models import Application

from . import services
from .demo import demo_accounts
from .forms import LoginForm
from .models import CtdSection, User
from .permissions import hod_required

ACTIVE = [Application.Status.UNDER_REVIEW, Application.Status.INFO_REQUESTED]


class LoginView(auth_views.LoginView):
    """The ordinary Django login. It only adds the demo accounts the page offers as buttons."""

    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        accounts = demo_accounts()
        return super().get_context_data(**kwargs) | {
            "sso_enabled": settings.SSO_ENABLED,
            "sso_label": settings.SSO_LABEL,
            "demo_accounts": accounts,
            "demo_password": settings.DEMO_LOGIN_PASSWORD if accounts else "",
        }


def _pk(value):
    """A primary key from a form field; anything else is a 404, not a server error."""
    if not str(value or "").isdigit():
        raise Http404
    return int(value)


@hod_required
def reviewers(request):
    """The HOD decides each reviewer's specialties; reviewers cannot change them."""
    if request.method == "POST" and "default_lead" in request.POST:
        lead = None
        if request.POST["default_lead"]:
            lead = get_object_or_404(User, pk=_pk(request.POST["default_lead"]), role=User.Role.REVIEWER)
        try:
            services.set_default_lead(lead, request.user)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                _("%(name)s now leads automatically assigned review teams.") % {"name": lead.display_name}
                if lead else _("No default lead: each team is led by the reviewer covering the most modules."),
            )
        return redirect("accounts:reviewers")

    if request.method == "POST":
        reviewer = get_object_or_404(User, pk=_pk(request.POST.get("reviewer")), role=User.Role.REVIEWER)
        try:
            services.set_specialties(reviewer, request.user, request.POST.getlist("specialties"))
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        else:
            messages.success(
                request,
                _("Specialties of %(name)s saved: %(modules)s.")
                % {"name": reviewer.display_name, "modules": reviewer.get_specialties_display() or "—"},
            )
        return redirect("accounts:reviewers")

    rows = (
        User.objects.filter(role=User.Role.REVIEWER)
        .select_related("specialties_updated_by")
        .annotate(active_modules=Count("review_assignments", filter=Q(review_assignments__application__status__in=ACTIVE)))
        .order_by("-is_active", "first_name", "username")
    )
    return render(
        request,
        "accounts/reviewers.html",
        {"reviewers": rows, "sections": CtdSection.choices, "coverage": services.coverage()},
    )
