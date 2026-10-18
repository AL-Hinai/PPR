from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F
from django.shortcuts import redirect, render
from django.utils import timezone

from apps.applications.models import Application, Decision, ReviewAssignment

S = Application.Status


def home(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    return render(request, "core/home.html")


@login_required
def dashboard(request):
    user = request.user
    if user.is_hod:
        return _hod_dashboard(request)
    if user.is_reviewer:
        return _reviewer_dashboard(request)
    if user.is_company:
        return _company_dashboard(request)
    if user.is_superuser:
        return redirect("admin:index")
    return render(request, "core/no_role.html", status=403)


def _status_counts(queryset):
    counts = dict(queryset.values_list("status").annotate(n=Count("pk")))
    return [(value, label, counts.get(value, 0)) for value, label in S.choices]


def _company_dashboard(request):
    applications = Application.objects.visible_to(request.user)
    action_needed = applications.filter(status__in=[S.DRAFT, S.VALIDATION_FAILED, S.INFO_REQUESTED])
    return render(
        request,
        "core/dashboard_company.html",
        {
            "recent": applications.select_related("company")[:8],
            "action_needed": action_needed,
            "counts": _status_counts(applications),
            "total": applications.count(),
            "approved": applications.filter(status=S.APPROVED).count(),
            "in_progress": applications.exclude(status__in=[S.DRAFT, S.APPROVED, S.REJECTED]).count(),
        },
    )


def _reviewer_dashboard(request):
    user = request.user
    applications = Application.objects.visible_to(user).select_related("company")
    to_review = applications.filter(status=S.UNDER_REVIEW)
    # Modules assigned to this reviewer that still need an assessment (new, or re-assessment after an answer).
    my_modules = []
    for application in to_review:
        pending = [row["assignment"].section for row in application.review_progress()
                   if row["pending"] and row["assignment"].reviewer_id == user.pk]
        if pending:
            my_modules.append({"application": application, "sections": pending})
    return render(
        request,
        "core/dashboard_reviewer.html",
        {
            "my_modules": my_modules,
            "specialties": user.get_specialties_display(),
            "to_review": to_review,
            "waiting": applications.filter(status=S.INFO_REQUESTED),
            "done": applications.filter(status__in=[S.REVIEW_COMPLETE, S.APPROVED, S.REJECTED])[:10],
        },
    )


def _hod_dashboard(request):
    applications = Application.objects.visible_to(request.user)
    year = timezone.localdate().year
    decisions = Decision.objects.filter(decided_at__year=year).select_related("application")
    durations = [
        (d.decided_at - d.application.submitted_at).days
        for d in decisions.filter(application__submitted_at__isnull=False)
    ]
    counts = _status_counts(applications)
    peak = max((c for _, _, c in counts), default=0) or 1
    # Active module assignments per reviewer, with their specialties.
    workload = (
        ReviewAssignment.objects.filter(application__status__in=[S.UNDER_REVIEW, S.INFO_REQUESTED])
        .values(name=F("reviewer__username"))
        .annotate(n=Count("pk"), applications=Count("application", distinct=True))
        .order_by("-n")
    )
    return render(
        request,
        "core/dashboard_hod.html",
        {
            "awaiting_assignment": applications.filter(status=S.VALIDATED).select_related("company"),
            "auto_assign": settings.AUTO_ASSIGN_REVIEW_TEAMS,
            "awaiting_decision": applications.filter(status=S.REVIEW_COMPLETE).select_related("company", "assigned_reviewer"),
            "counts": [(v, label, c, round(c * 100 / peak)) for v, label, c in counts if v != S.DRAFT],
            "approved_this_year": decisions.filter(outcome=Decision.Outcome.APPROVED).count(),
            "rejected_this_year": decisions.filter(outcome=Decision.Outcome.REJECTED).count(),
            "in_review": applications.filter(status__in=[S.UNDER_REVIEW, S.INFO_REQUESTED]).count(),
            "avg_days": round(sum(durations) / len(durations)) if durations else None,
            "workload": workload,
            "year": year,
        },
    )
