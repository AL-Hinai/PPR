"""Read-only JSON API for other Ministry systems (registers, pharmacovigilance, import permits).

Authenticate with ``Authorization: Bearer <key>`` (``manage.py create_api_key``). Keys see the applications
the Head of Department sees (everything except drafts), never documents, assessments or notes.
"""
from functools import wraps

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from apps.applications.models import Application

from .models import ApiToken

PAGE_SIZE = 100


def api_key_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        scheme, _, key = request.headers.get("Authorization", "").partition(" ")
        token = ApiToken.authenticate(key.strip()) if scheme.lower() == "bearer" else None
        if token is None:
            response = JsonResponse({"error": "invalid or missing API key"}, status=401)
            response["WWW-Authenticate"] = "Bearer"
            return response
        request.api_token = token
        return view(request, *args, **kwargs)
    return wrapper


def _queryset():
    return (Application.objects.exclude(status=Application.Status.DRAFT)
            .select_related("company", "decision").prefetch_related("sequences"))


def _decision(application):
    decision = getattr(application, "decision", None)
    if decision is None:
        return None
    return {"outcome": decision.outcome, "approval_no": decision.approval_no,
            "valid_until": decision.valid_until, "decided_at": decision.decided_at}


def _summary(application):
    return {
        "reference_no": application.reference_no,
        "product_name": application.product_name,
        "active_ingredients": application.active_ingredients,
        "strength": application.strength,
        "dosage_form": application.dosage_form,
        "atc_code": application.atc_code,
        "application_type": application.application_type,
        "status": application.status,
        "company": {"name_en": application.company.name_en, "name_ar": application.company.name_ar,
                    "registration_no": application.company.registration_no},
        "submitted_at": application.submitted_at,
        "updated_at": application.updated_at,
        "decision": _decision(application),
    }


@require_GET
@api_key_required
def application_list(request):
    """?status=APPROVED&updated_since=2026-01-01T00:00:00Z&page=2, newest change first, 100 per page."""
    queryset = _queryset()
    if status := request.GET.get("status"):
        queryset = queryset.filter(status=status)
    if since := request.GET.get("updated_since"):
        moment = parse_datetime(since)
        if moment is None:
            return JsonResponse({"error": "updated_since must be an ISO 8601 date-time"}, status=400)
        queryset = queryset.filter(updated_at__gte=moment)
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except ValueError:
        page = 1
    queryset = queryset.order_by("-updated_at", "-pk")
    total = queryset.count()
    items = queryset[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    return JsonResponse({"count": total, "page": page, "page_size": PAGE_SIZE,
                         "results": [_summary(a) for a in items]})


@require_GET
@api_key_required
def application_detail(request, reference_no):
    application = get_object_or_404(_queryset(), reference_no=reference_no)
    data = _summary(application)
    data["route"] = application.route
    data["sequences"] = [
        {"number": s.number, "validation_status": s.validation_status, "uploaded_at": s.uploaded_at,
         "submission_type": s.envelope.get("submission_type", ""), "submission_unit": s.envelope.get("submission_unit", "")}
        for s in sorted(application.sequences.all(), key=lambda s: s.number)
        if s.validation_status != s.ValidationStatus.PENDING
    ]
    return JsonResponse(data)
