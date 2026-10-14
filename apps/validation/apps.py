import logging

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ValidationConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.validation"
    verbose_name = _("eCTD validation")

    def ready(self):
        # pypdf is chatty about harmless structural quirks in non-strict mode.
        logging.getLogger("pypdf").setLevel(logging.ERROR)
