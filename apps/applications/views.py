import csv
import mimetypes
from collections import OrderedDict

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from apps.accounts.permissions import any_role_required, company_required, hod_required, reviewer_required
from apps.assistant.context import remember_application, remember_document
from apps.validation.ectd import build_dossier_tree, locate_sequence_dir
from apps.validation.models import Finding

from . import services
from .forms import (
    ApplicationForm,
    CompleteReviewForm,
    DecisionForm,
    InfoRequestForm,
    ResponseUploadForm,
    ReturnForm,
    ReviewForm,
    ReviewTeamForm,
    SequenceUploadForm,
)
from .models import Application, Sequence

S = Application.Status
TABS = ("overview", "sequences", "review", "history")
INLINE_TYPES = {".pdf", ".png", ".jpg", ".jpeg", ".gif"}
# Markup/text shown as plain source so applicant files can never run script in a reviewer's browser.
TEXT_TYPES = {".txt", ".xml", ".xsd", ".xsl", ".dtd", ".mod", ".ent", ".csv", ".json", ".md5", ".sgm", ".htm", ".html"}
PROGRESS_STEPS = [
    (gettext_lazy("Preparation"), {S.DRAFT}),
    (gettext_lazy("Technical validation"), {S.SUBMITTED, S.VALIDATING, S.VALIDATION_FAILED}),
    (gettext_lazy("Assignment"), {S.VALIDATED}),
    (gettext_lazy("Scientific review"), {S.UNDER_REVIEW, S.INFO_REQUESTED}),
    (gettext_lazy("HOD decision"), {S.REVIEW_COMPLETE}),
    (gettext_lazy("Decision issued"), {S.APPROVED, S.REJECTED}),
]


def _progress(status):
    """[(label, state)] where state is done / current / failed / todo."""
    current = next(i for i, (_label, statuses) in enumerate(PROGRESS_STEPS) if status in statuses)
    steps = []
    for i, (label, _statuses) in enumerate(PROGRESS_STEPS):
        if i < current or (i == current and status == S.APPROVED):
            state = "done"
        elif i == current:
            state = "failed" if status in (S.VALIDATION_FAILED, S.REJECTED) else "current"
        else:
            state = "todo"
        steps.append((label, state))
    return steps


def _get_application(request, pk):
    queryset = Application.objects.visible_to(request.user).select_related(
        "company", "assigned_reviewer", "created_by"
    )
    application = get_object_or_404(queryset, pk=pk)
    # The dossier assistant uses this to know which medicine the reader is working on.
    remember_application(request, application)
    return application


def _detail_url(application, tab="overview"):
    return f"{reverse('applications:detail', args=[application.pk])}?tab={tab}"


# --- list / create / edit --------------------------------------------------------

@any_role_required
def application_list(request):
    applications = Application.objects.visible_to(request.user).select_related("company", "assigned_reviewer")
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()
    if status in S.values:
        applications = applications.filter(status=status)
    if query:
        applications = applications.filter(
            Q(reference_no__icontains=query)
            | Q(product_name__icontains=query)
            | Q(active_ingredients__icontains=query)
            | Q(company__name_en__icontains=query)
            | Q(company__name_ar__icontains=query)
        )
    page = Paginator(applications, 20).get_page(request.GET.get("page"))
    return render(
        request,
        "applications/list.html",
        {"page": page, "status": status, "query": query, "statuses": S.choices},
    )


@company_required
def application_create(request):
    form = ApplicationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        application = form.save(commit=False)
        application.company = request.user.company
        application.created_by = request.user
        application.save()
        messages.success(request, _("Application created. Now upload the eCTD package (sequence 0000)."))
        return redirect(_detail_url(application, "sequences"))
    return render(request, "applications/form.html", {"form": form})


@company_required
def application_edit(request, pk):
    application = _get_application(request, pk)
    if application.status != S.DRAFT:
        raise PermissionDenied
    form = ApplicationForm(request.POST or None, instance=application)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Application updated."))
        return redirect(application)
    return render(request, "applications/form.html", {"form": form, "application": application})


# --- detail page ------------------------------------------------------------------

def _history_for(user, application):
    """The audit trail as this user may see it: applicants get no team changes, internal notes or reviewer names."""
    entries = []
    for entry in application.history.select_related("actor"):
        if user.is_company and entry.is_team_change:
            continue
        entry.shown_note = entry.note_for(user)
        entry.hide_actor = user.is_company and entry.actor is not None and entry.actor.is_reviewer
        entries.append(entry)
    return entries


def _detail_context(request, application, tab, **forms):
    user = request.user
    status = application.status
    is_owner = user.is_company and user.company_id == application.company_id
    is_lead = user.is_reviewer and application.assigned_reviewer_id == user.pk
    my_sections = application.sections_for(user) if user.is_reviewer else []
    pending = application.pending_sequence()

    context = {
        "application": application,
        "tab": tab if tab in TABS else "overview",
        "tabs": [
            ("overview", _("Overview")),
            ("sequences", _("eCTD sequences")),
            ("review", _("Assessment")),
            ("history", _("History")),
        ],
        "sequences": application.sequences.select_related("uploaded_by").prefetch_related("validation_runs"),
        "history": _history_for(user, application),
        "reviews": application.reviews.select_related("reviewer"),
        "info_requests": application.info_requests.select_related("raised_by", "response_sequence"),
        "decision": getattr(application, "decision", None),
        "pending_sequence": pending,
        "progress": _progress(status),
        "is_owner": is_owner,
        "is_lead": is_lead,
        "my_sections": my_sections,
        "is_assigned": is_lead or bool(my_sections),
        "review_progress": application.review_progress(),
        "missing_sections": application.missing_sections(),
    }
    if user.is_company:
        # Applicants see the questions sent to them and the decision, not the internal assessment.
        context.update(reviews=[], review_progress=[], missing_sections=[])
    if is_owner:
        context["can_edit"] = status == S.DRAFT
        if status in (S.DRAFT, S.VALIDATION_FAILED):
            context["upload_form"] = forms.get("upload_form") or SequenceUploadForm()
            context["can_submit"] = pending is not None
        if status == S.INFO_REQUESTED:
            context["response_form"] = forms.get("response_form") or ResponseUploadForm()
    if user.is_hod:
        if status in (S.VALIDATED, S.UNDER_REVIEW, S.INFO_REQUESTED):
            context["assign_form"] = forms.get("assign_form") or ReviewTeamForm(application)
        if status == S.REVIEW_COMPLETE:
            context["decision_form"] = forms.get("decision_form") or DecisionForm()
            context["return_form"] = forms.get("return_form") or ReturnForm()
    if status == S.UNDER_REVIEW and my_sections:
        context["review_form"] = forms.get("review_form") or ReviewForm(sections=my_sections)
    if status == S.UNDER_REVIEW and is_lead:
        context["info_form"] = forms.get("info_form") or InfoRequestForm(application=application)
        context["complete_form"] = forms.get("complete_form") or CompleteReviewForm()
    return context


def _render_detail(request, application, tab, status=200, **forms):
    context = _detail_context(request, application, tab, **forms)
    return render(request, "applications/detail.html", context, status=status)


@any_role_required
def application_detail(request, pk):
    application = _get_application(request, pk)
    return _render_detail(request, application, request.GET.get("tab", "overview"))


# --- company actions --------------------------------------------------------------

@company_required
@require_POST
def upload_sequence(request, pk):
    application = _get_application(request, pk)
    if application.status not in (S.DRAFT, S.VALIDATION_FAILED, S.INFO_REQUESTED):
        raise PermissionDenied

    if application.status == S.INFO_REQUESTED:
        form = ResponseUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return _render_detail(request, application, "sequences", status=400, response_form=form)
        sequence, run = services.respond_to_info_request(
            application, request.user, form.cleaned_data["package"], form.cleaned_data["note"]
        )
        if sequence.is_accepted:
            messages.success(request, _("Response sequence %(no)s passed validation and was sent to the reviewer.") % {"no": sequence.number})
        else:
            messages.error(request, _("Response sequence %(no)s failed technical validation. Fix the errors and upload again.") % {"no": sequence.number})
        return redirect("applications:sequence", pk=application.pk, seq_pk=sequence.pk)

    form = SequenceUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return _render_detail(request, application, "sequences", status=400, upload_form=form)
    sequence = services.store_sequence(application, request.user, form.cleaned_data["package"])
    messages.success(
        request, _("Package uploaded as sequence %(no)s. Submit it to start technical validation.") % {"no": sequence.number}
    )
    return redirect(_detail_url(application, "sequences"))


@company_required
@require_POST
def submit_application(request, pk):
    application = _get_application(request, pk)
    if application.status not in (S.DRAFT, S.VALIDATION_FAILED):
        raise PermissionDenied
    try:
        sequence, run = services.submit(application, request.user)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect(_detail_url(application, "sequences"))
    if sequence.is_accepted:
        messages.success(request, _("Your submission passed technical validation and is waiting for review."))
    else:
        messages.error(
            request,
            _("Technical validation failed with %(count)s error(s). Review the report, fix the package and resubmit.")
            % {"count": run.error_count},
        )
    return redirect("applications:sequence", pk=application.pk, seq_pk=sequence.pk)


# --- HOD actions ---------------------------------------------------------------------

@hod_required
@require_POST
def assign_reviewer(request, pk):
    application = _get_application(request, pk)
    form = ReviewTeamForm(application, request.POST)
    if not form.is_valid():
        return _render_detail(request, application, "overview", status=400, assign_form=form)
    try:
        services.assign_review_team(application, request.user, form.cleaned_data["lead"], form.sections())
    except ValidationError as exc:
        for error in exc.messages:
            form.add_error(None, error)
        return _render_detail(request, application, "overview", status=400, assign_form=form)
    messages.success(request, _("Review team assigned."))
    return redirect(application)


@hod_required
@require_POST
def decide(request, pk):
    application = _get_application(request, pk)
    if application.status != S.REVIEW_COMPLETE:
        raise PermissionDenied
    form = DecisionForm(request.POST)
    if not form.is_valid():
        return _render_detail(request, application, "review", status=400, decision_form=form)
    decision = services.decide(application, request.user, form.cleaned_data["outcome"], form.cleaned_data["justification"])
    messages.success(request, _("Decision recorded: %(outcome)s.") % {"outcome": decision.get_outcome_display()})
    return redirect(_detail_url(application, "review"))


@hod_required
@require_POST
def return_to_reviewer(request, pk):
    application = _get_application(request, pk)
    if application.status != S.REVIEW_COMPLETE:
        raise PermissionDenied
    form = ReturnForm(request.POST)
    if not form.is_valid():
        return _render_detail(request, application, "review", status=400, return_form=form)
    services.return_to_reviewer(application, request.user, form.cleaned_data["note"])
    messages.success(request, _("Application returned to the reviewer."))
    return redirect(_detail_url(application, "review"))


# --- reviewer actions ----------------------------------------------------------------

def _reviewer_application(request, pk):
    """Lead-reviewer actions: questions to the applicant and the recommendation."""
    application = _get_application(request, pk)
    if application.status != S.UNDER_REVIEW or application.assigned_reviewer_id != request.user.pk:
        raise PermissionDenied
    return application


@reviewer_required
@require_POST
def add_review(request, pk):
    """A module assessment, only for the modules the HOD assigned to this reviewer."""
    application = _get_application(request, pk)
    sections = application.sections_for(request.user)
    if application.status != S.UNDER_REVIEW or not sections:
        raise PermissionDenied
    form = ReviewForm(request.POST, sections=sections)
    if not form.is_valid():
        return _render_detail(request, application, "review", status=400, review_form=form)
    services.add_review(application, request.user, **form.cleaned_data)
    messages.success(request, _("Section review saved."))
    return redirect(_detail_url(application, "review"))


@reviewer_required
@require_POST
def request_info(request, pk):
    application = _reviewer_application(request, pk)
    form = InfoRequestForm(request.POST, application=application)
    if not form.is_valid():
        return _render_detail(request, application, "review", status=400, info_form=form)
    services.request_information(
        application, request.user, form.cleaned_data["questions"], form.cleaned_data["due_date"],
        sections=form.cleaned_data["sections"],
    )
    messages.success(request, _("Questions sent to the applicant. The review clock is stopped."))
    return redirect(_detail_url(application, "review"))


@reviewer_required
@require_POST
def complete_review(request, pk):
    application = _reviewer_application(request, pk)
    form = CompleteReviewForm(request.POST)
    if not form.is_valid():
        return _render_detail(request, application, "review", status=400, complete_form=form)
    try:
        services.complete_review(
            application, request.user, form.cleaned_data["recommendation"], form.cleaned_data["summary"]
        )
    except ValidationError as exc:
        form.add_error(None, exc)
        return _render_detail(request, application, "review", status=400, complete_form=form)
    messages.success(request, _("Review completed and sent to the Head of Department."))
    return redirect(_detail_url(application, "review"))


# --- certificate -------------------------------------------------------------------

@any_role_required
def certificate(request, pk):
    application = _get_application(request, pk)
    if application.status != S.APPROVED:
        raise Http404
    return render(request, "applications/certificate.html", {"application": application, "decision": application.decision})


# --- sequences: report, dossier viewer, files ---------------------------------------

def _get_sequence(request, pk, seq_pk):
    application = _get_application(request, pk)
    sequence = get_object_or_404(application.sequences.select_related("uploaded_by"), pk=seq_pk)
    return application, sequence


@any_role_required
def sequence_detail(request, pk, seq_pk):
    application, sequence = _get_sequence(request, pk, seq_pk)
    run = sequence.latest_run()
    severity = request.GET.get("severity", "")
    findings = run.findings.all() if run else Finding.objects.none()
    if severity in Finding.Severity.values:
        findings = findings.filter(severity=severity)

    layers = OrderedDict((value, {"label": label, "findings": []}) for value, label in Finding.Layer.choices)
    for finding in findings:
        layers[finding.layer]["findings"].append(finding)

    tree = []
    if sequence.is_accepted and sequence.extracted_dir and sequence.extracted_dir.is_dir():
        tree = build_dossier_tree(locate_sequence_dir(sequence.extracted_dir)[0])

    return render(
        request,
        "applications/sequence_detail.html",
        {
            "application": application,
            "sequence": sequence,
            "run": run,
            "layers": layers,
            "severity": severity,
            "severities": Finding.Severity.choices,
            "tree": tree,
            "envelope_rows": _envelope_rows(application, sequence.envelope),
        },
    )


def _same_name(a: str, b: str) -> bool:
    return " ".join(a.split()).casefold() == " ".join(b.split()).casefold()


def _envelope_rows(application, envelope: dict) -> list[dict]:
    """The GCC envelope next to the application record; names that differ are flagged for the reviewer."""
    if not envelope:
        return []
    company = application.company
    names = envelope.get("invented_names", [])
    rows = [
        (_("Invented name"), ", ".join(names), not any(_same_name(n, application.product_name) for n in names)),
        (_("Applicant"), envelope.get("applicant", ""),
         not any(_same_name(envelope.get("applicant", ""), n) for n in (company.name_en, company.name_ar) if n)),
        (_("INN"), ", ".join(envelope.get("inns", [])), False),
        (_("Submission type"), envelope.get("submission_type", ""), False),
        (_("Submission unit"), envelope.get("submission_unit", ""), False),
        (_("Procedure"), envelope.get("procedure", ""), False),
        (_("Receiving agency"), f"{envelope.get('agency', '')} ({envelope.get('country', '')})", False),
        (_("Related sequences"), ", ".join(envelope.get("related_sequences", [])), False),
        (_("Description"), envelope.get("description", ""), False),
    ]
    return [{"label": label, "value": value or "—", "differs": differs} for label, value, differs in rows]


@any_role_required
def sequence_report_csv(request, pk, seq_pk):
    application, sequence = _get_sequence(request, pk, seq_pk)
    run = sequence.latest_run()
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"{application.reference_no}-{sequence.number}-validation.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # BOM so Excel opens UTF-8 (Arabic) correctly
    writer = csv.writer(response)
    writer.writerow(["Layer", "Rule", "Severity", "Criterion", "File", "Location", "Detail"])
    for finding in run.findings.all() if run else []:
        writer.writerow(
            [
                finding.get_layer_display(),
                finding.rule_code,
                finding.get_severity_display(),
                str(finding.title),
                finding.file_path,
                finding.location,
                finding.detail,
            ]
        )
    return response


@any_role_required
def sequence_package(request, pk, seq_pk):
    application, sequence = _get_sequence(request, pk, seq_pk)
    if not sequence.package or not sequence.package.storage.exists(sequence.package.name):
        raise Http404
    return FileResponse(
        sequence.package.open("rb"),
        as_attachment=True,
        filename=f"{application.reference_no}-{sequence.number}.zip",
    )


def _sequence_document(sequence, path):
    """Absolute path of one document inside an accepted sequence, or 404."""
    if not sequence.is_accepted or not sequence.extracted_dir:
        raise Http404
    seq_dir = locate_sequence_dir(sequence.extracted_dir)[0].resolve()
    target = (seq_dir / path).resolve()
    if not target.is_relative_to(seq_dir) or not target.is_file():
        raise Http404
    return target, target.relative_to(seq_dir).as_posix()


@any_role_required
def sequence_document(request, pk, seq_pk, path):
    """In-app viewer for a dossier PDF (rendered with PDF.js, so no browser plugin is needed)."""
    application, sequence = _get_sequence(request, pk, seq_pk)
    target, rel_path = _sequence_document(sequence, path)
    if target.suffix.lower() != ".pdf":
        return redirect("applications:sequence_file", application.pk, sequence.pk, rel_path)
    remember_document(request, sequence, rel_path)
    return render(
        request,
        "applications/document_viewer.html",
        {
            "application": application,
            "sequence": sequence,
            "path": rel_path,
            "filename": target.name,
            "file_url": reverse("applications:sequence_file", args=[application.pk, sequence.pk, rel_path]),
        },
    )


@any_role_required
def sequence_file(request, pk, seq_pk, path):
    """Stream one document from an accepted sequence after access checks."""
    application, sequence = _get_sequence(request, pk, seq_pk)
    target, rel_path = _sequence_document(sequence, path)
    remember_document(request, sequence, rel_path)
    suffix = target.suffix.lower()
    if suffix in INLINE_TYPES:
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    elif suffix in TEXT_TYPES:
        content_type = "text/plain; charset=utf-8"
    else:
        content_type = "application/octet-stream"
    inline = content_type != "application/octet-stream"
    response = FileResponse(open(target, "rb"), as_attachment=not inline, filename=target.name, content_type=content_type)
    response["X-Content-Type-Options"] = "nosniff"
    if suffix != ".pdf":
        # Chromium's built-in PDF viewer refuses to load in a sandboxed document and
        # falls back to downloading, so PDFs are the one type served without it.
        response["Content-Security-Policy"] = "sandbox"
    return response
