"""Specialised review: one reviewer per CTD module, a lead reviewer, and who may do what."""
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.accounts.models import User
from apps.applications import services
from apps.applications.models import Application
from apps.assistant.agent import system_prompt
from apps.assistant.context import PageContext
from apps.notifications.models import Notification
from apps.validation import samples

from .conftest import upload

pytestmark = [pytest.mark.req("URS-08"), pytest.mark.req("URS-09")]

S = Application.Status


def _reviewer(username, sections):
    return User.objects.create_user(username=username, password="pw-Secret-123", role=User.Role.REVIEWER,
                                    specialties=sections, email=f"{username}@example.com")


@pytest.fixture
def team(db):
    return {
        "regulatory": _reviewer("regulatory", ["M1", "M2"]),
        "quality": _reviewer("quality", ["M3"]),
        "clinical": _reviewer("clinical", ["M5"]),
        "outsider": _reviewer("outsider", ["M3"]),
    }


@pytest.fixture
def generic(make_application, applicant):
    """A validated generic application: modules M1, M2, M3 and M5 are required."""
    application = make_application("GENERIC")
    upload(application, applicant, samples.build_package("0000", "GENERIC"))
    services.submit(application, applicant)
    assert application.required_sections() == ["M1", "M2", "M3", "M5"]
    return application


def _sections(team):
    return {"M1": team["regulatory"], "M2": team["regulatory"], "M3": team["quality"], "M5": team["clinical"]}


@pytest.mark.django_db
def test_hod_assigns_one_specialist_per_module(generic, hod, team, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        services.assign_review_team(generic, hod, team["quality"], _sections(team))
    assert generic.status == S.UNDER_REVIEW and generic.assigned_reviewer == team["quality"]
    assert dict(generic.assignments.values_list("section", "reviewer__username")) == {
        "M1": "regulatory", "M2": "regulatory", "M3": "quality", "M5": "clinical",
    }
    for name in ("regulatory", "quality", "clinical"):
        assert Notification.objects.filter(user=team[name], status=S.UNDER_REVIEW).exists()
    assert not Notification.objects.filter(user=team["outsider"]).exists()


@pytest.mark.django_db
def test_team_rules(generic, hod, team):
    sections = _sections(team)
    with pytest.raises(ValidationError, match="not specialised"):
        services.assign_review_team(generic, hod, team["quality"], {**sections, "M5": team["quality"]})
    with pytest.raises(ValidationError, match="required module"):
        services.assign_review_team(generic, hod, team["quality"], {**sections, "M5": None})
    with pytest.raises(ValidationError, match="lead reviewer"):
        services.assign_review_team(generic, hod, team["outsider"], sections)
    assert generic.status == S.VALIDATED and not generic.assignments.exists()


@pytest.mark.django_db
def test_module_reviewers_assess_only_their_modules(generic, hod, team):
    services.assign_review_team(generic, hod, team["quality"], _sections(team))

    with pytest.raises(ValidationError):
        services.add_review(generic, team["clinical"], "M3", "ACCEPTABLE", "Not my module")
    services.add_review(generic, team["quality"], "M3", "ACCEPTABLE", "OK")

    # Only the lead sends the recommendation, and only once every module is assessed.
    assert generic.missing_sections() == ["M1", "M2", "M5"]
    with pytest.raises(ValidationError, match="M1, M2, M5"):
        services.complete_review(generic, team["quality"], "APPROVE", "Too early")
    services.add_review(generic, team["regulatory"], "M1", "ACCEPTABLE", "OK")
    services.add_review(generic, team["regulatory"], "M2", "ACCEPTABLE", "OK")
    services.add_review(generic, team["clinical"], "M5", "MINOR", "OK")
    with pytest.raises(PermissionDenied):
        services.complete_review(generic, team["clinical"], "APPROVE", "Not the lead")
    services.complete_review(generic, team["quality"], "APPROVE", "Recommend approval")
    assert generic.status == S.REVIEW_COMPLETE


@pytest.mark.django_db
def test_reassigned_module_needs_a_new_assessment(generic, hod, team):
    services.assign_review_team(generic, hod, team["quality"], _sections(team))
    services.add_review(generic, team["quality"], "M3", "ACCEPTABLE", "OK")
    services.assign_review_team(generic, hod, team["regulatory"], {**_sections(team), "M3": team["outsider"]})
    assert "M3" in generic.missing_sections()
    assert generic.history.last().note.startswith("Lead reviewer")


@pytest.mark.django_db
def test_views_enforce_the_split(client, generic, hod, team):
    services.assign_review_team(generic, hod, team["quality"], _sections(team))
    sequence = generic.sequences.get()
    detail = reverse("applications:detail", args=[generic.pk])

    # A module reviewer sees the whole dossier read-only, but writes only their own modules.
    client.force_login(team["clinical"])
    page = client.get(detail + "?tab=review")
    assert page.status_code == 200
    assert [v for v, _ in page.context["review_form"].fields["section"].choices] == ["M5"]
    assert "complete_form" not in page.context and "info_form" not in page.context
    quality_doc = reverse("applications:sequence_file", args=[generic.pk, sequence.pk, samples.STABILITY_PATH])
    assert client.get(quality_doc).status_code == 200
    review = reverse("applications:add_review", args=[generic.pk])
    assert client.post(review, {"section": "M3", "assessment": "ACCEPTABLE", "comments": "x"}).status_code == 400
    assert client.post(reverse("applications:request_info", args=[generic.pk]), {"questions": "x"}).status_code == 403
    assert client.post(review, {"section": "M5", "assessment": "ACCEPTABLE", "comments": "BE ok"}).status_code == 302

    # A reviewer who is not on the team cannot see the application at all.
    client.force_login(team["outsider"])
    assert client.get(detail).status_code == 404
    assert client.get(quality_doc).status_code == 404

    # The lead gets the questions and recommendation forms.
    client.force_login(team["quality"])
    page = client.get(detail + "?tab=review")
    assert "complete_form" in page.context and page.context["missing_sections"] == ["M1", "M2", "M3"]


@pytest.mark.django_db
def test_hod_team_form(client, generic, hod, team):
    client.force_login(hod)
    page = client.get(reverse("applications:detail", args=[generic.pk]))
    form = page.context["assign_form"]
    # Each module only offers reviewers specialised in it.
    assert list(form.fields["section_M3"].queryset) == [team["outsider"], team["quality"]] or \
        set(form.fields["section_M3"].queryset) == {team["outsider"], team["quality"]}
    assert set(form.fields["section_M5"].queryset) == {team["clinical"]}
    assert not form.fields["section_M4"].required and form.fields["section_M5"].required

    data = {f"section_{s}": r.pk for s, r in _sections(team).items()} | {"lead": team["clinical"].pk}
    response = client.post(reverse("applications:assign", args=[generic.pk]), data)
    assert response.status_code == 302
    generic.refresh_from_db()
    assert generic.status == S.UNDER_REVIEW and generic.assigned_reviewer == team["clinical"]


@pytest.mark.django_db
def test_assistant_knows_the_readers_modules(generic, hod, team):
    services.assign_review_team(generic, hod, team["quality"], _sections(team))
    prompt = system_prompt(team["clinical"], PageContext(application=generic), "en")
    assert "assigned to assess M5" in prompt
    assert "M3 quality" in prompt and "lead reviewer quality" in prompt
