"""Use-cases behind the views. Each one validates state, does the work and moves the workflow."""
import datetime
import hashlib

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.validation.engine import validate_sequence

from .models import Application, Decision, InfoRequest, Review, ReviewAssignment, Sequence, StatusHistory
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
    if sequence.is_accepted and settings.AUTO_ASSIGN_REVIEW_TEAMS:
        auto_assign_review_team(application)
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


def assign_review_team(application, hod, lead, sections, note_prefix=""):
    """The assessment is split: one specialist per CTD module, and a lead reviewer.

    ``sections`` maps a CtdSection value to a reviewer (None leaves the module unassigned).
    Every module required for the application type must be assigned, each reviewer must be
    specialised in their module, and the lead must be on the team. ``hod`` is None when the
    platform assembles the team itself (``auto_assign_review_team``).
    """
    sections = {section: reviewer for section, reviewer in sections.items() if reviewer is not None}
    errors = []
    missing = [s for s in application.required_sections() if s not in sections]
    if missing:
        errors.append(_("Assign a reviewer to every required module: %(modules)s.") % {"modules": ", ".join(missing)})
    for section, reviewer in sorted(sections.items()):
        if not reviewer.can_review(section):
            errors.append(
                _("%(name)s is not specialised in %(module)s.") % {"name": reviewer.display_name, "module": section}
            )
    if lead is None or lead.pk not in {r.pk for r in sections.values()}:
        errors.append(_("The lead reviewer must be one of the module reviewers."))
    if errors:
        raise ValidationError(errors)
    if application.status not in (S.VALIDATED, S.UNDER_REVIEW, S.INFO_REQUESTED):
        raise ValidationError(_("A review team cannot be assigned at this stage."))

    with transaction.atomic():
        before = {a.section: a.reviewer_id for a in application.assignments.all()}
        previous_lead = application.assigned_reviewer_id
        application.assignments.exclude(section__in=sections).delete()
        for section, reviewer in sections.items():
            ReviewAssignment.objects.update_or_create(
                application=application, section=section, defaults={"reviewer": reviewer, "assigned_by": hod}
            )
        application.assigned_reviewer = lead
        application.save(update_fields=["assigned_reviewer", "updated_at"])

        team = "; ".join(f"{section}: {reviewer.display_name}" for section, reviewer in sorted(sections.items()))
        note = note_prefix + _("Lead reviewer: %(lead)s. Modules – %(team)s") % {"lead": lead.display_name, "team": team}
        if application.status == S.VALIDATED:
            return transition(application, S.UNDER_REVIEW, hod, note=note)
        if before == {s: r.pk for s, r in sections.items()} and previous_lead == lead.pk:
            return None  # nothing changed
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


def auto_assign_review_team(application):
    """Assemble the review team from reviewer specialties, without the HOD.

    Each required module goes to the qualified active reviewer with the fewest modules on
    active reviews, counting the ones just given out for this application, so a reviewer
    qualified for everything does not collect the whole dossier (ties: the narrower
    specialist, then by name). The lead is the HOD's default lead when they are on the
    team, otherwise the member covering the most modules. Returns None, leaving the
    application for the HOD, when some required module has no qualified reviewer.
    """
    from apps.accounts.models import User

    active = [S.UNDER_REVIEW, S.INFO_REQUESTED]
    reviewers = list(
        User.objects.filter(role=User.Role.REVIEWER, is_active=True)
        .annotate(load=Count("review_assignments", filter=Q(review_assignments__application__status__in=active)))
        .order_by("first_name", "last_name", "username")
    )
    load = {r.pk: r.load for r in reviewers}
    sections = {}
    for section in application.required_sections():
        qualified = [r for r in reviewers if r.can_review(section)]
        if not qualified:
            return None
        chosen = min(qualified, key=lambda r: (load[r.pk], len(r.specialties)))  # min keeps name order on a tie
        sections[section] = chosen
        load[chosen.pk] += 1
    team = list({r.pk: r for r in sections.values()}.values())
    lead = next((r for r in team if r.default_lead), None)
    if lead is None:
        modules = {r.pk: sum(1 for x in sections.values() if x.pk == r.pk) for r in team}
        lead = max(team, key=lambda r: modules[r.pk])  # max keeps the first module's reviewer on a tie
    return assign_review_team(
        application, None, lead, sections, note_prefix=_("Assigned automatically from reviewer specialties. ")
    )


def assign_reviewer(application, hod, reviewer):
    """One reviewer as lead and for every required module (small applications, tests, demo data)."""
    return assign_review_team(application, hod, reviewer, {s: reviewer for s in application.required_sections()})


def add_review(application, reviewer, section, assessment, comments):
    """A module assessment, by the specialist assigned to that module."""
    if application.status != S.UNDER_REVIEW:
        raise ValidationError(_("Assessments can only be recorded while the application is under review."))
    if section not in application.sections_for(reviewer):
        raise ValidationError(_("You are not assigned to assess %(module)s for this application.") % {"module": section})
    return Review.objects.create(
        application=application, reviewer=reviewer, section=section, assessment=assessment, comments=comments
    )


def request_information(application, reviewer, questions, due_date=None, sections=None):
    """The lead sends questions about some modules (all assigned modules when ``sections`` is None).

    Once the applicant answers, those modules need a fresh assessment before the review can complete.
    """
    assigned = [a.section for a in application.assignments.all()]
    sections = assigned if sections is None else [s for s in assigned if s in set(sections)]
    if not sections:
        raise ValidationError(_("Choose the module or modules the questions concern."))
    with transaction.atomic():
        InfoRequest.objects.create(
            application=application, raised_by=reviewer, questions=questions, due_date=due_date, sections=sections
        )
        transition(application, S.INFO_REQUESTED, reviewer, note=questions)


def complete_review(application, reviewer, recommendation, summary):
    """The lead reviewer's recommendation, once every assigned module has been assessed."""
    if not application.assignments.exists():
        raise ValidationError(_("The Head of Department has not assigned the modules yet."))
    missing = application.missing_sections()
    if missing:
        raise ValidationError(
            _("Every assigned module needs an assessment from its reviewer first. Still missing: %(modules)s.")
            % {"modules": ", ".join(missing)}
        )
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
