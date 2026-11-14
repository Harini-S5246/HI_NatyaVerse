"""Lifecycle tests for human-submitted narrative evidence review."""
from copy import deepcopy

import pytest

from app.core.errors import AppError
from app.services import narrative_evidence_review_service as service

ANALYSIS_A = "11111111-1111-1111-1111-111111111111"
ANALYSIS_B = "22222222-2222-2222-2222-222222222222"


def _submission(analysis_id=ANALYSIS_A, status="submitted"):
    return {
        "analysis_id": analysis_id, "video_id": analysis_id,
        "statement": "Verified narrative event: Performer A greets Performer B.",
        "statement_type": "verified_narrative_event", "source_reference": "curator log page 4",
        "submitted_by": "curator-1", "verification_method": "direct performance review",
        "verification_confidence": 0.9, "span": {"start_time": 0.0, "end_time": 2.0},
        "provenance": {"type": "expert_verification", "reference": "review-2026-01"},
        "performance_mode": "narrative_dance", "status": status,
    }


def _review(status="verified", eligible=True):
    return {"status": status, "verified_by": "expert-1", "verification_method": "source-backed review",
            "verification_confidence": 1.0, "production_eligible": eligible, "review_reason": "Source and timestamp were checked."}


def _memory_store(monkeypatch):
    store = {}
    def save(analysis_id, modality, value):
        store[(analysis_id, modality)] = deepcopy(value)
    def get(analysis_id, modality):
        try:
            return deepcopy(store[(analysis_id, modality)])
        except KeyError:
            raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND")
    monkeypatch.setattr(service, "save_modality_result", save)
    monkeypatch.setattr(service, "get_modality_result", get)
    return store


def test_draft_is_stored_and_not_story_eligible(monkeypatch):
    _memory_store(monkeypatch)
    record = service.submit_evidence(ANALYSIS_A, _submission(status="draft"))
    assert record["status"] == "draft"
    assert record["production_eligibility"] == {"status": "ineligible"}
    assert service.get_review(ANALYSIS_A)["story_eligible"] is False
    assert "draft" in service.story_unavailability_reason(ANALYSIS_A)


def test_empty_review_has_a_distinct_story_diagnostic(monkeypatch):
    _memory_store(monkeypatch)
    assert service.story_unavailability_reason(ANALYSIS_A) == "No narrative evidence review records exist for this performance."


def test_draft_requires_explicit_submission_before_reviewer_can_decide(monkeypatch):
    _memory_store(monkeypatch)
    record = service.submit_evidence(ANALYSIS_A, _submission(status="draft"))
    with pytest.raises(service.NarrativeEvidenceReviewValidationError, match="Only submitted"):
        service.review_evidence(ANALYSIS_A, record["evidence_id"], _review())

    submitted = service.submit_for_review(ANALYSIS_A, record["evidence_id"])
    assert submitted["status"] == "submitted"
    reviewed, package = service.review_evidence(ANALYSIS_A, record["evidence_id"], _review())
    assert reviewed["status"] == "verified"
    assert package is not None and package["production_eligible"] is True


def test_submitted_preserves_provenance_without_self_verification(monkeypatch):
    _memory_store(monkeypatch)
    record = service.submit_evidence(ANALYSIS_A, _submission())
    assert record["provenance"]["reference"] == "review-2026-01"
    assert record["verified_by"] is None
    assert record["status"] == "submitted"


def test_verified_requires_attribution_and_provenance_then_builds_package(monkeypatch):
    store = _memory_store(monkeypatch)
    record = service.submit_evidence(ANALYSIS_A, _submission())
    reviewed, package = service.review_evidence(ANALYSIS_A, record["evidence_id"], _review())
    assert reviewed["verified_by"] == "expert-1"
    assert reviewed["status"] == "verified"
    assert package is not None and package["production_eligible"] is True
    assert [event["event_id"] for event in package["events"]] == [record["evidence_id"]]
    assert (ANALYSIS_A, "performance_interpretation") in store


def test_rejected_evidence_never_builds_package(monkeypatch):
    _memory_store(monkeypatch)
    record = service.submit_evidence(ANALYSIS_A, _submission())
    reviewed, package = service.review_evidence(ANALYSIS_A, record["evidence_id"], _review(status="rejected", eligible=False))
    assert reviewed["status"] == "rejected"
    assert package is None
    assert service.get_review(ANALYSIS_A)["story_eligible"] is False


def test_missing_provenance_is_rejected(monkeypatch):
    _memory_store(monkeypatch)
    payload = _submission()
    del payload["provenance"]
    with pytest.raises(service.NarrativeEvidenceReviewValidationError, match="unsupported fields"):
        service.submit_evidence(ANALYSIS_A, payload)


def test_analysis_id_isolation_prevents_cross_analysis_review(monkeypatch):
    _memory_store(monkeypatch)
    record = service.submit_evidence(ANALYSIS_A, _submission())
    with pytest.raises(service.NarrativeEvidenceReviewValidationError, match="not found"):
        service.review_evidence(ANALYSIS_B, record["evidence_id"], _review())


def test_verified_but_ineligible_evidence_cannot_enter_package(monkeypatch):
    _memory_store(monkeypatch)
    record = service.submit_evidence(ANALYSIS_A, _submission())
    reviewed, package = service.review_evidence(ANALYSIS_A, record["evidence_id"], _review(eligible=False))
    assert reviewed["status"] == "verified"
    assert reviewed["production_eligibility"] == {"status": "ineligible"}
    assert package is None
    assert "not been marked production eligible" in service.story_unavailability_reason(ANALYSIS_A)
