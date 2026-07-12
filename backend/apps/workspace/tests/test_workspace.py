"""Phase 9 tests: AI suggestions + approval workflow, kanban, hierarchy, APIs."""
from __future__ import annotations

import io
import wave

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.tests.factories import UserFactory
from apps.jobs.services import execute_job
from apps.meetings.services.uploads import create_upload
from apps.workspace.enums import ApprovalStatus, OPEN_SUGGESTION_STATUSES, SuggestionType, TaskStatus
from apps.workspace.models import AISuggestion, Project, Risk, Task

pytestmark = pytest.mark.django_db


def _wav(seconds=40, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * rate * seconds)
    return buf.getvalue()


def _run(user):
    f = SimpleUploadedFile("m.wav", _wav(), content_type="audio/wav")
    meeting = create_upload(owner=user, uploaded_file=f, title="Team Sync").meeting
    job = meeting.meeting_jobs.order_by("-created_at").first().background_job
    execute_job(str(job.id))     # triggers AI analysis → subscriber → suggestions
    meeting.refresh_from_db()
    return meeting


@pytest.fixture
def meeting(user):
    return _run(user)


# --- suggestion engine (human-in-the-loop) ---------------------------------
def test_ai_creates_pending_suggestions_not_live_records(meeting, user):
    suggestions = AISuggestion.objects.filter(meeting=meeting)
    assert suggestions.count() >= 4                     # tasks, decision, risk, issue, follow-up
    assert all(s.status in OPEN_SUGGESTION_STATUSES for s in suggestions)  # pending / needs_review
    # Nothing materialized as a live Task yet — user is in control.
    assert Task.objects.filter(meeting=meeting).count() == 0
    # Each suggestion has a confidence score + reason (explainability).
    s = suggestions.first()
    assert 0 < s.confidence_score <= 100
    assert s.confidence in {"high", "medium", "low"}
    assert s.reason


def test_suggestion_types_cover_all(meeting):
    types = set(AISuggestion.objects.filter(meeting=meeting).values_list("suggestion_type", flat=True))
    assert {SuggestionType.TASK, SuggestionType.DECISION, SuggestionType.RISK} <= types


def test_approve_creates_real_task_with_evidence(meeting, user):
    from apps.workspace.services.materialize import approve_suggestion

    sug = AISuggestion.objects.filter(meeting=meeting, suggestion_type=SuggestionType.TASK).first()
    task = approve_suggestion(sug, actor=user)
    assert isinstance(task, Task)
    assert task.created_by_ai is True
    assert task.suggestion_id == sug.id
    assert task.confidence == sug.confidence            # explainability carried over
    sug.refresh_from_db()
    assert sug.status == ApprovalStatus.CONVERTED
    assert sug.approved_by == user
    assert sug.converted_to_id == task.id               # traceability link
    assert sug.original_json                            # immutable original preserved


def test_reject_creates_nothing(meeting, user):
    from apps.workspace.services.materialize import reject_suggestion

    sug = AISuggestion.objects.filter(meeting=meeting, suggestion_type=SuggestionType.RISK).first()
    reject_suggestion(sug, actor=user)
    sug.refresh_from_db()
    assert sug.status == ApprovalStatus.REJECTED
    assert Risk.objects.filter(meeting=meeting).count() == 0


def test_auto_approve_mode(user, settings):
    settings.AI_SUGGESTION_MODE = "always"
    m = _run(user)
    # In "always" mode suggestions are auto-approved → live records exist.
    assert AISuggestion.objects.filter(meeting=m, status=ApprovalStatus.CONVERTED).exists()
    assert Task.objects.filter(meeting=m).exists()


# --- kanban -----------------------------------------------------------------
def test_kanban_move_and_board(auth_client, user):
    task = Task.objects.create(owner=user, title="Manual task")
    resp = auth_client.post(f"/api/workspace/tasks/{task.id}/move/",
                            {"status": TaskStatus.IN_PROGRESS, "order": 1}, format="json")
    assert resp.status_code == 200
    task.refresh_from_db()
    assert task.status == TaskStatus.IN_PROGRESS

    board = auth_client.get("/api/workspace/tasks/board/")
    assert board.status_code == 200
    cols = {c["status"]: c for c in board.data["data"]}
    assert TaskStatus.IN_PROGRESS in cols


# --- hierarchy --------------------------------------------------------------
def test_workspace_project_hierarchy(auth_client, user):
    ws = auth_client.post("/api/workspace/workspaces/", {"name": "Acme Corp"}, format="json")
    assert ws.status_code == 201
    proj = auth_client.post("/api/workspace/projects/",
                            {"name": "ERP Upgrade", "workspace": ws.data["id"]}, format="json")
    assert proj.status_code == 201
    assert Project.objects.get(id=proj.data["id"]).workspace_id is not None


# --- API: suggestions queue -------------------------------------------------
def test_suggestions_api_approve(auth_client, user, meeting):
    q = auth_client.get(f"/api/workspace/suggestions/?meeting={meeting.id}")
    assert q.status_code == 200
    assert q.data["count"] >= 4
    sid = q.data["results"][0]["id"]
    approve = auth_client.post(f"/api/workspace/suggestions/{sid}/approve/", {}, format="json")
    assert approve.status_code == 200
    assert approve.data["data"]["suggestion"]["status"] == "converted"


def test_suggestions_cannot_be_created_manually(auth_client):
    resp = auth_client.post("/api/workspace/suggestions/", {"title": "x"}, format="json")
    assert resp.status_code == 405


# --- reports / analytics / search / timeline / permissions ------------------
def test_generate_report(auth_client, user, meeting):
    resp = auth_client.post("/api/workspace/reports/generate/",
                            {"report_type": "executive", "meeting": str(meeting.id)}, format="json")
    assert resp.status_code == 201
    assert resp.data["data"]["content"]
    assert resp.data["data"]["version"] == 1
    # Regenerate → new version, previous preserved.
    again = auth_client.post("/api/workspace/reports/generate/",
                             {"report_type": "executive", "meeting": str(meeting.id)}, format="json")
    assert again.data["data"]["version"] == 2


def test_analytics_and_dashboard(auth_client, user):
    Task.objects.create(owner=user, title="A", status=TaskStatus.COMPLETED)
    Task.objects.create(owner=user, title="B", status=TaskStatus.TODO)
    a = auth_client.get("/api/workspace/analytics/")
    assert a.status_code == 200
    assert a.data["data"]["total_tasks"] == 2
    assert a.data["data"]["task_completion_rate"] == 50.0
    assert auth_client.get("/api/workspace/dashboard/").status_code == 200


def test_search_keyword_and_semantic(auth_client, user):
    Task.objects.create(owner=user, title="Fix authentication bug")
    kw = auth_client.get("/api/workspace/search/?q=authentication")
    assert kw.status_code == 200
    assert len(kw.data["data"]["tasks"]) == 1
    sem = auth_client.get("/api/workspace/search/?q=login%20security&semantic=1")
    assert sem.status_code == 200
    assert "results" in sem.data["data"]


def test_timeline(auth_client, user, meeting):
    resp = auth_client.get(f"/api/workspace/timeline/{meeting.id}/")
    assert resp.status_code == 200
    assert "topics" in resp.data["data"]


# --- Workspace Readiness ---------------------------------------------------
def test_edit_before_approve_keeps_original_and_edited(meeting, user):
    from apps.workspace.services.materialize import approve_suggestion

    sug = AISuggestion.objects.filter(meeting=meeting, suggestion_type=SuggestionType.TASK).first()
    original = sug.original_json
    task = approve_suggestion(sug, actor=user, edited={"task": "Corrected task title"},
                              reviewer_notes="Fixed the wording")
    assert task.title == "Corrected task title"
    sug.refresh_from_db()
    assert sug.original_json == original            # immutable
    assert sug.edited_json.get("task") == "Corrected task title"
    assert sug.reviewer_notes == "Fixed the wording"


def test_bulk_approve(auth_client, user, meeting):
    ids = list(AISuggestion.objects.filter(meeting=meeting).values_list("id", flat=True))
    resp = auth_client.post("/api/workspace/suggestions/bulk/",
                            {"ids": [str(i) for i in ids], "action": "approve"}, format="json")
    assert resp.status_code == 200
    assert resp.data["data"]["count"] == len(ids)
    assert AISuggestion.objects.filter(meeting=meeting, status="converted").count() == len(ids)


def test_duplicate_detection_and_merge(user):
    from apps.workspace.services.activity import find_duplicate_tasks
    from apps.workspace.services.materialize import approve_suggestion
    from apps.workspace.models import AISuggestion as S

    Task.objects.create(owner=user, title="Implement authentication")
    dupes = find_duplicate_tasks(user, "Implement authentication")
    assert len(dupes) >= 1
    # Approving a duplicate suggestion with on_duplicate=merge links instead of creating.
    sug = S.objects.create(owner=user, meeting=None if False else _meeting_for(user),
                           suggestion_type=SuggestionType.TASK, title="Implement authentication",
                           generated_json={"task": "Implement authentication"})
    before = Task.objects.count()
    approve_suggestion(sug, actor=user, on_duplicate="merge")
    assert Task.objects.count() == before          # merged, not duplicated


def _meeting_for(user):
    from apps.meetings.models import Meeting
    return Meeting.objects.create(owner=user, title="dup-meeting")


def test_task_comments_and_activity(auth_client, user):
    task = Task.objects.create(owner=user, title="Manual task")
    c = auth_client.post(f"/api/workspace/tasks/{task.id}/comments/", {"body": "Working on it"}, format="json")
    assert c.status_code == 201
    listed = auth_client.get(f"/api/workspace/tasks/{task.id}/comments/")
    assert len(listed.data["data"]) == 1
    act = auth_client.get(f"/api/workspace/tasks/{task.id}/activity/")
    assert act.status_code == 200
    assert any(a["verb"] == "commented" for a in act.data["data"])


def test_task_related(auth_client, user, meeting):
    from apps.workspace.services.materialize import approve_suggestion
    sug = AISuggestion.objects.filter(meeting=meeting, suggestion_type=SuggestionType.TASK).first()
    task = approve_suggestion(sug, actor=user)
    resp = auth_client.get(f"/api/workspace/tasks/{task.id}/related/")
    assert resp.status_code == 200
    assert resp.data["data"]["source_meeting"]["id"] == str(meeting.id)


def test_rich_task_fields(auth_client, user):
    resp = auth_client.post("/api/workspace/tasks/", {
        "title": "Rich task", "labels": ["backend", "urgent"], "watchers": ["john"],
        "checklist": [{"id": "1", "text": "Step 1", "done": False}],
    }, format="json")
    assert resp.status_code == 201
    assert resp.data["labels"] == ["backend", "urgent"]
    assert resp.data["checklist"][0]["text"] == "Step 1"


def test_manual_crud_without_ai(auth_client, user):
    for path, payload in [
        ("tasks", {"title": "manual"}),
        ("risks", {"risk": "manual risk"}),
        ("decisions", {"decision": "manual decision"}),
        ("issues", {"title": "manual issue"}),
    ]:
        resp = auth_client.post(f"/api/workspace/{path}/", payload, format="json")
        assert resp.status_code == 201, (path, resp.data)


def test_suggestion_stats(auth_client, user, meeting):
    resp = auth_client.get("/api/workspace/suggestions/stats/")
    assert resp.status_code == 200
    assert "average_confidence" in resp.data["data"]
    assert resp.data["data"]["pending"] >= 1


def test_needs_review_for_low_confidence(user, monkeypatch):
    # Force low confidence grounding → needs_review status.
    monkeypatch.setattr("apps.workspace.services.materialize._ground", lambda *a, **k: (None, 40))
    m = _run(user)
    assert AISuggestion.objects.filter(meeting=m, status="needs_review").exists()


def test_owner_scoping(auth_client, api_client, user):
    task = Task.objects.create(owner=user, title="Mine")
    other = UserFactory()
    login = api_client.post("/api/auth/login/", {"email": other.email, "password": "SuperSecret123"}, format="json")
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert api_client.get(f"/api/workspace/tasks/{task.id}/").status_code in (403, 404)
    assert api_client.get("/api/workspace/tasks/").data["count"] == 0
