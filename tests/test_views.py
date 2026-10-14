"""Access control and page rendering through the real URLs."""
import pytest
from django.urls import reverse

from apps.applications import services
from apps.applications.models import Application
from apps.validation import samples

from .conftest import upload

S = Application.Status


@pytest.fixture
def approved_application(make_application, applicant, reviewer, hod):
    application = make_application()
    upload(application, applicant, samples.build_package("0000"))
    services.submit(application, applicant)
    services.assign_reviewer(application, hod, reviewer)
    application.reviews.create(reviewer=reviewer, section="M3", assessment="ACCEPTABLE", comments="OK")
    services.complete_review(application, reviewer, "APPROVE", "Recommend approval")
    services.decide(application, hod, "APPROVED", "OK")
    return application


def pages(application):
    sequence = application.sequences.get()
    return [
        reverse("core:dashboard"),
        reverse("applications:list"),
        *[f"{reverse('applications:detail', args=[application.pk])}?tab={t}" for t in ("overview", "sequences", "review", "history")],
        reverse("applications:sequence", args=[application.pk, sequence.pk]),
        reverse("applications:sequence_csv", args=[application.pk, sequence.pk]),
        reverse("applications:certificate", args=[application.pk]),
        reverse("notifications:list"),
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("who", ["applicant", "reviewer", "hod"])
def test_pages_render_for_each_role(client, approved_application, request, who):
    client.force_login(request.getfixturevalue(who))
    for url in pages(approved_application):
        response = client.get(url)
        assert response.status_code == 200, url


@pytest.mark.django_db
def test_pages_render_in_arabic_rtl(client, approved_application, applicant):
    client.force_login(applicant)
    client.cookies["django_language"] = "ar"
    response = client.get(reverse("applications:detail", args=[approved_application.pk]))
    assert response.status_code == 200
    assert 'dir="rtl"' in response.content.decode()


@pytest.mark.django_db
def test_other_company_cannot_see_application(client, approved_application, other_applicant, reviewer2):
    for user in (other_applicant, reviewer2):
        client.force_login(user)
        assert client.get(reverse("applications:detail", args=[approved_application.pk])).status_code == 404


@pytest.mark.django_db
def test_hod_does_not_see_drafts(client, make_application, hod):
    draft = make_application()
    client.force_login(hod)
    assert client.get(reverse("applications:detail", args=[draft.pk])).status_code == 404


@pytest.mark.django_db
def test_protected_document_download(client, approved_application, applicant, other_applicant):
    sequence = approved_application.sequences.get()
    url = reverse("applications:sequence_file", args=[approved_application.pk, sequence.pk, "m2/22-intro/introduction.pdf"])

    client.force_login(applicant)
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Security-Policy"] == "sandbox"
    assert b"".join(response.streaming_content).startswith(b"%PDF-")

    traversal = reverse("applications:sequence_file", args=[approved_application.pk, sequence.pk, "../../../config/settings/base.py"])
    assert client.get(traversal).status_code == 404

    client.force_login(other_applicant)
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_xml_documents_are_downloaded_not_rendered(client, approved_application, applicant):
    sequence = approved_application.sequences.get()
    client.force_login(applicant)
    response = client.get(reverse("applications:sequence_file", args=[approved_application.pk, sequence.pk, "index.xml"]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/octet-stream"
    assert "attachment" in response["Content-Disposition"]


@pytest.mark.django_db
def test_company_upload_and_submit_through_views(client, make_application, applicant):
    from django.core.files.uploadedfile import SimpleUploadedFile

    application = make_application()
    client.force_login(applicant)
    package = SimpleUploadedFile("dossier.zip", samples.build_package("0000"), content_type="application/zip")
    response = client.post(reverse("applications:upload", args=[application.pk]), {"package": package})
    assert response.status_code == 302
    response = client.post(reverse("applications:submit", args=[application.pk]))
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.status == S.VALIDATED


@pytest.mark.django_db
def test_upload_rejects_non_zip(client, make_application, applicant):
    from django.core.files.uploadedfile import SimpleUploadedFile

    application = make_application()
    client.force_login(applicant)
    response = client.post(
        reverse("applications:upload", args=[application.pk]),
        {"package": SimpleUploadedFile("dossier.pdf", b"%PDF-1.7")},
    )
    assert response.status_code == 400
    assert not application.sequences.exists()


@pytest.mark.django_db
def test_reviewer_actions_are_role_protected(client, approved_application, applicant):
    client.force_login(applicant)
    response = client.post(reverse("applications:decide", args=[approved_application.pk]), {"outcome": "APPROVED"})
    assert response.status_code == 403
