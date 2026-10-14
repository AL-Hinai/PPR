from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.applications.models import Application


class Notification(models.Model):
    """An in-app message about an application's status change.

    The text is rendered at display time so it follows the reader's language.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=20, choices=Application.Status.choices)
    note = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
