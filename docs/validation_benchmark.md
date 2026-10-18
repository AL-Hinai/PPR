# Validation benchmark: PPR against a reference validator

Before go-live, PPR's eCTD technical validation should give the same verdict as the validator that
applicants and other GCC authorities already use (EXTEDO EURSvalidator with the GCC validation set). Otherwise a
dossier that passed the applicant's check could fail in PPR, or a real defect could pass. This procedure compares
the two on the same packages and records every difference, its cause and its fix.

## What you need

- A reference validator: an EURSvalidator evaluation or subscription that includes the **Asia Pacific (GCC)**
  validation set, or access to an authority that runs EURS.
- The current GCC validation criteria (pass/fail and best-practice list) from SFDA or the Ministry, if available.
  PPR's GCC rules come from the GCC Module 1 Specifications v1.5 because this list is not published.
- Real dossiers (optional but strongly recommended), anonymised and used with the applicant's written consent.
  Keep them outside git: `benchmark/` is ignored.

## 1. Build the package set

```powershell
.venv\Scripts\python manage.py build_sample_packages --benchmark --out benchmark\synthetic
```

This writes about 37 packages and a `manifest.csv`:

| Kind | Packages |
|---|---|
| Valid | `valid-new-drug.zip`, `valid-generic.zip`, and the two-sequence lifecycle `lifecycle-valid/0000.zip` + `0001.zip` |
| Warnings only | `br-05-unreferenced-file.zip`, `fc-05-font-not-embedded.zip` |
| Broken | one package per PPR error rule (`sch-01-…` to `gcc-09-…`), each failing on exactly the rules in the manifest |
| Broken lifecycle | `lifecycle-broken/0001.zip`: `modified-file` points to a leaf that `0000` does not contain |

A top-level zip is one application. The zips inside a sub-folder are one application's sequences, validated in name
order so that each accepted sequence is available to the next one, as on upload.

`manifest.csv` columns: `package`, `application_type` (`NEW_DRUG`, `GENERIC`, `VARIATION`, `RENEWAL`),
`expected_codes` (space-separated PPR rule codes; empty means the package should pass cleanly) and `description`.
The same packages prove each rule in the test-suite (`apps/validation/benchmark.py`), so the set stays current.

To add real dossiers, copy them to `benchmark\real\` (a sub-folder per application, one zip per sequence) and add
manifest rows only when the expected result is known; unlisted packages are validated but not judged.

## 2. Run PPR

```powershell
.venv\Scripts\python manage.py benchmark_validation benchmark\synthetic --out benchmark\synthetic-summary.csv --findings benchmark\synthetic-findings.csv
```

The command validates without the database and writes:

- **summary CSV**, one row per package: PPR verdict (`PASS`, `PASS_WITH_WARNINGS`, `FAIL`), error and warning
  counts, rule codes, expected codes, `matches_expected`, and blank `reference_verdict`, `agreement` and `notes`
  columns for the comparison.
- **findings CSV**, one row per finding: rule, severity, criterion, file, location and detail, with blank
  `reference_criterion`, `reference_severity`, `agreement` and `notes` columns.

It stops with an error if any package differs from its manifest row, so it can also run as a regression check.
Run it again with `--type GENERIC` (or another type) for packages the manifest does not list.

## 3. Run the reference validator

Validate the same zips in EURSvalidator with the GCC validation set (the validation set and DTD are selected
automatically from the regional XML). Save the **long report** (errors, warnings and details) for every package
as PDF next to the package, for the record.

## 4. Compare

For each package, fill `reference_verdict` in the summary sheet and mark `agreement`:

| Agreement | Meaning |
|---|---|
| `same` | Both pass, or both fail for the same defect |
| `ppr-missed` | The reference reports an error PPR does not: PPR lacks a check |
| `ppr-extra` | PPR reports an error the reference does not: a PPR false positive, or a stricter Oman requirement |
| `severity` | Same defect, but error in one and warning in the other |
| `artefact` | The difference comes from how the synthetic package was built, not from the rules |

Then map each reference criterion to the PPR rule that covers it in the findings sheet (`reference_criterion`).
Criteria with no PPR rule are the gap list.

## 5. Resolve and record

| Finding | Action |
|---|---|
| `ppr-missed` | Add or extend a rule in `apps/validation/rules/`, add a broken package for it in `apps/validation/benchmark.py`, re-run |
| `ppr-extra` | Fix the rule, or keep it and record why (for example an Oman MOH requirement) with the HOD's approval |
| `severity` | Align with the published GCC criteria; record the decision |
| `artefact` | Fix the sample builder in `apps/validation/samples.py` |

Every fix adds its package to the benchmark set with the expected codes, so the difference cannot come back.

## Acceptance criteria

1. Every package in the synthetic set matches its manifest (`benchmark_validation` exits without error).
2. On every package, PPR and the reference give the same overall verdict (pass or fail).
3. No `ppr-missed` errors remain open.
4. Every remaining `ppr-extra` or `severity` difference is documented and approved by the Head of Department.

Keep the filled sheets and the reference reports with the go-live validation records (`docs/validation/`).

## Known limits

- The GCC regional DTD in `apps/validation/dtd/gcc/` is transcribed from the specification; replace it with the
  files SFDA or the Ministry distributes when available, then re-run this benchmark.
- GCC-07 (required Module 1 documents) follows the Oman MOH draft eCTD guideline and should be confirmed with the
  Drug Safety Center.
- Synthetic packages are generated by PPR itself, so they cannot reveal requirements PPR does not know about. Real
  dossiers and the reference validator are what close that gap.
