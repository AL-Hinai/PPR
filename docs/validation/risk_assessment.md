# Risk assessment

PPR · Document PPR-VAL-RA · Version 0.1 (draft)

Severity (S) and likelihood before controls (L): 1 low – 3 high. Risk = S × L; 6 or more is high and needs a
verified control before go-live.

| # | Hazard | Effect | S | L | Risk | Controls in PPR | Verified by |
|---|---|---|---|---|---|---|---|
| R1 | A defective dossier passes technical validation | Review of an unusable or tampered dossier | 3 | 2 | 6 | Official ICH DTD (checksum-pinned), 29 rules incl. GCC M1, MD5 of every file, one broken package per rule | URS-02–05 tests, PQ-02 benchmark |
| R2 | A valid dossier is rejected | Delay for the applicant; disputes | 2 | 2 | 4 | Rules aligned with GCC M1 v1.5; benchmark against EURSvalidator; warnings vs errors per specification | PQ-02 |
| R3 | GCC regional DTD differs from SFDA's file (transcribed from the specification) | R1 or R2 for Module 1 | 2 | 2 | 4 | Transcription documented; replace with distributed files when available; GCC-02 tests | PQ-02, dtd/README.md |
| R4 | A company sees another company's dossier or the internal assessment | Breach of confidential commercial information | 3 | 1 | 3 | `visible_to()` on every view and assistant tool; applicants never get assessments or notes; permission-checked file views; no public media | URS-13 tests, OQ-06 |
| R5 | Unauthorised sign-in (guessed or stolen password) | Access to dossiers, false decisions | 3 | 2 | 6 | Lockout after 5 failures, 12-character passwords, HTTPS + HSTS, 8-hour sessions, optional SSO for staff | URS-19 tests, IQ-04 |
| R6 | Cross-site scripting through dossier content | Session theft | 3 | 1 | 3 | Django auto-escaping, Content-Security-Policy (scripts from this site only), non-PDF files sandboxed | URS-19 tests |
| R7 | A large upload blocks the web server or times out | Site unavailable; lost submissions | 2 | 3 | 6 | Background worker (`VALIDATION_MODE=queue`), upload limits, zip-bomb and file-count limits | URS-07 tests, IQ-05, PQ-01 |
| R8 | The worker stops | Submissions stay "in progress" | 2 | 2 | 4 | Always-on task restarts it; stale jobs retried; failures notify the HOD; jobs visible in admin | URS-07 tests, IQ-05 |
| R9 | Status changed without a record | Decisions cannot be reconstructed | 3 | 1 | 3 | Every change through `workflow.transition()` with `StatusHistory`; role checks per transition | URS-12 tests |
| R10 | Dossier text sent to an external AI provider | Confidential data leaves the Ministry | 3 | 2 | 6 | Offline by default; external host shown to readers; decision record in assistant_data_protection.md | URS-17 tests, decision record |
| R11 | Loss of data (database or files) | Loss of regulatory records | 3 | 1 | 3 | PythonAnywhere MySQL backups; packages kept with SHA-256; backup and restore procedure to be agreed with IT | IQ-06 |
| R12 | Wrong reviewer assesses a module | Unqualified assessment | 2 | 1 | 2 | Specialties set by the HOD only; assessments limited to assigned modules | URS-08–09 tests |

Residual risks after controls are acceptable once the "Verified by" column is complete and PQ-02 shows no
open missed errors.

## Approval

| Role | Name | Signature | Date |
|---|---|---|---|
| Head of Department, Pharmacy | | | |
| Quality assurance | | | |
