"""Completed-analysis summaries may create review-only AI-assisted drafts."""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

from app.core.errors import AppError
from app.services import narrative_evidence_candidate_service as candidates
from app.services import narrative_evidence_review_service as review
from app.services import narrative_generation_service, story_integration_service
from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest

ANALYSIS_ID = "421f2740-e6c3-493e-b08e-5931157941c4"


class _GeminiProbe(LLMProvider):
    name = "gemini"

    def __init__(self):
        self.requests: list[StructuredGenerationRequest] = []
        self.response = "{}"

    @property
    def model(self):
        return "gemini-3.6-flash"

    def is_available(self):
        return True

    def generate(self, request):
        self.requests.append(request)
        return LLMResult(text=self.response, provider=self.name, model=self.model)


def _result():
    return {
        "analysis_id": ANALYSIS_ID, "video_id": ANALYSIS_ID, "status": "completed",
        "summary": {"dominant_mudra": "Anjali", "dominant_bhava": "Neutral", "mudra_event_count": 2, "bhava_event_count": 2, "frame_count": 12},
    }


def test_completed_summary_candidate_requires_edit_review_and_eligibility_before_gemini(monkeypatch):
    store: dict[tuple[str, str], dict] = {}
    probe = _GeminiProbe()

    def save(analysis_id, modality, value):
        store[(analysis_id, modality)] = deepcopy(value)

    def get(analysis_id, modality):
        try:
            return deepcopy(store[(analysis_id, modality)])
        except KeyError as exc:
            raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND") from exc

    monkeypatch.setattr(candidates, "get_result", lambda _: _result())
    monkeypatch.setattr(review, "save_modality_result", save)
    monkeypatch.setattr(review, "get_modality_result", get)
    monkeypatch.setattr(story_integration_service, "get_modality_result", get)
    monkeypatch.setattr(story_integration_service, "configured_provider_metadata", lambda: (probe, probe.name, probe.model))
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider="gemini", app_env="production"))
    monkeypatch.setattr(narrative_generation_service, "get_provider", lambda name: probe)

    candidate = candidates.prepare_candidates(ANALYSIS_ID)[0]
    assert candidate["status"] == "draft"
    assert candidate["candidate_origin"] == "ai_assisted"
    assert candidate["production_eligibility"] == {"status": "ineligible"}
    assert candidate["performance_mode"] == "unknown"
    assert story_integration_service.generate_story_for_analysis(ANALYSIS_ID)["status"] == "unavailable"
    assert probe.requests == []

    edited = review.update_draft_evidence(ANALYSIS_ID, candidate["evidence_id"], {
        "statement": "Human-reviewed statement based on the completed analysis summary.",
        "performance_mode": "narrative_dance",
    })
    review.submit_for_review(ANALYSIS_ID, edited["evidence_id"])
    reviewed, package = review.review_evidence(ANALYSIS_ID, edited["evidence_id"], {
        "status": "verified", "verified_by": "expert-reviewer", "verification_method": "source-backed human review",
        "verification_confidence": 1.0, "production_eligible": True, "review_reason": "Reviewed before production use.",
    })
    assert reviewed["status"] == "verified"
    assert package is not None and package["analysis_id"] == ANALYSIS_ID
    probe.response = json.dumps({"title": "Reviewed event", "narrative": edited["statement"], "used_event_ids": [edited["evidence_id"]]})
    story = story_integration_service.generate_story_for_analysis(ANALYSIS_ID)
    assert story["status"] == "generated"
    assert story["evidence_coverage"] == 1.0
    assert len(probe.requests) == 1
