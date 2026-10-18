"""The assessment stays internal, and answered questions must be re-assessed before the review completes."""
import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from apps.applications import services
from apps.applications.models import Application
from apps.assistant.context import PageContext
from apps.assistant.tools import ToolBox
from apps.notifications.models import Notification
from apps.validation import samples

from .conftest import upload

S = Application.Status


def _reviewer(username, sections, first_name):
    return User.objects.create_user(username=username, password="pw-Secret-123", role=User.Role.REVIEWER,
                                    specialties=sections, first_name=first_name, email=f"{username}@example.com")


@pytest.fixture
def team(db):
    return {
        "regulatory": _reviewer("regulatory", ["M1", "M2"], "Salim"),
        "quality": _reviewer("quality", ["M3"], "Maryam"),
        "clinical": _reviewer("clinical", ["M5"], "Aisha"),
    }


@pytest.fixture
def assessed(make_application, applicant, hod, team, django_capture_on_commit_callbacks):
    """A generic under review, every module assessed, the regulatory reviewer leading."""
    application = make_application("GENERIC")
    upload(application, applicant, samples.build_package("0000", "GENERIC"))
    with django_capture_on_commit_callbacks(execute=True):
        services.submit(application, applicant)
        services.assign_review_team(application, hod, team["regulatory"], {
            "M1": team["regulatory"], "M2": team["regulatory"], "M3": team["quality"], "M5": team["clinical"],
        })
    for section, name in (("M1", "regulatory"), ("M2", "regulatory"), ("M3", "quality"), ("M5", "clinical")):
        services.add_review(application, team[name], section, "MINOR", f"INTERNAL-{section} comment")
    return application


def _answer(application, applicant):
    response = SimpleUploadedFile(
        "response.zip",
        samples.build_package("0001", application.application_type, documents=samples.response_documents()),
    )
    services.respond_to_info_request(application, applicant, response, "Impurity C limit added.")
    application.refresh_from_db()


# --- re-assessment after the applicant answers ---------------------------------------

@pytest.mark.django_db
def test_questioned_module_must_be_reassessed_after_the_answer(assessed, applicant, team):
    lead = team["regulatory"]
    services.request_information(assessed, lead, "Clarify the impurity C limit.", sections=["M3"])
    _answer(assessed, applicant)
    assert assessed.status == S.UNDER_REVIEW

    assert assessed.missing_sections() == ["M3"]
    row = next(r for r in assessed.review_progress() if r["assignment"].section == "M3")
    assert row["reassess"] and row["review"].comments == "INTERNAL-M3 comment"
    with pytest.raises(ValidationError, match="M3"):
        services.complete_review(assessed, lead, Application.Recommendation.APPROVE, "Approve.")

    services.add_review(assessed, team["quality"], "M3", "ACCEPTABLE", "Answer resolves the impurity question.")
    assert assessed.missing_sections() == []
    services.complete_review(assessed, lead, Application.Recommendation.APPROVE, "Approve.")
    assert assessed.status == S.REVIEW_COMPLETE


@pytest.mark.django_db
def test_questions_must_name_assigned_modules(client, assessed, team):
    with pytest.raises(ValidationError, match="module"):
        services.request_information(assessed, team["regulatory"], "Anything?", sections=["M4"])  # not assigned
    client.force_login(team["regulatory"])
    response = client.post(reverse("applications:request_info", args=[assessed.pk]), {"questions": "Anything?"})
    assert response.status_code == 400 and assessed.info_requests.count() == 0


@pytest.mark.django_db
def test_reviewer_dashboard_lists_modules_to_reassess(client, assessed, applicant, team):
    services.request_information(assessed, team["regulatory"], "Clarify the impurity C limit.", sections=["M3"])
    _answer(assessed, applicant)
    client.force_login(team["quality"])
    assert assessed.reference_no in client.get(reverse("core:dashboard")).content.decode()
    client.force_login(team["clinical"])  # M5 was not questioned: nothing to do
    assert assessed.reference_no not in client.get(reverse("core:dashboard")).content.decode().split("My review queue")[0]


# --- what the applicant sees ------------------------------------------------------------

@pytest.mark.django_db
def test_applicant_sees_questions_and_decision_not_the_assessment(client, assessed, applicant, hod, team):
    lead = team["regulatory"]
    services.request_information(assessed, lead, "PUBLIC question about impurity C.", sections=["M3"])
    _answer(assessed, applicant)
    services.add_review(assessed, team["quality"], "M3", "ACCEPTABLE", "INTERNAL-M3 second look")
    services.complete_review(assessed, lead, Application.Recommendation.APPROVE, "INTERNAL lead summary")
    services.return_to_reviewer(assessed, hod, "INTERNAL hod return note")
    services.complete_review(assessed, lead, Application.Recommendation.APPROVE, "INTERNAL lead summary")
    services.decide(assessed, hod, "APPROVED", "PUBLIC decision justification")

    client.force_login(applicant)
    pages = "".join(
        client.get(reverse("applications:detail", args=[assessed.pk]), {"tab": tab}).content.decode()
        for tab in ("overview", "review", "history")
    )
    assert "PUBLIC question about impurity C." in pages
    assert "PUBLIC decision justification" in pages
    for secret in ("INTERNAL", "Salim", "Maryam", "Aisha", "Lead reviewer", "Acceptable", "Minor issues"):
        assert secret not in pages, secret

    client.force_login(hod)
    staff = client.get(reverse("applications:detail", args=[assessed.pk]), {"tab": "review"}).content.decode()
    assert "INTERNAL-M3 comment" in staff and "INTERNAL lead summary" in staff


@pytest.mark.django_db
def test_applicant_notifications_and_assistant_carry_no_internal_notes(assessed, applicant, hod, team,
                                                                       django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        services.assign_review_team(assessed, hod, team["quality"], {  # a team change, new lead
            "M1": team["regulatory"], "M2": team["regulatory"], "M3": team["quality"], "M5": team["clinical"],
        })
        services.request_information(assessed, team["quality"], "PUBLIC question.", sections=["M3"])
    notes = list(Notification.objects.filter(user=applicant).values_list("status", "note"))
    assert (S.INFO_REQUESTED, "PUBLIC question.") in notes
    assert all("Maryam" not in note and "Salim" not in note for _, note in notes)
    assert Notification.objects.filter(user=team["regulatory"], note__contains="Lead reviewer").exists()

    overview = ToolBox(applicant, PageContext(application=assessed)).invoke("get_application_overview", {}).payload
    assert "reviews" not in overview and "assigned_reviewer" not in overview
    assert overview["information_requests"][0]["questions"] == "PUBLIC question."
    staff = ToolBox(hod, PageContext(application=assessed)).invoke("get_application_overview", {}).payload
    assert staff["reviews"] and staff["assigned_reviewer"]
