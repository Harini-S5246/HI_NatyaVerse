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


def test_temporal_sequence_tracks_segmentation_and_transitions():
    sequence = mudra_service._build_temporal_sequence([
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 0, "confidence": 0.92},
        {"mudra": "Pataka", "timestamp": 1.0, "frame_number": 1, "confidence": 0.88},
        {"mudra": "Mayura", "timestamp": 2.0, "frame_number": 2, "confidence": 0.71},
        {"mudra": "Mayura", "timestamp": 3.0, "frame_number": 3, "confidence": 0.69},
    ], video_id="11111111-1111-4111-8111-111111111111", analysis_id="11111111-1111-4111-8111-111111111111")

    assert sequence["video_id"] == "11111111-1111-4111-8111-111111111111"
    assert [segment["mudra_label"] for segment in sequence["segments"]] == ["Pataka", "Mayura"]
    assert sequence["segments"][0]["duration"] == 1.0
    assert sequence["segments"][0]["frame_indices"] == [0, 1]
    assert sequence["transitions"][0]["previous_mudra"] == "Pataka"
    assert sequence["transitions"][0]["next_mudra"] == "Mayura"
    assert sequence["segments"][1]["transition"]["previous_mudra"] == "Pataka"


def test_temporal_sequence_orders_out_of_order_timestamps_and_preserves_evidence():
    sequence = mudra_service._build_temporal_sequence([
        {"mudra": "Mayura", "timestamp": 3.0, "frame_number": 3, "confidence": 0.74},
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 0, "confidence": 0.92},
        {"mudra": "Mayura", "timestamp": 2.0, "frame_number": 2, "confidence": 0.71},
        {"mudra": "Pataka", "timestamp": 1.0, "frame_number": 1, "confidence": 0.88},
    ], video_id="22222222-2222-4222-8222-222222222222", analysis_id="22222222-2222-4222-8222-222222222222")

    assert [segment["mudra_label"] for segment in sequence["segments"]] == ["Pataka", "Mayura"]
    assert sequence["segments"][0]["frame_indices"] == [0, 1]
    assert sequence["segments"][1]["frame_indices"] == [2, 3]
    assert sequence["segments"][0]["supporting_evidence_ids"] == [
        "22222222-2222-4222-8222-222222222222-frame-0",
        "22222222-2222-4222-8222-222222222222-frame-1",
    ]
    assert sequence["segments"][1]["supporting_evidence_ids"] == [
        "22222222-2222-4222-8222-222222222222-frame-2",
        "22222222-2222-4222-8222-222222222222-frame-3",
    ]
    assert sequence["segments"][0]["duration"] == 1.0
    assert sequence["segments"][1]["duration"] == 1.0


def test_temporal_sequence_handles_duplicate_timestamps_without_negative_duration():
    sequence = mudra_service._build_temporal_sequence([
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 0, "confidence": 0.90},
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 1, "confidence": 0.81},
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 2, "confidence": 0.85},
        {"mudra": "Mayura", "timestamp": 1.0, "frame_number": 3, "confidence": 0.70},
    ], video_id="22222222-2222-4222-8222-222222222223", analysis_id="22222222-2222-4222-8222-222222222223")

    assert len(sequence["segments"]) == 2
    assert sequence["segments"][0]["mudra_label"] == "Pataka"
    assert sequence["segments"][0]["duration"] == 0.0
    assert sequence["segments"][0]["frame_indices"] == [0, 1, 2]
    assert sequence["segments"][1]["duration"] == 0.0


def test_temporal_sequence_splits_on_large_timestamp_gap():
    sequence = mudra_service._build_temporal_sequence([
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 0, "confidence": 0.90},
        {"mudra": "Pataka", "timestamp": 0.5, "frame_number": 1, "confidence": 0.88},
        {"mudra": "Pataka", "timestamp": 2.0, "frame_number": 2, "confidence": 0.91},
    ], video_id="22222222-2222-4222-8222-222222222224", analysis_id="22222222-2222-4222-8222-222222222224")

    assert [segment["mudra_label"] for segment in sequence["segments"]] == ["Pataka", "Pataka"]
    assert sequence["segments"][0]["duration"] == 0.5
    assert sequence["segments"][1]["duration"] == 0.0
    assert sequence["segments"][0]["end_timestamp"] == 0.5
    assert sequence["segments"][1]["start_timestamp"] == 2.0


def test_temporal_sequence_detects_repeated_patterns_and_low_confidence():
    sequence = mudra_service._build_temporal_sequence([
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 0, "confidence": 0.42},
        {"mudra": "Mayura", "timestamp": 1.0, "frame_number": 1, "confidence": 0.66},
        {"mudra": "Pataka", "timestamp": 2.0, "frame_number": 2, "confidence": 0.71},
        {"mudra": "Mayura", "timestamp": 3.0, "frame_number": 3, "confidence": 0.69},
    ], video_id="22222222-2222-4222-8222-222222222222", analysis_id="22222222-2222-4222-8222-222222222222")

    assert [segment["mudra_label"] for segment in sequence["segments"]] == ["Pataka", "Mayura", "Pataka", "Mayura"]
    assert sequence["segments"][0]["uncertainty_status"] == "low_confidence"
    assert sequence["repeated_patterns"][0]["pattern"] == ["Pataka", "Mayura"]
    assert sequence["repeated_patterns"][0]["meaning_inferred"] is False


def test_temporal_sequence_handles_missing_predictions_and_timestamps():
    sequence = mudra_service._build_temporal_sequence([
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 0, "confidence": 0.91},
        {"mudra": "", "timestamp": 1.0, "frame_number": 1, "confidence": 0.90},
        {"mudra": "Pataka", "timestamp": 5.0, "frame_number": 2, "confidence": 0.92},
        {"mudra": "Mayura", "timestamp": 9.0, "frame_number": 3, "confidence": 0.77},
    ], video_id="33333333-3333-4333-8333-333333333333", analysis_id="33333333-3333-4333-8333-333333333333")

    assert [segment["mudra_label"] for segment in sequence["segments"]] == ["Pataka", "Pataka", "Mayura"]
    assert sequence["transitions"][0]["previous_mudra"] == "Pataka"
    assert sequence["uncertainty_summary"]["missing_prediction_count"] == 1


def test_temporal_sequence_rejects_invalid_timestamps_and_empty_input():
    empty = mudra_service._build_temporal_sequence([], video_id="44444444-4444-4444-8444-444444444444", analysis_id="44444444-4444-4444-8444-444444444444")
    invalid = mudra_service._build_temporal_sequence([
        {"mudra": "Pataka", "timestamp": "bad", "frame_number": 0, "confidence": 0.8},
        {"mudra": "Mayura", "timestamp": -1.0, "frame_number": 1, "confidence": 0.7},
    ], video_id="44444444-4444-4444-8444-444444444444", analysis_id="44444444-4444-4444-8444-444444444444")

    assert empty["segments"] == []
    assert invalid["segments"] == []


def test_temporal_sequence_preserves_video_and_analysis_boundaries():
    first = mudra_service._build_temporal_sequence([
        {"mudra": "Pataka", "timestamp": 0.0, "frame_number": 0, "confidence": 0.8},
        {"mudra": "Pataka", "timestamp": 0.5, "frame_number": 1, "confidence": 0.8},
    ], video_id="55555555-5555-4555-8555-555555555555", analysis_id="55555555-5555-4555-8555-555555555555")
    second = mudra_service._build_temporal_sequence([
        {"mudra": "Mayura", "timestamp": 0.0, "frame_number": 0, "confidence": 0.7},
    ], video_id="66666666-6666-4666-8666-666666666666", analysis_id="66666666-6666-4666-8666-666666666666")

    assert first["video_id"] != second["video_id"]
    assert first["analysis_id"] != second["analysis_id"]
    assert first["segments"][0]["supporting_evidence_ids"][0].startswith(first["analysis_id"])
    assert second["segments"][0]["supporting_evidence_ids"][0].startswith(second["analysis_id"])


def test_classification_requires_frame_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(mudra_service, "settings", SimpleNamespace(frame_output_dir=tmp_path))

    with pytest.raises(AppError, match="Frame manifest was not found") as error:
        mudra_service.classify_video_frames("00000000-0000-0000-0000-000000000000")

    assert error.value.code == "FRAME_MANIFEST_NOT_FOUND"


@pytest.mark.parametrize(("confidence", "expected_grounded"), [(0.95, True), (0.4, False)])
def test_classification_returns_schema_valid_predictions(
    tmp_path, monkeypatch, confidence, expected_grounded
):
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
            return {"label": "Pataka", "confidence": confidence, "probabilities": {"Pataka": confidence}}

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
    assert validated.frames[0].grounded is expected_grounded
    assert validated.frames[0].status == ("grounded" if expected_grounded else "unresolved")
    assert (validated.frames[0].meaning is not None) is expected_grounded
    assert validated.frames[0].verification_status == (
        "partially_verified" if expected_grounded else None
    )
    assert bool(validated.frames[0].source_references) is expected_grounded
    assert bool(validated.frames[0].uncertainty_notes) is expected_grounded
    assert (validated.grounded_count >= 1) is expected_grounded
    assert validated.evidence is not None
    assert bool(validated.evidence["grounded"]) is expected_grounded
