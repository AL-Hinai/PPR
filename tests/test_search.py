"""Cross-dossier search is limited to the applications the reader may open."""
import pytest
from django.urls import reverse

from apps.applications import services
from apps.applications.search import search_dossiers
from apps.assistant.documents import index_sequences
from apps.validation import samples

from .conftest import upload

pytestmark = [pytest.mark.req("URS-16"), pytest.mark.req("URS-13")]


@pytest.fixture
def indexed(make_application, applicant, other_applicant, reviewer, hod):
    mine = make_application()
    upload(mine, applicant, samples.build_package("0000"))
    services.submit(mine, applicant)
    services.assign_reviewer(mine, hod, reviewer)
    theirs = make_application(user=other_applicant)
    upload(theirs, other_applicant, samples.build_package("0000"))
    services.submit(theirs, other_applicant)
    index_sequences([*mine.accepted_sequences(), *theirs.accepted_sequences()], budget=float("inf"))
    return mine, theirs


@pytest.mark.django_db
def test_text_hits_are_grouped_by_document_with_titles(indexed, reviewer):
    mine, _ = indexed
    result = search_dossiers(reviewer, "shelf life storage")
    titles = {d["title"] for d in result["documents"]}
    assert "Stability summary and conclusion" in titles
    assert {d["application"].pk for d in result["documents"]} == {mine.pk}  # not assigned to the other one
    stability = next(d for d in result["documents"] if d["title"] == "Stability summary and conclusion")
    assert stability["section"].startswith("3 Quality") and stability["pages"][0]["page"] == 1
    assert "<mark" in stability["pages"][0]["snippet"]


@pytest.mark.django_db
def test_companies_only_find_their_own_dossiers(indexed, applicant):
    mine, theirs = indexed
    result = search_dossiers(applicant, "paracetamol")
    assert {d["application"].pk for d in result["documents"]} == {mine.pk}


@pytest.mark.django_db
def test_hod_searches_every_submitted_dossier_and_metadata(indexed, hod):
    mine, theirs = indexed
    result = search_dossiers(hod, "bioequivalence")
    assert {d["application"].pk for d in result["documents"]} == {mine.pk, theirs.pk}
    assert search_dossiers(hod, mine.reference_no)["applications"] == [mine]


@pytest.mark.django_db
def test_search_page(client, indexed, reviewer):
    client.force_login(reviewer)
    response = client.get(reverse("applications:search"), {"q": "shelf life"})
    assert response.status_code == 200
    assert b"Stability summary and conclusion" in response.content and b"#page=1" in response.content
    assert b'<script>' not in response.content  # snippets are escaped before highlighting
