"""Benchmark set: valid packages, one broken package per rule, and a two-sequence lifecycle.

The same packages prove each rule in the test-suite and are exported (``build_sample_packages --benchmark``)
to be validated by PPR and by a reference validator such as EURSvalidator; see docs/validation_benchmark.md.
"""
import csv
import io
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from lxml import etree
from pypdf import PdfReader, PdfWriter

from . import samples
from .ectd import XLINK_NS, locate_sequence_dir
from .engine import validate_package
from .rules import RULES_BY_CODE
from .rules.base import Severity

INTRO = "m2/22-intro/introduction.pdf"
REGIONAL = "m1/gc/gc-regional.xml"
MANIFEST = "manifest.csv"


# --- package builders ------------------------------------------------------------

def files(application_type="NEW_DRUG", documents=None, number="0000"):
    return samples.build_files(number, documents, application_type)


def with_doc(**kwargs):
    """Initial NEW_DRUG documents plus one extra document under 2.7 (last in CTD order)."""
    docs = samples.initial_documents("NEW_DRUG")
    docs.append(samples.Doc(section=(samples.M2, "m2-7-clinical-summary"), title="Extra", **kwargs))
    return files(documents=docs)


def encrypted_pdf():
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(samples.make_pdf("secret"))))
    writer.pdf_header = b"%PDF-1.7"
    writer.encrypt("open-sesame", algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def refreshed_zip(f):
    """Zip after editing the regional XML by hand: re-sign its leaf in index.xml and index-md5.txt."""
    index = etree.fromstring(f["index.xml"])
    for leaf in index.iter("leaf"):
        if leaf.get(f"{{{XLINK_NS}}}href") == REGIONAL:
            leaf.set("checksum", samples.md5(f[REGIONAL]))
    f["index.xml"] = etree.tostring(index, xml_declaration=True, encoding="UTF-8")
    samples.refresh_index_md5(f)
    return samples.to_zip(f)


def _edited(edit, refresh_md5=False):
    def build():
        f = files()
        edit(f)
        if refresh_md5:
            samples.refresh_index_md5(f)
        return samples.to_zip(f)
    return build


def _extra_doc(**kwargs):
    return lambda: samples.to_zip(with_doc(**kwargs))


def _envelope(**values):
    return lambda: samples.build_package("0000", envelope=values)


def _without_arabic_leaflet():
    docs = [d for d in samples.initial_documents("NEW_DRUG") if "/ar/" not in d.path]
    return samples.build_package("0000", documents=docs)


def _regional_leaf_appended():
    f = files()
    checksum = samples.md5(f[REGIONAL]).encode()
    f["index.xml"] = f["index.xml"].replace(
        b'operation="new" checksum-type="md5" checksum="' + checksum,
        b'operation="append" checksum-type="md5" checksum="' + checksum,
    )
    samples.refresh_index_md5(f)
    return samples.to_zip(f)


def _wrong_namespace():
    f = files()
    f[REGIONAL] = f[REGIONAL].replace(b"http://sfda.gov.sa", b"http://example.org")
    return refreshed_zip(f)


def _response_with_unknown_leaf():
    docs = samples.response_documents()
    docs[-1].modified_file = "../0000/index.xml#leaf-does-not-exist"
    return samples.build_package("0001", documents=docs)


# --- cases ---------------------------------------------------------------------------

@dataclass
class Case:
    label: str  # test id, e.g. "BR-03"
    package: str  # path in the exported set; a folder groups the sequences of one application
    build: Callable[[], bytes]
    expected: set[str] = field(default_factory=set)  # rule codes PPR must report (empty: passes cleanly)
    description: str = ""
    application_type: str = "NEW_DRUG"


def _ed(key, value):
    def edit(f):
        f[key] = value
    return edit


def _drop(*keys):
    def edit(f):
        for key in keys:
            del f[key]
    return edit


def broken_cases() -> list[Case]:
    """One package per error rule, each failing on exactly the listed rules."""
    return [
        Case("SCH-01", "sch-01-missing-index.zip", _edited(_drop("index.xml", "index-md5.txt")), {"SCH-01"},
             "index.xml is missing"),
        Case("SCH-02", "sch-02-malformed-index.zip",
             _edited(lambda f: f.update({"index.xml": f["index.xml"][:-40]}), refresh_md5=True), {"SCH-02"},
             "index.xml is truncated (not well-formed)"),
        Case("SCH-03", "sch-03-dtd-violation.zip",
             _edited(lambda f: f.update({"index.xml": f["index.xml"].replace(b"m2-2-introduction", b"m2-2-intro")}),
                     refresh_md5=True), {"SCH-03"}, "Unknown element m2-2-intro in index.xml"),
        Case("BR-01", "br-01-wrong-sequence-number.zip", lambda: samples.to_zip(files(), number="0003"), {"BR-01"},
             "Initial submission in folder 0003"),
        Case("BR-02", "br-02-wrong-index-md5.zip", _edited(_ed("index-md5.txt", b"0" * 32)), {"BR-02"},
             "index-md5.txt does not match index.xml"),
        Case("BR-03", "br-03-missing-document.zip", _edited(_drop(INTRO)), {"BR-03"},
             "A leaf points to a file that is not in the package"),
        Case("BR-04", "br-04-changed-document.zip", _edited(_ed(INTRO, samples.make_pdf("tampered after signing"))),
             {"BR-04"}, "A document changed after its checksum was recorded"),
        Case("BR-07", "br-07-replace-in-initial-sequence.zip",
             _extra_doc(path="m2/27-clin-sum/overview.pdf", operation="replace",
                        modified_file="../0000/index.xml#leaf-x"), {"BR-07"},
             "operation=replace in sequence 0000"),
        Case("BR-08", "br-08-bad-file-name.zip", _extra_doc(path="m2/27-clin-sum/Non Clinical Overview.pdf"), {"BR-08"},
             "Upper case and spaces in a file name"),
        Case("BR-09", "br-09-missing-ich-dtd.zip", _edited(_drop("util/dtd/ich-ectd-3-2.dtd")), {"BR-09"},
             "util/dtd/ich-ectd-3-2.dtd is missing"),
        Case("FC-01", "fc-01-executable.zip", _extra_doc(path="m2/27-clin-sum/tool.exe", content=b"MZ"), {"FC-01"},
             "An .exe file in Module 2"),
        Case("FC-02", "fc-02-password-protected-pdf.zip",
             _extra_doc(path="m2/27-clin-sum/locked.pdf", content=encrypted_pdf()), {"FC-02"}, "Encrypted PDF"),
        Case("FC-03", "fc-03-pdf-1-3.zip",
             _extra_doc(path="m2/27-clin-sum/old.pdf", content=samples.make_pdf("x", version="1.3")), {"FC-03"},
             "PDF version 1.3"),
        Case("FC-04", "fc-04-pdf-javascript.zip",
             _extra_doc(path="m2/27-clin-sum/script.pdf", content=samples.make_pdf("x", javascript=True)), {"FC-04"},
             "PDF with an OpenAction JavaScript"),
        Case("FC-07", "fc-07-empty-file.zip", _extra_doc(path="m2/27-clin-sum/empty.pdf", content=b""), {"FC-07"},
             "A 0-byte PDF"),
        Case("FC-00 zip slip", "fc-00-zip-slip.zip", lambda: samples.to_zip(files(), extra={"../evil.txt": b"x"}),
             {"FC-00"}, "A zip entry outside the package folder"),
        Case("FC-00 not a zip", "fc-00-not-a-zip.zip", lambda: b"this is not a zip file", {"FC-00"},
             "The upload is not a zip archive"),
        Case("GCC-01", "gcc-01-wrong-namespace.zip", _wrong_namespace, {"GCC-01"},
             "gc-regional.xml root in another namespace"),
        Case("GCC-02", "gcc-02-envelope-missing-description.zip", _envelope(**{"submission-description": None}),
             {"GCC-02"}, "Envelope without submission-description (DTD)"),
        Case("GCC-03 agency", "gcc-03-wrong-agency.zip", _envelope(agency="SA-SFDA"), {"GCC-03"},
             "Envelope for Oman names SA-SFDA"),
        Case("GCC-03 country", "gcc-03-envelope-for-another-country.zip", _envelope(country="sa", agency="SA-SFDA"),
             {"GCC-03"}, "Only a Saudi Arabia envelope"),
        Case("GCC-04", "gcc-04-envelope-sequence.zip", _envelope(sequence="0001"), {"GCC-04"},
             "Envelope sequence 0001 in sequence 0000"),
        Case("GCC-04 related", "gcc-04-related-sequence.zip", _envelope(**{"related-sequence": "0000"}), {"GCC-04"},
             "Sequence 0000 relates to itself"),
        Case("GCC-05", "gcc-05-submission-type.zip", _envelope(submission="new-gen"), {"GCC-05"},
             "New drug application submitted as new-gen"),
        Case("GCC-06", "gcc-06-submission-unit.zip", _envelope(**{"submission-unit": "response"}), {"GCC-06"},
             "Sequence 0000 with unit 'response'"),
        Case("GCC-06 reformat", "gcc-06-reformat-without-none.zip", _envelope(**{"submission-unit": "reformat"}),
             {"GCC-06"}, "Unit 'reformat' with type new-nce"),
        Case("GCC-07", "gcc-07-no-arabic-leaflet.zip", _without_arabic_leaflet, {"GCC-07"},
             "No Arabic patient information leaflet"),
        Case("GCC-08", "gcc-08-regional-leaf-append.zip", _regional_leaf_appended, {"GCC-08", "BR-07"},
             "gc-regional.xml referenced with operation append (BR-07: no modified-file)"),
        Case("GCC-09", "gcc-09-missing-gcc-dtd.zip", _edited(_drop("util/dtd/gc-envelope.mod")), {"GCC-09"},
             "util/dtd/gc-envelope.mod is missing"),
    ]


def benchmark_cases() -> list[Case]:
    """Everything exported for the benchmark: valid packages, warnings, broken packages, lifecycles."""
    return [
        Case("valid new drug", "valid-new-drug.zip", lambda: samples.build_package("0000", "NEW_DRUG"),
             description="Complete new drug (new-nce) sequence"),
        Case("valid generic", "valid-generic.zip", lambda: samples.build_package("0000", "GENERIC"),
             description="Complete generic (new-gen) sequence", application_type="GENERIC"),
        Case("valid lifecycle 0000", "lifecycle-valid/0000.zip", lambda: samples.build_package("0000"),
             description="Initial sequence of a two-sequence lifecycle"),
        Case("valid lifecycle 0001", "lifecycle-valid/0001.zip",
             lambda: samples.build_package("0001", documents=samples.response_documents()),
             description="Response sequence that replaces the stability summary"),
        Case("BR-05", "br-05-unreferenced-file.zip",
             _edited(_ed("m2/22-intro/notes.pdf", samples.make_pdf("stray"))), {"BR-05"},
             "A file no leaf refers to (warning)"),
        Case("FC-05", "fc-05-font-not-embedded.zip",
             _extra_doc(path="m2/27-clin-sum/arial.pdf", content=samples.make_pdf("x", font="Arial")), {"FC-05"},
             "PDF with a non-embedded font (warning)"),
        *broken_cases(),
        Case("BR-07 lifecycle 0000", "lifecycle-broken/0000.zip", lambda: samples.build_package("0000"),
             description="Initial sequence"),
        Case("BR-07 lifecycle 0001", "lifecycle-broken/0001.zip", _response_with_unknown_leaf, {"BR-07"},
             "modified-file points to a leaf that 0000 does not contain"),
    ]


def write_benchmark_set(folder: Path) -> list[Case]:
    """Write every benchmark package plus manifest.csv (what PPR is expected to report)."""
    cases = benchmark_cases()
    for case in cases:
        target = folder / case.package
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(case.build())
    with open(folder / MANIFEST, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["package", "application_type", "expected_codes", "description"])
        for case in cases:
            writer.writerow([case.package, case.application_type, " ".join(sorted(case.expected)), case.description])
    return cases


# --- running a folder of packages -----------------------------------------------------

@dataclass
class PackageResult:
    package: str
    application_type: str
    issues: list
    expected: set[str] | None = None  # from the manifest; None when the package is not listed

    @property
    def codes(self) -> set[str]:
        return {i.rule_code for i in self.issues}

    @property
    def errors(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.ERROR)

    @property
    def warnings(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.WARNING)

    @property
    def verdict(self) -> str:
        if self.errors:
            return "FAIL"
        return "PASS_WITH_WARNINGS" if self.warnings else "PASS"

    @property
    def matches(self) -> bool | None:
        return None if self.expected is None else self.codes == self.expected


def read_manifest(folder: Path) -> dict[str, dict]:
    path = folder / MANIFEST
    if not path.is_file():
        return {}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return {row["package"]: row for row in csv.DictReader(fh)}


def _groups(folder: Path) -> list[list[Path]]:
    """Top-level zips are one application each; the zips in a sub-folder are one application's sequences."""
    groups = [[path] for path in sorted(folder.glob("*.zip"))]
    groups += [sorted(sub.glob("*.zip")) for sub in sorted(p for p in folder.iterdir() if p.is_dir())]
    return [g for g in groups if g]


def run_benchmark(folder: Path, default_type: str = "NEW_DRUG") -> list[PackageResult]:
    """Validate every package in ``folder`` as PPR would on upload (sequence order within each application)."""
    manifest = read_manifest(folder)
    results = []
    for group in _groups(folder):
        with tempfile.TemporaryDirectory() as tmp:
            accepted: dict[str, Path] = {}
            for index, path in enumerate(group):
                name = path.relative_to(folder).as_posix()
                row = manifest.get(name)
                application_type = (row or {}).get("application_type") or default_type
                expected_number = f"{len(accepted):04d}"
                dest = Path(tmp) / str(index)
                issues, _ = validate_package(path, dest, expected_number=expected_number,
                                             application_type=application_type, previous=dict(accepted))
                result = PackageResult(name, application_type, issues,
                                       set(row["expected_codes"].split()) if row else None)
                if not result.errors:
                    accepted[expected_number] = locate_sequence_dir(dest)[0]
                results.append(result)
    return results


def write_results(results: list[PackageResult], summary_path: Path, findings_path: Path) -> None:
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["package", "application_type", "ppr_verdict", "errors", "warnings", "ppr_codes",
                         "expected_codes", "matches_expected", "reference_verdict", "agreement", "notes"])
        for r in results:
            writer.writerow([
                r.package, r.application_type, r.verdict, r.errors, r.warnings, " ".join(sorted(r.codes)),
                "" if r.expected is None else " ".join(sorted(r.expected)),
                {None: "", True: "yes", False: "NO"}[r.matches], "", "", "",
            ])
    with open(findings_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["package", "rule", "severity", "criterion", "file", "location", "detail",
                         "reference_criterion", "reference_severity", "agreement", "notes"])
        for r in results:
            for i in r.issues:
                rule = RULES_BY_CODE.get(i.rule_code)
                writer.writerow([r.package, i.rule_code, i.severity, str(rule.title) if rule else "",
                                 i.file_path, i.location, i.detail, "", "", "", ""])
