"""End-to-end safety checks using an in-memory synthetic review fixture only."""
from __future__ import annotations

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.services import narrative_evidence_review_service as review_service
from app.services import narrative_generation_service, story_integration_service
from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest

SYNTHETIC_ID = "e2e-synthetic-verified-story-001"


class _Provider(LLMProvider):
    def __init__(self, name: str, response: str):
        self.name = name
        self._response = response
        self.requests: list[StructuredGenerationRequest] = []

    @property
    def model(self) -> str:
        return f"{self.name}-test-model"

    def is_available(self) -> bool:
        return True

    def generate(self, request: StructuredGenerationRequest) -> LLMResult:
        self.requests.append(request)
        return LLMResult(text=self._response, provider=self.name, model=self.model)


def _submission(status: str = "submitted") -> dict:
    return {
        "analysis_id": SYNTHETIC_ID, "video_id": SYNTHETIC_ID,
        "statement": "Synthetic test event: Performer A acknowledges Performer B.",
        "statement_type": "verified_narrative_event", "source_reference": "synthetic test source: workflow-only",
        "submitted_by": "synthetic-curator", "verification_method": "synthetic test review",
        "verification_confidence": 1.0, "span": {"start_time": 0.0, "end_time": 1.0},
        "provenance": {"type": "expert_verification", "reference": "synthetic-test-fixture-only"},
        "performance_mode": "narrative_dance", "status": status,
    }


def _review(status: str = "verified", eligible: bool = True) -> dict:
    return {"status": status, "verified_by": "synthetic-verifier", "verification_method": "synthetic test review",
            "verification_confidence": 1.0, "production_eligible": eligible, "review_reason": "Synthetic workflow fixture only."}


def _wire_memory(monkeypatch):
    store: dict[tuple[str, str], dict] = {
        # These raw artifacts prove that neither review compilation nor the
        # live provider boundary reads them.
        (SYNTHETIC_ID, "mudra"): {"raw_label": "Krishna"},
        (SYNTHETIC_ID, "bhava"): {"prediction": "Sad"},
        (SYNTHETIC_ID, "fusion"): {"raw_fusion": "temple"},
        (SYNTHETIC_ID, "audio_evidence"): {"raw_audio": "lyrics"},
    }
    def save(analysis_id, modality, value):
        store[(analysis_id, modality)] = deepcopy(value)
    def get(analysis_id, modality):
        try:
            return deepcopy(store[(analysis_id, modality)])
        except KeyError:
            raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND")
    monkeypatch.setattr(review_service, "save_modality_result", save)
    monkeypatch.setattr(review_service, "get_modality_result", get)
    monkeypatch.setattr(story_integration_service, "get_modality_result", get)
    return store


def _configure_provider(monkeypatch, provider: _Provider):
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider=provider.name))
    monkeypatch.setattr(narrative_generation_service, "get_provider", lambda name: provider if name == provider.name else pytest.fail("provider fallback attempted"))
    monkeypatch.setattr(story_integration_service, "configured_provider_metadata", lambda: (provider, provider.name, provider.model))


@pytest.mark.parametrize("status", ["draft", "submitted"])
def test_no_draft_or_submitted_evidence_can_reach_story(monkeypatch, status):
    _wire_memory(monkeypatch)
    provider = _Provider("ollama", "{}")
    _configure_provider(monkeypatch, provider)
    review_service.submit_evidence(SYNTHETIC_ID, _submission(status))
    result = story_integration_service.generate_story_for_analysis(SYNTHETIC_ID)
    assert result["status"] == "unavailable"
    assert provider.requests == []


def test_no_evidence_means_no_provider_generation(monkeypatch):
    _wire_memory(monkeypatch)
    provider = _Provider("ollama", "{}")
    _configure_provider(monkeypatch, provider)
    result = story_integration_service.generate_story_for_analysis(SYNTHETIC_ID)
    assert result["status"] == "unavailable"
    assert provider.requests == []


@pytest.mark.parametrize("review_status, eligible", [("rejected", False), ("verified", False)])
def test_rejected_or_ineligible_evidence_cannot_reach_story(monkeypatch, review_status, eligible):
    _wire_memory(monkeypatch)
    provider = _Provider("ollama", "{}")
    _configure_provider(monkeypatch, provider)
    record = review_service.submit_evidence(SYNTHETIC_ID, _submission())
    _, package = review_service.review_evidence(SYNTHETIC_ID, record["evidence_id"], _review(review_status, eligible))
    assert package is None
    result = story_integration_service.generate_story_for_analysis(SYNTHETIC_ID)
    assert result["status"] == "unavailable"
    assert provider.requests == []


@pytest.mark.parametrize("provider_name", ["ollama", "gemini", "openai"])
def test_verified_eligible_evidence_reaches_one_provider_neutral_boundary(monkeypatch, provider_name):
    store = _wire_memory(monkeypatch)
    raw = json.dumps({"title": "Synthetic verified event", "narrative": "Synthetic test event: Performer A acknowledges Performer B.", "used_event_ids": []})
    # Event ID is not known until submission; update the mock response after it is created.
    provider = _Provider(provider_name, raw)
    _configure_provider(monkeypatch, provider)
    record = review_service.submit_evidence(SYNTHETIC_ID, _submission())
    provider._response = json.dumps({"title": "Synthetic verified event", "narrative": record["statement"], "used_event_ids": [record["evidence_id"]]})
    _, package = review_service.review_evidence(SYNTHETIC_ID, record["evidence_id"], _review())
    assert package is not None
    assert [event["event_id"] for event in package["events"]] == [record["evidence_id"]]
    assert (SYNTHETIC_ID, "performance_interpretation") in store
    result = story_integration_service.generate_story_for_analysis(SYNTHETIC_ID)
    assert result["status"] == "generated"
    assert result["provider"] == provider_name
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert isinstance(request, StructuredGenerationRequest)
    assert record["statement"] in request.prompt
    serialized_evidence = request.prompt.split("EVIDENCE:\n", 1)[1]
    for forbidden in ("Krishna", "Sad", "temple", "lyrics", "raw_audio", "raw_fusion"):
        assert forbidden not in serialized_evidence


@pytest.mark.parametrize("addition", ["Krishna appears.", "A temple is shown.", "A conch is present.", "The performer feels sad.", "Lyrics describe the event.", "This causes a farewell."])
def test_unsupported_generated_content_is_rejected(monkeypatch, addition):
    _wire_memory(monkeypatch)
    provider = _Provider("ollama", "{}")
    _configure_provider(monkeypatch, provider)
    record = review_service.submit_evidence(SYNTHETIC_ID, _submission())
    provider._response = json.dumps({"title": "Synthetic verified event", "narrative": f"{record['statement']} {addition}", "used_event_ids": [record["evidence_id"]]})
    review_service.review_evidence(SYNTHETIC_ID, record["evidence_id"], _review())
    result = story_integration_service.generate_story_for_analysis(SYNTHETIC_ID)
    assert result["status"] == "blocked"
    assert result["narrative"] is None
