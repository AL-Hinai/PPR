"""Reviewer notes on dossier pages: added from the PDF viewer, collected into the assessment.

Notes are internal to the Pharmacy Department: the review team and the HOD see them, only the author changes
them, and applicants never see them (the views require a reviewer or HOD who can see the application).
"""
from collections import OrderedDict

from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from apps.accounts.models import CtdSection
from apps.accounts.permissions import staff_required

from .models import DocumentNote
from .views import _get_application, _get_sequence, _sequence_document

MAX_NOTE = 5000
MAX_QUOTE = 1000


def _notes_for(application, sequence, path):
    return application.notes.filter(sequence=sequence, path=path).select_related("author").order_by("page", "created_at")


def _list(request, application, sequence, path, status=200, error=""):
    return render(request, "applications/_notes_list.html", {
        "application": application,
        "sequence": sequence,
        "path": path,
        "notes": _notes_for(application, sequence, path),
        "error": error,
    }, status=status)


@staff_required
def note_list(request, pk, seq_pk):
    """GET: the notes on one document (htmx partial). POST: add a note on a page."""
    application, sequence = _get_sequence(request, pk, seq_pk)
    source = request.POST if request.method == "POST" else request.GET
    _, path = _sequence_document(sequence, source.get("path", ""))
    if request.method != "POST":
        return _list(request, application, sequence, path)
    body = request.POST.get("body", "").strip()[:MAX_NOTE]
    try:
        page = max(1, int(request.POST.get("page", "1")))
    except ValueError:
        page = 1
    if not body:
        return _list(request, application, sequence, path, status=400, error="empty")
    DocumentNote.objects.create(
        application=application, sequence=sequence, path=path, page=page, body=body,
        quote=request.POST.get("quote", "").strip()[:MAX_QUOTE], section=DocumentNote.section_for(path),
        author=request.user,
    )
    return _list(request, application, sequence, path)


def _own_note(request, pk, note_pk):
    application = _get_application(request, pk)
    note = get_object_or_404(application.notes.select_related("sequence"), pk=note_pk)
    if note.author_id != request.user.pk:
        raise PermissionDenied
    return application, note


@staff_required
@require_POST
def note_edit(request, pk, note_pk):
    application, note = _own_note(request, pk, note_pk)
    body = request.POST.get("body", "").strip()[:MAX_NOTE]
    if body:
        note.body = body
        note.save(update_fields=["body", "updated_at"])
    return _list(request, application, note.sequence, note.path)


@staff_required
@require_POST
def note_delete(request, pk, note_pk):
    application, note = _own_note(request, pk, note_pk)
    sequence, path = note.sequence, note.path
    note.delete()
    return _list(request, application, sequence, path)


def _grouped(notes):
    """[(module label, [(document path, sequence, [notes])])], in CTD order."""
    labels = dict(CtdSection.choices)
    groups = OrderedDict()
    for note in notes:
        documents = groups.setdefault(note.section, OrderedDict())
        documents.setdefault((note.sequence.number, note.path), []).append(note)
    return [
        (labels.get(section, section or "—"),
         [(path, number, items) for (number, path), items in documents.items()])
        for section, documents in groups.items()
    ]


@staff_required
def notes_print(request, pk):
    """Every note on the application, by module, document and page, for the assessment report."""
    application = _get_application(request, pk)
    notes = application.notes.select_related("sequence", "author").order_by(
        "section", "sequence__number", "path", "page", "created_at"
    )
    if request.GET.get("mine"):
        notes = notes.filter(author=request.user)
    return render(request, "applications/notes_print.html", {
        "application": application,
        "groups": _grouped(notes),
        "count": len(notes),
        "mine": bool(request.GET.get("mine")),
    })


@staff_required
def my_notes_text(request, pk):
    """The reader's own notes on one module as plain text, to paste into their module assessment."""
    application = _get_application(request, pk)
    notes = application.notes.filter(author=request.user, section=request.GET.get("section", "")).select_related(
        "sequence"
    ).order_by("sequence__number", "path", "page", "created_at")
    lines = []
    for note in notes:
        lines.append(f"- {note.sequence.number}/{note.path}, p. {note.page}: {note.body}")
        if note.quote:
            lines.append(f'  "{note.quote}"')
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")
