"""Tests for the Story route's Phase 6 integration boundary."""
import json
from pathlib import Path

import pytest

from app.core.errors import AppError
from app.services import story_integration_service
from app.services.performance_interpretation_service import build_performance_interpretation


FIXTURE = Path(__file__).parents[1] / "app" / "data" / "knowledge" / "narrative" / "narrative_evidence.example.json"


def _production_package(analysis_id: str) -> dict:
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record["source_type"] = "expert_annotation"
    record["production_eligible"] = True
    return build_performance_interpretation(analysis_id, record)


def test_missing_production_package_is_unavailable_for_the_requested_id(monkeypatch):
    analysis_id = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setattr(
        story_integration_service,
        "get_modality_result",
        lambda *_: (_ for _ in ()).throw(AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND")),
    )
    result = story_integration_service.generate_story_for_analysis(analysis_id)
    assert result["status"] == "unavailable"
    assert result["analysis_id"] == result["video_id"] == analysis_id
    assert result["narrative"] is None


def test_current_alarippu_analysis_is_unavailable_without_an_eligible_package(monkeypatch):
    analysis_id = "827dcd2e-33b1-4826-8369-3730724e329a"
    monkeypatch.setattr(
        story_integration_service,
        "get_modality_result",
        lambda *_: (_ for _ in ()).throw(AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND")),
    )
    result = story_integration_service.generate_story_for_analysis(analysis_id)
    assert result["status"] == "unavailable"
    assert result["analysis_id"] == result["video_id"] == analysis_id
    assert result["narrative"] is None


def test_verified_package_is_sent_unchanged_to_phase_six(monkeypatch):
    analysis_id = "22222222-2222-2222-2222-222222222222"
    package = _production_package(analysis_id)
    captured = {}
    monkeypatch.setattr(story_integration_service, "get_modality_result", lambda *_: package)

    def generate(received, *, language):
        captured["package"] = received
        captured["language"] = language
        return {
            "schema_version": "1.0.0", "analysis_id": analysis_id, "video_id": analysis_id,
            "mode": "narrative_dance", "status": "generated", "language": language, "presentation_version": story_integration_service.STORY_PRESENTATION_VERSION, "title": "Verified sequence",
            "narrative": "Verified narrative event: Performer A greets Performer B.", "evidence_coverage": 1.0,
            "used_event_ids": ["synthetic-event-001"], "limitations": package["limitations"],
            "provider": "ollama", "model": "qwen2.5-coder:3b", "message": None,
        }

    monkeypatch.setattr(story_integration_service, "generate_narrative", generate)
    result = story_integration_service.generate_story_for_analysis(analysis_id)
    assert captured["package"] is package
    assert captured["language"] == "en"
    assert result["narrative"] == "Verified narrative event: Performer A greets Performer B."


def test_a_package_for_a_different_analysis_id_is_rejected(monkeypatch):
    requested_id = "33333333-3333-3333-3333-333333333333"
    monkeypatch.setattr(story_integration_service, "get_modality_result", lambda *_: _production_package("44444444-4444-4444-4444-444444444444"))
    with pytest.raises(AppError, match="does not belong"):
        story_integration_service.generate_story_for_analysis(requested_id)
