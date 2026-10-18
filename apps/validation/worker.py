"""Background validation: claims queued ``ValidationJob``s and runs them (``manage.py run_validation_worker``).

Jobs are claimed with a conditional UPDATE, so several workers (or a restarted one) never run the same job.
A job left RUNNING longer than ``STALE_AFTER`` (the worker died) is queued again, up to ``MAX_ATTEMPTS``.
"""
import datetime
import logging
import math
import traceback

from django.db.models import F
from django.utils import timezone

from .engine import validate_sequence
from .models import ValidationJob

logger = logging.getLogger(__name__)
J = ValidationJob.Status
MAX_ATTEMPTS = 3
STALE_AFTER = datetime.timedelta(minutes=30)


def claim_next() -> ValidationJob | None:
    for pk in ValidationJob.objects.filter(status=J.QUEUED).values_list("pk", flat=True)[:10]:
        claimed = ValidationJob.objects.filter(pk=pk, status=J.QUEUED).update(
            status=J.RUNNING, claimed_at=timezone.now(), attempts=F("attempts") + 1
        )
        if claimed:
            return ValidationJob.objects.select_related("sequence__application", "requested_by").get(pk=pk)
    return None


def process(job: ValidationJob) -> None:
    from apps.applications.services import finish_validation

    sequence = job.sequence
    try:
        validate_sequence(sequence)
        finish_validation(sequence, job.kind, job.requested_by, job.note)
    except Exception:
        logger.exception("Validation job %s failed", job.pk)
        _retry_or_fail(job, traceback.format_exc())
        return
    job.status, job.finished_at, job.error = J.DONE, timezone.now(), ""
    job.save(update_fields=["status", "finished_at", "error"])
    if sequence.is_accepted:
        _index_text(sequence)


def _index_text(sequence) -> None:
    """Extract the dossier text now, so search and the assistant do not wait for it later."""
    from apps.assistant.documents import index_sequences

    try:
        index_sequences([sequence], budget=math.inf)
    except Exception:  # text indexing is a convenience; the validation result stands
        logger.exception("Text indexing failed for %s", sequence)


def _retry_or_fail(job: ValidationJob, error: str) -> None:
    job.error = error[-5000:]
    if job.attempts < MAX_ATTEMPTS:
        job.status = J.QUEUED
        job.save(update_fields=["status", "error"])
        return
    job.status, job.finished_at = J.FAILED, timezone.now()
    job.save(update_fields=["status", "error", "finished_at"])
    from apps.notifications.services import notify_staff

    notify_staff(job.sequence.application,
                 f"Validation of sequence {job.sequence.number} failed {job.attempts} times and needs attention "
                 f"(validation job {job.pk}).")


def requeue_stale() -> int:
    """Jobs whose worker stopped mid-run: try again, or give up after MAX_ATTEMPTS."""
    stale = ValidationJob.objects.filter(status=J.RUNNING, claimed_at__lt=timezone.now() - STALE_AFTER)
    count = 0
    for job in stale.select_related("sequence__application"):
        _retry_or_fail(job, f"Worker stopped while running the job (claimed {job.claimed_at:%Y-%m-%d %H:%M}).")
        count += 1
    return count


def run_pending() -> int:
    """Process every queued job once; returns how many ran."""
    count = 0
    while (job := claim_next()) is not None:
        process(job)
        count += 1
    return count
