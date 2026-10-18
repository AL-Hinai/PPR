from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _


def assistant(request):
    """URLs and interface strings for the assistant drawer (rendered in base.html)."""
    if not getattr(request, "user", None) or not request.user.is_authenticated or not request.user.role:
        return {}
    # Cited documents open in the in-app viewer (it hands anything other than a PDF to the raw file view).
    file_url = reverse("applications:sequence_document", args=[999999, 888888, "PATH"])
    config = settings.ASSISTANT
    external = config["PROVIDER"] != "offline" and bool(config["API_KEY"])
    return {
        # Shown in the drawer: questions and dossier passages leave the server for this host.
        "assistant_external_host": urlparse(config["BASE_URL"]).hostname if external else "",
        "assistant_config": {
            "urls": {
                "session": reverse("assistant:session"),
                "ask": reverse("assistant:ask"),
                "new": reverse("assistant:new"),
                "file": file_url,
            },
            "t": {
                "you": _("You"),
                "name": _("Assistant"),
                "working": _("Searching the dossier…"),
                "steps": _("Steps taken: %s"),
                "open_doc": _("Open the cited page"),
                "source": {
                    "page": _("Reading"),
                    "pinned": _("Pinned"),
                    "recent": _("Recently opened"),
                },
                "stopped": {
                    "deadline": _("The assistant ran out of time. Ask a narrower question."),
                    "max_steps": _("The assistant stopped after too many steps. Ask a narrower question."),
                },
                "unavailable": _("The language model could not be reached. Try again in a moment."),
                "failed": _("The question could not be sent."),
                "suggest_doc": [_("Summarise this document"), _("What are the key values in this document?")],
                "suggest_app": [
                    _("Summarise this dossier"),
                    _("What is the proposed shelf life and storage condition?"),
                    _("Are there validation findings I should know about?"),
                ],
                "suggest_none": [_("Which applications can I see?")],
            },
        }
    }
