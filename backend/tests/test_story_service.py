"""Tests for evidence-grounded story generation."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.schemas.story import StoryResponse
from app.core.errors import AppError
from app.main import app
from app.services import story_service


client = TestClient(app)
VIDEO_ID = "00000000-0000-0000-0000-000000000000"


def _fusion_result_grounded(grounded_items=None, unresolved_items=None, detected_items=None):
    """A fusion result with grounded evidence ready for story generation."""
    if grounded_items is None:
        grounded_items = [
            {"id": "mudra-Pataka", "label": "Pataka", "detail": "Flag / banner", "confidence": 0.9}
        ]
    if unresolved_items is None:
        unresolved_items = [
            {"id": "mudra-Aralam", "label": "Aralam", "confidence": 0.7}
        ]
    if detected_items is None:
        detected_items = [
            {"id": "bhava-dominant", "label": "Happy bhava detected", "confidence": 0.85}
        ]

    grounded_items = [
        {
            **item,
            "knowledge_status": item.get("knowledge_status", "partially_verified"),
            "verification_status": item.get("verification_status", "partially_verified"),
            "claim_id": item.get("claim_id", f"claim-{item['label'].lower()}"),
            "source_references": item.get("source_references", ["project namesake gloss"]),
            "uncertainty_notes": item.get("uncertainty_notes", ["Bibliographic provenance is incomplete."]),
        }
        for item in grounded_items
    ]

    return {
        "analysis_id": VIDEO_ID,
        "video_id": VIDEO_ID,
        "status": "completed",
        "timeline": [
            {
                "start_time": 0.0,
                "end_time": 2.0,
                "mudra": "Pataka",
                "mudra_confidence": 0.9,
                "mudra_grounded": True,
                "bhava": "Happy",
                "bhava_confidence": 0.85,
            }
        ],
        "summary": {
            "dominant_mudra": "Pataka",
            "dominant_bhava": "Happy",
            "mudra_event_count": 1,
            "bhava_event_count": 1,
            "average_mudra_confidence": 0.9,
            "average_bhava_confidence": 0.85,
            "frame_count": 2,
        },
        "evidence": {
            "grounded": grounded_items,
            "detected": detected_items,
            "unresolved": unresolved_items,
            "interpreted": [],
        },
    }


def _fusion_result_no_grounded():
    """A fusion result with no grounded evidence."""
    return {
        "analysis_id": VIDEO_ID,
        "video_id": VIDEO_ID,
        "status": "completed",
        "timeline": [],
        "summary": {
            "dominant_mudra": None,
            "dominant_bhava": None,
            "mudra_event_count": 0,
            "bhava_event_count": 0,
            "average_mudra_confidence": None,
            "average_bhava_confidence": None,
            "frame_count": 0,
        },
        "evidence": {
            "grounded": [],
            "detected": [
                {"id": "bhava-dominant", "label": "Happy bhava detected", "confidence": 0.85}
            ],
            "unresolved": [
                {"id": "mudra-Aralam", "label": "Aralam", "confidence": 0.7}
            ],
            "interpreted": [],
        },
    }


def _fusion_result_only_detected_bhava():
    """A fusion result with ONLY detected bhava (no grounded mudra)."""
    return {
        "analysis_id": VIDEO_ID,
        "video_id": VIDEO_ID,
        "status": "completed",
        "timeline": [
            {
                "start_time": 0.0,
                "end_time": 2.0,
                "mudra": "Shivalinga",
                "mudra_confidence": 0.07,
                "mudra_grounded": False,
                "bhava": "Angry",
                "bhava_confidence": 0.686,
            }
        ],
        "summary": {
            "dominant_mudra": "Shivalinga",
            "dominant_bhava": "Angry",
            "mudra_event_count": 1,
            "bhava_event_count": 1,
            "average_mudra_confidence": 0.07,
            "average_bhava_confidence": 0.686,
            "frame_count": 309,
        },
        "evidence": {
            "grounded": [],
            "detected": [
                {"id": "bhava-dominant", "label": "Angry bhava detected", "confidence": 0.686}
            ],
            "unresolved": [
                {"id": "mudra-Shivalinga", "label": "Shivalinga", "confidence": 0.07,
                 "detail": "Meaning unavailable in current knowledge base"}
            ],
            "interpreted": [],
        },
    }


@pytest.fixture(autouse=True)
def _patch_persistence(monkeypatch):
    """Keep every test isolated from the real results directory."""
    monkeypatch.setattr(story_service, "save_modality_result", lambda *_: None)


class _FakeLLMResult:
    def __init__(self, text="", provider="gemini", model="test-model", error=None):
        self.text = text
        self.provider = provider
        self.model = model
        self.error = error


class _FakeProvider:
    name = "gemini"

    def __init__(self, available=True, result_text="A test narrative.", error=None):
        self._available = available
        self._result_text = result_text
        self._error = error
        self._model_name = "test-model"

    def is_available(self):
        return self._available

    def generate_story(self, evidence, language):
        return _FakeLLMResult(
            text=self._result_text,
            provider=self.name,
            model=self._model_name,
            error=self._error,
        )


# ----------------------------------------------------------------------
# Test 1: Grounded evidence → completed story
# ----------------------------------------------------------------------

def test_grounded_evidence_produces_completed_story(monkeypatch):
    """Test that grounded evidence results in a 'completed' status story."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "completed"
    assert result["title"] is not None
    assert result["story"] is not None
    assert len(result["interpretations"]) > 0
    assert result["generation_method"] == "llm"


def test_narrative_events_are_chronological_and_grounded_only(monkeypatch):
    """Narrative input includes verified events in order and excludes unresolved gestures."""
    fusion = _fusion_result_grounded(
        grounded_items=[
            {"id": "mudra-Pataka", "label": "Pataka", "detail": "Flag / banner", "confidence": 0.9},
            {"id": "mudra-Anjali", "label": "Anjali", "detail": "Salutation", "confidence": 0.8},
        ],
        unresolved_items=[
            {"id": "mudra-Aralam", "label": "Aralam", "confidence": 0.7},
        ],
    )
    fusion["timeline"].append(
        {
            "start_time": 2.0,
            "end_time": 3.0,
            "mudra": "Anjali",
            "mudra_confidence": 0.8,
            "mudra_grounded": True,
            "bhava": "Happy",
            "bhava_confidence": 0.85,
        }
    )
    captured = {}

    class CapturingProvider(_FakeProvider):
        def generate_story(self, evidence, language):
            captured["evidence"] = evidence
            return _FakeLLMResult(
                text="Pataka Flag / banner and Anjali Salutation with Happy bhava."
            )

    monkeypatch.setattr(story_service, "get_modality_result", lambda *_: fusion)
    monkeypatch.setattr(story_service, "get_provider", lambda *_: CapturingProvider())

    result = story_service.generate_story(VIDEO_ID, "en")
    events = captured["evidence"]["narrative_events"]

    assert [event["mudra"] for event in events] == ["Pataka", "Anjali"]
    assert all(event["grounded"] for event in events)
    assert "Aralam" not in {event["mudra"] for event in events}
    assert result["narrative_confidence"] == "medium"
    assert events[0]["verification_status"] == "partially_verified"
    assert events[0]["source_references"] == ["project namesake gloss"]
    assert "partially verified meaning" in result["interpretations"][0]["statement"]
    assert result["interpretations"][0]["verification_status"] == "partially_verified"


def test_legacy_grounded_flag_without_provenance_does_not_create_cultural_meaning():
    fusion = _fusion_result_grounded(
        grounded_items=[
            {"id": "mudra-Pataka", "label": "Pataka", "detail": "Flag / banner", "confidence": 0.9}
        ],
        detected_items=[],
    )
    fusion["evidence"]["grounded"][0].pop("verification_status")
    fusion["evidence"]["grounded"][0].pop("knowledge_status")
    fusion["evidence"]["grounded"][0].pop("claim_id")
    fusion["evidence"]["grounded"][0].pop("source_references")
    package = story_service._build_evidence_package(fusion)

    assert package["grounded_evidence"] == []
    assert package["narrative_events"] == []
    assert story_service._build_interpretations(fusion["evidence"])[0] == []


def test_generic_emotion_evidence_is_described_as_facial_expression_observation():
    interpretations, _, _ = story_service._build_interpretations({
        "grounded": [],
        "detected": [{
            "id": "emotion-happy",
            "label": "Happy facial expression detected",
            "confidence": 0.9,
        }],
        "unresolved": [],
        "interpreted": [],
    })

    assert interpretations[0]["statement"] == (
        "A facial-expression model recorded the predicted emotion label Happy."
    )
    assert "classical Bhava" not in interpretations[0]["statement"]
    assert "Rasa" not in interpretations[0]["statement"]


def test_repeated_grounded_occurrences_are_summarized_once(monkeypatch):
    """Repeated occurrences of one verified fact should not become report-like prose."""
    fusion = _fusion_result_grounded()
    fusion["timeline"] = fusion["timeline"] * 3
    captured = {}

    class CapturingProvider(_FakeProvider):
        def generate_story(self, evidence, language):
            captured["evidence"] = evidence
            return _FakeLLMResult(
                text="Pataka Flag / banner and Happy bhava."
            )

    monkeypatch.setattr(story_service, "get_modality_result", lambda *_: fusion)
    monkeypatch.setattr(story_service, "get_provider", lambda *_: CapturingProvider())

    story_service.generate_story(VIDEO_ID, "en")

    events = captured["evidence"]["narrative_events"]
    assert [event["mudra"] for event in events] == ["Pataka"]


# ----------------------------------------------------------------------
# Test 2: No evidence → insufficient_grounded_evidence
# ----------------------------------------------------------------------

def test_no_evidence_produces_insufficient_status(monkeypatch):
    """Test that no grounded/detected evidence results in 'insufficient_grounded_evidence' status."""
    fusion = _fusion_result_no_grounded()
    fusion["evidence"]["detected"] = []  # Remove detected too
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: fusion,
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "insufficient_grounded_evidence"
    assert result["title"] is None
    assert result["story"] is None
    assert len(result["interpretations"]) == 0
    assert result["message"] is not None


# ----------------------------------------------------------------------
# Test 3: Detected Bhava alone is sufficient for a limited story
# ----------------------------------------------------------------------

def test_detected_bhava_alone_supports_story(monkeypatch):
    """Test that detected Bhava (real model output) is valid evidence for a limited story."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_only_detected_bhava(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "completed"
    assert result["story"] is not None
    assert len(result["interpretations"]) > 0
    # The unresolved Shivalinga must remain unresolved
    assert "mudra-Shivalinga" in result["unresolved_evidence"]


# ----------------------------------------------------------------------
# Test 4: Supporting evidence IDs preserved
# ----------------------------------------------------------------------

def test_supporting_evidence_ids_preserved(monkeypatch):
    """Test that supporting evidence IDs are preserved in interpretations and response."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert len(result["supporting_evidence"]) > 0
    assert "mudra-Pataka" in result["supporting_evidence"]

    for interp in result["interpretations"]:
        assert "supporting_evidence" in interp
        assert len(interp["supporting_evidence"]) > 0


# ----------------------------------------------------------------------
# Test 5: English output
# ----------------------------------------------------------------------

def test_english_story_output(monkeypatch):
    """Test that English language produces appropriate English story text."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(
            result_text=(
                "This is an English narrative about Happy bhava, Pataka, "
                "and Flag / banner."
            )
        ),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["language"] == "en"
    assert result["story"] is not None
    assert "English narrative" in result["story"]


# ----------------------------------------------------------------------
# Test 6: Tamil output
# ----------------------------------------------------------------------

def test_tamil_story_output(monkeypatch):
    """Test that Tamil language produces appropriate Tamil story text."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(
            result_text="இது ஒரு தமிழ் கதை: Happy bhava, Pataka, Flag / banner."
        ),
    )

    result = story_service.generate_story(VIDEO_ID, "ta")

    assert result["language"] == "ta"
    assert result["story"] is not None
    assert "தமிழ்" in result["story"]


# ----------------------------------------------------------------------
# Test 7: Hindi output
# ----------------------------------------------------------------------

def test_hindi_story_output(monkeypatch):
    """Test that Hindi language produces appropriate Hindi story text."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(
            result_text="यह एक हिंदी कहानी है: Happy bhava, Pataka, Flag / banner।"
        ),
    )

    result = story_service.generate_story(VIDEO_ID, "hi")

    assert result["language"] == "hi"
    assert result["story"] is not None
    assert "हिंदी" in result["story"]


# ----------------------------------------------------------------------
# Test 8: Malayalam output
# ----------------------------------------------------------------------

def test_malayalam_story_output(monkeypatch):
    """Test that Malayalam language produces appropriate Malayalam story text."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(
            result_text="ഇതൊരു മലയാളം കഥയാണ്: Happy bhava, Pataka, Flag / banner."
        ),
    )

    result = story_service.generate_story(VIDEO_ID, "ml")

    assert result["language"] == "ml"
    assert result["story"] is not None
    assert "മലയാളം" in result["story"]


# ----------------------------------------------------------------------
# Test 9: Language aliases
# ----------------------------------------------------------------------

def test_language_aliases_en(monkeypatch):
    """Test that 'en' and 'english' both resolve to the same output."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result_en = story_service.generate_story(VIDEO_ID, "en")
    result_english = story_service.generate_story(VIDEO_ID, "english")

    assert result_en["language"] == result_english["language"] == "en"


def test_language_aliases_ta(monkeypatch):
    """Test that 'ta' and 'tamil' both resolve to the same output."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result_ta = story_service.generate_story(VIDEO_ID, "ta")
    result_tamil = story_service.generate_story(VIDEO_ID, "tamil")

    assert result_ta["language"] == result_tamil["language"] == "ta"


def test_language_aliases_hi(monkeypatch):
    """Test that 'hi' and 'hindi' both resolve to the same output."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result_hi = story_service.generate_story(VIDEO_ID, "hi")
    result_hindi = story_service.generate_story(VIDEO_ID, "hindi")

    assert result_hi["language"] == result_hindi["language"] == "hi"


def test_language_aliases_ml(monkeypatch):
    """Test that 'ml' and 'malayalam' both resolve to the same output."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result_ml = story_service.generate_story(VIDEO_ID, "ml")
    result_malayalam = story_service.generate_story(VIDEO_ID, "malayalam")

    assert result_ml["language"] == result_malayalam["language"] == "ml"


def test_language_aliases_case_insensitive(monkeypatch):
    """Test that language aliases are case-insensitive."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result_lower = story_service.generate_story(VIDEO_ID, "english")
    result_upper = story_service.generate_story(VIDEO_ID, "ENGLISH")
    result_mixed = story_service.generate_story(VIDEO_ID, "English")

    assert result_lower["language"] == result_upper["language"] == result_mixed["language"]


# ----------------------------------------------------------------------
# Test 10: Unsupported language
# ----------------------------------------------------------------------

def test_unsupported_language_raises_error(monkeypatch):
    """Test that unsupported language raises AppError with UNSUPPORTED_LANGUAGE code."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )

    with pytest.raises(AppError) as excinfo:
        story_service.generate_story(VIDEO_ID, "fr")

    assert excinfo.value.code == "UNSUPPORTED_LANGUAGE"
    assert excinfo.value.status_code == 400
    assert "Unsupported language" in excinfo.value.message


def test_default_language_is_english(monkeypatch):
    """Test that no language argument defaults to English."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result = story_service.generate_story(VIDEO_ID)

    assert result["language"] == "en"


# ----------------------------------------------------------------------
# Test 11: Missing fusion result
# ----------------------------------------------------------------------

def test_missing_fusion_result_raises_error(monkeypatch):
    """Test that missing fusion result raises FUSION_RESULT_REQUIRED."""
    def missing(*_):
        raise AppError("not found", 404, "MODALITY_RESULT_NOT_FOUND")

    monkeypatch.setattr(story_service, "get_modality_result", missing)

    with pytest.raises(AppError) as excinfo:
        story_service.generate_story(VIDEO_ID, "en")

    assert excinfo.value.code == "FUSION_RESULT_REQUIRED"
    assert excinfo.value.status_code == 404


def test_mismatched_fusion_result_is_rejected(monkeypatch):
    """Story generation must never use a fusion record belonging to another ID."""
    fusion = _fusion_result_grounded()
    fusion["analysis_id"] = "11111111-1111-1111-1111-111111111111"
    fusion["video_id"] = "11111111-1111-1111-1111-111111111111"
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: fusion,
    )

    with pytest.raises(AppError) as excinfo:
        story_service.generate_story(VIDEO_ID, "en")

    assert excinfo.value.code == "ANALYSIS_ID_MISMATCH"
    assert excinfo.value.status_code == 409


# ----------------------------------------------------------------------
# Test 12: Story persistence
# ----------------------------------------------------------------------

def test_story_persistence_is_called(monkeypatch):
    """Test that the story result is saved via save_modality_result."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    save_calls = []

    def mock_save(analysis_id, modality, result):
        save_calls.append((analysis_id, modality, result))

    monkeypatch.setattr(story_service, "save_modality_result", mock_save)

    story_service.generate_story(VIDEO_ID, "en")

    assert len(save_calls) == 1
    assert save_calls[0][0] == VIDEO_ID
    assert save_calls[0][1] == "story"
    assert save_calls[0][2]["analysis_id"] == VIDEO_ID
    assert save_calls[0][2]["status"] == "completed"


# ----------------------------------------------------------------------
# Test 13: StoryResponse schema validation
# ----------------------------------------------------------------------

def test_response_schema_validation_completed(monkeypatch):
    """Test that generated story passes StoryResponse schema validation."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")
    validated = StoryResponse.model_validate(result)

    assert validated.analysis_id == VIDEO_ID
    assert validated.status == "completed"
    assert validated.language == "en"
    assert validated.title is not None
    assert validated.story is not None
    assert len(validated.interpretations) > 0
    assert len(validated.supporting_evidence) > 0


def test_response_schema_validation_insufficient(monkeypatch):
    """Test that insufficient evidence response passes schema validation."""
    fusion = _fusion_result_no_grounded()
    fusion["evidence"]["detected"] = []
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: fusion,
    )

    result = story_service.generate_story(VIDEO_ID, "en")
    validated = StoryResponse.model_validate(result)

    assert validated.analysis_id == VIDEO_ID
    assert validated.status == "insufficient_grounded_evidence"
    assert validated.title is None
    assert validated.story is None
    assert validated.interpretations == []
    assert validated.message is not None


# ----------------------------------------------------------------------
# Test 14: Gemini provider
# ----------------------------------------------------------------------

def test_gemini_provider_used_by_default(monkeypatch):
    """Test that Gemini is the default provider."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    provider = _FakeProvider()
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: provider,
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["provider"] == "gemini"
    assert result["generation_method"] == "llm"


def test_openai_provider_explicit(monkeypatch):
    """Test that OpenAI can be explicitly selected."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    provider = _FakeProvider()
    provider.name = "openai"
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: provider,
    )

    result = story_service.generate_story(VIDEO_ID, "en", provider="openai")

    assert result["provider"] == "openai"
    assert result["generation_method"] == "llm"


# ----------------------------------------------------------------------
# Test 15: Provider failure → fallback
# ----------------------------------------------------------------------

def test_gemini_failure_returns_generation_error(monkeypatch):
    """Test that a provider failure returns an explicit generation error, not a stale default narrative."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(error="API error"),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "generation_failed"
    assert result["story"] is None
    assert result["title"] is None
    assert result["generation_method"] == "generation_error"
    assert result["provider"] == "gemini"
    assert "Story generation failed" in result["message"]


def test_provider_unavailable_returns_generation_error(monkeypatch):
    """Test that an unavailable provider returns an explicit generation error instead of stale narrative text."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(available=False),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "generation_failed"
    assert result["story"] is None
    assert result["title"] is None
    assert result["generation_method"] == "generation_error"
    assert "Story generation failed" in result["message"]


def test_invalid_llm_response_returns_generation_error(monkeypatch):
    """Test that empty LLM output returns an explicit generation error instead of any narrative."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(result_text=""),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "generation_failed"
    assert result["story"] is None
    assert result["title"] is None
    assert result["generation_method"] == "generation_error"
    assert "Story generation failed" in result["message"]


# ----------------------------------------------------------------------
# Test 16: Unresolved evidence surfaced
# ----------------------------------------------------------------------

def test_unresolved_evidence_surfaces_in_response(monkeypatch):
    """Test that unresolved evidence is surfaced in the response."""
    fusion_with_unresolved = _fusion_result_grounded(
        grounded_items=[
            {"id": "mudra-Pataka", "label": "Pataka", "detail": "Flag / banner", "confidence": 0.9}
        ],
        unresolved_items=[
            {"id": "mudra-Aralam", "label": "Aralam", "confidence": 0.7},
            {"id": "mudra-Unknown", "label": "Unknown", "confidence": 0.6},
        ],
    )

    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: fusion_with_unresolved,
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert len(result["unresolved_evidence"]) == 2
    assert "mudra-Aralam" in result["unresolved_evidence"]
    assert "mudra-Unknown" in result["unresolved_evidence"]


# ----------------------------------------------------------------------
# Test 17: Multiple grounded evidence items
# ----------------------------------------------------------------------

def test_multiple_grounded_evidence_items(monkeypatch):
    """Test story generation with multiple grounded evidence items."""
    fusion_multi = _fusion_result_grounded(
        grounded_items=[
            {"id": "mudra-Pataka", "label": "Pataka", "detail": "Flag / banner", "confidence": 0.9},
            {"id": "mudra-Tripataka", "label": "Tripataka", "detail": "Bamboo", "confidence": 0.85},
            {"id": "mudra-Ardhachandra", "label": "Ardhachandra", "detail": "Half moon", "confidence": 0.8},
        ]
    )

    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: fusion_multi,
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "completed"
    assert len(result["interpretations"]) >= 3
    assert len(result["supporting_evidence"]) >= 3


def test_empty_language_defaults_to_english(monkeypatch):
    """Test that empty string language defaults to English."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )
    monkeypatch.setattr(
        story_service,
        "get_provider",
        lambda *_: _FakeProvider(),
    )

    result = story_service.generate_story(VIDEO_ID, "")

    assert result["language"] == "en"


# ----------------------------------------------------------------------
# Endpoint Tests
# ----------------------------------------------------------------------

def test_story_endpoint_unknown_video():
    """Test that unknown video ID returns 404."""
    response = client.post(
        f"/api/videos/{VIDEO_ID}/story",
        json={"language": "en"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "VIDEO_NOT_FOUND"


def test_story_endpoint_with_valid_mock(monkeypatch):
    """Test story endpoint with mocked dependencies."""
    sample_response = {
        "schema_version": "1.0.0",
        "analysis_id": VIDEO_ID,
        "video_id": VIDEO_ID,
        "mode": "narrative_dance",
        "status": "generated",
        "title": "Verified sequence",
        "narrative": "Verified narrative event: Performer A greets Performer B.",
        "evidence_coverage": 1.0,
        "used_event_ids": ["event-1"],
        "limitations": [],
        "message": None,
        "provider": "ollama",
        "model": "qwen2.5-coder:3b",
    }

    with (
        patch("app.api.routes.stories.get_uploaded_video_path"),
        patch("app.api.routes.stories.generate_story_for_analysis", return_value=sample_response),
    ):
        response = client.post(
            f"/api/videos/{VIDEO_ID}/story",
            json={"language": "en"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "generated"
    assert body["title"] is not None
    assert body["used_event_ids"] == ["event-1"]


def test_story_endpoint_default_language():
    """Test story endpoint without language parameter."""
    sample_response = {
        "schema_version": "1.0.0",
        "analysis_id": VIDEO_ID,
        "video_id": VIDEO_ID, "mode": "unknown", "status": "unavailable",
        "title": None, "narrative": None, "evidence_coverage": 0.0,
        "used_event_ids": [], "limitations": ["No production evidence."],
        "message": "No production evidence.", "provider": "ollama", "model": "qwen2.5-coder:3b",
    }

    with (
        patch("app.api.routes.stories.get_uploaded_video_path"),
        patch("app.api.routes.stories.generate_story_for_analysis", return_value=sample_response),
    ):
        response = client.post(f"/api/videos/{VIDEO_ID}/story", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"


def test_story_get_endpoint_forwards_requested_language():
    sample_response = {
        "schema_version": "1.0.0",
        "analysis_id": VIDEO_ID,
        "video_id": VIDEO_ID,
        "mode": "unknown",
        "status": "unavailable",
        "language": "ta",
        "title": None,
        "narrative": None,
        "evidence_coverage": 0.0,
        "used_event_ids": [],
        "limitations": [],
        "message": "No production evidence.",
        "provider": "ollama",
        "model": "qwen2.5-coder:3b",
    }
    with (
        patch("app.api.routes.stories.get_uploaded_video_path"),
        patch("app.api.routes.stories.get_existing_story_for_analysis", return_value=sample_response) as get_story,
    ):
        response = client.get(f"/api/videos/{VIDEO_ID}/story", params={"language": "ta"})

    assert response.status_code == 200
    assert response.json()["language"] == "ta"
    get_story.assert_called_once_with(VIDEO_ID, language="ta")


def test_story_endpoint_ignores_legacy_provider_selection():
    """The integrated endpoint always uses the Phase 6 Ollama boundary."""
    sample_response = {
        "schema_version": "1.0.0",
        "analysis_id": VIDEO_ID,
        "video_id": VIDEO_ID, "mode": "unknown", "status": "unavailable",
        "title": None, "narrative": None, "evidence_coverage": 0.0,
        "used_event_ids": [], "limitations": ["No production evidence."],
        "message": "No production evidence.", "provider": "ollama", "model": "qwen2.5-coder:3b",
    }

    with (
        patch("app.api.routes.stories.get_uploaded_video_path"),
        patch("app.api.routes.stories.generate_story_for_analysis", return_value=sample_response) as generate,
    ):
        response = client.post(
            f"/api/videos/{VIDEO_ID}/story",
            json={"language": "ta", "provider": "openai"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "ollama"
    generate.assert_called_once_with(VIDEO_ID, language="ta")
