"""Each validation rule is proven by a package that breaks exactly that rule."""
import io

import pytest
from django.test import override_settings
from pypdf import PdfReader, PdfWriter

from apps.applications.models import Sequence
from apps.validation import samples
from apps.validation.ectd import heading_label
from apps.validation.samples import Doc

V = Sequence.ValidationStatus
INTRO = "m2/22-intro/introduction.pdf"


def files(application_type="NEW_DRUG", documents=None, number="0000"):
    return samples.build_files(number, documents, application_type)


def with_doc(**kwargs):
    """Initial NEW_DRUG documents plus one extra document under 2.7 (last in CTD order)."""
    docs = samples.initial_documents("NEW_DRUG")
    docs.append(Doc(section=(samples.M2, "m2-7-clinical-summary"), title="Extra", **kwargs))
    return files(documents=docs)


def encrypted_pdf():
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(samples.make_pdf("secret"))))
    writer.pdf_header = b"%PDF-1.7"
    writer.encrypt("open-sesame", algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.mark.django_db
@pytest.mark.parametrize("application_type", ["NEW_DRUG", "GENERIC"])
def test_valid_package_passes_every_rule(validate, application_type):
    sequence, run, codes = validate(samples.build_package("0000", application_type), application_type)
    assert codes == set()
    assert sequence.validation_status == V.PASSED
    assert sequence.extracted_dir.is_dir()


@pytest.mark.django_db
def test_lifecycle_response_sequence_passes(validate, make_application):
    application = make_application()
    first, _, _ = validate(samples.build_package("0000"), application=application)
    assert first.is_accepted
    second, run, codes = validate(
        samples.build_package("0001", documents=samples.response_documents()), application=application
    )
    assert codes == set(), list(run.findings.values_list("rule_code", "detail"))
    assert second.number == "0001"


def broken_cases():
    def missing_index():
        f = files()
        del f["index.xml"], f["index-md5.txt"]
        return samples.to_zip(f)

    def malformed_index():
        f = files()
        f["index.xml"] = f["index.xml"][:-40]
        samples.refresh_index_md5(f)
        return samples.to_zip(f)

    def dtd_violation():
        f = files()
        f["index.xml"] = f["index.xml"].replace(b"m2-2-introduction", b"m2-2-intro")
        samples.refresh_index_md5(f)
        return samples.to_zip(f)

    def wrong_md5():
        f = files()
        f["index-md5.txt"] = b"0" * 32
        return samples.to_zip(f)

    def missing_document():
        f = files()
        del f[INTRO]
        return samples.to_zip(f)

    def changed_document():
        f = files()
        f[INTRO] = samples.make_pdf("tampered after signing")
        return samples.to_zip(f)

    def unreferenced_file():
        f = files()
        f["m2/22-intro/notes.pdf"] = samples.make_pdf("stray")
        return samples.to_zip(f)

    def replace_in_initial_sequence():
        return samples.to_zip(with_doc(path="m2/27-clin-sum/overview.pdf", operation="replace",
                                       modified_file="../0000/index.xml#leaf-x"))

    def bad_name():
        return samples.to_zip(with_doc(path="m2/27-clin-sum/Non Clinical Overview.pdf"))

    def missing_util_dtd():
        f = files()
        del f["util/dtd/ich-ectd-3-2.dtd"]
        return samples.to_zip(f)

    def wrong_extension():
        return samples.to_zip(with_doc(path="m2/27-clin-sum/tool.exe", content=b"MZ"))

    return [
        ("SCH-01", missing_index, {"SCH-01"}),
        ("SCH-02", malformed_index, {"SCH-02"}),
        ("SCH-03", dtd_violation, {"SCH-03"}),
        ("BR-01", lambda: samples.to_zip(files(), number="0003"), {"BR-01"}),
        ("BR-02", wrong_md5, {"BR-02"}),
        ("BR-03", missing_document, {"BR-03"}),
        ("BR-04", changed_document, {"BR-04"}),
        ("BR-07", replace_in_initial_sequence, {"BR-07"}),
        ("BR-08", bad_name, {"BR-08"}),
        ("BR-09", missing_util_dtd, {"BR-09"}),
        ("FC-01", wrong_extension, {"FC-01"}),
        ("FC-02", lambda: samples.to_zip(with_doc(path="m2/27-clin-sum/locked.pdf", content=encrypted_pdf())), {"FC-02"}),
        ("FC-03", lambda: samples.to_zip(with_doc(path="m2/27-clin-sum/old.pdf", content=samples.make_pdf("x", version="1.3"))), {"FC-03"}),
        ("FC-04", lambda: samples.to_zip(with_doc(path="m2/27-clin-sum/script.pdf", content=samples.make_pdf("x", javascript=True))), {"FC-04"}),
        ("FC-07", lambda: samples.to_zip(with_doc(path="m2/27-clin-sum/empty.pdf", content=b"")), {"FC-07"}),
        ("FC-00 zip slip", lambda: samples.to_zip(files(), extra={"../evil.txt": b"x"}), {"FC-00"}),
        ("FC-00 not a zip", lambda: b"this is not a zip file", {"FC-00"}),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("label,build,expected", broken_cases(), ids=[c[0] for c in broken_cases()])
def test_each_rule_fails_its_broken_package(validate, label, build, expected):
    sequence, run, codes = validate(build())
    assert codes == expected, list(run.findings.values_list("rule_code", "detail"))
    assert sequence.validation_status == V.FAILED
    assert sequence.extracted_path == ""  # rejected packages are not kept unpacked


@pytest.mark.django_db
def test_missing_regional_xml(validate):
    f = files()
    del f["m1/gcc/gcc-regional.xml"]
    _, _, codes = validate(samples.to_zip(f))
    assert "SCH-04" in codes


@pytest.mark.django_db
def test_required_modules_depend_on_application_type(validate):
    generic = samples.build_package("0000", "GENERIC")  # has no Module 4
    _, _, codes = validate(generic, "NEW_DRUG")
    assert codes == {"BR-06"}
    _, _, codes = validate(generic, "GENERIC")
    assert codes == set()


@pytest.mark.django_db
def test_unreferenced_file_is_only_a_warning(validate):
    f = files()
    f["m2/22-intro/notes.pdf"] = samples.make_pdf("stray")
    sequence, run, codes = validate(samples.to_zip(f))
    assert codes == {"BR-05"}
    assert sequence.validation_status == V.PASSED_WITH_WARNINGS
    assert run.warning_count == 1 and run.error_count == 0


@pytest.mark.django_db
def test_unembedded_font_is_a_warning(validate):
    data = samples.to_zip(with_doc(path="m2/27-clin-sum/arial.pdf", content=samples.make_pdf("x", font="Arial")))
    sequence, _, codes = validate(data)
    assert codes == {"FC-05"}
    assert sequence.validation_status == V.PASSED_WITH_WARNINGS


@pytest.mark.django_db
@override_settings(ECTD_MAX_FILE_MB=0)
def test_file_size_limit(validate):
    _, _, codes = validate(samples.build_package())
    assert "FC-06" in codes


@pytest.mark.django_db
def test_modified_file_must_exist_in_previous_sequence(validate, make_application):
    application = make_application()
    validate(samples.build_package("0000"), application=application)
    docs = samples.response_documents()
    docs[-1].modified_file = "../0000/index.xml#leaf-does-not-exist"
    _, run, codes = validate(samples.build_package("0001", documents=docs), application=application)
    assert codes == {"BR-07"}
    assert "leaf-does-not-exist" in run.findings.get().detail


@pytest.mark.django_db
@override_settings(ECTD_MAX_UNCOMPRESSED_MB=0)
def test_zip_bomb_budget(validate):
    _, _, codes = validate(samples.build_package())
    assert codes == {"FC-00"}


def test_heading_labels():
    assert heading_label("m3-2-p-5-control-of-drug-product") == "3.2.P.5 Control of drug product"
    assert heading_label("m1-administrative-information-and-prescribing-information").startswith("1 Administrative")
