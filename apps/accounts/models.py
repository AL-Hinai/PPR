from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


class CtdSection(models.TextChoices):
    """The CTD modules a review is split into. Reviewers specialise in some of them."""

    M1 = "M1", _("Module 1 – Administrative & labelling")
    M2 = "M2", _("Module 2 – Summaries")
    M3 = "M3", _("Module 3 – Quality")
    M4 = "M4", _("Module 4 – Non-clinical")
    M5 = "M5", _("Module 5 – Clinical")


class User(AbstractUser):
    class Role(models.TextChoices):
        COMPANY = "COMPANY", _("Company applicant")
        REVIEWER = "REVIEWER", _("Reviewer")
        HOD = "HOD", _("Head of Department")

    role = models.CharField(_("role"), max_length=20, choices=Role.choices, default=Role.COMPANY)
    company = models.ForeignKey(
        "companies.Company",
        verbose_name=_("company"),
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="users",
    )
    preferred_language = models.CharField(
        _("preferred language"), max_length=5, choices=settings.LANGUAGES, default="en"
    )
    # Reviewers only: the CTD modules (CtdSection values) this reviewer is qualified to assess.
    # Set by the Head of Department only (accounts:reviewers); reviewers work within them.
    specialties = models.JSONField(_("review specialties"), default=list, blank=True)
    specialties_updated_by = models.ForeignKey(
        "self", verbose_name=_("specialties set by"), on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    specialties_updated_at = models.DateTimeField(_("specialties set at"), null=True, blank=True)
    # At most one reviewer: leads every review team assembled automatically that they are part of.
    default_lead = models.BooleanField(_("default lead reviewer"), default=False)

    def clean(self):
        super().clean()
        if self.role == self.Role.COMPANY and not self.company_id and not self.is_superuser:
            raise ValidationError({"company": _("Company applicants must belong to a company.")})
        if self.role != self.Role.COMPANY and self.company_id:
            raise ValidationError({"company": _("Only company applicants can belong to a company.")})
        if self.role != self.Role.REVIEWER and self.specialties:
            raise ValidationError({"specialties": _("Only reviewers have review specialties.")})

    @property
    def is_company(self):
        return self.role == self.Role.COMPANY and self.company_id is not None

    @property
    def is_reviewer(self):
        return self.role == self.Role.REVIEWER

    @property
    def is_hod(self):
        return self.role == self.Role.HOD

    def can_review(self, section) -> bool:
        return self.is_reviewer and self.is_active and section in (self.specialties or [])

    def get_specialties_display(self) -> str:
        return ", ".join(value for value in CtdSection.values if value in (self.specialties or []))

    @property
    def display_name(self):
        return self.get_full_name() or self.username
