import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import CtdSection


class ApplicationQuerySet(models.QuerySet):
    def visible_to(self, user):
        """The single place that decides which applications a user may see."""
        if not user.is_authenticated:
            return self.none()
        role = user.role
        if role == user.Role.COMPANY and user.company_id:
            return self.filter(company_id=user.company_id)
        if role == user.Role.REVIEWER:
            # The lead reviewer and every specialist assigned to one of its modules.
            assigned = ReviewAssignment.objects.filter(reviewer=user).values("application")
            return self.filter(Q(assigned_reviewer=user) | Q(pk__in=assigned))
        if role == user.Role.HOD:
            return self.exclude(status=Application.Status.DRAFT)
        return self.none()


class Application(models.Model):
    """A marketing authorisation application for one medicinal product."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        SUBMITTED = "SUBMITTED", _("Submitted")
        VALIDATING = "VALIDATING", _("Technical validation")
        VALIDATION_FAILED = "VALIDATION_FAILED", _("Validation failed")
        VALIDATED = "VALIDATED", _("Validated – awaiting assignment")
        UNDER_REVIEW = "UNDER_REVIEW", _("Under review")
        INFO_REQUESTED = "INFO_REQUESTED", _("Information requested")
        REVIEW_COMPLETE = "REVIEW_COMPLETE", _("Review complete – awaiting decision")
        APPROVED = "APPROVED", _("Approved")
        REJECTED = "REJECTED", _("Rejected")

    class Type(models.TextChoices):
        NEW_DRUG = "NEW_DRUG", _("New drug (innovator)")
        GENERIC = "GENERIC", _("Generic")
        VARIATION = "VARIATION", _("Variation")
        RENEWAL = "RENEWAL", _("Renewal")

    class Recommendation(models.TextChoices):
        APPROVE = "APPROVE", _("Approve")
        REJECT = "REJECT", _("Reject")

    reference_no = models.CharField(_("reference no."), max_length=30, unique=True, null=True, blank=True)
    company = models.ForeignKey(
        "companies.Company", verbose_name=_("company"), on_delete=models.PROTECT, related_name="applications"
    )
    application_type = models.CharField(_("application type"), max_length=20, choices=Type.choices)
    product_name = models.CharField(_("product name"), max_length=200)
    active_ingredients = models.CharField(_("active ingredient(s)"), max_length=300)
    dosage_form = models.CharField(_("dosage form"), max_length=100)
    strength = models.CharField(_("strength"), max_length=100)
    route = models.CharField(_("route of administration"), max_length=100)
    atc_code = models.CharField(_("ATC code"), max_length=10, blank=True)
    status = models.CharField(_("status"), max_length=20, choices=Status.choices, default=Status.DRAFT)
    # The lead reviewer: coordinates the module reviewers, sends questions and the recommendation.
    assigned_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("lead reviewer"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assigned_applications",
    )
    recommendation = models.CharField(
        _("reviewer recommendation"), max_length=10, choices=Recommendation.choices, blank=True
    )
    recommendation_note = models.TextField(_("recommendation summary"), blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_applications"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(_("submitted at"), null=True, blank=True)

    objects = ApplicationQuerySet.as_manager()

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = _("application")
        verbose_name_plural = _("applications")

    def __str__(self):
        return f"{self.reference_no or _('(draft)')} – {self.product_name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.reference_no:
            self.reference_no = f"MA-{self.created_at:%Y}-{self.pk:05d}"
            super().save(update_fields=["reference_no"])

    def get_absolute_url(self):
        return reverse("applications:detail", args=[self.pk])

    # --- eCTD lifecycle helpers -------------------------------------------
    def accepted_sequences(self):
        return self.sequences.filter(validation_status__in=Sequence.ACCEPTED_STATUSES).order_by("number")

    def next_sequence_number(self):
        return f"{self.accepted_sequences().count():04d}"

    def pending_sequence(self):
        return self.sequences.filter(validation_status=Sequence.ValidationStatus.PENDING).order_by("-uploaded_at").first()

    def latest_sequence(self):
        return self.sequences.order_by("-uploaded_at").first()

    def validation_in_progress(self):
        """A sequence is waiting for (or being checked by) the background validator."""
        return self.sequences.filter(validation_status=Sequence.ValidationStatus.QUEUED).exists()

    def open_info_request(self):
        return self.info_requests.filter(status=InfoRequest.Status.OPEN).first()

    # --- review team ---------------------------------------------------------
    def required_sections(self) -> list[str]:
        """CTD modules that must be assessed: those required in the dossier for this application type."""
        from apps.validation.rules.business import REQUIRED_MODULES

        return [m.upper() for m in REQUIRED_MODULES.get(self.application_type, ["m1"])]

    def sections_for(self, user) -> list[str]:
        if not user.is_authenticated:
            return []
        return list(self.assignments.filter(reviewer=user).order_by("section").values_list("section", flat=True))

    def review_progress(self) -> list[dict]:
        """One row per assigned module: who assesses it, the latest assessment, and whether one is still owed.

        A module the applicant was questioned about needs a fresh assessment once the answer is in:
        an assessment older than that answer is shown but no longer counts (``reassess``).
        """
        reviews = {}
        for review in self.reviews.order_by("created_at"):
            reviews[(review.section, review.reviewer_id)] = review
        answered = {}  # module -> when the applicant last answered questions about it
        for request in self.info_requests.filter(status=InfoRequest.Status.ANSWERED, answered_at__isnull=False):
            for section in request.sections or []:
                answered[section] = max(answered.get(section, request.answered_at), request.answered_at)
        rows = []
        for a in self.assignments.select_related("reviewer").order_by("section"):
            review = reviews.get((a.section, a.reviewer_id))
            reassess = review is not None and a.section in answered and review.created_at < answered[a.section]
            rows.append({"assignment": a, "review": review, "reassess": reassess, "pending": review is None or reassess})
        return rows

    def missing_sections(self) -> list[str]:
        """Modules still owed an assessment: never assessed, or questioned and answered since."""
        return [row["assignment"].section for row in self.review_progress() if row["pending"]]

    @property
    def is_closed(self):
        return self.status in (self.Status.APPROVED, self.Status.REJECTED)


def sequence_upload_to(instance, filename):
    return f"packages/{instance.application_id}/{instance.number}-{uuid.uuid4().hex}.zip"


class Sequence(models.Model):
    """One eCTD sequence (0000, 0001, …) uploaded as a zip package."""

    class ValidationStatus(models.TextChoices):
        PENDING = "PENDING", _("Not yet validated")
        QUEUED = "QUEUED", _("Validation in progress")
        PASSED = "PASSED", _("Passed")
        PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS", _("Passed with warnings")
        FAILED = "FAILED", _("Failed")

    ACCEPTED_STATUSES = (ValidationStatus.PASSED, ValidationStatus.PASSED_WITH_WARNINGS)

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="sequences")
    number = models.CharField(_("sequence"), max_length=4)
    package = models.FileField(_("eCTD package (zip)"), upload_to=sequence_upload_to, max_length=255)
    original_filename = models.CharField(max_length=255)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    extracted_path = models.CharField(max_length=255, blank=True)
    validation_status = models.CharField(
        _("validation status"), max_length=25, choices=ValidationStatus.choices, default=ValidationStatus.PENDING
    )
    description = models.CharField(_("description"), max_length=255, blank=True)
    # Submission envelope from the regional Module 1 XML, captured at validation.
    envelope = models.JSONField(_("envelope"), default=dict, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = _("sequence")
        verbose_name_plural = _("sequences")

    def __str__(self):
        return f"{self.application.reference_no} / {self.number}"

    @property
    def is_accepted(self):
        return self.validation_status in self.ACCEPTED_STATUSES

    @property
    def extracted_dir(self) -> Path | None:
        if not self.extracted_path:
            return None
        return Path(settings.MEDIA_ROOT) / self.extracted_path

    def latest_run(self):
        return self.validation_runs.order_by("-started_at").first()


class StatusHistory(models.Model):
    """Audit trail: every status change, who made it and why."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=20, choices=Application.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Application.Status.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Notes an applicant may read besides their own: validation results, the questions sent to
    # them and the decision. Assignment notes, the lead's summary and HOD returns stay internal.
    APPLICANT_NOTE_STATUSES = {
        Application.Status.VALIDATED, Application.Status.VALIDATION_FAILED,
        Application.Status.INFO_REQUESTED, Application.Status.APPROVED, Application.Status.REJECTED,
    }

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("status change")
        verbose_name_plural = _("status history")

    @property
    def is_team_change(self) -> bool:
        """A change to the review team: recorded without a status change, never shown to the applicant."""
        return self.from_status == self.to_status

    def note_for(self, user) -> str:
        if not user.is_company:
            return self.note
        own = self.actor is not None and self.actor.is_company
        return self.note if own or self.to_status in self.APPLICANT_NOTE_STATUSES else ""


class ReviewAssignment(models.Model):
    """One CTD module of one application, given to a reviewer specialised in it (automatically or by the HOD)."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="assignments")
    section = models.CharField(_("section"), max_length=5, choices=CtdSection.choices)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name=_("reviewer"), on_delete=models.PROTECT, related_name="review_assignments"
    )
    # Empty when the team was assembled automatically from reviewer specialties.
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["section"]
        constraints = [models.UniqueConstraint(fields=["application", "section"], name="one_reviewer_per_section")]
        verbose_name = _("module assignment")
        verbose_name_plural = _("module assignments")

    def __str__(self):
        return f"{self.application.reference_no} {self.section} → {self.reviewer}"


class Review(models.Model):
    """A reviewer's assessment of one CTD module."""

    Section = CtdSection

    class Assessment(models.TextChoices):
        ACCEPTABLE = "ACCEPTABLE", _("Acceptable")
        MINOR = "MINOR", _("Minor issues")
        MAJOR = "MAJOR", _("Major issues")

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews")
    section = models.CharField(_("section"), max_length=5, choices=Section.choices)
    assessment = models.CharField(_("assessment"), max_length=12, choices=Assessment.choices)
    comments = models.TextField(_("comments"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["section", "-created_at"]
        verbose_name = _("review")
        verbose_name_plural = _("reviews")


class InfoRequest(models.Model):
    """Questions sent to the company. The answer is a new eCTD sequence (clock stop)."""

    class Status(models.TextChoices):
        OPEN = "OPEN", _("Open")
        ANSWERED = "ANSWERED", _("Answered")

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="info_requests")
    raised_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    questions = models.TextField(_("questions"))
    # The CTD modules the questions concern; their reviewers re-assess them once the answer is in.
    sections = models.JSONField(_("modules concerned"), default=list, blank=True)
    due_date = models.DateField(_("response due"), null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    response_note = models.TextField(_("response note"), blank=True)
    response_sequence = models.ForeignKey(
        Sequence, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("information request")
        verbose_name_plural = _("information requests")


class Decision(models.Model):
    """The HOD's final decision."""

    class Outcome(models.TextChoices):
        APPROVED = "APPROVED", _("Approved")
        REJECTED = "REJECTED", _("Rejected")

    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="decision")
    hod = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    outcome = models.CharField(_("outcome"), max_length=10, choices=Outcome.choices)
    justification = models.TextField(_("justification"))
    approval_no = models.CharField(_("approval no."), max_length=30, unique=True, null=True, blank=True)
    valid_until = models.DateField(_("valid until"), null=True, blank=True)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("decision")
        verbose_name_plural = _("decisions")


class DocumentNote(models.Model):
    """A reviewer's note on one page of a dossier document. Internal: applicants never see notes.

    The original PDF is never changed; the note stores the page and, optionally, the text it is about.
    """

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="notes")
    sequence = models.ForeignKey(Sequence, on_delete=models.CASCADE, related_name="notes")
    path = models.CharField(_("document"), max_length=500)
    page = models.PositiveIntegerField(_("page"), default=1)
    quote = models.TextField(_("quoted text"), blank=True)
    body = models.TextField(_("note"))
    section = models.CharField(_("module"), max_length=5, blank=True)  # M1–M5, from the document's folder
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="document_notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["section", "path", "page", "created_at"]
        verbose_name = _("document note")
        verbose_name_plural = _("document notes")

    def __str__(self):
        return f"{self.path} p.{self.page}: {self.body[:40]}"

    @staticmethod
    def section_for(path: str) -> str:
        """'m3/32-body-data/…' -> 'M3'; '' when the path is outside the CTD modules."""
        head = path.split("/", 1)[0].lower()
        return head.upper() if head in ("m1", "m2", "m3", "m4", "m5") else ""
