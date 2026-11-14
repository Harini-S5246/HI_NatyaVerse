"""Tests for the Phase 1 provenance-preserving semantic event composer."""
import pytest

from app.core.errors import AppError
from app.services import semantic_event_service


ANALYSIS_ID = "2dcfa15a-42dc-4383-a270-5308de46ca14"


def _fusion_result():
    return {
        "analysis_id": ANALYSIS_ID,
        "video_id": ANALYSIS_ID,
        "status": "completed",
        "timeline": [
            {
                "start_time": 10.2,
                "end_time": 16.8,
                "mudra": "Alapadmam",
                "mudra_confidence": 0.70,
                "mudra_grounded": True,
                "bhava": "Neutral",
                "bhava_confidence": 0.368,
            },
            {
                "start_time": 16.8,
                "end_time": 18.0,
                "mudra": "Sikharam",
                "mudra_confidence": 0.12,
                "mudra_grounded": False,
                "bhava": "Neutral",
                "bhava_confidence": 0.368,
            },
        ],
        "evidence": {
            "grounded": [
                {
                    "id": "mudra-Alapadmam",
                    "label": "Alapadmam",
                    "detail": "Full-blown lotus",
                    "confidence": 0.70,
                    "knowledge_status": "partially_verified",
                    "verification_status": "partially_verified",
                    "claim_id": "claim-alapadmam",
                    "source_references": ["project namesake gloss"],
                    "uncertainty_notes": ["Bibliographic provenance is incomplete."],
                }
            ],
            "detected": [
                {
                    "id": "bhava-dominant",
                    "label": "Neutral bhava detected",
                    "confidence": 0.368,
                }
            ],
            "unresolved": [
                {
                    "id": "mudra-Sikharam",
                    "label": "Sikharam",
                    "detail": "Meaning unavailable in current knowledge base",
                    "confidence": 0.12,
                }
            ],
            "interpreted": [],
        },
    }


def test_composer_preserves_grounded_event_provenance(monkeypatch):
    monkeypatch.setattr(
        semantic_event_service,
        "get_modality_result",
        lambda *_: _fusion_result(),
    )

    artifact = semantic_event_service.compose_semantic_events(ANALYSIS_ID)
    grounded, unresolved = artifact["events"]

    assert artifact["analysis_id"] == artifact["video_id"] == ANALYSIS_ID
    assert grounded["start_time"] == 10.2
    assert grounded["end_time"] == 16.8
    assert grounded["duration"] == pytest.approx(6.6)
    assert grounded["mudra"] == {
        "label": "Alapadmam",
        "meaning": "Full-blown lotus",
        "confidence": 0.70,
        "grounding_status": "grounded",
        "knowledge_status": "partially_verified",
        "verification_status": "partially_verified",
        "claim_id": "claim-alapadmam",
        "source_references": ["project namesake gloss"],
        "uncertainty_notes": ["Bibliographic provenance is incomplete."],
        "evidence_ids": ["mudra-Alapadmam"],
    }
    assert grounded["semantic_grounding_status"] == "source_backed_mudra_knowledge"
    assert grounded["bhava"]["label"] == "Neutral"
    assert grounded["bhava"]["confidence"] == 0.368
    assert grounded["bhava"]["evidence_ids"] == ["fusion-timeline-0001"]
    assert grounded["evidence_ids"] == [
        "fusion-timeline-0001",
        "mudra-Alapadmam",
    ]
    assert grounded["action"] is None
    assert grounded["subject"] is None
    assert grounded["object"] is None
    assert grounded["location"] is None
    assert grounded["target"] is None
    assert grounded["pose"] is None
    assert grounded["audio"] is None
    assert grounded["causal_relation"] is None

    assert unresolved["mudra"]["label"] == "Sikharam"
    assert unresolved["mudra"]["meaning"] is None
    assert unresolved["mudra"]["grounding_status"] == "unresolved"
    assert unresolved["mudra"]["evidence_ids"] == ["mudra-Sikharam"]


def test_composer_adds_temporal_relation_without_causality(monkeypatch):
    monkeypatch.setattr(
        semantic_event_service,
        "get_modality_result",
        lambda *_: _fusion_result(),
    )

    events = semantic_event_service.compose_semantic_events(ANALYSIS_ID)["events"]

    assert events[0]["temporal_relation"] is None
    assert events[1]["temporal_relation"] == {
        "type": "after",
        "event_id": "event_0001",
        "evidence_ids": ["fusion-timeline-0002", "fusion-timeline-0001"],
    }
    assert all(event["causal_relation"] is None for event in events)


def test_cooccurring_facial_expression_does_not_create_mudra_bhava_relationship(monkeypatch):
    monkeypatch.setattr(
        semantic_event_service,
        "get_modality_result",
        lambda *_: _fusion_result(),
    )
    events = semantic_event_service.compose_semantic_events(ANALYSIS_ID)["events"]

    assert events[0]["mudra"]["verification_status"] == "partially_verified"
    assert events[0]["bhava"]["label"] == "Neutral"
    assert events[0]["semantic_grounding_status"] == "source_backed_mudra_knowledge"
    assert events[0]["causal_relation"] is None
    assert "bhava" not in events[0]["mudra"]


def test_composer_rejects_other_analysis_record(monkeypatch):
    fusion = _fusion_result()
    fusion["analysis_id"] = "11111111-1111-1111-1111-111111111111"
    fusion["video_id"] = fusion["analysis_id"]
    monkeypatch.setattr(
        semantic_event_service,
        "get_modality_result",
        lambda *_: fusion,
    )

    with pytest.raises(AppError) as excinfo:
        semantic_event_service.compose_semantic_events(ANALYSIS_ID)

    assert excinfo.value.code == "ANALYSIS_ID_MISMATCH"