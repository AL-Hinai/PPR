"""Create demo users, companies and applications at every workflow stage.

    python manage.py seed_demo            # password from DEMO_PASSWORD or the default below
    python manage.py seed_demo --reset    # delete existing demo data first
"""
import os

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.demo import DEMO_USERNAMES
from apps.accounts.models import User
from apps.accounts.services import set_default_lead, set_specialties
from apps.applications import services
from apps.applications.models import Application
from apps.companies.models import Company
from apps.validation import samples

DEFAULT_PASSWORD = "Demo@2026"
# One reviewer account per review discipline (CTD module specialties).
REVIEWERS = {
    "rev_regulatory": ("Salim", "Al-Busaidi", ["M1", "M2"]),
    "rev_quality": ("Maryam", "Al-Rawahi", ["M3"]),
    "rev_nonclinical": ("Khalid", "Al-Hinai", ["M4"]),
    "rev_clinical": ("Aisha", "Al-Balushi", ["M5"]),
}


class Command(BaseCommand):
    help = "Seed demo users, companies and applications (local development only)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo records first.")

    def handle(self, *args, reset=False, **options):
        password = os.environ.get("DEMO_PASSWORD", DEFAULT_PASSWORD)
        if reset:
            self._reset()
        with transaction.atomic():
            users = self._users(password)
        self._applications(users)
        self.stdout.write(self.style.SUCCESS("Demo data ready. Users (all share the same password):"))
        for user in users.values():
            self.stdout.write(f"  {user.username:<16} {user.get_role_display():<20} {user.get_specialties_display()}")

    def _reset(self):
        demo_companies = Company.objects.filter(registration_no__startswith="DEMO-")
        for application in Application.objects.filter(company__in=demo_companies):
            for sequence in application.sequences.all():
                sequence.package.delete(save=False)
            application.delete()
        User.objects.filter(username__in=DEMO_USERNAMES).delete()
        demo_companies.delete()

    def _user(self, username, password, role, first, last, company=None, specialties=()):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"role": role, "first_name": first, "last_name": last, "company": company,
                      "email": f"{username}@example.com", "specialties": list(specialties)},
        )
        if created:
            user.set_password(password)
            user.save()
        return user

    def _users(self, password):
        acme, _ = Company.objects.get_or_create(
            registration_no="DEMO-1001",
            defaults={"name_en": "Acme Pharmaceuticals LLC", "name_ar": "أكمي للأدوية ش.م.م",
                      "license_no": "PH-2201", "country": "Oman", "is_verified": True,
                      "contact_email": "regulatory@acme.example.com"},
        )
        gulf, _ = Company.objects.get_or_create(
            registration_no="DEMO-1002",
            defaults={"name_en": "Gulf Generics Co.", "name_ar": "شركة الخليج للأدوية الجنيسة",
                      "license_no": "PH-3307", "country": "United Arab Emirates", "is_verified": True},
        )
        R = User.Role
        users = {
            "hod": self._user("hod", password, R.HOD, "Jokha", "Al-Harthy"),
            **{
                username: self._user(username, password, R.REVIEWER, first, last, specialties=modules)
                for username, (first, last, modules) in REVIEWERS.items()
            },
            "acme": self._user("acme", password, R.COMPANY, "Ahmed", "Al-Kindi", acme),
            "gulfpharma": self._user("gulfpharma", password, R.COMPANY, "Fatma", "Al-Lawati", gulf),
        }
        # Specialties are the HOD's decision; record it as such.
        for username, (_first, _last, modules) in REVIEWERS.items():
            if users[username].specialties_updated_by is None:
                set_specialties(users[username], users["hod"], modules)
        if not User.objects.filter(default_lead=True).exists():
            set_default_lead(users["rev_regulatory"], users["hod"])
        return users

    def _upload(self, application, user, data):
        return services.store_sequence(
            application, user, SimpleUploadedFile("package.zip", data, content_type="application/zip")
        )

    def _team(self, application, hod, users):
        """The review team: assigned automatically on validation, or here when that is switched off."""
        if application.status == Application.Status.VALIDATED:
            reviewers = [users[name] for name in REVIEWERS]
            sections = {
                section: next(r for r in reviewers if section in r.specialties)
                for section in application.required_sections()
            }
            services.assign_review_team(application, hod, users["rev_regulatory"], sections)
        return {a.section: a.reviewer for a in application.assignments.select_related("reviewer")}

    def _assess_all(self, application, sections, comments):
        for section, reviewer in sections.items():
            services.add_review(application, reviewer, section, "ACCEPTABLE", comments.get(section, "Acceptable."))

    def _new(self, user, **fields):
        return Application.objects.create(company=user.company, created_by=user, **fields)

    def _files(self, application, number="0000", **kwargs):
        """Sample sequence whose GCC envelope names this application's product, company and substance."""
        envelope = {"applicant": application.company.name_en, "inn": application.active_ingredients.lower()}
        return samples.build_files(number, application_type=application.application_type,
                                   product_title=application.product_name, envelope=envelope, **kwargs)

    def _package(self, application, number="0000", **kwargs):
        return samples.to_zip(self._files(application, number, **kwargs), number)

    def _applications(self, users):
        if Application.objects.filter(company__registration_no__startswith="DEMO-").exists():
            self.stdout.write("Demo applications already exist (use --reset to recreate).")
            return
        acme, gulf, hod = users["acme"], users["gulfpharma"], users["hod"]
        regulatory, clinical = users["rev_regulatory"], users["rev_clinical"]
        paracetamol = {"active_ingredients": "Paracetamol", "dosage_form": "Film-coated tablet",
                       "strength": "500 mg", "route": "Oral", "atc_code": "N02BE01"}

        # 1. Draft with an uploaded (not yet submitted) package
        app = self._new(acme, application_type="GENERIC", product_name="Acme-Paracetamol 500 mg", **paracetamol)
        self._upload(app, acme, self._package(app))

        # 2. Validation failed (broken package)
        app = self._new(gulf, application_type="GENERIC", product_name="Gulf-Ibuprofen 400 mg",
                        active_ingredients="Ibuprofen", dosage_form="Tablet", strength="400 mg",
                        route="Oral", atc_code="M01AE01")
        broken = self._files(app)
        broken["m2/22-intro/introduction.pdf"] = samples.make_pdf("Edited after checksum")
        broken["m3/32-body-data/Extra File.PDF"] = samples.make_pdf("Unreferenced", version="1.3")
        self._upload(app, gulf, samples.to_zip(broken))
        services.submit(app, gulf)

        # 3. Validated; the review team is assigned automatically from reviewer specialties
        app = self._new(acme, application_type="NEW_DRUG", product_name="Cardiolex 10 mg",
                        active_ingredients="Rosuvastatin calcium", dosage_form="Film-coated tablet",
                        strength="10 mg", route="Oral", atc_code="C10AA07")
        self._upload(app, acme, self._package(app))
        services.submit(app, acme)

        # 4. Under review, with an information request answered by sequence 0001
        app = self._new(acme, application_type="NEW_DRUG", product_name="Acme-Paracetamol IV 10 mg/ml",
                        active_ingredients="Paracetamol", dosage_form="Solution for infusion",
                        strength="10 mg/ml", route="Intravenous", atc_code="N02BE01")
        self._upload(app, acme, self._package(app))
        services.submit(app, acme)
        team = self._team(app, hod, users)
        services.add_review(app, team["M1"], "M1", "ACCEPTABLE", "Labelling and SmPC are consistent with the application form.")
        services.request_information(app, regulatory, "1. Provide 12-month long-term stability data for batch B-003.\n"
                                                  "2. Clarify the specification limit for impurity C.", sections=["M3"])
        response = SimpleUploadedFile("response.zip", self._package(app, "0001", documents=samples.response_documents()))
        services.respond_to_info_request(app, acme, response, "Updated stability summary provided in 3.2.P.8.1.")

        # 5. Review complete, waiting for the HOD decision
        app = self._new(gulf, application_type="GENERIC", product_name="Gulf-Metformin 850 mg",
                        active_ingredients="Metformin hydrochloride", dosage_form="Film-coated tablet",
                        strength="850 mg", route="Oral", atc_code="A10BA02")
        self._upload(app, gulf, self._package(app))
        services.submit(app, gulf)
        team = self._team(app, hod, users)
        self._assess_all(app, {s: r for s, r in team.items() if s != "M5"},
                         {"M3": "Specifications and stability data are adequate."})
        services.add_review(app, clinical, "M5", "MINOR", "Bioequivalence demonstrated; minor reporting gaps noted.")
        services.complete_review(app, regulatory, Application.Recommendation.APPROVE,
                                 "Quality and bioequivalence are acceptable. Recommend approval.")

        # 6. Approved
        app = self._new(acme, application_type="GENERIC", product_name="Acme-Amoxicillin 500 mg",
                        active_ingredients="Amoxicillin trihydrate", dosage_form="Capsule",
                        strength="500 mg", route="Oral", atc_code="J01CA04")
        self._upload(app, acme, self._package(app))
        services.submit(app, acme)
        team = self._team(app, hod, users)
        self._assess_all(app, team, {})
        services.complete_review(app, regulatory, Application.Recommendation.APPROVE, "Recommend approval.")
        services.decide(app, hod, "APPROVED", "Meets quality, safety and efficacy requirements.")
