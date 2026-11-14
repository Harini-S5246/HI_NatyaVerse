"""Tests for the Phase 2 Pose evidence boundary."""
import pytest

from app.core.errors import AppError
from app.services import pose_event_service, semantic_event_service


ANALYSIS_ID = "2dcfa15a-42dc-4383-a270-5308de46ca14"


def _fusion():
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
            }
        ],
        "evidence": {"grounded": [], "detected": [], "unresolved": [], "interpreted": []},
    }


def test_pose_artifact_records_unavailable_movement(monkeypatch):
    monkeypatch.setattr(pose_event_service, "get_modality_result", lambda *_: _fusion())

    artifact = pose_event_service.compose_pose_events(ANALYSIS_ID)
    event = artifact["events"][0]

    assert artifact["status"] == "unavailable"
    assert artifact["supported_event_count"] == 0
    assert artifact["unknown_event_count"] == 1
    assert event["start_time"] == 10.2
    assert event["end_time"] == 16.8
    assert event["pose_evidence"] is None
    assert event["movement_evidence"] is None
    assert event["confidence"] is None
    assert event["evidence_ids"] == ["fusion-timeline-0001"]


def test_pose_artifact_rejects_other_analysis(monkeypatch):
    fusion = _fusion()
    fusion["analysis_id"] = "11111111-1111-1111-1111-111111111111"
    fusion["video_id"] = fusion["analysis_id"]
    monkeypatch.setattr(pose_event_service, "get_modality_result", lambda *_: fusion)

    with pytest.raises(AppError) as excinfo:
        pose_event_service.compose_pose_events(ANALYSIS_ID)

    assert excinfo.value.code == "ANALYSIS_ID_MISMATCH"


def test_semantic_composer_attaches_verified_pose_only(monkeypatch):
    fusion = _fusion()
    pose_artifact = {
        "analysis_id": ANALYSIS_ID,
        "video_id": ANALYSIS_ID,
        "events": [
            {
                "event_id": "pose_event_0001",
                "pose_evidence": {"label": "arm_extension"},
                "movement_evidence": {"label": "arm_extension"},
                "confidence": 0.91,
                "evidence_ids": ["pose-frame-0001"],
                "grounding_status": "grounded",
            }
        ],
    }

    def load(_analysis_id, modality):
        if modality == "fusion":
            return fusion
        if modality == "pose_events":
            return pose_artifact
        raise AppError("missing", 404, "MODALITY_RESULT_NOT_FOUND")

    monkeypatch.setattr(semantic_event_service, "get_modality_result", load)
    event = semantic_event_service.compose_semantic_events(ANALYSIS_ID)["events"][0]

    assert event["pose"]["movement_evidence"] == {"label": "arm_extension"}
    assert event["pose"]["evidence_ids"] == ["pose-frame-0001"]
    assert event["causal_relation"] is None