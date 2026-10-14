from django.db import models
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _


class Company(models.Model):
    """A pharmaceutical company (marketing authorisation applicant)."""

    name_en = models.CharField(_("name (English)"), max_length=200)
    name_ar = models.CharField(_("name (Arabic)"), max_length=200, blank=True)
    registration_no = models.CharField(_("commercial registration no."), max_length=50, unique=True)
    license_no = models.CharField(_("pharmaceutical license no."), max_length=50, blank=True)
    country = models.CharField(_("country"), max_length=100, default="Oman")
    address = models.TextField(_("address"), blank=True)
    contact_email = models.EmailField(_("contact email"), blank=True)
    contact_phone = models.CharField(_("contact phone"), max_length=30, blank=True)
    is_verified = models.BooleanField(_("verified"), default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name_en"]
        verbose_name = _("company")
        verbose_name_plural = _("companies")

    def __str__(self):
        return self.name

    @property
    def name(self):
        if get_language() == "ar" and self.name_ar:
            return self.name_ar
        return self.name_en
