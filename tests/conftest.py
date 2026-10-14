import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.applications import services
from apps.applications.models import Application
from apps.companies.models import Company
from apps.validation.engine import validate_sequence


@pytest.fixture
def company(db):
    return Company.objects.create(name_en="Acme Pharma", registration_no="CR-1")


@pytest.fixture
def other_company(db):
    return Company.objects.create(name_en="Other Pharma", registration_no="CR-2")


def _user(username, role, company=None):
    return User.objects.create_user(username=username, password="pw-Secret-123", role=role, company=company,
                                    email=f"{username}@example.com")


@pytest.fixture
def applicant(company):
    return _user("applicant", User.Role.COMPANY, company)


@pytest.fixture
def other_applicant(other_company):
    return _user("other", User.Role.COMPANY, other_company)


@pytest.fixture
def reviewer(db):
    return _user("reviewer", User.Role.REVIEWER)


@pytest.fixture
def reviewer2(db):
    return _user("reviewer2", User.Role.REVIEWER)


@pytest.fixture
def hod(db):
    return _user("hod", User.Role.HOD)


@pytest.fixture
def make_application(applicant):
    def make(application_type="NEW_DRUG", user=None):
        user = user or applicant
        return Application.objects.create(
            company=user.company,
            created_by=user,
            application_type=application_type,
            product_name="Testamol 500 mg",
            active_ingredients="Paracetamol",
            dosage_form="Tablet",
            strength="500 mg",
            route="Oral",
        )

    return make


def upload(application, user, data: bytes, name="package.zip"):
    return services.store_sequence(application, user, SimpleUploadedFile(name, data, content_type="application/zip"))


@pytest.fixture
def validate(make_application, applicant):
    """Upload bytes as the next sequence of a fresh application and validate it."""

    def run(data: bytes, application_type="NEW_DRUG", application=None):
        application = application or make_application(application_type)
        sequence = upload(application, applicant, data)
        run_ = validate_sequence(sequence)
        sequence.refresh_from_db()
        codes = {f.rule_code for f in run_.findings.all()}
        return sequence, run_, codes

    return run
