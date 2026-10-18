# eCTD DTDs

| File | Source | SHA-256 |
|---|---|---|
| `ich-ectd-3-2.dtd` | Official ICH eCTD DTD v3.2 (part of the eCTD v3.2.2 specification), unchanged from `ich-ectd-3-2_dtd_0.zip` at https://admin.ich.org/sites/default/files/inline-files/ich-ectd-3-2_dtd_0.zip (downloaded 18 October 2026) | `c094aa2bded99564ade8ac78ae1540f95e518461b8eebe9a3063f67a165c2731` |

Rule SCH-03 validates every `index.xml` against this file (`ECTD_DTD_PATH`). Do not edit it:
`tests/test_validation_rules.py::test_bundled_dtd_is_the_official_ich_dtd` fails if its checksum changes.
After replacing a DTD, re-run validation with `manage.py validate_sequence <id> [...]`.
