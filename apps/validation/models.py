from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class ValidationJob(models.Model):
    """A queued validation, run by ``manage.py run_validation_worker`` (VALIDATION_MODE = "queue")."""

    class Kind(models.TextChoices):
        SUBMIT = "SUBMIT", _("Submission")
        INFO_RESPONSE = "INFO_RESPONSE", _("Response to questions")

    class Status(models.TextChoices):
        QUEUED = "QUEUED", _("Queued")
        RUNNING = "RUNNING", _("Running")
        DONE = "DONE", _("Done")
        FAILED = "FAILED", _("Failed")

    ACTIVE = (Status.QUEUED, Status.RUNNING)

    sequence = models.ForeignKey("applications.Sequence", on_delete=models.CASCADE, related_name="jobs")
    kind = models.CharField(max_length=15, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    # The company user who submitted; the worker acts for them where the workflow needs a person.
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    note = models.TextField(blank=True)  # the applicant's note on a response to questions
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("validation job")
        verbose_name_plural = _("validation jobs")

    def __str__(self):
        return f"{self.get_kind_display()} job {self.pk} for {self.sequence} ({self.status})"


class ValidationRun(models.Model):
    """One execution of the eCTD validator against one sequence."""

    sequence = models.ForeignKey(
        "applications.Sequence", on_delete=models.CASCADE, related_name="validation_runs"
    )
    validator_version = models.CharField(max_length=20)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    info_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = _("validation run")
        verbose_name_plural = _("validation runs")

    def __str__(self):
        return f"Run {self.pk} for {self.sequence}"

    @property
    def duration(self):
        if self.finished_at:
            return self.finished_at - self.started_at
        return None


class Finding(models.Model):
    class Layer(models.TextChoices):
        SCHEMA = "SCHEMA", _("XML schema validation")
        BUSINESS = "BUSINESS", _("Business rule checks")
        FILE = "FILE", _("File compliance inspection")

    class Severity(models.TextChoices):
        ERROR = "ERROR", _("Error")
        WARNING = "WARNING", _("Warning")
        INFO = "INFO", _("Info")

    run = models.ForeignKey(ValidationRun, on_delete=models.CASCADE, related_name="findings")
    layer = models.CharField(max_length=10, choices=Layer.choices)
    rule_code = models.CharField(max_length=10)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    file_path = models.CharField(max_length=500, blank=True)
    location = models.CharField(max_length=100, blank=True)
    detail = models.TextField(blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = _("finding")
        verbose_name_plural = _("findings")

    def __str__(self):
        return f"{self.rule_code} {self.severity}: {self.detail[:60]}"

    @property
    def title(self):
        from .rules import RULES_BY_CODE

        rule = RULES_BY_CODE.get(self.rule_code)
        return rule.title if rule else self.rule_code
