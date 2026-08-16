"""Tests for Bhava temporal analysis over stored extracted frames."""
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.schemas.bhava import BhavaClassificationResponse
from app.core.errors import AppError
from app.main import app
from app.services import bhava_service, mudra_service


client = TestClient(app)
VIDEO_ID = "00000000-0000-0000-0000-000000000000"


def _write_manifest(frame_dir, entries, video_id=VIDEO_ID):
    manifest = {
        "video_id": video_id,
        "frame_count": len(entries),
        "frames": entries,
    }
    (frame_dir / "manifest.json").write_text(
        __import__("json").dumps(manifest),
        encoding="utf-8",
    )


def _write_image(path):
    image = np.zeros((24, 24, 3), dtype=np.uint8)
    assert cv2.imwrite(str(path), image)


class StubBhavaModel:
    """Returns a fixed label per call. ``labels`` list cycles for multi-frame tests."""

    def __init__(self, labels):
        self.labels = labels
        self.index = 0

    def predict(self, frame):
        label = self.labels[self.index % len(self.labels)]
        self.index += 1
        return {"label": label, "confidence": 0.85, "probabilities": {label: 0.85}}


# ----------------------------------------------------------------------
# Event grouping (pure function)
# ----------------------------------------------------------------------

def test_group_bhava_events_groups_only_consecutive_labels():
    events = bhava_service.group_bhava_events([
        {"bhava": "Happy", "timestamp": 0.0, "confidence": 0.8},
        {"bhava": "Happy", "timestamp": 1.0, "confidence": 1.0},
        {"bhava": "Sad", "timestamp": 2.0, "confidence": 0.7},
        {"bhava": "Happy", "timestamp": 3.0, "confidence": 0.9},
    ])

    assert events == [
        {"bhava": "Happy", "start_time": 0.0, "end_time": 1.0, "confidence": 0.9, "frame_count": 2},
        {"bhava": "Sad", "start_time": 2.0, "end_time": 2.0, "confidence": 0.7, "frame_count": 1},
        {"bhava": "Happy", "start_time": 3.0, "end_time": 3.0, "confidence": 0.9, "frame_count": 1},
    ]


# ----------------------------------------------------------------------
# Manifest / frame error paths
# ----------------------------------------------------------------------

def test_classification_requires_frame_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))

    with pytest.raises(AppError, match="Frame manifest was not found") as error:
        bhava_service.classify_video_bhava(VIDEO_ID)

    assert error.value.code == "FRAME_MANIFEST_NOT_FOUND"


def test_classification_rejects_malformed_manifest(tmp_path, monkeypatch):
    frame_dir = tmp_path / VIDEO_ID
    frame_dir.mkdir()
    (frame_dir / "manifest.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))

    with pytest.raises(AppError, match="Frame manifest could not be read") as error:
        bhava_service.classify_video_bhava(VIDEO_ID)

    assert error.value.code == "INVALID_FRAME_MANIFEST"


def test_classification_rejects_non_object_manifest(tmp_path, monkeypatch):
    frame_dir = tmp_path / VIDEO_ID
    frame_dir.mkdir()
    (frame_dir / "manifest.json").write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))

    with pytest.raises(AppError, match="Frame manifest is invalid") as error:
        bhava_service.classify_video_bhava(VIDEO_ID)

    assert error.value.code == "INVALID_FRAME_MANIFEST"


def test_classification_reports_missing_frame(tmp_path, monkeypatch):
    frame_dir = tmp_path / VIDEO_ID
    frame_dir.mkdir()
    # Manifest references a frame that was never written.
    _write_manifest(frame_dir, [{"frame_number": 0, "timestamp": 0.0, "filename": "frame_000000.jpg"}])
    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))
    monkeypatch.setattr(bhava_service.model_manager, "get", lambda _: StubBhavaModel(["Happy"]))

    with pytest.raises(AppError, match="Extracted frame is missing") as error:
        bhava_service.classify_video_bhava(VIDEO_ID)

    assert error.value.code == "FRAME_NOT_FOUND"


def test_classification_reports_unreadable_frame(tmp_path, monkeypatch):
    frame_dir = tmp_path / VIDEO_ID
    frame_dir.mkdir()
    _write_manifest(frame_dir, [{"frame_number": 0, "timestamp": 0.0, "filename": "frame_000000.jpg"}])
    # A text file with a .jpg extension cannot be decoded by cv2.imread.
    (frame_dir / "frame_000000.jpg").write_text("this is not an image", encoding="utf-8")
    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))
    monkeypatch.setattr(bhava_service.model_manager, "get", lambda _: StubBhavaModel(["Happy"]))

    with pytest.raises(AppError, match="not a valid image") as error:
        bhava_service.classify_video_bhava(VIDEO_ID)

    assert error.value.code == "INVALID_FRAME"


# ----------------------------------------------------------------------
# Successful classification
# ----------------------------------------------------------------------

def test_classification_returns_schema_valid_predictions(tmp_path, monkeypatch):
    frame_dir = tmp_path / VIDEO_ID
    frame_dir.mkdir()
    entries = [
        {"frame_number": 0, "timestamp": 0.0, "filename": "frame_000000.jpg"},
        {"frame_number": 1, "timestamp": 1.0, "filename": "frame_000001.jpg"},
        {"frame_number": 2, "timestamp": 2.0, "filename": "frame_000002.jpg"},
    ]
    _write_manifest(frame_dir, entries)
    for entry in entries:
        _write_image(frame_dir / entry["filename"])

    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))
    monkeypatch.setattr(bhava_service.model_manager, "get", lambda _: StubBhavaModel(["Happy"]))
    monkeypatch.setattr(bhava_service, "save_result", lambda _: None)
    monkeypatch.setattr(bhava_service, "save_modality_result", lambda *_: None)

    result = bhava_service.classify_video_bhava(VIDEO_ID)
    validated = BhavaClassificationResponse.model_validate(result)

    assert validated.prediction_count == 3
    assert validated.summary.dominant_bhava == "Happy"
    assert validated.summary.unique_bhava_count == 1
    assert validated.bhava_events[0].frame_count == 3
    assert validated.bhava["dominant_emotion"] == "Happy"
    assert len(validated.bhava["segments"]) == 1


def test_classification_builds_separate_identical_events(tmp_path, monkeypatch):
    frame_dir = tmp_path / VIDEO_ID
    frame_dir.mkdir()
    entries = [
        {"frame_number": 0, "timestamp": 0.0, "filename": "frame_000000.jpg"},
        {"frame_number": 1, "timestamp": 1.0, "filename": "frame_000001.jpg"},
        {"frame_number": 2, "timestamp": 2.0, "filename": "frame_000002.jpg"},
        {"frame_number": 3, "timestamp": 3.0, "filename": "frame_000003.jpg"},
    ]
    _write_manifest(frame_dir, entries)
    for entry in entries:
        _write_image(frame_dir / entry["filename"])

    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))
    # Happy, Sad, Happy -> identical labels separated by a different label stay separate.
    monkeypatch.setattr(bhava_service.model_manager, "get", lambda _: StubBhavaModel(["Happy", "Sad", "Happy", "Sad"]))
    monkeypatch.setattr(bhava_service, "save_result", lambda _: None)
    monkeypatch.setattr(bhava_service, "save_modality_result", lambda *_: None)

    result = bhava_service.classify_video_bhava(VIDEO_ID)
    validated = BhavaClassificationResponse.model_validate(result)

    assert len(validated.bhava_events) == 4
    assert validated.bhava_events[0].bhava == "Happy"
    assert validated.bhava_events[0].frame_count == 1
    assert validated.bhava_events[2].bhava == "Happy"
    assert validated.bhava_events[2].start_time == 2.0
    assert validated.summary.unique_bhava_count == 2
    assert validated.summary.dominant_bhava == "Happy"


def test_classification_evidence_detected_integration(tmp_path, monkeypatch):
    frame_dir = tmp_path / VIDEO_ID
    frame_dir.mkdir()
    entries = [
        {"frame_number": 0, "timestamp": 0.0, "filename": "frame_000000.jpg"},
        {"frame_number": 1, "timestamp": 1.0, "filename": "frame_000001.jpg"},
    ]
    _write_manifest(frame_dir, entries)
    for entry in entries:
        _write_image(frame_dir / entry["filename"])

    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))
    monkeypatch.setattr(bhava_service.model_manager, "get", lambda _: StubBhavaModel(["Happy"]))
    monkeypatch.setattr(bhava_service, "save_result", lambda _: None)
    monkeypatch.setattr(bhava_service, "save_modality_result", lambda *_: None)

    result = bhava_service.classify_video_bhava(VIDEO_ID)
    validated = BhavaClassificationResponse.model_validate(result)

    assert validated.evidence is not None
    assert any(
        item["label"] == "Happy bhava detected" and item["category"] == "detected"
        for item in validated.evidence["detected"]
    )
    # Bhava must never be grounded in the evidence via this module.
    assert len(validated.evidence["grounded"]) == 0


# ----------------------------------------------------------------------
# Endpoint
# ----------------------------------------------------------------------

def test_bhava_endpoint_reports_unknown_video():
    response = client.post(f"/api/videos/{VIDEO_ID}/bhavas")
    assert response.status_code == 404
    assert response.json()["code"] == "VIDEO_NOT_FOUND"


def test_bhava_endpoint_returns_validated_schema():
    sample = {
        "analysis_id": VIDEO_ID,
        "video_id": VIDEO_ID,
        "status": "completed",
        "frame_count": 2,
        "prediction_count": 2,
        "bhava_events": [
            {"bhava": "Happy", "start_time": 0.0, "end_time": 1.0, "confidence": 0.9, "frame_count": 2}
        ],
        "frames": [
            {"frame_number": 0, "timestamp": 0.0, "filename": "frame_000000.jpg", "bhava": "Happy", "confidence": 0.9},
            {"frame_number": 1, "timestamp": 1.0, "filename": "frame_000001.jpg", "bhava": "Happy", "confidence": 0.9},
        ],
        "summary": {"unique_bhava_count": 1, "dominant_bhava": "Happy", "average_confidence": 0.9},
        "bhava": {
            "dominant_emotion": "Happy",
            "confidence": 0.9,
            "detections": [],
            "segments": [
                {"label": "Happy", "start": 0.0, "end": 1.0, "confidence": 0.9}
            ],
        },
        "evidence": {
            "grounded": [],
            "detected": [
                {"id": "bhava-dominant", "label": "Happy bhava detected", "category": "detected", "confidence": 0.9}
            ],
            "unresolved": [],
            "interpreted": [],
        },
    }

    with (
        patch("app.api.routes.bhavas.get_uploaded_video_path"),
        patch("app.api.routes.bhavas.classify_video_bhava", return_value=sample),
    ):
        response = client.post(f"/api/videos/{VIDEO_ID}/bhavas")

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["dominant_bhava"] == "Happy"
    assert body["bhava"]["dominant_emotion"] == "Happy"
    assert body["evidence"]["detected"][0]["label"] == "Happy bhava detected"
    assert "bhava_events" in body
    assert "frames" in body