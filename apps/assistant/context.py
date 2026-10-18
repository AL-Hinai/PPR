"""Where the reader is: which medicine, which sequence, which document.

Roaa derived the assistant's context from the URL alone. PPR does the same — the
drawer sends ``location.pathname`` and the server resolves it against its own URL
conf — plus one thing the URL cannot say: dossier documents open in a new tab as
a raw PDF, where there is no drawer. So the document view records the last
document opened in the session, and the drawer picks it up when the reader comes
back to the application.

Every lookup goes through ``Application.objects.visible_to`` — a URL naming an
application the reader may not see resolves to no context at all.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

from django.urls import Resolver404, resolve
from django.utils.translation import gettext as _

from apps.applications.models import Application, Sequence
from apps.validation.ectd import locate_sequence_dir

SESSION_KEY = "assistant_recent"
# A document opened longer ago than this is no longer "what the reader is looking at".
RECENT_SECONDS = 3 * 60 * 60


@dataclass
class PageContext:
    application: Application | None = None
    sequence: Sequence | None = None
    document_path: str = ""
    # How the document was found: "page" (its URL), "pinned" (the reader chose it) or "recent" (opened in another tab).
    document_source: str = ""
    page: str = ""  # url name, e.g. "applications:detail"
    tab: str = ""

    @property
    def document_title(self) -> str:
        return self.document_path.rsplit("/", 1)[-1] if self.document_path else ""

    def label(self) -> str:
        if not self.application:
            return ""
        parts = [f"{self.application.product_name} ({self.application.reference_no})"]
        if self.sequence:
            parts.append(_("sequence %(number)s") % {"number": self.sequence.number})
        if self.document_path:
            parts.append(self.document_title)
        return " · ".join(parts)

    def as_json(self) -> dict:
        application = self.application
        return {
            "label": self.label(),
            "application": application.pk if application else None,
            "product": application.product_name if application else "",
            "reference": application.reference_no if application else "",
            "sequence": self.sequence.number if self.sequence else "",
            "sequence_id": self.sequence.pk if self.sequence else None,
            "document": self.document_path,
            "document_title": self.document_title,
            "document_source": self.document_source,
        }


def _document_exists(sequence: Sequence, path: str) -> bool:
    if not sequence.is_accepted or not sequence.extracted_dir or not sequence.extracted_dir.is_dir():
        return False
    seq_dir = locate_sequence_dir(sequence.extracted_dir)[0].resolve()
    target = (seq_dir / path).resolve()
    return target.is_relative_to(seq_dir) and target.is_file()


def resolve_context(request, page_url: str = "", pinned: dict | None = None) -> PageContext:
    user = request.user
    visible = Application.objects.visible_to(user)
    ctx = PageContext()

    path = urlsplit(page_url or "").path or "/"
    try:
        match = resolve(path)
    except Resolver404:
        match = None
    if match:
        ctx.page = match.view_name
        ctx.tab = dict(_query(page_url)).get("tab", "")
        if match.namespace == "applications" and "pk" in match.kwargs:
            ctx.application = visible.filter(pk=match.kwargs["pk"]).first()
            if ctx.application and "seq_pk" in match.kwargs:
                ctx.sequence = ctx.application.sequences.filter(pk=match.kwargs["seq_pk"]).first()
                if ctx.sequence and match.kwargs.get("path") and _document_exists(ctx.sequence, match.kwargs["path"]):
                    ctx.document_path = match.kwargs["path"]
                    ctx.document_source = "page"

    # The reader pinned a document from the dossier viewer ("Ask about this document").
    pinned_id = str((pinned or {}).get("sequence_id") or "")
    if pinned and not ctx.document_path and pinned_id.isdigit():
        sequence = Sequence.objects.filter(
            pk=int(pinned_id), application__in=visible
        ).select_related("application").first()
        doc = str(pinned.get("path") or "")
        if sequence and doc and _document_exists(sequence, doc):
            if ctx.application is None or ctx.application.pk == sequence.application_id:
                ctx.application, ctx.sequence = sequence.application, sequence
                ctx.document_path, ctx.document_source = doc, "pinned"

    # The document opened most recently in another tab, if it belongs to the medicine on screen
    # (or the reader is on a page that names no medicine).
    recent = request.session.get(SESSION_KEY) or {}
    if not ctx.document_path and recent and time.time() - recent.get("at", 0) < RECENT_SECONDS:
        if ctx.application is None or ctx.application.pk == recent.get("application"):
            application = ctx.application or visible.filter(pk=recent.get("application")).first()
            if application:
                ctx.application = application
                sequence = application.sequences.filter(pk=recent.get("sequence")).first()
                doc = recent.get("path") or ""
                if sequence and doc and (ctx.sequence is None or ctx.sequence.pk == sequence.pk):
                    if _document_exists(sequence, doc):
                        ctx.sequence = sequence
                        ctx.document_path, ctx.document_source = doc, "recent"
    return ctx


def _query(page_url: str):
    return parse_qsl(urlsplit(page_url or "").query)[:8]


def remember_application(request, application) -> None:
    """Called whenever an application page is shown: the medicine the reader is working on."""
    recent = request.session.get(SESSION_KEY) or {}
    if recent.get("application") != application.pk:
        request.session[SESSION_KEY] = {"application": application.pk, "at": time.time()}


def remember_document(request, sequence, path: str) -> None:
    """Called when a dossier document is opened (it opens in a new tab, away from the drawer)."""
    request.session[SESSION_KEY] = {
        "application": sequence.application_id,
        "sequence": sequence.pk,
        "path": path,
        "at": time.time(),
    }
