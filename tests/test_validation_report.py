"""Printable validation report and the link to it in notification emails."""
import pytest
from django.core import mail
from django.urls import reverse

from apps.applications import services
from apps.validation import samples

from .conftest import upload

pytestmark = [pytest.mark.req("URS-06"), pytest.mark.req("URS-20")]


def _failed_sequence(make_application, applicant):
    application = make_application()
    broken = samples.build_files("0000")
    broken["m2/22-intro/notes.pdf"] = samples.make_pdf("stray")  # BR-05 warning
    del broken["index-md5.txt"]  # BR-02 error
    sequence = upload(application, applicant, samples.to_zip(broken))
    services.submit(application, applicant)
    return application, sequence


@pytest.mark.django_db
def test_short_report_lists_errors_and_long_report_everything(client, make_application, applicant):
    application, sequence = _failed_sequence(make_application, applicant)
    client.force_login(applicant)
    url = reverse("applications:sequence_report", args=[application.pk, sequence.pk])
    short = client.get(url + "?mode=short").content.decode()
    full = client.get(url).content.decode()
    assert "BR-02" in short and "BR-05" not in short
    assert "BR-02" in full and "BR-05" in full
    assert "Failed" in full and sequence.sha256 in full


@pytest.mark.django_db
def test_other_companies_cannot_open_the_report(client, make_application, applicant, other_applicant):
    application, sequence = _failed_sequence(make_application, applicant)
    client.force_login(other_applicant)
    assert client.get(reverse("applications:sequence_report", args=[application.pk, sequence.pk])).status_code == 404


@pytest.mark.django_db
def test_validation_email_links_to_the_report(settings, make_application, applicant,
                                             django_capture_on_commit_callbacks):
    settings.SITE_URL = "https://ppr.example.org"
    with django_capture_on_commit_callbacks(execute=True):
        application, sequence = _failed_sequence(make_application, applicant)
    expected = "https://ppr.example.org" + reverse("applications:sequence_report", args=[application.pk, sequence.pk])
    assert any(expected in message.body for message in mail.outbox)
