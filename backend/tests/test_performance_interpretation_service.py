import copy
import json
from pathlib import Path

import pytest

from app.services.performance_interpretation_service import (
    PerformanceInterpretationValidationError,
    build_analysis_observation_interpretation,
    build_performance_interpretation,
    validate_performance_interpretation,
)

FIXTURE = Path(__file__).parents[1] / "app" / "data" / "knowledge" / "narrative" / "narrative_evidence.example.json"


def _record():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _mode(record, label, status="verified"):
    record["performance_mode"]["label"] = label
    record["performance_mode"]["verification_status"] = status


def test_verified_pure_dance_interpretation():
    record = _record()
    _mode(record, "pure_dance")
    package = build_performance_interpretation("a-1", record)
    assert package["interpretation_status"] == "available"
    assert package["events"][0]["type"] == "verified_performance_event"


def test_verified_narrative_dance_package_preserves_event_timestamps():
    package = build_performance_interpretation("a-1", _record())
    assert package["events"][0]["event_id"] == "synthetic-event-001"
    assert package["events"][0]["start_time"] == 0.0
    assert package["events"][0]["end_time"] == 2.0


def test_unknown_mode_is_unavailable_and_has_no_events():
    record = _record()
    _mode(record, "unknown", "unknown")
    package = build_performance_interpretation("a-1", record)
    assert package["interpretation_status"] == "unavailable"
    assert package["events"] == []


def test_missing_performance_mode_provenance_is_rejected():
    record = _record()
    del record["performance_mode"]["source"]
    with pytest.raises(PerformanceInterpretationValidationError, match="performance_mode.source"):
        build_performance_interpretation("a-1", record)


def test_event_without_provenance_is_rejected():
    record = _record()
    record["events"][0]["evidence"] = []
    with pytest.raises(PerformanceInterpretationValidationError, match="evidence"):
        build_performance_interpretation("a-1", record)


def test_unsupported_story_statement_field_is_rejected():
    record = _record()
    with pytest.raises(PerformanceInterpretationValidationError, match="unsupported narrative fields"):
        build_performance_interpretation("a-1", record, recorded_observations={"story": "invented"})


@pytest.mark.parametrize("field, label", [("subject", "Character"), ("location", "Forest")])
def test_unsupported_character_or_location_claim_is_rejected(field, label):
    record = _record()
    record["events"][0][field] = {"label": label, "verification_status": "unverified"}
    with pytest.raises(PerformanceInterpretationValidationError, match="unverified"):
        build_performance_interpretation("a-1", record)


def test_unsupported_causal_claim_is_rejected():
    record = _record()
    record["events"][0]["causal_relation"] = {"label": "causes", "verification_status": "verified", "evidence": []}
    with pytest.raises(PerformanceInterpretationValidationError, match="causal_relation.evidence"):
        build_performance_interpretation("a-1", record)


def test_mudra_meaning_is_reported_as_model_and_knowledge_base_observation_only():
    record = _record()
    _mode(record, "pure_dance")
    package = build_performance_interpretation("a-1", record, recorded_observations={"mudra": [{"label": "Alapadmam", "meaning": "Full-blown lotus", "recognition_confidence": 0.8, "evidence": [{"source": "model output + knowledge base", "source_reference": "recorded sources", "confidence": 0.8}]}]})
    statement = package["events"][1]["statement"]
    assert statement == "The model detected Alapadmam, and the knowledge base records a partially verified meaning as 'Full-blown lotus'."
    knowledge = package["events"][1]["mudra_knowledge"]
    assert knowledge["verification_status"] == "partially_verified"
    assert knowledge["claim_id"]
    assert knowledge["source_references"]
    assert knowledge["uncertainty_notes"]
    assert "shows" not in statement


@pytest.mark.parametrize("confidence", [None, 0.4])
def test_recorded_mudra_observation_withholds_meaning_without_reliable_confidence(confidence):
    record = _record()
    _mode(record, "pure_dance")
    observation = {
        "label": "Alapadmam",
        "meaning": "Full-blown lotus",
        "evidence": [{"source": "model output", "source_reference": "recorded sources", "confidence": 0.8}],
    }
    if confidence is not None:
        observation["recognition_confidence"] = confidence
    package = build_performance_interpretation(
        "a-1",
        record,
        recorded_observations={"mudra": [observation]},
    )

    knowledge = package["events"][1]["mudra_knowledge"]
    assert knowledge["meaning"] is None
    assert knowledge["grounding"] == "unresolved"
    assert knowledge["verification_status"] is None
    assert knowledge["uncertainty_reason"]


def test_bhava_is_explicitly_model_derived():
    record = _record()
    _mode(record, "pure_dance")
    package = build_performance_interpretation("a-1", record, recorded_observations={"bhava": [{"label": "Happy", "evidence": [{"source": "Bhava model", "source_reference": "stored output", "confidence": 0.6}]}]})
    assert package["events"][1]["statement"] == "Model output recorded facial expression: Happy."


def test_unavailable_pose_and_audio_do_not_become_evidence_or_lyrics():
    record = _record()
    _mode(record, "pure_dance")
    package = build_performance_interpretation("a-1", record, recorded_observations={"unavailable_modalities": ["pose", "audio"]})
    assert all("movement" not in event["statement"].lower() and "lyrics" not in event["statement"].lower() for event in package["events"])
    assert "no movement evidence" in package["limitations"][0].lower()
    assert "no lyrics" in package["limitations"][1].lower()


def test_evidence_references_are_preserved():
    package = build_performance_interpretation("a-1", _record())
    assert package["events"][0]["evidence"][0]["source_reference"] == "fixture annotation, event 1"


def test_synthetic_package_cannot_be_production_evidence():
    package = build_performance_interpretation("a-1", _record())
    with pytest.raises(PerformanceInterpretationValidationError, match="cannot be used"):
        validate_performance_interpretation(package, for_production=True)


def _analysis_inputs(analysis_id="analysis-a", mudra_confidence=0.9):
    artifact = {
        "analysis_id": analysis_id,
        "video_id": analysis_id,
        "status": "completed",
    }
    return (
        {
            **artifact,
            "timeline": [{
                "start_time": 0.0,
                "end_time": 1.0,
                "mudra": "Pataka",
                "mudra_confidence": mudra_confidence,
                "bhava": "Happy",
                "bhava_confidence": 0.8,
            }],
        },
        {**artifact, "mudra_events": [{"mudra": "Pataka", "start_time": 0.0, "end_time": 1.0}], "frames": []},
        {**artifact, "bhava_events": [{"bhava": "Happy", "start_time": 0.0, "end_time": 1.0}], "frames": []},
    )


def test_analysis_interpretation_preserves_partial_knowledge_provenance(monkeypatch):
    class KnowledgeStub:
        def retrieve_mudra(self, label):
            assert label == "Pataka"
            return {
                "status": "partially_verified",
                "claim": {
                    "claim_id": "claim-pataka",
                    "verification_status": "partially_verified",
                    "descriptions": {"en": "Flag / banner"},
                    "sources": [{"reference": "project namesake gloss"}],
                    "uncertainty_notes": ["Bibliographic provenance is incomplete."],
                },
                "reason": None,
            }

    monkeypatch.setattr(
        "app.services.performance_interpretation_service.knowledge_service",
        KnowledgeStub(),
    )
    fusion, mudra, bhava = _analysis_inputs()
    package = build_analysis_observation_interpretation("analysis-a", fusion, mudra, bhava)
    observation = package["events"][0]["observations"]["mudra"]

    assert observation["meaning"] == "Flag / banner"
    assert observation["grounding"] == "curated"
    assert observation["verification_status"] == "partially_verified"
    assert observation["knowledge_status"] == "partially_verified"
    assert observation["claim_id"] == "claim-pataka"
    assert observation["source_references"] == ["project namesake gloss"]
    assert observation["uncertainty_notes"] == ["Bibliographic provenance is incomplete."]


def test_analysis_interpretation_withholds_low_confidence_mudra_meaning(monkeypatch):
    class KnowledgeStub:
        calls = 0

        def retrieve_mudra(self, label):
            self.calls += 1
            raise AssertionError("Low-confidence Mudra must not be retrieved.")

    knowledge = KnowledgeStub()
    monkeypatch.setattr(
        "app.services.performance_interpretation_service.knowledge_service",
        knowledge,
    )
    fusion, mudra, bhava = _analysis_inputs(mudra_confidence=0.49)
    package = build_analysis_observation_interpretation("analysis-a", fusion, mudra, bhava)
    observation = package["events"][0]["observations"]["mudra"]

    assert knowledge.calls == 0
    assert observation["meaning"] is None
    assert observation["grounding"] == "unresolved"
    assert observation["verification_status"] is None
    assert observation["uncertainty_reason"]


@pytest.mark.parametrize("confidence", [None, float("nan"), -0.1, 1.1])
def test_analysis_interpretation_rejects_missing_or_invalid_recognition_confidence(confidence):
    fusion, mudra, bhava = _analysis_inputs(mudra_confidence=confidence)
    with pytest.raises(PerformanceInterpretationValidationError, match="confidence"):
        build_analysis_observation_interpretation("analysis-a", fusion, mudra, bhava)


def test_model_analysis_meaning_requires_verification_source_and_confidence(monkeypatch):
    class KnowledgeStub:
        def retrieve_mudra(self, label):
            return {
                "status": "partially_verified",
                "claim": {
                    "claim_id": "claim-pataka",
                    "verification_status": "partially_verified",
                    "descriptions": {"en": "Flag / banner"},
                    "sources": [{"reference": "project namesake gloss"}],
                    "uncertainty_notes": ["Bibliographic provenance is incomplete."],
                },
                "reason": None,
            }

    from app.services import performance_interpretation_service as service

    monkeypatch.setattr(service, "knowledge_service", KnowledgeStub())
    fusion, mudra, bhava = _analysis_inputs()
    package = build_analysis_observation_interpretation("analysis-a", fusion, mudra, bhava)

    del package["events"][0]["observations"]["mudra"]["verification_status"]
    with pytest.raises(PerformanceInterpretationValidationError, match="verification status"):
        validate_performance_interpretation(package)

    package["events"][0]["observations"]["mudra"]["verification_status"] = "partially_verified"
    package["events"][0]["observations"]["mudra"]["confidence"] = 0.4
    with pytest.raises(PerformanceInterpretationValidationError, match="confidence threshold"):
        validate_performance_interpretation(package)


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("claim_id", "forged-claim"),
        ("source_references", ["unrelated source"]),
    ],
)
def test_model_analysis_rejects_forged_claim_or_source_provenance(monkeypatch, field, forged_value):
    class KnowledgeStub:
        def retrieve_mudra(self, label):
            return {
                "status": "partially_verified",
                "claim": {
                    "claim_id": "claim-pataka",
                    "verification_status": "partially_verified",
                    "descriptions": {"en": "Flag / banner"},
                    "sources": [{"reference": "project namesake gloss"}],
                    "uncertainty_notes": ["Bibliographic provenance is incomplete."],
                },
                "reason": None,
            }

    from app.services import performance_interpretation_service as service

    monkeypatch.setattr(service, "knowledge_service", KnowledgeStub())
    fusion, mudra, bhava = _analysis_inputs()
    package = build_analysis_observation_interpretation("analysis-a", fusion, mudra, bhava)
    observation = package["events"][0]["observations"]["mudra"]
    observation[field] = forged_value

    with pytest.raises(PerformanceInterpretationValidationError, match="does not match"):
        validate_performance_interpretation(package)
