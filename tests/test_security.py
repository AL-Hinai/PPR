"""Login lockout, password management, Content-Security-Policy and production security settings."""
import re

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse

from apps.validation import samples

from .conftest import upload

pytestmark = [pytest.mark.req("URS-19")]

PASSWORD = "pw-Secret-123"


@pytest.mark.django_db
def test_login_locks_after_five_failures(client, applicant):
    url = reverse("accounts:login")
    for _ in range(5):
        client.post(url, {"username": "applicant", "password": "wrong"})
    response = client.post(url, {"username": "applicant", "password": PASSWORD})
    assert response.status_code == 429
    assert b"Too many failed sign-in attempts" in response.content
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_successful_login_still_works(client, applicant):
    response = client.post(reverse("accounts:login"), {"username": "applicant", "password": PASSWORD})
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(applicant.pk)


@pytest.mark.django_db
def test_password_change(client, applicant):
    client.force_login(applicant)
    new = "a-much-Longer-pass-2026"
    response = client.post(reverse("accounts:password_change"),
                           {"old_password": PASSWORD, "new_password1": new, "new_password2": new})
    assert response.status_code == 302
    applicant.refresh_from_db()
    assert applicant.check_password(new)


@pytest.mark.django_db
def test_password_reset_sends_a_working_link(client, applicant):
    client.post(reverse("accounts:password_reset"), {"email": applicant.email})
    assert len(mail.outbox) == 1
    link = re.search(r"https?://[^/]+(/\S+)", mail.outbox[0].body).group(1)
    form_url = client.get(link).url  # Django swaps the token for a session marker
    new = "another-Long-pass-2026"
    response = client.post(form_url, {"new_password1": new, "new_password2": new})
    assert response.status_code == 302
    applicant.refresh_from_db()
    assert applicant.check_password(new)


def test_passwords_need_twelve_characters():
    with pytest.raises(ValidationError):
        validate_password("Short-pw-1")
    validate_password("long-enough-Passphrase")


@pytest.mark.django_db
def test_pages_carry_a_nonce_csp(client, applicant, make_application):
    application = make_application()
    sequence = upload(application, applicant, samples.build_package("0000"))
    from apps.applications import services

    services.submit(application, applicant)
    client.force_login(applicant)
    path = "m2/22-intro/introduction.pdf"
    response = client.get(reverse("applications:sequence_document", args=[application.pk, sequence.pk, path]))
    policy = response["Content-Security-Policy"]
    assert "script-src 'self' 'nonce-" in policy and "frame-ancestors 'none'" in policy
    nonce = re.search(r"'nonce-([^']+)'", policy).group(1)
    assert f'nonce="{nonce}"'.encode() in response.content  # the viewer's inline module script
    assert b"cdn.jsdelivr.net" not in response.content  # libraries are served from this site
    assert b"onclick=" not in client.get(reverse("applications:sequence", args=[application.pk, sequence.pk])).content


def test_production_settings_pass_the_deploy_checks():
    """`manage.py check --deploy` is clean with the production settings (run apart: they need their own env)."""
    import os
    import secrets
    import subprocess
    import sys

    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings.production", "SECRET_KEY": secrets.token_urlsafe(50),
           "ALLOWED_HOSTS": "ppr.example.org", "DB_NAME": "x", "DB_USER": "x", "DB_PASSWORD": "x", "DB_HOST": "localhost"}
    script = (
        "import django, json; django.setup(); from django.conf import settings as s; "
        "from django.core.management import call_command; call_command('check', deploy=True, fail_level='WARNING'); "
        "print(json.dumps([s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_INCLUDE_SUBDOMAINS, s.SESSION_EXPIRE_AT_BROWSER_CLOSE, "
        "s.SESSION_COOKIE_AGE, s.VALIDATION_MODE]))"
    )
    result = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "[31536000, true, true, 28800, \"queue\"]"


@pytest.mark.django_db
def test_demo_login_buttons_are_absent_unless_switched_on(client, applicant):
    """DEMO_LOGIN is off outside local development, so the login page offers no demo accounts."""
    response = client.get(reverse("accounts:login"))
    assert b"Demonstration accounts" not in response.content
    assert applicant.username.encode() not in response.content


@pytest.mark.django_db
@override_settings(DEMO_LOGIN=True, DEMO_LOGIN_PASSWORD=PASSWORD)
def test_demo_login_button_signs_in_through_the_ordinary_form(client, applicant):
    """The button posts the login form, so authentication runs exactly as it does for a typed password."""
    applicant.username = "hod"  # a username seed_demo creates; only those are offered
    applicant.save()
    page = client.get(reverse("accounts:login"))
    assert b"Demonstration accounts" in page.content
    assert b'value="hod"' in page.content

    response = client.post(reverse("accounts:login"), {"username": "hod", "password": PASSWORD})
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(applicant.pk)


@pytest.mark.django_db
@override_settings(DEMO_LOGIN=True, DEMO_LOGIN_PASSWORD=PASSWORD)
def test_demo_login_offers_only_the_seeded_accounts(client, applicant):
    """An ordinary account is never listed, however the setting is configured."""
    response = client.get(reverse("accounts:login"))
    assert b"Demonstration accounts" not in response.content
    assert applicant.username.encode() not in response.content
