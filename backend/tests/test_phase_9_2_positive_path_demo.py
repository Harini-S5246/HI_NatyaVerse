"""Phase 9.2 synthetic demonstration of the validated positive Story path.

This module uses an in-memory modality store and deterministic providers.  It
never creates an upload, a model result, or narrative evidence for a real
performance.  The fixture is intentionally labelled synthetic throughout.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import settings
from app.core.errors import AppError
from app.services import narrative_evidence_review_service as review_service
from app.services import narrative_generation_service, story_integration_service
from app.services.llm.base import LLMProvider, LLMResult, StructuredGenerationRequest
from app.services.performance_interpretation_service import validate_performance_interpretation


SYNTHETIC_DEMONSTRATION_ID = "phase-9-2-synthetic-demonstration-001"
REAL_ALARIPPU_ID = "827dcd2e-33b1-4826-8369-3730724e329a"
DEMONSTRATION_STATEMENT = "Synthetic demonstration record: Event one is explicitly verified."


class DeterministicDemoProvider(LLMProvider):
    """A no-network provider that records the common structured request."""

    def __init__(self, name: str, response: str | None = None, error: str | None = None):
        self.name = name
        self._response = response
        self._error = error
        self.requests: list[StructuredGenerationRequest] = []

    @property
    def model(self) -> str:
        return f"{self.name}-synthetic-demo-model"

    def is_available(self) -> bool:
        return True

    def generate(self, request: StructuredGenerationRequest) -> LLMResult:
        self.requests.append(request)
        return LLMResult(text=self._response or "", provider=self.name, model=self.model, error=self._error)


def _submission(status: str) -> dict:
    return {
        "analysis_id": SYNTHETIC_DEMONSTRATION_ID,
        "video_id": SYNTHETIC_DEMONSTRATION_ID,
        "statement": DEMONSTRATION_STATEMENT,
        "statement_type": "verified_narrative_event",
        "source_reference": "synthetic demonstration source: record-001",
        "submitted_by": "synthetic-demo-curator",
        "verification_method": "synthetic demonstration review",
        "verification_confidence": 1.0,
        "span": {"start_time": 0.0, "end_time": 1.0},
        "provenance": {"type": "expert_verification", "reference": "synthetic-demo-fixture-only"},
        "performance_mode": "narrative_dance",
        "status": status,
    }


def _review(*, production_eligible: bool) -> dict:
    return {
        "status": "verified",
        "verified_by": "synthetic-demo-verifier",
        "verification_method": "synthetic demonstration review",
        "verification_confidence": 1.0,
        "production_eligible": production_eligible,
        "review_reason": "Synthetic demonstration fixture only; not a real performance.",
    }


def _valid_provider_response(event_id: str) -> str:
    return json.dumps({
        "title": "Synthetic demonstration summary",
        "narrative": DEMONSTRATION_STATEMENT,
        "used_event_ids": [event_id],
    })


def _real_alarippu_digests() -> dict[str, str]:
    """Fingerprint persisted real artifacts to prove the demo does not write them."""
    paths = [
        *settings.results_dir.glob(f"modalities/{REAL_ALARIPPU_ID}_*.json"),
        *settings.frame_output_dir.glob(f"{REAL_ALARIPPU_ID}/**/*"),
        *settings.upload_dir.glob(f"{REAL_ALARIPPU_ID}.*"),
    ]
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
        if path.is_file()
    }


@pytest.fixture
def isolated_demo(monkeypatch):
    """Wire review and Story integration to a synthetic-only in-memory store."""
    before = _real_alarippu_digests()
    store: dict[tuple[str, str], dict] = {
        # Deliberately tempting raw values: the production package/provider
        # boundary must never read them.
        (SYNTHETIC_DEMONSTRATION_ID, "mudra"): {"raw_mudra": "not narrative evidence"},
        (SYNTHETIC_DEMONSTRATION_ID, "bhava"): {"raw_bhava": "not narrative evidence"},
        (SYNTHETIC_DEMONSTRATION_ID, "fusion"): {"raw_fusion": "not narrative evidence"},
        (SYNTHETIC_DEMONSTRATION_ID, "audio_evidence"): {"raw_audio": "not narrative evidence"},
        (SYNTHETIC_DEMONSTRATION_ID, "frames"): {"raw_frame": "not narrative evidence"},
        (SYNTHETIC_DEMONSTRATION_ID, "video"): {"raw_video": "not narrative evidence"},
        (SYNTHETIC_DEMONSTRATION_ID, "story"): {"raw_legacy_story": "not verified narrative evidence"},
    }

    def save(analysis_id: str, modality: str, value: dict) -> None:
        assert analysis_id == SYNTHETIC_DEMONSTRATION_ID
        store[(analysis_id, modality)] = deepcopy(value)

    def get(analysis_id: str, modality: str) -> dict:
        try:
            return deepcopy(store[(analysis_id, modality)])
        except KeyError as exc:
            raise AppError("Synthetic demonstration artifact is absent.", 404, "MODALITY_RESULT_NOT_FOUND") from exc

    monkeypatch.setattr(review_service, "save_modality_result", save)
    monkeypatch.setattr(review_service, "get_modality_result", get)
    monkeypatch.setattr(story_integration_service, "get_modality_result", get)
    yield store
    assert _real_alarippu_digests() == before


def _configure_provider(monkeypatch, provider: DeterministicDemoProvider) -> None:
    monkeypatch.setattr(narrative_generation_service, "settings", SimpleNamespace(story_llm_provider=provider.name))
    monkeypatch.setattr(narrative_generation_service, "get_provider", lambda name: provider if name == provider.name else pytest.fail("provider fallback attempted"))
    monkeypatch.setattr(story_integration_service, "configured_provider_metadata", lambda: (provider, provider.name, provider.model))


@pytest.mark.parametrize("state", ["draft", "submitted"])
def test_draft_and_submitted_demo_evidence_do_not_create_package_or_call_provider(isolated_demo, monkeypatch, state):
    provider = DeterministicDemoProvider("ollama")
    _configure_provider(monkeypatch, provider)
    review_service.submit_evidence(SYNTHETIC_DEMONSTRATION_ID, _submission(state))

    response = story_integration_service.generate_story_for_analysis(SYNTHETIC_DEMONSTRATION_ID)

    assert (SYNTHETIC_DEMONSTRATION_ID, "performance_interpretation") not in isolated_demo
    assert response["status"] == "unavailable"
    assert response["narrative"] is None
    assert provider.requests == []


def test_verified_but_ineligible_demo_evidence_does_not_create_package_or_call_provider(isolated_demo, monkeypatch):
    provider = DeterministicDemoProvider("ollama")
    _configure_provider(monkeypatch, provider)
    record = review_service.submit_evidence(SYNTHETIC_DEMONSTRATION_ID, _submission("submitted"))
    _, package = review_service.review_evidence(SYNTHETIC_DEMONSTRATION_ID, record["evidence_id"], _review(production_eligible=False))

    response = story_integration_service.generate_story_for_analysis(SYNTHETIC_DEMONSTRATION_ID)

    assert package is None
    assert (SYNTHETIC_DEMONSTRATION_ID, "performance_interpretation") not in isolated_demo
    assert response["status"] == "unavailable"
    assert provider.requests == []


def _eligible_package(isolated_demo, monkeypatch, provider_name: str = "ollama") -> tuple[dict, DeterministicDemoProvider]:
    provider = DeterministicDemoProvider(provider_name)
    _configure_provider(monkeypatch, provider)
    record = review_service.submit_evidence(SYNTHETIC_DEMONSTRATION_ID, _submission("submitted"))
    _, package = review_service.review_evidence(SYNTHETIC_DEMONSTRATION_ID, record["evidence_id"], _review(production_eligible=True))
    assert package is not None
    provider._response = _valid_provider_response(record["evidence_id"])
    return package, provider


def test_verified_eligible_demo_creates_a_validated_package_with_only_explicit_evidence(isolated_demo, monkeypatch):
    package, provider = _eligible_package(isolated_demo, monkeypatch)
    validated = validate_performance_interpretation(package, for_production=True)
    serialized = json.dumps(validated, sort_keys=True)

    assert validated["analysis_id"] == SYNTHETIC_DEMONSTRATION_ID
    assert [event["statement"] for event in validated["events"]] == [DEMONSTRATION_STATEMENT]
    assert (SYNTHETIC_DEMONSTRATION_ID, "performance_interpretation") in isolated_demo
    for raw_key in ("raw_mudra", "raw_bhava", "raw_fusion", "raw_audio", "raw_frame", "raw_video", "raw_legacy_story"):
        assert raw_key not in serialized

    response = story_integration_service.generate_story_for_analysis(SYNTHETIC_DEMONSTRATION_ID)
    assert response["status"] == "generated"
    assert response["provider"] == provider.name
    assert response["model"] == provider.model
    assert response["evidence_coverage"] == 1.0
    assert response["narrative"] == DEMONSTRATION_STATEMENT
    assert len(provider.requests) == 1


def test_structured_request_is_provider_neutral_and_no_fallback_occurs(isolated_demo, monkeypatch):
    prompts: list[str] = []
    # Create one package once. Provider selection may change the adapter and
    # metadata, but must not change the package-derived request.
    package, _ = _eligible_package(isolated_demo, monkeypatch)
    event_id = package["events"][0]["event_id"]
    for provider_name in ("ollama", "gemini", "openai"):
        provider = DeterministicDemoProvider(provider_name, _valid_provider_response(event_id))
        _configure_provider(monkeypatch, provider)
        response = story_integration_service.generate_story_for_analysis(SYNTHETIC_DEMONSTRATION_ID)
        assert response["status"] == "generated"
        assert len(provider.requests) == 1
        prompts.append(provider.requests[0].prompt)
        assert package["events"][0]["statement"] in provider.requests[0].prompt

    assert prompts[0] == prompts[1] == prompts[2]


def test_unsupported_mock_output_is_blocked_without_provider_fallback(isolated_demo, monkeypatch):
    package, provider = _eligible_package(isolated_demo, monkeypatch)
    provider._response = json.dumps({
        "title": "Synthetic demonstration summary",
        "narrative": f"{DEMONSTRATION_STATEMENT} Unsupported extra fact.",
        "used_event_ids": [package["events"][0]["event_id"]],
    })

    response = story_integration_service.generate_story_for_analysis(SYNTHETIC_DEMONSTRATION_ID)

    assert response["status"] == "blocked"
    assert response["narrative"] is None
    assert len(provider.requests) == 1


def test_synthetic_identifier_is_isolated_from_real_alarippu_id():
    assert SYNTHETIC_DEMONSTRATION_ID != REAL_ALARIPPU_ID
    assert SYNTHETIC_DEMONSTRATION_ID.startswith("phase-9-2-synthetic-demonstration-")
