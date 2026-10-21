"""The workflow training guide: who can open it, what it covers, and that it follows the workflow it describes."""
import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

from apps.applications.models import Application
from apps.applications.workflow import TRANSITIONS
from apps.core import guide

S = Application.Status


def test_guide_requires_sign_in(client):
    response = client.get(reverse("core:guide"))
    assert response.status_code == 302
    assert reverse("accounts:login") in response["Location"]


@pytest.mark.parametrize("who", ["applicant", "reviewer", "hod"])
def test_every_role_sees_every_workflow(client, request, who):
    client.force_login(request.getfixturevalue(who))
    response = client.get(reverse("core:guide"))
    assert response.status_code == 200
    page = response.content.decode()
    for workflow in guide.WORKFLOWS:
        assert f'id="{workflow["key"]}"' in page
    assert reverse("core:guide") in page  # linked from the header


def test_every_status_is_explained():
    assert [status for status, _meaning, _actor in guide.STATUSES] == list(S)
    assert sorted(s for _label, statuses, _actor in guide.STAGES for s in statuses) == sorted(S)


def test_workflow_status_changes_are_real_transitions():
    """A workflow that says it moves an application from one status to another describes the state machine."""
    reachable = set(TRANSITIONS)
    # Paths through the automatic steps in between (e.g. Submitted on the way to Technical validation).
    reachable |= {(a, c) for a, b in TRANSITIONS for b2, c in TRANSITIONS if b == b2}
    for workflow in guide.WORKFLOWS:
        if workflow.get("to"):
            assert (workflow["from"], workflow["to"]) in reachable, workflow["key"]
    for from_status, to_status, _text in guide.LOOPS:
        assert (from_status, to_status) in TRANSITIONS


def test_every_video_exists_in_both_languages():
    workflow_keys = {w["key"] for w in guide.WORKFLOWS}
    for language in ("en", "ar"):
        for video in guide.videos(language):
            for path in (video["src"], video["poster"]):
                assert finders.find(path), path
            assert set(video["workflows"]) <= workflow_keys, video["key"]


def test_guide_links_workflows_to_their_videos(client, applicant):
    client.force_login(applicant)
    page = client.get(reverse("core:guide")).content.decode()
    for video in guide.VIDEOS:
        assert f'id="video-{video["key"]}"' in page
        assert f'href="#video-{video["key"]}"' in page


def test_every_role_has_workflows():
    for role, _label in guide.AUDIENCES:
        assert any(role in w["roles"] for w in guide.WORKFLOWS), role


@pytest.mark.req("URS-18")
def test_guide_in_arabic(client, hod):
    client.force_login(hod)
    client.cookies["django_language"] = "ar"
    response = client.get(reverse("core:guide"))
    page = response.content.decode()
    assert 'dir="rtl"' in page
    assert "دليل التدريب على مسارات العمل" in page
