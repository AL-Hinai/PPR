"""Reviewer specialties: decided by the Head of Department, followed by everyone else."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import CtdSection, User


def set_specialties(reviewer, hod, sections):
    """The HOD sets which CTD modules a reviewer may be assigned.

    A module cannot be taken away while the reviewer still holds it on an active review:
    the HOD reassigns that module first, so no assessment is left without a qualified owner.
    """
    from apps.applications.models import Application, ReviewAssignment

    if not hod.is_hod:
        raise PermissionDenied
    if not reviewer.is_reviewer:
        raise ValidationError(_("Only reviewers have review specialties."))
    sections = [s for s in CtdSection.values if s in set(sections)]
    removed = set(reviewer.specialties or []) - set(sections)
    active = ReviewAssignment.objects.filter(
        reviewer=reviewer,
        section__in=removed,
        # REVIEW_COMPLETE too: the HOD can send it back, and the module owner must still be qualified.
        application__status__in=[
            Application.Status.UNDER_REVIEW, Application.Status.INFO_REQUESTED, Application.Status.REVIEW_COMPLETE,
        ],
    ).select_related("application")
    if active:
        held = ", ".join(f"{a.application.reference_no} {a.section}" for a in active)
        raise ValidationError(
            _("%(name)s still holds these modules on active reviews: %(held)s. Reassign them first.")
            % {"name": reviewer.display_name, "held": held}
        )
    reviewer.specialties = sections
    reviewer.specialties_updated_by = hod
    reviewer.specialties_updated_at = timezone.now()
    reviewer.save(update_fields=["specialties", "specialties_updated_by", "specialties_updated_at"])
    return reviewer


def set_default_lead(reviewer, hod):
    """The HOD names the reviewer who leads automatically assembled teams (None clears it)."""
    if not hod.is_hod:
        raise PermissionDenied
    if reviewer is not None and not (reviewer.is_reviewer and reviewer.is_active):
        raise ValidationError(_("Only an active reviewer can be the default lead."))
    User.objects.filter(default_lead=True).exclude(pk=getattr(reviewer, "pk", None)).update(default_lead=False)
    if reviewer is not None and not reviewer.default_lead:
        reviewer.default_lead = True
        reviewer.save(update_fields=["default_lead"])
    return reviewer


def coverage():
    """How many active reviewers can take each module, so the HOD sees gaps."""
    reviewers = list(User.objects.filter(role=User.Role.REVIEWER, is_active=True))
    return [
        {
            "section": value,
            "label": label,
            "short": str(label).split("–", 1)[-1].strip(),  # "Module 3 – Quality" -> "Quality"
            "count": sum(1 for r in reviewers if value in (r.specialties or [])),
        }
        for value, label in CtdSection.choices
    ]
