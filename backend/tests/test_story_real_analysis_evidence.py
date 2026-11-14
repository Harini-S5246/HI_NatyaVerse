"""Regression coverage for evidence generated from real per-analysis results."""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.routes import stories
from app.core.errors import AppError
from app.main import app
from app.services import narrative_generation_service, story_integration_service
from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest

ANALYSIS_ID = "421f2740-e6c3-493e-b08e-5931157941c4"


class _Provider(LLMProvider):
    name = "gemini"

    def __init__(self, result: LLMResult | None = None) -> None:
        self.requests: list[StructuredGenerationRequest] = []
        self.result = result

    @property
    def model(self) -> str:
        return "gemini-test"

    def is_available(self) -> bool:
        return True

    def generate(self, request: StructuredGenerationRequest) -> LLMResult:
        self.requests.append(request)
        if self.result is not None:
            return self.result
        return LLMResult(
            text=json.dumps({
                "title": "A Shifting Moment",
                "narrative": "The opening brings a lotus-like gesture into view, lending the moment a sense of freshness.\n\nAs the performance continues, another gesture gives the expression a different quality.\n\nThe later part returns to expressive hand shapes, while the expression changes once more.\n\nThe performance closes without establishing one particular story or character.",
                "used_event_ids": ["analysis-segment-0001", "analysis-segment-0002"],
            }),
            provider=self.name,
            model=self.model,
        )


def _artifacts(mudra_id: str = ANALYSIS_ID) -> dict[tuple[str, str], dict]:
    fusion = {
        "analysis_id": ANALYSIS_ID,
        "video_id": ANALYSIS_ID,
        "status": "completed",
        "summary": {"frame_count": 2},
        "timeline": [
            {
                "start_time": 0.0,
                "end_time": 1.0,
                "mudra": "Alapadmam",
                "mudra_confidence": 0.92,
                "bhava": "Joy",
                "bhava_confidence": 0.74,
            },
            {
                "start_time": 1.0,
                "end_time": 2.0,
                "mudra": "Tripataka",
                "mudra_confidence": 0.61,
                "bhava": "Reflection",
                "bhava_confidence": 0.58,
            },
        ],
    }
    mudra = {
        "analysis_id": mudra_id,
        "video_id": mudra_id,
        "status": "completed",
        "mudra_events": [
            {"mudra": "Alapadmam", "start_time": 0.0, "end_time": 1.0, "confidence": 0.92},
            {"mudra": "Tripataka", "start_time": 1.0, "end_time": 2.0, "confidence": 0.61},
        ],
        "frames": [
            {"frame_number": 10, "timestamp": 0.5},
            {"frame_number": 20, "timestamp": 1.5},
        ],
    }
    bhava = {
        "analysis_id": ANALYSIS_ID,
        "video_id": ANALYSIS_ID,
        "status": "completed",
        "bhava_events": [
            {"bhava": "Joy", "start_time": 0.0, "end_time": 1.0, "confidence": 0.74},
            {"bhava": "Reflection", "start_time": 1.0, "end_time": 2.0, "confidence": 0.58},
        ],
        "frames": [
            {"frame_number": 10, "timestamp": 0.5},
            {"frame_number": 20, "timestamp": 1.5},
        ],
    }
    return {
        (ANALYSIS_ID, "fusion"): fusion,
        (ANALYSIS_ID, "mudra"): mudra,
        (ANALYSIS_ID, "bhava"): bhava,
    }


def _wire(monkeypatch, provider: _Provider, artifacts: dict[tuple[str, str], dict]):
    def get(analysis_id: str, modality: str) -> dict:
        try:
            return deepcopy(artifacts[(analysis_id, modality)])
        except KeyError as exc:
            raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND") from exc

    def save(analysis_id: str, modality: str, value: dict) -> None:
        artifacts[(analysis_id, modality)] = deepcopy(value)

    monkeypatch.setattr(story_integration_service, "get_modality_result", get)
    monkeypatch.setattr(story_integration_service, "save_modality_result", save)
    monkeypatch.setattr(story_integration_service, "configured_provider_metadata", lambda: (provider, "gemini", provider.model))
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider="gemini", app_env="production"))
    monkeypatch.setattr(narrative_generation_service, "get_provider", lambda name: provider)


def test_real_video_analysis_reaches_gemini_as_compact_chronological_evidence(monkeypatch):
    provider = _Provider()
    artifacts = _artifacts()
    _wire(monkeypatch, provider, artifacts)

    response = story_integration_service.generate_story_for_analysis(ANALYSIS_ID)

    assert response["status"] == "generated"
    assert response["analysis_id"] == response["video_id"] == ANALYSIS_ID
    assert response["mode"] == "evidence_based"
    assert response["used_event_ids"] == ["analysis-segment-0001", "analysis-segment-0002"]
    assert len(provider.requests) == 1
    prompt = provider.requests[0].prompt
    assert ANALYSIS_ID not in prompt
    assert "Full-blown lotus" in prompt
    assert '"chronological_beats"' in prompt
    assert "8-12 natural paragraphs when there are at least 8 chronological beats" in prompt
    assert "Use all meaningful expressive changes in the input" in prompt
    assert "Give the story a specific, natural title naming a supported emotional turn" in prompt
    assert "Keep technical terms, raw model labels, timestamps, frame numbers, and event identifiers out of the title and narrative" in prompt
    assert "return every supplied event_id in chronological order only in used_event_ids" in prompt.lower()
    assert "Translate generic predicted emotion labels into cautious human-readable expressive qualities" in prompt
    assert "claim what the dancer literally feels" in prompt.lower()
    for unresolved in ("{video_id}", "{timeline_data}", "{mudra_evidence}", "{bhava_evidence}"):
        assert unresolved not in prompt
    assert "raw_timeline" not in prompt


def test_evidence_ready_response_reports_package_coverage_separately_from_story_coverage(monkeypatch):
    provider = _Provider()
    artifacts = _artifacts()
    _wire(monkeypatch, provider, artifacts)
    monkeypatch.setattr(
        story_integration_service,
        "story_unavailability_reason",
        lambda _analysis_id: "No reviewed narrative record is needed for an evidence-based interpretation.",
    )

    response = story_integration_service.get_existing_story_for_analysis(ANALYSIS_ID)

    assert response["status"] == "unavailable"
    assert response["evidence_coverage"] == 0.0
    assert response["package_evidence_coverage"] == 1.0
    assert provider.requests == []


def test_story_post_endpoint_returns_generated_real_analysis_story(monkeypatch):
    provider = _Provider()
    artifacts = _artifacts()
    _wire(monkeypatch, provider, artifacts)
    monkeypatch.setattr(stories, "get_uploaded_video_path", lambda video_id: video_id)

    response = TestClient(app).post(f"/api/videos/{ANALYSIS_ID}/story", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "generated"
    assert body["video_id"] == ANALYSIS_ID
    assert body["mode"] == "evidence_based"
    assert len(provider.requests) == 1


def test_story_post_endpoint_preserves_gemini_rate_limit_metadata(monkeypatch):
    provider = _Provider(LLMResult(
        text="",
        provider="gemini",
        model="gemini-test",
        error="ResourceExhausted: quota exceeded",
        error_code="GEMINI_RATE_LIMITED",
        retry_after_seconds=54406,
    ))
    _wire(monkeypatch, provider, _artifacts())
    monkeypatch.setattr(stories, "get_uploaded_video_path", lambda video_id: video_id)

    response = TestClient(app).post(f"/api/videos/{ANALYSIS_ID}/story", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "retryable"
    assert body["error_code"] == "GEMINI_RATE_LIMITED"
    assert body["retry_after_seconds"] == 54406
    assert body["package_evidence_coverage"] == 1.0


def test_story_post_endpoint_rejects_unknown_upload_before_evidence_lookup(monkeypatch):
    def unknown_upload(_video_id: str) -> None:
        raise AppError("Uploaded video was not found.", 404, "VIDEO_NOT_FOUND")

    monkeypatch.setattr(stories, "get_uploaded_video_path", unknown_upload)
    monkeypatch.setattr(
        stories,
        "generate_story_for_analysis",
        lambda _video_id: pytest.fail("story generation must not run for an unknown upload"),
    )

    response = TestClient(app).post(f"/api/videos/{ANALYSIS_ID}/story", json={})

    assert response.status_code == 404
    assert response.json()["code"] == "VIDEO_NOT_FOUND"


def test_model_artifact_from_another_video_is_rejected_without_provider_call(monkeypatch):
    provider = _Provider()
    artifacts = _artifacts(mudra_id="another-analysis")
    _wire(monkeypatch, provider, artifacts)

    with pytest.raises(AppError, match="different analysis"):
        story_integration_service.generate_story_for_analysis(ANALYSIS_ID)

    assert provider.requests == []


def test_non_upload_identifier_never_reads_raw_modality_fallbacks(monkeypatch):
    provider = _Provider()
    requested: list[str] = []

    def get(_analysis_id: str, modality: str) -> dict:
        requested.append(modality)
        raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND")

    monkeypatch.setattr(story_integration_service, "get_modality_result", get)
    monkeypatch.setattr(story_integration_service, "configured_provider_metadata", lambda: (provider, "gemini", provider.model))
    response = story_integration_service.generate_story_for_analysis("phase-9-2-synthetic-demonstration-001")

    assert response["status"] == "unavailable"
    assert requested == ["performance_interpretation"]
    assert provider.requests == []


def test_unresolved_placeholder_is_blocked_before_provider_call(monkeypatch):
    provider = _Provider()
    artifacts = _artifacts()
    fusion = artifacts[(ANALYSIS_ID, "fusion")]
    fusion["timeline"][0]["mudra"] = "{mudra_evidence}"
    artifacts[(ANALYSIS_ID, "mudra")]["mudra_events"][0]["mudra"] = "{mudra_evidence}"
    _wire(monkeypatch, provider, artifacts)

    response = story_integration_service.generate_story_for_analysis(ANALYSIS_ID)

    assert response["status"] == "blocked"
    assert "placeholder" in response["message"]
    assert provider.requests == []


def test_gemini_timeout_is_reported_as_retryable_not_as_a_generic_failure(monkeypatch):
    provider = _Provider(LLMResult(
        text="",
        provider="gemini",
        model="gemini-test",
        error="TimeoutError: request exceeded timeout",
        error_code="GEMINI_TIMEOUT",
    ))
    artifacts = _artifacts()
    _wire(monkeypatch, provider, artifacts)

    response = story_integration_service.generate_story_for_analysis(ANALYSIS_ID)

    assert response["status"] == "retryable"
    assert response["error_code"] == "GEMINI_TIMEOUT"
    assert "timed out" in response["message"]
    assert len(provider.requests) == 1
