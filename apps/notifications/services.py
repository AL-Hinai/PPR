"""Who hears about which status change, in-app and by email."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import translation

from apps.accounts.models import User
from apps.applications.models import Application

from .models import Notification

logger = logging.getLogger(__name__)
S = Application.Status

COMPANY_STATUSES = {
    S.VALIDATED, S.VALIDATION_FAILED, S.UNDER_REVIEW, S.INFO_REQUESTED, S.APPROVED, S.REJECTED,
}
HOD_STATUSES = {S.VALIDATED, S.REVIEW_COMPLETE}
REVIEWER_STATUSES = {S.UNDER_REVIEW, S.REVIEW_COMPLETE, S.APPROVED, S.REJECTED}


def recipients_for(application, status):
    users = []
    if status in COMPANY_STATUSES:
        users += list(User.objects.filter(company_id=application.company_id, is_active=True))
    if status in HOD_STATUSES:
        users += list(User.objects.filter(role=User.Role.HOD, is_active=True))
    if status in REVIEWER_STATUSES:
        # The lead and every module reviewer.
        if application.assigned_reviewer_id:
            users.append(application.assigned_reviewer)
        users += [a.reviewer for a in application.assignments.select_related("reviewer")]
    unique = {u.pk: u for u in users}
    return list(unique.values())


def notify_status_change(application, history_entry):
    status = history_entry.to_status
    users = [u for u in recipients_for(application, status) if u.pk != history_entry.actor_id]
    if history_entry.is_team_change:  # internal: the applicant's status did not change
        users = [u for u in users if not u.is_company]
    Notification.objects.bulk_create(
        Notification(user=u, application=application, status=status, note=history_entry.note_for(u)) for u in users
    )
    for user in users:
        if user.email:
            _send_email(user, application, status, history_entry.note_for(user))


def _send_email(user, application, status, note):
    with translation.override(user.preferred_language):
        context = {
            "user": user,
            "application": application,
            "status_label": Application.Status(status).label,
            "note": note,
        }
        subject = render_to_string("notifications/email_subject.txt", context).strip()
        body = render_to_string("notifications/email_body.txt", context)
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email])
    except Exception:  # email is best-effort; the in-app notification already exists
        logger.exception("Could not send notification email to %s", user.email)
