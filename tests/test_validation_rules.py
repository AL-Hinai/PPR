"""Each validation rule is proven by a package that breaks exactly that rule."""
import hashlib
from pathlib import Path

import pytest
from django.test import override_settings
from lxml import etree

from apps.applications.models import Sequence
from apps.validation import samples
from apps.validation.benchmark import REGIONAL, broken_cases, duplicate_titles, files, with_doc
from apps.validation.ectd import heading_label

pytestmark = [pytest.mark.req("URS-02"), pytest.mark.req("URS-03"), pytest.mark.req("URS-04"), pytest.mark.req("URS-05")]

V = Sequence.ValidationStatus


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


@pytest.mark.django_db
def test_envelope_is_stored_on_the_sequence(validate):
    sequence, _, _ = validate(samples.build_package("0000", "GENERIC"), "GENERIC")
    envelope = sequence.envelope
    assert envelope["country"] == "om" and envelope["agency"] == "OM-MOH"
    assert envelope["submission_type"] == "new-gen" and envelope["submission_unit"] == "initial"
    assert envelope["invented_names"] == [samples.PRODUCT["product-name"]]
    assert envelope["sequence"] == "0000"


@pytest.mark.django_db
def test_later_initial_submission_unit_is_only_a_warning(validate, make_application):
    application = make_application()
    validate(samples.build_package("0000"), application=application)
    data = samples.build_package("0001", documents=samples.response_documents(), envelope={"submission-unit": "initial"})
    sequence, _, codes = validate(data, application=application)
    assert codes == {"GCC-06"}
    assert sequence.validation_status == V.PASSED_WITH_WARNINGS


def test_gcc_dtd_rejects_unknown_agency():
    from apps.validation.regions.gcc import GCC
    from apps.validation.rules.schema import load_dtd

    xml = samples.build_files("0000")[REGIONAL]
    dtd = load_dtd(GCC.dtd_path)
    assert dtd.validate(etree.fromstring(xml))
    assert not dtd.validate(etree.fromstring(xml.replace(b'code="OM-MOH"', b'code="OM-XX"')))


@pytest.mark.django_db
@pytest.mark.parametrize("case", broken_cases(), ids=lambda case: case.label)
def test_each_rule_fails_its_broken_package(validate, case):
    sequence, run, codes = validate(case.build(), case.application_type)
    assert codes == case.expected, list(run.findings.values_list("rule_code", "detail"))
    assert sequence.validation_status == V.FAILED
    assert sequence.extracted_path == ""  # rejected packages are not kept unpacked


@pytest.mark.django_db
def test_missing_regional_xml(validate):
    f = files()
    del f[REGIONAL]
    _, _, codes = validate(samples.to_zip(f))
    assert "SCH-04" in codes


@pytest.mark.django_db
def test_required_modules_depend_on_application_type(validate):
    generic = samples.build_package("0000", "GENERIC")  # has no Module 4, envelope says new-gen
    _, _, codes = validate(generic, "NEW_DRUG")
    assert codes == {"BR-06", "GCC-05"}
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
def test_scanned_pdf_without_a_text_layer_is_a_warning(validate):
    data = samples.to_zip(with_doc(path="m2/27-clin-sum/scan.pdf", content=samples.make_scanned_pdf()))
    sequence, _, codes = validate(data)
    assert codes == {"FC-08"}
    assert sequence.validation_status == V.PASSED_WITH_WARNINGS


@pytest.mark.django_db
def test_duplicate_titles_in_one_section_are_a_warning(validate):
    sequence, run, codes = validate(duplicate_titles())
    assert codes == {"BR-10"}
    assert sequence.validation_status == V.PASSED_WITH_WARNINGS
    detail = run.findings.get(rule_code="BR-10").detail
    assert "Introduction" in detail and "introduction-part-2.pdf" in detail


@pytest.mark.django_db
def test_the_same_title_under_different_nodes_is_not_a_clash(validate):
    """The Arabic and English leaflets sit under a pi-doc of their own each: one title, two places."""
    documents = samples.initial_documents("NEW_DRUG")
    for document in documents:
        if "133-leaflet" in document.path:
            document.title = "Patient information leaflet"
    _, _, codes = validate(samples.build_package("0000", documents=documents))
    assert codes == set()


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


OFFICIAL_ICH_DTD_SHA256 = "c094aa2bded99564ade8ac78ae1540f95e518461b8eebe9a3063f67a165c2731"


def test_bundled_dtd_is_the_official_ich_dtd(settings):
    """SCH-03 must check against the unchanged ICH file (source in apps/validation/dtd/README.md)."""
    data = Path(settings.ECTD_DTD_PATH).read_bytes()
    assert hashlib.sha256(data).hexdigest() == OFFICIAL_ICH_DTD_SHA256


@pytest.mark.django_db
@pytest.mark.parametrize("application_type", ["NEW_DRUG", "GENERIC", "VARIATION", "RENEWAL"])
def test_sample_packages_pass_the_official_dtd(validate, application_type):
    _, _, codes = validate(samples.build_package("0000", application_type), application_type)
    assert "SCH-03" not in codes


def test_heading_labels():
    assert heading_label("m3-2-p-5-control-of-drug-product") == "3.2.P.5 Control of drug product"
    assert heading_label("m1-administrative-information-and-prescribing-information").startswith("1 Administrative")


@pytest.mark.django_db
def test_ectd_4_package_is_named_as_such(validate):
    data = samples.to_zip({"submissionunit.xml": b"<submissionUnit/>", "m2/22-intro/introduction.pdf": samples.make_pdf("x")})
    _, run, codes = validate(data)
    assert "SCH-01" in codes
    assert "eCTD 4.0" in run.findings.get(rule_code="SCH-01").detail


def test_backbone_reader(tmp_path):
    from apps.validation.ectd import ECTD_32, detect_backbone, parse_xml

    for name, data in samples.build_files("0000").items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(data)
    assert detect_backbone(tmp_path) == "3.2.2"
    leaves = ECTD_32.leaves(parse_xml(tmp_path / "index.xml"), "index.xml", tmp_path)
    assert leaves[0].href == REGIONAL and all(leaf.checksum_type == "md5" for leaf in leaves)
    assert ECTD_32.tree(tmp_path)[0]["label"].startswith("1 Administrative")
