"""Use-cases behind the views. Each one validates state, does the work and moves the workflow."""
import datetime
import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.validation.engine import validate_sequence

from .models import Application, Decision, InfoRequest, Sequence, StatusHistory
from .workflow import transition

S = Application.Status


def store_sequence(application, user, uploaded_file, description="") -> Sequence:
    """Save an uploaded zip as the application's next sequence (replacing an unsubmitted one)."""
    for old in application.sequences.filter(validation_status=Sequence.ValidationStatus.PENDING):
        old.package.delete(save=False)
        old.delete()

    digest = hashlib.sha256()
    for chunk in uploaded_file.chunks():
        digest.update(chunk)
    uploaded_file.seek(0)

    sequence = Sequence(
        application=application,
        number=application.next_sequence_number(),
        original_filename=uploaded_file.name[:255],
        size=uploaded_file.size,
        sha256=digest.hexdigest(),
        description=description,
        uploaded_by=user,
    )
    sequence.package.save("package.zip", uploaded_file, save=False)
    sequence.save()
    return sequence


def submit(application, user):
    """Company submits (or resubmits after a failed validation); validation runs immediately."""
    sequence = application.pending_sequence()
    if sequence is None:
        raise ValidationError(_("Upload an eCTD package before submitting."))
    if application.status == S.DRAFT:
        transition(application, S.SUBMITTED, user)
        transition(application, S.VALIDATING)
    else:
        transition(application, S.VALIDATING, user)
    run = validate_sequence(sequence)
    transition(application, S.VALIDATED if sequence.is_accepted else S.VALIDATION_FAILED)
    return sequence, run


def respond_to_info_request(application, user, uploaded_file, note):
    """The company answers questions with a new sequence. It must pass validation to count."""
    info_request = application.open_info_request()
    if application.status != S.INFO_REQUESTED or info_request is None:
        raise ValidationError(_("There is no open information request."))
    sequence = store_sequence(application, user, uploaded_file, description=_("Response to questions"))
    run = validate_sequence(sequence)
    if sequence.is_accepted:
        with transaction.atomic():
            info_request.status = InfoRequest.Status.ANSWERED
            info_request.response_sequence = sequence
            info_request.response_note = note
            info_request.answered_at = timezone.now()
            info_request.save()
            transition(application, S.UNDER_REVIEW, user, note=note)
    return sequence, run


def assign_reviewer(application, hod, reviewer):
    with transaction.atomic():
        previous = application.assigned_reviewer
        application.assigned_reviewer = reviewer
        application.save(update_fields=["assigned_reviewer", "updated_at"])
        note = _("Assigned to %(name)s") % {"name": reviewer.display_name}
        if application.status == S.VALIDATED:
            return transition(application, S.UNDER_REVIEW, hod, note=note)
        if application.status in (S.UNDER_REVIEW, S.INFO_REQUESTED) and previous != reviewer:
            from apps.notifications.services import notify_status_change

            entry = StatusHistory.objects.create(
                application=application,
                from_status=application.status,
                to_status=application.status,
                actor=hod,
                note=note,
            )
            transaction.on_commit(lambda: notify_status_change(application, entry))
            return entry
        raise ValidationError(_("A reviewer cannot be assigned at this stage."))


def request_information(application, reviewer, questions, due_date=None):
    with transaction.atomic():
        InfoRequest.objects.create(
            application=application, raised_by=reviewer, questions=questions, due_date=due_date
        )
        transition(application, S.INFO_REQUESTED, reviewer, note=questions)


def complete_review(application, reviewer, recommendation, summary):
    if not application.reviews.exists():
        raise ValidationError(_("Record at least one section review before completing the review."))
    with transaction.atomic():
        application.recommendation = recommendation
        application.recommendation_note = summary
        application.save(update_fields=["recommendation", "recommendation_note", "updated_at"])
        transition(application, S.REVIEW_COMPLETE, reviewer, note=summary)


def return_to_reviewer(application, hod, note):
    transition(application, S.UNDER_REVIEW, hod, note=note)


def _add_years(date, years):
    try:
        return date.replace(year=date.year + years)
    except ValueError:  # 29 February
        return date.replace(year=date.year + years, day=28)


def decide(application, hod, outcome, justification):
    with transaction.atomic():
        decision = Decision.objects.create(
            application=application, hod=hod, outcome=outcome, justification=justification
        )
        if outcome == Decision.Outcome.APPROVED:
            today = timezone.localdate()
            decision.approval_no = f"PPR-{today:%Y}-{decision.pk:05d}"
            decision.valid_until = _add_years(today, settings.APPROVAL_VALIDITY_YEARS) - datetime.timedelta(days=1)
            decision.save(update_fields=["approval_no", "valid_until"])
            transition(application, S.APPROVED, hod, note=justification)
        else:
            transition(application, S.REJECTED, hod, note=justification)
    return decision
