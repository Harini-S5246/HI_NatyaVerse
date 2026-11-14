import copy
import json
from pathlib import Path

import pytest

from app.services.narrative_generation_service import (
    NarrativeGenerationValidationError,
    _ensure_narrative_paragraphs,
    _evidence_based_story_evidence,
    _validate_human_facing_narrative,
    _prompt,
    _validate_output_language,
    generate_narrative,
)
from app.services.performance_interpretation_service import build_performance_interpretation

FIXTURE = Path(__file__).parents[1] / "app" / "data" / "knowledge" / "narrative" / "narrative_evidence.example.json"


def _record():
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    record["source_type"] = "expert_annotation"
    record["production_eligible"] = True
    return record


def _package(mode="narrative_dance"):
    record = _record()
    record["performance_mode"]["label"] = mode
    record["performance_mode"]["verification_status"] = "unknown" if mode == "unknown" else "verified"
    return build_performance_interpretation("prod-1", record)


def _response_for(package, title="Verified sequence"):
    events = package["events"]
    return json.dumps({"title": title, "narrative": "\n\n".join(event["statement"] for event in events), "used_event_ids": [event["event_id"] for event in events]})


def test_valid_narrative_dance_generation():
    package = _package()
    result = generate_narrative(package, invoke=lambda _: _response_for(package))
    assert result["status"] == "generated"
    assert result["used_event_ids"] == ["synthetic-event-001"]


def test_requested_language_is_explicit_in_story_prompt():
    package = _package()
    prompt = _prompt(package, package["events"], "ta")
    assert "REQUESTED OUTPUT LANGUAGE: Tamil" in prompt
    assert "entire narrative entirely in Tamil" in prompt
    assert "Translate each emotional concept by its intended meaning" in prompt
    assert "gesture or expression has confidence below 0.5" in prompt
    evidence_package = _package()
    evidence_package["performance_mode"]["label"] = "evidence_based"
    evidence_prompt = _prompt(evidence_package, evidence_package["events"], "ta")
    assert "REQUESTED OUTPUT LANGUAGE: Tamil" in evidence_prompt
    assert "Maintain the same chronological coverage and level of detail as the English version" in evidence_prompt
    assert "8-12 natural paragraphs when there are at least 8 chronological beats" in evidence_prompt
    assert "Use all meaningful expressive changes in the input" in evidence_prompt
    assert "The evolving expression itself can be the complete story" in evidence_prompt
    assert "Never label a passage as a numbered phase, segment, section, or stage" in evidence_prompt
    assert "Give the story a specific, natural title naming a supported emotional turn" in evidence_prompt
    assert "Refer to these as symbolic associations" in evidence_prompt
    assert "The narrator speaks about the unfolding performance itself" in evidence_prompt
    assert "Prefer one paragraph for each beat" in evidence_prompt
    assert "No supported pose or physical context was detected" in evidence_prompt
    assert "an association with greeting returns" in evidence_prompt
    assert "End with the latest supported expressive state" in evidence_prompt
    assert "Keep Bharatanatyam Mudra names" in prompt
    assert "translate all other prose completely" in prompt


def test_evidence_based_output_requires_selected_script():
    _validate_output_language("வெளிப்பாடு", "இந்த நிகழ்ச்சி கைமுத்திரைகளால் தொடங்குகிறது.", "ta", "evidence_based")
    with pytest.raises(NarrativeGenerationValidationError, match="Tamil"):
        _validate_output_language(
            "An expressive journey",
            "The performance begins with graceful hand gestures.",
            "ta",
            "evidence_based",
        )
    _validate_output_language(
        "வெளிப்பாடு",
        "Hamsasyam முத்திரை தொடக்கத்தில் காணப்படுகிறது.",
        "ta",
        "evidence_based",
        {"Hamsasyam"},
    )
    with pytest.raises(NarrativeGenerationValidationError, match="untranslated English"):
        _validate_output_language(
            "வெளிப்பாடு",
            "Hamsasyam என்பது swan's beak எனப் பொருள்படும் முத்திரை.",
            "ta",
            "evidence_based",
            {"Hamsasyam"},
        )


def test_evidence_based_prompt_preserves_every_event_across_duration_based_sections():
    events = [
        {
            "event_id": f"analysis-segment-{index:04d}",
            "start_time": float(index),
            "end_time": float(index + 1),
            "frame_range": [index, index + 1],
            "observations": {
                "mudra": {
                    "label": "Alapadmam" if index < 45 else "Anjali",
                    "confidence": 0.8,
                    "meaning": "full-blown lotus (Alapadmam)" if index < 45 else "salutation (Anjali)",
                    "grounding": "curated",
                    "knowledge_status": "partially_verified",
                    "verification_status": "partially_verified",
                    "claim_id": f"claim-{index % 2}",
                    "source_references": ["project namesake gloss"],
                    "uncertainty_notes": ["Bibliographic provenance is incomplete."],
                },
                "bhava": {
                    "label": ("Sad", "Surprise", "Happy")[index // 30 % 3],
                    "confidence": 0.7,
                },
            },
        }
        for index in range(280)
    ]
    evidence = _evidence_based_story_evidence(events)
    segments = evidence["chronological_beats"]
    assert evidence["beat_count"] == 10
    assert len(segments) == 10
    assert [event_id for segment in segments for event_id in segment["event_ids"]] == [
        event["event_id"] for event in events
    ]
    assert segments[0]["symbolic_associations"][0]["meaning"] == "full-blown lotus"
    assert segments[0]["symbolic_associations"][0]["verification_status"] == "partially_verified"
    assert segments[0]["symbolic_associations"][0]["source_references"] == ["project namesake gloss"]
    assert "certainty" not in segments[0]["symbolic_associations"][0]
    assert segments[-1]["symbolic_associations"][0]["meaning"] == "salutation"
    assert segments[0]["expressive_qualities"][0]["meaning"] == "sorrow"
    assert [quality["meaning"] for quality in segments[-1]["expressive_qualities"]][-1] == "sorrow"
    assert all("change" in item for item in segments[0]["expressive_developments"])
    assert evidence["supported_pose_context_available"] is False
    assert all("supported_pose_context" not in segment for segment in segments)
    assert _prompt(
        {**_package(), "performance_mode": {"label": "evidence_based"}},
        events,
    ).count('"event_ids":') == 10


def test_legacy_curated_flag_without_verification_provenance_is_not_a_symbolic_association():
    event = {
        "event_id": "legacy-event",
        "start_time": 0.0,
        "end_time": 1.0,
        "observations": {
            "mudra": {
                "label": "Pataka",
                "meaning": "Flag / banner",
                "confidence": 0.99,
                "grounding": "curated",
            }
        },
    }

    evidence = _evidence_based_story_evidence([event])

    assert evidence["chronological_beats"][0]["symbolic_associations"] == []


def test_evidence_based_story_rejects_dense_or_technical_presentation():
    narrative = "The opening carries a quiet sense of expectation.\n\nA lotus-like gesture adds a moment of beauty.\n\nAs the performance continues, its expression changes.\n\nThe ending leaves the story open."
    _validate_human_facing_narrative("A Moment Unfolding", narrative, "evidence_based")
    with pytest.raises(NarrativeGenerationValidationError, match="3-12"):
        _validate_human_facing_narrative("Title", "A single dense paragraph.", "evidence_based")
    with pytest.raises(NarrativeGenerationValidationError, match="human-facing"):
        _validate_human_facing_narrative(
            "Title",
            narrative.replace("quiet sense of expectation", "model observations show changing expression labels"),
            "evidence_based",
        )
    with pytest.raises(NarrativeGenerationValidationError, match="phase labels"):
        _validate_human_facing_narrative(
            "A Moment Unfolding",
            narrative.replace("As the performance continues", "In the middle section two"),
            "evidence_based",
        )
    with pytest.raises(NarrativeGenerationValidationError, match="specific supported turn"):
        _validate_human_facing_narrative("An Expressive Journey", narrative, "evidence_based")


def test_evidence_based_title_can_reference_gesture_or_expression():
    narrative = "A possible lotus-like shape appears.\n\nThe expression appears sorrowful.\n\nAnother shape appears later."
    _validate_human_facing_narrative("Changing Expressions", narrative, "evidence_based")


def test_dense_provider_text_is_formatted_into_paragraphs_without_changing_its_words():
    source = "The opening gesture appears. The expression changes. A later gesture recurs. The story closes cautiously."
    formatted = _ensure_narrative_paragraphs(source, "evidence_based")
    assert len(formatted.split("\n\n")) == 4
    assert " ".join(formatted.split()) == source


def test_three_sentence_story_is_formatted_without_adding_filler():
    source = "At first, one gesture appears. Later, another returns. The expression then changes."
    formatted = _ensure_narrative_paragraphs(source, "evidence_based")
    assert len(formatted.split("\n\n")) == 3
    assert " ".join(formatted.split()) == source


def test_long_performance_rejects_short_narrative_even_when_otherwise_human_facing():
    narrative = "\n\n".join(f"Supported expressive development continues in section {index}." for index in range(4))
    with pytest.raises(NarrativeGenerationValidationError, match="8-12"):
        _validate_human_facing_narrative(
            "A Changing Journey",
            narrative,
            "evidence_based",
            minimum_paragraphs=8,
        )


def test_valid_pure_dance_generation():
    package = _package("pure_dance")
    result = generate_narrative(package, invoke=lambda _: _response_for(package, "Performance interpretation"))
    assert result["status"] == "generated"
    assert result["mode"] == "pure_dance"


def test_unknown_mode_is_unavailable_without_provider_call():
    result = generate_narrative(_package("unknown"), invoke=lambda _: pytest.fail("provider must not run"))
    assert result["status"] == "unavailable"
    assert result["narrative"] is None


def test_invalid_input_is_blocked_by_exception():
    with pytest.raises(NarrativeGenerationValidationError):
        generate_narrative({})


def test_production_ineligible_input_is_blocked():
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    package = build_performance_interpretation("test-1", record)
    with pytest.raises(NarrativeGenerationValidationError, match="production"):
        generate_narrative(package)


def test_missing_provenance_is_blocked():
    package = _package()
    del package["events"][0]["evidence"]
    with pytest.raises(NarrativeGenerationValidationError):
        generate_narrative(package)


@pytest.mark.parametrize("field, label", [("subject", "Krishna"), ("location", "Forest")])
def test_unsupported_character_or_location_claim_is_blocked(field, label):
    record = _record()
    record["events"][0][field] = {"label": label, "verification_status": "unverified"}
    with pytest.raises(Exception):
        build_performance_interpretation("prod-1", record)


def test_unsupported_causal_claim_is_blocked():
    record = _record()
    record["events"][0]["causal_relation"] = {"label": "causes", "verification_status": "verified", "evidence": []}
    with pytest.raises(Exception):
        build_performance_interpretation("prod-1", record)


def test_mudra_meaning_cannot_become_story_action():
    package = _package("pure_dance")
    bad = json.dumps({"title": "Performance", "narrative": "The dancer shows a lotus.", "used_event_ids": ["performance-mode"]})
    assert generate_narrative(package, invoke=lambda _: bad)["status"] == "blocked"


def test_bhava_remains_model_derived():
    package = _package("pure_dance")
    package["events"].append({"event_id": "bhava-1", "start_time": None, "end_time": None, "type": "recorded_model_observation", "statement": "Model output recorded Sad Bhava.", "evidence": [{"source": "Bhava model", "source_reference": "stored", "confidence": 0.6}]})
    result = generate_narrative(package, invoke=lambda _: _response_for(package, "Performance interpretation"))
    assert "Model output recorded Sad Bhava." in result["narrative"]


def test_unresolved_mudra_cannot_become_meaning():
    package = _package("pure_dance")
    raw = json.dumps({"title": "Performance interpretation", "narrative": "Unresolved gesture means a flower.", "used_event_ids": ["performance-mode"]})
    assert generate_narrative(package, invoke=lambda _: raw)["status"] == "blocked"


def test_hallucinated_event_id_is_rejected_and_metadata_is_preserved():
    package = _package()
    raw = json.dumps({"title": "Verified sequence", "narrative": package["events"][0]["statement"], "used_event_ids": ["made-up"]})
    result = generate_narrative(package, invoke=lambda _: raw)
    assert result["status"] == "blocked"
    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-3.5-flash-lite"


def test_verified_event_order_and_evidence_ids_are_preserved():
    record = _record()
    later = copy.deepcopy(record["events"][0])
    later["event_id"] = "synthetic-event-002"
    later["start_time"] = 3.0
    later["end_time"] = 4.0
    later["action"] = {"label": "acknowledges", "verification_status": "verified"}
    record["events"].append(later)
    package = build_performance_interpretation("prod-1", record)
    result = generate_narrative(package, invoke=lambda _: _response_for(package))
    assert result["used_event_ids"] == ["synthetic-event-001", "synthetic-event-002"]
    assert result["evidence_coverage"] == 1.0
    assert result["narrative"].find("greets") < result["narrative"].find("acknowledges")


def test_provider_failure_and_empty_response_have_no_fallback():
    package = _package()
    failure = generate_narrative(package, invoke=lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    empty = generate_narrative(package, invoke=lambda _: "")
    assert failure["status"] == empty["status"] == "blocked"
    assert failure["narrative"] is empty["narrative"] is None


def test_current_alarippu_case_without_production_evidence_cannot_generate():
    record = json.loads(FIXTURE.read_text(encoding="utf-8"))
    package = build_performance_interpretation("alarippu-id", record)
    with pytest.raises(NarrativeGenerationValidationError):
        generate_narrative(package)
