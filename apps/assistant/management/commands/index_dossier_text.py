from django.core.management.base import BaseCommand

from apps.applications.models import Application
from apps.assistant.documents import index_sequences


class Command(BaseCommand):
    help = "Extract the text of accepted dossier documents so the assistant can search them."

    def add_arguments(self, parser):
        parser.add_argument("--application", type=int, help="Only this application id.")

    def handle(self, *args, **options):
        applications = Application.objects.all()
        if options["application"]:
            applications = applications.filter(pk=options["application"])
        for application in applications:
            indexed, total = index_sequences(application.accepted_sequences(), budget=float("inf"))
            self.stdout.write(f"{application.reference_no}: {indexed}/{total} documents")
