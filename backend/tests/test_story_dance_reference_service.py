from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.errors import AppError
from app.services import result_service
from app.services import story_dance_reference_service as references


def _write_video_data(root: Path, video_id: str, predictions: list[dict]) -> None:
    frame_dir = root / "frames" / video_id
    result_dir = root / "results" / "modalities"
    frame_dir.mkdir(parents=True)
    result_dir.mkdir(parents=True)
    (root / "uploads" / f"{video_id}.mp4").parent.mkdir(parents=True, exist_ok=True)
    (root / "uploads" / f"{video_id}.mp4").write_bytes(b"existing upload")

    frames = [
        {
            "frame_number": prediction["frame_number"],
            "timestamp": prediction["timestamp"],
            "filename": prediction["filename"],
        }
        for prediction in predictions
    ]
    (frame_dir / "manifest.json").write_text(
        json.dumps({"video_id": video_id, "frame_count": len(frames), "frames": frames}),
        encoding="utf-8",
    )
    for frame in frames:
        (frame_dir / frame["filename"]).write_bytes(b"jpeg")
    (result_dir / f"{video_id}_mudra.json").write_text(
        json.dumps({
            "analysis_id": video_id,
            "video_id": video_id,
            "status": "completed",
            "frames": predictions,
        }),
        encoding="utf-8",
    )


@pytest.fixture
def reference_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    frame_root = tmp_path / "frames"
    result_root = tmp_path / "results"
    upload_root = tmp_path / "uploads"
    config = SimpleNamespace(
        frame_output_dir=frame_root,
        results_dir=result_root,
        upload_dir=upload_root,
        dance_reference_min_confidence=0.65,
        bhava_metadata_path=None,
    )
    monkeypatch.setattr(references, "settings", config)
    monkeypatch.setattr(references, "MUDRA_DATASET_ROOTS", ())
    monkeypatch.setattr(references, "BHAVA_DATASET_ROOT", tmp_path / "no-bhava-dataset")
    monkeypatch.setattr(result_service, "settings", config)

    def uploaded_video_path(video_id: str) -> Path:
        path = upload_root / f"{video_id}.mp4"
        if not path.is_file():
            raise AppError("Uploaded video was not found.", 404, "VIDEO_NOT_FOUND")
        return path

    monkeypatch.setattr(references, "get_uploaded_video_path", uploaded_video_path)
    return tmp_path


def test_reference_retrieval_uses_high_confidence_prediction_and_matching_manifest(
    reference_store: Path,
) -> None:
    video_id = "11111111-1111-4111-8111-111111111111"
    predictions = [
        {
            "frame_number": 2,
            "timestamp": 2.0,
            "filename": "frame_000002.jpg",
            "mudra": "Anjali",
            "confidence": 0.81,
        },
        {
            "frame_number": 8,
            "timestamp": 8.0,
            "filename": "frame_000008.jpg",
            "mudra": "Anjali",
            "confidence": 0.92,
        },
        {
            "frame_number": 9,
            "timestamp": 9.0,
            "filename": "frame_000009.jpg",
            "mudra": "Anjali",
            "confidence": 0.99,
        },
    ]
    _write_video_data(reference_store, video_id, predictions)
    manifest_path = reference_store / "frames" / video_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["frames"][-1]["timestamp"] = 10.0
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    response = references.get_scene_visual_references(
        references.SceneVisualReferencesRequest(
            scenes=[references.SceneVisualReferenceRequest(scene_id="scene-2", mudra_label="Anjali")]
        )
    )[0]

    assert response.confidence_threshold == 0.65
    assert response.mudra.status == "matched"
    assert response.mudra.predicted_label == "Anjali"
    assert response.mudra.confidence == 0.92
    assert response.mudra.video_id == video_id
    assert response.mudra.timestamp == 8.0
    assert response.mudra.image_url == (
        f"/api/videos/{video_id}/frames/frame_000008.jpg"
    )
    assert response.mudra.evidence_status == (
        "Saved model prediction; not ground truth or expert-verified."
    )
    assert response.bhava.status == "unavailable"
    assert response.pose.status == "unavailable"


def test_no_low_confidence_or_unmapped_reference_is_substituted(
    reference_store: Path,
) -> None:
    video_id = "22222222-2222-4222-8222-222222222222"
    _write_video_data(
        reference_store,
        video_id,
        [{
            "frame_number": 1,
            "timestamp": 1.0,
            "filename": "frame_000001.jpg",
            "mudra": "Shanka",
            "confidence": 0.64,
        }],
    )

    response = references.get_scene_visual_references(
        references.SceneVisualReferencesRequest(
            scenes=[
                references.SceneVisualReferenceRequest(
                    scene_id="scene-4",
                    mudra_label="Shanka",
                    bhava_label=None,
                    pose_label="Bhramari",
                )
            ]
        )
    )[0]

    assert response.mudra.status == "unavailable"
    assert "65%" in (response.mudra.unavailable_reason or "")
    assert response.mudra.image_url is None
    assert response.bhava.status == "unavailable"
    assert response.pose.status == "unavailable"
    assert "no classified pose evidence" in (response.pose.unavailable_reason or "")


def test_mudra_reference_uses_original_frame_without_claiming_an_unverified_crop(
    reference_store: Path,
) -> None:
    video_id = "33333333-3333-4333-8333-333333333333"
    prediction = {
        "frame_number": 4,
        "timestamp": 4.0,
        "filename": "frame_000004.jpg",
        "mudra": "Alapadmam",
        "confidence": 0.9,
    }
    _write_video_data(reference_store, video_id, [prediction])
    frame_path = reference_store / "frames" / video_id / prediction["filename"]
    cv2 = pytest.importorskip("cv2")
    import numpy as np

    cv2.imwrite(str(frame_path), np.full((300, 400, 3), 127, dtype=np.uint8))
    original_bytes = frame_path.read_bytes()

    response = references.get_scene_visual_references(
        references.SceneVisualReferencesRequest(
            scenes=[references.SceneVisualReferenceRequest(scene_id="scene-1", mudra_label="Alapadmam")]
        )
    )[0]
    assert response.mudra.status == "matched"
    assert response.mudra.crop_status == "full_source_frame_no_hand_landmarks"
    assert response.mudra.image_url == (
        f"/api/videos/{video_id}/frames/frame_000004.jpg"
    )
    assert frame_path.read_bytes() == original_bytes
    assert response.mudra.original_frame_url == (
        f"/api/videos/{video_id}/frames/frame_000004.jpg"
    )


def test_mudra_dataset_fallback_selects_distinct_labelled_examples(
    reference_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_root = reference_store / "Mudra_Dataset"
    class_dir = dataset_root / "Alapadmam"
    class_dir.mkdir(parents=True)
    (class_dir / "sample-a.jpg").write_bytes(b"labelled example a")
    (class_dir / "sample-b.jpg").write_bytes(b"labelled example b")
    monkeypatch.setattr(references, "MUDRA_DATASET_ROOTS", (dataset_root,))

    responses = references.get_scene_visual_references(
        references.SceneVisualReferencesRequest(
            scenes=[
                references.SceneVisualReferenceRequest(
                    scene_id="scene-1",
                    mudra_label="Alapadmam",
                ),
                references.SceneVisualReferenceRequest(
                    scene_id="scene-2",
                    mudra_label="Alapadmam",
                ),
            ]
        )
    )

    first, second = [response.mudra for response in responses]
    assert first.source_type == "project_dataset"
    assert first.reference_status == "dataset_labelled"
    assert first.dataset_label == "Alapadmam"
    assert first.dataset_name == "Mudra_Dataset"
    assert first.dataset_relative_path.startswith(
        "Natya_dataset/Mudra_Dataset/Alapadmam/"
    )
    assert first.asset_id != second.asset_id
    assert first.image_url == (
        f"/api/story-to-dance/stories/reference-assets/{first.asset_id}"
    )
    assert first.video_id is None
    assert first.confidence is None


def test_bhava_dataset_uses_explicit_model_class_order_for_numeric_folder_ids(
    reference_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_root = reference_store / "Bhava_Dataset"
    image_path = dataset_root / "train" / "3" / "example.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"mapped dataset image")
    metadata_path = reference_store / "bhava_model_metadata.json"
    metadata_path.write_text(
        json.dumps({
            "classes": [
                "Angry",
                "Disgust",
                "Fear",
                "Happy",
                "Sad",
                "Surprise",
                "Neutral",
            ]
        }),
        encoding="utf-8",
    )
    reference_config = references.settings
    reference_config.bhava_metadata_path = metadata_path
    monkeypatch.setattr(references, "BHAVA_DATASET_ROOT", dataset_root)

    response = references.get_scene_visual_references(
        references.SceneVisualReferencesRequest(
            scenes=[
                references.SceneVisualReferenceRequest(
                    scene_id="scene-happy",
                    bhava_label="Happy",
                )
            ]
        )
    )[0]

    assert response.bhava.status == "matched"
    assert response.bhava.source_type == "project_dataset"
    assert response.bhava.reference_status == "dataset_labelled"
    assert response.bhava.dataset_label == "Happy"
    assert response.bhava.dataset_relative_path.endswith("/train/3/example.jpg")
    assert "not a Bharatanatyam-specific" in response.bhava.evidence_status


def test_dataset_asset_lookup_rejects_unknown_or_malformed_ids(
    reference_store: Path,
) -> None:
    with pytest.raises(AppError) as malformed:
        references.get_dataset_reference_asset_path("../arbitrary-file")
    assert malformed.value.status_code == 400

    with pytest.raises(AppError) as unknown:
        references.get_dataset_reference_asset_path("0" * 64)
    assert unknown.value.status_code == 404


def test_dataset_reference_route_serves_indexed_image(
    reference_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    from fastapi.testclient import TestClient

    from app.main import app

    dataset_root = reference_store / "Mudra_Dataset"
    class_dir = dataset_root / "Shanka"
    class_dir.mkdir(parents=True)
    image_path = class_dir / "sample.jpg"
    assert cv2.imwrite(str(image_path), np.full((32, 32, 3), 127, dtype=np.uint8))
    monkeypatch.setattr(references, "MUDRA_DATASET_ROOTS", (dataset_root,))
    asset_id = next(iter(references._known_dataset_assets()))

    response = TestClient(app).get(
        f"/api/story-to-dance/stories/reference-assets/{asset_id}"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content.startswith(b"\xff\xd8")
