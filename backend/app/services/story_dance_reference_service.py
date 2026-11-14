"""Read-only retrieval of analyzed Dance-to-Story frame references."""
from __future__ import annotations

import logging
import hashlib
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.config import settings
from app.core.errors import AppError
from app.services.result_service import modality_result_path
from app.services.upload_service import get_uploaded_video_path
from app.utils.json_utils import load_json

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MUDRA_DATASET_ROOTS = (
    PROJECT_ROOT / "Natya_dataset" / "Mudra_Dataset",
    PROJECT_ROOT / "Natya_dataset" / "Merged_Dataset",
)
BHAVA_DATASET_ROOT = PROJECT_ROOT / "Natya_dataset" / "Bhava_Dataset"


class SceneVisualReferenceRequest(BaseModel):
    scene_id: str = Field(min_length=1, max_length=128)
    mudra_label: str | None = Field(default=None, max_length=128)
    bhava_label: str | None = Field(default=None, max_length=128)
    pose_label: str | None = Field(default=None, max_length=128)


class SceneVisualReferencesRequest(BaseModel):
    scenes: list[SceneVisualReferenceRequest] = Field(min_length=1, max_length=100)


class VisualReference(BaseModel):
    category: Literal["mudra", "bhava", "pose"]
    status: Literal["matched", "unavailable"]
    source_type: Literal["analyzed_video", "project_dataset", "unavailable"] = "unavailable"
    reference_status: Literal[
        "model_predicted", "dataset_labelled", "expert_verified", "unavailable"
    ] = "unavailable"
    concept: str | None = None
    predicted_label: str | None = None
    dataset_label: str | None = None
    confidence: float | None = None
    confidence_threshold: float
    video_id: str | None = None
    frame_number: int | None = None
    timestamp: float | None = None
    frame_filename: str | None = None
    image_url: str | None = None
    original_frame_url: str | None = None
    asset_id: str | None = None
    dataset_name: str | None = None
    dataset_relative_path: str | None = None
    evidence_status: str
    crop_status: str
    unavailable_reason: str | None = None
    reused_in_scenes: list[str] = Field(default_factory=list)


DatasetAsset = tuple[str, str, Path, str]


@lru_cache(maxsize=2)
def _dataset_asset_index(roots: tuple[str, ...]) -> dict[str, DatasetAsset]:
    assets: dict[str, DatasetAsset] = {}
    allowed_extensions = {".jpg", ".jpeg", ".png"}
    for root_name in roots:
        root = Path(root_name)
        if not root.is_dir():
            continue
        resolved_root = root.resolve()
        dataset_name = root.name
        for class_dir in sorted(root.iterdir()):
            if not class_dir.is_dir():
                continue
            for image_path in sorted(class_dir.iterdir()):
                if image_path.suffix.casefold() not in allowed_extensions or not image_path.is_file():
                    continue
                try:
                    resolved_path = image_path.resolve()
                    relative_to_dataset = resolved_path.relative_to(resolved_root)
                except (OSError, ValueError):
                    logger.warning("Skipping a Mudra dataset image outside its class directory: %s", image_path)
                    continue
                relative_path = Path("Natya_dataset") / dataset_name / relative_to_dataset
                relative_path_text = relative_path.as_posix()
                asset_id = hashlib.sha256(relative_path_text.encode("utf-8")).hexdigest()
                assets[asset_id] = (
                    dataset_name,
                    class_dir.name,
                    resolved_path,
                    relative_path_text,
                )
    return assets


def _known_dataset_assets() -> dict[str, DatasetAsset]:
    assets = _dataset_asset_index(tuple(str(root) for root in MUDRA_DATASET_ROOTS))
    assets.update(_bhava_dataset_asset_index(
        str(BHAVA_DATASET_ROOT),
        str(settings.bhava_metadata_path or ""),
    ))
    return assets


@lru_cache(maxsize=2)
def _bhava_dataset_asset_index(
    root_name: str,
    metadata_name: str,
) -> dict[str, DatasetAsset]:
    root = Path(root_name)
    metadata_path = Path(metadata_name) if metadata_name else None
    metadata = _read_json(metadata_path) if metadata_path is not None else None
    classes = metadata.get("classes") if metadata else None
    if (
        not root.is_dir()
        or metadata is None
        or not isinstance(classes, list)
        or not all(isinstance(label, str) and label for label in classes)
    ):
        return {}

    assets: dict[str, DatasetAsset] = {}
    resolved_root = root.resolve()
    allowed_extensions = {".jpg", ".jpeg", ".png"}
    for split_dir in sorted(root.iterdir()):
        if not split_dir.is_dir() or split_dir.name.casefold() not in {"train", "test", "valid", "val"}:
            continue
        for class_dir in sorted(split_dir.iterdir()):
            if not class_dir.is_dir() or not class_dir.name.isdecimal():
                continue
            class_index = int(class_dir.name)
            if class_index < 0 or class_index >= len(classes):
                continue
            dataset_label = classes[class_index]
            for image_path in sorted(class_dir.iterdir()):
                if image_path.suffix.casefold() not in allowed_extensions or not image_path.is_file():
                    continue
                try:
                    resolved_path = image_path.resolve()
                    relative_to_dataset = resolved_path.relative_to(resolved_root)
                except (OSError, ValueError):
                    logger.warning("Skipping a Bhava dataset image outside its split directory: %s", image_path)
                    continue
                relative_path = Path("Natya_dataset") / root.name / relative_to_dataset
                relative_path_text = relative_path.as_posix()
                asset_id = hashlib.sha256(relative_path_text.encode("utf-8")).hexdigest()
                assets[asset_id] = (
                    root.name,
                    dataset_label,
                    resolved_path,
                    relative_path_text,
                )
    return assets


def get_dataset_reference_asset_path(asset_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", asset_id):
        raise AppError("Invalid reference asset ID.", 400, "INVALID_REFERENCE_ASSET_ID")
    asset = _known_dataset_assets().get(asset_id)
    if asset is None or not asset[2].is_file():
        raise AppError("Dataset reference image was not found.", 404, "REFERENCE_ASSET_NOT_FOUND")
    return asset[2]


class SceneVisualReferences(BaseModel):
    scene_id: str
    mudra: VisualReference
    bhava: VisualReference
    pose: VisualReference
    confidence_threshold: float


def _unavailable(
    category: Literal["mudra", "bhava", "pose"],
    concept: str | None,
    reason: str,
) -> VisualReference:
    return VisualReference(
        category=category,
        status="unavailable",
        source_type="unavailable",
        reference_status="unavailable",
        concept=concept,
        confidence_threshold=settings.dance_reference_min_confidence,
        evidence_status="Reference unavailable — dataset evidence not found.",
        crop_status="not_applicable",
        unavailable_reason=reason,
    )


def _uploaded_video_ids() -> list[str]:
    video_ids: list[str] = []
    if not settings.frame_output_dir.is_dir():
        return video_ids
    for frame_dir in sorted(settings.frame_output_dir.iterdir()):
        if not frame_dir.is_dir() or not (frame_dir / "manifest.json").is_file():
            continue
        try:
            get_uploaded_video_path(frame_dir.name)
        except AppError:
            continue
        video_ids.append(frame_dir.name)
    return video_ids


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = load_json(path)
    except (OSError, ValueError):
        logger.warning("Dance reference source could not be read: path=%s", path)
        return None
    return value if isinstance(value, dict) else None


def _matching_manifest_frame(
    manifest_frames: list[Any],
    prediction: dict[str, Any],
) -> dict[str, Any] | None:
    frame_number = prediction.get("frame_number")
    filename = prediction.get("filename")
    timestamp = prediction.get("timestamp")
    if (
        not isinstance(frame_number, int)
        or not isinstance(filename, str)
        or Path(filename).name != filename
        or not isinstance(timestamp, (int, float))
        or isinstance(timestamp, bool)
        or not math.isfinite(float(timestamp))
    ):
        return None

    return next(
        (
            frame
            for frame in manifest_frames
            if isinstance(frame, dict)
            and frame.get("frame_number") == frame_number
            and frame.get("filename") == filename
            and isinstance(frame.get("timestamp"), (int, float))
            and abs(float(frame["timestamp"]) - float(timestamp)) < 0.01
        ),
        None,
    )


def _prediction_index(category: Literal["mudra", "bhava"]) -> list[tuple[str, float, str, dict[str, Any]]]:
    label_key = category
    index: list[tuple[str, float, str, dict[str, Any]]] = []
    for video_id in _uploaded_video_ids():
        modality_path = modality_result_path(video_id, category)
        result = _read_json(modality_path)
        if (
            result is None
            or result.get("video_id") != video_id
            or result.get("analysis_id") != video_id
        ):
            continue

        manifest_path = settings.frame_output_dir / video_id / "manifest.json"
        manifest = _read_json(manifest_path)
        manifest_frames = manifest.get("frames") if manifest else None
        if (
            manifest is None
            or manifest.get("video_id") != video_id
            or not isinstance(manifest_frames, list)
        ):
            continue

        predictions = result.get("frames")
        if not isinstance(predictions, list):
            continue
        for prediction in predictions:
            if not isinstance(prediction, dict):
                continue
            label = prediction.get(label_key)
            confidence = prediction.get("confidence")
            if (
                not isinstance(label, str)
                or not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not math.isfinite(float(confidence))
                or not 0 <= float(confidence) <= 1
            ):
                continue
            frame = _matching_manifest_frame(manifest_frames, prediction)
            if frame is None:
                continue
            image_path = settings.frame_output_dir / video_id / frame["filename"]
            if image_path.is_file():
                index.append((label, float(confidence), video_id, frame))
    return index


def _find_prediction_reference(
    category: Literal["mudra", "bhava"],
    requested_label: str | None,
    prediction_index: list[tuple[str, float, str, dict[str, Any]]],
    used_reference_keys: set[str],
    selected_dataset_assets: set[str],
) -> VisualReference:
    if not requested_label:
        return _unavailable(
            category,
            None,
            "No supported classical mapping was provided for this scene.",
        )

    confidence_threshold = settings.dance_reference_min_confidence
    label_predictions = [
        (confidence, video_id, frame)
        for label, confidence, video_id, frame in prediction_index
        if label.casefold() == requested_label.casefold()
    ]
    candidates = [
        (confidence, video_id, frame)
        for confidence, video_id, frame in label_predictions
        if confidence_threshold <= confidence <= 1
    ]

    candidates.sort(key=lambda item: (-item[0], item[1], int(item[2]["frame_number"])))
    for confidence, video_id, frame in candidates:
        filename = frame["filename"]
        source_key = f"video:{video_id}:{filename}"
        if source_key in used_reference_keys:
            continue
        display_filename, crop_status = _prepare_display_frame(category, video_id, filename)
        if category == "bhava" and crop_status != "face_detector_crop":
            continue
        used_reference_keys.add(source_key)
        return VisualReference(
            category=category,
            status="matched",
            source_type="analyzed_video",
            reference_status="model_predicted",
            concept=requested_label,
            predicted_label=requested_label,
            confidence=confidence,
            confidence_threshold=confidence_threshold,
            video_id=video_id,
            frame_number=frame["frame_number"],
            timestamp=float(frame["timestamp"]),
            frame_filename=filename,
            image_url=f"/api/videos/{video_id}/frames/{display_filename}",
            original_frame_url=f"/api/videos/{video_id}/frames/{filename}",
            evidence_status="Saved model prediction; not ground truth or expert-verified.",
            crop_status=crop_status,
        )

    dataset_reference = _find_dataset_reference(
        category,
        requested_label,
        selected_dataset_assets,
    )
    if dataset_reference is not None:
        selected_dataset_assets.add(dataset_reference.asset_id or "")
        return dataset_reference

    if candidates:
        confidence, video_id, frame = candidates[0]
        filename = frame["filename"]
        display_filename, crop_status = _prepare_display_frame(category, video_id, filename)
        if category != "bhava" or crop_status == "face_detector_crop":
            return VisualReference(
                category=category,
                status="matched",
                source_type="analyzed_video",
                reference_status="model_predicted",
                concept=requested_label,
                predicted_label=requested_label,
                confidence=confidence,
                confidence_threshold=confidence_threshold,
                video_id=video_id,
                frame_number=frame["frame_number"],
                timestamp=float(frame["timestamp"]),
                frame_filename=filename,
                image_url=f"/api/videos/{video_id}/frames/{display_filename}",
                original_frame_url=f"/api/videos/{video_id}/frames/{filename}",
                evidence_status="Saved model prediction; not ground truth or expert-verified.",
                crop_status=crop_status,
            )

    if category == "mudra":
        if label_predictions:
            return _unavailable(
                category,
                requested_label,
                (
                    f"No matching mudra prediction met the configured "
                    f"{confidence_threshold:.0%} confidence threshold, and no labelled "
                    f"Mudra dataset image was found for {requested_label}."
                ),
            )
        return _unavailable(
            category,
            requested_label,
            f"No analyzed prediction or labelled Mudra dataset image was found for {requested_label}.",
        )
    if requested_label and candidates:
        return _unavailable(
            category,
            requested_label,
            f"No matching {category} frame contained a localized face crop.",
        )
    return _unavailable(
        category,
        requested_label,
        (
            f"No matching {category} prediction met the configured "
            f"{confidence_threshold:.0%} confidence threshold in analyzed uploads."
        ),
    )


def _find_dataset_reference(
    category: Literal["mudra", "bhava"],
    requested_label: str,
    selected_assets: set[str],
) -> VisualReference | None:
    assets = _known_dataset_assets()
    matching = [
        (asset_id, asset)
        for asset_id, asset in assets.items()
        if asset[0] in (
            {root.name for root in MUDRA_DATASET_ROOTS}
            if category == "mudra"
            else {BHAVA_DATASET_ROOT.name}
        )
        and asset[1].casefold() == requested_label.casefold()
    ]
    if not matching:
        return None
    matching.sort(key=lambda item: item[1][3])
    asset_id, (dataset_name, dataset_label, _, relative_path) = next(
        (
            item
            for item in matching
            if item[0] not in selected_assets
        ),
        matching[0],
    )
    return VisualReference(
        category=category,
        status="matched",
        source_type="project_dataset",
        reference_status="dataset_labelled",
        concept=requested_label,
        dataset_label=dataset_label,
        confidence_threshold=settings.dance_reference_min_confidence,
        image_url=f"/api/story-to-dance/stories/reference-assets/{asset_id}",
        original_frame_url=f"/api/story-to-dance/stories/reference-assets/{asset_id}",
        asset_id=asset_id,
        dataset_name=dataset_name,
        dataset_relative_path=relative_path,
        evidence_status=(
            "Dataset class label from the source folder; not expert-verified."
            if category == "mudra"
            else (
                "Numeric dataset class ID mapped by the saved Bhava model class order; "
                "generic facial-expression data, not a Bharatanatyam-specific or "
                "expert-verified Bhava."
            )
        ),
        crop_status="dataset_image",
    )


def _find_pose_reference(requested_label: str | None) -> VisualReference:
    if not requested_label:
        return _unavailable("pose", None, "No supported pose mapping was provided for this scene.")

    # Current saved pose-events are explicitly unavailable and have no pose labels
    # or frame filenames. A movement concept alone cannot be used as a pose label.
    return _unavailable(
        "pose",
        requested_label,
        "Saved pose analysis has no classified pose evidence or linked frame for this concept.",
    )


def _prepare_display_frame(
    category: Literal["mudra", "bhava"],
    video_id: str,
    source_filename: str,
) -> tuple[str, str]:
    """Prepare a category-appropriate display image without changing the source."""
    try:
        import cv2
    except ImportError:
        logger.warning("OpenCV is unavailable; serving the uncropped source frame.")
        return source_filename, "unprocessed_source_frame"

    source_path = settings.frame_output_dir / video_id / source_filename
    image = cv2.imread(str(source_path))
    if image is None:
        logger.warning("Source frame could not be decoded for reference crop: %s", source_path)
        return source_filename, "unprocessed_source_frame"

    height, width = image.shape[:2]
    if category == "mudra":
        return source_filename, "full_source_frame_no_hand_landmarks"

    crop_status = "unprocessed_source_frame_crop"
    if category == "bhava":
        try:
            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            detector = cv2.CascadeClassifier(str(cascade_path))
            if not detector.empty():
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                faces = detector.detectMultiScale(
                    gray,
                    scaleFactor=1.1,
                    minNeighbors=5,
                    minSize=(max(32, width // 30), max(32, height // 30)),
                )
                if len(faces):
                    x, y, face_width, face_height = max(
                        faces,
                        key=lambda item: int(item[2]) * int(item[3]),
                    )
                    padding_x = int(face_width * 0.55)
                    padding_y = int(face_height * 0.7)
                    left = max(0, int(x) - padding_x)
                    top = max(0, int(y) - padding_y)
                    right = min(width, int(x + face_width + padding_x))
                    bottom = min(height, int(y + face_height + padding_y))
                    crop_status = "face_detector_crop"
                else:
                    return source_filename, "face_not_localized"
            else:
                logger.warning("OpenCV face cascade is unavailable; no Bhava crop can be verified.")
                return source_filename, "face_not_localized"
        except cv2.error:
            logger.exception("Face crop detection failed; no Bhava crop can be verified.")
            return source_filename, "face_not_localized"

    if right <= left or bottom <= top:
        logger.warning("Reference crop bounds were invalid: video_id=%s frame=%s", video_id, source_filename)
        return source_filename, "unprocessed_source_frame"

    crop_filename = f"reference_{category}_{Path(source_filename).stem}.jpg"
    crop_path = settings.frame_output_dir / video_id / crop_filename
    if not crop_path.is_file() and not cv2.imwrite(
        str(crop_path),
        image[top:bottom, left:right],
        [cv2.IMWRITE_JPEG_QUALITY, 92],
    ):
        logger.warning("Derived reference crop could not be written: %s", crop_path)
        return source_filename, "unprocessed_source_frame"
    return crop_filename, crop_status


def get_scene_visual_references(
    request: SceneVisualReferencesRequest,
) -> list[SceneVisualReferences]:
    confidence_threshold = settings.dance_reference_min_confidence
    if not math.isfinite(confidence_threshold) or not 0 <= confidence_threshold <= 1:
        raise ValueError("DANCE_REFERENCE_MIN_CONFIDENCE must be between 0 and 1.")

    prediction_indexes: dict[str, list[tuple[str, float, str, dict[str, Any]]]] = {}
    if any(scene.mudra_label for scene in request.scenes):
        prediction_indexes["mudra"] = _prediction_index("mudra")
    if any(scene.bhava_label for scene in request.scenes):
        prediction_indexes["bhava"] = _prediction_index("bhava")
    selected_assets: set[str] = set()
    selected_bhava_assets: set[str] = set()
    used_reference_keys: dict[str, set[str]] = {
        "mudra": set(),
        "bhava": set(),
    }
    results = [
        SceneVisualReferences(
            scene_id=scene.scene_id,
            mudra=_find_prediction_reference(
                "mudra",
                scene.mudra_label,
                prediction_indexes.get("mudra", []),
                used_reference_keys["mudra"],
                selected_assets,
            ),
            bhava=_find_prediction_reference(
                "bhava",
                scene.bhava_label,
                prediction_indexes.get("bhava", []),
                used_reference_keys["bhava"],
                selected_bhava_assets,
            ),
            pose=_find_pose_reference(scene.pose_label),
            confidence_threshold=confidence_threshold,
        )
        for scene in request.scenes
    ]
    for category in ("mudra", "bhava", "pose"):
        references_by_source: dict[str, list[str]] = {}
        for result in results:
            reference = getattr(result, category)
            if reference.source_type == "analyzed_video":
                source_key = f"video:{reference.video_id}:{reference.frame_filename}"
            elif reference.source_type == "project_dataset":
                source_key = f"dataset:{reference.asset_id}"
            else:
                continue
            references_by_source.setdefault(source_key, []).append(result.scene_id)
        for result in results:
            reference = getattr(result, category)
            if reference.source_type == "analyzed_video":
                source_key = f"video:{reference.video_id}:{reference.frame_filename}"
            elif reference.source_type == "project_dataset":
                source_key = f"dataset:{reference.asset_id}"
            else:
                continue
            reference.reused_in_scenes = [
                scene_id
                for scene_id in references_by_source[source_key]
                if scene_id != result.scene_id
            ]
    return results
