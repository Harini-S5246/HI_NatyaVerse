import copy
import json
from pathlib import Path

import pytest

from app.services.narrative_evidence_service import (
    NarrativeEvidenceValidationError,
    can_generate_narrative_story,
    load_narrative_evidence,
    validate_narrative_evidence,
)

FIXTURE = Path(__file__).parents[1] / "app" / "data" / "knowledge" / "narrative" / "narrative_evidence.example.json"


def _record():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_valid_narrative_event_is_loaded_without_changes():
    record = _record()
    assert validate_narrative_evidence(record) is record


def test_event_without_provenance_is_rejected():
    record = _record()
    record["events"][0]["evidence"] = []
    with pytest.raises(NarrativeEvidenceValidationError, match="evidence"):
        validate_narrative_evidence(record)


def test_missing_character_verification_is_rejected():
    record = _record()
    del record["events"][0]["subject"]["verification_status"]
    with pytest.raises(NarrativeEvidenceValidationError, match="verification_status"):
        validate_narrative_evidence(record)


def test_causal_relation_without_causal_evidence_is_rejected():
    record = _record()
    record["events"][0]["causal_relation"] = {
        "label": "causes",
        "verification_status": "verified",
        "evidence": [],
    }
    with pytest.raises(NarrativeEvidenceValidationError, match="causal_relation.evidence"):
        validate_narrative_evidence(record)


def test_timestamp_ordering_is_enforced():
    record = _record()
    later = copy.deepcopy(record["events"][0])
    later["event_id"] = "synthetic-event-002"
    later["start_time"] = 3.0
    later["end_time"] = 4.0
    record["events"] = [later, record["events"][0]]
    with pytest.raises(NarrativeEvidenceValidationError, match="non-decreasing"):
        validate_narrative_evidence(record)


def test_unknown_fields_are_preserved_and_not_converted_to_claims():
    record = _record()
    event = validate_narrative_evidence(record)["events"][0]
    assert event["location"] == {"label": None, "verification_status": "unknown"}
    assert event["object"] == {"label": None, "verification_status": "unknown"}


def test_source_references_are_preserved(tmp_path):
    path = tmp_path / "record.json"
    path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    record = load_narrative_evidence(path)
    assert record["source_reference"] == "narrative_evidence.example.json"
    assert record["events"][0]["evidence"][0]["source_reference"] == "fixture annotation, event 1"


def test_synthetic_fixture_cannot_be_used_as_production_evidence():
    with pytest.raises(NarrativeEvidenceValidationError, match="not eligible"):
        load_narrative_evidence(FIXTURE, for_production=True)


def test_valid_pure_dance_record_with_no_narrative_events_is_blocked():
    record = _record()
    record["performance_mode"]["label"] = "pure_dance"
    record["events"] = []
    assert validate_narrative_evidence(record) is record
    assert can_generate_narrative_story(record) is False


def test_valid_narrative_dance_record_requires_and_accepts_verified_event():
    record = _record()
    assert record["performance_mode"]["label"] == "narrative_dance"
    assert can_generate_narrative_story(record) is True


def test_unknown_mode_blocks_story_generation_without_guessing():
    record = _record()
    record["performance_mode"]["label"] = "unknown"
    record["performance_mode"]["verification_status"] = "unknown"
    assert can_generate_narrative_story(record) is False


def test_invalid_performance_mode_verification_status_is_rejected():
    record = _record()
    record["performance_mode"]["verification_status"] = "unknown"
    with pytest.raises(NarrativeEvidenceValidationError, match="known performance_mode"):
        validate_narrative_evidence(record)


def test_performance_mode_missing_provenance_is_rejected():
    record = _record()
    del record["performance_mode"]["source_reference"]
    with pytest.raises(NarrativeEvidenceValidationError, match="source_reference"):
        validate_narrative_evidence(record)


def test_narrative_dance_without_verified_narrative_events_is_blocked():
    record = _record()
    record["events"] = []
    assert can_generate_narrative_story(record) is False


def test_unsupported_narrative_event_is_rejected():
    record = _record()
    record["events"][0]["action"] = {
        "label": "guesses",
        "verification_status": "unverified",
    }
    with pytest.raises(NarrativeEvidenceValidationError, match="unverified"):
        validate_narrative_evidence(record)
