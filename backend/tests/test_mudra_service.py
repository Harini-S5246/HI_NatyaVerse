from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.api.schemas.mudra import MudraClassificationResponse
from app.config import settings as app_settings
from app.core.errors import AppError
from app.services import mudra_service


def test_group_mudra_events_groups_only_consecutive_labels():
    events = mudra_service.group_mudra_events([
        {"mudra": "Pataka", "timestamp": 0.0, "confidence": 0.8},
        {"mudra": "Pataka", "timestamp": 1.0, "confidence": 1.0},
        {"mudra": "Mayura", "timestamp": 2.0, "confidence": 0.7},
        {"mudra": "Pataka", "timestamp": 3.0, "confidence": 0.9},
    ])

    assert events == [
        {"mudra": "Pataka", "start_time": 0.0, "end_time": 1.0, "confidence": 0.9, "frame_count": 2},
        {"mudra": "Mayura", "start_time": 2.0, "end_time": 2.0, "confidence": 0.7, "frame_count": 1},
        {"mudra": "Pataka", "start_time": 3.0, "end_time": 3.0, "confidence": 0.9, "frame_count": 1},
    ]


def test_classification_requires_frame_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))

    with pytest.raises(AppError, match="Frame manifest was not found") as error:
        mudra_service.classify_video_frames("00000000-0000-0000-0000-000000000000")

    assert error.value.code == "FRAME_MANIFEST_NOT_FOUND"


def test_classification_returns_schema_valid_predictions(tmp_path, monkeypatch):
    video_id = "00000000-0000-0000-0000-000000000000"
    frame_dir = tmp_path / video_id
    frame_dir.mkdir()
    image = np.zeros((24, 24, 3), dtype=np.uint8)
    assert cv2.imwrite(str(frame_dir / "frame_000000.jpg"), image)
    assert cv2.imwrite(str(frame_dir / "frame_000001.jpg"), image)
    (frame_dir / "manifest.json").write_text(
        '{"video_id":"00000000-0000-0000-0000-000000000000","frame_count":2,"frames":['
        '{"frame_number":0,"timestamp":0.0,"filename":"frame_000000.jpg"},'
        '{"frame_number":1,"timestamp":1.0,"filename":"frame_000001.jpg"}'
        ']}',
        encoding="utf-8",
    )

    class StubMudraModel:
        def predict(self, frame):
            return {"label": "Pataka", "confidence": 0.95, "probabilities": {"Pataka": 0.95}}

    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))
    monkeypatch.setattr(mudra_service.model_manager, "get", lambda _: StubMudraModel())
    monkeypatch.setattr(mudra_service, "save_result", lambda _: None)
    monkeypatch.setattr(mudra_service, "save_modality_result", lambda *_: None)
    # Point the knowledge graph at the real curated knowledge file so Pataka grounds.
    monkeypatch.setattr(
        "app.services.knowledge_service.settings",
        SimpleNamespace(mudra_knowledge_path=app_settings.mudra_knowledge_path),
    )

    result = mudra_service.classify_video_frames(video_id)
    validated = MudraClassificationResponse.model_validate(result)

    assert validated.prediction_count == 2
    assert validated.summary.dominant_mudra == "Pataka"
    assert validated.mudra_events[0].frame_count == 2
    # New grounding fields must be present.
    assert validated.frames[0].grounded is True
    assert validated.frames[0].status == "grounded"
    assert validated.frames[0].meaning is not None
    assert validated.grounded_count >= 1
    assert validated.evidence is not None
    assert len(validated.evidence["grounded"]) >= 1
