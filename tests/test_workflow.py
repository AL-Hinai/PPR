import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.applications import services
from apps.applications.models import Application, InfoRequest
from apps.applications.workflow import TransitionError, can_transition, transition
from apps.notifications.models import Notification
from apps.validation import samples

from .conftest import upload

S = Application.Status


def zip_file(data, name="package.zip"):
    return SimpleUploadedFile(name, data, content_type="application/zip")


@pytest.mark.django_db
def test_full_lifecycle(make_application, applicant, reviewer, hod, django_capture_on_commit_callbacks):
    application = make_application()
    upload(application, applicant, samples.build_package("0000"))

    with django_capture_on_commit_callbacks(execute=True):
        sequence, run = services.submit(application, applicant)
    assert sequence.is_accepted and application.status == S.VALIDATED
    assert application.reference_no.startswith("MA-")
    assert Notification.objects.filter(user=hod, status=S.VALIDATED).exists()

    with django_capture_on_commit_callbacks(execute=True):
        services.assign_reviewer(application, hod, reviewer)
    assert application.status == S.UNDER_REVIEW
    assert Notification.objects.filter(user=reviewer, status=S.UNDER_REVIEW).exists()

    services.request_information(application, reviewer, "Provide stability data.")
    assert application.status == S.INFO_REQUESTED

    response = zip_file(samples.build_package("0001", documents=samples.response_documents()))
    sequence, run = services.respond_to_info_request(application, applicant, response, "Stability data added.")
    assert sequence.number == "0001" and sequence.is_accepted
    assert application.status == S.UNDER_REVIEW
    assert application.info_requests.get().status == InfoRequest.Status.ANSWERED

    with pytest.raises(ValidationError):
        services.complete_review(application, reviewer, "APPROVE", "No section reviews yet")
    application.reviews.create(reviewer=reviewer, section="M3", assessment="ACCEPTABLE", comments="OK")
    services.complete_review(application, reviewer, "APPROVE", "Recommend approval")
    assert application.status == S.REVIEW_COMPLETE

    decision = services.decide(application, hod, "APPROVED", "All requirements met")
    assert application.status == S.APPROVED
    assert decision.approval_no.startswith("PPR-") and decision.valid_until

    statuses = list(application.history.values_list("to_status", flat=True))
    assert statuses == [
        S.SUBMITTED, S.VALIDATING, S.VALIDATED, S.UNDER_REVIEW, S.INFO_REQUESTED,
        S.UNDER_REVIEW, S.REVIEW_COMPLETE, S.APPROVED,
    ]


@pytest.mark.django_db
def test_failed_validation_then_resubmit(make_application, applicant):
    application = make_application()
    broken = samples.build_files()
    broken["index-md5.txt"] = b"bad"
    upload(application, applicant, samples.to_zip(broken))
    sequence, run = services.submit(application, applicant)
    assert application.status == S.VALIDATION_FAILED and run.error_count == 1

    upload(application, applicant, samples.build_package("0000"))
    sequence, run = services.submit(application, applicant)
    assert sequence.number == "0000" and sequence.is_accepted
    assert application.status == S.VALIDATED


@pytest.mark.django_db
def test_failed_response_keeps_info_request_open(make_application, applicant, reviewer, hod):
    application = make_application()
    upload(application, applicant, samples.build_package("0000"))
    services.submit(application, applicant)
    services.assign_reviewer(application, hod, reviewer)
    services.request_information(application, reviewer, "Questions")

    bad = zip_file(samples.build_package("0000"))  # wrong sequence number
    sequence, run = services.respond_to_info_request(application, applicant, bad, "note")
    assert not sequence.is_accepted
    assert application.status == S.INFO_REQUESTED
    assert application.open_info_request() is not None


@pytest.mark.django_db
def test_submit_requires_a_package(make_application, applicant):
    with pytest.raises(ValidationError):
        services.submit(make_application(), applicant)


@pytest.mark.django_db
def test_transition_permissions(make_application, applicant, other_applicant, reviewer, reviewer2, hod):
    application = make_application()
    assert can_transition(application, S.SUBMITTED, applicant)
    assert not can_transition(application, S.SUBMITTED, other_applicant)  # different company
    assert not can_transition(application, S.SUBMITTED, hod)
    assert not can_transition(application, S.APPROVED, hod)  # not an allowed edge from DRAFT

    application.status = S.UNDER_REVIEW
    application.assigned_reviewer = reviewer
    assert can_transition(application, S.REVIEW_COMPLETE, reviewer)
    assert not can_transition(application, S.REVIEW_COMPLETE, reviewer2)  # not assigned
    assert not can_transition(application, S.REVIEW_COMPLETE, applicant)

    application.status = S.REVIEW_COMPLETE
    assert can_transition(application, S.APPROVED, hod)
    assert not can_transition(application, S.APPROVED, reviewer)
    with pytest.raises(TransitionError):
        transition(application, S.APPROVED, applicant)
