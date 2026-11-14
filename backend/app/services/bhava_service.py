"""Bhava (emotional expression) classification over stored extracted frames.

This service mirrors the established Mudra temporal-pipeline pattern:

* Reads ``backend/frames/<video_id>/manifest.json`` (reusing the exact
  manifest loader implemented for the Mudra service — no duplication).
* Streams the stored JPEG frames one at a time and runs the existing
  Bhava image classifier (EfficientNetB0, 7 Navarasa classes) via the
  shared ``ModelManager``.
* Groups consecutive identical Bhava predictions into temporal events.
* Persists the result through the existing ``result_service``.
"""
from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path

from app.core.errors import AppError
from app.models.model_manager import model_manager
from app.services.knowledge_service import build_evidence
from app.services.mudra_service import _load_frame_manifest
from app.services.result_service import save_modality_result, save_result

logger = logging.getLogger(__name__)


def group_bhava_events(predictions: list[dict]) -> list[dict]:
    """Group consecutive identical frame labels into temporal Bhava events.

    Only consecutive identical labels are merged.  A label that reappears
    later (after a different label) starts a NEW event.
    """
    events: list[dict] = []
    for prediction in predictions:
        if events and events[-1]["bhava"] == prediction["bhava"]:
            event = events[-1]
            event["end_time"] = prediction["timestamp"]
            event["frame_count"] += 1
            event["_confidence_total"] += prediction["confidence"]
            event["confidence"] = event["_confidence_total"] / event["frame_count"]
            continue

        events.append({
            "bhava": prediction["bhava"],
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


def classify_video_bhava(video_id: str) -> dict:
    """Run the existing Bhava image classifier over manifest-listed JPEG frames."""
    frame_dir, manifest = _load_frame_manifest(video_id)
    logger.info("Bhava inference starting: video_id=%s frames_dir=%s frames_discovered=%s", video_id, frame_dir, len(manifest["frames"]))
    try:
        model = model_manager.get("bhava")
        logger.info("Bhava model loaded: video_id=%s classes=%s", video_id, len(getattr(model, "class_names", None) or []))
    except Exception as exc:
        logger.error("Bhava model unavailable: video_id=%s error=%s", video_id, exc)
        raise AppError("Bhava model is unavailable.", 503, "BHAVA_MODEL_UNAVAILABLE") from exc

    try:
        import cv2
    except ImportError as exc:
        raise AppError("Bhava classification requires OpenCV.", 503, "VIDEO_BACKEND_UNAVAILABLE") from exc

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
            raise AppError("Bhava inference failed.", 500, "BHAVA_INFERENCE_FAILED") from exc
        label = prediction.get("label")
        confidence = prediction.get("confidence")
        if not isinstance(label, str) or not isinstance(confidence, (int, float)):
            raise AppError("Bhava model returned an invalid prediction.", 500, "BHAVA_INFERENCE_FAILED")
        predictions.append({
            "frame_number": frame_number,
            "timestamp": float(timestamp),
            "filename": filename,
            "bhava": label,
            "confidence": float(confidence),
        })

    events = group_bhava_events(predictions)
    labels = [prediction["bhava"] for prediction in predictions]
    dominant = Counter(labels).most_common(1)[0][0] if labels else None
    dominant_frames = [p for p in predictions if p["bhava"] == dominant] if dominant else []
    dominant_confidence = (
        round(sum(p["confidence"] for p in dominant_frames) / len(dominant_frames), 6)
        if dominant_frames
        else None
    )

    response = {
        "analysis_id": video_id,
        "video_id": video_id,
        "status": "completed",
        "frame_count": len(manifest["frames"]),
        "prediction_count": len(predictions),
        "bhava_events": events,
        "frames": predictions,
        "summary": {
            "unique_bhava_count": len(set(labels)),
            "dominant_bhava": dominant,
            "average_confidence": round(sum(item["confidence"] for item in predictions) / len(predictions), 6) if predictions else 0.0,
        },
        "bhava": {
            "dominant_emotion": dominant,
            "confidence": dominant_confidence,
            "detections": [
                {
                    "name": event["bhava"],
                    "confidence": event["confidence"],
                    "timestamps": [event["start_time"], event["end_time"]],
                }
                for event in events
            ],
            "segments": [
                {
                    "label": event["bhava"],
                    "start": event["start_time"],
                    "end": event["end_time"],
                    "confidence": event["confidence"],
                }
                for event in events
            ],
        },
    }
    response["evidence"] = build_evidence(response)
    save_result(response)
    save_modality_result(video_id, "bhava", response)
    logger.info("Bhava inference completed: video_id=%s frames_analyzed=%s dominant=%s", video_id, len(predictions), dominant)
    return response
