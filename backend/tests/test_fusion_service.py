"""Tests for multimodal fusion and evidence consolidation."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.schemas.fusion import FusionResponse
from app.core.errors import AppError
from app.main import app
from app.services import fusion_service


client = TestClient(app)
VIDEO_ID = "00000000-0000-0000-0000-000000000000"


def _mudra_result(events=None, summary_override=None):
    """A plausible stored Mudra modality result."""
    if events is None:
        events = [
            {"mudra": "Pataka", "start_time": 0.0, "end_time": 2.0, "confidence": 0.9, "frame_count": 2},
            {"mudra": "Aralam", "start_time": 3.0, "end_time": 4.0, "confidence": 0.7, "frame_count": 1},
        ]
    summary = summary_override if summary_override is not None else {
        "dominant_mudra": "Pataka",
        "average_confidence": 0.85,
    }
    return {
        "analysis_id": VIDEO_ID,
        "frame_count": 5,
        "mudra_events": events,
        "summary": summary,
        "mudra": {
            "detections": [
                {
                    "name": "Pataka",
                    "confidence": 0.9,
                    "grounded": True,
                    "meaning": "Flag / banner",
                    "status": "grounded",
                    "timestamps": [0.0, 2.0],
                },
                {
                    "name": "Aralam",
                    "confidence": 0.7,
                    "grounded": False,
                    "meaning": None,
                    "status": "unresolved",
                    "timestamps": [3.0, 4.0],
                },
            ]
        },
        "evidence": {
            "grounded": [
                {"id": "mudra-Pataka", "label": "Pataka", "category": "grounded", "detail": "Flag / banner", "confidence": 0.9}
            ],
            "detected": [],
            "unresolved": [
                {"id": "mudra-Aralam", "label": "Aralam", "category": "unresolved", "confidence": 0.7}
            ],
            "interpreted": [],
        },
    }


def _bhava_result(events=None, summary_confidence=0.75):
    """Build a plausible stored Bhava modality result."""
    if events is None:
        events = [
            {"bhava": "Happy", "start_time": 0.0, "end_time": 2.0, "confidence": 0.85, "frame_count": 2},
            {"bhava": "Sad", "start_time": 2.0, "end_time": 4.0, "confidence": 0.75, "frame_count": 2},
        ]
    summary = {"dominant_bhava": "Happy", "average_confidence": summary_confidence}
    return {
        "event_id": VIDEO_ID,
        "frame_count": 5,
        "bhava_events": events,
        "summary": summary,
        "bhava": {
            "dominant_emotion": "Happy",
            "confidence": 0.85,
            "detections": [
                {"name": "Happy", "confidence": 0.85, "timestamps": [0.0, 2.0]},
                {"name": "Sad", "confidence": 0.75, "timestamps": [2.0, 4.0]},
            ],
            "segments": [
                {"label": "Happy", "start": 0.0, "end": 2.0, "confidence": 0.85},
                {"label": "Sad", "start": 2.0, "end": 4.0, "confidence": 0.75},
            ],
        },
        "evidence": {
            "grounded": [],
            "detected": [
                {"id": "bhava-dominant", "label": "Happy bhava detected", "category": "detected", "confidence": 0.85}
            ],
            "unresolved": [],
            "interpreted": [],
        },
    }


@pytest.fixture(autouse=True)
def _patch_persistence(monkeypatch):
    """Keep every test isolated from the real results directory."""
    monkeypatch.setattr(fusion_service, "save_result", lambda _: None)
    monkeypatch.setattr(fusion_service, "save_modality_result", lambda *_: None)


# ----------------------------------------------------------------------
# Missing results
# ----------------------------------------------------------------------

def test_fusion_requires_mudra_result(monkeypatch):
    def missing(*_):
        raise AppError("not found", 404, "MODALITY_RESULT_NOT_FOUND")

    monkeypatch.setattr(fusion_service, "get_modality_result", missing)

    with pytest.raises(AppError) as excinfo:
        fusion_service.fuse_video(VIDEO_ID)

    assert excinfo.value.code == "MUDRA_RESULT_REQUIRED"


def test_fusion_requires_bhava_result(monkeypatch):
    def getter(analysis_id, modality):
        if modality == "mudra":
            return _mudra_result()
        raise AppError("not found", 404, "MODALITY_RESULT_NOT_FOUND")

    monkeypatch.setattr(fusion_service, "get_modality_result", getter)

    with pytest.raises(AppError) as excinfo:
        fusion_service.fuse_video(VIDEO_ID)

    assert excinfo.value.code == "BHAVA_RESULT_REQUIRED"


# ----------------------------------------------------------------------
# Successful fusion + timestamp alignment
# ----------------------------------------------------------------------

def test_successful_fusion(monkeypatch):
    monkeypatch.setattr(
        fusion_service,
        "get_modality_result",
        lambda analysis_id, modality: _mudra_result() if modality == "mudra" else _bhava_result(),
    )

    result = fusion_service.fuse_video(VIDEO_ID)
    validated = FusionResponse.model_validate(result)

    assert validated.analysis_id == VIDEO_ID
    assert validated.status == "completed"
    assert validated.summary.dominant_mudra == "Pataka"
    assert validated.summary.dominant_bhava == "Happy"
    assert validated.summary.mudra_event_count == 2
    assert validated.summary.bhava_event_count == 2
    assert validated.summary.average_mudra_confidence == 0.85
    assert validated.summary.frame_count == 5


def test_timestamp_alignment(monkeypatch):
    monkeypatch.setattr(
        fusion_service,
        "get_modality_result",
        lambda analysis_id, modality: _mudra_result() if modality == "mudra" else _bhava_result(),
    )

    result = fusion_service.fuse_video(VIDEO_ID)
    timeline = result["timeline"]

    # The first row covers [0, 2] where Pataka (mudra) and Happy (bhava) co-occur.
    assert timeline[0]["mudra"] == "Pataka"
    assert timeline[0]["bhava"] == "Happy"
    assert timeline[0]["start_time"] == 0.0
    assert timeline[0]["end_time"] == 2.0

    # The second row covers [2, 3] where Pataka continues but Happy -> Sad.
    assert timeline[1]["mudra"] == "Pataka"
    assert timeline[1]["bhava"] == "Sad"
    assert timeline[1]["start_time"] == 2.0
    assert timeline[1]["end_time"] == 3.0

    # The third row covers [3, 4] where Aralam (mudra) and Sad (bhava) co-occur.
    assert timeline[2]["mudra"] == "Aralam"
    assert timeline[2]["bhava"] == "Sad"
    assert timeline[2]["start_time"] == 3.0
    assert timeline[2]["end_time"] == 4.0


# ----------------------------------------------------------------------
# Evidence preservation
# ----------------------------------------------------------------------

def test_preserves_grounded_mudra(monkeypatch):
    monkeypatch.setattr(
        fusion_service,
        "get_modality_result",
        lambda analysis_id, modality: _mudra_result() if modality == "mudra" else _bhava_result(),
    )

    result = fusion_service.fuse_video(VIDEO_ID)
    evidence = result["evidence"]

    assert any(item["id"] == "mudra-Pataka" for item in evidence["grounded"])
    grounded_pataka = next(item for item in evidence["grounded"] if item["id"] == "mudra-Pataka")
    assert grounded_pataka["category"] == "grounded"
    assert grounded_pataka["detail"] == "Flag / banner"


def test_preserves_unresolved_mudra(monkeypatch):
    monkeypatch.setattr(
        fusion_service,
        "get_modality_result",
        lambda analysis_id, modality: _mudra_result() if modality == "mudra" else _bhava_result(),
    )

    result = fusion_service.fuse_video(VIDEO_ID)
    evidence = result["evidence"]

    assert any(item["id"] == "mudra-Aralam" for item in evidence["unresolved"])
    unresolved = next(item for item in evidence["unresolved"] if item["id"] == "mudra-Aralam")
    assert unresolved["category"] == "unresolved"


def test_preserves_bhava_detected_evidence(monkeypatch):
    monkeypatch.setattr(
        fusion_service,
        "get_modality_result",
        lambda analysis_id, modality: _mudra_result() if modality == "mudra" else _bhava_result(),
    )

    result = fusion_service.fuse_video(VIDEO_ID)
    evidence = result["evidence"]

    assert any(item["id"] == "bhava-dominant" for item in evidence["detected"])
    detected = next(item for item in evidence["detected"] if item["id"] == "bhava-dominant")
    assert detected["category"] == "detected"
    assert detected["label"] == "Happy bhava detected"


def test_schema_compatibility(monkeypatch):
    monkeypatch.setattr(
        fusion_service,
        "get_modality_result",
        lambda analysis_id, modality: _mudra_result() if modality == "mudra" else _bhava_result(),
    )

    result = fusion_service.fuse_video(VIDEO_ID)
    validated = FusionResponse.model_validate(result)

    assert set(validated.evidence.keys()) == {"grounded", "detected", "unresolved", "interpreted"}
    for row in validated.timeline:
        assert "mudra" in row.model_dump()
        assert "bhava" in row.model_dump()
        assert "mudra_grounded" in row.model_dump()


# ----------------------------------------------------------------------
# No fabricated Mudra-Bhava relationship
# ----------------------------------------------------------------------

def test_no_fabricated_mudra_bhava_relationship(monkeypatch):
    monkeypatch.setattr(
        fusion_service,
        "get_modality_result",
        lambda analysis_id, modality: _mudra_result() if modality == "mudra" else _bhava_result(),
    )

    result = fusion_service.fuse_video(VIDEO_ID)
    relationship_fields = ["relationship", "mudra_means_bhava", "meaning_relation", "connection"]

    # The fusion layer must never emit a claim connecting a specific mudra to a specific bhava.
    for row in result["timeline"]:
        for field in relationship_fields:
            assert field not in row, f"Fusion must not invent field '{field}'"
    # Summary must not contain any cross-modal relationship claim.
    for field in relationship_fields:
        assert field not in result["summary"]


# ----------------------------------------------------------------------
# Empty results
# ----------------------------------------------------------------------

def test_fusion_empty_results(monkeypatch):
    empty_mudra = _mudra_result(events=[], summary_override={"dominant_mudra": None, "average_confidence": None})
    # With no events there are also no detections / no evidence.
    empty_mudra["mudra"] = {"detections": []}
    empty_mudra["evidence"] = {"grounded": [], "detected": [], "unresolved": [], "interpreted": []}
    empty_bhava = _bhava_result(events=[])
    empty_bhava["summary"] = {"dominant_bhava": None, "average_confidence": None}
    empty_bhava["bhava"] = {"dominant_emotion": None, "detections": [], "segments": []}
    empty_bhava["evidence"] = {"grounded": [], "detected": [], "unresolved": [], "interpreted": []}

    monkeypatch.setattr(
        fusion_service,
        "get_modality_result",
        lambda analysis_id, modality: empty_mudra if modality == "mudra" else empty_bhava,
    )

    result = fusion_service.fuse_video(VIDEO_ID)
    validated = FusionResponse.model_validate(result)

    assert validated.timeline == []
    assert validated.summary.dominant_mudra is None
    assert validated.summary.dominant_bhava is None
    assert validated.summary.mudra_event_count == 0
    assert validated.summary.bhava_event_count == 0
    assert validated.evidence == {
        "grounded": [],
        "detected": [],
        "unresolved": [],
        "interpreted": [],
    }


# ----------------------------------------------------------------------
# Endpoint
# ----------------------------------------------------------------------

def test_fusion_endpoint_reports_unknown_video():
    response = client.post(f"/api/videos/{VIDEO_ID}/fusion")
    assert response.status_code == 404
    assert response.json()["code"] == "VIDEO_NOT_FOUND"


def test_fusion_endpoint_returns_validated_schema():
    sample = {
        "analysis_id": VIDEO_ID,
        "status": "completed",
        "timeline": [
            {"start_time": 0.0, "end_time": 2.0, "mudra": "Pataka", "mudra_confidence": 0.9, "mudra_grounded": True, "bhava": "Happy", "bhava_confidence": 0.85}
        ],
        "summary": {
            "dominant_mudra": "Pataka",
            "dominant_bhava": "Happy",
            "mudra_event_count": 1,
            "bhava_event_count": 1,
            "average_mudra_confidence": 0.9,
            "average_bhava_confidence": 0.85,
            "frame_count": 5,
        },
        "evidence": {
            "grounded": [],
            "detected": [{"id": "bhava-dominant", "label": "Happy bhava detected", "category": "detected", "confidence": 0.85}],
            "unresolved": [],
            "interpreted": [],
        },
    }

    with (
        patch("app.api.routes.fusion.get_uploaded_video_path"),
        patch("app.api.routes.fusion.fuse_video", return_value=sample),
    ):
        response = client.post(f"/api/videos/{VIDEO_ID}/fusion")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["dominant_mudra"] == "Pataka"
    assert body["summary"]["dominant_bhava"] == "Happy"
    assert body["timeline"][0]["mudra"] == "Pataka"
    assert body["timeline"][0]["mudra_grounded"] is True
    assert "evidence" in body