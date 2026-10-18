"""VALIDATION_MODE = "queue": submissions wait for run_validation_worker instead of validating in the request."""
import datetime

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.applications import services
from apps.applications.models import Application, Sequence
from apps.notifications.models import Notification
from apps.validation import samples, worker
from apps.validation.models import ValidationJob

from .conftest import upload

pytestmark = [pytest.mark.req("URS-07"), pytest.mark.req("URS-10"), pytest.mark.req("URS-20")]

S = Application.Status
V = Sequence.ValidationStatus
J = ValidationJob.Status


@pytest.fixture(autouse=True)
def queue_mode(settings):
    settings.VALIDATION_MODE = "queue"


def _submitted(make_application, applicant, data=None, application_type="GENERIC"):
    application = make_application(application_type)
    upload(application, applicant, data or samples.build_package("0000", application_type))
    sequence, run = services.submit(application, applicant)
    return application, sequence, run


@pytest.mark.django_db
def test_submit_queues_and_the_worker_finishes_the_workflow(make_application, applicant):
    application, sequence, run = _submitted(make_application, applicant)
    assert run is None
    application.refresh_from_db(), sequence.refresh_from_db()
    assert application.status == S.VALIDATING and sequence.validation_status == V.QUEUED
    assert application.validation_in_progress()

    call_command("run_validation_worker", once=True)

    application.refresh_from_db(), sequence.refresh_from_db()
    assert application.status == S.VALIDATED
    assert sequence.validation_status == V.PASSED
    job = sequence.jobs.get()
    assert job.status == J.DONE and job.attempts == 1 and job.finished_at
    assert sequence.document_texts.exists()  # text indexed for search and the assistant


@pytest.mark.django_db
def test_failed_package_ends_in_validation_failed(make_application, applicant):
    broken = samples.build_files("0000", application_type="GENERIC")
    del broken["index-md5.txt"]
    application, _, _ = _submitted(make_application, applicant, samples.to_zip(broken))
    worker.run_pending()
    application.refresh_from_db()
    assert application.status == S.VALIDATION_FAILED


@pytest.mark.django_db
def test_no_upload_while_a_sequence_is_queued(make_application, applicant):
    application, _, _ = _submitted(make_application, applicant)
    with pytest.raises(ValidationError):
        services.store_sequence(application, applicant,
                                SimpleUploadedFile("again.zip", samples.build_package("0000", "GENERIC")))


@pytest.mark.django_db
def test_response_to_questions_is_answered_by_the_worker(make_application, applicant, reviewer, hod):
    application, _, _ = _submitted(make_application, applicant)
    worker.run_pending()
    application.refresh_from_db()
    services.assign_reviewer(application, hod, reviewer)
    services.request_information(application, reviewer, "Provide stability data.")
    response = SimpleUploadedFile("r.zip", samples.build_package("0001", "GENERIC", documents=samples.response_documents()))
    sequence, run = services.respond_to_info_request(application, applicant, response, "Data added.")
    assert run is None
    application.refresh_from_db()
    assert application.status == S.INFO_REQUESTED  # until the worker has validated the response

    worker.run_pending()
    application.refresh_from_db()
    assert application.status == S.UNDER_REVIEW
    info = application.info_requests.get()
    assert info.response_sequence_id == sequence.pk and info.response_note == "Data added."
    assert application.history.filter(to_status=S.UNDER_REVIEW, actor=applicant).exists()


@pytest.mark.django_db
def test_failed_response_notifies_the_company(make_application, applicant, reviewer, hod):
    application, _, _ = _submitted(make_application, applicant)
    worker.run_pending()
    application.refresh_from_db()
    services.assign_reviewer(application, hod, reviewer)
    services.request_information(application, reviewer, "Provide stability data.")
    broken = samples.build_files("0001", application_type="GENERIC", documents=samples.response_documents())
    del broken["index-md5.txt"]
    services.respond_to_info_request(application, applicant, SimpleUploadedFile("r.zip", samples.to_zip(broken)), "")
    worker.run_pending()
    application.refresh_from_db()
    assert application.status == S.INFO_REQUESTED
    assert Notification.objects.filter(user=applicant, note__contains="failed technical validation").exists()


@pytest.mark.django_db
def test_crashing_job_is_retried_then_reported(make_application, applicant, hod, monkeypatch):
    application, sequence, _ = _submitted(make_application, applicant)
    monkeypatch.setattr(worker, "validate_sequence", lambda s: 1 / 0)
    for _ in range(worker.MAX_ATTEMPTS):
        worker.run_pending()
    job = sequence.jobs.get()
    assert job.status == J.FAILED and job.attempts == worker.MAX_ATTEMPTS
    assert "ZeroDivisionError" in job.error
    assert Notification.objects.filter(user=hod, note__contains="needs attention").exists()


@pytest.mark.django_db
def test_stale_running_job_is_requeued(make_application, applicant):
    _, sequence, _ = _submitted(make_application, applicant)
    job = worker.claim_next()
    ValidationJob.objects.filter(pk=job.pk).update(claimed_at=timezone.now() - datetime.timedelta(hours=1))
    assert worker.claim_next() is None  # still RUNNING
    assert worker.requeue_stale() == 1
    assert worker.run_pending() == 1
    sequence.refresh_from_db()
    assert sequence.validation_status == V.PASSED


@pytest.mark.django_db
def test_progress_endpoint_refreshes_the_page_when_done(client, make_application, applicant):
    application, _, _ = _submitted(make_application, applicant)
    client.force_login(applicant)
    url = reverse("applications:validation_status", args=[application.pk])
    assert client.get(url).status_code == 204
    detail = client.get(reverse("applications:detail", args=[application.pk]))
    assert url.encode() in detail.content  # the polling banner
    worker.run_pending()
    assert client.get(url)["HX-Refresh"] == "true"
