"""Regression matrix for a non-demo performance's evidence lifecycle."""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

from app.core.errors import AppError
from app.services import narrative_evidence_review_service as review_service
from app.services import narrative_generation_service, story_integration_service
from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest


# Deliberately a normal uploaded-performance UUID, never the demo fixture ID.
REAL_ANALYSIS_ID = "421f2740-e6c3-493e-b08e-5931157941c4"


class _GeminiProbe(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        self.requests: list[StructuredGenerationRequest] = []
        self.response = "{}"

    @property
    def model(self) -> str:
        return "gemini-3.6-flash"

    def is_available(self) -> bool:
        return True

    def generate(self, request: StructuredGenerationRequest) -> LLMResult:
        self.requests.append(request)
        return LLMResult(text=self.response, provider=self.name, model=self.model)


def _submission(status: str) -> dict:
    return {
        "analysis_id": REAL_ANALYSIS_ID, "video_id": REAL_ANALYSIS_ID,
        "statement": "Curator-verified performance event for regression testing.",
        "statement_type": "verified_narrative_event", "source_reference": "regression curator source",
        "submitted_by": "regression-curator", "verification_method": "source-backed review",
        "verification_confidence": 1.0, "span": {"start_time": 0.0, "end_time": 1.0},
        "provenance": {"type": "expert_verification", "reference": "regression-source"},
        "performance_mode": "narrative_dance", "status": status,
    }


def _decision(eligible: bool) -> dict:
    return {
        "status": "verified", "verified_by": "regression-reviewer",
        "verification_method": "source-backed review", "verification_confidence": 1.0,
        "production_eligible": eligible, "review_reason": "Regression lifecycle review.",
    }


def _wire(monkeypatch):
    store: dict[tuple[str, str], dict] = {}

    def save(analysis_id, modality, value):
        store[(analysis_id, modality)] = deepcopy(value)

    def get(analysis_id, modality):
        try:
            return deepcopy(store[(analysis_id, modality)])
        except KeyError as exc:
            raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND") from exc

    probe = _GeminiProbe()
    monkeypatch.setattr(review_service, "save_modality_result", save)
    monkeypatch.setattr(review_service, "get_modality_result", get)
    monkeypatch.setattr(story_integration_service, "get_modality_result", get)
    monkeypatch.setattr(story_integration_service, "configured_provider_metadata", lambda: (probe, probe.name, probe.model))
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider="gemini", app_env="production"))
    monkeypatch.setattr(narrative_generation_service, "get_provider", lambda name: probe if name == "gemini" else None)
    return store, probe


def test_real_performance_evidence_lifecycle_only_invokes_gemini_after_eligibility(monkeypatch):
    store, probe = _wire(monkeypatch)

    # No evidence -> unavailable.
    assert story_integration_service.generate_story_for_analysis(REAL_ANALYSIS_ID)["status"] == "unavailable"

    # Draft -> unavailable.
    draft = review_service.submit_evidence(REAL_ANALYSIS_ID, _submission("draft"))
    assert story_integration_service.generate_story_for_analysis(REAL_ANALYSIS_ID)["status"] == "unavailable"
    assert probe.requests == []
    review_service.submit_for_review(REAL_ANALYSIS_ID, draft["evidence_id"])

    # Submitted but unverified -> unavailable.
    assert story_integration_service.generate_story_for_analysis(REAL_ANALYSIS_ID)["status"] == "unavailable"
    assert probe.requests == []

    # Verified but ineligible -> unavailable and no package.
    reviewed, package = review_service.review_evidence(REAL_ANALYSIS_ID, draft["evidence_id"], _decision(False))
    assert reviewed["production_eligibility"] == {"status": "ineligible"}
    assert package is None
    assert (REAL_ANALYSIS_ID, "performance_interpretation") not in store
    assert story_integration_service.generate_story_for_analysis(REAL_ANALYSIS_ID)["status"] == "unavailable"
    assert probe.requests == []

    # A different, verified and eligible real-performance record compiles the
    # package under the same analysis ID and is the only point Gemini is called.
    eligible = review_service.submit_evidence(REAL_ANALYSIS_ID, _submission("submitted"))
    probe.response = json.dumps({
        "title": "Verified performance event",
        "narrative": eligible["statement"],
        "used_event_ids": [eligible["evidence_id"]],
    })
    reviewed, package = review_service.review_evidence(REAL_ANALYSIS_ID, eligible["evidence_id"], _decision(True))
    assert reviewed["production_eligibility"] == {"status": "eligible"}
    assert package is not None
    assert package["analysis_id"] == package["video_id"] == REAL_ANALYSIS_ID
    assert [event["event_id"] for event in package["events"]] == [eligible["evidence_id"]]
    assert store[(REAL_ANALYSIS_ID, "performance_interpretation")]["analysis_id"] == REAL_ANALYSIS_ID

    story = story_integration_service.generate_story_for_analysis(REAL_ANALYSIS_ID)
    assert story["status"] == "generated"
    assert story["provider"] == "gemini"
    assert story["model"] == "gemini-3.6-flash"
    assert story["evidence_coverage"] == 1.0
    assert len(probe.requests) == 1
