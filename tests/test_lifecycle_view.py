"""The current dossier applies new / replace / append / delete across the accepted sequences."""
import pytest
from django.urls import reverse

from apps.applications.lifecycle import build_current_view
from apps.validation import samples
from apps.validation.benchmark import INTRO
from apps.validation.samples import Doc

pytestmark = [pytest.mark.req("URS-14")]

QOS = "m2/23-qos/quality-overall-summary.pdf"


def _third_sequence_docs():
    """0002: delete the introduction, append an addendum to the quality overall summary."""
    cover, responses = samples.response_documents()[:2]
    return [
        cover,
        responses,
        Doc(INTRO, "Introduction", (samples.M2, "m2-2-introduction"), operation="delete",
            modified_file=f"../0000/index.xml#{samples.leaf_id('0000', INTRO)}"),
        Doc("m2/23-qos/qos-addendum.pdf", "Quality overall summary – addendum",
            (samples.M2, "m2-3-quality-overall-summary", "m2-3-introduction"), operation="append",
            modified_file=f"../0000/index.xml#{samples.leaf_id('0000', QOS)}"),
    ]


def _leaves(nodes):
    for node in nodes:
        yield from node["leaves"]
        yield from _leaves(node["children"])


@pytest.fixture
def three_sequences(db, validate, make_application):
    application = make_application()
    for number, docs in (("0000", None), ("0001", samples.response_documents()), ("0002", _third_sequence_docs())):
        sequence, run, codes = validate(samples.build_package(number, documents=docs), application=application)
        assert codes == set(), list(run.findings.values_list("rule_code", "detail"))
    return application


def test_current_view_applies_every_operation(three_sequences):
    view = build_current_view(three_sequences)
    leaves = {leaf["title"]: leaf for leaf in _leaves(view["tree"])}
    assert view["sequences"] == ["0000", "0001", "0002"]

    original = leaves["Stability summary and conclusion"]
    updated = leaves["Stability summary and conclusion (updated)"]
    assert original["status"] == "replaced" and original["changed_in"] == "0001"
    assert updated["status"] == "current"
    assert [s["sequence"] for s in updated["history"]] == ["0000", "0001"]

    assert leaves["Introduction"]["status"] == "deleted" and leaves["Introduction"]["changed_in"] == "0002"
    addendum = leaves["Quality overall summary – addendum"]
    assert addendum["appends_to"] == "Quality overall summary" and addendum["status"] == "current"
    assert leaves["Quality overall summary"]["status"] == "current"
    assert view["counts"]["replaced"] == 1 and view["counts"]["deleted"] == 1
    assert not any(leaf["unresolved"] for leaf in leaves.values())


def test_current_dossier_tab_renders(client, three_sequences, applicant):
    client.force_login(applicant)
    response = client.get(reverse("applications:detail", args=[three_sequences.pk]) + "?tab=dossier")
    assert response.status_code == 200
    body = response.content.decode()
    assert "Stability summary and conclusion (updated)" in body
    assert "replaced in 0001" in body and "deleted in 0002" in body
