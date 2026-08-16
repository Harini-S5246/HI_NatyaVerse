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

    return {
        "analysis_id": VIDEO_ID,
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


@pytest.fixture(autouse=True)
def _patch_persistence(monkeypatch):
    """Keep every test isolated from the real results directory."""
    monkeypatch.setattr(story_service, "save_modality_result", lambda *_: None)


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

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "completed"
    assert result["title"] is not None
    assert result["story"] is not None
    assert len(result["interpretations"]) > 0


# ----------------------------------------------------------------------
# Test 2: Unresolved evidence → insufficient_grounded_evidence
# ----------------------------------------------------------------------

def test_unresolved_evidence_produces_insufficient_status(monkeypatch):
    """Test that no grounded evidence results in 'insufficient_grounded_evidence' status."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_no_grounded(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "insufficient_grounded_evidence"
    assert result["title"] is None
    assert result["story"] is None
    assert len(result["interpretations"]) == 0
    assert result["message"] is not None


# ----------------------------------------------------------------------
# Test 3: Detected Bhava is not converted into interpretation
# ----------------------------------------------------------------------

def test_detected_bhava_not_converted_to_interpretation(monkeypatch):
    """Test that detected (non-grounded) evidence is NOT turned into interpretations."""
    # Create a fusion result with ONLY detected bhava and NO grounded evidence
    fusion_result = {
        "analysis_id": VIDEO_ID,
        "status": "completed",
        "timeline": [],
        "summary": {},
        "evidence": {
            "grounded": [],  # Empty - no grounded evidence
            "detected": [
                {"id": "bhava-Happy", "label": "Happy bhava detected", "confidence": 0.85}
            ],
            "unresolved": [],
            "interpreted": [],
        },
    }

    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: fusion_result,
    )

    result = story_service.generate_story(VIDEO_ID, "en")

    # Bhava should NOT produce an interpretation since it's only detected, not grounded
    assert result["status"] == "insufficient_grounded_evidence"
    assert result["interpretations"] == []
    # Bhava detected should NOT appear in unresolved_evidence (unresolved is for grounded but missing KB)
    assert "bhava-Happy" not in [item["id"] for item in result.get("unresolved_evidence", [])]


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

    result = story_service.generate_story(VIDEO_ID, "en")

    # Check that supporting evidence IDs are tracked
    assert len(result["supporting_evidence"]) > 0
    assert "mudra-Pataka" in result["supporting_evidence"]

    # Check that interpretations reference their supporting evidence
    for interp in result["interpretations"]:
        assert "supporting_evidence" in interp
        assert len(interp["supporting_evidence"]) > 0
        assert interp["supporting_evidence"][0] in result["supporting_evidence"]


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

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["language"] == "en"
    assert result["title"] == "Evidence-Grounded Interpretation"
    assert result["story"] is not None
    # Check for English-specific content in the story body
    assert "This interpretation is generated exclusively from evidence supported by the curated knowledge base" in result["story"]
    assert "gesture appears in this performance" in result["story"]


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

    result = story_service.generate_story(VIDEO_ID, "ta")

    assert result["language"] == "ta"
    assert result["title"] == "சான்று அடிப்படையிலான விளக்கம்"
    assert result["story"] is not None
    # Check for Tamil-specific content in the story body
    assert "இந்த விளக்கம், அறிவுத் தளத்தால் ஆதரிக்கப்படும் சான்றுகளை" in result["story"]
    # The statement itself should still be in English (curated content)
    assert "Flag / banner" in result["story"]


# ----------------------------------------------------------------------
# Test 7: English/Tamil aliases
# ----------------------------------------------------------------------

def test_language_aliases_en(monkeypatch):
    """Test that 'en' and 'english' both resolve to the same output."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )

    result_en = story_service.generate_story(VIDEO_ID, "en")
    result_english = story_service.generate_story(VIDEO_ID, "english")

    assert result_en["language"] == result_english["language"] == "en"
    assert result_en["title"] == result_english["title"]
    assert result_en["story"] == result_english["story"]


def test_language_aliases_ta(monkeypatch):
    """Test that 'ta' and 'tamil' both resolve to the same output."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )

    result_ta = story_service.generate_story(VIDEO_ID, "ta")
    result_tamil = story_service.generate_story(VIDEO_ID, "tamil")

    assert result_ta["language"] == result_tamil["language"] == "ta"
    assert result_ta["title"] == result_tamil["title"]
    assert result_ta["story"] == result_tamil["story"]


def test_language_aliases_case_insensitive(monkeypatch):
    """Test that language aliases are case-insensitive."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )

    result_lower = story_service.generate_story(VIDEO_ID, "english")
    result_upper = story_service.generate_story(VIDEO_ID, "ENGLISH")
    result_mixed = story_service.generate_story(VIDEO_ID, "English")

    assert result_lower["language"] == result_upper["language"] == result_mixed["language"]


# ----------------------------------------------------------------------
# Test 8: Unsupported language
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

    result = story_service.generate_story(VIDEO_ID)

    assert result["language"] == "en"


# ----------------------------------------------------------------------
# Test 9: Missing fusion result
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


# ----------------------------------------------------------------------
# Test 10: Story persistence
# ----------------------------------------------------------------------

def test_story_persistence_is_called(monkeypatch):
    """Test that the story result is saved via save_modality_result."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
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
# Test 11: StoryResponse schema validation
# ----------------------------------------------------------------------

def test_response_schema_validation_completed(monkeypatch):
    """Test that generated story passes StoryResponse schema validation."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
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
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_no_grounded(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")
    validated = StoryResponse.model_validate(result)

    assert validated.analysis_id == VIDEO_ID
    assert validated.status == "insufficient_grounded_evidence"
    assert validated.title is None
    assert validated.story is None
    assert validated.interpretations == []
    assert validated.message is not None


def test_response_schema_interpretations_structure(monkeypatch):
    """Test that interpretations have correct structure and types."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
    )

    result = story_service.generate_story(VIDEO_ID, "en")
    validated = StoryResponse.model_validate(result)

    for interp in validated.interpretations:
        assert isinstance(interp.id, str)
        assert isinstance(interp.statement, str)
        assert isinstance(interp.supporting_evidence, list)
        assert all(isinstance(eid, str) for eid in interp.supporting_evidence)
        assert interp.status == "evidence_supported"
        # Confidence may be None or float
        if interp.confidence is not None:
            assert isinstance(interp.confidence, (int, float))


# ----------------------------------------------------------------------
# Additional edge cases
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

    result = story_service.generate_story(VIDEO_ID, "en")

    # Unresolved evidence should appear in the response (as evidence IDs, not labels)
    assert len(result["unresolved_evidence"]) == 2
    assert "mudra-Aralam" in result["unresolved_evidence"]
    assert "mudra-Unknown" in result["unresolved_evidence"]


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

    result = story_service.generate_story(VIDEO_ID, "en")

    assert result["status"] == "completed"
    assert len(result["interpretations"]) == 3
    assert len(result["supporting_evidence"]) == 3
    # Each supporting evidence ID should be from our input
    for ev_id in result["supporting_evidence"]:
        assert ev_id.startswith("mudra-")


def test_empty_language_defaults_to_english(monkeypatch):
    """Test that empty string language defaults to English."""
    monkeypatch.setattr(
        story_service,
        "get_modality_result",
        lambda *_: _fusion_result_grounded(),
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
        "analysis_id": VIDEO_ID,
        "status": "completed",
        "language": "en",
        "title": "Evidence-Grounded Interpretation",
        "story": "This is a test story.",
        "interpretations": [
            {
                "id": "interp-pataka",
                "statement": "The Pataka gesture appears in this performance. In the curated knowledge base, Pataka corresponds to Flag / banner.",
                "supporting_evidence": ["mudra-Pataka"],
                "confidence": 0.9,
                "status": "evidence_supported",
            }
        ],
        "supporting_evidence": ["mudra-Pataka"],
        "unresolved_evidence": [],
        "message": None,
    }

    with (
        patch("app.api.routes.stories.get_uploaded_video_path"),
        patch("app.api.routes.stories.generate_story", return_value=sample_response),
    ):
        response = client.post(
            f"/api/videos/{VIDEO_ID}/story",
            json={"language": "en"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["language"] == "en"
    assert body["title"] is not None
    assert len(body["interpretations"]) > 0


def test_story_endpoint_default_language():
    """Test story endpoint without language parameter."""
    sample_response = {
        "analysis_id": VIDEO_ID,
        "status": "completed",
        "language": "en",
        "title": "Evidence-Grounded Interpretation",
        "story": "This is a test story.",
        "interpretations": [],
        "supporting_evidence": [],
        "unresolved_evidence": [],
        "message": None,
    }

    with (
        patch("app.api.routes.stories.get_uploaded_video_path"),
        patch("app.api.routes.stories.generate_story", return_value=sample_response),
    ):
        response = client.post(f"/api/videos/{VIDEO_ID}/story", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "en"
