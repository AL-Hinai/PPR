"""The dossier assistant: context detection, access scoping, document tools and the agent loop."""
import json

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.applications import services
from apps.assistant import agent
from apps.assistant.context import SESSION_KEY, resolve_context
from apps.assistant.llm import Completion, Finished, OfflineProvider, TextDelta, ToolCall
from apps.assistant.models import Conversation, DocumentText
from apps.assistant.tools import ToolBox
from apps.validation import samples

from .conftest import upload

STABILITY = samples.STABILITY_PATH


@pytest.fixture
def dossier(make_application, applicant, reviewer, hod):
    """An application under review with an accepted sequence 0000."""
    application = make_application()
    upload(application, applicant, samples.build_package("0000"))
    services.submit(application, applicant)
    services.assign_reviewer(application, hod, reviewer)
    return application


def _request(user, session=None):
    request = RequestFactory().get("/")
    request.user = user
    request.session = session if session is not None else {}
    return request


def _file_url(application, path=STABILITY):
    sequence = application.sequences.get()
    return reverse("applications:sequence_file", args=[application.pk, sequence.pk, path])


# --- context ---------------------------------------------------------------------

@pytest.mark.django_db
def test_context_detects_application_sequence_and_document(dossier, reviewer):
    detail = resolve_context(_request(reviewer), f"/applications/{dossier.pk}/?tab=review")
    assert detail.application == dossier and detail.tab == "review" and not detail.document_path

    on_file = resolve_context(_request(reviewer), _file_url(dossier))
    assert on_file.sequence.number == "0000"
    assert on_file.document_path == STABILITY and on_file.document_source == "page"


@pytest.mark.django_db
def test_context_ignores_applications_the_reader_cannot_see(dossier, other_applicant, reviewer2):
    for user in (other_applicant, reviewer2):
        assert resolve_context(_request(user), f"/applications/{dossier.pk}/").application is None


@pytest.mark.django_db
def test_opening_a_document_makes_it_the_context(client, dossier, reviewer):
    client.force_login(reviewer)
    assert client.get(_file_url(dossier)).status_code == 200
    assert client.session[SESSION_KEY]["path"] == STABILITY

    # Back on the application page (or the dashboard) the document opened in the other tab is the context.
    for page in (f"/applications/{dossier.pk}/", "/dashboard/"):
        response = client.get(reverse("assistant:session"), {"page": page})
        context = response.json()["context"]
        assert context["application"] == dossier.pk
        assert context["document"] == STABILITY and context["document_source"] == "recent"


@pytest.mark.django_db
def test_pinned_document_is_validated(dossier, reviewer, other_applicant):
    sequence = dossier.sequences.get()
    pinned = {"sequence_id": sequence.pk, "path": STABILITY}
    ctx = resolve_context(_request(reviewer), "/dashboard/", pinned)
    assert ctx.document_source == "pinned" and ctx.application == dossier
    assert resolve_context(_request(other_applicant), "/dashboard/", pinned).application is None
    traversal = {"sequence_id": sequence.pk, "path": "../../../config/settings/base.py"}
    assert not resolve_context(_request(reviewer), "/dashboard/", traversal).document_path
    assert resolve_context(_request(reviewer), "/dashboard/", {"sequence_id": "abc", "path": STABILITY}).document_path == ""


# --- tools -----------------------------------------------------------------------

@pytest.mark.django_db
def test_search_and_read_documents(dossier, reviewer):
    box = ToolBox(reviewer, resolve_context(_request(reviewer), f"/applications/{dossier.pk}/"))

    found = box.invoke("search_documents", {"query": "shelf life storage"})
    assert found.ok
    paths = [hit["path"] for hit in found.payload["hits"]]
    assert STABILITY in paths
    assert DocumentText.objects.filter(sequence__application=dossier).exists()

    read = box.invoke("read_document", {"path": f"0000/{STABILITY}"})
    assert read.ok and read.payload["total_pages"] == 1
    assert "24 months" in read.payload["pages"][0]["text"]

    bad = box.invoke("read_document", {"path": f"0000/{STABILITY}", "start_page": "abc"})
    assert not bad.ok and "Bad arguments" in bad.payload["error"]

    listed = box.invoke("list_documents", {"module": "m5"})
    assert [d["title"] for d in listed.payload["documents"]] == ["Bioequivalence study BE-001"]

    overview = box.invoke("get_application_overview", {})
    assert overview.payload["product_name"] == dossier.product_name


@pytest.mark.django_db
def test_tools_are_scoped_to_what_the_reader_may_see(dossier, reviewer2):
    box = ToolBox(reviewer2, resolve_context(_request(reviewer2), "/dashboard/"))
    assert not box.invoke("get_application_overview", {}).ok
    denied = box.invoke("read_document", {"application_id": dossier.pk, "path": STABILITY})
    assert not denied.ok and "not accessible" in denied.payload["error"]
    assert box.invoke("find_applications", {"query": ""}).payload["applications"] == []


# --- agent loop ------------------------------------------------------------------

class ScriptedModel:
    """Calls one tool, then answers with what it read."""

    name = "scripted"

    def __init__(self):
        self.seen = []

    def stream(self, messages, *, tools=()):
        self.seen.append(messages)
        if messages[-1].role != "tool":
            yield Finished(Completion(tool_calls=(ToolCall("c1", "read_document", {"path": STABILITY}),)))
            return
        result = json.loads(messages[-1].content)
        text = "Shelf life: " + ("24 months" if "24 months" in result["pages"][0]["text"] else "?")
        yield TextDelta(text)
        yield Finished(Completion(text=text))


@pytest.mark.django_db
def test_agent_loop_calls_tools_and_stores_the_answer(dossier, reviewer):
    ctx = resolve_context(_request(reviewer), _file_url(dossier))
    conversation = Conversation.objects.create(user=reviewer)
    model = ScriptedModel()

    events = list(agent.run(reviewer, conversation, "What is the shelf life?", ctx, "en", llm=model))

    assert [e["type"] for e in events] == ["context", "step", "text", "done"]
    assert events[-1]["message"]["content"] == "Shelf life: 24 months"
    system = model.seen[0][0].content
    assert dossier.reference_no in system and STABILITY in system
    roles = list(conversation.messages.values_list("role", flat=True))
    assert roles == ["user", "assistant"]
    assert conversation.messages.last().steps[0]["tool"] == "read_document"


@pytest.mark.django_db
def test_offline_mode_streams_passages_through_the_view(client, dossier, reviewer, settings):
    settings.ASSISTANT = {**settings.ASSISTANT, "API_KEY": ""}
    client.force_login(reviewer)
    response = client.post(
        reverse("assistant:ask"),
        {"question": "stability shelf life", "page": f"/applications/{dossier.pk}/"},
        content_type="application/json",
    )
    assert response["Content-Type"].startswith("application/x-ndjson")
    events = [json.loads(line) for line in b"".join(response.streaming_content).decode().splitlines()]
    assert events[0]["type"] == "context" and events[0]["provider"] == OfflineProvider.name
    assert events[-1]["type"] == "done"
    assert "stability-summary.pdf" in events[-1]["message"]["content"]

    session = client.get(reverse("assistant:session"), {"page": "/dashboard/"}).json()
    assert [m["role"] for m in session["messages"]] == ["user", "assistant"]

    client.post(reverse("assistant:new"))
    assert client.get(reverse("assistant:session")).json()["messages"] == []


@pytest.mark.django_db
def test_drawer_renders_on_pages(client, dossier, reviewer):
    client.force_login(reviewer)
    page = client.get(reverse("applications:sequence", args=[dossier.pk, dossier.sequences.get().pk]))
    assert b'id="assistant-config"' in page.content
    assert b"assistant-pin" in page.content  # "Ask" buttons on the dossier tree
