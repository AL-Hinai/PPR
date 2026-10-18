"""Dossier documents as text: listing, extraction (cached per page) and search.

Text is extracted lazily, the first time a tool needs a document, and stored in
``DocumentText`` so later questions are a database query. ``manage.py
index_dossier_text`` pre-builds it for large dossiers. Only accepted sequences
are read, exactly as the dossier viewer shows them.
"""
from __future__ import annotations

import logging
import re
import time
import zipfile
from pathlib import Path

from django.db.models import Q
from pypdf import PdfReader

from apps.applications.models import Sequence
from apps.validation.ectd import build_dossier_tree, locate_sequence_dir

from .models import DocumentText

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = (".pdf", ".docx", ".txt", ".xml")
MAX_PAGES = 400
MAX_PAGE_CHARS = 20_000
# How long one search may spend extracting documents it has not seen before.
INDEX_BUDGET_SECONDS = 25


def sequence_dir(sequence: Sequence) -> Path | None:
    if not sequence.is_accepted or not sequence.extracted_dir or not sequence.extracted_dir.is_dir():
        return None
    return locate_sequence_dir(sequence.extracted_dir)[0].resolve()


def resolve_file(sequence: Sequence, path: str) -> Path | None:
    root = sequence_dir(sequence)
    if root is None or not path:
        return None
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        return None
    return target


def list_documents(sequence: Sequence) -> list[dict]:
    """Every leaf of the sequence's CTD tree, flattened, with its section heading."""
    root = sequence_dir(sequence)
    if root is None:
        return []
    documents: list[dict] = []

    def walk(node, trail):
        here = [*trail, node["label"]]
        for leaf in node["leaves"]:
            if leaf["exists"]:
                documents.append(
                    {
                        "sequence": sequence.number,
                        "path": leaf["path"],
                        "title": leaf["title"],
                        "section": " › ".join(here),
                        "operation": leaf["operation"],
                    }
                )
        for child in node["children"]:
            walk(child, here)

    for module in build_dossier_tree(root):
        walk(module, [])
    return documents


def _clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:MAX_PAGE_CHARS]


def extract_pages(file: Path) -> list[str]:
    suffix = file.suffix.lower()
    try:
        if suffix == ".pdf":
            reader = PdfReader(str(file))
            if reader.is_encrypted:
                return []
            return [_clean(page.extract_text() or "") for page in reader.pages[:MAX_PAGES]]
        if suffix == ".docx":
            with zipfile.ZipFile(file) as archive:
                xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
            xml = re.sub(r"</w:p>", "\n", xml)
            return [_clean(re.sub(r"<[^>]+>", "", xml))]
        if suffix in (".txt", ".xml"):
            return [_clean(file.read_text(encoding="utf-8", errors="replace"))]
    except Exception:  # a broken file must not break the conversation
        logger.warning("Could not extract text from %s", file, exc_info=True)
    return []


def ensure_text(sequence: Sequence, path: str, title: str = "", section: str = "") -> bool:
    """Extract and store one document's text if it has not been already. True if it is stored."""
    if DocumentText.objects.filter(sequence=sequence, path=path).exists():
        return True
    file = resolve_file(sequence, path)
    if file is None or file.suffix.lower() not in TEXT_SUFFIXES:
        return False
    pages = extract_pages(file) or [""]
    DocumentText.objects.bulk_create(
        [DocumentText(sequence=sequence, path=path, page=i, text=text, title=title[:300], section=section[:500])
         for i, text in enumerate(pages, start=1)],
        ignore_conflicts=True,
    )
    return True


def index_sequences(sequences, budget: float = INDEX_BUDGET_SECONDS) -> tuple[int, int]:
    """Extract every not-yet-indexed document, within a time budget. Returns (indexed, total)."""
    started = time.monotonic()
    indexed = total = 0
    for sequence in sequences:
        stored = DocumentText.objects.filter(sequence=sequence)
        done = set(stored.values_list("path", flat=True).distinct())
        untitled = set(stored.filter(title="").values_list("path", flat=True).distinct())
        for doc in list_documents(sequence):
            if not doc["path"].lower().endswith(TEXT_SUFFIXES):
                continue
            total += 1
            if doc["path"] in done:
                indexed += 1
                if doc["path"] in untitled:  # extracted on demand by the assistant, before titles were known
                    stored.filter(path=doc["path"]).update(title=doc["title"][:300], section=doc["section"][:500])
            elif time.monotonic() - started < budget and ensure_text(sequence, doc["path"], doc["title"], doc["section"]):
                indexed += 1
    return indexed, total


def read_pages(sequence: Sequence, path: str, start: int, count: int) -> tuple[list[DocumentText], int]:
    ensure_text(sequence, path)
    rows = DocumentText.objects.filter(sequence=sequence, path=path)
    total = rows.count()
    return list(rows.filter(page__gte=start, page__lt=start + count)), total


def _terms(query: str) -> list[str]:
    words = re.findall(r"[\w\-\.%]+", query.lower())
    stop = {"the", "and", "for", "with", "what", "which", "this", "that", "from", "are", "is", "of", "in", "on", "to"}
    terms = [w for w in words if len(w) >= 3 and w not in stop]
    return list(dict.fromkeys(terms))[:8]


def _snippet(text: str, terms: list[str], width: int = 320) -> str:
    lower = text.lower()
    positions = [lower.find(t) for t in terms if lower.find(t) >= 0]
    centre = min(positions) if positions else 0
    start = max(0, centre - width // 3)
    snippet = text[start : start + width].replace("\n", " ").strip()
    return ("…" if start else "") + snippet + ("…" if start + width < len(text) else "")


def search(sequences, query: str, limit: int = 8) -> list[dict]:
    terms = _terms(query)
    if not terms:
        return []
    sequences = list(sequences)
    by_id = {s.pk: s for s in sequences}
    condition = Q()
    for term in terms:
        condition |= Q(text__icontains=term)
    rows = DocumentText.objects.filter(condition, sequence__in=sequences)[:600]
    scored = []
    for row in rows:
        lower = row.text.lower()
        hits = sum(lower.count(t) for t in terms)
        breadth = sum(1 for t in terms if t in lower)
        if hits:
            scored.append((breadth, hits, row))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    titles = _titles(by_id, [row for *_rest, row in scored[:limit] if not row.title])
    return [
        {
            "sequence": by_id[row.sequence_id].number,
            "path": row.path,
            "title": row.title or titles.get((row.sequence_id, row.path), row.path.rsplit("/", 1)[-1]),
            "page": row.page,
            "snippet": _snippet(row.text, terms),
        }
        for _breadth, _hits, row in scored[:limit]
    ]


def _titles(by_id: dict, rows) -> dict:
    """Titles for rows stored before titles were kept, from the CTD trees of just those sequences."""
    needed = {row.sequence_id for row in rows}
    return {(pk, d["path"]): d["title"] for pk in needed for d in list_documents(by_id[pk])}
