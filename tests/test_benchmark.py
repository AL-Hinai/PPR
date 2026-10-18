"""The exported benchmark set validates as its manifest says, without the database."""
import csv

import pytest
from django.core.management import CommandError, call_command

from apps.validation.benchmark import MANIFEST, benchmark_cases, run_benchmark, write_benchmark_set

pytestmark = [pytest.mark.req("URS-23")]


@pytest.fixture
def benchmark_set(tmp_path):
    write_benchmark_set(tmp_path)
    return tmp_path


def test_every_package_matches_its_manifest_row(benchmark_set):
    results = run_benchmark(benchmark_set)
    assert len(results) == len(benchmark_cases())
    assert [r.package for r in results if not r.matches] == []
    assert not [i for r in results for i in r.issues if "internal error" in i.detail]  # no rule crashed
    by_package = {r.package: r for r in results}
    assert by_package["valid-new-drug.zip"].verdict == "PASS"
    assert by_package["lifecycle-valid/0001.zip"].verdict == "PASS"  # 0000 of the same folder is its predecessor
    assert by_package["br-05-unreferenced-file.zip"].verdict == "PASS_WITH_WARNINGS"
    assert by_package["lifecycle-broken/0001.zip"].codes == {"BR-07"}


def test_command_writes_comparison_sheets(benchmark_set, tmp_path):
    summary, findings = tmp_path / "summary.csv", tmp_path / "findings.csv"
    call_command("benchmark_validation", str(benchmark_set), out=str(summary), findings=str(findings))
    with open(summary, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(benchmark_cases())
    assert {row["matches_expected"] for row in rows} == {"yes"}
    assert "reference_verdict" in rows[0]  # left blank for the reference validator's result
    with open(findings, encoding="utf-8-sig") as fh:
        assert any(row["rule"] == "GCC-07" for row in csv.DictReader(fh))


def test_command_fails_when_findings_differ_from_the_manifest(benchmark_set, tmp_path):
    manifest = benchmark_set / MANIFEST
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("valid-new-drug.zip,NEW_DRUG,,",
                                                                     "valid-new-drug.zip,NEW_DRUG,BR-03,"),
                        encoding="utf-8")
    with pytest.raises(CommandError, match="valid-new-drug.zip"):
        call_command("benchmark_validation", str(benchmark_set),
                     out=str(tmp_path / "s.csv"), findings=str(tmp_path / "f.csv"))
