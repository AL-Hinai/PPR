from django.core.management.base import BaseCommand

from apps.api.models import ApiToken


class Command(BaseCommand):
    help = "Issue a read-only API key for another system. The key is printed once; only its hash is stored."

    def add_arguments(self, parser):
        parser.add_argument("name", help="The system that will use the key, e.g. 'Drug register'.")

    def handle(self, *args, name, **options):
        token, key = ApiToken.issue(name)
        self.stdout.write(f"API key for {token.name} (store it now; it cannot be shown again):\n{key}")
