"""Layer 3 – file compliance: formats, security settings and sizes."""
from django.utils.translation import gettext_lazy as _

from .base import Layer, Rule, Severity

ALLOWED_EXTENSIONS = {"pdf", "xml", "xsd", "dtd", "xsl", "txt", "xpt", "jpg", "jpeg", "png", "gif", "svg"}
MODULE1_ONLY_EXTENSIONS = {"docx", "doc", "rtf"}
DTD_MODULE_EXTENSIONS = {"mod"}  # modular DTD parts (GCC gc-envelope.mod, gc-leaf.mod), only in util/dtd
ALLOWED_PDF_VERSIONS = {"1.4", "1.5", "1.6", "1.7"}


class PackageArchive(Rule):
    """Raised by the engine itself when the zip cannot be safely extracted."""

    code = "FC-00"
    layer = Layer.FILE
    title = _("The package must be a valid, safe ZIP archive")

    def check(self, ctx):
        return []


class AllowedFileTypes(Rule):
    code = "FC-01"
    layer = Layer.FILE
    title = _("Only accepted file formats may be submitted")

    def check(self, ctx):
        for path in ctx.files:
            rel = ctx.rel(path)
            ext = path.suffix.lower().lstrip(".")
            if ext in ALLOWED_EXTENSIONS:
                continue
            if ext in DTD_MODULE_EXTENSIONS and "/util/dtd/" in f"/{rel}":
                continue
            if ext in MODULE1_ONLY_EXTENSIONS:
                if not rel.startswith("m1/"):
                    yield self.issue(f".{ext} files are only accepted in Module 1.", file_path=rel)
                continue
            yield self.issue(f".{ext or '(no extension)'} is not an accepted file format.", file_path=rel)


class PdfNotSecured(Rule):
    code = "FC-02"
    layer = Layer.FILE
    title = _("PDF files must open without passwords or security restrictions")

    def check(self, ctx):
        for path in ctx.pdf_files:
            report = ctx.pdf(path)
            if report.error:
                yield self.issue(report.error, file_path=ctx.rel(path))
            elif report.encrypted:
                yield self.issue("The PDF is encrypted or password-protected.", file_path=ctx.rel(path))


class PdfVersion(Rule):
    code = "FC-03"
    layer = Layer.FILE
    title = _("PDF files must be version 1.4 to 1.7")

    def check(self, ctx):
        for path in ctx.pdf_files:
            report = ctx.pdf(path)
            if report.version and report.version not in ALLOWED_PDF_VERSIONS:
                yield self.issue(f"PDF version is {report.version}.", file_path=ctx.rel(path))


class PdfNoActiveContent(Rule):
    code = "FC-04"
    layer = Layer.FILE
    title = _("PDF files must not contain JavaScript or launch actions")

    def check(self, ctx):
        for path in ctx.pdf_files:
            report = ctx.pdf(path)
            if report.readable and report.active_content:
                yield self.issue("Found: " + ", ".join(report.active_content) + ".", file_path=ctx.rel(path))


class PdfFontsEmbedded(Rule):
    code = "FC-05"
    layer = Layer.FILE
    severity = Severity.WARNING
    title = _("Fonts used in PDF files should be embedded")

    def check(self, ctx):
        for path in ctx.pdf_files:
            report = ctx.pdf(path)
            if report.readable and report.unembedded_fonts:
                fonts = report.unembedded_fonts
                listed = ", ".join(fonts[:5]) + (f" (+{len(fonts) - 5} more)" if len(fonts) > 5 else "")
                yield self.issue(f"Fonts not embedded: {listed}.", file_path=ctx.rel(path))


class PdfTextLayer(Rule):
    """A scan of a paper document carries no text: it cannot be searched, quoted or read back.

    Only files with no text at all are reported. Single image pages (a chromatogram, a signed
    certificate page) are normal inside an otherwise readable document and are left alone.
    """

    code = "FC-08"
    layer = Layer.FILE
    severity = Severity.WARNING
    title = _("PDF files should contain searchable text, not only scanned images")

    def check(self, ctx):
        for path in ctx.pdf_files:
            report = ctx.pdf(path)
            if report.readable and report.is_scanned:
                pages = report.pages_read
                yield self.issue(
                    f"No text could be extracted from {'the page' if pages == 1 else f'any of the first {pages} pages'}. "
                    "A scanned document cannot be searched; file it with a text layer (OCR).",
                    file_path=ctx.rel(path),
                )


class FileSizeLimit(Rule):
    code = "FC-06"
    layer = Layer.FILE
    title = _("Individual files must not exceed the maximum file size")

    def check(self, ctx):
        limit = ctx.limits.max_file_bytes
        for path in ctx.files:
            size = path.stat().st_size
            if size > limit:
                yield self.issue(
                    f"File is {size / 1048576:.1f} MB; the limit is {limit / 1048576:.0f} MB.",
                    file_path=ctx.rel(path),
                )


class NoEmptyFiles(Rule):
    code = "FC-07"
    layer = Layer.FILE
    title = _("Files must not be empty")

    def check(self, ctx):
        for path in ctx.files:
            if path.stat().st_size == 0:
                yield self.issue("The file is 0 bytes.", file_path=ctx.rel(path))


PACKAGE_RULE = PackageArchive()
RULES = [
    AllowedFileTypes(),
    PdfNotSecured(),
    PdfVersion(),
    PdfNoActiveContent(),
    PdfFontsEmbedded(),
    FileSizeLimit(),
    NoEmptyFiles(),
    PdfTextLayer(),
]
