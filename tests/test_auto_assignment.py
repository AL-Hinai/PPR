"""Review teams assembled automatically from reviewer specialties when validation passes."""
import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.services import set_default_lead
from apps.applications import services
from apps.applications.models import Application
from apps.notifications.models import Notification
from apps.validation import samples

from .conftest import upload

S = Application.Status


@pytest.fixture(autouse=True)
def auto_assign(settings):
    settings.AUTO_ASSIGN_REVIEW_TEAMS = True


def _reviewer(username, sections, first_name=""):
    return User.objects.create_user(username=username, password="pw-Secret-123", role=User.Role.REVIEWER,
                                    specialties=sections, first_name=first_name, email=f"{username}@example.com")


@pytest.fixture
def team(db):
    return {
        "regulatory": _reviewer("regulatory", ["M1", "M2"]),
        "quality": _reviewer("quality", ["M3"]),
        "nonclinical": _reviewer("nonclinical", ["M4"]),
        "clinical": _reviewer("clinical", ["M5"]),
    }


def _submit(make_application, applicant, application_type="GENERIC"):
    application = make_application(application_type)
    upload(application, applicant, samples.build_package("0000", application_type))
    services.submit(application, applicant)
    return application


def _team(application):
    return dict(application.assignments.values_list("section", "reviewer__username"))


@pytest.mark.django_db
def test_validated_application_goes_straight_to_its_specialists(
    make_application, applicant, hod, team, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        application = _submit(make_application, applicant)
    assert application.status == S.UNDER_REVIEW
    assert _team(application) == {"M1": "regulatory", "M2": "regulatory", "M3": "quality", "M5": "clinical"}
    # No default lead: the reviewer covering the most modules leads.
    assert application.assigned_reviewer == team["regulatory"]
    assert all(a.assigned_by is None for a in application.assignments.all())

    entry = application.history.get(to_status=S.UNDER_REVIEW)
    assert entry.actor is None and "automatically" in entry.note
    for name in ("regulatory", "quality", "clinical"):
        assert Notification.objects.filter(user=team[name], status=S.UNDER_REVIEW).exists()
    assert not Notification.objects.filter(user=team["nonclinical"]).exists()  # M4 is not required for a generic


@pytest.mark.django_db
def test_default_lead_leads_the_team(make_application, applicant, hod, team):
    set_default_lead(team["clinical"], hod)
    application = _submit(make_application, applicant, "NEW_DRUG")
    assert _team(application) == {
        "M1": "regulatory", "M2": "regulatory", "M3": "quality", "M4": "nonclinical", "M5": "clinical",
    }
    assert application.assigned_reviewer == team["clinical"]


@pytest.mark.django_db
def test_the_least_busy_specialist_gets_the_module(make_application, applicant, team):
    _reviewer("quality2", ["M3"])
    first = _submit(make_application, applicant)
    second = _submit(make_application, applicant)
    assert _team(first)["M3"] == "quality"
    assert _team(second)["M3"] == "quality2"


@pytest.mark.django_db
def test_generalists_share_a_dossier_instead_of_one_taking_it_all(make_application, applicant):
    # As after migrating from generalist reviewers: everyone is qualified for every module.
    generalists = [_reviewer(f"gen{i}", ["M1", "M2", "M3", "M4", "M5"]) for i in range(3)]
    application = _submit(make_application, applicant, "NEW_DRUG")
    holders = list(_team(application).values())
    assert sorted(holders) == ["gen0", "gen0", "gen1", "gen1", "gen2"]
    assert application.assigned_reviewer in generalists


@pytest.mark.django_db
def test_waits_for_the_hod_when_a_module_has_no_specialist(make_application, applicant, hod, team):
    team["quality"].specialties = []
    team["quality"].save()
    application = _submit(make_application, applicant)
    assert application.status == S.VALIDATED and not application.assignments.exists()

    team["quality"].specialties = ["M3"]
    team["quality"].save()
    services.assign_review_team(application, hod, team["regulatory"], {
        "M1": team["regulatory"], "M2": team["regulatory"], "M3": team["quality"], "M5": team["clinical"],
    })
    assert application.status == S.UNDER_REVIEW


@pytest.mark.django_db
def test_switched_off_leaves_assignment_to_the_hod(settings, make_application, applicant, team):
    settings.AUTO_ASSIGN_REVIEW_TEAMS = False
    application = _submit(make_application, applicant)
    assert application.status == S.VALIDATED and not application.assignments.exists()


@pytest.mark.django_db
def test_hod_sets_one_default_lead_on_the_reviewers_page(client, hod, team):
    client.force_login(hod)
    url = reverse("accounts:reviewers")
    client.post(url, {"default_lead": team["quality"].pk})
    client.post(url, {"default_lead": team["clinical"].pk})
    assert list(User.objects.filter(default_lead=True)) == [team["clinical"]]

    assert client.post(url, {"default_lead": "abc"}).status_code == 404
    assert client.post(url, {"reviewer": "abc", "specialties": ["M1"]}).status_code == 404

    client.post(url, {"default_lead": ""})
    assert not User.objects.filter(default_lead=True).exists()

    client.force_login(team["quality"])
    assert client.post(url, {"default_lead": team["quality"].pk}).status_code in (302, 403)
    assert not User.objects.filter(default_lead=True).exists()
