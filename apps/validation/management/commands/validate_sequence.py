from django.core.management.base import BaseCommand, CommandError

from apps.applications.models import Sequence
from apps.validation.engine import validate_sequence


class Command(BaseCommand):
    help = "Re-run eCTD technical validation for one or more sequences (by id)."

    def add_arguments(self, parser):
        parser.add_argument("sequence_ids", nargs="+", type=int)

    def handle(self, *args, sequence_ids, **options):
        for pk in sequence_ids:
            try:
                sequence = Sequence.objects.select_related("application").get(pk=pk)
            except Sequence.DoesNotExist as exc:
                raise CommandError(f"Sequence {pk} does not exist.") from exc
            run = validate_sequence(sequence)
            self.stdout.write(
                f"{sequence}: {sequence.get_validation_status_display()} "
                f"({run.error_count} errors, {run.warning_count} warnings)"
            )
