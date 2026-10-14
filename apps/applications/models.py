import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class ApplicationQuerySet(models.QuerySet):
    def visible_to(self, user):
        """The single place that decides which applications a user may see."""
        if not user.is_authenticated:
            return self.none()
        role = user.role
        if role == user.Role.COMPANY and user.company_id:
            return self.filter(company_id=user.company_id)
        if role == user.Role.REVIEWER:
            return self.filter(assigned_reviewer=user)
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
    assigned_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("assigned reviewer"),
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

    def open_info_request(self):
        return self.info_requests.filter(status=InfoRequest.Status.OPEN).first()

    @property
    def is_closed(self):
        return self.status in (self.Status.APPROVED, self.Status.REJECTED)


def sequence_upload_to(instance, filename):
    return f"packages/{instance.application_id}/{instance.number}-{uuid.uuid4().hex}.zip"


class Sequence(models.Model):
    """One eCTD sequence (0000, 0001, …) uploaded as a zip package."""

    class ValidationStatus(models.TextChoices):
        PENDING = "PENDING", _("Not yet validated")
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

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("status change")
        verbose_name_plural = _("status history")


class Review(models.Model):
    """A reviewer's assessment of one CTD module."""

    class Section(models.TextChoices):
        M1 = "M1", _("Module 1 – Administrative & labelling")
        M2 = "M2", _("Module 2 – Summaries")
        M3 = "M3", _("Module 3 – Quality")
        M4 = "M4", _("Module 4 – Non-clinical")
        M5 = "M5", _("Module 5 – Clinical")

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
