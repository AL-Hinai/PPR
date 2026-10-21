"""Content of the workflow training guide (/guide/).

Every workflow in the system, step by step, with the role that performs each step. Statuses come
from ``Application.Status`` so the guide uses the same names as the rest of the interface; button
and screen names are quoted exactly as they appear on screen.
"""
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.applications.models import Application

S = Application.Status
R = User.Role
SYSTEM = "SYSTEM"
LEAD = "LEAD"
ALL = "ALL"

# Who a step belongs to: label and badge colours.
ACTORS = {
    R.COMPANY: (_("Company applicant"), "bg-sky-50 text-sky-700 ring-sky-600/20"),
    R.REVIEWER: (_("Reviewer"), "bg-amber-50 text-amber-800 ring-amber-600/20"),
    LEAD: (_("Lead reviewer"), "bg-orange-50 text-orange-700 ring-orange-600/20"),
    R.HOD: (_("Head of Department"), "bg-violet-50 text-violet-700 ring-violet-600/20"),
    SYSTEM: (_("System"), "bg-slate-100 text-slate-700 ring-slate-500/20"),
    ALL: (_("Every user"), "bg-brand-50 text-brand-800 ring-brand-600/20"),
}

# The role filter at the top of the page. A workflow shows under a role when that role takes part in it.
AUDIENCES = [
    (R.COMPANY, _("Company applicant")),
    (R.REVIEWER, _("Reviewer")),
    (R.HOD, _("Head of Department")),
]

# The stages of the progress bar on each application, with the statuses inside them and who moves them on.
STAGES = [
    (_("Preparation"), [S.DRAFT], R.COMPANY),
    (_("Technical validation"), [S.SUBMITTED, S.VALIDATING, S.VALIDATION_FAILED], SYSTEM),
    (_("Assignment"), [S.VALIDATED], R.HOD),
    (_("Scientific review"), [S.UNDER_REVIEW, S.INFO_REQUESTED], R.REVIEWER),
    (_("HOD decision"), [S.REVIEW_COMPLETE], R.HOD),
    (_("Decision issued"), [S.APPROVED, S.REJECTED], None),
]

# The three ways an application goes back a step.
LOOPS = [
    (S.VALIDATION_FAILED, S.VALIDATING, _("The company corrects the package and resubmits it.")),
    (S.INFO_REQUESTED, S.UNDER_REVIEW, _("The company answers the lead reviewer's questions with a validated sequence.")),
    (S.REVIEW_COMPLETE, S.UNDER_REVIEW, _("The Head of Department returns the application for further review.")),
]

# One row per status: what it means and who acts next.
STATUSES = [
    (S.DRAFT, _("The company is preparing the application. Only the company can see it."), R.COMPANY),
    (S.SUBMITTED, _("The company has submitted the first eCTD sequence."), SYSTEM),
    (S.VALIDATING, _("The three-layer technical validation is running on the sequence."), SYSTEM),
    (S.VALIDATION_FAILED, _("The package has errors. The company corrects it and resubmits."), R.COMPANY),
    (S.VALIDATED, _("The dossier passed validation and waits for a review team."), R.HOD),
    (S.UNDER_REVIEW, _("Specialist reviewers assess their CTD modules."), R.REVIEWER),
    (S.INFO_REQUESTED, _("The review clock is stopped until the company answers the lead reviewer's questions."), R.COMPANY),
    (S.REVIEW_COMPLETE, _("The lead reviewer has sent a recommendation to the Head of Department."), R.HOD),
    (S.APPROVED, _("The marketing authorisation is granted and the certificate can be printed."), None),
    (S.REJECTED, _("The application is refused. The justification is on the Assessment tab."), None),
]

WORKFLOWS = [
    {
        "key": "account",
        "title": _("Sign in and manage your account"),
        "roles": [R.COMPANY, R.REVIEWER, R.HOD],
        "summary": _("Every user signs in with the account issued by the Pharmacy Department. There is no self-registration."),
        "steps": [
            (ALL, _("Open PPR and choose “Sign in”. Enter your username and password.")),
            (ALL, _("Department staff can use “Sign in with your Ministry account” instead of a password when single sign-on is switched on.")),
            (ALL, _("Use the language button in the top bar to switch between English and Arabic at any time.")),
            (ALL, _("To change your password, open the account menu (your initial) at the end of the top bar and choose “Change password”. Passwords need at least 12 characters.")),
            (ALL, _("Forgot your password? Choose “Forgot your password?” on the sign-in page. A one-time reset link is sent to your email address.")),
        ],
        "result": _("You land on the dashboard for your role."),
        "tips": [
            _("Five wrong passwords block sign-in to the account from that address for an hour."),
            _("Sessions end after a working day or when you close the browser. Sign out on shared computers."),
        ],
    },
    {
        "key": "create",
        "title": _("Create an application and submit the eCTD package"),
        "roles": [R.COMPANY],
        "from": S.DRAFT,
        "to": S.VALIDATING,
        "summary": _("The company enters the product details, uploads the first eCTD sequence (0000) and submits it."),
        "steps": [
            (R.COMPANY, _("Choose “New application” in the top bar.")),
            (R.COMPANY, _("Fill in the product details: application type, product name, active ingredients, dosage form, strength, route and ATC code. Choose “Create and continue”.")),
            (R.COMPANY, _("On the “eCTD sequences” tab, choose the zip file of sequence 0000 and select “Upload”.")),
            (R.COMPANY, _("Check the file name shown, then choose “Submit for validation”. While it is still a draft you can correct the details with “Edit”.")),
            (SYSTEM, _("The status changes to Submitted and then to Technical validation.")),
        ],
        "result": _("The validation report is ready within moments. The application is no longer a draft and the Head of Department can see it."),
        "tips": [
            _("The zip contains one sequence folder (for example 0000) with index.xml, index-md5.txt, the regional Module 1 XML and util/dtd/ich-ectd-3-2.dtd."),
            _("File names must be lowercase. PDFs must be version 1.4 to 1.7 with no password or security settings."),
            _("Uploading again before you submit replaces the waiting package."),
        ],
    },
    {
        "key": "validation",
        "title": _("Technical validation and correcting a failed package"),
        "roles": [R.COMPANY],
        "from": S.VALIDATING,
        "to": S.VALIDATED,
        "summary": _("The system checks every sequence in three layers, the way the FDA and the EMA do, before any scientific review."),
        "steps": [
            (SYSTEM, _("Layer 1, XML schema: index.xml is well-formed and valid against the ICH eCTD 3.2 DTD, and the regional Module 1 against the GCC specification.")),
            (SYSTEM, _("Layer 2, business rules: sequence numbers, MD5 checksums, required modules for the application type, lifecycle operations and naming rules.")),
            (SYSTEM, _("Layer 3, file compliance: accepted formats, PDF version, no passwords or scripts, embedded fonts and size limits.")),
            (SYSTEM, _("Any error fails the sequence (Validation failed). Warnings are reported but do not block it (Validated).")),
            (R.COMPANY, _("If validation failed, open “View report & resubmit”. Each finding shows the rule, the file and the line. Download it with “Report (CSV)” or “Report (PDF)” for your regulatory team.")),
            (R.COMPANY, _("Correct the package, upload it under “Upload a corrected package” and choose “Resubmit for validation”.")),
        ],
        "result": _("A passed sequence is accepted into the dossier and the application moves on to review team assignment."),
        "tips": [
            _("Only accepted sequences count. A failed upload keeps the same sequence number for the corrected package."),
            _("“Report & dossier” on an accepted sequence opens its document tree and the built-in PDF viewer."),
        ],
    },
    {
        "key": "specialties",
        "title": _("Set reviewer specialties"),
        "roles": [R.HOD],
        "summary": _("The Head of Department decides which CTD modules each reviewer may assess. Automatic team assignment relies on these specialties."),
        "steps": [
            (R.HOD, _("Choose “Reviewers” in the top bar.")),
            (R.HOD, _("Check the coverage cards at the top: a module marked “No reviewer” cannot be assigned automatically.")),
            (R.HOD, _("For each reviewer, tick the modules (M1 to M5) they are qualified to assess and save the row.")),
            (R.HOD, _("Choose “Make default lead” for the reviewer who should lead review teams by default.")),
        ],
        "result": _("Each change records who set it and when. Reviewers see their specialties on their dashboard but cannot change them."),
        "tips": [
            _("Give every module at least two reviewers so that work can be shared and leave can be covered."),
        ],
    },
    {
        "key": "assign",
        "title": _("Assign the review team"),
        "roles": [R.HOD],
        "from": S.VALIDATED,
        "to": S.UNDER_REVIEW,
        "summary": _("Each required CTD module is given to a specialist reviewer, and one team member is named lead reviewer."),
        "steps": [
            (SYSTEM, _("When a dossier passes validation, the system assigns the team automatically: each required module goes to the qualified reviewer with the fewest active modules, led by the default lead.")),
            (R.HOD, _("If a required module has no qualified reviewer, the application waits on your dashboard under “Validated – assign a review team”.")),
            (R.HOD, _("Open the application. In the “Next step” panel on the Overview tab, choose a reviewer for each required module and pick the lead reviewer from the team. Choose “Assign review team”.")),
            (R.HOD, _("To change the team later, use “Update review team”. A module given to another reviewer needs a new assessment from them.")),
        ],
        "result": _("The application is Under review and every team member is notified."),
        "tips": [
            _("The lead reviewer must also assess at least one module."),
            _("The “Reviewer workload” panel on your dashboard shows how many modules each reviewer is handling."),
        ],
    },
    {
        "key": "assess",
        "title": _("Assess your CTD modules"),
        "roles": [R.REVIEWER],
        "from": S.UNDER_REVIEW,
        "summary": _("Each specialist reads the dossier and records an assessment for the modules assigned to them."),
        "steps": [
            (R.REVIEWER, _("Open your dashboard. “Modules awaiting your assessment” lists each application and the modules you still owe.")),
            (R.REVIEWER, _("Read the dossier on the “Current dossier” tab. It shows every accepted sequence applied in order, with replaced and deleted documents marked. PDFs open in the built-in viewer.")),
            (R.REVIEWER, _("In the viewer, select text and choose “Add note on page” to keep internal notes. Notes are never shown to the company.")),
            (R.REVIEWER, _("On the “Assessment” tab, under “Add section review”, choose the module, the assessment (Acceptable, Minor issues or Major issues) and write your comments. “Insert my notes on this module” copies your notes in. Choose “Save review”.")),
        ],
        "result": _("Your module shows as assessed. When every module has its assessment, the lead reviewer can complete the review."),
        "tips": [
            _("You can read the whole dossier, but you can only assess the modules assigned to you."),
            _("After the company answers questions, the modules concerned show “Re-assessment needed”: record a fresh assessment."),
        ],
    },
    {
        "key": "questions",
        "title": _("Request information from the company (clock stop)"),
        "roles": [R.REVIEWER, R.COMPANY],
        "from": S.UNDER_REVIEW,
        "to": S.INFO_REQUESTED,
        "summary": _("The lead reviewer collects the team's questions and sends them to the company. The review clock stops until it answers."),
        "steps": [
            (LEAD, _("On the “Assessment” tab, open “Request information”.")),
            (LEAD, _("Tick the modules the questions concern, write the questions and, if needed, set the date the response is due.")),
            (LEAD, _("Choose “Send questions (clock stop)”. The company is notified straight away.")),
        ],
        "result": _("The status is Information requested. The application shows “Waiting for applicant” on the reviewers' dashboards."),
        "tips": [
            _("Only the lead reviewer can send questions. Other team members pass theirs to the lead."),
        ],
    },
    {
        "key": "respond",
        "title": _("Respond to an information request"),
        "roles": [R.COMPANY],
        "from": S.INFO_REQUESTED,
        "to": S.UNDER_REVIEW,
        "summary": _("The company answers with a new eCTD sequence, which is validated before it reaches the reviewers."),
        "steps": [
            (R.COMPANY, _("Open the application from “Action needed” on your dashboard and choose “Upload response”.")),
            (R.COMPANY, _("Read the “Questions from the reviewer” and the due date.")),
            (R.COMPANY, _("Write a short response summary, choose the zip of the next sequence and select “Upload and validate”.")),
            (SYSTEM, _("The response sequence goes through the same three-layer validation. If it fails, correct it and upload again.")),
        ],
        "result": _("A passed response sequence restarts the review clock (Under review). The modules concerned need a fresh assessment."),
        "tips": [
            _("Use the eCTD lifecycle operations (replace, append, delete) so the reviewers see exactly what changed."),
        ],
    },
    {
        "key": "recommend",
        "title": _("Complete the review and send the recommendation"),
        "roles": [R.REVIEWER],
        "from": S.UNDER_REVIEW,
        "to": S.REVIEW_COMPLETE,
        "summary": _("Once every assigned module has been assessed, the lead reviewer sends one recommendation for the whole team."),
        "steps": [
            (LEAD, _("Check “Section reviews” on the “Assessment” tab: every module needs an assessment and none may be waiting for re-assessment.")),
            (LEAD, _("Under “Complete review”, choose the recommendation (Approve or Reject) and write the assessment summary.")),
            (LEAD, _("Choose “Send to Head of Department”.")),
        ],
        "result": _("The status is Review complete – awaiting decision and the Head of Department is notified."),
        "tips": [
            _("If the Head of Department returns the application, it comes back Under review with their note in the history."),
        ],
    },
    {
        "key": "decide",
        "title": _("Decide and issue the certificate"),
        "roles": [R.HOD, R.COMPANY],
        "from": S.REVIEW_COMPLETE,
        "to": S.APPROVED,
        "summary": _("The Head of Department approves or rejects the application, or returns it to the reviewers."),
        "steps": [
            (R.HOD, _("Open the application from “Awaiting your decision” on your dashboard and choose “Decide”.")),
            (R.HOD, _("Read the “Lead reviewer recommendation” and the “Section reviews”.")),
            (R.HOD, _("Under “Record your decision”, choose Approved or Rejected, write the justification and choose “Confirm decision”.")),
            (R.HOD, _("To ask for more work instead, write what the reviewer should re-examine and choose “Return for further review”.")),
            (SYSTEM, _("An approval receives an approval number (PPR-year-number) and a validity date.")),
            (R.COMPANY, _("The company opens “Approval certificate” to print the bilingual certificate or save it as a PDF.")),
        ],
        "result": _("The status is Approved or Rejected. The decision cannot be changed in the system."),
        "tips": [
            _("Write the justification for the record: it appears on the Assessment tab and in the audit trail."),
        ],
    },
    {
        "key": "tracking",
        "title": _("Follow an application: notifications, history and search"),
        "roles": [R.COMPANY, R.REVIEWER, R.HOD],
        "summary": _("Tools every user has for knowing what happened and what to do next."),
        "steps": [
            (ALL, _("The bell in the top bar lists notifications. Every status change also sends an email to the people involved.")),
            (ALL, _("The progress bar at the top of each application shows its stage. The “Next step” panel on the Overview tab says what is expected and from whom.")),
            (ALL, _("The “History” tab is the audit trail: every status change with the user, the time and the note.")),
            (ALL, _("“Search dossiers” searches every application you can open: its details and the text of its accepted documents.")),
            (ALL, _("On the Applications list, filter by status or search by name to find work quickly.")),
        ],
        "result": _("You only ever see the applications your role allows: your company's, the ones assigned to you, or (Head of Department) every submitted one."),
        "tips": [],
    },
    {
        "key": "assistant",
        "title": _("Use the dossier assistant and review notes"),
        "roles": [R.COMPANY, R.REVIEWER, R.HOD],
        "summary": _("Tools for reading a dossier faster. They never replace the reviewer's own assessment."),
        "steps": [
            (ALL, _("Choose “Ask the assistant” at the bottom of the page. It knows the application and the document you have open.")),
            (ALL, _("Ask about composition, specifications, stability, clinical data or validation findings. Answers cite the document and page; open the citation to check it.")),
            (R.REVIEWER, _("Open “Assessment notes” on the Assessment tab to see the team's notes for an application. Filter to “My notes” or print them.")),
        ],
        "result": _("You find the relevant pages quickly and keep your notes with the dossier."),
        "tips": [
            _("The assistant can be wrong. Check the cited pages before relying on an answer."),
        ],
    },
]


# Recorded walkthroughs of the demo system, with captions in each language: static/core/training/<key>-<lang>.webm
# (and a .jpg poster). Durations are those of the English recordings.
VIDEOS = [
    {"key": "01-getting-started", "title": _("Getting started with PPR"), "duration": "1:21",
     "roles": [R.COMPANY, R.REVIEWER, R.HOD], "workflows": ["account", "tracking"]},
    {"key": "02-company-submit", "title": _("Create and submit an application"), "duration": "1:40",
     "roles": [R.COMPANY], "workflows": ["create", "validation"]},
    {"key": "03-hod-teams", "title": _("Reviewer specialties and review teams"), "duration": "1:13",
     "roles": [R.HOD], "workflows": ["specialties", "assign"]},
    {"key": "04-reviewer-assess", "title": _("Assess your CTD module"), "duration": "1:21",
     "roles": [R.REVIEWER], "workflows": ["assess", "assistant"]},
    {"key": "05-questions-response", "title": _("Questions to the applicant and the response"), "duration": "1:31",
     "roles": [R.REVIEWER, R.COMPANY], "workflows": ["questions", "respond"]},
    {"key": "06-lead-recommend", "title": _("Complete the review"), "duration": "0:52",
     "roles": [R.REVIEWER], "workflows": ["recommend"]},
    {"key": "07-hod-decide", "title": _("Decide and issue the certificate"), "duration": "1:09",
     "roles": [R.HOD, R.COMPANY], "workflows": ["decide"]},
]


def videos(language):
    """The walkthroughs in the reader's language (English for any language without its own recording)."""
    suffix = "ar" if language.startswith("ar") else "en"
    numbers = {w["key"]: n for n, w in enumerate(WORKFLOWS, start=1)}
    titles = {w["key"]: w["title"] for w in WORKFLOWS}
    return [{**v, "src": f"core/training/{v['key']}-{suffix}.webm", "poster": f"core/training/{v['key']}-{suffix}.jpg",
             "covers": [{"key": k, "number": numbers[k], "title": titles[k]} for k in v["workflows"]]}
            for v in VIDEOS]


def workflows():
    """The workflows with their actor labels resolved, numbered in order, and the video that shows them."""
    shown_in = {key: v["key"] for v in VIDEOS for key in v["workflows"]}
    items = []
    for number, workflow in enumerate(WORKFLOWS, start=1):
        steps = [{"actor": actor, "label": ACTORS[actor][0], "css": ACTORS[actor][1], "text": text}
                 for actor, text in workflow["steps"]]
        items.append({**workflow, "number": number, "steps": steps, "video": shown_in.get(workflow["key"])})
    return items


def stages():
    return [
        {"number": number, "label": label, "statuses": statuses,
         "actor": ACTORS[actor][0] if actor else None, "css": ACTORS[actor][1] if actor else ""}
        for number, (label, statuses, actor) in enumerate(STAGES, start=1)
    ]


def statuses():
    return [
        {"status": status, "meaning": meaning,
         "next": ACTORS[actor][0] if actor else None, "css": ACTORS[actor][1] if actor else ""}
        for status, meaning, actor in STATUSES
    ]


def matrix(items):
    """Who takes part in which workflow: one row per workflow, one column per audience."""
    return [{"number": w["number"], "key": w["key"], "title": w["title"],
             "cells": [role in w["roles"] for role, _label in AUDIENCES]} for w in items]
