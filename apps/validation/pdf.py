"""PDF inspection for the file-compliance layer (one pass per file)."""
import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

MAX_PAGES_SCANNED = 50
STANDARD_FONTS = {
    "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic",
    "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique",
    "Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique",
    "Symbol", "ZapfDingbats",
}
ACTIVE_ACTIONS = ("/JavaScript", "/Launch")


@dataclass
class PdfReport:
    error: str = ""
    encrypted: bool = False
    version: str = ""
    active_content: list[str] = field(default_factory=list)
    unembedded_fonts: list[str] = field(default_factory=list)

    @property
    def readable(self):
        return not self.error and not self.encrypted


def _resolve(obj):
    return obj.get_object() if obj is not None and hasattr(obj, "get_object") else obj


def _version_key(version: str):
    try:
        major, minor = version.split(".")
        return int(major), int(minor)
    except ValueError:
        return (0, 0)


def inspect_pdf(path: Path) -> PdfReport:
    report = PdfReport()
    with open(path, "rb") as fh:
        head = fh.read(1024)
    match = re.search(rb"%PDF-(\d\.\d)", head)
    if not match:
        report.error = "The file does not start with a PDF header (%PDF-x.y)."
        return report
    report.version = match.group(1).decode()

    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            report.encrypted = True
            return report
        catalog = _resolve(reader.trailer["/Root"])
        catalog_version = catalog.get("/Version")
        if catalog_version:
            candidate = str(catalog_version).lstrip("/")
            if _version_key(candidate) > _version_key(report.version):
                report.version = candidate
        report.active_content = _active_content(reader, catalog)
        report.unembedded_fonts = _unembedded_fonts(reader)
    except Exception as exc:  # pypdf raises many types on damaged files
        report.error = f"The PDF cannot be read: {exc}"
    return report


def _action_type(action):
    action = _resolve(action)
    if hasattr(action, "get"):
        kind = action.get("/S")
        if kind in ACTIVE_ACTIONS:
            return str(kind)
    return None


def _active_content(reader, catalog) -> list[str]:
    found = set()
    names = _resolve(catalog.get("/Names"))
    if names is not None and "/JavaScript" in names:
        found.add("document-level JavaScript")
    if "/AA" in catalog:
        found.add("document additional-actions")
    if kind := _action_type(catalog.get("/OpenAction")):
        found.add(f"open action {kind}")
    for page in reader.pages[:MAX_PAGES_SCANNED]:
        if "/AA" in page:
            found.add("page additional-actions")
        for annot in _resolve(page.get("/Annots")) or []:
            annot = _resolve(annot)
            if kind := _action_type(annot.get("/A")):
                found.add(f"link action {kind}")
    return sorted(found)


def _unembedded_fonts(reader) -> list[str]:
    missing = set()
    for page in reader.pages[:MAX_PAGES_SCANNED]:
        resources = _resolve(page.get("/Resources"))
        fonts = _resolve(resources.get("/Font")) if resources is not None else None
        if not fonts:
            continue
        for ref in fonts.values():
            font = _resolve(ref)
            subtype = font.get("/Subtype")
            if subtype == "/Type3":
                continue  # glyphs are defined inside the PDF
            base_name = str(font.get("/BaseFont", "")).lstrip("/")
            descriptor_owner = font
            if subtype == "/Type0":
                descendants = _resolve(font.get("/DescendantFonts")) or []
                if descendants:
                    descriptor_owner = _resolve(descendants[0])
            descriptor = _resolve(descriptor_owner.get("/FontDescriptor"))
            embedded = descriptor is not None and any(
                key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3")
            )
            if not embedded and base_name.split("+")[-1] not in STANDARD_FONTS:
                missing.add(base_name or "(unnamed font)")
    return sorted(missing)
