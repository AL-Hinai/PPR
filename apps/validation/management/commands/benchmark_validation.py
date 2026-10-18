from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.applications.models import Application
from apps.validation.benchmark import run_benchmark, write_results
from apps.validation.engine import VALIDATOR_VERSION


class Command(BaseCommand):
    help = (
        "Validate a folder of eCTD packages without the database and write CSV results to compare with a "
        "reference validator (see docs/validation_benchmark.md). Top-level zips are separate applications; "
        "the zips in a sub-folder are one application's sequences in name order. A manifest.csv states the "
        "application type and the rule codes PPR is expected to report."
    )

    def add_arguments(self, parser):
        parser.add_argument("folder")
        parser.add_argument("--out", default="benchmark-summary.csv", help="One row per package.")
        parser.add_argument("--findings", default="benchmark-findings.csv", help="One row per finding.")
        parser.add_argument("--type", default="NEW_DRUG", choices=Application.Type.values,
                            help="Application type for packages the manifest does not list.")

    def handle(self, *args, folder, out, findings, type, **options):
        folder = Path(folder)
        if not folder.is_dir():
            raise CommandError(f"{folder} is not a folder.")
        results = run_benchmark(folder, default_type=type)
        if not results:
            raise CommandError(f"No .zip packages in {folder}.")
        write_results(results, Path(out), Path(findings))

        for r in results:
            mark = {None: "  ", True: "ok", False: "NO"}[r.matches]  # ASCII: Windows consoles are often cp1252
            codes = " ".join(sorted(r.codes)) or "-"
            self.stdout.write(f"{mark} {r.package:<48} {r.verdict:<19} {codes}")
        mismatches = [r for r in results if r.matches is False]
        self.stdout.write(
            f"\nValidator v{VALIDATOR_VERSION}: {len(results)} packages, "
            f"{sum(r.verdict == 'FAIL' for r in results)} failed, {len(mismatches)} differ from the manifest."
        )
        self.stdout.write(f"Wrote {out} and {findings}.")
        if mismatches:
            raise CommandError(
                "PPR's findings differ from the manifest for: " + ", ".join(r.package for r in mismatches)
            )
