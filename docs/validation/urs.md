# User requirements specification (URS)

PPR — Pharmaceutical Product Registration · Document PPR-VAL-URS · Version 0.1 (draft for approval)

The requirements the Pharmacy Department sets for PPR. Each one is verified by automated tests
(tagged `@pytest.mark.req("URS-nn")`, see [traceability.md](traceability.md)) and, where the table says so,
by a scripted check in the [IQ/OQ/PQ protocol](iq_oq_pq.md). Sources: the HOD's brief for an FDA/EMA-style
eCTD process, report PPR-CMP-001 (comparison with EXTEDO), the GCC Module 1 Specifications v1.5 and the Oman
MOH draft eCTD guideline.

| ID | Requirement | Priority | Also verified in |
|---|---|---|---|
| URS-01 | Pharmaceutical companies create applications, upload eCTD sequences (zip) and submit them through the portal. | High | OQ-01 |
| URS-02 | Every sequence is validated against the official ICH eCTD v3.2.2 DTD before review. | High | OQ-02 |
| URS-03 | Business rules are enforced: sequence numbering, MD5 checksums of the backbone and every document, references, lifecycle operations, ICH file naming. | High | OQ-02 |
| URS-04 | File compliance is enforced: accepted formats, PDF version 1.4–1.7, no passwords or security, no JavaScript, size limits, no empty files. | High | OQ-02 |
| URS-05 | GCC Module 1 v1.5 is enforced: regional DTD, envelope addressed to Oman (OM-MOH), submission type and unit, required Module 1 documents including Arabic and English leaflets. | High | OQ-02, PQ-02 |
| URS-06 | Validation results are shown per layer, exported as CSV and as a printable short/long report. | Medium | OQ-03 |
| URS-07 | Validation of large dossiers runs in the background and does not block the web site; failed jobs are retried and reported. | High | IQ-05, OQ-04 |
| URS-08 | The HOD sets reviewer specialties and assigns one specialist per CTD module (or the team is assembled automatically by workload). | High | OQ-05 |
| URS-09 | Reviewers assess only their modules; the lead reviewer sends questions and the recommendation once every module is assessed. | High | OQ-05 |
| URS-10 | Information requests are answered with a new sequence that must pass validation before the review resumes. | High | OQ-05 |
| URS-11 | The HOD approves or rejects; approval produces a certificate with a validity period. | High | OQ-05 |
| URS-12 | Every status change is recorded in an audit trail (who, when, from, to, note). | High | OQ-05 |
| URS-13 | Access is role-based: companies see only their own applications and never the internal assessment, notes or other companies' dossiers; reviewers see only their assigned applications. | High | OQ-06 |
| URS-14 | Reviewers can see the cumulative (current) dossier across all accepted sequences, with replaced and deleted documents. | Medium | OQ-07 |
| URS-15 | Reviewers can add notes to document pages without changing the original files, and collect them for the assessment report. | Medium | OQ-07 |
| URS-16 | Staff can search the text of every dossier they may open. | Medium | OQ-07 |
| URS-17 | The dossier assistant answers only from dossiers the reader may open and cites the pages it used. | Low | OQ-08 |
| URS-18 | The interface is available in Arabic (right-to-left) and English. | High | OQ-09 |
| URS-19 | Security: login lockout after repeated failures, passwords of at least 12 characters, password reset by email, HTTPS with HSTS, sessions limited to a working day, Content-Security-Policy. | High | IQ-04, OQ-10 |
| URS-20 | Users are notified in the application and by email of status changes and validation results. | Medium | OQ-04 |
| URS-21 | Other Ministry systems can read application status and decisions through a key-protected read-only API. | Low | OQ-11 |
| URS-22 | Department staff can sign in with their Ministry account (single sign-on), when Ministry IT provides an OpenID Connect provider. | Low | PQ-03 |
| URS-23 | PPR's validation verdicts are benchmarked against a reference validator before go-live. | High | PQ-02 |

## Approval

| Role | Name | Signature | Date |
|---|---|---|---|
| Head of Department, Pharmacy (system owner) | | | |
| Quality assurance | | | |
| Ministry IT | | | |
