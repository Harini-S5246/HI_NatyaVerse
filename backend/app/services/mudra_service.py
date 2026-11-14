from __future__ import annotations

import logging
import math
from collections import Counter
from pathlib import Path

from app.config import settings
from app.core.errors import AppError
from app.models.model_manager import model_manager
from app.services.knowledge_service import (
    build_evidence,
    ground_mudra,
    is_reliable_recognition_confidence,
)
from app.services.result_service import save_modality_result, save_result
from app.utils.json_utils import load_json

logger = logging.getLogger(__name__)

DEFAULT_SEGMENT_GAP_SECONDS = 1.0
LOW_CONFIDENCE_THRESHOLD = 0.5
MISSING_PREDICTION_STATUSES = {"missing", "unavailable", "invalid", "no_hand_detection"}


def _normalise_prediction(prediction: dict, *, default_frame_number: int | None = None) -> dict | None:
    """Return a usable model prediction, skipping invalid/missing observations."""
    if not isinstance(prediction, dict):
        return None

    label = prediction.get("mudra")
    if not isinstance(label, str) or not label.strip():
        return None

    try:
        timestamp = float(prediction.get("timestamp"))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(timestamp) or timestamp < 0:
        return None

    frame_number = prediction.get("frame_number")
    if frame_number is None:
        frame_number = prediction.get("frame_index", default_frame_number)
    if not isinstance(frame_number, int):
        frame_number = default_frame_number

    confidence = prediction.get("confidence")
    if confidence is None or isinstance(confidence, bool):
        confidence = None
    else:
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = None
        if not math.isfinite(confidence):
            confidence = None

    status = prediction.get("status")
    if isinstance(status, str):
        status = status.strip().lower()
        if status in MISSING_PREDICTION_STATUSES:
            return None

    return {
        "mudra": label.strip(),
        "timestamp": timestamp,
        "frame_number": frame_number,
        "confidence": confidence,
        "status": status or "valid",
        "grounded": bool(prediction.get("grounded")),
        "meaning": prediction.get("meaning"),
    }


def _detect_repeated_patterns(segment_labels: list[str]) -> list[dict]:
    """Find repeated consecutive mudra sequences without attaching cultural meaning."""
    if len(segment_labels) < 2:
        return []

    patterns: list[dict] = []
    max_pattern_length = min(4, len(segment_labels) // 2)
    for pattern_length in range(1, max_pattern_length + 1):
        index = 0
        while index + (pattern_length * 2) <= len(segment_labels):
            candidate = segment_labels[index:index + pattern_length]
            next_window = segment_labels[index + pattern_length:index + (pattern_length * 2)]
            if candidate == next_window:
                occurrences = [index]
                cursor = index + pattern_length
                while cursor + pattern_length <= len(segment_labels):
                    window = segment_labels[cursor:cursor + pattern_length]
                    if window == candidate:
                        occurrences.append(cursor)
                        cursor += pattern_length
                    else:
                        break
                if len(occurrences) >= 2:
                    patterns.append({
                        "pattern_length": pattern_length,
                        "pattern": candidate,
                        "occurrence_indices": occurrences,
                        "pattern_id": f"pattern-{pattern_length}-{index + 1}",
                    })
                index = cursor
            else:
                index += 1
    return patterns


def _build_temporal_sequence(predictions: list[dict], *, video_id: str | None = None, analysis_id: str | None = None, max_gap_seconds: float = DEFAULT_SEGMENT_GAP_SECONDS) -> dict:
    """Build a structured temporal sequence while keeping the legacy mudra_events output unchanged."""
    sequence_id = f"{analysis_id or video_id or 'mudra'}-temporal-sequence"
    valid_predictions = []
    missing_prediction_count = 0
    for index, prediction in enumerate(predictions):
        normalised = _normalise_prediction(prediction, default_frame_number=index)
        if normalised is None:
            if isinstance(prediction, dict) and not prediction.get("mudra"):
                missing_prediction_count += 1
            continue
        valid_predictions.append(normalised)

    valid_predictions.sort(key=lambda item: (
        float(item["timestamp"]),
        int(item["frame_number"]) if isinstance(item["frame_number"], int) else 0,
    ))

    segments: list[dict] = []
    for prediction in valid_predictions:
        if not segments or segments[-1]["mudra_label"] != prediction["mudra"] or (prediction["timestamp"] - segments[-1]["end_timestamp"]) > max_gap_seconds:
            segments.append({
                "video_id": video_id,
                "analysis_id": analysis_id,
                "sequence_id": sequence_id,
                "segment_id": None,
                "mudra_label": prediction["mudra"],
                "start_timestamp": prediction["timestamp"],
                "end_timestamp": prediction["timestamp"],
                "duration": 0.0,
                "frame_indices": [prediction["frame_number"]] if prediction["frame_number"] is not None else [],
                "supporting_evidence_ids": [f"{analysis_id or video_id or 'mudra'}-frame-{prediction['frame_number']}"] if prediction["frame_number"] is not None else [],
                "confidence": {
                    "mean": prediction["confidence"],
                    "min": prediction["confidence"],
                    "max": prediction["confidence"],
                    "source": "model_prediction",
                    "low_confidence": prediction["confidence"] is not None and prediction["confidence"] < LOW_CONFIDENCE_THRESHOLD,
                },
                "previous_segment": None,
                "next_segment": None,
                "transition": None,
                "repeated_pattern": None,
                "uncertainty_status": "low_confidence" if prediction["confidence"] is not None and prediction["confidence"] < LOW_CONFIDENCE_THRESHOLD else "normal",
                "status": prediction.get("status", "valid"),
            })
        else:
            current = segments[-1]
            current["end_timestamp"] = prediction["timestamp"]
            current["duration"] = round(current["end_timestamp"] - current["start_timestamp"], 6)
            frame_number = prediction["frame_number"]
            if frame_number is not None:
                current["frame_indices"].append(frame_number)
                current["supporting_evidence_ids"].append(f"{analysis_id or video_id or 'mudra'}-frame-{frame_number}")
            current["confidence"]["mean"] = round((current["confidence"]["mean"] + (prediction["confidence"] if prediction["confidence"] is not None else 0.0)) / 2, 6) if prediction["confidence"] is not None else current["confidence"]["mean"]
            if prediction["confidence"] is not None:
                current["confidence"]["min"] = min(current["confidence"]["min"], prediction["confidence"])
                current["confidence"]["max"] = max(current["confidence"]["max"], prediction["confidence"])
            current["confidence"]["low_confidence"] = current["confidence"]["mean"] < LOW_CONFIDENCE_THRESHOLD
            current["uncertainty_status"] = "low_confidence" if current["confidence"]["mean"] < LOW_CONFIDENCE_THRESHOLD else "normal"
            current["status"] = prediction.get("status", current["status"])

    for index, segment in enumerate(segments):
        segment["segment_id"] = f"{sequence_id}-segment-{index + 1}"
        segment["duration"] = round(segment["end_timestamp"] - segment["start_timestamp"], 6)
        if index > 0:
            previous = segments[index - 1]
            segment["previous_segment"] = previous["segment_id"]
            segment["transition"] = None
            if previous["mudra_label"] != segment["mudra_label"]:
                segment["transition"] = {
                    "transition_id": f"{sequence_id}-transition-{index}",
                    "previous_segment": previous["segment_id"],
                    "previous_mudra": previous["mudra_label"],
                    "next_segment": segment["segment_id"],
                    "next_mudra": segment["mudra_label"],
                    "transition_timestamp": segment["start_timestamp"],
                    "previous_end_timestamp": previous["end_timestamp"],
                    "next_start_timestamp": segment["start_timestamp"],
                    "transition_type": "mudra_change",
                }
        if index < len(segments) - 1:
            segments[index]["next_segment"] = segments[index + 1]["segment_id"]

    repeated_patterns = _detect_repeated_patterns([segment["mudra_label"] for segment in segments])
    for pattern in repeated_patterns:
        pattern_id = pattern["pattern_id"]
        occurrence_timestamps = []
        for occurrence_index in pattern["occurrence_indices"]:
            segment = segments[occurrence_index]
            occurrence_timestamps.append({
                "segment_id": segment["segment_id"],
                "start_timestamp": segment["start_timestamp"],
                "end_timestamp": segment["end_timestamp"],
            })
        for occurrence_index in pattern["occurrence_indices"]:
            segments[occurrence_index]["repeated_pattern"] = {
                "pattern_id": pattern_id,
                "pattern": pattern["pattern"],
                "occurrence_count": len(pattern["occurrence_indices"]),
                "occurrence_timestamps": occurrence_timestamps,
                "meaning_inferred": False,
            }

    for index, segment in enumerate(segments):
        if index < len(segments) - 1:
            segment["next_segment"] = segments[index + 1]["segment_id"]
        else:
            segment["next_segment"] = None

    uncertainty_counts = {
        "missing_prediction_count": missing_prediction_count,
        "low_confidence_segment_count": sum(1 for segment in segments if segment["uncertainty_status"] == "low_confidence"),
        "uncertain_segment_ids": [segment["segment_id"] for segment in segments if segment["uncertainty_status"] != "normal"],
    }

    return {
        "video_id": video_id,
        "analysis_id": analysis_id,
        "sequence_id": sequence_id,
        "segments": segments,
        "transitions": [segment["transition"] for segment in segments if segment["transition"] is not None],
        "repeated_patterns": [
            {
                "pattern_id": pattern["pattern_id"],
                "pattern": pattern["pattern"],
                "occurrence_count": len(pattern["occurrence_indices"]),
                "occurrence_timestamps": [segments[index]["start_timestamp"] for index in pattern["occurrence_indices"]],
                "meaning_inferred": False,
            }
            for pattern in repeated_patterns
        ],
        "uncertainty_summary": uncertainty_counts,
        "max_gap_seconds": max_gap_seconds,
    }


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
    logger.info("Mudra inference starting: video_id=%s frames_dir=%s frames_discovered=%s", video_id, frame_dir, len(manifest["frames"]))
    try:
        model = model_manager.get("mudra")
        logger.info("Mudra model loaded: video_id=%s classes=%s", video_id, len(getattr(model, "class_names", None) or []))
    except Exception as exc:
        logger.error("Mudra model unavailable: video_id=%s error=%s", video_id, exc)
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
        knowledge = (
            ground_mudra(label)
            if is_reliable_recognition_confidence(confidence)
            else None
        )
        predictions.append({
            "frame_number": frame_number,
            "timestamp": float(timestamp),
            "filename": filename,
            "mudra": label,
            "confidence": float(confidence),
            "grounded": knowledge is not None,
            "meaning": knowledge["meaning"] if knowledge else None,
            "status": "grounded" if knowledge else "unresolved",
            "knowledge_status": knowledge["verification_status"] if knowledge else None,
            "verification_status": knowledge["verification_status"] if knowledge else None,
            "claim_id": knowledge["claim_id"] if knowledge else None,
            "source_references": knowledge["source_references"] if knowledge else [],
            "uncertainty_notes": knowledge["uncertainty_notes"] if knowledge else [],
            "uncertainty_reason": (
                None if knowledge else
                "Meaning withheld because recognition confidence is missing, invalid, or below 0.5."
                if not is_reliable_recognition_confidence(confidence) else
                "Meaning unavailable in current knowledge base."
            ),
        })

    events = group_mudra_events(predictions)
    labels = [prediction["mudra"] for prediction in predictions]
    grounded_count = sum(1 for prediction in predictions if prediction["grounded"])
    logger.info("Mudra inference completed: video_id=%s frames_analyzed=%s unique_mudras=%s dominant=%s", video_id, len(predictions), len(set(labels)), Counter(labels).most_common(1)[0][0] if labels else None)
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
                    "knowledge_status": knowledge["verification_status"] if knowledge else None,
                    "meaning": knowledge["meaning"] if knowledge else None,
                    "timestamps": [event["start_time"], event["end_time"]],
                    "verification_status": knowledge["verification_status"] if knowledge else None,
                    "claim_id": knowledge["claim_id"] if knowledge else None,
                    "source_references": knowledge["source_references"] if knowledge else [],
                    "uncertainty_notes": knowledge["uncertainty_notes"] if knowledge else [],
                    "uncertainty_reason": (
                        None if knowledge else
                        "Meaning withheld because recognition confidence is missing, invalid, or below 0.5."
                        if not is_reliable_recognition_confidence(event["confidence"]) else
                        "Meaning unavailable in current knowledge base."
                    ),
                }
                for event in events
                for knowledge in [
                    ground_mudra(event["mudra"])
                    if is_reliable_recognition_confidence(event["confidence"])
                    else None
                ]
            ]
        },
    }
    response["temporal_sequence"] = _build_temporal_sequence(predictions, video_id=video_id, analysis_id=video_id)
    response["evidence"] = build_evidence(response)
    save_result(response)
    save_modality_result(video_id, "mudra", response)
    logger.info("Mudra result saved: video_id=%s", video_id)
    return response
