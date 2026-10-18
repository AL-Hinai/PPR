"""Runs the three validation layers against one uploaded sequence."""
import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .context import Limits, ValidationContext
from .ectd import locate_sequence_dir
from .extract import ArchiveError, safe_extract
from .models import Finding, ValidationRun
from .rules import ALL_RULES
from .rules.base import Severity
from .rules.files import PACKAGE_RULE

logger = logging.getLogger(__name__)
VALIDATOR_VERSION = "2.1"  # 2.0: official ICH eCTD 3.2 DTD; 2.1: GCC Module 1 rules
MB = 1024 * 1024


def _extraction_dir(sequence) -> tuple[str, Path]:
    rel = f"extracted/{sequence.application_id}/{sequence.pk}"
    return rel, Path(settings.MEDIA_ROOT) / rel


def _previous_sequences(sequence) -> tuple[str, dict[str, Path]]:
    """(expected number for this sequence, accepted earlier sequence no. -> its folder)."""
    earlier = list(
        sequence.application.accepted_sequences()
        .exclude(pk=sequence.pk)
        .filter(uploaded_at__lt=sequence.uploaded_at)
    )
    folders = {}
    for seq in earlier:
        if seq.extracted_dir and seq.extracted_dir.is_dir():
            folders[seq.number] = locate_sequence_dir(seq.extracted_dir)[0]
    return f"{len(earlier):04d}", folders


def _capped(issues, rule, limit):
    if len(issues) <= limit:
        return issues
    extra = len(issues) - limit
    return [*issues[:limit], rule.issue(f"…and {extra} more finding(s) of this kind.")]


def run_rules(ctx) -> list:
    issues = []
    limit = settings.ECTD_MAX_FINDINGS_PER_RULE
    for rule in ALL_RULES:
        if not rule.applies(ctx):
            continue
        try:
            found = list(rule.check(ctx))
        except Exception:
            logger.exception("Validation rule %s crashed", rule.code)
            found = [rule.issue("The check could not be completed because of an internal error.")]
        issues.extend(_capped(found, rule, limit))
    return issues


def validate_package(zip_path, dest: Path, *, expected_number: str, application_type: str,
                     previous: dict[str, Path] | None = None) -> tuple[list, dict]:
    """Extract one package into ``dest`` and run every rule, without touching the database.

    Returns (issues, envelope). Used by ``validate_sequence`` and the ``benchmark_validation`` command.
    """
    try:
        safe_extract(
            zip_path,
            dest,
            max_total_bytes=settings.ECTD_MAX_UNCOMPRESSED_MB * MB,
            max_files=settings.ECTD_MAX_FILES,
        )
    except ArchiveError as exc:
        return [PACKAGE_RULE.issue(str(exc))], {}
    ctx = ValidationContext(
        root=dest,
        expected_number=expected_number,
        application_type=application_type,
        region=settings.ECTD_REGION,
        dtd_path=Path(settings.ECTD_DTD_PATH),
        limits=Limits(max_file_bytes=settings.ECTD_MAX_FILE_MB * MB),
        previous=previous or {},
        country=settings.ECTD_COUNTRY,
    )
    return run_rules(ctx), ctx.envelope or {}


def validate_sequence(sequence) -> ValidationRun:
    application = sequence.application
    run = ValidationRun.objects.create(sequence=sequence, validator_version=VALIDATOR_VERSION)
    rel_dir, dest = _extraction_dir(sequence)
    shutil.rmtree(dest, ignore_errors=True)

    expected, previous = _previous_sequences(sequence)
    issues, envelope = validate_package(
        sequence.package.path, dest,
        expected_number=expected, application_type=application.application_type, previous=previous,
    )

    Finding.objects.bulk_create(
        Finding(
            run=run,
            layer=i.layer,
            rule_code=i.rule_code,
            severity=i.severity,
            detail=i.detail,
            file_path=i.file_path[:500],
            location=i.location[:100],
        )
        for i in issues
    )
    run.error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
    run.warning_count = sum(1 for i in issues if i.severity == Severity.WARNING)
    run.info_count = sum(1 for i in issues if i.severity == Severity.INFO)
    run.finished_at = timezone.now()
    run.save()

    Status = sequence.ValidationStatus
    if run.error_count:
        sequence.validation_status = Status.FAILED
        sequence.extracted_path = ""
        shutil.rmtree(dest, ignore_errors=True)  # rejected packages are not kept unpacked
    else:
        sequence.validation_status = Status.PASSED_WITH_WARNINGS if run.warning_count else Status.PASSED
        sequence.extracted_path = rel_dir
    sequence.envelope = envelope
    sequence.save(update_fields=["validation_status", "extracted_path", "envelope"])
    logger.info(
        "Validated %s: %s (%d errors, %d warnings)", sequence, sequence.validation_status, run.error_count, run.warning_count
    )
    return run
