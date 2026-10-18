import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ApiToken(models.Model):
    """A read-only key for another Ministry system. Only its SHA-256 is stored; the key is shown once."""

    name = models.CharField(_("system"), max_length=100, help_text=_("The system that uses this key."))
    digest = models.CharField(max_length=64, unique=True, editable=False)
    prefix = models.CharField(max_length=8, editable=False)  # first characters, to recognise a key in logs
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("API key")
        verbose_name_plural = _("API keys")

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @classmethod
    def issue(cls, name: str, created_by=None) -> tuple["ApiToken", str]:
        key = "ppr_" + secrets.token_urlsafe(32)
        token = cls.objects.create(name=name, digest=_digest(key), prefix=key[:8], created_by=created_by)
        return token, key

    @classmethod
    def authenticate(cls, key: str) -> "ApiToken | None":
        token = cls.objects.filter(digest=_digest(key), is_active=True).first() if key else None
        if token:
            cls.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return token
