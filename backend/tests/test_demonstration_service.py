"""Tests for the isolated synthetic demonstration workflow; no provider network calls."""
from __future__ import annotations

from copy import deepcopy

from app.core.errors import AppError
from app.services import demonstration_service


def test_demo_creates_standard_review_package_and_exposes_only_package_events(monkeypatch):
    store: dict[tuple[str, str], dict] = {}

    def save(analysis_id, modality, value):
        store[(analysis_id, modality)] = deepcopy(value)

    def get(analysis_id, modality):
        try:
            return deepcopy(store[(analysis_id, modality)])
        except KeyError as exc:
            raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND") from exc

    # Wire the existing lifecycle services to the test-only store.
    from app.services import narrative_evidence_review_service as review_service
    monkeypatch.setattr(review_service, "save_modality_result", save)
    monkeypatch.setattr(review_service, "get_modality_result", get)
    monkeypatch.setattr(demonstration_service, "get_modality_result", get)

    generated = {
        "schema_version": "1.0.0", "analysis_id": demonstration_service.DEMONSTRATION_ANALYSIS_ID,
        "video_id": demonstration_service.DEMONSTRATION_ANALYSIS_ID, "mode": "narrative_dance",
        "status": "generated", "title": "Synthetic demonstration summary",
        "narrative": demonstration_service.DEMONSTRATION_STATEMENT, "evidence_coverage": 1.0,
        "used_event_ids": [], "limitations": [], "provider": "gemini", "model": "gemini-test-model", "message": None,
    }
    monkeypatch.setattr(demonstration_service, "generate_story_for_analysis", lambda analysis_id: {**generated, "used_event_ids": [store[(analysis_id, "performance_interpretation")]["events"][0]["event_id"]]})

    result = demonstration_service.generate_demonstration_story()
    package = store[(demonstration_service.DEMONSTRATION_ANALYSIS_ID, "performance_interpretation")]
    ledger = store[(demonstration_service.DEMONSTRATION_ANALYSIS_ID, "narrative_evidence_review")]

    assert result["demonstration"] is True
    assert result["analysis_id"] == demonstration_service.DEMONSTRATION_ANALYSIS_ID
    assert result["story"]["provider"] == "gemini"
    assert [event["statement"] for event in package["events"]] == [demonstration_service.DEMONSTRATION_STATEMENT]
    assert [event["statement"] for event in result["evidence_used"]] == [demonstration_service.DEMONSTRATION_STATEMENT]
    assert {record["status"] for record in ledger["records"]} == {"draft", "verified"}
    assert ledger["records"][1]["production_eligibility"] == {"status": "eligible"}


def test_demo_reuses_its_existing_package_without_creating_real_analysis_artifacts(monkeypatch):
    package = {
        "analysis_id": demonstration_service.DEMONSTRATION_ANALYSIS_ID,
        "video_id": demonstration_service.DEMONSTRATION_ANALYSIS_ID,
        "events": [{"event_id": "demo-event", "statement": demonstration_service.DEMONSTRATION_STATEMENT, "type": "verified_narrative_event"}],
    }
    monkeypatch.setattr(demonstration_service, "get_modality_result", lambda *_: package)
    monkeypatch.setattr(demonstration_service, "get_review", lambda _: (_ for _ in ()).throw(AssertionError("review lifecycle should not rerun")))

    assert demonstration_service.ensure_demonstration_package() is package
