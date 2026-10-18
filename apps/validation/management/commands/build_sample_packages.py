from pathlib import Path

from django.core.management.base import BaseCommand

from apps.validation import samples
from apps.validation.benchmark import write_benchmark_set


class Command(BaseCommand):
    help = "Write demo eCTD zip packages (valid and broken) for manual testing."

    def add_arguments(self, parser):
        parser.add_argument("--out", default="sample_packages")
        parser.add_argument(
            "--benchmark", action="store_true",
            help="Write the benchmark set instead: valid packages, one broken package per rule, and manifest.csv.",
        )

    def handle(self, *args, out, benchmark, **options):
        folder = Path(out)
        folder.mkdir(parents=True, exist_ok=True)
        if benchmark:
            cases = write_benchmark_set(folder)
            self.stdout.write(f"wrote {len(cases)} packages and {folder / 'manifest.csv'}")
            return

        packages = {
            "0000-new-drug-valid.zip": samples.build_package("0000", "NEW_DRUG"),
            "0000-generic-valid.zip": samples.build_package("0000", "GENERIC"),
            "0001-response-valid.zip": samples.build_package("0001", documents=samples.response_documents()),
        }

        broken = samples.build_files("0000", application_type="NEW_DRUG")
        broken["m2/22-intro/introduction.pdf"] = samples.make_pdf("Changed after the checksum was taken")
        broken["m3/32-body-data/32p-drug-prod/product-1/32p1-desc-comp/Description.PDF"] = samples.make_pdf(
            "Old file", version="1.3"
        )
        del broken["index-md5.txt"]
        packages["0000-new-drug-broken.zip"] = samples.to_zip(broken)

        for name, data in packages.items():
            (folder / name).write_bytes(data)
            self.stdout.write(f"wrote {folder / name} ({len(data) // 1024} KB)")
