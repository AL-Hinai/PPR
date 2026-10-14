from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _


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

    def clean(self):
        super().clean()
        if self.role == self.Role.COMPANY and not self.company_id and not self.is_superuser:
            raise ValidationError({"company": _("Company applicants must belong to a company.")})
        if self.role != self.Role.COMPANY and self.company_id:
            raise ValidationError({"company": _("Only company applicants can belong to a company.")})

    @property
    def is_company(self):
        return self.role == self.Role.COMPANY and self.company_id is not None

    @property
    def is_reviewer(self):
        return self.role == self.Role.REVIEWER

    @property
    def is_hod(self):
        return self.role == self.Role.HOD

    @property
    def display_name(self):
        return self.get_full_name() or self.username
