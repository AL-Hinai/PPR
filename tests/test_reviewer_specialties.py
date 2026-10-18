"""Reviewer specialties are set by the Head of Department only."""
import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from apps.accounts import services
from apps.accounts.models import User
from apps.applications import services as app_services
from apps.applications.models import Application
from apps.validation import samples

from .conftest import upload

URL = reverse("accounts:reviewers")


@pytest.mark.django_db
def test_only_the_hod_opens_the_reviewers_page(client, hod, reviewer, applicant):
    for user in (reviewer, applicant):
        client.force_login(user)
        assert client.get(URL).status_code == 403
        assert client.post(URL, {"reviewer": reviewer.pk, "specialties": ["M1"]}).status_code == 403
    reviewer.refresh_from_db()
    assert reviewer.specialties == ["M1", "M2", "M3", "M4", "M5"]

    client.force_login(hod)
    page = client.get(URL)
    assert page.status_code == 200 and reviewer.username.encode() in page.content


@pytest.mark.django_db
def test_hod_sets_specialties_and_it_is_recorded(client, hod, reviewer):
    client.force_login(hod)
    response = client.post(URL, {"reviewer": reviewer.pk, "specialties": ["M5", "M3", "XX"]})
    assert response.status_code == 302
    reviewer.refresh_from_db()
    assert reviewer.specialties == ["M3", "M5"]
    assert reviewer.specialties_updated_by == hod and reviewer.specialties_updated_at


@pytest.mark.django_db
def test_rules(hod, reviewer, applicant):
    with pytest.raises(PermissionDenied):
        services.set_specialties(reviewer, reviewer, ["M1"])
    with pytest.raises(ValidationError):
        services.set_specialties(applicant, hod, ["M1"])


@pytest.mark.django_db
def test_cannot_remove_a_module_held_on_an_active_review(make_application, applicant, hod, reviewer):
    application = make_application("GENERIC")
    upload(application, applicant, samples.build_package("0000", "GENERIC"))
    app_services.submit(application, applicant)
    app_services.assign_reviewer(application, hod, reviewer)  # holds M1, M2, M3, M5

    with pytest.raises(ValidationError, match=f"{application.reference_no} M3"):
        services.set_specialties(reviewer, hod, ["M1", "M2", "M5"])
    services.set_specialties(reviewer, hod, ["M1", "M2", "M3", "M5"])  # M4 is not held: fine
    assert User.objects.get(pk=reviewer.pk).specialties == ["M1", "M2", "M3", "M5"]

    # Still held once the review is with the HOD, who may send it back.
    application.status = Application.Status.REVIEW_COMPLETE
    application.save(update_fields=["status"])
    with pytest.raises(ValidationError, match=f"{application.reference_no} M3"):
        services.set_specialties(reviewer, hod, ["M1", "M2", "M5"])


@pytest.mark.django_db
def test_admin_cannot_edit_specialties(admin_client, reviewer):
    page = admin_client.get(reverse("admin:accounts_user_change", args=[reviewer.pk]))
    assert page.status_code == 200
    assert b'name="specialties"' not in page.content
