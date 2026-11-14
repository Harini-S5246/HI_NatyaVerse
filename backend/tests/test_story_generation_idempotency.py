"""Story reads and retries must not consume additional Gemini requests."""
from __future__ import annotations

from copy import deepcopy

from app.core.errors import AppError
from app.services import story_integration_service as service

ANALYSIS_ID = "55555555-5555-4555-8555-555555555555"


def _package() -> dict:
    return {"schema_version": "1.0.0", "analysis_id": ANALYSIS_ID, "video_id": ANALYSIS_ID, "source_type": "curated_annotation", "production_eligible": True, "performance_mode": {"label": "narrative_dance", "verification_status": "verified", "source": "source", "source_reference": "reference", "confidence": 1.0}, "interpretation_status": "available", "summary": "Verified event.", "limitations": ["Verified evidence only."], "events": [{"event_id": "event-1", "start_time": None, "end_time": None, "type": "verified_narrative_event", "statement": "Verified event.", "evidence": [{"source": "source", "source_reference": "reference", "confidence": 1.0}]}]}


def _generated(language: str = "en") -> dict:
    return {"schema_version": "1.0.0", "analysis_id": ANALYSIS_ID, "video_id": ANALYSIS_ID, "mode": "narrative_dance", "status": "generated", "language": language, "presentation_version": service.STORY_PRESENTATION_VERSION, "title": "Verified", "narrative": "Verified event.", "evidence_coverage": 1.0, "used_event_ids": ["event-1"], "limitations": ["Verified evidence only."], "provider": "gemini", "model": "gemini-3.6-flash", "message": None}


def _wire(monkeypatch):
    store = {(ANALYSIS_ID, "performance_interpretation"): _package()}
    def get(analysis_id, modality):
        try:
            return deepcopy(store[(analysis_id, modality)])
        except KeyError as exc:
            raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND") from exc
    def save(analysis_id, modality, value):
        store[(analysis_id, modality)] = deepcopy(value)
    monkeypatch.setattr(service, "get_modality_result", get)
    monkeypatch.setattr(service, "save_modality_result", save)
    return store


def test_get_existing_story_never_invokes_generation(monkeypatch):
    _wire(monkeypatch)
    monkeypatch.setattr(service, "generate_narrative", lambda _: (_ for _ in ()).throw(AssertionError("GET must not generate")))
    result = service.get_existing_story_for_analysis(ANALYSIS_ID)
    assert result["status"] == "unavailable"
    assert "Select Generate Story" in result["message"]


def test_repeated_generation_for_same_package_uses_one_provider_call(monkeypatch):
    _wire(monkeypatch)
    calls = []
    monkeypatch.setattr(service, "generate_narrative", lambda package, **kwargs: calls.append(kwargs["language"]) or _generated(kwargs["language"]))
    first = service.generate_story_for_analysis(ANALYSIS_ID)
    second = service.generate_story_for_analysis(ANALYSIS_ID)
    assert first["status"] == second["status"] == "generated"
    assert len(calls) == 1


def test_in_progress_generation_returns_retryable_without_provider_call(monkeypatch):
    _wire(monkeypatch)
    key = f"{ANALYSIS_ID}:{service._package_fingerprint(_package())}:en"
    lock = service._lock_for(key)
    assert lock.acquire(blocking=False)
    try:
        monkeypatch.setattr(service, "generate_narrative", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("duplicate provider call")))
        result = service.generate_story_for_analysis(ANALYSIS_ID)
    finally:
        lock.release()
    assert result["status"] == "retryable"


def test_language_variants_are_persisted_and_read_independently(monkeypatch):
    _wire(monkeypatch)
    calls = []

    def generate(_package, *, language):
        calls.append(language)
        return _generated(language)

    monkeypatch.setattr(service, "generate_narrative", generate)
    english = service.generate_story_for_analysis(ANALYSIS_ID, language="en")
    tamil = service.generate_story_for_analysis(ANALYSIS_ID, language="ta")

    assert english["language"] == "en"
    assert tamil["language"] == "ta"
    assert service.get_existing_story_for_analysis(ANALYSIS_ID, language="ta")["language"] == "ta"
    assert service.get_existing_story_for_analysis(ANALYSIS_ID, language="en")["language"] == "en"
    assert calls == ["en", "ta"]


def test_story_cache_rejects_other_video_id_even_when_fingerprint_matches(monkeypatch):
    other_analysis_id = "66666666-6666-4666-8666-666666666666"
    store = {(ANALYSIS_ID, "performance_interpretation"): _package()}
    mismatched = {
        "schema_version": "1.0.0",
        "analysis_id": ANALYSIS_ID,
        "video_id": other_analysis_id,
        "package_fingerprint": service._package_fingerprint(_package()),
        "story": _generated("en"),
        "story_variants": {"en": _generated("en")},
    }

    def get(analysis_id, modality):
        try:
            return deepcopy(store[(analysis_id, modality)])
        except KeyError as exc:
            if analysis_id == ANALYSIS_ID and modality == "story_generation":
                return deepcopy(mismatched)
            raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND") from exc

    def save(analysis_id, modality, value):
        store[(analysis_id, modality)] = deepcopy(value)

    monkeypatch.setattr(service, "get_modality_result", get)
    monkeypatch.setattr(service, "save_modality_result", save)

    result = service.get_existing_story_for_analysis(ANALYSIS_ID)
    assert result["status"] == "unavailable"
    assert "Select Generate Story" in result["message"]
