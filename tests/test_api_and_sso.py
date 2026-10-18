"""Read-only API for other systems, and optional single sign-on for staff."""
import pytest
from django.core.management import call_command
from django.template.loader import render_to_string
from django.test import override_settings
from django.urls import reverse

from apps.accounts.sso import StaffOIDCBackend
from apps.api.models import ApiToken
from apps.applications import services
from apps.validation import samples

from .conftest import upload

pytestmark = [pytest.mark.req("URS-21"), pytest.mark.req("URS-22")]


@pytest.fixture
def approved(make_application, applicant, reviewer, hod):
    application = make_application("GENERIC")
    upload(application, applicant, samples.build_package("0000", "GENERIC"))
    services.submit(application, applicant)
    services.assign_reviewer(application, hod, reviewer)
    for section in application.required_sections():
        services.add_review(application, reviewer, section, "ACCEPTABLE", "ok")
    services.complete_review(application, reviewer, "APPROVE", "ok")
    services.decide(application, hod, "APPROVED", "ok")
    return application


@pytest.mark.django_db
def test_api_requires_a_valid_key(client):
    url = reverse("api:applications")
    assert client.get(url).status_code == 401
    assert client.get(url, HTTP_AUTHORIZATION="Bearer nope").status_code == 401
    token, key = ApiToken.issue("Register")
    token.is_active = False
    token.save()
    assert client.get(url, HTTP_AUTHORIZATION=f"Bearer {key}").status_code == 401


@pytest.mark.django_db
def test_api_lists_and_details_applications_without_drafts(client, approved, make_application):
    make_application()  # a draft: never exposed
    token, key = ApiToken.issue("Register")
    auth = {"HTTP_AUTHORIZATION": f"Bearer {key}"}
    data = client.get(reverse("api:applications"), {"status": "APPROVED"}, **auth).json()
    assert data["count"] == 1
    item = data["results"][0]
    assert item["reference_no"] == approved.reference_no and item["decision"]["approval_no"].startswith("PPR-")
    assert client.get(reverse("api:applications"), **auth).json()["count"] == 1  # the draft is not listed
    detail = client.get(reverse("api:application", args=[approved.reference_no]), **auth).json()
    assert detail["sequences"][0] == {**detail["sequences"][0], "number": "0000", "validation_status": "PASSED",
                                      "submission_type": "new-gen"}
    token.refresh_from_db()
    assert token.last_used_at is not None
    assert client.get(reverse("api:applications"), {"updated_since": "yesterday"}, **auth).status_code == 400


@pytest.mark.django_db
def test_create_api_key_stores_only_a_hash(capsys):
    call_command("create_api_key", "Drug register")
    key = capsys.readouterr().out.strip().splitlines()[-1]
    token = ApiToken.objects.get()
    assert key.startswith("ppr_") and key not in (token.digest, token.prefix)
    assert ApiToken.authenticate(key) == token


@pytest.mark.django_db
def test_sso_signs_in_existing_staff_only(hod, reviewer, applicant):
    backend = StaffOIDCBackend.__new__(StaffOIDCBackend)  # no provider settings needed for the lookup
    backend.UserModel = type(hod)
    assert list(backend.filter_users_by_claims({"email": hod.email.upper()})) == [hod]
    assert list(backend.filter_users_by_claims({"upn": reviewer.email})) == [reviewer]
    assert not backend.filter_users_by_claims({"email": applicant.email}).exists()  # companies keep passwords
    assert not backend.filter_users_by_claims({"email": "stranger@moh.gov.om"}).exists()
    assert backend.create_user({"email": "new@moh.gov.om"}) is None


@override_settings(ROOT_URLCONF="tests.sso_urls")
def test_login_page_offers_sso_when_enabled(rf):
    html = render_to_string("accounts/login.html", {"sso_enabled": True, "form": None}, request=rf.get("/"))
    assert "Sign in with your Ministry account" in html and "/oidc/authenticate/" in html


@pytest.mark.django_db
def test_login_page_without_sso(client):
    assert b"/oidc/" not in client.get(reverse("accounts:login")).content
