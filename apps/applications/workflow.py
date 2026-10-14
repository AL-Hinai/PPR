"""Application state machine.

Every status change goes through ``transition()`` so permissions, the audit
trail and notifications are handled in one place.
"""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import Application, StatusHistory

S = Application.Status
R = User.Role
SYSTEM = "SYSTEM"  # actor=None: the platform itself (e.g. the validator)

# (from, to) -> who may perform it
TRANSITIONS = {
    (S.DRAFT, S.SUBMITTED): {R.COMPANY},
    (S.SUBMITTED, S.VALIDATING): {SYSTEM},
    (S.VALIDATION_FAILED, S.VALIDATING): {R.COMPANY},
    (S.VALIDATING, S.VALIDATED): {SYSTEM},
    (S.VALIDATING, S.VALIDATION_FAILED): {SYSTEM},
    (S.VALIDATED, S.UNDER_REVIEW): {R.HOD},
    (S.UNDER_REVIEW, S.INFO_REQUESTED): {R.REVIEWER},
    (S.INFO_REQUESTED, S.UNDER_REVIEW): {R.COMPANY},
    (S.UNDER_REVIEW, S.REVIEW_COMPLETE): {R.REVIEWER},
    (S.REVIEW_COMPLETE, S.UNDER_REVIEW): {R.HOD},
    (S.REVIEW_COMPLETE, S.APPROVED): {R.HOD},
    (S.REVIEW_COMPLETE, S.REJECTED): {R.HOD},
}


class TransitionError(PermissionDenied):
    pass


def can_transition(application, to_status, actor):
    allowed = TRANSITIONS.get((application.status, to_status))
    if not allowed:
        return False
    if actor is None:
        return SYSTEM in allowed
    if actor.role not in allowed:
        return False
    if actor.role == R.COMPANY:
        return actor.company_id == application.company_id
    if actor.role == R.REVIEWER:
        return application.assigned_reviewer_id == actor.pk
    return True


def transition(application, to_status, actor=None, note=""):
    if not can_transition(application, to_status, actor):
        raise TransitionError(f"{application.status} -> {to_status} is not allowed for this user.")

    from apps.notifications.services import notify_status_change

    with transaction.atomic():
        entry = StatusHistory.objects.create(
            application=application,
            from_status=application.status,
            to_status=to_status,
            actor=actor,
            note=note,
        )
        application.status = to_status
        fields = ["status", "updated_at"]
        if to_status == S.SUBMITTED:
            application.submitted_at = timezone.now()
            fields.append("submitted_at")
        application.save(update_fields=fields)
        transaction.on_commit(lambda: notify_status_change(application, entry))
    return entry
