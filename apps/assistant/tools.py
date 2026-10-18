"""What the assistant may do: read, never write.

Every tool is scoped by ``Application.objects.visible_to(user)`` — the same rule
as every page — so a reviewer's assistant sees only their assigned dossiers and a
company's only its own. When a tool is called without ``application_id`` it acts
on the medicine the reader is looking at.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from django.db.models import Q

from apps.applications.models import Application
from apps.validation.models import Finding

from . import documents
from .context import PageContext
from .llm import ToolSpec

MAX_RESULT_CHARS = 16_000
READ_PAGES = 3
MAX_READ_PAGES = 8

_APP_ID = {"type": "integer", "description": "Application id. Omit to use the application the reader is viewing."}
_SEQUENCE = {"type": "string", "description": "Sequence number such as 0000 or 0001. Omit for all accepted sequences."}

SPECS = (
    ToolSpec(
        "get_application_overview",
        "Product details, status, sequences with validation results, reviews, information requests and decision "
        "for one marketing authorisation application (a medicine).",
        {"type": "object", "properties": {"application_id": _APP_ID}},
    ),
    ToolSpec(
        "list_documents",
        "The documents of the eCTD dossier with their CTD section, path and lifecycle operation.",
        {
            "type": "object",
            "properties": {
                "application_id": _APP_ID,
                "sequence": _SEQUENCE,
                "module": {"type": "string", "description": "Optional CTD module filter: m1, m2, m3, m4 or m5."},
            },
        },
    ),
    ToolSpec(
        "search_documents",
        "Full-text search across the dossier documents (PDF text). Returns matching pages with snippets. "
        "Use the terms the documents would use (usually English), e.g. 'dissolution', 'shelf life', 'impurity'.",
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords to look for."},
                "application_id": _APP_ID,
                "sequence": _SEQUENCE,
            },
            "required": ["query"],
        },
    ),
    ToolSpec(
        "read_document",
        "Read the text of a dossier document, a few pages at a time.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Document path inside the sequence, from list_documents or search_documents."},
                "sequence": {"type": "string", "description": "Sequence number of the document. Omit for the latest that has it."},
                "application_id": _APP_ID,
                "start_page": {"type": "integer", "description": "First page to read (1-based). Default 1."},
                "pages": {"type": "integer", "description": f"How many pages (max {MAX_READ_PAGES}). Default {READ_PAGES}."},
            },
            "required": ["path"],
        },
    ),
    ToolSpec(
        "get_validation_report",
        "eCTD technical validation findings (errors and warnings) for a sequence.",
        {
            "type": "object",
            "properties": {
                "application_id": _APP_ID,
                "sequence": {"type": "string", "description": "Sequence number. Omit for the latest uploaded."},
            },
        },
    ),
    ToolSpec(
        "find_applications",
        "Find applications (medicines) the reader can access, by product name, active ingredient or reference number. "
        "Empty query lists the most recent.",
        {"type": "object", "properties": {"query": {"type": "string"}}},
    ),
)


@dataclass
class Outcome:
    payload: dict
    summary: str
    ok: bool = True


class ToolError(Exception):
    pass


class ToolBox:
    specs = SPECS

    def __init__(self, user, context: PageContext):
        self.user = user
        self.context = context
        self.visible = Application.objects.visible_to(user)

    def invoke(self, name: str, arguments: dict) -> Outcome:
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return Outcome({"error": f"Unknown tool {name}"}, f"unknown tool {name}", ok=False)
        try:
            outcome = handler(**{k: v for k, v in (arguments or {}).items() if v not in (None, "")})
        except ToolError as exc:
            return Outcome({"error": str(exc)}, str(exc), ok=False)
        except (TypeError, ValueError) as exc:  # e.g. a page number the model sent as text
            return Outcome({"error": f"Bad arguments: {exc}"}, "bad arguments", ok=False)
        text = json.dumps(outcome.payload, ensure_ascii=False, default=str)
        if len(text) > MAX_RESULT_CHARS:
            outcome.payload = {"truncated": True, "partial": text[:MAX_RESULT_CHARS]}
        return outcome

    # ------------------------------------------------------------------ helpers

    def _application(self, application_id=None) -> Application:
        if application_id is None:
            if self.context.application is None:
                raise ToolError("No application is open. Ask which medicine, or use find_applications.")
            return self.context.application
        application = self.visible.filter(pk=application_id).first()
        if application is None:
            raise ToolError(f"Application {application_id} does not exist or is not accessible to this reader.")
        return application

    def _sequences(self, application, number=None):
        sequences = application.accepted_sequences()
        if number:
            sequences = sequences.filter(number=str(number).zfill(4))
            if not sequences.exists():
                raise ToolError(f"Sequence {number} is not an accepted sequence of {application.reference_no}.")
        return list(sequences)

    # -------------------------------------------------------------------- tools

    def _tool_get_application_overview(self, application_id=None) -> Outcome:
        a = self._application(application_id)
        decision = getattr(a, "decision", None)
        payload = {
            "id": a.pk,
            "reference_no": a.reference_no,
            "product_name": a.product_name,
            "active_ingredients": a.active_ingredients,
            "dosage_form": a.dosage_form,
            "strength": a.strength,
            "route": a.route,
            "atc_code": a.atc_code,
            "application_type": a.get_application_type_display(),
            "company": str(a.company),
            "status": a.get_status_display(),
            "assigned_reviewer": a.assigned_reviewer.display_name if a.assigned_reviewer else None,
            "submitted_at": a.submitted_at,
            "recommendation": a.get_recommendation_display() if a.recommendation else None,
            "recommendation_note": a.recommendation_note or None,
            "sequences": [
                {
                    "number": s.number,
                    "validation": s.get_validation_status_display(),
                    "description": s.description,
                    "uploaded_at": s.uploaded_at,
                }
                for s in a.sequences.order_by("number", "uploaded_at")
            ],
            "reviews": [
                {"section": r.get_section_display(), "assessment": r.get_assessment_display(), "comments": r.comments,
                 "reviewer": r.reviewer.display_name}
                for r in a.reviews.select_related("reviewer")
            ],
            "information_requests": [
                {"questions": i.questions, "status": i.get_status_display(), "due": i.due_date,
                 "response_note": i.response_note}
                for i in a.info_requests.all()
            ],
            "decision": {
                "outcome": decision.get_outcome_display(),
                "justification": decision.justification,
                "approval_no": decision.approval_no,
                "valid_until": decision.valid_until,
            } if decision else None,
        }
        if self.user.is_company:
            # Applicants see the questions sent to them and the decision, not the internal assessment.
            for key in ("assigned_reviewer", "recommendation", "recommendation_note", "reviews"):
                payload.pop(key, None)
        return Outcome(payload, f"{a.reference_no} · {a.product_name}")

    def _tool_list_documents(self, application_id=None, sequence=None, module=None) -> Outcome:
        a = self._application(application_id)
        docs = [d for s in self._sequences(a, sequence) for d in documents.list_documents(s)]
        if module:
            prefix = str(module).lower().strip()
            docs = [d for d in docs if d["path"].lower().startswith(prefix + "/")]
        return Outcome({"application": a.reference_no, "count": len(docs), "documents": docs[:150]},
                       f"{len(docs)} documents")

    def _tool_search_documents(self, query, application_id=None, sequence=None) -> Outcome:
        a = self._application(application_id)
        sequences = self._sequences(a, sequence)
        indexed, total = documents.index_sequences(sequences)
        hits = documents.search(sequences, str(query))
        payload = {"application": a.reference_no, "query": query, "hits": hits}
        if indexed < total:
            payload["note"] = f"Only {indexed} of {total} documents could be read in time; results may be incomplete."
        return Outcome(payload, f"“{query}” · {len(hits)} hits")

    def _tool_read_document(self, path, sequence=None, application_id=None, start_page=1, pages=READ_PAGES) -> Outcome:
        a = self._application(application_id)
        path = str(path).lstrip("/")
        # A citation like 0000/m3/... carries its sequence in front.
        if not sequence and len(path) > 5 and path[:4].isdigit() and path[4] == "/":
            sequence, path = path[:4], path[5:]
        candidates = self._sequences(a, sequence)
        target = next((s for s in reversed(candidates) if documents.resolve_file(s, path)), None)
        if target is None:
            raise ToolError(f"Document {path} was not found in the accepted sequences of {a.reference_no}.")
        start = max(1, int(start_page))
        count = min(MAX_READ_PAGES, max(1, int(pages)))
        rows, total = documents.read_pages(target, path, start, count)
        payload = {
            "application": a.reference_no,
            "sequence": target.number,
            "path": path,
            "total_pages": total,
            "pages": [{"page": r.page, "text": r.text} for r in rows],
        }
        if total and not any(r.text for r in rows):
            payload["note"] = "No extractable text on these pages (scanned image or empty)."
        end = start + len(rows) - 1
        return Outcome(payload, f"{path.rsplit('/', 1)[-1]} p.{start}–{end} of {total}")

    def _tool_get_validation_report(self, application_id=None, sequence=None) -> Outcome:
        a = self._application(application_id)
        seqs = a.sequences.all()
        if sequence:
            seqs = seqs.filter(number=str(sequence).zfill(4))
        target = seqs.order_by("-uploaded_at").first()
        if target is None:
            raise ToolError("No such sequence.")
        run = target.latest_run()
        if run is None:
            return Outcome({"sequence": target.number, "validated": False}, f"{target.number} not validated")
        findings = run.findings.exclude(severity=Finding.Severity.INFO)[:80]
        payload = {
            "sequence": target.number,
            "status": target.get_validation_status_display(),
            "errors": run.error_count,
            "warnings": run.warning_count,
            "findings": [
                {"rule": f.rule_code, "criterion": str(f.title), "severity": f.severity, "file": f.file_path,
                 "detail": f.detail}
                for f in findings
            ],
        }
        return Outcome(payload, f"{target.number}: {run.error_count} errors, {run.warning_count} warnings")

    def _tool_find_applications(self, query="") -> Outcome:
        apps_ = self.visible.select_related("company")
        query = str(query).strip()
        if query:
            apps_ = apps_.filter(
                Q(product_name__icontains=query) | Q(active_ingredients__icontains=query)
                | Q(reference_no__icontains=query) | Q(company__name_en__icontains=query)
            )
        rows = [
            {"id": a.pk, "reference_no": a.reference_no, "product_name": a.product_name,
             "active_ingredients": a.active_ingredients, "status": a.get_status_display(), "company": str(a.company)}
            for a in apps_[:25]
        ]
        return Outcome({"applications": rows}, f"{len(rows)} applications")
