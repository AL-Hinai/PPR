"""Bulk test data on top of seed_demo: more companies, reviewers and applications in every state.

    python manage.py seed_bulk                 # 150 applications (runs seed_demo first if needed)
    python manage.py seed_bulk --count 300     # more
    python manage.py seed_bulk --reset         # delete earlier bulk data first
    python manage.py seed_bulk --seed 7        # another reproducible mix

Every broken package from the validation benchmark is submitted once, so each error rule has a
failed application to look at; warning packages pass to review. The rest of the applications are
spread over the workflow (drafts, failed then fixed, review in progress, questions open, overdue
or answered, recommendations, approvals and rejections), and their history is spread over the
last year so dashboards, KPIs and lists look like a system in use. Bulk accounts share the demo
password; their usernames start with ``bulk_`` and their companies' registration numbers with ``BULK-``.
"""
import datetime
import os
import random

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import transaction
from django.db.models import Q
from django.test.utils import override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.services import set_specialties
from apps.applications import services
from apps.applications.models import (
    Application, Decision, DocumentNote, InfoRequest, Review, ReviewAssignment, Sequence, StatusHistory,
)
from apps.companies.models import Company
from apps.notifications.models import Notification
from apps.validation import samples
from apps.validation.benchmark import REGIONAL, Case, benchmark_cases, broken_cases, with_doc
from apps.validation.models import ValidationRun

from .seed_demo import DEFAULT_PASSWORD
from .seed_demo import Command as DemoCommand

S = Application.Status
USER_PREFIX = "bulk_"
COMPANY_PREFIX = "BULK-"

COMPANIES = [
    # registration suffix, English name, Arabic name, country, contact first/last name
    ("2001", "Muscat Pharma SAOG", "مسقط فارما ش.م.ع.ع", "Oman", "Hilal", "Al-Saadi"),
    ("2002", "Dhofar Life Sciences LLC", "ظفار لعلوم الحياة ش.م.م", "Oman", "Noor", "Al-Mahri"),
    ("2003", "Riyadh BioMed Co.", "شركة الرياض بايوميد", "Saudi Arabia", "Faisal", "Al-Qahtani"),
    ("2004", "Emirates Generics FZ-LLC", "الإمارات للأدوية الجنيسة", "United Arab Emirates", "Mariam", "Al-Mansoori"),
    ("2005", "Kuwait Medica K.S.C.", "الكويت ميديكا ش.م.ك", "Kuwait", "Yousef", "Al-Sabah"),
    ("2006", "Bahrain Pharmaceutical Industries", "البحرين للصناعات الدوائية", "Bahrain", "Layla", "Al-Khalifa"),
    ("2007", "Qatar Health Products", "قطر للمنتجات الصحية", "Qatar", "Hamad", "Al-Thani"),
    ("2008", "Sohar Generics LLC", "صحار للأدوية الجنيسة ش.م.م", "Oman", "Salma", "Al-Farsi"),
    ("2009", "Nizwa Biologics SAOC", "نزوى للمستحضرات الحيوية", "Oman", "Said", "Al-Abri"),
    ("2010", "EuroMed Laboratories GmbH", "يورو ميد للمختبرات", "Germany", "Anna", "Becker"),
]

# Extra reviewers so automatic assignment spreads the load (username, first, last, modules).
REVIEWERS = [
    ("bulk_rev_m1a", "Huda", "Al-Riyami", ["M1", "M2"]),
    ("bulk_rev_m1b", "Ali", "Al-Shukaili", ["M1"]),
    ("bulk_rev_m3a", "Zainab", "Al-Lamki", ["M3"]),
    ("bulk_rev_m3b", "Tariq", "Al-Habsi", ["M2", "M3"]),
    ("bulk_rev_m4", "Rashid", "Al-Wahaibi", ["M4"]),
    ("bulk_rev_m45", "Amal", "Al-Jabri", ["M4", "M5"]),
    ("bulk_rev_m5", "Nasser", "Al-Siyabi", ["M5"]),
]

# product, active ingredient(s), dosage form, strength, route, ATC
PRODUCTS = [
    ("Amlodipine", "Amlodipine besilate", "Tablet", "5 mg", "Oral", "C08CA01"),
    ("Atorvastatin", "Atorvastatin calcium", "Film-coated tablet", "20 mg", "Oral", "C10AA05"),
    ("Omeprazole", "Omeprazole", "Gastro-resistant capsule", "20 mg", "Oral", "A02BC01"),
    ("Pantoprazole", "Pantoprazole sodium sesquihydrate", "Gastro-resistant tablet", "40 mg", "Oral", "A02BC02"),
    ("Losartan", "Losartan potassium", "Film-coated tablet", "50 mg", "Oral", "C09CA01"),
    ("Valsartan", "Valsartan", "Film-coated tablet", "80 mg", "Oral", "C09CA03"),
    ("Bisoprolol", "Bisoprolol fumarate", "Film-coated tablet", "5 mg", "Oral", "C07AB07"),
    ("Clopidogrel", "Clopidogrel hydrogen sulfate", "Film-coated tablet", "75 mg", "Oral", "B01AC04"),
    ("Sitagliptin", "Sitagliptin phosphate monohydrate", "Film-coated tablet", "100 mg", "Oral", "A10BH01"),
    ("Gliclazide", "Gliclazide", "Modified-release tablet", "60 mg", "Oral", "A10BB09"),
    ("Empagliflozin", "Empagliflozin", "Film-coated tablet", "10 mg", "Oral", "A10BK03"),
    ("Insulin Glargine", "Insulin glargine", "Solution for injection", "100 U/ml", "Subcutaneous", "A10AE04"),
    ("Azithromycin", "Azithromycin dihydrate", "Film-coated tablet", "500 mg", "Oral", "J01FA10"),
    ("Ciprofloxacin", "Ciprofloxacin hydrochloride", "Film-coated tablet", "500 mg", "Oral", "J01MA02"),
    ("Ceftriaxone", "Ceftriaxone sodium", "Powder for solution for injection", "1 g", "Intravenous", "J01DD04"),
    ("Cefuroxime", "Cefuroxime axetil", "Film-coated tablet", "250 mg", "Oral", "J01DC02"),
    ("Levofloxacin", "Levofloxacin hemihydrate", "Solution for infusion", "5 mg/ml", "Intravenous", "J01MA12"),
    ("Fluconazole", "Fluconazole", "Capsule", "150 mg", "Oral", "J02AC01"),
    ("Montelukast", "Montelukast sodium", "Chewable tablet", "5 mg", "Oral", "R03DC03"),
    ("Salbutamol", "Salbutamol sulfate", "Pressurised inhalation, suspension", "100 mcg/dose", "Inhalation", "R03AC02"),
    ("Cetirizine", "Cetirizine dihydrochloride", "Film-coated tablet", "10 mg", "Oral", "R06AE07"),
    ("Desloratadine", "Desloratadine", "Oral solution", "0.5 mg/ml", "Oral", "R06AX27"),
    ("Sertraline", "Sertraline hydrochloride", "Film-coated tablet", "50 mg", "Oral", "N06AB06"),
    ("Escitalopram", "Escitalopram oxalate", "Film-coated tablet", "10 mg", "Oral", "N06AB10"),
    ("Levetiracetam", "Levetiracetam", "Film-coated tablet", "500 mg", "Oral", "N03AX14"),
    ("Pregabalin", "Pregabalin", "Hard capsule", "75 mg", "Oral", "N03AX16"),
    ("Tramadol", "Tramadol hydrochloride", "Prolonged-release tablet", "100 mg", "Oral", "N02AX02"),
    ("Diclofenac", "Diclofenac sodium", "Gastro-resistant tablet", "50 mg", "Oral", "M01AB05"),
    ("Celecoxib", "Celecoxib", "Hard capsule", "200 mg", "Oral", "M01AH01"),
    ("Allopurinol", "Allopurinol", "Tablet", "300 mg", "Oral", "M04AA01"),
    ("Levothyroxine", "Levothyroxine sodium", "Tablet", "100 mcg", "Oral", "H03AA01"),
    ("Prednisolone", "Prednisolone", "Tablet", "5 mg", "Oral", "H02AB06"),
    ("Enoxaparin", "Enoxaparin sodium", "Solution for injection in pre-filled syringe", "40 mg/0.4 ml",
     "Subcutaneous", "B01AB05"),
    ("Rivaroxaban", "Rivaroxaban", "Film-coated tablet", "20 mg", "Oral", "B01AF01"),
    ("Ondansetron", "Ondansetron hydrochloride dihydrate", "Orodispersible tablet", "8 mg", "Oral", "A04AA01"),
    ("Tamsulosin", "Tamsulosin hydrochloride", "Prolonged-release capsule", "0.4 mg", "Oral", "G04CA02"),
    ("Finasteride", "Finasteride", "Film-coated tablet", "5 mg", "Oral", "G04CB01"),
    ("Imatinib", "Imatinib mesilate", "Film-coated tablet", "400 mg", "Oral", "L01EA01"),
    ("Capecitabine", "Capecitabine", "Film-coated tablet", "500 mg", "Oral", "L01BC06"),
    ("Methotrexate", "Methotrexate sodium", "Solution for injection", "25 mg/ml", "Intramuscular", "L04AX03"),
]
BRANDS = ["Muscovir", "Dhofarin", "Riyamed", "Emiral", "Kuwamed", "Bahrapharm", "Qatarix", "Soharex", "Nizwal",
          "Euromed", "Oryx", "Falcona", "Lubanix", "Frankin", "Corniche", "Wadimed"]

QUESTIONS = [
    "Provide 12-month long-term stability data for the three primary batches.",
    "Clarify the specification limit for the unspecified impurities.",
    "Submit the dissolution profile comparison (f2) against the reference product.",
    "Provide the GMP certificate of the finished product manufacturer, valid at the time of submission.",
    "Justify the proposed shelf life given the accelerated stability results.",
    "Provide the validation report for the related-substances HPLC method.",
    "Submit the Arabic patient information leaflet in line with the approved English text.",
    "Provide the bioequivalence study's statistical analysis plan and raw PK data.",
    "Clarify the source and TSE/BSE status of excipients of animal origin.",
    "Provide the nitrosamine risk assessment for the active substance and finished product.",
]
FINDINGS = {
    "ACCEPTABLE": ["Acceptable.", "Documentation is complete and consistent.", "No objections.",
                   "Data support the proposed claims."],
    "MINOR": ["Minor editorial inconsistencies between the SmPC and the leaflet.",
              "Minor gaps in the batch analysis tables; can be resolved post-approval.",
              "Stability commitment acceptable; ongoing study to be reported."],
    "MAJOR": ["Major objection: impurity limits are not justified.",
              "Major objection: bioequivalence not demonstrated for Cmax.",
              "Major objection: the manufacturing process validation is incomplete."],
}
NOTES = [
    "Check this value against the batch analysis in 3.2.P.5.4.",
    "Inconsistent with the SmPC section 6.3.",
    "Reference product batch number missing here.",
    "Confirm the storage condition wording.",
    "Good summary; no further questions on this page.",
]


def extra_broken_cases():
    """The error rules the benchmark set has no package for."""
    def without_regional():
        files = samples.build_files("0000")
        del files[REGIONAL]
        return samples.to_zip(files)

    def without_module_4():
        docs = [d for d in samples.initial_documents("NEW_DRUG") if not d.path.startswith("m4/")]
        return samples.build_package("0000", "NEW_DRUG", documents=docs)

    def large_file():  # over the 1 MB limit the scenario sets
        text = "\n".join(["Large appendix"] + [f"Batch record line {n}" for n in range(60000)])
        return samples.to_zip(with_doc(path="m2/27-clin-sum/large.pdf", content=samples.make_pdf(text)))

    return [
        Case("SCH-04", "", without_regional, {"SCH-04", "BR-03"}, "gc-regional.xml is missing"),
        Case("BR-06", "", without_module_4, {"BR-06"}, "New drug without Module 4 documents"),
        Case("FC-06", "", large_file, {"FC-06"}, "A document over the file size limit"),
    ]


@transaction.atomic
def delete_bulk_data():
    """Remove everything seed_bulk created (seed_demo --reset calls this first)."""
    companies = Company.objects.filter(registration_no__startswith=COMPANY_PREFIX)
    bulk_users = User.objects.filter(username__startswith=USER_PREFIX)
    # Bulk applications of the demo companies carry one of the bulk brand names.
    bulk_brands = Q()
    for brand in BRANDS:
        bulk_brands |= Q(product_name__startswith=f"{brand} ")
    applications = Application.objects.filter(Q(company__in=companies) | bulk_brands)
    for application in applications:
        for sequence in application.sequences.all():
            sequence.package.delete(save=False)
        application.delete()
    # Reviews and assignments of bulk reviewers on demo applications.
    ReviewAssignment.objects.filter(reviewer__in=bulk_users).delete()
    Review.objects.filter(reviewer__in=bulk_users).delete()
    DocumentNote.objects.filter(author__in=bulk_users).delete()
    Application.objects.filter(assigned_reviewer__in=bulk_users).update(assigned_reviewer=None)
    bulk_users.delete()
    companies.delete()


class Command(DemoCommand):
    help = "Seed many applications in every workflow state for testing (local development only)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=150, help="Applications to create (default 150).")
        parser.add_argument("--reset", action="store_true", help="Delete earlier bulk data first.")
        parser.add_argument("--seed", type=int, default=2026, help="Random seed (same seed, same mix).")

    def handle(self, *args, count=150, reset=False, seed=2026, **options):
        self.rng = random.Random(seed)
        password = os.environ.get("DEMO_PASSWORD", DEFAULT_PASSWORD)
        if reset:
            delete_bulk_data()
        if not User.objects.filter(username="hod").exists():
            call_command("seed_demo", stdout=self.stdout)
        if Company.objects.filter(registration_no__startswith=COMPANY_PREFIX).exists():
            self.stdout.write("Bulk data already exists (use --reset to recreate).")
            return
        with transaction.atomic():
            self.users = self._users(password)  # the seed_demo accounts (get_or_create)
            self.hod = self.users["hod"]
            self.applicants = [self.users["acme"], self.users["gulfpharma"], *self._bulk_users(password)]
        self.products = self._product_names()

        plan = [(name, None) for name in self.SCENARIOS] + [("failed", case) for case in broken_cases() + extra_broken_cases()]
        plan += [("warning", case) for case in benchmark_cases() if case.expected and case.label in self.WARNINGS]
        weighted = [name for name, weight in self.SCENARIOS.items() for _ in range(weight)]
        while len(plan) < count:
            plan.append((self.rng.choice(weighted), None))
        self.rng.shuffle(plan)

        # In-app notifications are kept; emails would only flood the console.
        with override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"):
            for index, (scenario, case) in enumerate(plan, 1):
                build = getattr(self, f"_scenario_{scenario}")
                app = build(case) if case else build()
                self._backdate(app)
                if index % 10 == 0 or index == len(plan):
                    self.stdout.write(f"  {index}/{len(plan)} applications")
        self._summary()

    # --- accounts ------------------------------------------------------------------------

    def _bulk_users(self, password):
        R = User.Role
        applicants = []
        for suffix, name_en, name_ar, country, first, last in COMPANIES:
            company, _ = Company.objects.get_or_create(
                registration_no=f"{COMPANY_PREFIX}{suffix}",
                defaults={"name_en": name_en, "name_ar": name_ar, "license_no": f"PH-{suffix}", "country": country,
                          "is_verified": suffix != "2010",  # one unverified company
                          "contact_email": f"regulatory{suffix}@example.com"},
            )
            applicants.append(self._user(f"{USER_PREFIX}co{suffix}", password, R.COMPANY, first, last, company))
        for username, first, last, modules in REVIEWERS:
            reviewer = self._user(username, password, R.REVIEWER, first, last, specialties=modules)
            if reviewer.specialties_updated_by is None:
                set_specialties(reviewer, self.hod, modules)
        return applicants

    def _product_names(self):
        names = [(f"{brand} {product[0]} {product[3]}", product) for brand in BRANDS for product in PRODUCTS]
        self.rng.shuffle(names)
        return iter(names)

    # --- building blocks -----------------------------------------------------------------

    def _application(self, application_type=None, applicant=None):
        applicant = applicant or self.rng.choice(self.applicants)
        application_type = application_type or self.rng.choices(
            ["GENERIC", "NEW_DRUG", "VARIATION", "RENEWAL"], weights=[6, 3, 1, 1]
        )[0]
        name, (_, ingredient, form, strength, route, atc) = next(self.products)
        return self._new(applicant, application_type=application_type, product_name=name,
                         active_ingredients=ingredient, dosage_form=form, strength=strength, route=route,
                         atc_code=atc)

    def _submit_valid(self, app):
        self._upload(app, app.created_by, self._package(app, app.next_sequence_number()))
        services.submit(app, app.created_by)
        app.refresh_from_db()
        return app

    def _submit_zip(self, app, data):
        self._upload(app, app.created_by, data)
        services.submit(app, app.created_by)
        app.refresh_from_db()
        return app

    def _team(self, app):
        return {a.section: a.reviewer for a in app.assignments.select_related("reviewer")}

    def _assess(self, app, sections=None, weights=(7, 3, 1)):
        for section, reviewer in self._team(app).items():
            if sections is not None and section not in sections:
                continue
            assessment = self.rng.choices(["ACCEPTABLE", "MINOR", "MAJOR"], weights=weights)[0]
            services.add_review(app, reviewer, section, assessment, self.rng.choice(FINDINGS[assessment]))

    def _ask(self, app, due_days=30):
        sections = list(self._team(app))
        chosen = self.rng.sample(sections, k=min(len(sections), self.rng.randint(1, 2)))
        questions = "\n".join(f"{n}. {q}" for n, q in enumerate(self.rng.sample(QUESTIONS, self.rng.randint(1, 3)), 1))
        services.request_information(app, app.assigned_reviewer, questions,
                                     due_date=timezone.localdate() + datetime.timedelta(days=due_days),
                                     sections=chosen)

    def _answer(self, app, valid=True):
        if valid:
            data = self._package(app, "0001", documents=samples.response_documents())
        else:
            docs = samples.response_documents()
            docs[-1].modified_file = "../0000/index.xml#leaf-does-not-exist"  # BR-07
            data = self._package(app, "0001", documents=docs)
        services.respond_to_info_request(app, app.created_by, SimpleUploadedFile("response.zip", data),
                                         "Responses to the questions are in Module 1.11; updated data in Module 3.")
        app.refresh_from_db()

    def _reassess(self, app):
        """Fresh assessments for the modules an answered request concerned."""
        self._assess(app, sections=app.missing_sections(), weights=(8, 2, 0))

    def _complete(self, app, approve=True):
        recommendation = Application.Recommendation.APPROVE if approve else Application.Recommendation.REJECT
        summary = ("Quality, safety and efficacy are adequately demonstrated. Recommend approval." if approve else
                   "Major objections remain unresolved. Recommend rejection.")
        services.complete_review(app, app.assigned_reviewer, recommendation, summary)
        app.refresh_from_db()

    def _decide(self, app, outcome):
        text = {"APPROVED": "Meets quality, safety and efficacy requirements.",
                "REJECTED": "The benefit-risk balance is not established; major objections unresolved."}[outcome]
        services.decide(app, self.hod, outcome, text)
        app.refresh_from_db()

    def _notes(self, app):
        sequence = app.accepted_sequences().first()
        team = self._team(app)
        paths = [p for p in self._files(app) if p.endswith(".pdf")]
        for path in self.rng.sample(paths, k=min(3, len(paths))):
            section = DocumentNote.section_for(path)
            author = team.get(section) or app.assigned_reviewer
            DocumentNote.objects.create(application=app, sequence=sequence, path=path, page=1, section=section,
                                        body=self.rng.choice(NOTES), author=author)

    # --- scenarios (name: weight when filling up to --count) --------------------------------

    SCENARIOS = {
        "draft_empty": 3, "draft_uploaded": 4, "failed_twice": 2, "failed_then_fixed": 4, "awaiting_assignment": 2,
        "under_review_new": 5, "under_review_partial": 6, "info_open": 4, "info_overdue": 2, "info_response_failed": 2,
        "info_answered": 4, "complete_approve": 4, "complete_reject": 2, "returned_to_lead": 2,
        "approved": 10, "approved_after_questions": 6, "rejected": 4,
    }
    WARNINGS = {"BR-05", "FC-05", "FC-08", "BR-10"}

    def _scenario_draft_empty(self):
        return self._application()

    def _scenario_draft_uploaded(self):
        app = self._application()
        self._upload(app, app.created_by, self._package(app))
        return app

    def _scenario_failed(self, case):
        """One benchmark broken package: fails on exactly the rule(s) it is built to break."""
        app = self._application(case.application_type)
        max_file_mb = 1 if case.label == "FC-06" else settings.ECTD_MAX_FILE_MB
        with override_settings(ECTD_MAX_FILE_MB=max_file_mb):
            return self._submit_zip(app, case.build())

    def _scenario_warning(self, case):
        """A package that passes with warnings goes on to review."""
        app = self._application(case.application_type)
        self._submit_zip(app, case.build())
        if app.status == S.UNDER_REVIEW and self.rng.random() < 0.5:
            self._assess(app, sections=list(self._team(app))[:1])
        return app

    def _broken_generic(self, app):
        broken = self._files(app)
        broken["m2/22-intro/introduction.pdf"] = samples.make_pdf("Edited after checksum")  # BR-04
        broken["m3/32-body-data/Extra File.PDF"] = samples.make_pdf("Unreferenced", version="1.3")  # BR-05/08, FC-03
        return samples.to_zip(broken)

    def _scenario_failed_twice(self):
        app = self._application()
        self._submit_zip(app, self._broken_generic(app))
        files = self._files(app)
        del files["util/dtd/ich-ectd-3-2.dtd"]  # BR-09 on the second attempt
        return self._submit_zip(app, samples.to_zip(files))

    def _scenario_failed_then_fixed(self):
        app = self._application()
        self._submit_zip(app, self._broken_generic(app))
        self._submit_valid(app)
        if app.status == S.UNDER_REVIEW and self.rng.random() < 0.5:
            self._assess(app)
        return app

    def _scenario_awaiting_assignment(self):
        app = self._application()
        with override_settings(AUTO_ASSIGN_REVIEW_TEAMS=False):
            return self._submit_valid(app)

    def _scenario_under_review_new(self):
        return self._submit_valid(self._application())

    def _scenario_under_review_partial(self):
        app = self._submit_valid(self._application())
        sections = list(self._team(app))
        self._assess(app, sections=self.rng.sample(sections, k=self.rng.randint(1, max(1, len(sections) - 1))))
        self._notes(app)
        return app

    def _scenario_info_open(self):
        app = self._submit_valid(self._application())
        self._assess(app, sections=list(self._team(app))[:1])
        self._ask(app)
        return app

    def _scenario_info_overdue(self):
        app = self._submit_valid(self._application())
        self._ask(app, due_days=-self.rng.randint(3, 40))
        app.min_age_days = 60  # backdated far enough that the due date is past
        return app

    def _scenario_info_response_failed(self):
        app = self._submit_valid(self._application())
        self._ask(app)
        self._answer(app, valid=False)  # 0001 fails BR-07; the request stays open
        return app

    def _scenario_info_answered(self):
        app = self._submit_valid(self._application())
        self._assess(app)
        self._ask(app)
        self._answer(app)
        if self.rng.random() < 0.5:
            self._reassess(app)
        self._notes(app)
        return app

    def _scenario_complete_approve(self):
        app = self._submit_valid(self._application())
        self._assess(app, weights=(8, 2, 0))
        self._complete(app)
        return app

    def _scenario_complete_reject(self):
        app = self._submit_valid(self._application())
        self._assess(app, weights=(2, 2, 5))
        self._complete(app, approve=False)
        return app

    def _scenario_returned_to_lead(self):
        app = self._scenario_complete_approve()
        services.return_to_reviewer(app, self.hod, "Please confirm the stability commitment before I decide.")
        app.refresh_from_db()
        return app

    def _scenario_approved(self):
        app = self._scenario_complete_approve()
        self._decide(app, "APPROVED")
        return app

    def _scenario_approved_after_questions(self):
        app = self._submit_valid(self._application())
        self._assess(app)
        self._ask(app)
        self._answer(app)
        self._reassess(app)
        self._complete(app)
        self._decide(app, "APPROVED")
        return app

    def _scenario_rejected(self):
        app = self._scenario_complete_reject()
        self._decide(app, "REJECTED")
        return app

    # --- history spread over the past year ---------------------------------------------------

    def _gap(self, entry):
        """Time from this history entry to the next one."""
        if entry.to_status in (S.SUBMITTED, S.VALIDATING):  # the validator answers within minutes
            return datetime.timedelta(minutes=self.rng.randint(1, 12))
        if entry.to_status == S.VALIDATION_FAILED:
            return datetime.timedelta(days=self.rng.randint(2, 15), hours=self.rng.randint(0, 23))
        return datetime.timedelta(days=self.rng.randint(1, 20), hours=self.rng.randint(0, 23))

    def _backdate(self, app):
        """Move the application's records into the past, keeping their order (built seconds apart)."""
        now = timezone.now()
        history = list(StatusHistory.objects.filter(application=app).order_by("pk"))
        first = datetime.timedelta(days=self.rng.randint(1, 10), hours=self.rng.randint(0, 23))
        gaps = [first] + [self._gap(entry) for entry in history[:-1]]
        span = sum(gaps, datetime.timedelta())
        closed = app.status in (S.APPROVED, S.REJECTED, S.VALIDATION_FAILED)
        slack = datetime.timedelta(days=self.rng.randint(0, 240 if closed else 25), hours=self.rng.randint(0, 23))
        start = now - span - slack - datetime.timedelta(days=getattr(app, "min_age_days", 0))
        start = max(start, now - datetime.timedelta(days=420))

        # Anchors: (real time, fake time); everything else keeps its offset from the last anchor before it.
        anchors, fake = [(app.created_at, start)], start
        for gap, entry in zip(gaps, history):
            fake += gap
            anchors.append((entry.created_at, min(fake, now)))

        def shift(real):
            if real is None:
                return None
            base_real, base_fake = anchors[0]
            for anchor_real, anchor_fake in anchors:
                if anchor_real <= real:
                    base_real, base_fake = anchor_real, anchor_fake
            return min(base_fake + (real - base_real), now)

        for entry in history:
            StatusHistory.objects.filter(pk=entry.pk).update(created_at=shift(entry.created_at))
        sequences = list(app.sequences.all())
        for sequence in sequences:
            Sequence.objects.filter(pk=sequence.pk).update(uploaded_at=shift(sequence.uploaded_at))
        for run in ValidationRun.objects.filter(sequence__in=sequences):
            ValidationRun.objects.filter(pk=run.pk).update(started_at=shift(run.started_at),
                                                           finished_at=shift(run.finished_at))
        for model, fields in ((ReviewAssignment, ["assigned_at"]), (Review, ["created_at"]),
                              (DocumentNote, ["created_at", "updated_at"]), (Notification, ["created_at"])):
            for obj in model.objects.filter(application=app):
                model.objects.filter(pk=obj.pk).update(**{f: shift(getattr(obj, f)) for f in fields})
        for request in InfoRequest.objects.filter(application=app):
            created = shift(request.created_at)
            overdue = request.due_date and request.due_date < timezone.localdate()
            due = (now - datetime.timedelta(days=self.rng.randint(3, 30))) if overdue else created + datetime.timedelta(days=30)
            InfoRequest.objects.filter(pk=request.pk).update(created_at=created, answered_at=shift(request.answered_at),
                                                             due_date=due.date())
        decision = Decision.objects.filter(application=app).first()
        if decision:
            decided = shift(decision.decided_at)
            fields = {"decided_at": decided}
            if decision.approval_no:
                fields["approval_no"] = f"PPR-{decided:%Y}-{decision.pk:05d}"
                fields["valid_until"] = (services._add_years(decided.date(), settings.APPROVAL_VALIDITY_YEARS)
                                         - datetime.timedelta(days=1))
            Decision.objects.filter(pk=decision.pk).update(**fields)
        Application.objects.filter(pk=app.pk).update(
            created_at=start, submitted_at=shift(app.submitted_at), updated_at=anchors[-1][1],
            reference_no=f"MA-{start:%Y}-{app.pk:05d}",
        )

    def _summary(self):
        self.stdout.write(self.style.SUCCESS("Bulk data ready. Applications by status:"))
        for value, label in S.choices:
            self.stdout.write(f"  {label:<40} {Application.objects.filter(status=value).count():>4}")
        self.stdout.write(f"Bulk accounts (password as for seed_demo): {USER_PREFIX}co2001..{USER_PREFIX}co2010 "
                          f"(companies), {', '.join(r[0] for r in REVIEWERS)} (reviewers)")
