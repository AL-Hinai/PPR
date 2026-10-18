# PPR — Pharmaceutical Product Registration

A Django + Tailwind system for the Pharmacy Department. Pharmaceutical companies apply
for medicine approval (marketing authorisation) by uploading dossiers in the
international **eCTD** format. As at the FDA and EMA, every package must pass automated
**eCTD technical validation** before any scientific review starts.

Bilingual **English / Arabic (RTL)**. Runs on SQLite locally and MySQL on PythonAnywhere.

## Workflow

```
Company: Draft ──upload 0000──► Submitted ──► Technical validation ─┬─► Validation failed ──fix & resubmit──┐
                                                                     └─► Validated ◄──────────────────────────┘
HOD:     Validated ──assign review team (one specialist per CTD module + lead)──► Under review
Lead reviewer: Under review ──request info──► Information requested ──company uploads 0001 (validated)──► Under review
Module reviewers: assess their own modules · Lead reviewer: all modules assessed ──recommendation──► Review complete
HOD:     Review complete ──► Approved (certificate) | Rejected | back to Under review
```

Every transition goes through `apps/applications/workflow.py`. That module checks the role, writes the
audit trail (`StatusHistory`) and sends in-app and email notifications.

| Role | Can |
|---|---|
| **Company applicant** | Create applications, upload eCTD sequences, submit, answer information requests, print the certificate |
| **Reviewer** | Specialised in CTD modules (M1–M5), set by the HOD on the Reviewers page and read-only for everyone else. Assesses only the modules the HOD assigned them; reads the whole dossier of those applications |
| **Lead reviewer** | One reviewer of the team, named by the HOD: sends questions to the applicant and the recommendation once every module is assessed |
| **Head of Department (HOD)** | Set each reviewer's specialties (a module cannot be removed while the reviewer holds it on an active review), assign the review team (only qualified specialists are offered per module), see KPIs, approve/reject, return to the lead |
| Superuser | Django admin (`/admin/`): users, companies, roles |

## eCTD technical validation (3 layers, 20 rules)

Code: `apps/validation/`. Each rule is a small class in `rules/`, so new rules can be added without touching the engine.

| Layer | Rule | Checks |
|---|---|---|
| 1. XML schema | SCH-01 | `index.xml` exists |
| | SCH-02 | `index.xml` is well-formed |
| | SCH-03 | `index.xml` is valid against the ICH eCTD 3.2 DTD |
| | SCH-04 | Regional Module 1 XML (`m1/<region>/<region>-regional.xml`) exists and is well-formed |
| 2. Business rules | BR-01 | One sequence folder with the expected number (0000, 0001, …) |
| | BR-02 | `index-md5.txt` matches the MD5 of `index.xml` |
| | BR-03 | Every leaf `xlink:href` points to an existing file inside the sequence |
| | BR-04 | Every leaf checksum matches the file's MD5 |
| | BR-05 | No unreferenced files (warning) |
| | BR-06 | Modules required for the application type contain documents |
| | BR-07 | Lifecycle operations (new/replace/append/delete) are valid; `modified-file` resolves to a leaf in an earlier accepted sequence |
| | BR-08 | ICH naming: lowercase `a-z0-9-`, names ≤ 64 characters, paths ≤ 180 characters |
| | BR-09 | `util/dtd/ich-ectd-3-2.dtd` present |
| 3. File compliance | FC-00 | Safe, valid ZIP (no zip-slip, symlinks, encryption or zip bombs) |
| | FC-01 | Accepted file formats only (`.docx` only in Module 1) |
| | FC-02 | PDFs open without passwords or security settings |
| | FC-03 | PDF version 1.4–1.7 |
| | FC-04 | No JavaScript or launch actions in PDFs |
| | FC-05 | Fonts embedded (warning) |
| | FC-06 / FC-07 | File size limit, no empty files |

Any **error** fails the sequence. Warnings let it pass ("Passed with warnings"). Each run is stored as a
`ValidationRun` with its `Finding`s, shown as a report (with CSV export). Accepted sequences can be browsed
in the dossier viewer (CTD tree → documents).

> **Note on the DTD:** `apps/validation/dtd/ich-ectd-3-2.dtd` is the official ICH eCTD v3.2 DTD, unchanged
> (source and checksum in [apps/validation/dtd/README.md](apps/validation/dtd/README.md)). `ECTD_DTD_PATH`
> can point elsewhere if needed. The Module 1 region folder is set with
> `ECTD_REGION` (default `gcc`).

## Dossier assistant

A chat drawer on every page (ported from Roaa's assistant): the "Ask the assistant" button opens it.
It knows which medicine the reader is working on and answers from that dossier's documents, citing
`sequence/path p.N` as links to the page.

- **Context detection** (`apps/assistant/context.py`): the drawer sends the page URL, which the server
  resolves to the application, sequence and document. Dossier PDFs open in a new tab, so opening one is
  remembered in the session and becomes the context when the reader returns ("Recently opened"). The
  **Ask** button next to each document in the dossier viewer pins that document.
- **Agent** (`agent.py`, `tools.py`): a tool-calling loop over read-only tools: application overview,
  list / search / read documents, validation report, find applications. Every tool is limited by
  `Application.objects.visible_to(user)`, so readers only see the dossiers they can already open.
  Without Celery on PythonAnywhere the loop runs inside the request and streams NDJSON to the drawer.
- **Documents** (`documents.py`): PDF/DOCX text is extracted with pypdf when first needed and cached per page
  in `DocumentText`. For large dossiers, pre-build the cache with `manage.py index_dossier_text`.
- **Model**: any OpenAI-compatible chat API (DeepSeek by default). Set `ASSISTANT_API_KEY` (and optionally
  `ASSISTANT_BASE_URL`, `ASSISTANT_MODEL`) in `.env`. Without a key the drawer runs in **offline mode**:
  it shows the best-matching passages instead of a written answer.

## Quick start (Windows / PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements\local.txt
copy .env.example .env
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py seed_demo          # demo users + applications at every stage
.venv\Scripts\python manage.py runserver
```

Open http://127.0.0.1:8000. Demo users: `acme`, `gulfpharma` (companies), `hod`, and one reviewer per discipline:
`rev_regulatory` (M1, M2), `rev_quality` (M3), `rev_nonclinical` (M4), `rev_clinical` (M5).
All use the password printed by `seed_demo` (default `Demo@2026`, or set `DEMO_PASSWORD`).
Create an admin with `manage.py createsuperuser`.

Sample packages for manual uploads (valid, broken and a 0001 response):

```powershell
.venv\Scripts\python manage.py build_sample_packages --out sample_packages
```

## Tailwind CSS

django-tailwind runs in **standalone mode** (no Node.js). The Tailwind CLI binary downloads automatically.

```powershell
.venv\Scripts\python manage.py tailwind start   # watch mode while developing
.venv\Scripts\python manage.py tailwind build   # minified build; commit theme/static/css/dist/styles.css
```

The source is `theme/static_src/src/styles.css` (brand colours and component classes such as `.btn`, `.card`, `.input`).
Templates use logical utilities (`ms-*`, `pe-*`, `text-start`, `rtl:`) so one template works in both directions.

## Translations (Arabic)

GNU gettext isn't needed. `scripts/i18n.py` does what `makemessages` / `compilemessages` do:

```powershell
.venv\Scripts\python scripts\i18n.py extract   # update locale\ar\LC_MESSAGES\django.po
# edit the .po file
.venv\Scripts\python scripts\i18n.py compile   # build django.mo (committed)
```

## Tests

```powershell
.venv\Scripts\python -m pytest
```

The tests build eCTD packages in code (`apps/validation/samples.py`): a valid package plus one broken
variant per rule. They also cover the full workflow, permissions, protected file access and every page in both languages.

## Useful commands

| Command | Purpose |
|---|---|
| `manage.py validate_sequence <id> [...]` | Re-run validation (e.g. after updating the DTD) |
| `manage.py seed_demo --reset` | Recreate demo data |
| `manage.py build_sample_packages` | Write demo eCTD zips |
| `manage.py index_dossier_text [--application <id>]` | Extract dossier text for the assistant |

## Project layout

```
config/settings/{base,local,test,production}.py
apps/accounts       custom User (role, company), role decorators
apps/companies      Company profile
apps/applications   Application, Sequence, Review, InfoRequest, Decision, StatusHistory, workflow, services, views
apps/validation     eCTD engine: extract.py, context.py, pdf.py, rules/, engine.py, samples.py, dtd/
apps/notifications  in-app + email notifications
apps/assistant      dossier assistant: context, tools, agent loop, LLM client, document text cache
apps/core           dashboards, UI template tags, seed_demo
templates/          Tailwind templates (RTL aware)
theme/              django-tailwind app
locale/ar/          Arabic translations
docs/               deployment guide
```

Deployment: see [docs/deploy_pythonanywhere.md](docs/deploy_pythonanywhere.md).
