"""Route tests for explicitly submitted narrative evidence only."""
import pytest

from app.api.routes import narrative_evidence as route
from app.core.errors import AppError
from app.services import verified_narrative_evidence_service

from test_verified_narrative_evidence_service import ANALYSIS_ID, _payload


def test_route_persists_isolated_evidence_and_matching_package(monkeypatch):
    saved = []
    monkeypatch.setattr(route, "get_uploaded_video_path", lambda value: value)
    monkeypatch.setattr(verified_narrative_evidence_service, "save_modality_result", lambda *args: saved.append(args))
    monkeypatch.setattr(route, "save_modality_result", lambda *args: saved.append(args))
    result = route.create_narrative_evidence(ANALYSIS_ID, _payload())
    assert result["narrative_evidence"]["analysis_id"] == ANALYSIS_ID
    assert result["performance_interpretation"]["video_id"] == ANALYSIS_ID
    assert [call[1] for call in saved] == ["narrative_evidence", "performance_interpretation"]


def test_route_rejects_mismatched_payload_id(monkeypatch):
    monkeypatch.setattr(route, "get_uploaded_video_path", lambda value: value)
    with pytest.raises(AppError) as error:
        route.create_narrative_evidence(ANALYSIS_ID, _payload("22222222-2222-2222-2222-222222222222"))
    assert error.value.code == "INVALID_NARRATIVE_EVIDENCE"


def test_route_exposes_explicit_draft_submission_transition(monkeypatch):
    monkeypatch.setattr(route, "get_uploaded_video_path", lambda value: value)
    captured = {}
    monkeypatch.setattr(route, "submit_for_review", lambda analysis_id, evidence_id: captured.update({"analysis_id": analysis_id, "evidence_id": evidence_id}) or {"status": "submitted"})
    result = route.submit_narrative_evidence_for_review(ANALYSIS_ID, "evidence-1")
    assert result["narrative_evidence"]["status"] == "submitted"
    assert result["story_eligible"] is False
    assert captured == {"analysis_id": ANALYSIS_ID, "evidence_id": "evidence-1"}
