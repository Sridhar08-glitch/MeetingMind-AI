"""Shared fixtures for agent tests."""
from __future__ import annotations

import pytest

from apps.knowledge.services import executive as exe
from apps.knowledge.services.consensus import ConsensusService
from apps.knowledge.services.index import KnowledgeIndexService
from apps.meetings.models import Meeting, TranscriptSegment
from apps.workspace.models import Decision, Project, Risk, Task


@pytest.fixture
def seeded(user):
    """A small but complete workspace: project, meetings (indexed), decisions,
    tasks, risks, consensus + a materialized executive snapshot."""
    proj = Project.objects.create(owner=user, name="Platform")
    m1 = Meeting.objects.create(owner=user, title="Auth review", description="d", project=proj)
    TranscriptSegment.objects.create(meeting=m1, index=0, start_time=0.0, end_time=5.0,
                                     speaker="Alice", text="We will use OAuth2 with OIDC for authentication.")
    Decision.objects.create(owner=user, meeting=m1, project=proj, decision="Adopt OAuth2 for authentication",
                            confidence_score=88)
    Task.objects.create(owner=user, meeting=m1, project=proj, title="Migrate auth", status="blocked", confidence_score=70)
    Risk.objects.create(owner=user, meeting=m1, project=proj, risk="Auth downtime for customer", severity="high",
                        status="open", confidence_score=65)
    KnowledgeIndexService().index_meeting(m1)

    m2 = Meeting.objects.create(owner=user, title="Auth follow-up", description="d", project=proj)
    TranscriptSegment.objects.create(meeting=m2, index=0, start_time=0.0, end_time=5.0,
                                     speaker="Bob", text="Confirmed OAuth2 for authentication after review.")
    Decision.objects.create(owner=user, meeting=m2, project=proj, decision="Keep OAuth2 for authentication",
                            confidence_score=90)
    KnowledgeIndexService().index_meeting(m2)

    ConsensusService().compute(user, persist=True)
    exe.materialize(user, actor=user)
    return proj
