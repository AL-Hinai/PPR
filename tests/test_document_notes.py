"""Review notes on dossier pages: who may see, add and change them, and how they are collected."""
import pytest
from django.urls import reverse

from apps.applications import services
from apps.applications.models import DocumentNote
from apps.validation import samples

from .conftest import upload

pytestmark = [pytest.mark.req("URS-15"), pytest.mark.req("URS-13")]

PATH = "m3/32-body-data/32p-drug-prod/product-1/32p8-stab/stability-summary.pdf"


@pytest.fixture
def under_review(make_application, applicant, reviewer, hod):
    application = make_application()
    sequence = upload(application, applicant, samples.build_package("0000"))
    services.submit(application, applicant)
    services.assign_reviewer(application, hod, reviewer)
    return application, sequence


def _add(client, application, sequence, body="Shelf life not justified", page=2, quote="Proposed shelf life: 24 months"):
    url = reverse("applications:notes", args=[application.pk, sequence.pk])
    return client.post(url, {"path": PATH, "page": page, "body": body, "quote": quote})


@pytest.mark.django_db
def test_reviewer_adds_a_note_on_a_page(client, under_review, reviewer):
    application, sequence = under_review
    client.force_login(reviewer)
    response = _add(client, application, sequence)
    assert response.status_code == 200 and b"Shelf life not justified" in response.content
    note = DocumentNote.objects.get()
    assert (note.page, note.section, note.author, note.quote) == (2, "M3", reviewer, "Proposed shelf life: 24 months")
    viewer = client.get(reverse("applications:sequence_document", args=[application.pk, sequence.pk, PATH]))
    assert b"Review notes" in viewer.content and b"Shelf life not justified" in viewer.content


@pytest.mark.django_db
def test_applicant_never_sees_or_adds_notes(client, under_review, reviewer, applicant):
    application, sequence = under_review
    client.force_login(reviewer)
    _add(client, application, sequence)
    client.force_login(applicant)
    viewer = client.get(reverse("applications:sequence_document", args=[application.pk, sequence.pk, PATH]))
    assert viewer.status_code == 200
    assert b"Review notes" not in viewer.content and b"Shelf life not justified" not in viewer.content
    assert _add(client, application, sequence).status_code == 403
    assert client.get(reverse("applications:notes_print", args=[application.pk])).status_code == 403


@pytest.mark.django_db
def test_reviewers_outside_the_team_cannot_see_notes(client, under_review, reviewer, reviewer2):
    application, sequence = under_review
    client.force_login(reviewer)
    _add(client, application, sequence)
    client.force_login(reviewer2)
    url = reverse("applications:notes", args=[application.pk, sequence.pk]) + f"?path={PATH}"
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_only_the_author_edits_or_deletes(client, under_review, reviewer, hod):
    application, sequence = under_review
    client.force_login(reviewer)
    _add(client, application, sequence)
    note = DocumentNote.objects.get()
    client.force_login(hod)  # sees the note, but cannot change it
    assert client.post(reverse("applications:note_edit", args=[application.pk, note.pk]), {"body": "x"}).status_code == 403
    assert client.post(reverse("applications:note_delete", args=[application.pk, note.pk])).status_code == 403
    client.force_login(reviewer)
    client.post(reverse("applications:note_edit", args=[application.pk, note.pk]), {"body": "Justify 36 months"})
    note.refresh_from_db()
    assert note.body == "Justify 36 months"
    client.post(reverse("applications:note_delete", args=[application.pk, note.pk]))
    assert not DocumentNote.objects.exists()


@pytest.mark.django_db
def test_notes_are_collected_for_the_assessment(client, under_review, reviewer):
    application, sequence = under_review
    client.force_login(reviewer)
    _add(client, application, sequence, body="First point", page=1)
    _add(client, application, sequence, body="Second point", page=3, quote="")
    report = client.get(reverse("applications:notes_print", args=[application.pk])).content.decode()
    assert "Module 3" in report and "First point" in report and "Second point" in report
    text = client.get(reverse("applications:my_notes", args=[application.pk]) + "?section=M3").content.decode()
    assert text.splitlines()[0] == f"- 0000/{PATH}, p. 1: First point"
    assert "p. 3: Second point" in text
    assert client.get(reverse("applications:my_notes", args=[application.pk]) + "?section=M5").content == b""


@pytest.mark.django_db
def test_empty_note_and_unknown_document_are_rejected(client, under_review, reviewer):
    application, sequence = under_review
    client.force_login(reviewer)
    assert _add(client, application, sequence, body="  ").status_code == 400
    url = reverse("applications:notes", args=[application.pk, sequence.pk])
    assert client.post(url, {"path": "../../etc/passwd", "page": 1, "body": "x"}).status_code == 404
    assert not DocumentNote.objects.exists()
