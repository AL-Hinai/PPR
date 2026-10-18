# Qualification protocol (IQ / OQ / PQ)

PPR · Document PPR-VAL-QP · Version 0.1 (protocol, not yet executed)

Execute on the production PythonAnywhere account (IQ, OQ) and with real dossiers (PQ). Record each result in the
execution log with the date, the executor and evidence (screenshot, command output, file).

## Installation qualification (IQ)

| ID | Check | Acceptance criterion |
|---|---|---|
| IQ-01 | Code version | The deployed commit equals the release commit; `git status` is clean |
| IQ-02 | Dependencies | `pip install -r requirements/production.txt` completes; `pip check` reports no conflicts |
| IQ-03 | Database | `manage.py migrate` applies all migrations; `manage.py makemigrations --check` reports no changes |
| IQ-04 | Security configuration | `manage.py check --deploy` reports no issues; the site redirects HTTP to HTTPS and sends `Strict-Transport-Security` and `Content-Security-Policy` headers |
| IQ-05 | Validation worker | The always-on task runs `run_validation_worker`; its log shows "Validation worker started" |
| IQ-06 | Backups | MySQL backups are enabled and a restore has been tested by Ministry IT |
| IQ-07 | Reference files | `apps/validation/dtd/ich-ectd-3-2.dtd` has the SHA-256 in `dtd/README.md`; the GCC DTD files are present |
| IQ-08 | Email | A password-reset email arrives from the configured sender; `SITE_URL` links open the site |

## Operational qualification (OQ)

| ID | Check | Acceptance criterion |
|---|---|---|
| OQ-01 | Automated suite | `python scripts/traceability.py --run` on the release: every requirement has tests, 0 failed |
| OQ-02 | Validation rules | `manage.py build_sample_packages --benchmark --out benchmark/synthetic` then `manage.py benchmark_validation benchmark/synthetic` exits without error (every package matches its manifest) |
| OQ-03 | Reports | For one failed and one passed sequence: on-screen report, CSV and printed PDF (short and long) show the same findings |
| OQ-04 | Background validation and notifications | Submit a sample package as a company: status "Validation in progress", then the result within 2 minutes; the company receives the in-app notification and the email with the report link |
| OQ-05 | Workflow | Run one application through validation, team assignment, assessment of every module, an information request answered by sequence 0001, recommendation, approval and certificate; the History tab lists every step with user and time |
| OQ-06 | Access control | As a second company: the first company's application, documents and report return "not found"; as a company: no assessment, notes or reviewer comments are visible |
| OQ-07 | Reviewer tools | The Current dossier tab shows the 0001 replacement; a note added on page 2 of a PDF appears in the notes page and is inserted into the module assessment; search finds a phrase from that document |
| OQ-08 | Assistant | `manage.py assistant_smoke_test` passes with the approved configuration (offline or model) |
| OQ-09 | Languages | Each page used in OQ-05 displays correctly in Arabic (right-to-left) |
| OQ-10 | Security behaviour | Five wrong passwords block sign-in to that account from that address for an hour; a password shorter than 12 characters is refused; a session ends when the browser closes |
| OQ-11 | API | Without a key the API answers 401; with a key it lists the approved application of OQ-05 and no drafts |

## Performance qualification (PQ)

| ID | Check | Acceptance criterion |
|---|---|---|
| PQ-01 | Large dossier | Upload and validate the largest expected real dossier (target: 500 MB); the site stays responsive and the result arrives |
| PQ-02 | Benchmark against the reference validator | Procedure in [validation_benchmark.md](../validation_benchmark.md): same overall verdict on every package; no open `ppr-missed` errors; remaining differences approved by the HOD |
| PQ-03 | Pilot | Two to three months with real submissions from volunteer companies in parallel with the current process; no critical defect open at the end; SSO, if configured, used by all staff |

## Execution log

| ID | Date | Executor | Result (pass / fail, deviation no.) | Evidence |
|---|---|---|---|---|
| | | | | |

## Release approval

| Role | Name | Signature | Date |
|---|---|---|---|
| Head of Department, Pharmacy | | | |
| Quality assurance | | | |
| Ministry IT | | | |
