from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.applications.models import Application

from . import services
from .models import CtdSection, User
from .permissions import hod_required

ACTIVE = [Application.Status.UNDER_REVIEW, Application.Status.INFO_REQUESTED]


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
