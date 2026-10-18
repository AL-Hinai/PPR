import json

from django.conf import settings
from django.http import HttpResponseBadRequest, JsonResponse, StreamingHttpResponse
from django.utils.translation import get_language
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.permissions import any_role_required
from apps.applications.models import Application

from . import agent
from .context import resolve_context
from .llm import provider
from .models import Conversation

MAX_QUESTION = 4000


def _conversation(user, create=True):
    conversation = user.assistant_conversations.first()
    if conversation is None and create:
        conversation = Conversation.objects.create(user=user)
    return conversation


def _links(user, application_ids) -> dict:
    """{application id: {sequence number: sequence id}} so the drawer can turn citations into links."""
    links: dict = {}
    applications = Application.objects.visible_to(user).filter(pk__in=[i for i in application_ids if i])
    for application in applications.prefetch_related("sequences"):
        links[str(application.pk)] = {s.number: s.pk for s in application.sequences.all() if s.is_accepted}
    return links


@any_role_required
@require_GET
def session(request):
    """The open thread and what the drawer is about, for the page the reader is on."""
    ctx = resolve_context(request, request.GET.get("page", ""), _pinned(request.GET.get("pinned")))
    conversation = _conversation(request.user, create=False)
    messages = list(conversation.messages.all()) if conversation else []
    llm = provider()
    return JsonResponse(
        {
            "context": ctx.as_json(),
            "messages": [agent.serialize(m) for m in messages],
            "links": _links(request.user, {m.application_id for m in messages} | {ctx.as_json()["application"]}),
            "provider": llm.name,
        }
    )


def _pinned(raw):
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


@any_role_required
@require_POST
def ask(request):
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return HttpResponseBadRequest("invalid JSON")
    question = str(body.get("question") or "").strip()[:MAX_QUESTION]
    if not question:
        return HttpResponseBadRequest("empty question")
    ctx = resolve_context(request, str(body.get("page") or ""), _pinned(body.get("pinned")))
    conversation = _conversation(request.user)
    language = get_language() or settings.LANGUAGE_CODE
    links = _links(request.user, {ctx.as_json()["application"]})

    def events():
        for event in agent.run(request.user, conversation, question, ctx, language):
            if event["type"] == "context":
                event["links"] = links
            yield json.dumps(event, ensure_ascii=False, default=str) + "\n"

    response = StreamingHttpResponse(events(), content_type="application/x-ndjson; charset=utf-8")
    # Ask proxies (nginx on PythonAnywhere) not to buffer, so text arrives as it is written.
    response["X-Accel-Buffering"] = "no"
    response["Cache-Control"] = "no-cache"
    return response


@any_role_required
@require_POST
def new_conversation(request):
    Conversation.objects.create(user=request.user)
    return JsonResponse({"ok": True})
