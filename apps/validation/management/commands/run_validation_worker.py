import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.validation import worker


class Command(BaseCommand):
    help = (
        "Run queued eCTD validations (VALIDATION_MODE = 'queue'). Keep it running as a PythonAnywhere "
        "always-on task; use --once to process the queue and exit."
    )

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process the queued jobs, then exit.")
        parser.add_argument("--sleep", type=float, default=5.0, help="Seconds to wait when the queue is empty.")

    def handle(self, *args, once, sleep, **options):
        if not once:
            self.stdout.write(f"Validation worker started; polling every {sleep:g}s.")
        while True:
            close_old_connections()  # MySQL drops idle connections; reconnect between polls
            stale = worker.requeue_stale()
            ran = worker.run_pending()
            if stale or ran:
                self.stdout.write(f"Requeued {stale} stale job(s); ran {ran} job(s).")
            if once:
                return
            time.sleep(sleep)
