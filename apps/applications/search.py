"""Search across every dossier the reader may open: application details and the extracted document text.

On MySQL the page text has a FULLTEXT index (assistant migration 0003) and is ranked by MATCH … AGAINST;
elsewhere (SQLite in development) pages matching any term are ranked by how many terms and hits they contain.
"""
import re
from collections import OrderedDict

from django.db import connection
from django.db.models import Q
from django.db.models.expressions import RawSQL
from django.shortcuts import render
from django.utils.html import escape
from django.utils.safestring import mark_safe

from apps.accounts.permissions import any_role_required
from apps.assistant.documents import _snippet, _terms
from apps.assistant.models import DocumentText

from .models import Application, Sequence

MAX_ROWS = 400  # pages read before grouping
MAX_DOCUMENTS = 60
MAX_PAGES_PER_DOCUMENT = 5


def _highlight(text: str, terms: list[str]) -> str:
    escaped = escape(text)
    if not terms:
        return escaped
    pattern = re.compile("|".join(re.escape(escape(t)) for t in sorted(terms, key=len, reverse=True)), re.IGNORECASE)
    return mark_safe(pattern.sub(lambda m: f'<mark class="rounded bg-amber-100 px-0.5">{m.group(0)}</mark>', escaped))


def _page_rows(sequences, query: str, terms: list[str]):
    rows = DocumentText.objects.filter(sequence__in=sequences).select_related("sequence")
    if connection.vendor == "mysql":
        score = RawSQL("MATCH(assistant_documenttext.text) AGAINST (%s IN NATURAL LANGUAGE MODE)", (query,))
        return list(rows.annotate(score=score).filter(score__gt=0).order_by("-score")[:MAX_ROWS])
    condition = Q()
    for term in terms:
        condition |= Q(text__icontains=term)
    scored = []
    for row in rows.filter(condition)[: MAX_ROWS * 3]:
        lower = row.text.lower()
        scored.append(((sum(1 for t in terms if t in lower), sum(lower.count(t) for t in terms)), row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [row for _score, row in scored[:MAX_ROWS]]


def search_dossiers(user, query: str) -> dict:
    query = query.strip()[:200]
    terms = _terms(query)
    applications = Application.objects.visible_to(user).select_related("company")
    result = {"query": query, "terms": terms, "applications": [], "documents": [], "document_count": 0}
    if not query:
        return result
    result["applications"] = list(applications.filter(
        Q(reference_no__icontains=query) | Q(product_name__icontains=query) | Q(active_ingredients__icontains=query)
        | Q(company__name_en__icontains=query) | Q(company__name_ar__icontains=query) | Q(atc_code__icontains=query)
    ).order_by("-updated_at")[:20])
    if not terms:
        return result

    sequences = Sequence.objects.filter(application__in=applications, validation_status__in=Sequence.ACCEPTED_STATUSES)
    by_app = {a.pk: a for a in applications.filter(sequences__in=sequences).distinct()}
    documents = OrderedDict()
    for row in _page_rows(sequences, query, terms):
        key = (row.sequence_id, row.path)
        if key not in documents:
            if len(documents) >= MAX_DOCUMENTS:
                continue
            documents[key] = {
                "application": by_app[row.sequence.application_id],
                "sequence": row.sequence,
                "path": row.path,
                "title": row.title or row.path.rsplit("/", 1)[-1],
                "section": row.section,
                "pages": [],
            }
        pages = documents[key]["pages"]
        if len(pages) < MAX_PAGES_PER_DOCUMENT:
            pages.append({"page": row.page, "snippet": _highlight(_snippet(row.text, terms), terms)})
    for document in documents.values():
        document["pages"].sort(key=lambda p: p["page"])
    result["documents"] = list(documents.values())
    result["document_count"] = len(documents)
    return result


@any_role_required
def search(request):
    context = search_dossiers(request.user, request.GET.get("q", ""))
    if request.htmx:  # the search dialog in the header: results only, as the reader types
        return render(request, "applications/_search_results.html", context | {"in_dialog": True})
    return render(request, "applications/search.html", context)
