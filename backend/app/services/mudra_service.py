from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.config import settings
from app.core.errors import AppError
from app.models.model_manager import model_manager
from app.services.knowledge_service import build_evidence, ground_mudra
from app.services.result_service import save_modality_result, save_result
from app.utils.json_utils import load_json


def group_mudra_events(predictions: list[dict]) -> list[dict]:
    """Group consecutive identical frame labels into temporal Mudra events."""
    events: list[dict] = []
    for prediction in predictions:
        if events and events[-1]["mudra"] == prediction["mudra"]:
            event = events[-1]
            event["end_time"] = prediction["timestamp"]
            event["frame_count"] += 1
            event["_confidence_total"] += prediction["confidence"]
            event["confidence"] = event["_confidence_total"] / event["frame_count"]
            continue

        events.append({
            "mudra": prediction["mudra"],
            "start_time": prediction["timestamp"],
            "end_time": prediction["timestamp"],
            "confidence": prediction["confidence"],
            "frame_count": 1,
            "_confidence_total": prediction["confidence"],
        })

    for event in events:
        event.pop("_confidence_total")
        event["confidence"] = round(event["confidence"], 6)
    return events


def _load_frame_manifest(video_id: str) -> tuple[Path, dict]:
    frame_dir = settings.frame_output_dir / video_id
    manifest_path = frame_dir / "manifest.json"
    if not manifest_path.is_file():
        raise AppError("Frame manifest was not found for this video.", 404, "FRAME_MANIFEST_NOT_FOUND")

    try:
        manifest = load_json(manifest_path)
    except Exception as exc:
        raise AppError("Frame manifest could not be read.", 400, "INVALID_FRAME_MANIFEST") from exc

    if not isinstance(manifest, dict):
        raise AppError("Frame manifest is invalid for this video.", 400, "INVALID_FRAME_MANIFEST")
    frames = manifest.get("frames")
    frame_count = manifest.get("frame_count")
    if manifest.get("video_id") != video_id or not isinstance(frames, list) or not isinstance(frame_count, int) or frame_count != len(frames):
        raise AppError("Frame manifest is invalid for this video.", 400, "INVALID_FRAME_MANIFEST")
    return frame_dir, manifest


def classify_video_frames(video_id: str) -> dict:
    """Run the existing Mudra image classifier over manifest-listed JPEG frames."""
    frame_dir, manifest = _load_frame_manifest(video_id)
    try:
        model = model_manager.get("mudra")
    except Exception as exc:
        raise AppError("Mudra model is unavailable.", 503, "MUDRA_MODEL_UNAVAILABLE") from exc

    try:
        import cv2
    except ImportError as exc:
        raise AppError("Mudra classification requires OpenCV.", 503, "VIDEO_BACKEND_UNAVAILABLE") from exc

    predictions: list[dict] = []
    for entry in manifest["frames"]:
        if not isinstance(entry, dict):
            raise AppError("Frame manifest contains an invalid frame entry.", 400, "INVALID_FRAME_MANIFEST")
        frame_number, timestamp, filename = entry.get("frame_number"), entry.get("timestamp"), entry.get("filename")
        if not isinstance(frame_number, int) or not isinstance(timestamp, (int, float)) or not isinstance(filename, str):
            raise AppError("Frame manifest contains an invalid frame entry.", 400, "INVALID_FRAME_MANIFEST")
        if Path(filename).name != filename or Path(filename).suffix.lower() not in {".jpg", ".jpeg"}:
            raise AppError("Frame manifest contains an unsafe frame filename.", 400, "INVALID_FRAME_MANIFEST")

        frame_path = frame_dir / filename
        if not frame_path.is_file():
            raise AppError(f"Extracted frame is missing: {filename}", 404, "FRAME_NOT_FOUND")
        frame = cv2.imread(str(frame_path))
        if frame is None:
            raise AppError(f"Extracted frame is not a valid image: {filename}", 400, "INVALID_FRAME")

        try:
            prediction = model.predict(frame)
        except Exception as exc:
            raise AppError("Mudra inference failed.", 500, "MUDRA_INFERENCE_FAILED") from exc
        label = prediction.get("label")
        confidence = prediction.get("confidence")
        if not isinstance(label, str) or not isinstance(confidence, (int, float)):
            raise AppError("Mudra model returned an invalid prediction.", 500, "MUDRA_INFERENCE_FAILED")
        knowledge = ground_mudra(label)
        predictions.append({
            "frame_number": frame_number,
            "timestamp": float(timestamp),
            "filename": filename,
            "mudra": label,
            "confidence": float(confidence),
            "grounded": knowledge is not None,
            "meaning": knowledge["meaning"] if knowledge else None,
            "status": "grounded" if knowledge else "unresolved",
        })

    events = group_mudra_events(predictions)
    labels = [prediction["mudra"] for prediction in predictions]
    grounded_count = sum(1 for prediction in predictions if prediction["grounded"])
    response = {
        "analysis_id": video_id,
        "video_id": video_id,
        "status": "completed",
        "frame_count": len(manifest["frames"]),
        "prediction_count": len(predictions),
        "grounded_count": grounded_count,
        "unresolved_count": len(predictions) - grounded_count,
        "mudra_events": events,
        "frames": predictions,
        "summary": {
            "unique_mudra_count": len(set(labels)),
            "dominant_mudra": Counter(labels).most_common(1)[0][0] if labels else None,
            "average_confidence": round(sum(item["confidence"] for item in predictions) / len(predictions), 6) if predictions else 0.0,
        },
        "mudra": {
            "detections": [
                {
                    "name": event["mudra"],
                    "confidence": event["confidence"],
                    "grounded": knowledge is not None,
                    "status": "grounded" if knowledge else "unresolved",
                    "meaning": knowledge["meaning"] if knowledge else None,
                    "timestamps": [event["start_time"], event["end_time"]],
                }
                for event in events
                for knowledge in [ground_mudra(event["mudra"])]
            ]
        },
    }
    response["evidence"] = build_evidence(response)
    save_result(response)
    save_modality_result(video_id, "mudra", response)
    return response
