# eCTD DTDs

| File | Source | SHA-256 |
|---|---|---|
| `ich-ectd-3-2.dtd` | Official ICH eCTD DTD v3.2 (part of the eCTD v3.2.2 specification), unchanged from `ich-ectd-3-2_dtd_0.zip` at https://admin.ich.org/sites/default/files/inline-files/ich-ectd-3-2_dtd_0.zip (downloaded 18 October 2026) | `c094aa2bded99564ade8ac78ae1540f95e518461b8eebe9a3063f67a165c2731` |

| `gcc/gc-regional.dtd`, `gcc/gc-envelope.mod`, `gcc/gc-leaf.mod` | GCC regional DTD 1.1 (envelope module 1.2), **transcribed** from Appendix 6 of the *GCC Module 1 Specifications v1.5* (SFDA, November 2015): https://www.sfda.gov.sa/sites/default/files/2021-03/GCC%20Module%201%20Specifications_v1.5-EN.pdf | not byte-identical to SFDA's files |

The GCC DTD files are not published as downloads, so these were typed in from the specification. They declare
the same elements, attributes and value lists, but their whitespace and comments differ, so their MD5 cannot
match the checksums SFDA publishes. Replace them with the files SFDA or the Ministry distributes when available.
Rule GCC-02 validates `m1/gc/gc-regional.xml` against `gcc/gc-regional.dtd`.

Rule SCH-03 validates every `index.xml` against `ich-ectd-3-2.dtd` (`ECTD_DTD_PATH`). Do not edit it:
`tests/test_validation_rules.py::test_bundled_dtd_is_the_official_ich_dtd` fails if its checksum changes.
After replacing a DTD, re-run validation with `manage.py validate_sequence <id> [...]`.
