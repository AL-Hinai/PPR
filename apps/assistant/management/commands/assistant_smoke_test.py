import re
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.applications.models import Application
from apps.assistant import agent
from apps.assistant.context import PageContext
from apps.assistant.documents import resolve_file
from apps.assistant.models import Conversation
from apps.assistant.models import Message as StoredMessage

CITATION_RE = re.compile(r"\[(\d{4})/([^\]\s]+?) p\.(\d+)\]")


class Command(BaseCommand):
    help = (
        "Ask the dossier assistant one question with the configured model (ASSISTANT_API_KEY) and check the "
        "answer: provider, tools used, citations that resolve to real dossier pages, latency and tokens."
    )

    def add_arguments(self, parser):
        parser.add_argument("--application", type=int, help="Application id (default: one with an accepted sequence).")
        parser.add_argument("--user", default="", help="Username to ask as (default: a Head of Department).")
        parser.add_argument("--question", default="What is the proposed shelf life and storage condition? Cite the pages.")
        parser.add_argument("--language", default="en")

    def handle(self, *args, application, user, question, language, **options):
        reader = User.objects.filter(username=user).first() if user else User.objects.filter(
            role=User.Role.HOD, is_active=True).first()
        if reader is None:
            raise CommandError("No user to ask as. Pass --user.")
        apps = Application.objects.visible_to(reader).filter(sequences__validation_status__in=["PASSED", "PASSED_WITH_WARNINGS"])
        app = apps.filter(pk=application).first() if application else apps.distinct().order_by("-pk").first()
        if app is None:
            raise CommandError("No application with an accepted sequence is visible to this user.")

        conversation = Conversation.objects.create(user=reader)
        started, text, steps, outcome, provider = time.monotonic(), "", [], None, ""
        try:
            for event in agent.run(reader, conversation, question, PageContext(application=app), language):
                kind = event["type"]
                if kind == "context":
                    provider = event["provider"]
                elif kind == "step":
                    steps.append(event)
                elif kind == "text":
                    text += event["text"]
                elif kind == "done":
                    outcome, text = event["message"], event["message"]["content"]
                elif kind in ("stopped", "error"):
                    outcome = event
        finally:
            elapsed = time.monotonic() - started

        self.stdout.write(f"Provider: {provider} ({settings.ASSISTANT['MODEL'] if provider != 'offline' else 'no API key'})")
        self.stdout.write(f"Application: {app.reference_no} · {app.product_name} · asked as {reader.username}")
        self.stdout.write(f"Question: {question}")
        self.stdout.write(f"Tools: {', '.join(s['tool'] + ('' if s['ok'] else ' (failed)') for s in steps) or '-'}")
        self.stdout.write(f"Latency: {elapsed:.1f}s")
        stored = StoredMessage.objects.filter(pk=(outcome or {}).get("id")).first()
        if stored and stored.prompt_tokens is not None:
            self.stdout.write(f"Tokens: {stored.prompt_tokens} prompt + {stored.completion_tokens} completion")
        self.stdout.write("\n" + text.strip() + "\n")

        if not outcome or outcome.get("type") in ("stopped", "error"):
            raise CommandError(f"The assistant did not answer: {outcome}")
        citations = CITATION_RE.findall(text)
        sequences = {s.number: s for s in app.accepted_sequences()}
        broken = [c for c in citations if c[0] not in sequences or resolve_file(sequences[c[0]], c[1]) is None]
        self.stdout.write(f"Citations: {len(citations)} ({len(broken)} do not resolve to a dossier file)")
        if not citations:
            raise CommandError("The answer cites no dossier page.")
        if broken:
            raise CommandError(f"Citations that do not resolve: {broken}")
        self.stdout.write(self.style.SUCCESS("Smoke test passed."))
